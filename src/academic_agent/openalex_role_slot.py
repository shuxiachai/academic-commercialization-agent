"""Candidate-local role-slot consensus kernel for disconnected v6 studies.

The v5 development result showed that a semantically useful candidate could be
lost for three unrelated reasons: a neighbouring row invalidated the complete
batch, the model changed its candidate action with input order, or two valid
passes proposed slightly different role sets.  This successor removes those
three language-generation decisions from the trust boundary.  The model may
only propose fixed positional quote slots; deterministic code isolates each
row and slot, verifies source text, derives candidate admission, and selects a
bounded evidence set.

This module deliberately contains no HTTP client, model client, retry, repair,
label access, planner trigger, or production import.  It is a zero-network
decision kernel whose output remains disconnected from reports.
"""

from __future__ import annotations

import hashlib
import json
import re
from itertools import combinations
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from academic_agent.openalex_claim_scope import OpenAlexClaimScopeCandidate
from academic_agent.openalex_evidence_set import (
    EvidenceRoleKind,
    EvidenceSetRoleProfile,
    EvidenceSetSelectionContract,
    JudgeQuoteField,
    SelectedEvidenceSource,
)


RoleSlotProposalState = Literal["SUPPORTED", "ABSTAIN"]
ProvisionalCandidateAction = Literal["KEEP", "ABSTAIN"]
EvidenceSetAction = Literal["SELECT", "ABSTAIN"]
RoleSlotPassState = Literal["valid", "malformed", "contract_invalid"]
RoleSlotPassError = Literal[
    "response_too_large",
    "json_invalid",
    "envelope_invalid",
    "case_id_mismatch",
]
CandidateRowState = Literal[
    "valid",
    "partial",
    "missing",
    "duplicate",
    "malformed",
    "pass_unavailable",
]
RoleSlotAuditState = Literal[
    "supported",
    "abstained",
    "invalid_quote",
    "malformed",
    "missing",
    "duplicate",
    "order_mismatch",
    "row_unavailable",
]
CandidateAbstentionReason = Literal[
    "insufficient_required_roles",
    "insufficient_context_roles",
    "missing_title_anchor",
]
CaseAbstentionReason = Literal["no_valid_candidates", "no_covering_set"]

_CASE_ID_PATTERN = r"^[A-Z][0-9]{2}$"
_ROLE_ID_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_WHITESPACE = re.compile(r"\s+")
_MAX_RAW_RESPONSE_CHARACTERS = 200_000
_EXPECTED_ENVELOPE_KEYS = {"case_id", "candidates"}
_EXPECTED_CANDIDATE_KEYS = {"candidate_sha256", "slots"}

_SYSTEM_PROMPT = """You are a bounded academic quote-extraction component.
For every supplied candidate and every numbered role slot, report SUPPORTED
only when an exact quote from that candidate's title or abstract directly
supports the role description. Otherwise report ABSTAIN. Do not decide source
admission, relevance, novelty, truth, set selection, or commercial value. Do
not use outside knowledge, paraphrase quotes, omit slots, add slots, change
slot order, omit candidates, or return prose outside one JSON object."""


class RoleSlotContractError(ValueError):
    """Raised when code-owned inputs cannot satisfy the frozen v6 contract."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _model_sha256(value: BaseModel) -> str:
    return _sha256_text(value.model_dump_json(exclude_none=False))


def _normalized_quote_text(value: str) -> str:
    """Normalize layout only; lexical changes are not quote verification."""

    # This intentionally mirrors the historical evidence-set boundary without
    # importing its private helper.  Case folding, Unicode normalization,
    # stemming, and translation would turn paraphrases into apparent quotes.
    return _WHITESPACE.sub(
        " ",
        value.replace("\r\n", "\n").replace("\r", "\n"),
    ).strip()


class RoleSlotInput(BaseModel):
    """One internal role identity and its fixed outbound slot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_index: int = Field(ge=0, le=15)
    role_id: str = Field(pattern=_ROLE_ID_PATTERN)
    role_kind: EvidenceRoleKind
    description: str = Field(min_length=10, max_length=600)


