"""Quote-grounded evidence-set kernel for disconnected OpenAlex studies.

Scope-link v4 required one source to express the whole topic relation in one
sentence.  The completed diagnostic found both provider noise and useful
sources whose contribution was distributed across papers.  This candidate
therefore treats a model as a bounded proposal mechanism: two order-reversed
passes may assign code-owned roles only when every assignment quotes the title
or abstract.  Deterministic code verifies those quotes, requires pass
agreement, and chooses the smallest covering set of at most three sources.

This module contains no provider client, model client, retry loop, label access
or production import.  Malformed output and disagreement become ABSTAIN; they
never trigger a hidden repair call.
"""

from __future__ import annotations

import hashlib
import json
import re
from itertools import combinations
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from academic_agent.openalex_claim_scope import OpenAlexClaimScopeCandidate


EvidenceRoleKind = Literal["required", "scope", "supporting"]
JudgeAction = Literal["KEEP", "ABSTAIN"]
JudgeQuoteField = Literal["title", "abstract"]
JudgePassState = Literal["valid", "malformed", "contract_invalid"]
EvidenceSetAction = Literal["SELECT", "ABSTAIN"]
JudgePassErrorCode = Literal[
    "response_too_large",
    "schema_invalid",
    "case_id_mismatch",
    "candidate_order_mismatch",
]
CandidateAbstentionReason = Literal[
    "judge_pass_invalid",
    "judge_abstained",
    "judge_action_disagreement",
    "judge_role_disagreement",
    "unknown_role",
    "invalid_quote",
    "insufficient_required_roles",
    "insufficient_context_roles",
    "missing_title_anchor",
]
CaseAbstentionReason = Literal["no_valid_candidates", "no_covering_set"]

_ROLE_ID_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"
_CASE_ID_PATTERN = r"^[A-Z][0-9]{2}$"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_WHITESPACE = re.compile(r"\s+")
_MAX_RAW_RESPONSE_CHARACTERS = 200_000


class EvidenceSetContractError(ValueError):
    """Raised when code-owned inputs cannot satisfy the frozen contract."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _model_sha256(value: BaseModel) -> str:
    return _sha256_text(value.model_dump_json(exclude_none=False))


def _normalized_quote_text(value: str) -> str:
    """Normalize layout only; lexical case and characters remain evidence."""

    # The protocol permits line-ending and Unicode-whitespace normalization so
    # a copied sentence is not rejected because JSON flattened its layout.  It
    # deliberately does not case-fold, stem, translate, or normalize Unicode
    # characters because each of those would admit a paraphrase as a quote.
    return _WHITESPACE.sub(" ", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


class EvidenceSetRoleSpec(BaseModel):
    """One code-owned semantic role described without lexical answer keys."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role_id: str = Field(pattern=_ROLE_ID_PATTERN)
    description: str = Field(min_length=10, max_length=600)


class EvidenceSetRoleProfile(BaseModel):
    """Required, scope and supporting roles for one frozen research topic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_roles: tuple[EvidenceSetRoleSpec, ...] = Field(
        min_length=2,
        max_length=4,
    )
    scope_roles: tuple[EvidenceSetRoleSpec, ...] = Field(
        min_length=1,
        max_length=4,
    )
    supporting_roles: tuple[EvidenceSetRoleSpec, ...] = Field(
        min_length=2,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_unique_roles(self) -> "EvidenceSetRoleProfile":
        roles = (*self.required_roles, *self.scope_roles, *self.supporting_roles)
        role_ids = tuple(role.role_id for role in roles)
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("evidence-set role IDs must be unique")
        return self

    def sha256(self) -> str:
        """Bind every role identifier and natural-language description."""

        return _model_sha256(self)

    def role_kinds(self) -> dict[str, EvidenceRoleKind]:
        """Return the code-owned role classification used after judging."""

        return {
            **{role.role_id: "required" for role in self.required_roles},
            **{role.role_id: "scope" for role in self.scope_roles},
            **{role.role_id: "supporting" for role in self.supporting_roles},
        }


class EvidenceSetSelectionContract(BaseModel):
    """Deterministic per-source and collection coverage requirements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_roles_covered: Literal["all"] = "all"
    minimum_scope_roles: int = Field(ge=1, le=4)
    minimum_supporting_roles: int = Field(ge=1, le=8)
    maximum_selected_sources_per_case: int = Field(ge=1, le=3)
    minimum_candidate_required_roles: int = Field(ge=1, le=4)
    minimum_candidate_context_roles: int = Field(ge=1, le=8)
    minimum_candidate_title_anchor_roles: int = Field(ge=1, le=8)

    def sha256(self) -> str:
        """Bind every source-eligibility and set-cover threshold."""

        return _model_sha256(self)


