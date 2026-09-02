"""Zero-network preflight for adaptive role-gap closure v8.

Role-directed retrieval v7 showed that a second fixed broad query could add
relevant papers without closing the role that blocked a usable evidence set.
V8 therefore freezes one anchor query plus five mutually exclusive closure
options per case.  This module checks those identities and exercises the
candidate-local router without importing a provider, executor, model, or
private review artifact.  Running its CLI cannot spend a search or model
budget.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from academic_agent.evidence import EvidenceSource
from academic_agent.evidence_gap import (
    GapContext,
    GapPlanProposal,
    GapSearchIntent,
    ValidatedGapCall,
    ValidatedGapPlan,
    build_gap_context,
    source_collection_sha256,
    validate_gap_plan,
)
from academic_agent.openalex_evidence_set import (
    EvidenceRoleKind,
    EvidenceSetRoleProfile,
    EvidenceSetRoleSpec,
)
from academic_agent.source_pipeline import SourceCollection


_ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE_PATH = _ROOT / "tests/fixtures/openalex_role_gap_v8_challenge.json"
EXPECTED_FIXTURE_SHA256 = (
    "0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7"
)
_DEVELOPMENT_ORDER = tuple(f"AC{index:02d}" for index in range(1, 9))
_UNSEEN_ORDER = tuple(f"AD{index:02d}" for index in range(1, 9))
_ROLE_KIND_ORDER: tuple[EvidenceRoleKind, ...] = (
    "required",
    "scope",
    "supporting",
)
_COLLECTED_AT = datetime(2026, 9, 2, tzinfo=UTC)
_ACCESSED_DATE = date(2026, 9, 2)
_TOKEN_BOUNDARY = re.compile(r"[^a-z0-9]+")


class OpenAlexRoleGapPreflightError(ValueError):
    """Raised before live authority when the frozen v8 contract drifts."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_bytes(canonical.encode("utf-8"))


def _model_sha256(value: BaseModel) -> str:
    return _sha256_bytes(value.model_dump_json(exclude_none=False).encode("utf-8"))


class RoleGapProviderContract(BaseModel):
    """Exact bounded OpenAlex boundary without importing its transport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["anonymous_openalex"] = "anonymous_openalex"
    maximum_requests_per_case: Literal[2] = 2
    result_limit_per_request: Literal[6] = 6
    require_abstract: Literal[True] = True
    allow_redirects: Literal[False] = False
    allow_retries: Literal[False] = False

    def sha256(self) -> str:
        return _model_sha256(self)


class RoleGapRoutingContract(BaseModel):
    """Frozen router semantics; every boolean is part of the experiment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    anchor_lane_id: Literal["anchor_search"] = "anchor_search"
    closure_lane_id: Literal["role_closure"] = "role_closure"
    candidate_local_signals: Literal[True] = True
    group_match_requires_all_phrases: Literal[True] = True
    provider_metadata_may_establish_role: Literal[False] = False
    missing_role_tiebreak: Literal["frozen_case_priority"] = (
        "frozen_case_priority"
    )
    closure_query_must_be_frozen: Literal[True] = True
    maximum_closure_calls: Literal[1] = 1
    stop_when_no_gap: Literal[True] = True

    def sha256(self) -> str:
        return _model_sha256(self)


class RoleGapPortfolioContract(BaseModel):
    """Frozen merge and later human-review limits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    deduplicate_by: tuple[str, str]
    preserve_route_provenance: Literal[True] = True
    preserve_provider_rank: Literal[True] = True
    maximum_unique_candidates_per_case: Literal[12] = 12
    maximum_cover_sources_per_case: Literal[3] = 3
    semantic_filter_before_human_qualification: Literal[False] = False

    @model_validator(mode="after")
    def _validate_deduplication_order(self) -> "RoleGapPortfolioContract":
        if self.deduplicate_by != (
            "normalized_doi",
            "canonical_openalex_url",
        ):
            raise ValueError("v8 deduplication precedence drifted")
        return self

    def sha256(self) -> str:
        return _model_sha256(self)


class RoleGapQualificationContract(BaseModel):
    """Conjunctive human gates; this preflight cannot claim they passed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_cases_with_relevant_novel_candidate: Literal[6] = 6
    minimum_candidate_pool_precision: Literal[0.25] = 0.25
    minimum_human_correct_routing_decisions: Literal[6] = 6
    minimum_cases_with_selected_role_closure_value: Literal[4] = 4
    minimum_human_coverable_cases: Literal[6] = 6
    minimum_coverability_gain_over_anchor: Literal[2] = 2

    def sha256(self) -> str:
        return _model_sha256(self)