class RoleSlotCandidateInput(BaseModel):
    """The only candidate fields permitted to cross the model boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_sha256: str = Field(pattern=_SHA256_PATTERN)
    title: str = Field(min_length=5, max_length=600)
    abstract: str = Field(min_length=1, max_length=8000)


class RoleSlotBatchInput(BaseModel):
    """One immutable pass over a code-owned candidate and role order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=_CASE_ID_PATTERN)
    topic: str = Field(min_length=20, max_length=300)
    pass_number: Literal[1, 2, 3]
    roles: tuple[RoleSlotInput, ...] = Field(min_length=5, max_length=16)
    candidates: tuple[RoleSlotCandidateInput, ...] = Field(
        min_length=1,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_fixed_slots_and_candidates(self) -> "RoleSlotBatchInput":
        slot_indices = tuple(role.slot_index for role in self.roles)
        if slot_indices != tuple(range(len(self.roles))):
            raise ValueError("role slots must be zero-based and contiguous")
        role_ids = tuple(role.role_id for role in self.roles)
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("role slot IDs must be unique")
        candidate_ids = tuple(item.candidate_sha256 for item in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate identities must be unique within a pass")
        return self

    def sha256(self) -> str:
        """Bind internal role IDs as well as every outbound field and order."""

        return _model_sha256(self)


class RoleSlotProposal(BaseModel):
    """One strict model proposal before source-text verification."""

    # Strict primitives prevent JSON booleans from becoming integer slot 0/1.
    # Only this provider-facing object needs strict coercion; audit models are
    # constructed by code from already typed values.
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    slot_index: int = Field(ge=0, le=15)
    state: RoleSlotProposalState
    field: JudgeQuoteField | None = None
    quote: str | None = Field(default=None, max_length=8000)

    @model_validator(mode="after")
    def _validate_state_shape(self) -> "RoleSlotProposal":
        if self.state == "SUPPORTED":
            if self.field is None or self.quote is None or not self.quote.strip():
                raise ValueError("SUPPORTED requires a non-empty field and quote")
        elif self.field is not None or self.quote is not None:
            raise ValueError("ABSTAIN requires null field and quote")
        return self


class RoleSlotAudit(BaseModel):
    """One slot after local schema and exact-quote checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_index: int = Field(ge=0, le=15)
    role_id: str = Field(pattern=_ROLE_ID_PATTERN)
    role_kind: EvidenceRoleKind
    state: RoleSlotAuditState
    proposal_state: RoleSlotProposalState | None = None
    field: JudgeQuoteField | None = None
    quote: str | None = None

    @model_validator(mode="after")
    def _validate_audit_shape(self) -> "RoleSlotAudit":
        if self.state == "supported":
            if (
                self.proposal_state != "SUPPORTED"
                or self.field is None
                or self.quote is None
            ):
                raise ValueError("supported slot requires its verified proposal")
        elif self.state == "abstained":
            if (
                self.proposal_state != "ABSTAIN"
                or self.field is not None
                or self.quote is not None
            ):
                raise ValueError("abstained slot requires only an ABSTAIN proposal")
        elif self.state == "invalid_quote":
            if (
                self.proposal_state != "SUPPORTED"
                or self.field is None
                or self.quote is None
            ):
                raise ValueError("invalid quote must retain the rejected proposal")
        return self


class CandidatePassAudit(BaseModel):
    """Every expected role slot for one candidate in one pass."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_sha256: str = Field(pattern=_SHA256_PATTERN)
    row_state: CandidateRowState
    slots: tuple[RoleSlotAudit, ...] = Field(min_length=5, max_length=16)
    provisional_action: ProvisionalCandidateAction | None
    invalid_slot_count: int = Field(ge=0, le=32)
    unknown_slot_count: int = Field(ge=0, le=32)

    @model_validator(mode="after")
    def _validate_complete_slot_boundary(self) -> "CandidatePassAudit":
        indices = tuple(item.slot_index for item in self.slots)
        if indices != tuple(range(len(self.slots))):
            raise ValueError("every expected slot must reach the candidate audit")
        role_ids = tuple(item.role_id for item in self.slots)
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("candidate audit role IDs must be unique")
        clean_states = {"supported", "abstained"}
        if self.row_state == "valid":
            if any(item.state not in clean_states for item in self.slots):
                raise ValueError("valid row cannot contain an invalid slot")
            if self.invalid_slot_count or self.unknown_slot_count:
                raise ValueError("valid row cannot report slot errors")
            if self.provisional_action is None:
                raise ValueError("valid row requires a code-derived disposition")
        elif self.row_state == "partial":
            if (
                all(item.state in clean_states for item in self.slots)
                and self.unknown_slot_count == 0
            ):
                raise ValueError("partial row requires at least one invalid slot")
            if self.provisional_action is not None:
                raise ValueError("partial row cannot enter the stability metric")
        else:
            if any(item.state != "row_unavailable" for item in self.slots):
                raise ValueError("unavailable row must expose unavailable slots")
            if self.provisional_action is not None:
                raise ValueError("unavailable row cannot have a disposition")
        return self


class RoleSlotPassAudit(BaseModel):
    """Top-level parse state plus every expected candidate row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pass_number: Literal[1, 2, 3]
    state: RoleSlotPassState
    raw_response_sha256: str = Field(pattern=_SHA256_PATTERN)
    input_sha256: str = Field(pattern=_SHA256_PATTERN)
    error_code: RoleSlotPassError | None = None
    expected_candidate_order: tuple[str, ...] = Field(min_length=1, max_length=8)
    candidate_rows: tuple[CandidatePassAudit, ...] = Field(
        min_length=1,
        max_length=8,
    )
    unknown_candidate_sha256s: tuple[str, ...] = Field(max_length=32)
    malformed_unidentified_row_count: int = Field(ge=0, le=32)
    local_valid_row_count: int = Field(ge=0, le=8)

    @model_validator(mode="after")
    def _validate_complete_candidate_boundary(self) -> "RoleSlotPassAudit":
        if any(
            re.fullmatch(_SHA256_PATTERN, value) is None
            for value in self.expected_candidate_order
        ):
            raise ValueError("expected candidate order contains an invalid identity")
        observed = tuple(item.candidate_sha256 for item in self.candidate_rows)
        if observed != self.expected_candidate_order:
            raise ValueError("every expected candidate must reach the pass boundary")
        valid_count = sum(
            item.row_state == "valid" for item in self.candidate_rows
        )
        if valid_count != self.local_valid_row_count:
            raise ValueError("local valid-row count does not match candidate rows")
        if self.state == "valid":
            if self.error_code is not None:
                raise ValueError("valid pass cannot carry a top-level error")
        else:
            if self.error_code is None:
                raise ValueError("invalid pass requires an explicit error code")
            if any(
                item.row_state != "pass_unavailable"
                for item in self.candidate_rows
            ):
                raise ValueError("invalid pass must expose unavailable rows")
        return self


class RolePassObservation(BaseModel):
    """One pass contribution retained inside the final role decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pass_number: Literal[1, 2, 3]
    state: RoleSlotAuditState
    field: JudgeQuoteField | None
    quote: str | None


class RoleConsensusAudit(BaseModel):
    """Three pass observations and the deterministic two-of-three outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_index: int = Field(ge=0, le=15)
    role_id: str = Field(pattern=_ROLE_ID_PATTERN)
    role_kind: EvidenceRoleKind
    observations: tuple[RolePassObservation, ...] = Field(
        min_length=3,
        max_length=3,
    )
    support_count: int = Field(ge=0, le=3)
    title_support_count: int = Field(ge=0, le=3)
    consensus_supported: bool

    @model_validator(mode="after")
    def _validate_consensus_math(self) -> "RoleConsensusAudit":
        if tuple(item.pass_number for item in self.observations) != (1, 2, 3):
            raise ValueError("role observations must cover passes one through three")
        support_count = sum(
            item.state == "supported" for item in self.observations
        )
        title_count = sum(
            item.state == "supported" and item.field == "title"
            for item in self.observations
        )
        if (support_count, title_count) != (
            self.support_count,
            self.title_support_count,
        ):
            raise ValueError("role consensus counts do not match observations")
        if self.consensus_supported != (self.support_count >= 2):
            raise ValueError("role consensus must use the frozen two-of-three rule")
        return self


class CandidateRoleSlotAudit(BaseModel):
    """Final candidate decision derived entirely from verified role slots."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_sha256: str = Field(pattern=_SHA256_PATTERN)
    provider_result_index: int = Field(ge=0)
    action: ProvisionalCandidateAction
    pass_row_states: tuple[CandidateRowState, ...] = Field(
        min_length=3,
        max_length=3,
    )
    provisional_actions: tuple[ProvisionalCandidateAction | None, ...] = Field(
        min_length=3,
        max_length=3,
    )
    provisional_disposition_unanimous: bool
    role_consensus: tuple[RoleConsensusAudit, ...] = Field(
        min_length=5,
        max_length=16,
    )
    required_role_ids: tuple[str, ...]
    scope_role_ids: tuple[str, ...]
    supporting_role_ids: tuple[str, ...]
    title_anchor_role_ids: tuple[str, ...]
    abstention_reasons: tuple[CandidateAbstentionReason, ...]

    @model_validator(mode="after")
    def _validate_candidate_derivation(self) -> "CandidateRoleSlotAudit":
        role_ids = tuple(item.role_id for item in self.role_consensus)
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("candidate role consensus identities must be unique")
        supported = {
            item.role_id for item in self.role_consensus if item.consensus_supported
        }
        assigned = {
            *self.required_role_ids,
            *self.scope_role_ids,
            *self.supporting_role_ids,
        }
        if assigned != supported:
            raise ValueError("every consensus role must reach candidate assignments")
        if not set(self.title_anchor_role_ids).issubset(supported):
            raise ValueError("title anchors must be consensus-supported roles")
        expected_unanimous = (
            None not in self.provisional_actions
            and len(set(self.provisional_actions)) == 1
        )
        if self.provisional_disposition_unanimous != expected_unanimous:
            raise ValueError("provisional unanimity does not match pass actions")
        if self.action == "KEEP" and self.abstention_reasons:
            raise ValueError("KEEP candidate cannot carry abstention reasons")
        if self.action == "ABSTAIN" and not self.abstention_reasons:
            raise ValueError("ABSTAIN candidate requires explicit threshold reasons")
        return self


class RoleSlotCaseAudit(BaseModel):
    """Complete v6 decision at the future runner and review seam."""

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
    passes: tuple[RoleSlotPassAudit, ...] = Field(min_length=3, max_length=3)
    candidate_decisions: tuple[CandidateRoleSlotAudit, ...] = Field(
        min_length=1,
        max_length=8,
    )
    selected_sources: tuple[SelectedEvidenceSource, ...] = Field(max_length=3)
    covered_required_role_ids: tuple[str, ...]
    covered_scope_role_ids: tuple[str, ...]
    covered_supporting_role_ids: tuple[str, ...]
    local_valid_row_numerator: int = Field(ge=0, le=24)
    local_valid_row_denominator: int = Field(ge=3, le=24)
    local_valid_row_rate: float = Field(ge=0.0, le=1.0)
    provisional_unanimity_numerator: int = Field(ge=0, le=8)
    provisional_unanimity_denominator: int = Field(ge=1, le=8)
    provisional_disposition_unanimity: float = Field(ge=0.0, le=1.0)
    abstention_reasons: tuple[CaseAbstentionReason, ...]

    @model_validator(mode="after")
    def _validate_complete_case_boundary(self) -> "RoleSlotCaseAudit":
        if tuple(item.pass_number for item in self.passes) != (1, 2, 3):
            raise ValueError("case audit must retain all three passes")
        if len(self.candidate_decisions) != self.provider_candidate_count:
            raise ValueError("every provider candidate must reach the case boundary")
        candidate_ids = tuple(
            item.candidate_sha256 for item in self.candidate_decisions
        )
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate decision identities must be unique")
        for pass_audit in self.passes:
            if set(pass_audit.expected_candidate_order) != set(candidate_ids):
                raise ValueError("each pass must cover the same candidate identities")
        decisions_by_id = {
            item.candidate_sha256: item for item in self.candidate_decisions
        }
        selected_ids = tuple(item.candidate_sha256 for item in self.selected_sources)
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError("selected source identities must be unique")
        if not set(selected_ids).issubset(decisions_by_id):
            raise ValueError("selected source is missing from candidate decisions")
        for selected in self.selected_sources:
            decision = decisions_by_id[selected.candidate_sha256]
            expected_roles = (
                *decision.required_role_ids,
                *decision.scope_role_ids,
                *decision.supporting_role_ids,
            )
            if decision.action != "KEEP" or selected.role_ids != expected_roles:
                raise ValueError(
                    "selected source must deliver every deterministic KEEP role"
                )
        expected_row_denominator = self.provider_candidate_count * 3
        expected_valid_rows = sum(
            item.local_valid_row_count for item in self.passes
        )
        if (
            self.local_valid_row_denominator != expected_row_denominator
            or self.local_valid_row_numerator != expected_valid_rows
            or self.local_valid_row_rate
            != expected_valid_rows / expected_row_denominator
        ):
            raise ValueError("local valid-row metric does not match pass audits")
        expected_unanimous = sum(
            item.provisional_disposition_unanimous
            for item in self.candidate_decisions
        )
        if (
            self.provisional_unanimity_denominator != self.provider_candidate_count
            or self.provisional_unanimity_numerator != expected_unanimous
            or self.provisional_disposition_unanimity
            != expected_unanimous / self.provider_candidate_count
        ):
            raise ValueError("provisional unanimity metric does not match candidates")
        if self.action == "SELECT":
            if not self.selected_sources or self.abstention_reasons:
                raise ValueError("SELECT requires sources and no abstention reason")
        elif self.selected_sources or not self.abstention_reasons:
            raise ValueError("ABSTAIN requires no sources and an explicit reason")
        return self


def _ordered_roles(profile: EvidenceSetRoleProfile) -> tuple[RoleSlotInput, ...]:
    return tuple(
        RoleSlotInput(
            slot_index=index,
            role_id=role.role_id,
            role_kind=kind,
            description=role.description,
        )
        for index, (kind, role) in enumerate(
            (kind, role)
            for kind, roles in (
                ("required", profile.required_roles),
                ("scope", profile.scope_roles),
                ("supporting", profile.supporting_roles),
            )
            for role in roles
        )
    )


def _provider_ordered_candidates(
    candidates: tuple[OpenAlexClaimScopeCandidate, ...],
) -> tuple[OpenAlexClaimScopeCandidate, ...]:
    if not candidates:
        raise RoleSlotContractError("at least one candidate is required")
    if len(candidates) > 8:
        raise RoleSlotContractError("at most eight provider candidates are allowed")
    indices = tuple(item.evidence.provider_result_index for item in candidates)
    if any(index is None for index in indices):
        raise RoleSlotContractError("every candidate requires a provider result index")
    if len(indices) != len(set(indices)):
        raise RoleSlotContractError("provider result indices must be unique")
    identities = tuple(item.sha256() for item in candidates)
    if len(identities) != len(set(identities)):
        raise RoleSlotContractError("candidate identities must be unique")
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.evidence.provider_result_index,
                item.sha256(),
            ),
        )
    )


