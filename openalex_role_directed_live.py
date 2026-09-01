"""Write-once live runner for the frozen AA01-AA08 v7 retrieval study.

The production pipeline never imports this module.  It exists to determine
whether two code-owned OpenAlex searches produce a reviewable evidence
portfolio before any semantic judge or production Planner is considered.  The
CLI defaults to a zero-network protocol check; provider work requires an
explicit live flag, budget acknowledgement, fresh output path, and a separate
owner authorization naming the merged revision.
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
from academic_agent.evidence_gap import (
    ValidatedGapCall,
    ValidatedGapPlan,
    source_collection_sha256,
)
from academic_agent.source_pipeline import SourceCollection
from academic_agent.tools.anonymous_openalex_search import (
    AnonymousOpenAlexEvidenceSearchAdapter,
)
from academic_agent.tools.evidence_search import (
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
)
from openalex_role_directed_unseen import (
    EXPECTED_FIXTURE_SHA256,
    PreparedRoleDirectedCase,
    RetrievalLaneId,
    RoleDirectedCaseSpec,
    RoleDirectedPortfolioContract,
    RoleDirectedProviderContract,
    RoleDirectedQualificationContract,
    dry_run,
    load_frozen_cases,
)


_ROOT = Path(__file__).resolve().parent
_RUNNER_PATH = Path(__file__).resolve()
_IMPLEMENTATION_PATHS = {
    "anonymous_openalex_search.py": (_ROOT / "src/academic_agent/tools/anonymous_openalex_search.py"),
    "domain_evidence_search.py": (_ROOT / "src/academic_agent/tools/domain_evidence_search.py"),
    "evidence.py": _ROOT / "src/academic_agent/evidence.py",
    "evidence_gap.py": _ROOT / "src/academic_agent/evidence_gap.py",
    "evidence_search.py": _ROOT / "src/academic_agent/tools/evidence_search.py",
    "openalex_role_directed_unseen.py": (_ROOT / "openalex_role_directed_unseen.py"),
}
# These hashes bind behavior-bearing dependencies before output reservation or
# adapter construction.  The runner records its own observed hash instead of
# recursively trying to embed an expected hash of its complete bytes.
EXPECTED_IMPLEMENTATION_SHA256 = {
    "anonymous_openalex_search.py": ("bcaa201622fe5241115661cd9d5a6f7616761eddfedb9acf364b3693e7a044c9"),
    "domain_evidence_search.py": ("ae79c38378321f6ce4481e682787ee49f930ec4c34b696d404fcf78d97b2eeab"),
    "evidence.py": ("8e9eda3126dc1b81ec5a97e23ecfce8ba64c59a0d77c9a3fb3aec259f07b38c5"),
    "evidence_gap.py": ("f2b978ce2af6b4e1d759116466d5a79371e6e4a7e414198b728b427cd93eea25"),
    "evidence_search.py": ("2721debe3bb193b8971f8a89db0f4c91342944cb232f1829c02dd8d3780422d0"),
    "openalex_role_directed_unseen.py": ("c69b67add9b0eee0ce3a19cd25213dab339b8e0d75e3828ab9cf161856622b7a"),
}

MAXIMUM_REQUESTS = 16
MAXIMUM_PROVIDER_ROWS = 96
MAXIMUM_SOFT_STOP_USD = 0.02
ANONYMOUS_DAILY_BUDGET_USD = 0.10
_CASE_ORDER = tuple(f"AA{index:02d}" for index in range(1, 9))
_LANE_ORDER: tuple[RetrievalLaneId, RetrievalLaneId] = (
    "technology_scope",
    "technology_evidence",
)
_AGGREGATE_SOURCE_FILES = (
    "manifest.json",
    "execution.json",
    "provider-rows.csv",
    "unique-candidates.csv",
    "review.csv",
)
_PROVIDER_ROW_COLUMNS = (
    "case_id",
    "lane_id",
    "lane_index",
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
_UNIQUE_CANDIDATE_COLUMNS = (
    "case_id",
    "unique_candidate_sha256",
    "owner_occurrence_sha256",
    "lane_memberships",
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
_REVIEW_COLUMNS = (
    "case_id",
    "topic",
    "unique_candidate_sha256",
    "lane_memberships",
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
    "directly_relevant",
    "baseline_novel",
    "supported_role_ids",
    "review_note",
)


RoleDirectedAdapter = Callable[
    [ValidatedGapCall],
    ToolAdapterResponse | dict[str, Any],
]
AdapterFactory = Callable[[], RoleDirectedAdapter]
Clock = Callable[[], float]
StopReason = Literal[
    "completed",
    "soft_stop",
    "cost_uninspectable",
    "request_failed",
    "accounting_invalid",
]
ReviewPacketEligibility = Literal[
    "eligible_for_source_lock",
    "mechanical_gate_failed",
    "incomplete",
]
CostState = Literal["known", "uninspectable", "not_observed"]
DeduplicationBasis = Literal[
    "new_unique",
    "normalized_doi",
    "canonical_openalex_url",
]


class OpenAlexRoleDirectedLiveError(ValueError):
    """Raised when the frozen live boundary cannot be represented safely."""


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


def _plan_sha256(value: ValidatedGapPlan) -> str:
    return _model_sha256(value)


def _candidate_sha256(value: ToolEvidenceCandidate) -> str:
    return _model_sha256(value)


def _normalized_doi(value: str | None) -> str | None:
    normalized = normalize_doi(value)
    return normalized.casefold() if normalized else None


def _canonical_openalex_url(value: str) -> str:
    """Return a stable OpenAlex work identity, rejecting non-record URLs."""

    canonical = canonicalize_url(value)
    parsed = urlsplit(canonical)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").casefold() != "openalex.org"
        or parsed.query
        or re.fullmatch(r"/W[0-9]+", parsed.path, flags=re.IGNORECASE) is None
    ):
        raise OpenAlexRoleDirectedLiveError("role-directed candidate URL is not a canonical OpenAlex work")
    return f"https://openalex.org/{parsed.path.lstrip('/').upper()}"


class RoleDirectedFrozenCaseArtifact(BaseModel):
    """Complete deterministic case expansion persisted before provider work."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: RoleDirectedCaseSpec
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lane_contract_sha256s: tuple[str, str]
    source_collection: SourceCollection
    validated_plan: ValidatedGapPlan

    @model_validator(mode="after")
    def _validate_expanded_identities(self) -> "RoleDirectedFrozenCaseArtifact":
        if source_collection_sha256(self.source_collection) != self.collection_sha256:
            raise ValueError("expanded source collection hash does not match")
        if _plan_sha256(self.validated_plan) != self.plan_sha256:
            raise ValueError("expanded validated plan hash does not match")
        if self.spec.roles.profile().sha256() != self.profile_sha256:
            raise ValueError("expanded role profile hash does not match")
        if tuple(lane.lane_id for lane in self.spec.lanes) != _LANE_ORDER:
            raise ValueError("manifest lane order drifted")
        if len(self.validated_plan.calls) != 2:
            raise ValueError("manifest case must retain two validated calls")
        if any(len(value) != 64 for value in self.lane_contract_sha256s):
            raise ValueError("manifest lane contract identity is malformed")
        return self