class RoleGapRoleSpec(BaseModel):
    """One semantic role plus the only phrases and query that may route it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,80}$")
    description: str = Field(min_length=10, max_length=600)
    signal_groups: tuple[tuple[str, ...], ...] = Field(min_length=1, max_length=4)
    closure_query: str = Field(min_length=20, max_length=500)

    @field_validator("signal_groups")
    @classmethod
    def _validate_signal_groups(
        cls,
        value: tuple[tuple[str, ...], ...],
    ) -> tuple[tuple[str, ...], ...]:
        normalized_groups: list[tuple[str, ...]] = []
        for group in value:
            if not 1 <= len(group) <= 4:
                raise ValueError("each role signal group must contain 1-4 phrases")
            phrases = tuple(" ".join(phrase.split()) for phrase in group)
            if any(len(phrase) < 2 for phrase in phrases):
                raise ValueError("role signal phrases cannot be blank or one character")
            if len({phrase.casefold() for phrase in phrases}) != len(phrases):
                raise ValueError("phrases must be unique within a signal group")
            normalized_groups.append(phrases)
        if len(set(normalized_groups)) != len(normalized_groups):
            raise ValueError("signal groups must be unique within a role")
        return tuple(normalized_groups)

    def profile_spec(self) -> EvidenceSetRoleSpec:
        """Strip routing-only fields before using the shared role profile."""

        return EvidenceSetRoleSpec(
            role_id=self.role_id,
            description=self.description,
        )


class RoleGapRoleGroups(BaseModel):
    """Exactly five roles produce exactly five closure options per case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required: tuple[RoleGapRoleSpec, RoleGapRoleSpec]
    scope: tuple[RoleGapRoleSpec]
    supporting: tuple[RoleGapRoleSpec, RoleGapRoleSpec]

    @model_validator(mode="after")
    def _validate_unique_role_ids(self) -> "RoleGapRoleGroups":
        role_ids = tuple(role.role_id for _, role in self.ordered_roles())
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("v8 role IDs must be unique within a case")
        return self

    def ordered_roles(self) -> tuple[tuple[EvidenceRoleKind, RoleGapRoleSpec], ...]:
        return (
            *(("required", role) for role in self.required),
            *(("scope", role) for role in self.scope),
            *(("supporting", role) for role in self.supporting),
        )

    def profile(self) -> EvidenceSetRoleProfile:
        # The shared profile remains the source of truth for semantic role
        # identity. Signal phrases and closure queries are deliberately absent.
        return EvidenceSetRoleProfile(
            required_roles=tuple(role.profile_spec() for role in self.required),
            scope_roles=tuple(role.profile_spec() for role in self.scope),
            supporting_roles=tuple(
                role.profile_spec() for role in self.supporting
            ),
        )