def build_role_slot_inputs(
    *,
    case_id: str,
    topic: str,
    profile: EvidenceSetRoleProfile,
    candidates: tuple[OpenAlexClaimScopeCandidate, ...],
) -> tuple[RoleSlotBatchInput, RoleSlotBatchInput, RoleSlotBatchInput]:
    """Build provider, reverse, and candidate-identity pass orders."""

    ordered = _provider_ordered_candidates(candidates)
    roles = _ordered_roles(profile)

    def candidate_input(
        candidate: OpenAlexClaimScopeCandidate,
    ) -> RoleSlotCandidateInput:
        return RoleSlotCandidateInput(
            candidate_sha256=candidate.sha256(),
            title=candidate.evidence.title,
            abstract=candidate.evidence.evidence_summary,
        )

    provider_order = tuple(candidate_input(item) for item in ordered)
    identity_order = tuple(
        sorted(provider_order, key=lambda item: item.candidate_sha256)
    )
    return (
        RoleSlotBatchInput(
            case_id=case_id,
            topic=topic,
            pass_number=1,
            roles=roles,
            candidates=provider_order,
        ),
        RoleSlotBatchInput(
            case_id=case_id,
            topic=topic,
            pass_number=2,
            roles=roles,
            candidates=tuple(reversed(provider_order)),
        ),
        RoleSlotBatchInput(
            case_id=case_id,
            topic=topic,
            pass_number=3,
            roles=roles,
            candidates=identity_order,
        ),
    )