class JudgeRoleInput(BaseModel):
    """One role visible to the label-blind semantic judge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role_id: str = Field(pattern=_ROLE_ID_PATTERN)
    role_kind: EvidenceRoleKind
    description: str = Field(min_length=10, max_length=600)


class JudgeCandidateInput(BaseModel):
    """The complete candidate surface allowed to cross the model boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_sha256: str = Field(pattern=_SHA256_PATTERN)
    title: str = Field(min_length=5, max_length=600)
    abstract: str = Field(min_length=1, max_length=8000)


class JudgeBatchInput(BaseModel):
    """One immutable judge request; no URL or provider metadata can enter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=_CASE_ID_PATTERN)
    topic: str = Field(min_length=20, max_length=300)
    pass_number: Literal[1, 2]
    roles: tuple[JudgeRoleInput, ...] = Field(min_length=5, max_length=16)
    candidates: tuple[JudgeCandidateInput, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _validate_unique_inputs(self) -> "JudgeBatchInput":
        role_ids = tuple(role.role_id for role in self.roles)
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("judge input role IDs must be unique")
        candidate_ids = tuple(item.candidate_sha256 for item in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("judge input candidate identities must be unique")
        return self

    def sha256(self) -> str:
        """Bind the exact order and evidence text crossing the judge seam."""

        return _model_sha256(self)


class JudgeRoleQuote(BaseModel):
    """One model-proposed role backed by a purported source-text quote."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role_id: str = Field(pattern=_ROLE_ID_PATTERN)
    field: JudgeQuoteField
    quote: str = Field(min_length=1, max_length=8000)