class RoleGapCaseSpec(BaseModel):
    """One anchor plus a complete, mutually exclusive closure portfolio."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^A[CD]0[1-8]$")
    topic: str = Field(min_length=20, max_length=300)
    anchor_query: str = Field(min_length=20, max_length=500)
    closure_priority_role_ids: tuple[str, str, str, str, str]
    roles: RoleGapRoleGroups

    @model_validator(mode="after")
    def _validate_priority_and_queries(self) -> "RoleGapCaseSpec":
        role_ids = tuple(role.role_id for _, role in self.roles.ordered_roles())
        if len(set(self.closure_priority_role_ids)) != 5:
            raise ValueError("closure-priority role IDs must be unique")
        if set(self.closure_priority_role_ids) != set(role_ids):
            raise ValueError("closure priority must name every role exactly once")
        queries = (
            self.anchor_query,
            *(role.closure_query for _, role in self.roles.ordered_roles()),
        )
        if len({query.casefold() for query in queries}) != len(queries):
            raise ValueError("anchor and closure queries must be distinct")
        return self

    def sha256(self) -> str:
        return _model_sha256(self)


class RoleGapChallengeManifest(BaseModel):
    """Complete raw-byte-frozen v8 development and unseen challenge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    method_id: Literal["openalex-adaptive-role-gap-closure-v8"]
    provider_contract: RoleGapProviderContract
    routing_contract: RoleGapRoutingContract
    portfolio_contract: RoleGapPortfolioContract
    qualification_contract: RoleGapQualificationContract
    development_cases: tuple[
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
    ]
    unseen_cases: tuple[
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
        RoleGapCaseSpec,
    ]

    @model_validator(mode="after")
    def _validate_cross_contracts(self) -> "RoleGapChallengeManifest":
        if tuple(case.case_id for case in self.development_cases) != (
            _DEVELOPMENT_ORDER
        ):
            raise ValueError("development cases must remain AC01 through AC08")
        if tuple(case.case_id for case in self.unseen_cases) != _UNSEEN_ORDER:
            raise ValueError("unseen cases must remain AD01 through AD08")

        all_cases = (*self.development_cases, *self.unseen_cases)
        if len({case.topic.casefold() for case in all_cases}) != len(all_cases):
            raise ValueError("topic strings must be unique across both cohorts")
        queries = tuple(
            query
            for case in all_cases
            for query in (
                case.anchor_query,
                *(
                    role.closure_query
                    for _, role in case.roles.ordered_roles()
                ),
            )
        )
        if len(queries) != 96:
            raise ValueError("v8 must freeze one anchor and five closures per case")
        if len({query.casefold() for query in queries}) != len(queries):
            raise ValueError("all v8 search queries must be globally unique")
        if (
            self.provider_contract.maximum_requests_per_case
            * self.provider_contract.result_limit_per_request
            != self.portfolio_contract.maximum_unique_candidates_per_case
        ):
            raise ValueError("provider row ceiling and portfolio ceiling drifted")
        return self


class RoleGapCandidateText(BaseModel):
    """Only source text may drive routing; provider metadata is not accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=2000)
    abstract: str = Field(min_length=1, max_length=50_000)


class RoleSignalObservation(BaseModel):
    """First candidate-local match, or an explicit checked absence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role_id: str
    role_kind: EvidenceRoleKind
    observed: bool
    checked_candidate_count: int = Field(ge=0)
    matched_candidate_index: int | None = Field(default=None, ge=0)
    matched_signal_group_index: int | None = Field(default=None, ge=0)
    matched_phrases: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_match_shape(self) -> "RoleSignalObservation":
        details = (
            self.matched_candidate_index,
            self.matched_signal_group_index,
        )
        if self.observed:
            if any(value is None for value in details) or not self.matched_phrases:
                raise ValueError("an observed role requires local match provenance")
            if self.matched_candidate_index >= self.checked_candidate_count:
                raise ValueError("matched candidate index exceeds checked candidates")
        elif any(value is not None for value in details) or self.matched_phrases:
            raise ValueError("an absent role cannot carry match provenance")
        return self


