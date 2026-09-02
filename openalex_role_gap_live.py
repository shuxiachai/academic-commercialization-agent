"""Write-once live runner for the frozen AC01-AC08 role-gap v8 study.

The production pipeline never imports this module. Each case spends one
anonymous OpenAlex anchor request, records a candidate-local role decision,
and may then spend one already-frozen closure request. The CLI defaults to a
zero-network protocol check; a provider run requires a separate owner
authorization naming the merged revision and frozen fixture.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from academic_agent.evidence import canonicalize_url, normalize_doi
from academic_agent.evidence_gap import ValidatedGapCall, source_collection_sha256
from academic_agent.openalex_evidence_set import EvidenceRoleKind
from academic_agent.source_pipeline import SourceCollection
from academic_agent.tools.anonymous_openalex_search import (
    AnonymousOpenAlexEvidenceSearchAdapter,
)
from academic_agent.tools.evidence_search import (
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
)
from openalex_role_gap_unseen import (
    EXPECTED_FIXTURE_SHA256,
    PreparedRoleGapCase,
    RoleGapCaseSpec,
    RoleGapClosureOption,
    RoleGapPortfolioContract,
    RoleGapProviderContract,
    RoleGapQualificationContract,
    RoleGapRouteDecision,
    RoleGapRoutingContract,
    RoleGapCandidateText,
    dry_run,
    load_frozen_cases,
    route_anchor_candidates,
)


_ROOT = Path(__file__).resolve().parent
_RUNNER_PATH = Path(__file__).resolve()
_IMPLEMENTATION_PATHS = {
    "anonymous_openalex_search.py": (
        _ROOT / "src/academic_agent/tools/anonymous_openalex_search.py"
    ),
    "domain_evidence_search.py": (
        _ROOT / "src/academic_agent/tools/domain_evidence_search.py"
    ),
    "evidence.py": _ROOT / "src/academic_agent/evidence.py",
    "evidence_gap.py": _ROOT / "src/academic_agent/evidence_gap.py",
    "evidence_search.py": _ROOT / "src/academic_agent/tools/evidence_search.py",
    "openalex_role_gap_unseen.py": _ROOT / "openalex_role_gap_unseen.py",
}
# Behavior-bearing dependencies are locked before output reservation or client
# construction. The runner records its observed self hash because embedding an
# expected digest of its own complete bytes would be recursive.
EXPECTED_IMPLEMENTATION_SHA256 = {
    "anonymous_openalex_search.py": (
        "bcaa201622fe5241115661cd9d5a6f7616761eddfedb9acf364b3693e7a044c9"
    ),
    "domain_evidence_search.py": (
        "ae79c38378321f6ce4481e682787ee49f930ec4c34b696d404fcf78d97b2eeab"
    ),
    "evidence.py": (
        "8e9eda3126dc1b81ec5a97e23ecfce8ba64c59a0d77c9a3fb3aec259f07b38c5"
    ),
    "evidence_gap.py": (
        "f2b978ce2af6b4e1d759116466d5a79371e6e4a7e414198b728b427cd93eea25"
    ),
    "evidence_search.py": (
        "2721debe3bb193b8971f8a89db0f4c91342944cb232f1829c02dd8d3780422d0"
    ),
    "openalex_role_gap_unseen.py": (
        "51c77c8615cf160b364ac68232c4a366f73a171aca9b011b73f311a5d0072b19"
    ),
}

MAXIMUM_REQUESTS = 16
MAXIMUM_PROVIDER_ROWS = 96
MAXIMUM_SOFT_STOP_USD = 0.02
ANONYMOUS_DAILY_BUDGET_USD = 0.10
_CASE_ORDER = tuple(f"AC{index:02d}" for index in range(1, 9))
_LANE_ORDER: tuple[Literal["anchor_search"], Literal["role_closure"]] = (
    "anchor_search",
    "role_closure",
)
_AGGREGATE_SOURCE_FILES = (
    "manifest.json",
    "execution.json",
    "provider-rows.csv",
    "route-decisions.csv",
    "unique-candidates.csv",
    "candidate-review.csv",
    "case-review.csv",
)
_PROVIDER_ROW_COLUMNS = (
    "case_id",
    "lane_id",
    "lane_index",
    "selected_role_id",
    "selected_role_kind",
    "provider",
    "tool",
    "provider_request_id",
    "provider_request_id_source",
    "provider_cost_basis",
    "provider_result_index",
    "adapter_disposition",
    "candidate_sha256",
    "occurrence_sha256",
    "unique_candidate_sha256",
    "deduplication_basis",
    "deduplication_value",
    "owner_occurrence_sha256",
    "title",
    "url",
    "normalized_doi",
    "publisher",
    "published_date",
    "evidence_summary",
    "summary_source",
    "citation_count",
    "provider_rejection_code",
    "rejection_detail",
    "latency_ms",
    "trace_id",
)
_ROUTE_COLUMNS = (
    "case_id",
    "route_execution_sha256",
    "anchor_execution_sha256",
    "checked",
    "action",
    "reason",
    "missing_role_ids",
    "selected_role_id",
    "selected_role_kind",
    "selected_query",
    "selected_idempotency_key",
    "selected_plan_sha256",
    "selected_closure_contract_sha256",
    "observations",
)
_UNIQUE_CANDIDATE_COLUMNS = (
    "case_id",
    "unique_candidate_sha256",
    "owner_occurrence_sha256",
    "lane_memberships",
    "selected_closure_role_id",
    "occurrence_sha256s",
    "provider_ranks",
    "candidate_sha256",
    "title",
    "url",
    "normalized_doi",
    "publisher",
    "published_date",
    "evidence_summary",
    "summary_source",
    "citation_count",
)
_CANDIDATE_REVIEW_COLUMNS = (
    "case_id",
    "topic",
    "unique_candidate_sha256",
    "lane_memberships",
    "selected_closure_role_id",
    "occurrence_count",
    "provider_ranks",
    "title",
    "url",
    "normalized_doi",
    "publisher",
    "published_date",
    "evidence_summary",
    "summary_source",
    "citation_count",
    "frozen_baseline_sources",
    "frozen_role_profile",
    "frozen_route_decision",
    "directly_relevant",
    "baseline_novel",
    "supported_role_ids",
    "closure_contributed_selected_role",
    "review_note",
)
_CASE_REVIEW_COLUMNS = (
    "case_id",
    "topic",
    "route_execution_sha256",
    "route_action",
    "route_reason",
    "missing_role_ids",
    "selected_role_id",
    "selected_role_kind",
    "anchor_candidate_count",
    "closure_candidate_count",
    "frozen_role_profile",
    "frozen_route_decision",
    "routing_decision_correct",
    "anchor_human_coverable_within_three",
    "union_human_coverable_within_three",
    "review_note",
)


LaneId = Literal["anchor_search", "role_closure"]
RoleGapAdapter = Callable[
    [ValidatedGapCall],
    ToolAdapterResponse | dict[str, Any],
]
AdapterFactory = Callable[[], RoleGapAdapter]
Clock = Callable[[], float]
StopReason = Literal[
    "completed",
    "soft_stop",
    "cost_uninspectable",
    "request_failed",
    "accounting_invalid",
]
CostState = Literal["known", "uninspectable", "not_observed"]
DeduplicationBasis = Literal[
    "new_unique",
    "normalized_doi",
    "canonical_openalex_url",
]


class OpenAlexRoleGapLiveError(ValueError):
    """Raised when the frozen adaptive live boundary cannot be represented."""


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


def _candidate_sha256(value: ToolEvidenceCandidate) -> str:
    return _model_sha256(value)


def _normalized_doi(value: str | None) -> str | None:
    normalized = normalize_doi(value)
    return normalized.casefold() if normalized else None


def _canonical_openalex_url(value: str) -> str:
    """Return one stable OpenAlex work identity, rejecting non-record URLs."""

    canonical = canonicalize_url(value)
    parsed = urlsplit(canonical)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").casefold() != "openalex.org"
        or parsed.query
        or re.fullmatch(r"/W[0-9]+", parsed.path, flags=re.IGNORECASE) is None
    ):
        raise OpenAlexRoleGapLiveError(
            "adaptive role-gap candidate URL is not a canonical OpenAlex work"
        )
    return f"https://openalex.org/{parsed.path.lstrip('/').upper()}"


def _has_frozen_openalex_accounting(response: ToolAdapterResponse) -> bool:
    """Return whether a response is safe to persist as provider evidence."""

    usage = response.provider_usage
    return (
        response.tool == "academic_search"
        and usage is not None
        and usage.provider == "openalex"
        and usage.cost_basis == "reported_usd"
        and usage.result_count <= 6
        and all(
            candidate.summary_source == "abstract"
            for candidate in response.candidates
        )
    )


class RoleGapFrozenCaseArtifact(BaseModel):
    """Complete deterministic AC expansion persisted before provider work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: RoleGapCaseSpec
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_collection: SourceCollection
    anchor_call: ValidatedGapCall
    anchor_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    anchor_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    closure_options: tuple[RoleGapClosureOption, ...] = Field(
        min_length=5,
        max_length=5,
    )

    @model_validator(mode="after")
    def _validate_expanded_identities(self) -> "RoleGapFrozenCaseArtifact":
        if source_collection_sha256(self.source_collection) != self.collection_sha256:
            raise ValueError("expanded source collection hash does not match")
        if self.spec.roles.profile().sha256() != self.profile_sha256:
            raise ValueError("expanded role profile hash does not match")
        role_ids = tuple(option.role_id for option in self.closure_options)
        expected_ids = tuple(role.role_id for _, role in self.spec.roles.ordered_roles())
        if role_ids != expected_ids:
            raise ValueError("manifest closure option order drifted")
        if self.anchor_call.query != self.spec.anchor_query:
            raise ValueError("manifest anchor query drifted")
        return self