def build_role_slot_prompts(batch: RoleSlotBatchInput) -> tuple[str, str]:
    """Serialize the exact action-free provider prompt for one v6 pass."""

    # Internal role IDs are deliberately absent.  The slot index is sufficient
    # to map a returned quote to the immutable profile, and removing the ID
    # prevents the model from duplicating or inventing role identifiers.
    outbound = {
        "case_id": batch.case_id,
        "topic": batch.topic,
        "pass_number": batch.pass_number,
        "roles": [
            {
                "slot_index": role.slot_index,
                "role_kind": role.role_kind,
                "description": role.description,
            }
            for role in batch.roles
        ],
        "candidates": [
            candidate.model_dump(mode="json") for candidate in batch.candidates
        ],
    }
    response_shape = {
        "case_id": batch.case_id,
        "candidates": [
            {
                "candidate_sha256": "candidate identity",
                "slots": [
                    {
                        "slot_index": 0,
                        "state": "SUPPORTED or ABSTAIN",
                        "field": "title, abstract, or null",
                        "quote": "exact source span or null",
                    }
                ],
            }
        ],
    }
    user_prompt = (
        "Extract every numbered role slot for every candidate. SUPPORTED requires "
        "one exact title-or-abstract quote; ABSTAIN requires null field and quote. "
        "Return candidates and slots in the supplied order. Return only strict "
        "JSON with this shape:\n"
        f"{json.dumps(response_shape, ensure_ascii=True, sort_keys=True)}\n"
        "INPUT:\n"
        f"{json.dumps(outbound, ensure_ascii=True, separators=(',', ':'))}"
    )
    return _SYSTEM_PROMPT, user_prompt