class RoleGapClosureOption(BaseModel):
    """One pre-authorized role/query identity; only one option may be selected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role_id: str
    role_kind: EvidenceRoleKind
    query: str
    call: ValidatedGapCall
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    closure_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_query_binding(self) -> "RoleGapClosureOption":
        if self.query != self.call.query:
            raise ValueError("closure option query must equal its validated call")
        return self


class RoleGapRouteDecision(BaseModel):
    """Serializable decision that distinguishes abstention from unchecked state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    checked: Literal[True] = True
    action: Literal["search", "abstain"]
    reason: Literal[
        "highest_priority_missing_role",
        "abstain_no_mechanical_role_gap",
    ]
    observations: tuple[RoleSignalObservation, ...]
    missing_role_ids: tuple[str, ...]
    selected_closure: RoleGapClosureOption | None = None

    @model_validator(mode="after")
    def _validate_decision_shape(self) -> "RoleGapRouteDecision":
        if self.action == "search":
            if self.reason != "highest_priority_missing_role":
                raise ValueError("search must report the frozen priority reason")
            if self.selected_closure is None or not self.missing_role_ids:
                raise ValueError("search requires a selected missing-role closure")
            if self.selected_closure.role_id != self.missing_role_ids[0]:
                raise ValueError("selected closure must be the first missing role")
        elif (
            self.reason != "abstain_no_mechanical_role_gap"
            or self.selected_closure is not None
            or self.missing_role_ids
        ):
            raise ValueError("no-gap abstention cannot carry a closure or missing role")
        return self


@dataclass(frozen=True)
class PreparedRoleGapCase:
    """All deterministic identities needed before a future provider exists."""

    spec: RoleGapCaseSpec
    collection: SourceCollection
    context: GapContext
    anchor_call: ValidatedGapCall
    anchor_plan_sha256: str
    anchor_contract_sha256: str
    closure_options: tuple[RoleGapClosureOption, ...]
    collection_sha256: str
    profile_sha256: str
    case_contract_sha256: str


def _plan_sha256(plan: ValidatedGapPlan) -> str:
    return _sha256_bytes(plan.model_dump_json(exclude_none=False).encode("utf-8"))


def _normalized_text(value: str) -> str:
    return " ".join(token for token in _TOKEN_BOUNDARY.split(value.casefold()) if token)


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    normalized_phrase = _normalized_text(phrase)
    return f" {normalized_phrase} " in f" {normalized_text} "


def _observe_role(
    role_kind: EvidenceRoleKind,
    role: RoleGapRoleSpec,
    candidates: tuple[RoleGapCandidateText, ...],
) -> RoleSignalObservation:
    """Match every phrase in one group inside one candidate, never a pool."""

    for candidate_index, candidate in enumerate(candidates):
        # Joining title and abstract is allowed by the frozen wording, but the
        # loop remains candidate-local. Moving this normalization outside the
        # loop would recreate the cross-source evidence-pooling defect.
        candidate_text = _normalized_text(f"{candidate.title} {candidate.abstract}")
        for group_index, phrases in enumerate(role.signal_groups):
            if all(_contains_phrase(candidate_text, phrase) for phrase in phrases):
                return RoleSignalObservation(
                    role_id=role.role_id,
                    role_kind=role_kind,
                    observed=True,
                    checked_candidate_count=len(candidates),
                    matched_candidate_index=candidate_index,
                    matched_signal_group_index=group_index,
                    matched_phrases=phrases,
                )
    return RoleSignalObservation(
        role_id=role.role_id,
        role_kind=role_kind,
        observed=False,
        checked_candidate_count=len(candidates),
    )


def route_anchor_candidates(
    prepared: PreparedRoleGapCase,
    candidates: tuple[RoleGapCandidateText, ...],
) -> RoleGapRouteDecision:
    """Choose one frozen closure by priority, or explicitly spend no request."""

    role_by_id = {
        role.role_id: (role_kind, role)
        for role_kind, role in prepared.spec.roles.ordered_roles()
    }
    option_by_role = {option.role_id: option for option in prepared.closure_options}
    if set(option_by_role) != set(role_by_id):
        raise OpenAlexRoleGapPreflightError(
            f"{prepared.spec.case_id}: closure options do not cover every role"
        )

    # Evaluation follows serialized role order so the audit is stable. The
    # missing list is rebuilt from frozen priority, which prevents JSON role
    # order from silently becoming the routing policy.
    observations = tuple(
        _observe_role(role_kind, role, candidates)
        for role_kind, role in prepared.spec.roles.ordered_roles()
    )
    observed_role_ids = {
        observation.role_id for observation in observations if observation.observed
    }
    missing_role_ids = tuple(
        role_id
        for role_id in prepared.spec.closure_priority_role_ids
        if role_id not in observed_role_ids
    )
    if not missing_role_ids:
        return RoleGapRouteDecision(
            action="abstain",
            reason="abstain_no_mechanical_role_gap",
            observations=observations,
            missing_role_ids=(),
        )
    return RoleGapRouteDecision(
        action="search",
        reason="highest_priority_missing_role",
        observations=observations,
        missing_role_ids=missing_role_ids,
        selected_closure=option_by_role[missing_role_ids[0]],
    )