class RoleGapManifestArtifact(BaseModel):
    """Write-once method, input, routing, budget, and disconnection boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    method_id: Literal["openalex-adaptive-role-gap-closure-v8"] = (
        "openalex-adaptive-role-gap-closure-v8"
    )
    mode: Literal["openalex_adaptive_role_gap_v8_manifest"] = (
        "openalex_adaptive_role_gap_v8_manifest"
    )
    cohort: Literal["development"] = "development"
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    planner_trigger_connected: Literal[False] = False
    recovery_connected: Literal[False] = False
    model_calls_authorized: Literal[False] = False
    api_key_used: Literal[False] = False
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    runner_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    maximum_requests: Literal[16] = MAXIMUM_REQUESTS
    maximum_provider_rows: Literal[96] = MAXIMUM_PROVIDER_ROWS
    anonymous_daily_budget_usd: Literal[0.1] = ANONYMOUS_DAILY_BUDGET_USD
    soft_stop_usd: float = Field(gt=0.0, le=MAXIMUM_SOFT_STOP_USD)
    provider_contract: RoleGapProviderContract
    routing_contract: RoleGapRoutingContract
    portfolio_contract: RoleGapPortfolioContract
    qualification_contract: RoleGapQualificationContract
    cases: tuple[RoleGapFrozenCaseArtifact, ...] = Field(
        min_length=8,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_frozen_contract(self) -> "RoleGapManifestArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("manifest fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("manifest implementation identities do not match")
        if tuple(case.spec.case_id for case in self.cases) != _CASE_ORDER:
            raise ValueError("manifest cases must remain ordered AC01 through AC08")
        possible_calls = sum(1 + len(case.closure_options) for case in self.cases)
        if possible_calls != 48:
            raise ValueError("manifest must retain eight anchors and forty closures")
        return self


class RoleGapLaneExecution(BaseModel):
    """One spent request with exact adaptive lane identity and accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^AC0[1-8]$")
    lane_id: LaneId
    lane_index: int = Field(ge=0, le=1)
    selected_role_id: str | None = None
    selected_role_kind: EvidenceRoleKind | None = None
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lane_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_id: str = Field(
        pattern=r"^openalex-role-gap-v8-ac0[1-8]-(?:anchor-search|role-closure-[a-z0-9-]+)$"
    )
    state: Literal["completed", "failed"]
    outbound_attempt_count: Literal[1] = 1
    response: ToolAdapterResponse | None = None
    failure_type: str | None = Field(default=None, max_length=100)
    failure_detail: str | None = Field(default=None, max_length=500)
    failure_retryable: bool | None = None
    search_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    latency_ms: float = Field(ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _validate_lane_and_response(self) -> "RoleGapLaneExecution":
        if self.lane_id != _LANE_ORDER[self.lane_index]:
            raise ValueError("lane identity and index drifted")
        if self.lane_id == "anchor_search":
            if self.selected_role_id is not None or self.selected_role_kind is not None:
                raise ValueError("anchor lane cannot carry a selected closure role")
        elif self.selected_role_id is None or self.selected_role_kind is None:
            raise ValueError("closure lane requires its selected role identity")

        if self.response is not None and not _has_frozen_openalex_accounting(
            self.response
        ):
            raise ValueError(
                "persisted response lacks the frozen abstract-bearing "
                "OpenAlex accounting"
            )
        if self.state == "completed":
            if self.response is None:
                raise ValueError("completed lane requires an adapter response")
            if any(
                value is not None
                for value in (
                    self.failure_type,
                    self.failure_detail,
                    self.failure_retryable,
                )
            ):
                raise ValueError("completed lane cannot carry failure metadata")
            if self.response.idempotency_key != self.idempotency_key:
                raise ValueError("response idempotency identity drifted")
            if self.response.search_cost_usd != self.search_cost_usd:
                raise ValueError("lane cost drifted from provider response")
        else:
            if self.failure_type is None or self.failure_detail is None:
                raise ValueError("failed lane requires explicit failure metadata")
            if self.response is not None and (
                self.response.search_cost_usd != self.search_cost_usd
            ):
                raise ValueError("failed lane cost drifted from provider response")
        return self


class RoleGapRouteExecution(BaseModel):
    """Durable checked route between the anchor journal and optional closure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^AC0[1-8]$")
    anchor_execution_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: RoleGapRouteDecision

    @model_validator(mode="after")
    def _validate_decision_identity(self) -> "RoleGapRouteExecution":
        if self.decision_sha256 != _model_sha256(self.decision):
            raise ValueError("route decision identity drifted")
        return self


class RoleGapCandidateOccurrence(BaseModel):
    """One provider candidate and its request, route, and owner lineage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^AC0[1-8]$")
    lane_id: LaneId
    lane_index: int = Field(ge=0, le=1)
    selected_role_id: str | None = None
    selected_role_kind: EvidenceRoleKind | None = None
    provider_result_index: int = Field(ge=0, le=5)
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    occurrence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    unique_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_occurrence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    deduplication_basis: DeduplicationBasis
    deduplication_value: str = Field(min_length=1, max_length=2000)
    normalized_doi: str | None = Field(default=None, max_length=300)
    canonical_openalex_url: str = Field(min_length=20, max_length=2000)
    candidate: ToolEvidenceCandidate

    @model_validator(mode="after")
    def _validate_occurrence_identity(self) -> "RoleGapCandidateOccurrence":
        if self.lane_id != _LANE_ORDER[self.lane_index]:
            raise ValueError("occurrence lane identity and index drifted")
        if self.lane_id == "anchor_search" and (
            self.selected_role_id is not None or self.selected_role_kind is not None
        ):
            raise ValueError("anchor occurrence cannot carry a closure role")
        if self.lane_id == "role_closure" and (
            self.selected_role_id is None or self.selected_role_kind is None
        ):
            raise ValueError("closure occurrence lost its route role")
        if _candidate_sha256(self.candidate) != self.candidate_sha256:
            raise ValueError("occurrence candidate identity drifted")
        if self.candidate.provider_result_index != self.provider_result_index:
            raise ValueError("occurrence provider rank drifted")
        is_owner = self.occurrence_sha256 == self.owner_occurrence_sha256
        if is_owner != (self.deduplication_basis == "new_unique"):
            raise ValueError("occurrence owner and deduplication basis disagree")
        if self.normalized_doi != _normalized_doi(self.candidate.doi):
            raise ValueError("occurrence DOI normalization drifted")
        if self.canonical_openalex_url != _canonical_openalex_url(self.candidate.url):
            raise ValueError("occurrence OpenAlex URL normalization drifted")
        return self


class RoleGapUniqueCandidate(BaseModel):
    """One first-seen source retaining all adaptive-lane occurrences."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^AC0[1-8]$")
    unique_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_occurrence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_candidate: ToolEvidenceCandidate
    lane_memberships: tuple[LaneId, ...] = Field(min_length=1, max_length=2)
    selected_closure_role_id: str | None = None
    occurrence_sha256s: tuple[str, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def _validate_unique_identity(self) -> "RoleGapUniqueCandidate":
        expected = _sha256_json(
            {
                "case_id": self.case_id,
                "owner_occurrence_sha256": self.owner_occurrence_sha256,
            }
        )
        if self.unique_candidate_sha256 != expected:
            raise ValueError("unique candidate identity drifted")
        if _candidate_sha256(self.primary_candidate) != self.primary_candidate_sha256:
            raise ValueError("primary candidate identity drifted")
        expected_lanes = tuple(
            lane for lane in _LANE_ORDER if lane in self.lane_memberships
        )
        if self.lane_memberships != expected_lanes:
            raise ValueError("unique candidate lane memberships are not canonical")
        has_closure = "role_closure" in self.lane_memberships
        if has_closure != (self.selected_closure_role_id is not None):
            raise ValueError("unique candidate closure membership lost its route role")
        if len(set(self.occurrence_sha256s)) != len(self.occurrence_sha256s):
            raise ValueError("unique candidate occurrences must be unique")
        return self


class RoleGapCasePortfolio(BaseModel):
    """One checked route joined to its completed anchor and optional closure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^AC0[1-8]$")
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    route_execution_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lane_execution_sha256s: tuple[str, ...] = Field(min_length=1, max_length=2)
    occurrences: tuple[RoleGapCandidateOccurrence, ...] = Field(max_length=12)
    unique_candidates: tuple[RoleGapUniqueCandidate, ...] = Field(max_length=12)

    @model_validator(mode="after")
    def _validate_portfolio_lineage(self) -> "RoleGapCasePortfolio":
        if any(item.case_id != self.case_id for item in self.occurrences):
            raise ValueError("portfolio occurrence belongs to another case")
        occurrence_ids = tuple(item.occurrence_sha256 for item in self.occurrences)
        if len(set(occurrence_ids)) != len(occurrence_ids):
            raise ValueError("portfolio occurrence identities must be unique")
        unique_ids = {item.unique_candidate_sha256 for item in self.unique_candidates}
        if len(unique_ids) != len(self.unique_candidates):
            raise ValueError("portfolio unique candidate identities must be unique")
        if any(
            item.unique_candidate_sha256 not in unique_ids
            for item in self.occurrences
        ):
            raise ValueError("portfolio occurrence lost its unique-source owner")
        for candidate in self.unique_candidates:
            linked = tuple(
                occurrence
                for occurrence in self.occurrences
                if occurrence.unique_candidate_sha256
                == candidate.unique_candidate_sha256
            )
            if tuple(item.occurrence_sha256 for item in linked) != (
                candidate.occurrence_sha256s
            ):
                raise ValueError("unique candidate occurrence lineage drifted")
            lanes = tuple(
                lane
                for lane in _LANE_ORDER
                if any(item.lane_id == lane for item in linked)
            )
            if lanes != candidate.lane_memberships:
                raise ValueError("unique candidate lane lineage drifted")
        return self


class RoleGapProviderSummary(BaseModel):
    """Provider accounting where missing observations cannot become zero cost."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openalex"] = "openalex"
    access_mode: Literal["anonymous_no_key"] = "anonymous_no_key"
    authorized_case_count: Literal[8] = 8
    maximum_request_count: Literal[16] = MAXIMUM_REQUESTS
    attempted_request_count: int = Field(ge=0, le=16)
    successful_request_count: int = Field(ge=0, le=16)
    completed_case_count: int = Field(ge=0, le=8)
    cost_state: CostState
    reported_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    total_latency_ms: float = Field(ge=0.0, allow_inf_nan=False)
    stopped_reason: StopReason

    @model_validator(mode="after")
    def _validate_accounting(self) -> "RoleGapProviderSummary":
        if self.successful_request_count > self.attempted_request_count:
            raise ValueError("successful requests cannot exceed attempted requests")
        if self.cost_state == "known" and self.reported_cost_usd is None:
            raise ValueError("known provider cost requires a numeric total")
        if self.cost_state != "known" and self.reported_cost_usd is not None:
            raise ValueError("unknown provider cost must keep USD null")
        completed = self.completed_case_count == len(_CASE_ORDER)
        if (self.stopped_reason == "completed") != completed:
            raise ValueError("provider completion does not match completed cases")
        return self


class RoleGapExecutionArtifact(BaseModel):
    """Final adaptive execution; source value remains a human judgment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    method_id: Literal["openalex-adaptive-role-gap-closure-v8"] = (
        "openalex-adaptive-role-gap-closure-v8"
    )
    mode: Literal["openalex_adaptive_role_gap_v8_execution"] = (
        "openalex_adaptive_role_gap_v8_execution"
    )
    cohort: Literal["development"] = "development"
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    planner_trigger_connected: Literal[False] = False
    recovery_connected: Literal[False] = False
    model_call_count: Literal[0] = 0
    api_key_used: Literal[False] = False
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    runner_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    maximum_requests: Literal[16] = MAXIMUM_REQUESTS
    maximum_provider_rows: Literal[96] = MAXIMUM_PROVIDER_ROWS
    anonymous_daily_budget_usd: Literal[0.1] = ANONYMOUS_DAILY_BUDGET_USD
    soft_stop_usd: float = Field(gt=0.0, le=MAXIMUM_SOFT_STOP_USD)
    request_count: int = Field(ge=0, le=16)
    successful_request_count: int = Field(ge=0, le=16)
    route_decision_count: int = Field(ge=0, le=8)
    closure_request_count: int = Field(ge=0, le=8)
    completed_portfolio_count: int = Field(ge=0, le=8)
    provider_row_count: int = Field(ge=0, le=96)
    provider_candidate_count: int = Field(ge=0, le=96)
    provider_rejection_count: int = Field(ge=0, le=96)
    unique_candidate_count: int = Field(ge=0, le=96)
    serialized_boundary_complete: Literal[True] = True
    overall_state: Literal["completed", "partial"]
    review_packet_eligibility: Literal["eligible_for_source_lock", "incomplete"]
    source_lock_state: Literal["not_created"] = "not_created"
    human_review_state: Literal["not_prepared"] = "not_prepared"
    source_value_state: Literal["not_evaluated"] = "not_evaluated"
    provider_summary: RoleGapProviderSummary
    lane_executions: tuple[RoleGapLaneExecution, ...] = Field(max_length=16)
    route_executions: tuple[RoleGapRouteExecution, ...] = Field(max_length=8)
    portfolios: tuple[RoleGapCasePortfolio, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def _validate_totals_and_states(self) -> "RoleGapExecutionArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("execution fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("execution implementation identities do not match")
        if len(self.lane_executions) != self.request_count:
            raise ValueError("request count must equal persisted journals")
        if sum(item.outbound_attempt_count for item in self.lane_executions) != (
            self.request_count
        ):
            raise ValueError("each journal must represent exactly one request")
        successful = sum(item.state == "completed" for item in self.lane_executions)
        if successful != self.successful_request_count:
            raise ValueError("successful-request count drifted")
        closure_count = sum(
            item.lane_id == "role_closure" for item in self.lane_executions
        )
        if closure_count != self.closure_request_count:
            raise ValueError("closure-request count drifted")
        if len(self.route_executions) != self.route_decision_count:
            raise ValueError("route-decision count drifted")
        route_case_ids = tuple(item.case_id for item in self.route_executions)
        if route_case_ids != _CASE_ORDER[: len(route_case_ids)]:
            raise ValueError("route executions must preserve the AC prefix")
        if tuple(item.case_id for item in self.portfolios) != _CASE_ORDER[
            : len(self.portfolios)
        ]:
            raise ValueError("case portfolios must preserve the AC prefix")
        if len(self.portfolios) != self.completed_portfolio_count:
            raise ValueError("completed-portfolio count drifted")

        lane_pairs = [(item.case_id, item.lane_id) for item in self.lane_executions]
        if len(set(lane_pairs)) != len(lane_pairs):
            raise ValueError("a case lane was attempted more than once")
        for case_index, case_id in enumerate(_CASE_ORDER):
            case_lanes = [item for item in self.lane_executions if item.case_id == case_id]
            if not case_lanes:
                if any(item[0] in _CASE_ORDER[case_index + 1 :] for item in lane_pairs):
                    raise ValueError("lane executions skipped an earlier AC case")
                continue
            if case_lanes[0].lane_id != "anchor_search" or len(case_lanes) > 2:
                raise ValueError("each case must begin with one anchor")
            route = next(
                (item for item in self.route_executions if item.case_id == case_id),
                None,
            )
            if len(case_lanes) == 2:
                if (
                    case_lanes[1].lane_id != "role_closure"
                    or route is None
                    or route.decision.action != "search"
                ):
                    raise ValueError("closure request lacks its checked search route")
                selected = route.decision.selected_closure
                if selected is None or (
                    case_lanes[1].idempotency_key != selected.call.idempotency_key
                ):
                    raise ValueError("closure request identity drifted from route")

        route_by_case = {item.case_id: item for item in self.route_executions}
        lane_by_pair = {
            (item.case_id, item.lane_id): item for item in self.lane_executions
        }
        for portfolio in self.portfolios:
            route = route_by_case.get(portfolio.case_id)
            anchor = lane_by_pair.get((portfolio.case_id, "anchor_search"))
            if route is None or anchor is None or anchor.state != "completed":
                raise ValueError("portfolio lacks a completed anchor and route")
            expected_lanes = [anchor]
            if route.decision.action == "search":
                closure = lane_by_pair.get((portfolio.case_id, "role_closure"))
                if closure is None or closure.state != "completed":
                    raise ValueError("search route portfolio lacks completed closure")
                expected_lanes.append(closure)
            if tuple(_model_sha256(item) for item in expected_lanes) != (
                portfolio.lane_execution_sha256s
            ):
                raise ValueError("portfolio request-journal identities drifted")
            if _model_sha256(route) != portfolio.route_execution_sha256:
                raise ValueError("portfolio route identity drifted")

        responses = tuple(
            item.response for item in self.lane_executions if item.response is not None
        )
        provider_candidates = sum(len(item.candidates) for item in responses)
        provider_rejections = sum(len(item.provider_rejections) for item in responses)
        if provider_candidates != self.provider_candidate_count:
            raise ValueError("provider-candidate count drifted")
        if provider_rejections != self.provider_rejection_count:
            raise ValueError("provider-rejection count drifted")
        if provider_candidates + provider_rejections != self.provider_row_count:
            raise ValueError("provider-row count drifted")
        if sum(len(item.unique_candidates) for item in self.portfolios) != (
            self.unique_candidate_count
        ):
            raise ValueError("unique-candidate count drifted")
        completed_occurrences = sum(len(item.occurrences) for item in self.portfolios)
        portfolio_case_ids = {item.case_id for item in self.portfolios}
        expected_occurrences = sum(
            len(item.response.candidates)
            for item in self.lane_executions
            if item.state == "completed"
            and item.response is not None
            and item.case_id in portfolio_case_ids
        )
        if completed_occurrences != expected_occurrences:
            raise ValueError("completed provider candidate lost portfolio lineage")
        if self.provider_summary.attempted_request_count != self.request_count:
            raise ValueError("provider request count drifted from execution")
        if self.provider_summary.successful_request_count != successful:
            raise ValueError("provider success count drifted from execution")
        if self.provider_summary.completed_case_count != len(self.portfolios):
            raise ValueError("provider completed-case count drifted")
        expected_latency = sum(item.latency_ms for item in self.lane_executions)
        if not math.isclose(
            self.provider_summary.total_latency_ms,
            expected_latency,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError("provider latency total drifted from request journals")
        completed = len(self.portfolios) == len(_CASE_ORDER)
        if (self.overall_state == "completed") != completed:
            raise ValueError("overall state does not match durable completion")
        expected_eligibility = (
            "eligible_for_source_lock" if completed else "incomplete"
        )
        if self.review_packet_eligibility != expected_eligibility:
            raise ValueError("review-packet eligibility drifted")
        return self


class _NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects because one lane authorizes one outbound request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del req, fp, code, msg, headers, newurl
        return None


class _OneRequestTransport:
    """Concrete transport with neither redirect following nor internal retry."""

    def __call__(
        self,
        *,
        endpoint: str,
        method: str,
        body: bytes | None,
        headers: Mapping[str, str],
        timeout: float,
    ) -> bytes:
        request = Request(endpoint, data=body, headers=dict(headers), method=method)
        opener = build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            return response.read()


def _file_sha256(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise OpenAlexRoleGapLiveError(
            f"could not read frozen implementation file {path.name}: {exc}"
        ) from exc


def verify_frozen_implementation() -> dict[str, str]:
    """Reject dependency drift before output or adapter construction."""

    if set(_IMPLEMENTATION_PATHS) != set(EXPECTED_IMPLEMENTATION_SHA256):
        raise OpenAlexRoleGapLiveError(
            "adaptive role-gap implementation lock names are inconsistent"
        )
    observed = {
        name: _file_sha256(path) for name, path in _IMPLEMENTATION_PATHS.items()
    }
    if observed != EXPECTED_IMPLEMENTATION_SHA256:
        changed = sorted(
            name
            for name, digest in observed.items()
            if EXPECTED_IMPLEMENTATION_SHA256.get(name) != digest
        )
        raise OpenAlexRoleGapLiveError(
            "adaptive role-gap implementation identity drifted: "
            + ", ".join(changed)
        )
    return observed


def protocol_dry_run() -> dict[str, Any]:
    """Expose frozen AC identities while constructing no provider client."""

    result = dry_run("development")
    result["implementation_sha256"] = verify_frozen_implementation()
    result["runner_sha256"] = _file_sha256(_RUNNER_PATH)
    result["live_runner_maximum_requests"] = MAXIMUM_REQUESTS
    result["live_runner_maximum_soft_stop_usd"] = MAXIMUM_SOFT_STOP_USD
    return result


def _manifest_artifact(
    cases: tuple[PreparedRoleGapCase, ...],
    *,
    fixture_sha256: str,
    implementation_sha256: dict[str, str],
    runner_sha256: str,
    soft_stop_usd: float,
    provider_contract: RoleGapProviderContract,
    routing_contract: RoleGapRoutingContract,
    portfolio_contract: RoleGapPortfolioContract,
    qualification_contract: RoleGapQualificationContract,
) -> RoleGapManifestArtifact:
    return RoleGapManifestArtifact(
        fixture_sha256=fixture_sha256,
        implementation_sha256=implementation_sha256,
        runner_sha256=runner_sha256,
        soft_stop_usd=soft_stop_usd,
        provider_contract=provider_contract,
        routing_contract=routing_contract,
        portfolio_contract=portfolio_contract,
        qualification_contract=qualification_contract,
        cases=tuple(
            RoleGapFrozenCaseArtifact(
                spec=case.spec,
                collection_sha256=case.collection_sha256,
                profile_sha256=case.profile_sha256,
                case_contract_sha256=case.case_contract_sha256,
                source_collection=case.collection,
                anchor_call=case.anchor_call,
                anchor_plan_sha256=case.anchor_plan_sha256,
                anchor_contract_sha256=case.anchor_contract_sha256,
                closure_options=case.closure_options,
            )
            for case in cases
        ),
    )


def _write_new(path: Path, value: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(value)
    except OSError as exc:
        raise OpenAlexRoleGapLiveError(
            f"could not create write-once artifact {path}: {exc}"
        ) from exc


def _json_text(value: BaseModel | dict[str, Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _write_lane_journal(
    output_dir: Path,
    execution: RoleGapLaneExecution,
) -> None:
    journal_dir = output_dir / "lane-executions"
    journal_dir.mkdir(exist_ok=True)
    _write_new(
        journal_dir / f"{execution.case_id}--{execution.lane_id}.json",
        _json_text(execution),
    )


def _write_route_journal(
    output_dir: Path,
    execution: RoleGapRouteExecution,
) -> None:
    route_dir = output_dir / "route-executions"
    route_dir.mkdir(exist_ok=True)
    _write_new(route_dir / f"{execution.case_id}.json", _json_text(execution))


def _write_case_portfolio(
    output_dir: Path,
    portfolio: RoleGapCasePortfolio,
) -> None:
    portfolio_dir = output_dir / "case-portfolios"
    portfolio_dir.mkdir(exist_ok=True)
    _write_new(
        portfolio_dir / f"{portfolio.case_id}.json",
        _json_text(portfolio),
    )


def _validation_detail(exc: ValidationError) -> str:
    """Describe invalid structure without copying potentially unsafe input."""

    details = []
    for error in exc.errors(include_input=False)[:4]:
        location = ".".join(str(part) for part in error["loc"]) or "response"
        details.append(f"{location}:{error['type']}")
    return "; ".join(details)[:500] or "adapter response failed validation"


def _lane_identity(
    case: PreparedRoleGapCase,
    lane_id: LaneId,
    selected_closure: RoleGapClosureOption | None,
) -> tuple[ValidatedGapCall, str, str, str | None, EvidenceRoleKind | None]:
    if lane_id == "anchor_search":
        if selected_closure is not None:
            raise OpenAlexRoleGapLiveError("anchor lane cannot select a closure")
        return (
            case.anchor_call,
            case.anchor_plan_sha256,
            case.anchor_contract_sha256,
            None,
            None,
        )
    if selected_closure is None:
        raise OpenAlexRoleGapLiveError("closure lane requires a frozen option")
    return (
        selected_closure.call,
        selected_closure.plan_sha256,
        selected_closure.closure_contract_sha256,
        selected_closure.role_id,
        selected_closure.role_kind,
    )


def _trace_id(
    case_id: str,
    lane_id: LaneId,
    selected_role_id: str | None,
) -> str:
    suffix = lane_id.replace("_", "-")
    if selected_role_id is not None:
        suffix = f"{suffix}-{selected_role_id.replace('_', '-')}"
    return f"openalex-role-gap-v8-{case_id.casefold()}-{suffix}"


def _failure_execution(
    case: PreparedRoleGapCase,
    lane_id: LaneId,
    selected_closure: RoleGapClosureOption | None,
    *,
    failure_type: str,
    failure_detail: str,
    failure_retryable: bool | None,
    latency_ms: float,
    response: ToolAdapterResponse | None = None,
    search_cost_usd: float | None = None,
) -> RoleGapLaneExecution:
    call, plan_sha256, contract_sha256, role_id, role_kind = _lane_identity(
        case,
        lane_id,
        selected_closure,
    )
    return RoleGapLaneExecution(
        case_id=case.spec.case_id,
        lane_id=lane_id,
        lane_index=_LANE_ORDER.index(lane_id),
        selected_role_id=role_id,
        selected_role_kind=role_kind,
        collection_sha256=case.collection_sha256,
        profile_sha256=case.profile_sha256,
        case_contract_sha256=case.case_contract_sha256,
        plan_sha256=plan_sha256,
        lane_contract_sha256=contract_sha256,
        idempotency_key=call.idempotency_key,
        trace_id=_trace_id(case.spec.case_id, lane_id, role_id),
        state="failed",
        response=response,
        failure_type=failure_type,
        failure_detail=failure_detail[:500],
        failure_retryable=failure_retryable,
        search_cost_usd=search_cost_usd,
        latency_ms=latency_ms,
    )


def _completed_execution(
    case: PreparedRoleGapCase,
    lane_id: LaneId,
    selected_closure: RoleGapClosureOption | None,
    response: ToolAdapterResponse,
    latency_ms: float,
) -> RoleGapLaneExecution:
    call, plan_sha256, contract_sha256, role_id, role_kind = _lane_identity(
        case,
        lane_id,
        selected_closure,
    )
    return RoleGapLaneExecution(
        case_id=case.spec.case_id,
        lane_id=lane_id,
        lane_index=_LANE_ORDER.index(lane_id),
        selected_role_id=role_id,
        selected_role_kind=role_kind,
        collection_sha256=case.collection_sha256,
        profile_sha256=case.profile_sha256,
        case_contract_sha256=case.case_contract_sha256,
        plan_sha256=plan_sha256,
        lane_contract_sha256=contract_sha256,
        idempotency_key=call.idempotency_key,
        trace_id=_trace_id(case.spec.case_id, lane_id, role_id),
        state="completed",
        response=response,
        search_cost_usd=response.search_cost_usd,
        latency_ms=latency_ms,
    )


def _elapsed_ms(clock: Clock, started_at: float) -> float:
    elapsed = (clock() - started_at) * 1000.0
    if not math.isfinite(elapsed) or elapsed < 0.0:
        raise OpenAlexRoleGapLiveError("monotonic request latency is invalid")
    return elapsed


def _execute_request(
    adapter: RoleGapAdapter,
    case: PreparedRoleGapCase,
    lane_id: LaneId,
    selected_closure: RoleGapClosureOption | None,
    clock: Clock,
) -> tuple[RoleGapLaneExecution, StopReason | None]:
    call, _, _, _, _ = _lane_identity(case, lane_id, selected_closure)
    started_at = clock()
    try:
        raw_response = adapter(call)
    except ToolAdapterFailure as exc:
        return (
            _failure_execution(
                case,
                lane_id,
                selected_closure,
                failure_type=exc.failure_type,
                failure_detail=str(exc),
                failure_retryable=exc.retryable,
                latency_ms=_elapsed_ms(clock, started_at),
                search_cost_usd=exc.search_cost_usd,
            ),
            "request_failed",
        )
    latency_ms = _elapsed_ms(clock, started_at)
    try:
        response = ToolAdapterResponse.model_validate(raw_response)
    except ValidationError as exc:
        return (
            _failure_execution(
                case,
                lane_id,
                selected_closure,
                failure_type="adapter_response_invalid",
                failure_detail=_validation_detail(exc),
                failure_retryable=False,
                latency_ms=latency_ms,
            ),
            "accounting_invalid",
        )
    if response.idempotency_key != call.idempotency_key:
        preserved_response = (
            response if _has_frozen_openalex_accounting(response) else None
        )
        return (
            _failure_execution(
                case,
                lane_id,
                selected_closure,
                failure_type="adapter_identity_mismatch",
                failure_detail=(
                    "adapter response idempotency key does not match the authorized lane"
                ),
                failure_retryable=False,
                latency_ms=latency_ms,
                response=preserved_response,
                search_cost_usd=(
                    response.search_cost_usd
                    if preserved_response is not None
                    else None
                ),
            ),
            "accounting_invalid",
        )
    try:
        execution = _completed_execution(
            case,
            lane_id,
            selected_closure,
            response,
            latency_ms,
        )
    except ValidationError as exc:
        # A Pydantic-shaped response can still fail this study's stricter
        # OpenAlex accounting contract. Without provider usage there is no
        # auditable request or row identity, so retaining the payload would
        # either fabricate zero cost or make unaccounted candidates look
        # eligible for aggregation.
        preserved_response = (
            response if _has_frozen_openalex_accounting(response) else None
        )
        return (
            _failure_execution(
                case,
                lane_id,
                selected_closure,
                failure_type="adapter_response_invalid",
                failure_detail=_validation_detail(exc),
                failure_retryable=False,
                latency_ms=latency_ms,
                response=preserved_response,
                search_cost_usd=(
                    response.search_cost_usd
                    if preserved_response is not None
                    else None
                ),
            ),
            "accounting_invalid",
        )
    return execution, None


def _route_execution(
    case: PreparedRoleGapCase,
    anchor: RoleGapLaneExecution,
) -> RoleGapRouteExecution:
    if anchor.state != "completed" or anchor.response is None:
        raise OpenAlexRoleGapLiveError("routing requires a completed anchor response")
    candidates = tuple(
        RoleGapCandidateText(
            title=candidate.title,
            abstract=candidate.evidence_summary,
        )
        for candidate in anchor.response.candidates
    )
    decision = route_anchor_candidates(case, candidates)
    return RoleGapRouteExecution(
        case_id=case.spec.case_id,
        anchor_execution_sha256=_model_sha256(anchor),
        decision_sha256=_model_sha256(decision),
        decision=decision,
    )


def _occurrence_sha256(
    case_id: str,
    lane_id: LaneId,
    provider_result_index: int,
    candidate_sha256: str,
) -> str:
    return _sha256_json(
        {
            "case_id": case_id,
            "lane_id": lane_id,
            "provider_result_index": provider_result_index,
            "candidate_sha256": candidate_sha256,
        }
    )


def _compatible_url_owner(
    owners: list[dict[str, Any]],
    normalized_doi: str | None,
) -> dict[str, Any] | None:
    """Return one unambiguous owner without merging conflicting DOIs."""

    compatible = [
        owner
        for owner in owners
        if owner["normalized_doi"] is None
        or normalized_doi is None
        or owner["normalized_doi"] == normalized_doi
    ]
    return compatible[0] if len(compatible) == 1 else None


def build_case_portfolio(
    case: PreparedRoleGapCase,
    route: RoleGapRouteExecution,
    lane_executions: tuple[RoleGapLaneExecution, ...],
) -> RoleGapCasePortfolio:
    """Join the checked adaptive path while retaining every occurrence."""

    expected_lane_ids: tuple[LaneId, ...] = (
        ("anchor_search", "role_closure")
        if route.decision.action == "search"
        else ("anchor_search",)
    )
    if (
        route.case_id != case.spec.case_id
        or tuple(item.lane_id for item in lane_executions) != expected_lane_ids
        or any(
            item.state != "completed" or item.response is None
            for item in lane_executions
        )
    ):
        raise OpenAlexRoleGapLiveError(
            "case portfolio requires its ordered completed adaptive path"
        )
    if route.anchor_execution_sha256 != _model_sha256(lane_executions[0]):
        raise OpenAlexRoleGapLiveError("route anchor identity drifted")
    selected = route.decision.selected_closure
    if route.decision.action == "search":
        if selected is None or lane_executions[1].idempotency_key != (
            selected.call.idempotency_key
        ):
            raise OpenAlexRoleGapLiveError("portfolio closure identity drifted")

    owner_records: list[dict[str, Any]] = []
    seen_dois: dict[str, dict[str, Any]] = {}
    seen_urls: dict[str, list[dict[str, Any]]] = {}
    occurrences: list[RoleGapCandidateOccurrence] = []
    for lane_execution in lane_executions:
        response = lane_execution.response
        if response is None:  # pragma: no cover - guarded above and by Pydantic
            raise OpenAlexRoleGapLiveError("completed lane lost its response")
        for candidate in sorted(
            response.candidates,
            key=lambda item: (
                item.provider_result_index
                if item.provider_result_index is not None
                else -1
            ),
        ):
            provider_index = candidate.provider_result_index
            if provider_index is None:
                raise OpenAlexRoleGapLiveError(
                    "provider-accounted candidate lost its result index"
                )
            candidate_digest = _candidate_sha256(candidate)
            occurrence_digest = _occurrence_sha256(
                case.spec.case_id,
                lane_execution.lane_id,
                provider_index,
                candidate_digest,
            )
            normalized_doi = _normalized_doi(candidate.doi)
            canonical_url = _canonical_openalex_url(candidate.url)
            owner = seen_dois.get(normalized_doi) if normalized_doi else None
            basis: DeduplicationBasis = "normalized_doi"
            deduplication_value = normalized_doi or canonical_url
            if owner is None:
                owner = _compatible_url_owner(
                    seen_urls.get(canonical_url, []),
                    normalized_doi,
                )
                basis = "canonical_openalex_url"
                deduplication_value = canonical_url
            if owner is None:
                unique_digest = _sha256_json(
                    {
                        "case_id": case.spec.case_id,
                        "owner_occurrence_sha256": occurrence_digest,
                    }
                )
                owner = {
                    "unique_candidate_sha256": unique_digest,
                    "owner_occurrence_sha256": occurrence_digest,
                    "primary_candidate_sha256": candidate_digest,
                    "primary_candidate": candidate,
                    "normalized_doi": normalized_doi,
                    "canonical_openalex_url": canonical_url,
                    "lane_memberships": [],
                    "occurrence_sha256s": [],
                    "selected_closure_role_id": None,
                }
                owner_records.append(owner)
                basis = "new_unique"
                deduplication_value = normalized_doi or canonical_url
                if normalized_doi:
                    seen_dois[normalized_doi] = owner
                seen_urls.setdefault(canonical_url, []).append(owner)
            # A later occurrence can add a DOI to a first-seen URL-only owner,
            # or add another canonical URL to a DOI owner. Register both
            # secondary identities without changing which source was first.
            if normalized_doi and normalized_doi not in seen_dois:
                seen_dois[normalized_doi] = owner
            url_owners = seen_urls.setdefault(canonical_url, [])
            if not any(existing is owner for existing in url_owners):
                url_owners.append(owner)
            if lane_execution.lane_id not in owner["lane_memberships"]:
                owner["lane_memberships"].append(lane_execution.lane_id)
            if lane_execution.selected_role_id is not None:
                owner["selected_closure_role_id"] = lane_execution.selected_role_id
            owner["occurrence_sha256s"].append(occurrence_digest)
            occurrences.append(
                RoleGapCandidateOccurrence(
                    case_id=case.spec.case_id,
                    lane_id=lane_execution.lane_id,
                    lane_index=lane_execution.lane_index,
                    selected_role_id=lane_execution.selected_role_id,
                    selected_role_kind=lane_execution.selected_role_kind,
                    provider_result_index=provider_index,
                    candidate_sha256=candidate_digest,
                    occurrence_sha256=occurrence_digest,
                    unique_candidate_sha256=owner["unique_candidate_sha256"],
                    owner_occurrence_sha256=owner["owner_occurrence_sha256"],
                    deduplication_basis=basis,
                    deduplication_value=deduplication_value,
                    normalized_doi=normalized_doi,
                    canonical_openalex_url=canonical_url,
                    candidate=candidate,
                )
            )

    unique_candidates = tuple(
        RoleGapUniqueCandidate(
            case_id=case.spec.case_id,
            unique_candidate_sha256=owner["unique_candidate_sha256"],
            owner_occurrence_sha256=owner["owner_occurrence_sha256"],
            primary_candidate_sha256=owner["primary_candidate_sha256"],
            primary_candidate=owner["primary_candidate"],
            lane_memberships=tuple(owner["lane_memberships"]),
            selected_closure_role_id=owner["selected_closure_role_id"],
            occurrence_sha256s=tuple(owner["occurrence_sha256s"]),
        )
        for owner in owner_records
    )
    return RoleGapCasePortfolio(
        case_id=case.spec.case_id,
        collection_sha256=case.collection_sha256,
        profile_sha256=case.profile_sha256,
        case_contract_sha256=case.case_contract_sha256,
        route_execution_sha256=_model_sha256(route),
        lane_execution_sha256s=tuple(
            _model_sha256(item) for item in lane_executions
        ),
        occurrences=tuple(occurrences),
        unique_candidates=unique_candidates,
    )


def _provider_cost(
    executions: list[RoleGapLaneExecution],
) -> tuple[CostState, float | None]:
    if not executions:
        return "not_observed", None
    if any(item.search_cost_usd is None for item in executions):
        return "uninspectable", None
    return "known", sum(
        item.search_cost_usd
        for item in executions
        if item.search_cost_usd is not None
    )


def _json_compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _occurrence_by_provider_row(
    portfolios: tuple[RoleGapCasePortfolio, ...],
) -> dict[tuple[str, LaneId, int], RoleGapCandidateOccurrence]:
    return {
        (item.case_id, item.lane_id, item.provider_result_index): item
        for portfolio in portfolios
        for item in portfolio.occurrences
    }


def _provider_rows(
    executions: tuple[RoleGapLaneExecution, ...],
    portfolios: tuple[RoleGapCasePortfolio, ...],
) -> list[dict[str, str]]:
    occurrence_by_row = _occurrence_by_provider_row(portfolios)
    rows: list[dict[str, str]] = []
    for execution in executions:
        response = execution.response
        if response is None:
            continue
        usage = response.provider_usage
        if usage is None:
            raise OpenAlexRoleGapLiveError(
                "persisted OpenAlex response lost provider accounting"
            )
        for candidate in response.candidates:
            provider_index = candidate.provider_result_index
            if provider_index is None:
                raise OpenAlexRoleGapLiveError(
                    "persisted provider candidate lost its result index"
                )
            occurrence = occurrence_by_row.get(
                (execution.case_id, execution.lane_id, provider_index)
            )
            rows.append(
                {
                    "case_id": execution.case_id,
                    "lane_id": execution.lane_id,
                    "lane_index": str(execution.lane_index),
                    "selected_role_id": execution.selected_role_id or "",
                    "selected_role_kind": execution.selected_role_kind or "",
                    "provider": usage.provider,
                    "tool": response.tool,
                    "provider_request_id": usage.request_id,
                    "provider_request_id_source": usage.request_id_source,
                    "provider_cost_basis": usage.cost_basis,
                    "provider_result_index": str(provider_index),
                    "adapter_disposition": "candidate",
                    "candidate_sha256": _candidate_sha256(candidate),
                    "occurrence_sha256": (
                        occurrence.occurrence_sha256 if occurrence else ""
                    ),
                    "unique_candidate_sha256": (
                        occurrence.unique_candidate_sha256 if occurrence else ""
                    ),
                    "deduplication_basis": (
                        occurrence.deduplication_basis
                        if occurrence
                        else "NOT_EVALUATED"
                    ),
                    "deduplication_value": (
                        occurrence.deduplication_value if occurrence else ""
                    ),
                    "owner_occurrence_sha256": (
                        occurrence.owner_occurrence_sha256 if occurrence else ""
                    ),
                    "title": candidate.title,
                    "url": candidate.url,
                    "normalized_doi": _normalized_doi(candidate.doi) or "",
                    "publisher": candidate.publisher,
                    "published_date": (
                        candidate.published_date.isoformat()
                        if candidate.published_date
                        else ""
                    ),
                    "evidence_summary": candidate.evidence_summary,
                    "summary_source": candidate.summary_source,
                    "citation_count": (
                        str(candidate.citation_count)
                        if candidate.citation_count is not None
                        else ""
                    ),
                    "provider_rejection_code": "",
                    "rejection_detail": "",
                    "latency_ms": str(execution.latency_ms),
                    "trace_id": execution.trace_id,
                }
            )
        for rejection in response.provider_rejections:
            rows.append(
                {
                    "case_id": execution.case_id,
                    "lane_id": execution.lane_id,
                    "lane_index": str(execution.lane_index),
                    "selected_role_id": execution.selected_role_id or "",
                    "selected_role_kind": execution.selected_role_kind or "",
                    "provider": usage.provider,
                    "tool": response.tool,
                    "provider_request_id": usage.request_id,
                    "provider_request_id_source": usage.request_id_source,
                    "provider_cost_basis": usage.cost_basis,
                    "provider_result_index": str(rejection.provider_result_index),
                    "adapter_disposition": "provider_rejected",
                    "candidate_sha256": "",
                    "occurrence_sha256": "",
                    "unique_candidate_sha256": "",
                    "deduplication_basis": "NOT_APPLICABLE",
                    "deduplication_value": "",
                    "owner_occurrence_sha256": "",
                    "title": rejection.title or "",
                    "url": rejection.url or "",
                    "normalized_doi": "",
                    "publisher": "",
                    "published_date": "",
                    "evidence_summary": "",
                    "summary_source": "",
                    "citation_count": "",
                    "provider_rejection_code": rejection.code,
                    "rejection_detail": rejection.detail,
                    "latency_ms": str(execution.latency_ms),
                    "trace_id": execution.trace_id,
                }
            )
    rows.sort(
        key=lambda row: (
            _CASE_ORDER.index(row["case_id"]),
            int(row["lane_index"]),
            int(row["provider_result_index"]),
        )
    )
    return rows


def _route_rows(
    routes: tuple[RoleGapRouteExecution, ...],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for route in routes:
        decision = route.decision
        selected = decision.selected_closure
        rows.append(
            {
                "case_id": route.case_id,
                "route_execution_sha256": _model_sha256(route),
                "anchor_execution_sha256": route.anchor_execution_sha256,
                "checked": "true",
                "action": decision.action,
                "reason": decision.reason,
                "missing_role_ids": _json_compact(decision.missing_role_ids),
                "selected_role_id": selected.role_id if selected else "",
                "selected_role_kind": selected.role_kind if selected else "",
                "selected_query": selected.query if selected else "",
                "selected_idempotency_key": (
                    selected.call.idempotency_key if selected else ""
                ),
                "selected_plan_sha256": selected.plan_sha256 if selected else "",
                "selected_closure_contract_sha256": (
                    selected.closure_contract_sha256 if selected else ""
                ),
                "observations": _json_compact(
                    [
                        observation.model_dump(mode="json")
                        for observation in decision.observations
                    ]
                ),
            }
        )
    return rows


def _unique_and_review_rows(
    manifest: RoleGapManifestArtifact,
    routes: tuple[RoleGapRouteExecution, ...],
    portfolios: tuple[RoleGapCasePortfolio, ...],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    case_inputs = {item.spec.case_id: item for item in manifest.cases}
    route_by_case = {item.case_id: item for item in routes}
    unique_rows: list[dict[str, str]] = []
    candidate_review_rows: list[dict[str, str]] = []
    case_review_rows: list[dict[str, str]] = []
    for portfolio in portfolios:
        frozen = case_inputs[portfolio.case_id]
        route = route_by_case[portfolio.case_id]
        occurrence_by_id = {
            item.occurrence_sha256: item for item in portfolio.occurrences
        }
        anchor_count = sum(
            item.lane_id == "anchor_search" for item in portfolio.occurrences
        )
        closure_count = sum(
            item.lane_id == "role_closure" for item in portfolio.occurrences
        )
        selected = route.decision.selected_closure
        frozen_profile = _json_compact(
            frozen.spec.roles.profile().model_dump(mode="json")
        )
        frozen_route = _json_compact(route.decision.model_dump(mode="json"))
        case_review_rows.append(
            {
                "case_id": portfolio.case_id,
                "topic": frozen.spec.topic,
                "route_execution_sha256": _model_sha256(route),
                "route_action": route.decision.action,
                "route_reason": route.decision.reason,
                "missing_role_ids": _json_compact(
                    route.decision.missing_role_ids
                ),
                "selected_role_id": selected.role_id if selected else "",
                "selected_role_kind": selected.role_kind if selected else "",
                "anchor_candidate_count": str(anchor_count),
                "closure_candidate_count": str(closure_count),
                "frozen_role_profile": frozen_profile,
                "frozen_route_decision": frozen_route,
                "routing_decision_correct": "",
                "anchor_human_coverable_within_three": "",
                "union_human_coverable_within_three": "",
                "review_note": "",
            }
        )
        for item in portfolio.unique_candidates:
            candidate = item.primary_candidate
            linked = [
                occurrence_by_id[occurrence_id]
                for occurrence_id in item.occurrence_sha256s
            ]
            provider_ranks = [
                {
                    "lane_id": occurrence.lane_id,
                    "selected_role_id": occurrence.selected_role_id,
                    "provider_result_index": occurrence.provider_result_index,
                }
                for occurrence in linked
            ]
            memberships = _json_compact(item.lane_memberships)
            common = {
                "case_id": item.case_id,
                "unique_candidate_sha256": item.unique_candidate_sha256,
                "lane_memberships": memberships,
                "selected_closure_role_id": (
                    item.selected_closure_role_id or ""
                ),
                "provider_ranks": _json_compact(provider_ranks),
                "title": candidate.title,
                "url": candidate.url,
                "normalized_doi": _normalized_doi(candidate.doi) or "",
                "publisher": candidate.publisher,
                "published_date": (
                    candidate.published_date.isoformat()
                    if candidate.published_date
                    else ""
                ),
                "evidence_summary": candidate.evidence_summary,
                "summary_source": candidate.summary_source,
                "citation_count": (
                    str(candidate.citation_count)
                    if candidate.citation_count is not None
                    else ""
                ),
            }
            unique_rows.append(
                {
                    **common,
                    "owner_occurrence_sha256": item.owner_occurrence_sha256,
                    "occurrence_sha256s": _json_compact(
                        item.occurrence_sha256s
                    ),
                    "candidate_sha256": item.primary_candidate_sha256,
                }
            )
            candidate_review_rows.append(
                {
                    **common,
                    "topic": frozen.spec.topic,
                    "occurrence_count": str(len(item.occurrence_sha256s)),
                    "frozen_baseline_sources": _json_compact(
                        [
                            source.model_dump(mode="json")
                            for source in frozen.source_collection.academic_sources
                        ]
                    ),
                    "frozen_role_profile": frozen_profile,
                    "frozen_route_decision": frozen_route,
                    "directly_relevant": "",
                    "baseline_novel": "",
                    "supported_role_ids": "",
                    "closure_contributed_selected_role": "",
                    "review_note": "",
                }
            )
    return unique_rows, candidate_review_rows, case_review_rows


def _csv_text(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _validate_route_manifest_binding(
    manifest: RoleGapManifestArtifact,
    routes: tuple[RoleGapRouteExecution, ...],
) -> None:
    """Reject a valid route object bound to the wrong frozen AC case."""

    cases = {item.spec.case_id: item for item in manifest.cases}
    for route in routes:
        frozen = cases[route.case_id]
        expected_role_ids = tuple(
            role.role_id for _, role in frozen.spec.roles.ordered_roles()
        )
        observed_role_ids = tuple(
            observation.role_id for observation in route.decision.observations
        )
        if observed_role_ids != expected_role_ids:
            raise OpenAlexRoleGapLiveError(
                f"{route.case_id}: route observations drifted from frozen roles"
            )
        selected = route.decision.selected_closure
        if selected is None:
            continue
        expected = next(
            (
                option
                for option in frozen.closure_options
                if option.role_id == selected.role_id
            ),
            None,
        )
        if expected is None or expected != selected:
            raise OpenAlexRoleGapLiveError(
                f"{route.case_id}: selected closure drifted from manifest"
            )


def _write_final_artifacts(
    output_dir: Path,
    manifest: RoleGapManifestArtifact,
    artifact: RoleGapExecutionArtifact,
) -> None:
    _validate_route_manifest_binding(manifest, artifact.route_executions)
    provider_rows = _provider_rows(
        artifact.lane_executions,
        artifact.portfolios,
    )
    route_rows = _route_rows(artifact.route_executions)
    unique_rows, candidate_review_rows, case_review_rows = (
        _unique_and_review_rows(
            manifest,
            artifact.route_executions,
            artifact.portfolios,
        )
    )
    if len(provider_rows) != artifact.provider_row_count:
        raise OpenAlexRoleGapLiveError(
            "provider row disappeared before the aggregate boundary"
        )
    if len(route_rows) != artifact.route_decision_count:
        raise OpenAlexRoleGapLiveError(
            "route decision disappeared before the aggregate boundary"
        )
    if len(unique_rows) != artifact.unique_candidate_count:
        raise OpenAlexRoleGapLiveError(
            "unique candidate disappeared before the aggregate boundary"
        )
    if len(candidate_review_rows) != artifact.unique_candidate_count:
        raise OpenAlexRoleGapLiveError(
            "candidate disappeared before the blank review boundary"
        )
    if len(case_review_rows) != artifact.completed_portfolio_count:
        raise OpenAlexRoleGapLiveError(
            "completed case disappeared before the route-review boundary"
        )
    _write_new(output_dir / "execution.json", _json_text(artifact))
    _write_new(
        output_dir / "provider-rows.csv",
        _csv_text(_PROVIDER_ROW_COLUMNS, provider_rows),
    )
    _write_new(
        output_dir / "route-decisions.csv",
        _csv_text(_ROUTE_COLUMNS, route_rows),
    )
    _write_new(
        output_dir / "unique-candidates.csv",
        _csv_text(_UNIQUE_CANDIDATE_COLUMNS, unique_rows),
    )
    _write_new(
        output_dir / "candidate-review.csv",
        _csv_text(_CANDIDATE_REVIEW_COLUMNS, candidate_review_rows),
    )
    _write_new(
        output_dir / "case-review.csv",
        _csv_text(_CASE_REVIEW_COLUMNS, case_review_rows),
    )
    source_paths = [output_dir / name for name in _AGGREGATE_SOURCE_FILES]
    source_paths.extend(sorted((output_dir / "lane-executions").glob("*.json")))
    source_paths.extend(sorted((output_dir / "route-executions").glob("*.json")))
    source_paths.extend(sorted((output_dir / "case-portfolios").glob("*.json")))
    file_hashes = {
        path.relative_to(output_dir).as_posix(): _sha256_bytes(path.read_bytes())
        for path in source_paths
    }
    _write_new(
        output_dir / "artifact-index.json",
        _json_text(
            {
                "schema_version": 1,
                "mode": "openalex_adaptive_role_gap_v8_artifact_index",
                "production_connected": False,
                "report_workflow_connected": False,
                "planner_trigger_connected": False,
                "recovery_connected": False,
                "model_call_count": 0,
                "source_file_sha256": file_hashes,
            }
        ),
    )


def execute_live_study(
    *,
    output_dir: Path,
    soft_stop_usd: float,
    acknowledge_anonymous_daily_budget: bool,
    adapter_factory: AdapterFactory | None = None,
    monotonic_clock: Clock | None = None,
) -> RoleGapExecutionArtifact:
    """Run AC01-AC08 under the frozen adaptive write-once boundary."""

    if not 0.0 < soft_stop_usd <= MAXIMUM_SOFT_STOP_USD:
        raise OpenAlexRoleGapLiveError(
            "adaptive role-gap v8 soft stop must be greater than zero "
            "and at most USD 0.02"
        )
    if not acknowledge_anonymous_daily_budget:
        raise OpenAlexRoleGapLiveError(
            "adaptive role-gap v8 execution requires daily-budget acknowledgement"
        )
    if (os.getenv("OPENALEX_API_KEY") or "").strip():
        raise OpenAlexRoleGapLiveError(
            "anonymous adaptive role-gap v8 study refuses a configured "
            "OPENALEX_API_KEY"
        )
    if output_dir.exists():
        raise FileExistsError(
            f"adaptive role-gap v8 output already exists: {output_dir}"
        )

    fixture_sha256, challenge, cases = load_frozen_cases("development")
    implementation_sha256 = verify_frozen_implementation()
    runner_sha256 = _file_sha256(_RUNNER_PATH)
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = _manifest_artifact(
        cases,
        fixture_sha256=fixture_sha256,
        implementation_sha256=implementation_sha256,
        runner_sha256=runner_sha256,
        soft_stop_usd=soft_stop_usd,
        provider_contract=challenge.provider_contract,
        routing_contract=challenge.routing_contract,
        portfolio_contract=challenge.portfolio_contract,
        qualification_contract=challenge.qualification_contract,
    )
    # The manifest is durable authority for every possible request. Constructing
    # the adapter earlier would make a crash leave an unaudited spender.
    _write_new(output_dir / "manifest.json", _json_text(manifest))
    adapter: RoleGapAdapter
    if adapter_factory is not None:
        adapter = adapter_factory()
    else:
        adapter = AnonymousOpenAlexEvidenceSearchAdapter(
            transport=_OneRequestTransport()
        )

    executions: list[RoleGapLaneExecution] = []
    routes: list[RoleGapRouteExecution] = []
    portfolios: list[RoleGapCasePortfolio] = []
    clock = monotonic_clock or time.perf_counter
    known_cost = 0.0
    stopped_reason: StopReason = "completed"
    for case in cases:
        if known_cost + 1e-12 >= soft_stop_usd:
            stopped_reason = "soft_stop"
            break

        anchor, request_stop = _execute_request(
            adapter,
            case,
            "anchor_search",
            None,
            clock,
        )
        # A spent anchor reaches storage before routing can inspect it.
        _write_lane_journal(output_dir, anchor)
        executions.append(anchor)
        if anchor.search_cost_usd is None:
            stopped_reason = request_stop or "cost_uninspectable"
            break
        known_cost += anchor.search_cost_usd
        if request_stop is not None:
            stopped_reason = request_stop
            break

        route = _route_execution(case, anchor)
        # A selected closure is not authority until the complete checked route
        # is durable. This separates a real abstention from an unchecked case.
        _write_route_journal(output_dir, route)
        routes.append(route)
        case_executions = [anchor]
        selected = route.decision.selected_closure
        if selected is not None:
            if known_cost + 1e-12 >= soft_stop_usd:
                stopped_reason = "soft_stop"
                break
            closure, request_stop = _execute_request(
                adapter,
                case,
                "role_closure",
                selected,
                clock,
            )
            _write_lane_journal(output_dir, closure)
            executions.append(closure)
            if closure.search_cost_usd is None:
                stopped_reason = request_stop or "cost_uninspectable"
                break
            known_cost += closure.search_cost_usd
            if request_stop is not None:
                stopped_reason = request_stop
                break
            case_executions.append(closure)

        portfolio = build_case_portfolio(
            case,
            route,
            tuple(case_executions),
        )
        # The next case cannot spend until its predecessor has a complete
        # adaptive portfolio at rest.
        _write_case_portfolio(output_dir, portfolio)
        portfolios.append(portfolio)

    cost_state, reported_cost = _provider_cost(executions)
    successful_request_count = sum(
        item.state == "completed" for item in executions
    )
    provider_candidate_count = sum(
        len(item.response.candidates)
        for item in executions
        if item.response is not None
    )
    provider_rejection_count = sum(
        len(item.response.provider_rejections)
        for item in executions
        if item.response is not None
    )
    completed = len(portfolios) == len(_CASE_ORDER)
    if completed:
        stopped_reason = "completed"
    provider_summary = RoleGapProviderSummary(
        attempted_request_count=len(executions),
        successful_request_count=successful_request_count,
        completed_case_count=len(portfolios),
        cost_state=cost_state,
        reported_cost_usd=reported_cost,
        total_latency_ms=sum(item.latency_ms for item in executions),
        stopped_reason=stopped_reason,
    )
    artifact = RoleGapExecutionArtifact(
        fixture_sha256=fixture_sha256,
        implementation_sha256=implementation_sha256,
        runner_sha256=runner_sha256,
        soft_stop_usd=soft_stop_usd,
        request_count=len(executions),
        successful_request_count=successful_request_count,
        route_decision_count=len(routes),
        closure_request_count=sum(
            item.lane_id == "role_closure" for item in executions
        ),
        completed_portfolio_count=len(portfolios),
        provider_row_count=provider_candidate_count + provider_rejection_count,
        provider_candidate_count=provider_candidate_count,
        provider_rejection_count=provider_rejection_count,
        unique_candidate_count=sum(
            len(item.unique_candidates) for item in portfolios
        ),
        overall_state="completed" if completed else "partial",
        review_packet_eligibility=(
            "eligible_for_source_lock" if completed else "incomplete"
        ),
        provider_summary=provider_summary,
        lane_executions=tuple(executions),
        route_executions=tuple(routes),
        portfolios=tuple(portfolios),
    )
    _write_final_artifacts(output_dir, manifest, artifact)
    return artifact


def _stdout_json(value: object) -> str:
    """Render reversible CLI JSON independently of the caller's locale."""

    # Authoritative artifacts preserve original UTF-8 provider text. Stdout is
    # only a projection and can still be strict GBK on Windows.
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Frozen OpenAlex adaptive role-gap v8 live harness."
    )
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--soft-stop-usd", type=float)
    parser.add_argument(
        "--acknowledge-anonymous-daily-budget",
        action="store_true",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.execute_live:
        print(_stdout_json(protocol_dry_run()))
        return 0
    if args.output_dir is None or args.soft_stop_usd is None:
        raise SystemExit("--execute-live requires --output-dir and --soft-stop-usd")
    artifact = execute_live_study(
        output_dir=args.output_dir,
        soft_stop_usd=args.soft_stop_usd,
        acknowledge_anonymous_daily_budget=(
            args.acknowledge_anonymous_daily_budget
        ),
    )
    print(_stdout_json(artifact.model_dump(mode="json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