def _quote_is_valid(
    proposal: RoleSlotProposal,
    candidate: RoleSlotCandidateInput,
) -> bool:
    if proposal.field is None or proposal.quote is None:
        return False
    source = candidate.title if proposal.field == "title" else candidate.abstract
    normalized_quote = _normalized_quote_text(proposal.quote)
    return bool(
        normalized_quote and normalized_quote in _normalized_quote_text(source)
    )


def _unavailable_slots(
    roles: tuple[RoleSlotInput, ...],
) -> tuple[RoleSlotAudit, ...]:
    return tuple(
        RoleSlotAudit(
            slot_index=role.slot_index,
            role_id=role.role_id,
            role_kind=role.role_kind,
            state="row_unavailable",
        )
        for role in roles
    )


def _unavailable_candidate_row(
    *,
    candidate_sha256: str,
    roles: tuple[RoleSlotInput, ...],
    row_state: Literal["missing", "duplicate", "malformed", "pass_unavailable"],
) -> CandidatePassAudit:
    return CandidatePassAudit(
        candidate_sha256=candidate_sha256,
        row_state=row_state,
        slots=_unavailable_slots(roles),
        provisional_action=None,
        invalid_slot_count=len(roles),
        unknown_slot_count=0,
    )


def _slot_audit(
    *,
    raw_slot: object,
    raw_position: int,
    role: RoleSlotInput,
    candidate: RoleSlotCandidateInput,
) -> RoleSlotAudit:
    try:
        proposal = RoleSlotProposal.model_validate(raw_slot)
    except ValidationError:
        return RoleSlotAudit(
            slot_index=role.slot_index,
            role_id=role.role_id,
            role_kind=role.role_kind,
            state="malformed",
        )
    if raw_position != role.slot_index:
        return RoleSlotAudit(
            slot_index=role.slot_index,
            role_id=role.role_id,
            role_kind=role.role_kind,
            state="order_mismatch",
            proposal_state=proposal.state,
            field=proposal.field,
            quote=proposal.quote,
        )
    if proposal.state == "ABSTAIN":
        return RoleSlotAudit(
            slot_index=role.slot_index,
            role_id=role.role_id,
            role_kind=role.role_kind,
            state="abstained",
            proposal_state=proposal.state,
        )
    if not _quote_is_valid(proposal, candidate):
        return RoleSlotAudit(
            slot_index=role.slot_index,
            role_id=role.role_id,
            role_kind=role.role_kind,
            state="invalid_quote",
            proposal_state=proposal.state,
            field=proposal.field,
            quote=proposal.quote,
        )
    return RoleSlotAudit(
        slot_index=role.slot_index,
        role_id=role.role_id,
        role_kind=role.role_kind,
        state="supported",
        proposal_state=proposal.state,
        field=proposal.field,
        quote=proposal.quote,
    )