def _seed_source(spec: RoleGapCaseSpec) -> EvidenceSource:
    """Create a valid gap context without claiming provider evidence exists."""

    return EvidenceSource(
        source_id="A1",
        title=f"{spec.topic}: frozen adaptive role-gap v8 baseline context",
        url=(
            "https://doi.org/10.5555/openalex-role-gap-v8."
            f"{spec.case_id.casefold()}"
        ),
        publisher="Frozen Adaptive Role-gap v8 Fixture",
        accessed_date=_ACCESSED_DATE,
        source_type="academic_paper",
        evidence_summary=(
            f"This synthetic baseline records the question {spec.topic}. "
            "It contains no provider candidate and preserves an explicit "
            "academic retrieval gap for this disconnected preflight."
        ),
        summary_source="abstract",
    )


def _single_call_plan(
    context: GapContext,
    *,
    query: str,
    trigger_id: str,
    result_limit: int,
    rationale: str,
) -> ValidatedGapPlan:
    return validate_gap_plan(
        context,
        GapPlanProposal(
            decision="search",
            rationale=rationale,
            calls=(
                GapSearchIntent(
                    tool="academic_search",
                    query=query,
                    trigger_ids=(trigger_id,),
                    result_limit=result_limit,
                ),
            ),
        ),
    )


def _case_contract_sha256(
    spec: RoleGapCaseSpec,
    *,
    method_id: str,
    provider_contract_sha256: str,
    routing_contract_sha256: str,
    portfolio_contract_sha256: str,
    qualification_contract_sha256: str,
) -> str:
    return _sha256_json(
        {
            "method_id": method_id,
            "spec": spec.model_dump(mode="json"),
            "provider_contract_sha256": provider_contract_sha256,
            "routing_contract_sha256": routing_contract_sha256,
            "portfolio_contract_sha256": portfolio_contract_sha256,
            "qualification_contract_sha256": qualification_contract_sha256,
        }
    )


def _route_contract_sha256(
    spec: RoleGapCaseSpec,
    *,
    lane_id: str,
    role_kind: EvidenceRoleKind | None,
    role: RoleGapRoleSpec | None,
    call: ValidatedGapCall,
    method_id: str,
    provider_contract_sha256: str,
    routing_contract_sha256: str,
) -> str:
    return _sha256_json(
        {
            "method_id": method_id,
            "case_id": spec.case_id,
            "topic": spec.topic,
            "lane_id": lane_id,
            "role_kind": role_kind,
            "role": role.model_dump(mode="json") if role else None,
            "validated_call": call.model_dump(mode="json"),
            "provider_contract_sha256": provider_contract_sha256,
            "routing_contract_sha256": routing_contract_sha256,
        }
    )