class JudgeCandidateDecision(BaseModel):
    """One KEEP/ABSTAIN proposal in an otherwise all-row batch response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_sha256: str = Field(pattern=_SHA256_PATTERN)
    action: JudgeAction
    role_quotes: tuple[JudgeRoleQuote, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def _validate_action_shape(self) -> "JudgeCandidateDecision":
        role_ids = tuple(item.role_id for item in self.role_quotes)
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("judge decision role IDs must be unique")
        if self.action == "KEEP" and not self.role_quotes:
            raise ValueError("KEEP requires at least one quoted role")
        if self.action == "ABSTAIN" and self.role_quotes:
            raise ValueError("ABSTAIN cannot carry role quotes")
        return self


class JudgeBatchResponse(BaseModel):
    """Strict JSON response containing one decision for every input row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=_CASE_ID_PATTERN)
    candidate_order: tuple[str, ...] = Field(min_length=1, max_length=8)
    decisions: tuple[JudgeCandidateDecision, ...] = Field(
        min_length=1,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_complete_order(self) -> "JudgeBatchResponse":
        if any(re.fullmatch(_SHA256_PATTERN, value) is None for value in self.candidate_order):
            raise ValueError("candidate_order contains an invalid identity")
        if len(self.candidate_order) != len(set(self.candidate_order)):
            raise ValueError("candidate_order identities must be unique")
        decision_ids = tuple(item.candidate_sha256 for item in self.decisions)
        if decision_ids != self.candidate_order:
            raise ValueError("decisions must cover candidate_order in exact order")
        return self


class JudgePassAudit(BaseModel):
    """Parse and contract state for one raw model response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pass_number: Literal[1, 2]
    state: JudgePassState
    raw_response_sha256: str = Field(pattern=_SHA256_PATTERN)
    input_sha256: str = Field(pattern=_SHA256_PATTERN)
    error_code: JudgePassErrorCode | None = None
    response: JudgeBatchResponse | None = None

    @model_validator(mode="after")
    def _validate_state_shape(self) -> "JudgePassAudit":
        if self.state == "valid":
            if self.response is None or self.error_code is not None:
                raise ValueError("valid judge pass requires only a parsed response")
        elif self.response is not None or self.error_code is None:
            raise ValueError("invalid judge pass requires only an error code")
        return self


class VerifiedRoleQuote(BaseModel):
    """A consensus role whose two independently returned quotes both verify."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role_id: str = Field(pattern=_ROLE_ID_PATTERN)
    role_kind: EvidenceRoleKind
    first_field: JudgeQuoteField
    first_quote: str
    second_field: JudgeQuoteField
    second_quote: str


class EvidenceSetCandidateAudit(BaseModel):
    """One all-row decision after consensus, quote and contribution checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_sha256: str = Field(pattern=_SHA256_PATTERN)
    provider_result_index: int = Field(ge=0)
    action: JudgeAction
    first_action: JudgeAction | None
    second_action: JudgeAction | None
    judge_agreement: bool
    required_role_ids: tuple[str, ...]
    scope_role_ids: tuple[str, ...]
    supporting_role_ids: tuple[str, ...]
    title_anchor_role_ids: tuple[str, ...]
    verified_role_quotes: tuple[VerifiedRoleQuote, ...]
    abstention_reasons: tuple[CandidateAbstentionReason, ...]

    @model_validator(mode="after")
    def _validate_action_shape(self) -> "EvidenceSetCandidateAudit":
        role_ids = (
            *self.required_role_ids,
            *self.scope_role_ids,
            *self.supporting_role_ids,
        )
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("candidate role assignments must be unique")
        verified_ids = tuple(item.role_id for item in self.verified_role_quotes)
        if set(verified_ids) != set(role_ids):
            raise ValueError("verified quotes must cover every assigned role")
        if not set(self.title_anchor_role_ids).issubset(role_ids):
            raise ValueError("title anchors must be assigned candidate roles")
        if self.action == "KEEP" and self.abstention_reasons:
            raise ValueError("KEEP candidate cannot carry abstention reasons")
        if self.action == "ABSTAIN" and not self.abstention_reasons:
            raise ValueError("ABSTAIN candidate requires an explicit reason")
        return self


class SelectedEvidenceSource(BaseModel):
    """One selected source and every consensus role delivered downstream."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_sha256: str = Field(pattern=_SHA256_PATTERN)
    provider_result_index: int = Field(ge=0)
    role_ids: tuple[str, ...] = Field(min_length=1)


class EvidenceSetCaseAudit(BaseModel):
    """Complete zero-network decision at the future runner/review seam."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=_CASE_ID_PATTERN)
    topic: str = Field(min_length=20, max_length=300)
    action: EvidenceSetAction
    profile_sha256: str = Field(pattern=_SHA256_PATTERN)
    selection_contract_sha256: str = Field(pattern=_SHA256_PATTERN)
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    planner_trigger_connected: Literal[False] = False
    provider_candidate_count: int = Field(ge=1, le=8)
    first_pass: JudgePassAudit
    second_pass: JudgePassAudit
    candidate_decisions: tuple[EvidenceSetCandidateAudit, ...] = Field(
        min_length=1,
        max_length=8,
    )
    selected_sources: tuple[SelectedEvidenceSource, ...] = Field(max_length=3)
    covered_required_role_ids: tuple[str, ...]
    covered_scope_role_ids: tuple[str, ...]
    covered_supporting_role_ids: tuple[str, ...]
    judge_agreement_numerator: int = Field(ge=0, le=8)
    judge_agreement_denominator: int = Field(ge=1, le=8)
    judge_disposition_agreement: float = Field(ge=0.0, le=1.0)
    abstention_reasons: tuple[CaseAbstentionReason, ...]

    @model_validator(mode="after")
    def _validate_complete_boundary(self) -> "EvidenceSetCaseAudit":
        if len(self.candidate_decisions) != self.provider_candidate_count:
            raise ValueError("every provider candidate must reach the audit boundary")
        candidate_ids = tuple(item.candidate_sha256 for item in self.candidate_decisions)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate audit identities must be unique")
        selected_ids = tuple(item.candidate_sha256 for item in self.selected_sources)
        if not set(selected_ids).issubset(candidate_ids):
            raise ValueError("selected source is missing from candidate decisions")
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError("selected source identities must be unique")
        decisions_by_id = {
            item.candidate_sha256: item for item in self.candidate_decisions
        }
        selected_decisions = tuple(decisions_by_id[value] for value in selected_ids)
        for selected, decision in zip(
            self.selected_sources,
            selected_decisions,
            strict=True,
        ):
            expected_roles = (
                *decision.required_role_ids,
                *decision.scope_role_ids,
                *decision.supporting_role_ids,
            )
            if decision.action != "KEEP" or selected.role_ids != expected_roles:
                raise ValueError(
                    "selected source must deliver every verified KEEP role"
                )
        expected_required = {
            role_id for item in selected_decisions for role_id in item.required_role_ids
        }
        expected_scope = {
            role_id for item in selected_decisions for role_id in item.scope_role_ids
        }
        expected_supporting = {
            role_id
            for item in selected_decisions
            for role_id in item.supporting_role_ids
        }
        if set(self.covered_required_role_ids) != expected_required:
            raise ValueError("covered required roles drifted from selected sources")
        if set(self.covered_scope_role_ids) != expected_scope:
            raise ValueError("covered scope roles drifted from selected sources")
        if set(self.covered_supporting_role_ids) != expected_supporting:
            raise ValueError("covered supporting roles drifted from selected sources")
        if self.judge_agreement_denominator != self.provider_candidate_count:
            raise ValueError("agreement denominator must include every candidate")
        expected_rate = self.judge_agreement_numerator / self.judge_agreement_denominator
        if abs(self.judge_disposition_agreement - expected_rate) > 1e-12:
            raise ValueError("judge agreement rate does not match its counts")
        if self.action == "SELECT":
            if not self.selected_sources or self.abstention_reasons:
                raise ValueError("SELECT requires sources and no abstention reason")
        elif self.selected_sources or not self.abstention_reasons:
            raise ValueError("ABSTAIN requires no selected sources and a reason")
        return self


def _role_inputs(profile: EvidenceSetRoleProfile) -> tuple[JudgeRoleInput, ...]:
    return tuple(
        JudgeRoleInput(
            role_id=role.role_id,
            role_kind=kind,
            description=role.description,
        )
        for kind, roles in (
            ("required", profile.required_roles),
            ("scope", profile.scope_roles),
            ("supporting", profile.supporting_roles),
        )
        for role in roles
    )


def _provider_ordered_candidates(
    candidates: tuple[OpenAlexClaimScopeCandidate, ...],
) -> tuple[OpenAlexClaimScopeCandidate, ...]:
    if not candidates:
        raise EvidenceSetContractError("at least one candidate is required")
    if len(candidates) > 8:
        raise EvidenceSetContractError("at most eight provider candidates are allowed")
    indices = tuple(item.evidence.provider_result_index for item in candidates)
    if any(index is None for index in indices):
        raise EvidenceSetContractError("every candidate requires a provider result index")
    if len(indices) != len(set(indices)):
        raise EvidenceSetContractError("provider result indices must be unique")
    identities = tuple(item.sha256() for item in candidates)
    if len(identities) != len(set(identities)):
        raise EvidenceSetContractError("candidate identities must be unique")
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.evidence.provider_result_index,
                item.sha256(),
            ),
        )
    )


def build_judge_inputs(
    *,
    case_id: str,
    topic: str,
    profile: EvidenceSetRoleProfile,
    candidates: tuple[OpenAlexClaimScopeCandidate, ...],
) -> tuple[JudgeBatchInput, JudgeBatchInput]:
    """Build provider-order and reverse-order inputs with no hidden metadata."""

    ordered = _provider_ordered_candidates(candidates)
    roles = _role_inputs(profile)

    def candidate_input(candidate: OpenAlexClaimScopeCandidate) -> JudgeCandidateInput:
        return JudgeCandidateInput(
            candidate_sha256=candidate.sha256(),
            title=candidate.evidence.title,
            abstract=candidate.evidence.evidence_summary,
        )

    first_candidates = tuple(candidate_input(item) for item in ordered)
    return (
        JudgeBatchInput(
            case_id=case_id,
            topic=topic,
            pass_number=1,
            roles=roles,
            candidates=first_candidates,
        ),
        JudgeBatchInput(
            case_id=case_id,
            topic=topic,
            pass_number=2,
            roles=roles,
            candidates=tuple(reversed(first_candidates)),
        ),
    )


def parse_judge_pass(
    raw_response: str,
    expected_input: JudgeBatchInput,
) -> JudgePassAudit:
    """Parse one exact JSON response without repair, fallback or retry."""

    response_sha256 = _sha256_text(raw_response)
    if len(raw_response) > _MAX_RAW_RESPONSE_CHARACTERS:
        return JudgePassAudit(
            pass_number=expected_input.pass_number,
            state="malformed",
            raw_response_sha256=response_sha256,
            input_sha256=expected_input.sha256(),
            error_code="response_too_large",
        )
    try:
        parsed_json = json.loads(raw_response)
        response = JudgeBatchResponse.model_validate(parsed_json)
    except (json.JSONDecodeError, ValidationError):
        return JudgePassAudit(
            pass_number=expected_input.pass_number,
            state="malformed",
            raw_response_sha256=response_sha256,
            input_sha256=expected_input.sha256(),
            error_code="schema_invalid",
        )
    if response.case_id != expected_input.case_id:
        return JudgePassAudit(
            pass_number=expected_input.pass_number,
            state="contract_invalid",
            raw_response_sha256=response_sha256,
            input_sha256=expected_input.sha256(),
            error_code="case_id_mismatch",
        )
    expected_order = tuple(
        item.candidate_sha256 for item in expected_input.candidates
    )
    if response.candidate_order != expected_order:
        return JudgePassAudit(
            pass_number=expected_input.pass_number,
            state="contract_invalid",
            raw_response_sha256=response_sha256,
            input_sha256=expected_input.sha256(),
            error_code="candidate_order_mismatch",
        )
    return JudgePassAudit(
        pass_number=expected_input.pass_number,
        state="valid",
        raw_response_sha256=response_sha256,
        input_sha256=expected_input.sha256(),
        response=response,
    )


def _quote_is_valid(
    quote: JudgeRoleQuote,
    candidate: OpenAlexClaimScopeCandidate,
) -> bool:
    source = (
        candidate.evidence.title
        if quote.field == "title"
        else candidate.evidence.evidence_summary
    )
    normalized_quote = _normalized_quote_text(quote.quote)
    return bool(
        normalized_quote
        and normalized_quote in _normalized_quote_text(source)
    )


def _invalid_pass_candidate(
    candidate: OpenAlexClaimScopeCandidate,
) -> EvidenceSetCandidateAudit:
    return EvidenceSetCandidateAudit(
        candidate_sha256=candidate.sha256(),
        provider_result_index=candidate.evidence.provider_result_index,
        action="ABSTAIN",
        first_action=None,
        second_action=None,
        judge_agreement=False,
        required_role_ids=(),
        scope_role_ids=(),
        supporting_role_ids=(),
        title_anchor_role_ids=(),
        verified_role_quotes=(),
        abstention_reasons=("judge_pass_invalid",),
    )


def _candidate_audit(
    candidate: OpenAlexClaimScopeCandidate,
    first: JudgeCandidateDecision,
    second: JudgeCandidateDecision,
    profile: EvidenceSetRoleProfile,
    contract: EvidenceSetSelectionContract,
) -> EvidenceSetCandidateAudit:
    reasons: list[CandidateAbstentionReason] = []
    role_kinds = profile.role_kinds()
    first_role_ids = tuple(item.role_id for item in first.role_quotes)
    second_role_ids = tuple(item.role_id for item in second.role_quotes)
    verified: list[VerifiedRoleQuote] = []
    agreement = False

    if first.action == second.action == "ABSTAIN":
        agreement = True
        reasons.append("judge_abstained")
    elif first.action != second.action:
        reasons.append("judge_action_disagreement")
    elif set(first_role_ids) != set(second_role_ids):
        reasons.append("judge_role_disagreement")
    else:
        first_by_role = {item.role_id: item for item in first.role_quotes}
        second_by_role = {item.role_id: item for item in second.role_quotes}
        unknown_roles = set(first_by_role).difference(role_kinds)
        if unknown_roles:
            reasons.append("unknown_role")
        else:
            for role_id in role_kinds:
                if role_id not in first_by_role:
                    continue
                first_quote = first_by_role[role_id]
                second_quote = second_by_role[role_id]
                if not (
                    _quote_is_valid(first_quote, candidate)
                    and _quote_is_valid(second_quote, candidate)
                ):
                    reasons.append("invalid_quote")
                    break
                verified.append(
                    VerifiedRoleQuote(
                        role_id=role_id,
                        role_kind=role_kinds[role_id],
                        first_field=first_quote.field,
                        first_quote=first_quote.quote,
                        second_field=second_quote.field,
                        second_quote=second_quote.quote,
                    )
                )
            if not reasons:
                agreement = True

    required = tuple(
        item.role_id for item in verified if item.role_kind == "required"
    )
    scope = tuple(item.role_id for item in verified if item.role_kind == "scope")
    supporting = tuple(
        item.role_id for item in verified if item.role_kind == "supporting"
    )
    title_anchors = tuple(
        item.role_id
        for item in verified
        if item.first_field == item.second_field == "title"
    )
    if agreement and first.action == second.action == "KEEP":
        if len(required) < contract.minimum_candidate_required_roles:
            reasons.append("insufficient_required_roles")
        if len(scope) + len(supporting) < contract.minimum_candidate_context_roles:
            reasons.append("insufficient_context_roles")
        if len(title_anchors) < contract.minimum_candidate_title_anchor_roles:
            reasons.append("missing_title_anchor")

    return EvidenceSetCandidateAudit(
        candidate_sha256=candidate.sha256(),
        provider_result_index=candidate.evidence.provider_result_index,
        action="ABSTAIN" if reasons else "KEEP",
        first_action=first.action,
        second_action=second.action,
        judge_agreement=agreement,
        required_role_ids=required,
        scope_role_ids=scope,
        supporting_role_ids=supporting,
        title_anchor_role_ids=title_anchors,
        verified_role_quotes=tuple(verified),
        abstention_reasons=tuple(reasons),
    )


def _selection_contract_is_possible(
    profile: EvidenceSetRoleProfile,
    contract: EvidenceSetSelectionContract,
) -> None:
    if contract.minimum_scope_roles > len(profile.scope_roles):
        raise EvidenceSetContractError(
            "minimum_scope_roles exceeds the profile scope-role count"
        )
    if contract.minimum_supporting_roles > len(profile.supporting_roles):
        raise EvidenceSetContractError(
            "minimum_supporting_roles exceeds the profile supporting-role count"
        )


def _covers_profile(
    decisions: tuple[EvidenceSetCandidateAudit, ...],
    profile: EvidenceSetRoleProfile,
    contract: EvidenceSetSelectionContract,
) -> bool:
    required = {role_id for item in decisions for role_id in item.required_role_ids}
    scope = {role_id for item in decisions for role_id in item.scope_role_ids}
    supporting = {
        role_id for item in decisions for role_id in item.supporting_role_ids
    }
    return (
        required == {role.role_id for role in profile.required_roles}
        and len(scope) >= contract.minimum_scope_roles
        and len(supporting) >= contract.minimum_supporting_roles
    )


def _select_sources(
    decisions: tuple[EvidenceSetCandidateAudit, ...],
    profile: EvidenceSetRoleProfile,
    contract: EvidenceSetSelectionContract,
) -> tuple[EvidenceSetCandidateAudit, ...]:
    eligible = tuple(
        sorted(
            (item for item in decisions if item.action == "KEEP"),
            key=lambda item: (item.provider_result_index, item.candidate_sha256),
        )
    )
    for size in range(1, contract.maximum_selected_sources_per_case + 1):
        valid = tuple(
            group
            for group in combinations(eligible, size)
            if _covers_profile(group, profile, contract)
        )
        if valid:
            return min(
                valid,
                key=lambda group: (
                    tuple(item.provider_result_index for item in group),
                    tuple(item.candidate_sha256 for item in group),
                ),
            )
    return ()


def evaluate_evidence_set_case(
    *,
    case_id: str,
    topic: str,
    profile: EvidenceSetRoleProfile,
    selection_contract: EvidenceSetSelectionContract,
    candidates: tuple[OpenAlexClaimScopeCandidate, ...],
    first_raw_response: str,
    second_raw_response: str,
) -> EvidenceSetCaseAudit:
    """Evaluate two raw judge responses and emit every row at one seam."""

    _selection_contract_is_possible(profile, selection_contract)
    ordered = _provider_ordered_candidates(candidates)
    first_input, second_input = build_judge_inputs(
        case_id=case_id,
        topic=topic,
        profile=profile,
        candidates=ordered,
    )
    first_pass = parse_judge_pass(first_raw_response, first_input)
    second_pass = parse_judge_pass(second_raw_response, second_input)

    if first_pass.state != "valid" or second_pass.state != "valid":
        candidate_decisions = tuple(
            _invalid_pass_candidate(candidate) for candidate in ordered
        )
    else:
        first_by_id = {
            item.candidate_sha256: item for item in first_pass.response.decisions
        }
        second_by_id = {
            item.candidate_sha256: item for item in second_pass.response.decisions
        }
        candidate_decisions = tuple(
            _candidate_audit(
                candidate,
                first_by_id[candidate.sha256()],
                second_by_id[candidate.sha256()],
                profile,
                selection_contract,
            )
            for candidate in ordered
        )

    selected = _select_sources(candidate_decisions, profile, selection_contract)
    selected_sources = tuple(
        SelectedEvidenceSource(
            candidate_sha256=item.candidate_sha256,
            provider_result_index=item.provider_result_index,
            role_ids=(
                *item.required_role_ids,
                *item.scope_role_ids,
                *item.supporting_role_ids,
            ),
        )
        for item in selected
    )
    covered_required = tuple(
        role.role_id
        for role in profile.required_roles
        if any(role.role_id in item.required_role_ids for item in selected)
    )
    covered_scope = tuple(
        role.role_id
        for role in profile.scope_roles
        if any(role.role_id in item.scope_role_ids for item in selected)
    )
    covered_supporting = tuple(
        role.role_id
        for role in profile.supporting_roles
        if any(role.role_id in item.supporting_role_ids for item in selected)
    )
    agreement_numerator = sum(
        item.judge_agreement for item in candidate_decisions
    )
    eligible_count = sum(item.action == "KEEP" for item in candidate_decisions)
    abstention_reasons: tuple[CaseAbstentionReason, ...] = ()
    if not selected:
        abstention_reasons = (
            "no_valid_candidates" if eligible_count == 0 else "no_covering_set",
        )

    return EvidenceSetCaseAudit(
        case_id=case_id,
        topic=topic,
        action="SELECT" if selected else "ABSTAIN",
        profile_sha256=profile.sha256(),
        selection_contract_sha256=selection_contract.sha256(),
        provider_candidate_count=len(ordered),
        first_pass=first_pass,
        second_pass=second_pass,
        candidate_decisions=candidate_decisions,
        selected_sources=selected_sources,
        covered_required_role_ids=covered_required,
        covered_scope_role_ids=covered_scope,
        covered_supporting_role_ids=covered_supporting,
        judge_agreement_numerator=agreement_numerator,
        judge_agreement_denominator=len(ordered),
        judge_disposition_agreement=agreement_numerator / len(ordered),
        abstention_reasons=abstention_reasons,
    )