def _provisional_action(
    slots: tuple[RoleSlotAudit, ...],
    contract: EvidenceSetSelectionContract,
) -> ProvisionalCandidateAction:
    supported = tuple(item for item in slots if item.state == "supported")
    required_count = sum(item.role_kind == "required" for item in supported)
    context_count = sum(
        item.role_kind in {"scope", "supporting"} for item in supported
    )
    title_count = sum(item.field == "title" for item in supported)
    return (
        "KEEP"
        if required_count >= contract.minimum_candidate_required_roles
        and context_count >= contract.minimum_candidate_context_roles
        and title_count >= contract.minimum_candidate_title_anchor_roles
        else "ABSTAIN"
    )


def _candidate_row_from_raw(
    *,
    raw_row: object,
    candidate: RoleSlotCandidateInput,
    roles: tuple[RoleSlotInput, ...],
    contract: EvidenceSetSelectionContract,
) -> CandidatePassAudit:
    if (
        not isinstance(raw_row, dict)
        or set(raw_row) != _EXPECTED_CANDIDATE_KEYS
        or raw_row.get("candidate_sha256") != candidate.candidate_sha256
        or not isinstance(raw_row.get("slots"), list)
    ):
        return _unavailable_candidate_row(
            candidate_sha256=candidate.candidate_sha256,
            roles=roles,
            row_state="malformed",
        )

    raw_slots = raw_row["slots"]
    by_index: dict[int, list[tuple[int, object]]] = {}
    unknown_slot_count = 0
    for position, raw_slot in enumerate(raw_slots):
        if not isinstance(raw_slot, dict):
            unknown_slot_count += 1
            continue
        slot_index = raw_slot.get("slot_index")
        # bool is an int subclass, but it is never a valid JSON slot identity.
        if (
            isinstance(slot_index, bool)
            or not isinstance(slot_index, int)
            or not 0 <= slot_index < len(roles)
        ):
            unknown_slot_count += 1
            continue
        by_index.setdefault(slot_index, []).append((position, raw_slot))

    audits: list[RoleSlotAudit] = []
    for role in roles:
        matches = by_index.get(role.slot_index, [])
        if not matches:
            audits.append(
                RoleSlotAudit(
                    slot_index=role.slot_index,
                    role_id=role.role_id,
                    role_kind=role.role_kind,
                    state="missing",
                )
            )
        elif len(matches) > 1:
            audits.append(
                RoleSlotAudit(
                    slot_index=role.slot_index,
                    role_id=role.role_id,
                    role_kind=role.role_kind,
                    state="duplicate",
                )
            )
        else:
            position, raw_slot = matches[0]
            audits.append(
                _slot_audit(
                    raw_slot=raw_slot,
                    raw_position=position,
                    role=role,
                    candidate=candidate,
                )
            )

    slots = tuple(audits)
    clean_states = {"supported", "abstained"}
    invalid_slot_count = sum(item.state not in clean_states for item in slots)
    row_is_valid = (
        len(raw_slots) == len(roles)
        and unknown_slot_count == 0
        and invalid_slot_count == 0
    )
    return CandidatePassAudit(
        candidate_sha256=candidate.candidate_sha256,
        row_state="valid" if row_is_valid else "partial",
        slots=slots,
        provisional_action=(
            _provisional_action(slots, contract) if row_is_valid else None
        ),
        invalid_slot_count=invalid_slot_count,
        unknown_slot_count=unknown_slot_count,
    )


def _invalid_pass_audit(
    *,
    raw_response_sha256: str,
    expected_input: RoleSlotBatchInput,
    error_code: RoleSlotPassError,
    state: Literal["malformed", "contract_invalid"],
) -> RoleSlotPassAudit:
    return RoleSlotPassAudit(
        pass_number=expected_input.pass_number,
        state=state,
        raw_response_sha256=raw_response_sha256,
        input_sha256=expected_input.sha256(),
        error_code=error_code,
        expected_candidate_order=tuple(
            item.candidate_sha256 for item in expected_input.candidates
        ),
        candidate_rows=tuple(
            _unavailable_candidate_row(
                candidate_sha256=item.candidate_sha256,
                roles=expected_input.roles,
                row_state="pass_unavailable",
            )
            for item in expected_input.candidates
        ),
        unknown_candidate_sha256s=(),
        malformed_unidentified_row_count=0,
        local_valid_row_count=0,
    )