def build_case(
    spec: RoleGapCaseSpec,
    *,
    method_id: str,
    provider_contract_sha256: str,
    routing_contract_sha256: str,
    portfolio_contract_sha256: str,
    qualification_contract_sha256: str,
    result_limit: int,
) -> PreparedRoleGapCase:
    """Expand six possible identities while authorizing no provider request."""

    collection = SourceCollection(
        topic=spec.topic,
        display_topic=spec.topic,
        output_language="English",
        weight_profile="industrial",
        collected_at=_COLLECTED_AT,
        academic_sources=[_seed_source(spec)],
        academic_queries=[spec.topic],
        patent_queries=[spec.topic],
        market_queries=[spec.topic],
        failed_domains={"academic": "frozen adaptive role-gap v8 challenge"},
    )
    context = build_gap_context(collection)
    trigger = next(
        (
            signal
            for signal in context.signals
            if signal.code == "retrieval_domain_failed"
            and signal.subject == "academic"
        ),
        None,
    )
    if trigger is None:
        raise OpenAlexRoleGapPreflightError(
            f"{spec.case_id}: frozen academic gap signal was not produced"
        )

    anchor_plan = _single_call_plan(
        context,
        query=spec.anchor_query,
        trigger_id=trigger.signal_id,
        result_limit=result_limit,
        rationale=(
            "The frozen v8 case authorizes its one code-owned anchor request "
            "before any candidate-local role observation exists."
        ),
    )
    anchor_call = anchor_plan.calls[0]
    options: list[RoleGapClosureOption] = []
    for role_kind, role in spec.roles.ordered_roles():
        option_plan = _single_call_plan(
            context,
            query=role.closure_query,
            trigger_id=trigger.signal_id,
            result_limit=result_limit,
            rationale=(
                "The frozen v8 role portfolio pre-authorizes this one query "
                "only if candidate-local routing later selects its missing role."
            ),
        )
        option_call = option_plan.calls[0]
        options.append(
            RoleGapClosureOption(
                role_id=role.role_id,
                role_kind=role_kind,
                query=role.closure_query,
                call=option_call,
                plan_sha256=_plan_sha256(option_plan),
                closure_contract_sha256=_route_contract_sha256(
                    spec,
                    lane_id="role_closure",
                    role_kind=role_kind,
                    role=role,
                    call=option_call,
                    method_id=method_id,
                    provider_contract_sha256=provider_contract_sha256,
                    routing_contract_sha256=routing_contract_sha256,
                ),
            )
        )

    profile_sha256 = spec.roles.profile().sha256()
    return PreparedRoleGapCase(
        spec=spec,
        collection=collection,
        context=context,
        anchor_call=anchor_call,
        anchor_plan_sha256=_plan_sha256(anchor_plan),
        anchor_contract_sha256=_route_contract_sha256(
            spec,
            lane_id="anchor_search",
            role_kind=None,
            role=None,
            call=anchor_call,
            method_id=method_id,
            provider_contract_sha256=provider_contract_sha256,
            routing_contract_sha256=routing_contract_sha256,
        ),
        closure_options=tuple(options),
        collection_sha256=source_collection_sha256(collection),
        profile_sha256=profile_sha256,
        case_contract_sha256=_case_contract_sha256(
            spec,
            method_id=method_id,
            provider_contract_sha256=provider_contract_sha256,
            routing_contract_sha256=routing_contract_sha256,
            portfolio_contract_sha256=portfolio_contract_sha256,
            qualification_contract_sha256=qualification_contract_sha256,
        ),
    )