class RoleDirectedManifestArtifact(BaseModel):
    """Write-once method, input, budget, and disconnection boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_role_directed_v7_manifest"] = "openalex_role_directed_v7_manifest"
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
    provider_contract: RoleDirectedProviderContract
    portfolio_contract: RoleDirectedPortfolioContract
    qualification_contract: RoleDirectedQualificationContract
    cases: tuple[RoleDirectedFrozenCaseArtifact, ...] = Field(
        min_length=8,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_frozen_contract(self) -> "RoleDirectedManifestArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("manifest fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("manifest implementation identities do not match")
        if tuple(case.spec.case_id for case in self.cases) != _CASE_ORDER:
            raise ValueError("manifest cases must remain ordered AA01 through AA08")
        lane_count = sum(len(case.validated_plan.calls) for case in self.cases)
        if lane_count != MAXIMUM_REQUESTS:
            raise ValueError("manifest must commit all sixteen lane requests")
        return self


class RoleDirectedLaneExecution(BaseModel):
    """One spent-request journal with explicit identity and accounting state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^AA0[1-8]$")
    lane_id: RetrievalLaneId
    lane_index: int = Field(ge=0, le=1)
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lane_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_id: str = Field(
        pattern=(
            r"^openalex-role-directed-v7-aa0[1-8]-"
            r"(?:technology-scope|technology-evidence)$"
        )
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
    def _validate_state_and_response(self) -> "RoleDirectedLaneExecution":
        if self.lane_id != _LANE_ORDER[self.lane_index]:
            raise ValueError("lane identity and index drifted")
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
            usage = self.response.provider_usage
            if (
                self.response.tool != "academic_search"
                or usage is None
                or usage.provider != "openalex"
                or usage.cost_basis != "reported_usd"
                or usage.result_count > 6
            ):
                raise ValueError("completed lane lacks the frozen OpenAlex accounting")
        else:
            if self.failure_type is None or self.failure_detail is None:
                raise ValueError("failed lane requires explicit failure metadata")
            if self.response is not None and (self.response.search_cost_usd != self.search_cost_usd):
                raise ValueError("failed lane cost drifted from provider response")
        return self


class RoleDirectedCandidateOccurrence(BaseModel):
    """One provider candidate and its deterministic portfolio lineage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^AA0[1-8]$")
    lane_id: RetrievalLaneId
    lane_index: int = Field(ge=0, le=1)
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
    def _validate_occurrence_identity(self) -> "RoleDirectedCandidateOccurrence":
        if self.lane_id != _LANE_ORDER[self.lane_index]:
            raise ValueError("occurrence lane identity and index drifted")
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


class RoleDirectedUniqueCandidate(BaseModel):
    """One first-seen source retaining every lane and provider occurrence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^AA0[1-8]$")
    unique_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_occurrence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    primary_candidate: ToolEvidenceCandidate
    lane_memberships: tuple[RetrievalLaneId, ...] = Field(min_length=1, max_length=2)
    occurrence_sha256s: tuple[str, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def _validate_unique_identity(self) -> "RoleDirectedUniqueCandidate":
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
        expected_lanes = tuple(lane for lane in _LANE_ORDER if lane in self.lane_memberships)
        if self.lane_memberships != expected_lanes:
            raise ValueError("unique candidate lane memberships are not canonical")
        if len(set(self.occurrence_sha256s)) != len(self.occurrence_sha256s):
            raise ValueError("unique candidate occurrences must be unique")
        return self


class RoleDirectedCasePortfolio(BaseModel):
    """Two completed lane journals joined without semantic source filtering."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^AA0[1-8]$")
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lane_execution_sha256s: tuple[str, str]
    occurrences: tuple[RoleDirectedCandidateOccurrence, ...] = Field(max_length=12)
    unique_candidates: tuple[RoleDirectedUniqueCandidate, ...] = Field(max_length=12)

    @model_validator(mode="after")
    def _validate_portfolio_lineage(self) -> "RoleDirectedCasePortfolio":
        if any(item.case_id != self.case_id for item in self.occurrences):
            raise ValueError("portfolio occurrence belongs to another case")
        occurrence_ids = tuple(item.occurrence_sha256 for item in self.occurrences)
        if len(set(occurrence_ids)) != len(occurrence_ids):
            raise ValueError("portfolio occurrence identities must be unique")
        unique_ids = {item.unique_candidate_sha256 for item in self.unique_candidates}
        if len(unique_ids) != len(self.unique_candidates):
            raise ValueError("portfolio unique candidate identities must be unique")
        if any(item.unique_candidate_sha256 not in unique_ids for item in self.occurrences):
            raise ValueError("portfolio occurrence lost its unique-source owner")
        by_unique = {
            unique_id: tuple(
                occurrence.occurrence_sha256
                for occurrence in self.occurrences
                if occurrence.unique_candidate_sha256 == unique_id
            )
            for unique_id in unique_ids
        }
        for candidate in self.unique_candidates:
            if by_unique[candidate.unique_candidate_sha256] != (candidate.occurrence_sha256s):
                raise ValueError("unique candidate occurrence lineage drifted")
            lanes = tuple(
                lane
                for lane in _LANE_ORDER
                if any(
                    occurrence.lane_id == lane
                    and occurrence.unique_candidate_sha256 == candidate.unique_candidate_sha256
                    for occurrence in self.occurrences
                )
            )
            if lanes != candidate.lane_memberships:
                raise ValueError("unique candidate lane lineage drifted")
        return self


class RoleDirectedProviderSummary(BaseModel):
    """Provider accounting where missing observations cannot become zero cost."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openalex"] = "openalex"
    access_mode: Literal["anonymous_no_key"] = "anonymous_no_key"
    authorized_case_count: Literal[8] = 8
    authorized_lane_count: Literal[16] = MAXIMUM_REQUESTS
    attempted_lane_count: int = Field(ge=0, le=16)
    successful_lane_count: int = Field(ge=0, le=16)
    request_count: int = Field(ge=0, le=16)
    cost_state: CostState
    reported_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    total_latency_ms: float = Field(ge=0.0, allow_inf_nan=False)
    stopped_reason: StopReason

    @model_validator(mode="after")
    def _validate_accounting(self) -> "RoleDirectedProviderSummary":
        if self.successful_lane_count > self.attempted_lane_count:
            raise ValueError("successful lanes cannot exceed attempted lanes")
        if self.request_count != self.attempted_lane_count:
            raise ValueError("every attempted lane must own exactly one request")
        if self.cost_state == "known" and self.reported_cost_usd is None:
            raise ValueError("known provider cost requires a numeric total")
        if self.cost_state != "known" and self.reported_cost_usd is not None:
            raise ValueError("unknown provider cost must keep USD null")
        completed = self.successful_lane_count == MAXIMUM_REQUESTS
        if (self.stopped_reason == "completed") != completed:
            raise ValueError("provider completion does not match successful lanes")
        return self


class RoleDirectedExecutionArtifact(BaseModel):
    """Final execution state; source value remains a later human judgment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_role_directed_v7_execution"] = "openalex_role_directed_v7_execution"
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
    attempted_lane_count: int = Field(ge=0, le=16)
    successful_lane_count: int = Field(ge=0, le=16)
    completed_portfolio_count: int = Field(ge=0, le=8)
    provider_row_count: int = Field(ge=0, le=96)
    provider_candidate_count: int = Field(ge=0, le=96)
    provider_rejection_count: int = Field(ge=0, le=96)
    unique_candidate_count: int = Field(ge=0, le=96)
    serialized_boundary_complete: Literal[True] = True
    overall_state: Literal["completed", "partial"]
    review_packet_eligibility: ReviewPacketEligibility
    source_lock_state: Literal["not_created"] = "not_created"
    human_review_state: Literal["not_prepared"] = "not_prepared"
    source_value_state: Literal["not_evaluated"] = "not_evaluated"
    provider_summary: RoleDirectedProviderSummary
    lane_executions: tuple[RoleDirectedLaneExecution, ...] = Field(max_length=16)
    portfolios: tuple[RoleDirectedCasePortfolio, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def _validate_totals_and_states(self) -> "RoleDirectedExecutionArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("execution fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("execution implementation identities do not match")
        expected_lanes = tuple((case_id, lane_id) for case_id in _CASE_ORDER for lane_id in _LANE_ORDER)
        observed_lanes = tuple((item.case_id, item.lane_id) for item in self.lane_executions)
        if observed_lanes != expected_lanes[: len(observed_lanes)]:
            raise ValueError("lane executions must preserve the frozen prefix")
        if len(self.lane_executions) != self.attempted_lane_count:
            raise ValueError("attempted lanes must equal persisted journals")
        if self.request_count != sum(item.outbound_attempt_count for item in self.lane_executions):
            raise ValueError("request count must equal lane journal attempts")
        successful = sum(item.state == "completed" for item in self.lane_executions)
        if successful != self.successful_lane_count:
            raise ValueError("successful-lane count drifted")
        expected_portfolios = _CASE_ORDER[: len(self.portfolios)]
        if tuple(item.case_id for item in self.portfolios) != expected_portfolios:
            raise ValueError("case portfolios must preserve the frozen prefix")
        if len(self.portfolios) != self.completed_portfolio_count:
            raise ValueError("completed-portfolio count drifted")
        for portfolio in self.portfolios:
            lane_items = tuple(item for item in self.lane_executions if item.case_id == portfolio.case_id)
            if len(lane_items) != 2 or any(item.state != "completed" for item in lane_items):
                raise ValueError("portfolio requires two completed lane journals")
            if tuple(_model_sha256(item) for item in lane_items) != (portfolio.lane_execution_sha256s):
                raise ValueError("portfolio lane-journal identities drifted")
        responses = tuple(item.response for item in self.lane_executions if item.response is not None)
        provider_candidates = sum(len(item.candidates) for item in responses)
        provider_rejections = sum(len(item.provider_rejections) for item in responses)
        if provider_candidates != self.provider_candidate_count:
            raise ValueError("provider-candidate count drifted")
        if provider_rejections != self.provider_rejection_count:
            raise ValueError("provider-rejection count drifted")
        if provider_candidates + provider_rejections != self.provider_row_count:
            raise ValueError("provider-row count drifted")
        unique_candidates = sum(len(item.unique_candidates) for item in self.portfolios)
        if unique_candidates != self.unique_candidate_count:
            raise ValueError("unique-candidate count drifted")
        portfolio_occurrences = sum(len(item.occurrences) for item in self.portfolios)
        portfolio_case_ids = {item.case_id for item in self.portfolios}
        completed_candidates = sum(
            len(item.response.candidates)
            for item in self.lane_executions
            if item.state == "completed" and item.response is not None and item.case_id in portfolio_case_ids
        )
        if portfolio_occurrences != completed_candidates:
            raise ValueError("completed provider candidate lost portfolio lineage")
        if self.provider_summary.request_count != self.request_count:
            raise ValueError("provider request count drifted from execution")
        if self.provider_summary.attempted_lane_count != self.attempted_lane_count:
            raise ValueError("provider attempted-lane count drifted")
        if self.provider_summary.successful_lane_count != self.successful_lane_count:
            raise ValueError("provider successful-lane count drifted")
        expected_latency = sum(item.latency_ms for item in self.lane_executions)
        if not math.isclose(
            self.provider_summary.total_latency_ms,
            expected_latency,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError("provider latency total drifted from lane journals")
        completed = self.successful_lane_count == MAXIMUM_REQUESTS and self.completed_portfolio_count == len(
            _CASE_ORDER
        )
        if (self.overall_state == "completed") != completed:
            raise ValueError("overall state does not match durable completion")
        expected_eligibility: ReviewPacketEligibility = "eligible_for_source_lock" if completed else "incomplete"
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
        raise OpenAlexRoleDirectedLiveError(f"could not read frozen implementation file {path.name}: {exc}") from exc


def verify_frozen_implementation() -> dict[str, str]:
    """Reject dependency drift before output or adapter construction."""

    if set(_IMPLEMENTATION_PATHS) != set(EXPECTED_IMPLEMENTATION_SHA256):
        raise OpenAlexRoleDirectedLiveError("role-directed implementation lock names are inconsistent")
    observed = {name: _file_sha256(path) for name, path in _IMPLEMENTATION_PATHS.items()}
    if observed != EXPECTED_IMPLEMENTATION_SHA256:
        changed = sorted(
            name for name, digest in observed.items() if EXPECTED_IMPLEMENTATION_SHA256.get(name) != digest
        )
        raise OpenAlexRoleDirectedLiveError("role-directed implementation identity drifted: " + ", ".join(changed))
    return observed


def protocol_dry_run() -> dict[str, Any]:
    """Expose frozen AA and dependency identities while opening zero sockets."""

    result = dry_run("development")
    result["implementation_sha256"] = verify_frozen_implementation()
    result["runner_sha256"] = _file_sha256(_RUNNER_PATH)
    result["live_runner_maximum_requests"] = MAXIMUM_REQUESTS
    result["live_runner_maximum_soft_stop_usd"] = MAXIMUM_SOFT_STOP_USD
    return result


def _manifest_artifact(
    cases: tuple[PreparedRoleDirectedCase, ...],
    *,
    fixture_sha256: str,
    implementation_sha256: dict[str, str],
    runner_sha256: str,
    soft_stop_usd: float,
    provider_contract: RoleDirectedProviderContract,
    portfolio_contract: RoleDirectedPortfolioContract,
    qualification_contract: RoleDirectedQualificationContract,
) -> RoleDirectedManifestArtifact:
    return RoleDirectedManifestArtifact(
        fixture_sha256=fixture_sha256,
        implementation_sha256=implementation_sha256,
        runner_sha256=runner_sha256,
        soft_stop_usd=soft_stop_usd,
        provider_contract=provider_contract,
        portfolio_contract=portfolio_contract,
        qualification_contract=qualification_contract,
        cases=tuple(
            RoleDirectedFrozenCaseArtifact(
                spec=case.spec,
                collection_sha256=case.collection_sha256,
                plan_sha256=case.plan_sha256,
                profile_sha256=case.profile_sha256,
                case_contract_sha256=case.case_contract_sha256,
                lane_contract_sha256s=case.lane_contract_sha256s,
                source_collection=case.collection,
                validated_plan=case.plan,
            )
            for case in cases
        ),
    )


def _write_new(path: Path, value: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(value)
    except OSError as exc:
        raise OpenAlexRoleDirectedLiveError(f"could not create write-once artifact {path}: {exc}") from exc


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
    execution: RoleDirectedLaneExecution,
) -> None:
    journal_dir = output_dir / "lane-executions"
    journal_dir.mkdir(exist_ok=True)
    filename = f"{execution.case_id}--{execution.lane_id}.json"
    _write_new(journal_dir / filename, _json_text(execution))


def _write_case_portfolio(
    output_dir: Path,
    portfolio: RoleDirectedCasePortfolio,
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


def _trace_id(case_id: str, lane_id: RetrievalLaneId) -> str:
    return f"openalex-role-directed-v7-{case_id.casefold()}-{lane_id.replace('_', '-')}"


def _failure_execution(
    case: PreparedRoleDirectedCase,
    lane_id: RetrievalLaneId,
    lane_index: int,
    call: ValidatedGapCall,
    *,
    failure_type: str,
    failure_detail: str,
    failure_retryable: bool | None,
    latency_ms: float,
    response: ToolAdapterResponse | None = None,
    search_cost_usd: float | None = None,
) -> RoleDirectedLaneExecution:
    return RoleDirectedLaneExecution(
        case_id=case.spec.case_id,
        lane_id=lane_id,
        lane_index=lane_index,
        collection_sha256=case.collection_sha256,
        plan_sha256=case.plan_sha256,
        profile_sha256=case.profile_sha256,
        case_contract_sha256=case.case_contract_sha256,
        lane_contract_sha256=case.lane_contract_sha256s[lane_index],
        idempotency_key=call.idempotency_key,
        trace_id=_trace_id(case.spec.case_id, lane_id),
        state="failed",
        response=response,
        failure_type=failure_type,
        failure_detail=failure_detail[:500],
        failure_retryable=failure_retryable,
        search_cost_usd=search_cost_usd,
        latency_ms=latency_ms,
    )


def _completed_execution(
    case: PreparedRoleDirectedCase,
    lane_id: RetrievalLaneId,
    lane_index: int,
    call: ValidatedGapCall,
    response: ToolAdapterResponse,
    latency_ms: float,
) -> RoleDirectedLaneExecution:
    return RoleDirectedLaneExecution(
        case_id=case.spec.case_id,
        lane_id=lane_id,
        lane_index=lane_index,
        collection_sha256=case.collection_sha256,
        plan_sha256=case.plan_sha256,
        profile_sha256=case.profile_sha256,
        case_contract_sha256=case.case_contract_sha256,
        lane_contract_sha256=case.lane_contract_sha256s[lane_index],
        idempotency_key=call.idempotency_key,
        trace_id=_trace_id(case.spec.case_id, lane_id),
        state="completed",
        response=response,
        search_cost_usd=response.search_cost_usd,
        latency_ms=latency_ms,
    )


def _occurrence_sha256(
    case_id: str,
    lane_id: RetrievalLaneId,
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
    """Return one unambiguous owner without merging conflicting non-empty DOIs."""

    compatible = [
        owner
        for owner in owners
        if owner["normalized_doi"] is None or normalized_doi is None or owner["normalized_doi"] == normalized_doi
    ]
    return compatible[0] if len(compatible) == 1 else None


def build_case_portfolio(
    case: PreparedRoleDirectedCase,
    lane_executions: tuple[RoleDirectedLaneExecution, RoleDirectedLaneExecution],
) -> RoleDirectedCasePortfolio:
    """Join two lanes in deterministic order while retaining every occurrence."""

    if tuple(item.lane_id for item in lane_executions) != _LANE_ORDER or any(
        item.state != "completed" or item.response is None for item in lane_executions
    ):
        raise OpenAlexRoleDirectedLiveError("case portfolio requires both ordered completed lane journals")

    owner_records: list[dict[str, Any]] = []
    seen_dois: dict[str, dict[str, Any]] = {}
    seen_urls: dict[str, list[dict[str, Any]]] = {}
    occurrences: list[RoleDirectedCandidateOccurrence] = []

    for lane_execution in lane_executions:
        response = lane_execution.response
        if response is None:  # pragma: no cover - guarded above and by Pydantic
            raise OpenAlexRoleDirectedLiveError("completed lane lost its response")
        for candidate in response.candidates:
            provider_index = candidate.provider_result_index
            if provider_index is None:
                raise OpenAlexRoleDirectedLiveError("provider-accounted candidate lost its result index")
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
                }
                owner_records.append(owner)
                if normalized_doi:
                    seen_dois[normalized_doi] = owner
                seen_urls.setdefault(canonical_url, []).append(owner)
                basis = "new_unique"
                deduplication_value = normalized_doi or canonical_url
            # Every occurrence can introduce a useful secondary identity.  For
            # example, a no-DOI first row may be followed by the same OpenAlex
            # record with a DOI.  Registering both identities here lets later
            # occurrences join the same owner without changing the first-seen
            # source or erasing the path by which it was discovered.
            if normalized_doi and normalized_doi not in seen_dois:
                seen_dois[normalized_doi] = owner
            url_owners = seen_urls.setdefault(canonical_url, [])
            if not any(existing is owner for existing in url_owners):
                url_owners.append(owner)
            if lane_execution.lane_id not in owner["lane_memberships"]:
                owner["lane_memberships"].append(lane_execution.lane_id)
            owner["occurrence_sha256s"].append(occurrence_digest)
            occurrences.append(
                RoleDirectedCandidateOccurrence(
                    case_id=case.spec.case_id,
                    lane_id=lane_execution.lane_id,
                    lane_index=lane_execution.lane_index,
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
        RoleDirectedUniqueCandidate(
            case_id=case.spec.case_id,
            unique_candidate_sha256=owner["unique_candidate_sha256"],
            owner_occurrence_sha256=owner["owner_occurrence_sha256"],
            primary_candidate_sha256=owner["primary_candidate_sha256"],
            primary_candidate=owner["primary_candidate"],
            lane_memberships=tuple(owner["lane_memberships"]),
            occurrence_sha256s=tuple(owner["occurrence_sha256s"]),
        )
        for owner in owner_records
    )
    return RoleDirectedCasePortfolio(
        case_id=case.spec.case_id,
        collection_sha256=case.collection_sha256,
        plan_sha256=case.plan_sha256,
        profile_sha256=case.profile_sha256,
        case_contract_sha256=case.case_contract_sha256,
        lane_execution_sha256s=tuple(_model_sha256(item) for item in lane_executions),
        occurrences=tuple(occurrences),
        unique_candidates=unique_candidates,
    )


def _provider_cost(
    executions: list[RoleDirectedLaneExecution],
) -> tuple[CostState, float | None]:
    if not executions:
        return "not_observed", None
    values = [item.search_cost_usd for item in executions]
    if any(value is None for value in values):
        return "uninspectable", None
    return "known", sum(value for value in values if value is not None)


def _elapsed_ms(clock: Clock, started_at: float) -> float:
    """Keep a spent request journal even if an injected clock goes backwards."""

    elapsed_ms = (clock() - started_at) * 1000.0
    if not math.isfinite(elapsed_ms):
        raise OpenAlexRoleDirectedLiveError("request clock produced non-finite latency")
    return max(0.0, elapsed_ms)


def _json_compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _occurrence_by_provider_row(
    portfolios: tuple[RoleDirectedCasePortfolio, ...],
) -> dict[tuple[str, RetrievalLaneId, int], RoleDirectedCandidateOccurrence]:
    return {
        (item.case_id, item.lane_id, item.provider_result_index): item
        for portfolio in portfolios
        for item in portfolio.occurrences
    }


def _provider_rows(
    executions: tuple[RoleDirectedLaneExecution, ...],
    portfolios: tuple[RoleDirectedCasePortfolio, ...],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    occurrence_map = _occurrence_by_provider_row(portfolios)
    for execution in executions:
        response = execution.response
        if response is None:
            continue
        usage = response.provider_usage
        if usage is None:
            # A generically parseable ToolAdapterResponse can still fail the
            # frozen OpenAlex accounting contract.  Its safe shape remains in
            # the failed lane journal, but rows without a provider request
            # identity cannot be promoted into the auditable provider table.
            if execution.state == "failed":
                continue
            raise OpenAlexRoleDirectedLiveError("persisted OpenAlex response lost provider accounting")
        for candidate in response.candidates:
            index = candidate.provider_result_index
            if index is None:
                raise OpenAlexRoleDirectedLiveError("provider candidate lost its result index")
            occurrence = occurrence_map.get((execution.case_id, execution.lane_id, index))
            rows.append(
                {
                    "case_id": execution.case_id,
                    "lane_id": execution.lane_id,
                    "lane_index": str(execution.lane_index),
                    "provider": usage.provider,
                    "tool": response.tool,
                    "provider_request_id": response.provider_request_id or "",
                    "provider_request_id_source": usage.request_id_source,
                    "provider_cost_basis": usage.cost_basis,
                    "provider_result_index": str(index),
                    "adapter_disposition": "candidate",
                    "candidate_sha256": _candidate_sha256(candidate),
                    "occurrence_sha256": (occurrence.occurrence_sha256 if occurrence else ""),
                    "unique_candidate_sha256": (occurrence.unique_candidate_sha256 if occurrence else ""),
                    "deduplication_basis": (occurrence.deduplication_basis if occurrence else "NOT_EVALUATED"),
                    "deduplication_value": (occurrence.deduplication_value if occurrence else ""),
                    "owner_occurrence_sha256": (occurrence.owner_occurrence_sha256 if occurrence else ""),
                    "title": candidate.title,
                    "url": candidate.url,
                    "normalized_doi": _normalized_doi(candidate.doi) or "",
                    "publisher": candidate.publisher,
                    "published_date": (candidate.published_date.isoformat() if candidate.published_date else ""),
                    "evidence_summary": candidate.evidence_summary,
                    "summary_source": candidate.summary_source,
                    "citation_count": (str(candidate.citation_count) if candidate.citation_count is not None else ""),
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
                    "provider": usage.provider,
                    "tool": response.tool,
                    "provider_request_id": response.provider_request_id or "",
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


def _unique_and_review_rows(
    manifest: RoleDirectedManifestArtifact,
    portfolios: tuple[RoleDirectedCasePortfolio, ...],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    case_inputs = {item.spec.case_id: item for item in manifest.cases}
    unique_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    for portfolio in portfolios:
        occurrences = {item.occurrence_sha256: item for item in portfolio.occurrences}
        frozen = case_inputs[portfolio.case_id]
        for item in portfolio.unique_candidates:
            candidate = item.primary_candidate
            provider_ranks = [
                {
                    "lane_id": occurrences[occurrence_id].lane_id,
                    "provider_result_index": (occurrences[occurrence_id].provider_result_index),
                }
                for occurrence_id in item.occurrence_sha256s
            ]
            lane_memberships = _json_compact(item.lane_memberships)
            unique_rows.append(
                {
                    "case_id": item.case_id,
                    "unique_candidate_sha256": item.unique_candidate_sha256,
                    "owner_occurrence_sha256": item.owner_occurrence_sha256,
                    "lane_memberships": lane_memberships,
                    "occurrence_sha256s": _json_compact(item.occurrence_sha256s),
                    "provider_ranks": _json_compact(provider_ranks),
                    "candidate_sha256": item.primary_candidate_sha256,
                    "title": candidate.title,
                    "url": candidate.url,
                    "normalized_doi": _normalized_doi(candidate.doi) or "",
                    "publisher": candidate.publisher,
                    "published_date": (candidate.published_date.isoformat() if candidate.published_date else ""),
                    "evidence_summary": candidate.evidence_summary,
                    "summary_source": candidate.summary_source,
                    "citation_count": (str(candidate.citation_count) if candidate.citation_count is not None else ""),
                }
            )
            review_rows.append(
                {
                    "case_id": item.case_id,
                    "topic": frozen.spec.topic,
                    "unique_candidate_sha256": item.unique_candidate_sha256,
                    "lane_memberships": lane_memberships,
                    "occurrence_count": str(len(item.occurrence_sha256s)),
                    "provider_ranks": _json_compact(provider_ranks),
                    "title": candidate.title,
                    "url": candidate.url,
                    "normalized_doi": _normalized_doi(candidate.doi) or "",
                    "publisher": candidate.publisher,
                    "published_date": (candidate.published_date.isoformat() if candidate.published_date else ""),
                    "evidence_summary": candidate.evidence_summary,
                    "summary_source": candidate.summary_source,
                    "citation_count": (str(candidate.citation_count) if candidate.citation_count is not None else ""),
                    "frozen_baseline_sources": _json_compact(
                        [source.model_dump(mode="json") for source in frozen.source_collection.academic_sources]
                    ),
                    "frozen_role_profile": _json_compact(frozen.spec.roles.profile().model_dump(mode="json")),
                    "directly_relevant": "",
                    "baseline_novel": "",
                    "supported_role_ids": "",
                    "review_note": "",
                }
            )
    return unique_rows, review_rows


def _csv_text(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _write_final_artifacts(
    output_dir: Path,
    manifest: RoleDirectedManifestArtifact,
    artifact: RoleDirectedExecutionArtifact,
) -> None:
    provider_rows = _provider_rows(artifact.lane_executions, artifact.portfolios)
    unique_rows, review_rows = _unique_and_review_rows(manifest, artifact.portfolios)
    if len(provider_rows) != artifact.provider_row_count:
        raise OpenAlexRoleDirectedLiveError("provider row disappeared before the aggregate boundary")
    if len(unique_rows) != artifact.unique_candidate_count:
        raise OpenAlexRoleDirectedLiveError("unique candidate disappeared before the aggregate boundary")
    if len(review_rows) != artifact.unique_candidate_count:
        raise OpenAlexRoleDirectedLiveError("candidate disappeared before the blank review boundary")
    _write_new(output_dir / "execution.json", _json_text(artifact))
    _write_new(
        output_dir / "provider-rows.csv",
        _csv_text(_PROVIDER_ROW_COLUMNS, provider_rows),
    )
    _write_new(
        output_dir / "unique-candidates.csv",
        _csv_text(_UNIQUE_CANDIDATE_COLUMNS, unique_rows),
    )
    _write_new(
        output_dir / "review.csv",
        _csv_text(_REVIEW_COLUMNS, review_rows),
    )
    source_paths = [output_dir / name for name in _AGGREGATE_SOURCE_FILES]
    source_paths.extend(sorted((output_dir / "lane-executions").glob("*.json")))
    source_paths.extend(sorted((output_dir / "case-portfolios").glob("*.json")))
    file_hashes = {path.relative_to(output_dir).as_posix(): _sha256_bytes(path.read_bytes()) for path in source_paths}
    _write_new(
        output_dir / "artifact-index.json",
        _json_text(
            {
                "schema_version": 1,
                "mode": "openalex_role_directed_v7_artifact_index",
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
) -> RoleDirectedExecutionArtifact:
    """Run AA01-AA08 under a provider-reported write-once budget boundary."""

    if not 0.0 < soft_stop_usd <= MAXIMUM_SOFT_STOP_USD:
        raise OpenAlexRoleDirectedLiveError("role-directed v7 soft stop must be greater than zero and at most USD 0.02")
    if not acknowledge_anonymous_daily_budget:
        raise OpenAlexRoleDirectedLiveError("role-directed v7 execution requires daily-budget acknowledgement")
    if (os.getenv("OPENALEX_API_KEY") or "").strip():
        raise OpenAlexRoleDirectedLiveError("anonymous role-directed v7 study refuses a configured OPENALEX_API_KEY")
    if output_dir.exists():
        raise FileExistsError(f"role-directed v7 output already exists: {output_dir}")

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
        portfolio_contract=challenge.portfolio_contract,
        qualification_contract=challenge.qualification_contract,
    )
    # This file is durable authority for the exact calls.  Constructing the
    # adapter before it exists would make a crash leave an unaudited spender.
    adapter: RoleDirectedAdapter
    _write_new(output_dir / "manifest.json", _json_text(manifest))
    if adapter_factory is not None:
        adapter = adapter_factory()
    else:
        adapter = AnonymousOpenAlexEvidenceSearchAdapter(transport=_OneRequestTransport())

    executions: list[RoleDirectedLaneExecution] = []
    portfolios: list[RoleDirectedCasePortfolio] = []
    clock = monotonic_clock or time.perf_counter
    known_cost = 0.0
    stopped_reason: StopReason = "completed"
    stop = False
    for case in cases:
        case_executions: list[RoleDirectedLaneExecution] = []
        for lane_index, (lane, call) in enumerate(zip(case.spec.lanes, case.plan.calls, strict=True)):
            if known_cost + 1e-12 >= soft_stop_usd:
                stopped_reason = "soft_stop"
                stop = True
                break
            lane_stop_reason: StopReason | None = None
            started_at = clock()
            try:
                raw_response = adapter(call)
            except ToolAdapterFailure as exc:
                latency_ms = _elapsed_ms(clock, started_at)
                execution = _failure_execution(
                    case,
                    lane.lane_id,
                    lane_index,
                    call,
                    failure_type=exc.failure_type,
                    failure_detail=str(exc),
                    failure_retryable=exc.retryable,
                    latency_ms=latency_ms,
                    search_cost_usd=exc.search_cost_usd,
                )
                lane_stop_reason = "request_failed"
            else:
                latency_ms = _elapsed_ms(clock, started_at)
                try:
                    response = ToolAdapterResponse.model_validate(raw_response)
                except ValidationError as exc:
                    execution = _failure_execution(
                        case,
                        lane.lane_id,
                        lane_index,
                        call,
                        failure_type="adapter_response_invalid",
                        failure_detail=_validation_detail(exc),
                        failure_retryable=False,
                        latency_ms=latency_ms,
                    )
                    lane_stop_reason = "accounting_invalid"
                else:
                    if response.idempotency_key != call.idempotency_key:
                        execution = _failure_execution(
                            case,
                            lane.lane_id,
                            lane_index,
                            call,
                            failure_type="adapter_identity_mismatch",
                            failure_detail=("adapter response idempotency key does not match the authorized lane"),
                            failure_retryable=False,
                            latency_ms=latency_ms,
                            response=response,
                            search_cost_usd=response.search_cost_usd,
                        )
                        lane_stop_reason = "accounting_invalid"
                    else:
                        try:
                            execution = _completed_execution(
                                case,
                                lane.lane_id,
                                lane_index,
                                call,
                                response,
                                latency_ms,
                            )
                        except ValidationError as exc:
                            execution = _failure_execution(
                                case,
                                lane.lane_id,
                                lane_index,
                                call,
                                failure_type="adapter_response_invalid",
                                failure_detail=_validation_detail(exc),
                                failure_retryable=False,
                                latency_ms=latency_ms,
                                response=response,
                                search_cost_usd=response.search_cost_usd,
                            )
                            lane_stop_reason = "accounting_invalid"

            # The spent request reaches durable storage before any later lane
            # can begin.  This also preserves a one-lane partial case without
            # pretending that a two-lane portfolio exists.
            _write_lane_journal(output_dir, execution)
            executions.append(execution)
            case_executions.append(execution)
            if execution.search_cost_usd is None:
                stopped_reason = lane_stop_reason or "cost_uninspectable"
                stop = True
                break
            known_cost += execution.search_cost_usd
            if lane_stop_reason is not None:
                stopped_reason = lane_stop_reason
                stop = True
                break

        if len(case_executions) == 2 and all(item.state == "completed" for item in case_executions):
            portfolio = build_case_portfolio(
                case,
                (case_executions[0], case_executions[1]),
            )
            _write_case_portfolio(output_dir, portfolio)
            portfolios.append(portfolio)
        if stop:
            break

    cost_state, reported_cost = _provider_cost(executions)
    successful_lane_count = sum(item.state == "completed" for item in executions)
    provider_candidate_count = sum(len(item.response.candidates) for item in executions if item.response is not None)
    provider_rejection_count = sum(
        len(item.response.provider_rejections) for item in executions if item.response is not None
    )
    completed = successful_lane_count == MAXIMUM_REQUESTS and len(portfolios) == len(_CASE_ORDER)
    if completed:
        stopped_reason = "completed"
    provider_summary = RoleDirectedProviderSummary(
        attempted_lane_count=len(executions),
        successful_lane_count=successful_lane_count,
        request_count=len(executions),
        cost_state=cost_state,
        reported_cost_usd=reported_cost,
        total_latency_ms=sum(item.latency_ms for item in executions),
        stopped_reason=stopped_reason,
    )
    artifact = RoleDirectedExecutionArtifact(
        fixture_sha256=fixture_sha256,
        implementation_sha256=implementation_sha256,
        runner_sha256=runner_sha256,
        soft_stop_usd=soft_stop_usd,
        request_count=len(executions),
        attempted_lane_count=len(executions),
        successful_lane_count=successful_lane_count,
        completed_portfolio_count=len(portfolios),
        provider_row_count=provider_candidate_count + provider_rejection_count,
        provider_candidate_count=provider_candidate_count,
        provider_rejection_count=provider_rejection_count,
        unique_candidate_count=sum(len(item.unique_candidates) for item in portfolios),
        overall_state="completed" if completed else "partial",
        review_packet_eligibility=("eligible_for_source_lock" if completed else "incomplete"),
        provider_summary=provider_summary,
        lane_executions=tuple(executions),
        portfolios=tuple(portfolios),
    )
    _write_final_artifacts(output_dir, manifest, artifact)
    return artifact


def _stdout_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Frozen OpenAlex role-directed retrieval v7 live harness.")
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--soft-stop-usd", type=float)
    parser.add_argument("--acknowledge-anonymous-daily-budget", action="store_true")
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
        acknowledge_anonymous_daily_budget=(args.acknowledge_anonymous_daily_budget),
    )
    print(_stdout_json(artifact.model_dump(mode="json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