def parse_role_slot_pass(
    raw_response: str,
    expected_input: RoleSlotBatchInput,
    selection_contract: EvidenceSetSelectionContract,
) -> RoleSlotPassAudit:
    """Parse one response while containing schema failures to their row."""

    response_sha256 = _sha256_text(raw_response)
    if len(raw_response) > _MAX_RAW_RESPONSE_CHARACTERS:
        return _invalid_pass_audit(
            raw_response_sha256=response_sha256,
            expected_input=expected_input,
            error_code="response_too_large",
            state="malformed",
        )
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError:
        return _invalid_pass_audit(
            raw_response_sha256=response_sha256,
            expected_input=expected_input,
            error_code="json_invalid",
            state="malformed",
        )
    if (
        not isinstance(payload, dict)
        or set(payload) != _EXPECTED_ENVELOPE_KEYS
        or not isinstance(payload.get("case_id"), str)
        or not isinstance(payload.get("candidates"), list)
        or len(payload["candidates"]) > 32
    ):
        return _invalid_pass_audit(
            raw_response_sha256=response_sha256,
            expected_input=expected_input,
            error_code="envelope_invalid",
            state="malformed",
        )
    if payload["case_id"] != expected_input.case_id:
        return _invalid_pass_audit(
            raw_response_sha256=response_sha256,
            expected_input=expected_input,
            error_code="case_id_mismatch",
            state="contract_invalid",
        )

    expected_by_id = {
        item.candidate_sha256: item for item in expected_input.candidates
    }
    grouped: dict[str, list[object]] = {
        candidate_sha256: [] for candidate_sha256 in expected_by_id
    }
    unknown_candidate_sha256s: list[str] = []
    malformed_unidentified_rows = 0
    for raw_row in payload["candidates"]:
        candidate_sha256 = (
            raw_row.get("candidate_sha256")
            if isinstance(raw_row, dict)
            else None
        )
        if (
            not isinstance(candidate_sha256, str)
            or re.fullmatch(_SHA256_PATTERN, candidate_sha256) is None
        ):
            malformed_unidentified_rows += 1
        elif candidate_sha256 not in grouped:
            unknown_candidate_sha256s.append(candidate_sha256)
        else:
            grouped[candidate_sha256].append(raw_row)

    candidate_rows: list[CandidatePassAudit] = []
    for candidate in expected_input.candidates:
        rows = grouped[candidate.candidate_sha256]
        if not rows:
            candidate_rows.append(
                _unavailable_candidate_row(
                    candidate_sha256=candidate.candidate_sha256,
                    roles=expected_input.roles,
                    row_state="missing",
                )
            )
        elif len(rows) > 1:
            candidate_rows.append(
                _unavailable_candidate_row(
                    candidate_sha256=candidate.candidate_sha256,
                    roles=expected_input.roles,
                    row_state="duplicate",
                )
            )
        else:
            candidate_rows.append(
                _candidate_row_from_raw(
                    raw_row=rows[0],
                    candidate=candidate,
                    roles=expected_input.roles,
                    contract=selection_contract,
                )
            )

    candidate_rows_tuple = tuple(candidate_rows)
    return RoleSlotPassAudit(
        pass_number=expected_input.pass_number,
        state="valid",
        raw_response_sha256=response_sha256,
        input_sha256=expected_input.sha256(),
        error_code=None,
        expected_candidate_order=tuple(expected_by_id),
        candidate_rows=candidate_rows_tuple,
        unknown_candidate_sha256s=tuple(unknown_candidate_sha256s),
        malformed_unidentified_row_count=malformed_unidentified_rows,
        local_valid_row_count=sum(
            item.row_state == "valid" for item in candidate_rows_tuple
        ),
    )


def _selection_contract_is_possible(
    profile: EvidenceSetRoleProfile,
    contract: EvidenceSetSelectionContract,
) -> None:
    if contract.minimum_scope_roles > len(profile.scope_roles):
        raise RoleSlotContractError(
            "minimum_scope_roles exceeds the profile scope-role count"
        )
    if contract.minimum_supporting_roles > len(profile.supporting_roles):
        raise RoleSlotContractError(
            "minimum_supporting_roles exceeds the supporting-role count"
        )