def load_frozen_cases(
    cohort: Literal["development", "unseen"] = "development",
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> tuple[
    str,
    RoleGapChallengeManifest,
    tuple[PreparedRoleGapCase, ...],
]:
    """Validate raw bytes before parsing or expanding either cohort."""

    raw = fixture_path.read_bytes()
    fixture_sha256 = _sha256_bytes(raw)
    if fixture_sha256 != expected_fixture_sha256:
        raise OpenAlexRoleGapPreflightError(
            "adaptive role-gap v8 fixture byte identity drifted: "
            f"expected {expected_fixture_sha256}, got {fixture_sha256}"
        )
    manifest = RoleGapChallengeManifest.model_validate_json(raw)
    specs = (
        manifest.development_cases
        if cohort == "development"
        else manifest.unseen_cases
    )
    provider_sha256 = manifest.provider_contract.sha256()
    routing_sha256 = manifest.routing_contract.sha256()
    portfolio_sha256 = manifest.portfolio_contract.sha256()
    qualification_sha256 = manifest.qualification_contract.sha256()
    return (
        fixture_sha256,
        manifest,
        tuple(
            build_case(
                spec,
                method_id=manifest.method_id,
                provider_contract_sha256=provider_sha256,
                routing_contract_sha256=routing_sha256,
                portfolio_contract_sha256=portfolio_sha256,
                qualification_contract_sha256=qualification_sha256,
                result_limit=manifest.provider_contract.result_limit_per_request,
            )
            for spec in specs
        ),
    )


def _serialize_case(case: PreparedRoleGapCase) -> dict[str, Any]:
    # An empty-anchor probe is not a provider observation. It exists so tests
    # can assert that every negative observation and selected identity survives
    # the same serialized seam a future runner would expose.
    route_probe = route_anchor_candidates(case, ())
    return {
        "case_id": case.spec.case_id,
        "case_spec_sha256": case.spec.sha256(),
        "collection_sha256": case.collection_sha256,
        "profile_sha256": case.profile_sha256,
        "case_contract_sha256": case.case_contract_sha256,
        "closure_priority_role_ids": list(
            case.spec.closure_priority_role_ids
        ),
        "anchor": {
            "lane_id": "anchor_search",
            "query": case.spec.anchor_query,
            "idempotency_key": case.anchor_call.idempotency_key,
            "plan_sha256": case.anchor_plan_sha256,
            "anchor_contract_sha256": case.anchor_contract_sha256,
            "result_limit": case.anchor_call.result_limit,
        },
        "closure_options": [
            {
                "role_id": option.role_id,
                "role_kind": option.role_kind,
                "query": option.query,
                "idempotency_key": option.call.idempotency_key,
                "plan_sha256": option.plan_sha256,
                "closure_contract_sha256": option.closure_contract_sha256,
                "result_limit": option.call.result_limit,
            }
            for option in case.closure_options
        ],
        "empty_anchor_route_probe": route_probe.model_dump(mode="json"),
        "route_probe_uses_provider_observations": False,
    }


def dry_run(
    cohort: Literal["development", "unseen"] = "development",
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> dict[str, Any]:
    """Expose every frozen identity while constructing no live client."""

    fixture_sha256, manifest, cases = load_frozen_cases(
        cohort,
        fixture_path,
        expected_fixture_sha256=expected_fixture_sha256,
    )
    potential_calls = len(cases) * (1 + len(cases[0].closure_options))
    maximum_executed_calls = (
        len(cases) * manifest.provider_contract.maximum_requests_per_case
    )
    return {
        "mode": "openalex_adaptive_role_gap_v8_dry_run",
        "cohort": cohort,
        "method_id": manifest.method_id,
        "production_connected": False,
        "report_workflow_connected": False,
        "shadow_planner_connected": False,
        "checkpoint_connected": False,
        "recovery_connected": False,
        "real_network_calls_performed": False,
        "real_model_calls_performed": False,
        "private_labels_opened": False,
        "human_qualification_performed": False,
        "live_provider_requests_authorized": False,
        "live_model_calls_authorized": False,
        "fixture_sha256": fixture_sha256,
        "case_count": len(cases),
        "potential_call_identity_count": potential_calls,
        "maximum_executed_search_request_count": maximum_executed_calls,
        "maximum_provider_row_count": (
            maximum_executed_calls
            * manifest.provider_contract.result_limit_per_request
        ),
        "maximum_model_call_count": 0,
        "provider_contract": manifest.provider_contract.model_dump(mode="json"),
        "routing_contract": manifest.routing_contract.model_dump(mode="json"),
        "portfolio_contract": manifest.portfolio_contract.model_dump(mode="json"),
        "qualification_contract": manifest.qualification_contract.model_dump(
            mode="json"
        ),
        "provider_contract_sha256": manifest.provider_contract.sha256(),
        "routing_contract_sha256": manifest.routing_contract.sha256(),
        "portfolio_contract_sha256": manifest.portfolio_contract.sha256(),
        "qualification_contract_sha256": (
            manifest.qualification_contract.sha256()
        ),
        "cases": [_serialize_case(case) for case in cases],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cohort",
        choices=("development", "unseen"),
        default="development",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    print(json.dumps(dry_run(args.cohort), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