def _candidate_decision(
    *,
    candidate: OpenAlexClaimScopeCandidate,
    pass_rows: tuple[CandidatePassAudit, CandidatePassAudit, CandidatePassAudit],
    roles: tuple[RoleSlotInput, ...],
    contract: EvidenceSetSelectionContract,
) -> CandidateRoleSlotAudit:
    role_consensus: list[RoleConsensusAudit] = []
    for role in roles:
        slot_observations = tuple(
            row.slots[role.slot_index] for row in pass_rows
        )
        observations = tuple(
            RolePassObservation(
                pass_number=pass_number,
                state=slot.state,
                field=slot.field,
                quote=slot.quote,
            )
            for pass_number, slot in enumerate(slot_observations, start=1)
        )
        support_count = sum(item.state == "supported" for item in observations)
        title_support_count = sum(
            item.state == "supported" and item.field == "title"
            for item in observations
        )
        role_consensus.append(
            RoleConsensusAudit(
                slot_index=role.slot_index,
                role_id=role.role_id,
                role_kind=role.role_kind,
                observations=observations,
                support_count=support_count,
                title_support_count=title_support_count,
                consensus_supported=support_count >= 2,
            )
        )

    consensus = tuple(role_consensus)
    required = tuple(
        item.role_id
        for item in consensus
        if item.consensus_supported and item.role_kind == "required"
    )
    scope = tuple(
        item.role_id
        for item in consensus
        if item.consensus_supported and item.role_kind == "scope"
    )
    supporting = tuple(
        item.role_id
        for item in consensus
        if item.consensus_supported and item.role_kind == "supporting"
    )
    title_anchors = tuple(
        item.role_id
        for item in consensus
        if item.consensus_supported and item.title_support_count >= 2
    )
    reasons: list[CandidateAbstentionReason] = []
    if len(required) < contract.minimum_candidate_required_roles:
        reasons.append("insufficient_required_roles")
    if len(scope) + len(supporting) < contract.minimum_candidate_context_roles:
        reasons.append("insufficient_context_roles")
    if len(title_anchors) < contract.minimum_candidate_title_anchor_roles:
        reasons.append("missing_title_anchor")
    provisional_actions = tuple(row.provisional_action for row in pass_rows)
    unanimous = (
        None not in provisional_actions and len(set(provisional_actions)) == 1
    )
    return CandidateRoleSlotAudit(
        candidate_sha256=candidate.sha256(),
        provider_result_index=candidate.evidence.provider_result_index,
        action="ABSTAIN" if reasons else "KEEP",
        pass_row_states=tuple(row.row_state for row in pass_rows),
        provisional_actions=provisional_actions,
        provisional_disposition_unanimous=unanimous,
        role_consensus=consensus,
        required_role_ids=required,
        scope_role_ids=scope,
        supporting_role_ids=supporting,
        title_anchor_role_ids=title_anchors,
        abstention_reasons=tuple(reasons),
    )


def _covers_profile(
    decisions: tuple[CandidateRoleSlotAudit, ...],
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
    decisions: tuple[CandidateRoleSlotAudit, ...],
    profile: EvidenceSetRoleProfile,
    contract: EvidenceSetSelectionContract,
) -> tuple[CandidateRoleSlotAudit, ...]:
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


def evaluate_role_slot_case(
    *,
    case_id: str,
    topic: str,
    profile: EvidenceSetRoleProfile,
    selection_contract: EvidenceSetSelectionContract,
    candidates: tuple[OpenAlexClaimScopeCandidate, ...],
    raw_responses: tuple[str, str, str],
) -> RoleSlotCaseAudit:
    """Evaluate three responses and preserve every local outcome at one seam."""

    _selection_contract_is_possible(profile, selection_contract)
    ordered_candidates = _provider_ordered_candidates(candidates)
    inputs = build_role_slot_inputs(
        case_id=case_id,
        topic=topic,
        profile=profile,
        candidates=ordered_candidates,
    )
    passes = tuple(
        parse_role_slot_pass(raw_response, expected_input, selection_contract)
        for raw_response, expected_input in zip(raw_responses, inputs, strict=True)
    )
    rows_by_pass = tuple(
        {row.candidate_sha256: row for row in pass_audit.candidate_rows}
        for pass_audit in passes
    )
    roles = inputs[0].roles
    candidate_decisions = tuple(
        _candidate_decision(
            candidate=candidate,
            pass_rows=tuple(
                rows[candidate.sha256()] for rows in rows_by_pass
            ),
            roles=roles,
            contract=selection_contract,
        )
        for candidate in ordered_candidates
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
    eligible_count = sum(item.action == "KEEP" for item in candidate_decisions)
    abstention_reasons: tuple[CaseAbstentionReason, ...] = ()
    if not selected:
        abstention_reasons = (
            "no_valid_candidates" if eligible_count == 0 else "no_covering_set",
        )
    valid_rows = sum(item.local_valid_row_count for item in passes)
    row_denominator = len(ordered_candidates) * 3
    unanimous = sum(
        item.provisional_disposition_unanimous for item in candidate_decisions
    )
    return RoleSlotCaseAudit(
        case_id=case_id,
        topic=topic,
        action="SELECT" if selected else "ABSTAIN",
        profile_sha256=profile.sha256(),
        selection_contract_sha256=selection_contract.sha256(),
        provider_candidate_count=len(ordered_candidates),
        passes=passes,
        candidate_decisions=candidate_decisions,
        selected_sources=selected_sources,
        covered_required_role_ids=covered_required,
        covered_scope_role_ids=covered_scope,
        covered_supporting_role_ids=covered_supporting,
        local_valid_row_numerator=valid_rows,
        local_valid_row_denominator=row_denominator,
        local_valid_row_rate=valid_rows / row_denominator,
        provisional_unanimity_numerator=unanimous,
        provisional_unanimity_denominator=len(ordered_candidates),
        provisional_disposition_unanimity=unanimous / len(ordered_candidates),
        abstention_reasons=abstention_reasons,
    )
