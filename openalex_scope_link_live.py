"""Production-disconnected live runner for the scope-link v4 challenge.

The default command is a zero-network preflight.  Live execution requires an
explicit flag, a bounded provider-reported soft stop, and acknowledgement of
the anonymous OpenAlex daily budget.  Every frozen input is persisted before
adapter construction, and each one-request case journal is committed before a
later request may start.  The resulting ACCEPT rows remain unregistered review
candidates: this module is never imported by the production report worker.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from academic_agent.evidence_gap import (
    ValidatedGapCall,
    ValidatedGapPlan,
    source_collection_sha256,
)
from academic_agent.openalex_claim_scope import OpenAlexClaimScopeCandidate
from academic_agent.openalex_scope_link import (
    OpenAlexScopeLinkDecision,
    evaluate_openalex_scope_link,
)
from academic_agent.source_pipeline import SourceCollection
from academic_agent.tools.evidence_search import ToolAdapterFailure
from academic_agent.tools.openalex_claim_scope_search import (
    AnonymousOpenAlexClaimScopeAdapter,
    OpenAlexClaimScopeAdapterResponse,
)
from openalex_scope_link_unseen import (
    EXPECTED_FIXTURE_SHA256,
    ScopeLinkCaseSpec,
    ScopeLinkSourceValueGates,
    PreparedScopeLinkCase,
    dry_run,
    load_frozen_cases,
)


_ROOT = Path(__file__).resolve().parent
_RUNNER_PATH = Path(__file__).resolve()
_IMPLEMENTATION_PATHS = {
    "domain_evidence_search.py": (
        _ROOT / "src/academic_agent/tools/domain_evidence_search.py"
    ),
    "evidence.py": _ROOT / "src/academic_agent/evidence.py",
    "evidence_gap.py": _ROOT / "src/academic_agent/evidence_gap.py",
    "evidence_search.py": _ROOT / "src/academic_agent/tools/evidence_search.py",
    "openalex_claim_scope.py": (
        _ROOT / "src/academic_agent/openalex_claim_scope.py"
    ),
    "openalex_claim_scope_search.py": (
        _ROOT / "src/academic_agent/tools/openalex_claim_scope_search.py"
    ),
    "openalex_precision.py": _ROOT / "src/academic_agent/openalex_precision.py",
    "openalex_scope_link.py": _ROOT / "src/academic_agent/openalex_scope_link.py",
    "openalex_scope_link_unseen.py": _ROOT / "openalex_scope_link_unseen.py",
}
# These values are populated from the merge-candidate bytes before any live
# request.  A later code drift must create a new study rather than silently
# changing the method under the original W01-W08 identities.
EXPECTED_IMPLEMENTATION_SHA256 = {
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
    "openalex_claim_scope.py": (
        "739e165838ff5042ec863c3c510311e737216e8d90804c8d3da5095acce22f16"
    ),
    "openalex_claim_scope_search.py": (
        "070d07ac8c4bcaa32bfbc563513b4034162b012aea1f47ce3208ed06cb085642"
    ),
    "openalex_precision.py": (
        "7c6e0f2999aae68a9caa042584c886bc5273037a2eaf2e95d80c553b7a503029"
    ),
    "openalex_scope_link.py": (
        "abfb9a6b6af1691411f4ad3689b0f5052c42dfeddfdc30cb2e9e21c7d0ff2667"
    ),
    "openalex_scope_link_unseen.py": (
        "1e3c0b15c9608cf83b414ee52ac2da7540728149970fa45ab9e6306773ef4749"
    ),
}
MAXIMUM_REQUESTS = 8
MAXIMUM_SOFT_STOP_USD = 0.01
ANONYMOUS_DAILY_BUDGET_USD = 0.10
_CASE_ORDER = tuple(f"W{index:02d}" for index in range(1, 9))
_AGGREGATE_SOURCE_FILES = (
    "manifest.json",
    "execution.json",
    "candidates.csv",
    "review.csv",
)
_CANDIDATE_COLUMNS = (
    "case_id",
    "provider",
    "tool",
    "provider_request_id",
    "provider_request_id_source",
    "provider_cost_basis",
    "provider_result_index",
    "adapter_disposition",
    "scope_link_action",
    "abstention_reasons",
    "missing_required_groups",
    "exact_required_groups",
    "provider_only_required_groups",
    "exact_scope_groups",
    "linked_scope_groups",
    "title_anchor_groups",
    "required_match_provenance",
    "scope_match_provenance",
    "supporting_match_provenance",
    "link_evidence",
    "aboutness_signal_count",
    "candidate_sha256",
    "profile_sha256",
    "title",
    "url",
    "provider_rejection_code",
    "rejection_detail",
    "latency_ms",
    "trace_id",
)
_REVIEW_COLUMNS = (
    "case_id",
    "provider",
    "provider_result_index",
    "candidate_sha256",
    "title",
    "url",
    "relevant",
    "novel",
    "review_note",
)


ScopeLinkAdapter = Callable[
    [ValidatedGapCall],
    OpenAlexClaimScopeAdapterResponse | dict[str, Any],
]
AdapterFactory = Callable[[], ScopeLinkAdapter]
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


class OpenAlexScopeLinkLiveError(ValueError):
    """Raised before provider work when a frozen live boundary fails."""


class ScopeLinkFrozenCaseArtifact(BaseModel):
    """Complete deterministic case input persisted before the first request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: ScopeLinkCaseSpec
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_collection: SourceCollection
    validated_plan: ValidatedGapPlan

    @model_validator(mode="after")
    def _validate_expanded_identities(self) -> "ScopeLinkFrozenCaseArtifact":
        if source_collection_sha256(self.source_collection) != self.collection_sha256:
            raise ValueError("expanded source collection hash does not match")
        plan_sha256 = _sha256_bytes(
            self.validated_plan.model_dump_json(exclude_none=False).encode("utf-8")
        )
        if plan_sha256 != self.plan_sha256:
            raise ValueError("expanded validated plan hash does not match")
        if self.spec.profile.sha256() != self.profile_sha256:
            raise ValueError("expanded scope-link profile hash does not match")
        return self


class ScopeLinkManifestArtifact(BaseModel):
    """Write-once expansion of all frozen inputs and implementation identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_scope_link_v4_manifest"] = (
        "openalex_scope_link_v4_manifest"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    api_key_used: Literal[False] = False
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    runner_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    maximum_requests: Literal[8] = MAXIMUM_REQUESTS
    anonymous_daily_budget_usd: Literal[0.1] = ANONYMOUS_DAILY_BUDGET_USD
    soft_stop_usd: float = Field(gt=0.0, le=MAXIMUM_SOFT_STOP_USD)
    source_value_gates: ScopeLinkSourceValueGates
    cases: tuple[ScopeLinkFrozenCaseArtifact, ...] = Field(
        min_length=8,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_frozen_contract(self) -> "ScopeLinkManifestArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("manifest fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("manifest implementation identities do not match")
        if tuple(case.spec.case_id for case in self.cases) != _CASE_ORDER:
            raise ValueError("manifest cases must remain ordered W01 through W08")
        return self


class ScopeLinkCandidateEvaluation(BaseModel):
    """One provider candidate joined to its label-blind v4 decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_result_index: int = Field(ge=0, le=7)
    candidate: OpenAlexClaimScopeCandidate
    decision: OpenAlexScopeLinkDecision

    @model_validator(mode="after")
    def _validate_candidate_identity(self) -> "ScopeLinkCandidateEvaluation":
        if self.candidate.evidence.provider_result_index != self.provider_result_index:
            raise ValueError("candidate provider index drifted from evaluation")
        if self.candidate.sha256() != self.decision.candidate_sha256:
            raise ValueError("scope-link decision is attached to another candidate")
        return self


class ScopeLinkCaseExecution(BaseModel):
    """One request journal, including explicit failure and accounting states."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^W0[1-8]$")
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_id: str = Field(pattern=r"^openalex-scope-link-v4-w0[1-8]$")
    state: Literal["completed", "failed"]
    outbound_attempt_count: Literal[1] = 1
    response: OpenAlexClaimScopeAdapterResponse | None = None
    evaluations: tuple[ScopeLinkCandidateEvaluation, ...] = Field(
        default=(),
        max_length=8,
    )
    failure_type: str | None = Field(default=None, max_length=100)
    failure_detail: str | None = Field(default=None, max_length=500)
    failure_retryable: bool | None = None
    search_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    latency_ms: float = Field(
        ge=0.0,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def _validate_state_and_evaluations(self) -> "ScopeLinkCaseExecution":
        if self.state == "completed":
            if self.response is None:
                raise ValueError("completed case requires an adapter response")
            if any(
                value is not None
                for value in (
                    self.failure_type,
                    self.failure_detail,
                    self.failure_retryable,
                )
            ):
                raise ValueError("completed case cannot carry failure metadata")
            if self.response.idempotency_key != self.idempotency_key:
                raise ValueError("response idempotency identity drifted")
            if self.response.search_cost_usd != self.search_cost_usd:
                raise ValueError("case cost drifted from provider response")
            expected = tuple(
                (
                    int(candidate.evidence.provider_result_index),
                    candidate,
                )
                for candidate in self.response.candidates
                if candidate.evidence.provider_result_index is not None
            )
            observed = tuple(
                (item.provider_result_index, item.candidate)
                for item in self.evaluations
            )
            if observed != expected:
                raise ValueError("every provider candidate must reach v4 evaluation")
            if any(
                item.decision.profile_sha256 != self.profile_sha256
                for item in self.evaluations
            ):
                raise ValueError("scope-link decision profile identity drifted")
        else:
            if self.failure_type is None or self.failure_detail is None:
                raise ValueError("failed case requires explicit failure metadata")
            if self.evaluations:
                raise ValueError("failed case cannot imply completed evaluations")
            if self.response is not None and (
                self.response.search_cost_usd != self.search_cost_usd
            ):
                raise ValueError("failed case cost drifted from provider response")
        return self


class ScopeLinkProviderSummary(BaseModel):
    """Anonymous provider accounting where no observation is not a pass."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openalex"] = "openalex"
    access_mode: Literal["anonymous_no_key"] = "anonymous_no_key"
    authorized_case_count: Literal[8] = MAXIMUM_REQUESTS
    attempted_case_count: int = Field(ge=0, le=8)
    successful_case_count: int = Field(ge=0, le=8)
    request_count: int = Field(ge=0, le=8)
    cost_state: Literal["known", "uninspectable", "not_observed"]
    reported_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    total_latency_ms: float = Field(
        ge=0.0,
        allow_inf_nan=False,
    )
    stopped_reason: StopReason

    @model_validator(mode="after")
    def _validate_accounting(self) -> "ScopeLinkProviderSummary":
        if self.successful_case_count > self.attempted_case_count:
            raise ValueError("successful cases cannot exceed attempted cases")
        if self.request_count != self.attempted_case_count:
            raise ValueError("every attempted case must own exactly one request")
        if self.cost_state == "known" and self.reported_cost_usd is None:
            raise ValueError("known provider cost requires a numeric total")
        if self.cost_state != "known" and self.reported_cost_usd is not None:
            raise ValueError("uninspectable provider cost must keep USD null")
        completed = self.successful_case_count == MAXIMUM_REQUESTS
        if (self.stopped_reason == "completed") != completed:
            raise ValueError("provider completion does not match successful cases")
        return self


class ScopeLinkExecutionArtifact(BaseModel):
    """Final write-once state; source value still requires eligible humans."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_scope_link_v4_execution"] = (
        "openalex_scope_link_v4_execution"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    api_key_used: Literal[False] = False
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    runner_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    maximum_requests: Literal[8] = MAXIMUM_REQUESTS
    anonymous_daily_budget_usd: Literal[0.1] = ANONYMOUS_DAILY_BUDGET_USD
    soft_stop_usd: float = Field(gt=0.0, le=MAXIMUM_SOFT_STOP_USD)
    request_count: int = Field(ge=0, le=8)
    attempted_case_count: int = Field(ge=0, le=8)
    successful_case_count: int = Field(ge=0, le=8)
    overall_state: Literal["completed", "partial"]
    scope_link_accepted_candidate_count: int = Field(ge=0, le=64)
    scope_link_abstained_candidate_count: int = Field(ge=0, le=64)
    scope_link_accepted_case_count: int = Field(ge=0, le=8)
    review_packet_eligibility: ReviewPacketEligibility
    source_lock_state: Literal["not_created"] = "not_created"
    human_review_state: Literal["not_prepared"] = "not_prepared"
    source_value_state: Literal["not_evaluated"] = "not_evaluated"
    source_value_gates: ScopeLinkSourceValueGates
    provider_summary: ScopeLinkProviderSummary
    cases: tuple[ScopeLinkCaseExecution, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def _validate_totals_and_states(self) -> "ScopeLinkExecutionArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("execution fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("execution implementation identities do not match")
        case_ids = tuple(case.case_id for case in self.cases)
        if case_ids != _CASE_ORDER[: len(case_ids)]:
            raise ValueError("case executions must preserve the frozen prefix")
        if len(self.cases) != self.attempted_case_count:
            raise ValueError("attempted cases must equal persisted journals")
        if self.request_count != sum(
            case.outbound_attempt_count for case in self.cases
        ):
            raise ValueError("request count must equal journal attempt total")
        successful = sum(case.state == "completed" for case in self.cases)
        if successful != self.successful_case_count:
            raise ValueError("successful cases must equal completed journals")
        if self.provider_summary.request_count != self.request_count:
            raise ValueError("provider request count drifted from execution")
        if self.provider_summary.attempted_case_count != self.attempted_case_count:
            raise ValueError("provider attempted-case count drifted")
        if self.provider_summary.successful_case_count != self.successful_case_count:
            raise ValueError("provider successful-case count drifted")
        expected_latency = sum(case.latency_ms for case in self.cases)
        if not math.isclose(
            self.provider_summary.total_latency_ms,
            expected_latency,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError("provider latency total drifted from case journals")

        evaluations = tuple(
            item for case in self.cases for item in case.evaluations
        )
        accepted = sum(item.decision.action == "ACCEPT" for item in evaluations)
        abstained = sum(item.decision.action == "ABSTAIN" for item in evaluations)
        accepted_cases = sum(
            any(item.decision.action == "ACCEPT" for item in case.evaluations)
            for case in self.cases
        )
        if accepted != self.scope_link_accepted_candidate_count:
            raise ValueError("accepted-candidate count drifted")
        if abstained != self.scope_link_abstained_candidate_count:
            raise ValueError("abstained-candidate count drifted")
        if accepted_cases != self.scope_link_accepted_case_count:
            raise ValueError("accepted-case count drifted")

        completed = self.successful_case_count == MAXIMUM_REQUESTS
        if (self.overall_state == "completed") != completed:
            raise ValueError("overall state does not match provider completion")
        expected_eligibility: ReviewPacketEligibility
        if not completed:
            expected_eligibility = "incomplete"
        elif accepted_cases < self.source_value_gates.accepted_case_count_min:
            expected_eligibility = "mechanical_gate_failed"
        else:
            expected_eligibility = "eligible_for_source_lock"
        if self.review_packet_eligibility != expected_eligibility:
            raise ValueError("review-packet eligibility drifted from frozen gates")
        return self


class _NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects because one case authorizes one outbound request."""

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
        request = Request(
            endpoint,
            data=body,
            headers=dict(headers),
            method=method,
        )
        opener = build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            return response.read()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise OpenAlexScopeLinkLiveError(
            f"could not read frozen implementation file {path.name}: {exc}"
        ) from exc


def verify_frozen_implementation() -> dict[str, str]:
    """Reject code drift before output reservation or adapter construction."""

    if set(_IMPLEMENTATION_PATHS) != set(EXPECTED_IMPLEMENTATION_SHA256):
        raise OpenAlexScopeLinkLiveError(
            "scope-link implementation lock names are inconsistent"
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
        raise OpenAlexScopeLinkLiveError(
            "scope-link implementation identity drifted: " + ", ".join(changed)
        )
    return observed


def protocol_dry_run() -> dict[str, Any]:
    """Expose fixture and implementation identities while opening zero sockets."""

    result = dry_run()
    result["implementation_sha256"] = verify_frozen_implementation()
    result["runner_sha256"] = _file_sha256(_RUNNER_PATH)
    return result


def _manifest_artifact(
    cases: tuple[PreparedScopeLinkCase, ...],
    fixture_sha256: str,
    implementation_sha256: dict[str, str],
    runner_sha256: str,
    gates: ScopeLinkSourceValueGates,
    soft_stop_usd: float,
) -> ScopeLinkManifestArtifact:
    return ScopeLinkManifestArtifact(
        fixture_sha256=fixture_sha256,
        implementation_sha256=implementation_sha256,
        runner_sha256=runner_sha256,
        soft_stop_usd=soft_stop_usd,
        source_value_gates=gates,
        cases=tuple(
            ScopeLinkFrozenCaseArtifact(
                spec=case.spec,
                collection_sha256=case.collection_sha256,
                plan_sha256=case.plan_sha256,
                profile_sha256=case.profile_sha256,
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
        raise OpenAlexScopeLinkLiveError(
            f"could not create write-once artifact {path}: {exc}"
        ) from exc


def _json_text(value: BaseModel | dict[str, Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _write_case_journal(
    output_dir: Path,
    execution: ScopeLinkCaseExecution,
) -> None:
    journal_dir = output_dir / "case-executions"
    journal_dir.mkdir(exist_ok=True)
    _write_new(journal_dir / f"{execution.case_id}.json", _json_text(execution))


def _validation_detail(exc: ValidationError) -> str:
    """Describe a failed response shape without copying provider input."""

    details = []
    for error in exc.errors(include_input=False)[:4]:
        location = ".".join(str(part) for part in error["loc"]) or "response"
        details.append(f"{location}:{error['type']}")
    return "; ".join(details)[:500] or "adapter response failed validation"


def _failure_execution(
    case: PreparedScopeLinkCase,
    *,
    failure_type: str,
    failure_detail: str,
    failure_retryable: bool | None,
    latency_ms: float,
    response: OpenAlexClaimScopeAdapterResponse | None = None,
    search_cost_usd: float | None = None,
) -> ScopeLinkCaseExecution:
    return ScopeLinkCaseExecution(
        case_id=case.spec.case_id,
        collection_sha256=case.collection_sha256,
        plan_sha256=case.plan_sha256,
        profile_sha256=case.profile_sha256,
        idempotency_key=case.plan.calls[0].idempotency_key,
        trace_id=f"openalex-scope-link-v4-{case.spec.case_id.casefold()}",
        state="failed",
        response=response,
        failure_type=failure_type,
        failure_detail=failure_detail[:500],
        failure_retryable=failure_retryable,
        search_cost_usd=search_cost_usd,
        latency_ms=latency_ms,
    )


def _completed_execution(
    case: PreparedScopeLinkCase,
    response: OpenAlexClaimScopeAdapterResponse,
    latency_ms: float,
) -> ScopeLinkCaseExecution:
    return ScopeLinkCaseExecution(
        case_id=case.spec.case_id,
        collection_sha256=case.collection_sha256,
        plan_sha256=case.plan_sha256,
        profile_sha256=case.profile_sha256,
        idempotency_key=case.plan.calls[0].idempotency_key,
        trace_id=f"openalex-scope-link-v4-{case.spec.case_id.casefold()}",
        state="completed",
        response=response,
        evaluations=tuple(
            ScopeLinkCandidateEvaluation(
                provider_result_index=int(
                    candidate.evidence.provider_result_index
                ),
                candidate=candidate,
                decision=evaluate_openalex_scope_link(
                    candidate,
                    case.spec.profile,
                ),
            )
            for candidate in response.candidates
            if candidate.evidence.provider_result_index is not None
        ),
        search_cost_usd=response.search_cost_usd,
        latency_ms=latency_ms,
    )


def _provider_cost(
    executions: list[ScopeLinkCaseExecution],
) -> tuple[Literal["known", "uninspectable", "not_observed"], float | None]:
    if not executions:
        return "not_observed", None
    values = [item.search_cost_usd for item in executions]
    if any(value is None for value in values):
        return "uninspectable", None
    return "known", sum(value for value in values if value is not None)


def _elapsed_ms(clock: Clock, started_at: float) -> float:
    """Return monotonic request latency without losing a spent-request journal."""

    elapsed_ms = (clock() - started_at) * 1000.0
    if not math.isfinite(elapsed_ms):
        raise OpenAlexScopeLinkLiveError("request clock produced non-finite latency")
    # perf_counter is monotonic. Clamping a custom test clock's backwards
    # reading is safer than dropping the journal for an already-spent request.
    return max(0.0, elapsed_ms)


def _json_compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _candidate_rows(
    executions: tuple[ScopeLinkCaseExecution, ...],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    reviews: list[dict[str, str]] = []
    for execution in executions:
        response = execution.response
        if response is None:
            continue
        evaluations = {
            item.provider_result_index: item for item in execution.evaluations
        }
        usage = response.provider_usage
        for candidate in response.candidates:
            index = candidate.evidence.provider_result_index
            if index is None:
                raise OpenAlexScopeLinkLiveError(
                    "provider-accounted candidate lost its result index"
                )
            evaluation = evaluations.get(index)
            decision = evaluation.decision if evaluation is not None else None
            rows.append(
                {
                    "case_id": execution.case_id,
                    "provider": "openalex",
                    "tool": response.tool,
                    "provider_request_id": response.provider_request_id,
                    "provider_request_id_source": usage.request_id_source,
                    "provider_cost_basis": usage.cost_basis,
                    "provider_result_index": str(index),
                    "adapter_disposition": "candidate",
                    "scope_link_action": (
                        decision.action if decision is not None else "NOT_EVALUATED"
                    ),
                    "abstention_reasons": _json_compact(
                        decision.abstention_reasons if decision else ()
                    ),
                    "missing_required_groups": _json_compact(
                        decision.missing_required_groups if decision else ()
                    ),
                    "exact_required_groups": _json_compact(
                        decision.exact_required_groups if decision else ()
                    ),
                    "provider_only_required_groups": _json_compact(
                        decision.provider_only_required_groups if decision else ()
                    ),
                    "exact_scope_groups": _json_compact(
                        decision.exact_scope_groups if decision else ()
                    ),
                    "linked_scope_groups": _json_compact(
                        decision.linked_scope_groups if decision else ()
                    ),
                    "title_anchor_groups": _json_compact(
                        decision.title_anchor_groups if decision else ()
                    ),
                    "required_match_provenance": _json_compact(
                        [
                            item.model_dump(mode="json")
                            for item in decision.required_matches
                        ]
                        if decision
                        else []
                    ),
                    "scope_match_provenance": _json_compact(
                        [
                            item.model_dump(mode="json")
                            for item in decision.scope_matches
                        ]
                        if decision
                        else []
                    ),
                    "supporting_match_provenance": _json_compact(
                        [
                            item.model_dump(mode="json")
                            for item in decision.supporting_matches
                        ]
                        if decision
                        else []
                    ),
                    "link_evidence": _json_compact(
                        [
                            item.model_dump(mode="json")
                            for item in decision.link_evidence
                        ]
                        if decision
                        else []
                    ),
                    "aboutness_signal_count": str(len(candidate.aboutness)),
                    "candidate_sha256": (
                        decision.candidate_sha256 if decision else candidate.sha256()
                    ),
                    "profile_sha256": execution.profile_sha256,
                    "title": candidate.evidence.title,
                    "url": candidate.evidence.url,
                    "provider_rejection_code": "",
                    "rejection_detail": "",
                    "latency_ms": str(execution.latency_ms),
                    "trace_id": execution.trace_id,
                }
            )
            if decision is not None and decision.action == "ACCEPT":
                reviews.append(
                    {
                        "case_id": execution.case_id,
                        "provider": "openalex",
                        "provider_result_index": str(index),
                        "candidate_sha256": decision.candidate_sha256,
                        "title": candidate.evidence.title,
                        "url": candidate.evidence.url,
                        "relevant": "",
                        "novel": "",
                        "review_note": "",
                    }
                )
        for rejection in response.provider_rejections:
            rows.append(
                {
                    "case_id": execution.case_id,
                    "provider": "openalex",
                    "tool": response.tool,
                    "provider_request_id": response.provider_request_id,
                    "provider_request_id_source": usage.request_id_source,
                    "provider_cost_basis": usage.cost_basis,
                    "provider_result_index": str(rejection.provider_result_index),
                    "adapter_disposition": "provider_rejected",
                    "scope_link_action": "NOT_EVALUATED",
                    "abstention_reasons": "[]",
                    "missing_required_groups": "[]",
                    "exact_required_groups": "[]",
                    "provider_only_required_groups": "[]",
                    "exact_scope_groups": "[]",
                    "linked_scope_groups": "[]",
                    "title_anchor_groups": "[]",
                    "required_match_provenance": "[]",
                    "scope_match_provenance": "[]",
                    "supporting_match_provenance": "[]",
                    "link_evidence": "[]",
                    "aboutness_signal_count": "0",
                    "candidate_sha256": "",
                    "profile_sha256": execution.profile_sha256,
                    "title": rejection.title or "",
                    "url": rejection.url or "",
                    "provider_rejection_code": rejection.code,
                    "rejection_detail": rejection.detail,
                    "latency_ms": str(execution.latency_ms),
                    "trace_id": execution.trace_id,
                }
            )
    rows.sort(key=lambda row: (row["case_id"], int(row["provider_result_index"])))
    reviews.sort(
        key=lambda row: (row["case_id"], int(row["provider_result_index"]))
    )
    return rows, reviews


def _csv_text(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _write_final_artifacts(
    output_dir: Path,
    artifact: ScopeLinkExecutionArtifact,
) -> None:
    rows, reviews = _candidate_rows(artifact.cases)
    _write_new(output_dir / "execution.json", _json_text(artifact))
    _write_new(
        output_dir / "candidates.csv",
        _csv_text(_CANDIDATE_COLUMNS, rows),
    )
    _write_new(output_dir / "review.csv", _csv_text(_REVIEW_COLUMNS, reviews))
    file_hashes = {
        name: _sha256_bytes((output_dir / name).read_bytes())
        for name in _AGGREGATE_SOURCE_FILES
    }
    _write_new(
        output_dir / "artifact-index.json",
        _json_text(
            {
                "schema_version": 1,
                "mode": "openalex_scope_link_v4_artifact_index",
                "production_connected": False,
                "report_workflow_connected": False,
                "source_file_sha256": file_hashes,
            }
        ),
    )


def _review_packet_eligibility(
    *,
    successful_case_count: int,
    accepted_case_count: int,
    gates: ScopeLinkSourceValueGates,
) -> ReviewPacketEligibility:
    if successful_case_count != MAXIMUM_REQUESTS:
        return "incomplete"
    if accepted_case_count < gates.accepted_case_count_min:
        return "mechanical_gate_failed"
    return "eligible_for_source_lock"


def execute_live_study(
    *,
    output_dir: Path,
    soft_stop_usd: float,
    acknowledge_anonymous_daily_budget: bool,
    adapter_factory: AdapterFactory | None = None,
    monotonic_clock: Clock | None = None,
) -> ScopeLinkExecutionArtifact:
    """Run W01-W08 under a provider-reported soft stop and write-once seams."""

    if not 0.0 < soft_stop_usd <= MAXIMUM_SOFT_STOP_USD:
        raise OpenAlexScopeLinkLiveError(
            "scope-link v4 soft stop must be greater than zero and at most USD 0.01"
        )
    if not acknowledge_anonymous_daily_budget:
        raise OpenAlexScopeLinkLiveError(
            "scope-link v4 execution requires daily-budget acknowledgement"
        )
    if (os.getenv("OPENALEX_API_KEY") or "").strip():
        raise OpenAlexScopeLinkLiveError(
            "anonymous scope-link v4 study refuses a configured OPENALEX_API_KEY"
        )
    if output_dir.exists():
        raise FileExistsError(f"scope-link v4 output already exists: {output_dir}")

    fixture_sha256, challenge, cases = load_frozen_cases()
    implementation_sha256 = verify_frozen_implementation()
    runner_sha256 = _file_sha256(_RUNNER_PATH)
    # Reserve the path and persist the complete method before constructing a
    # network-capable object.  This ordering is a crash/retry boundary, not a
    # cosmetic artifact convention.
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = _manifest_artifact(
        cases,
        fixture_sha256,
        implementation_sha256,
        runner_sha256,
        challenge.source_value_gates,
        soft_stop_usd,
    )
    _write_new(output_dir / "manifest.json", _json_text(manifest))
    adapter: ScopeLinkAdapter
    if adapter_factory is not None:
        adapter = adapter_factory()
    else:
        adapter = AnonymousOpenAlexClaimScopeAdapter(
            transport=_OneRequestTransport()
        )

    executions: list[ScopeLinkCaseExecution] = []
    clock = monotonic_clock or time.perf_counter
    known_cost = 0.0
    stopped_reason: StopReason = "completed"
    for case in cases:
        if known_cost + 1e-12 >= soft_stop_usd:
            stopped_reason = "soft_stop"
            break
        call = case.plan.calls[0]
        case_stop_reason: StopReason | None = None
        started_at = clock()
        try:
            raw_response = adapter(call)
        except ToolAdapterFailure as exc:
            latency_ms = _elapsed_ms(clock, started_at)
            execution = _failure_execution(
                case,
                failure_type=exc.failure_type,
                failure_detail=str(exc),
                failure_retryable=exc.retryable,
                latency_ms=latency_ms,
                search_cost_usd=exc.search_cost_usd,
            )
            case_stop_reason = "request_failed"
        else:
            latency_ms = _elapsed_ms(clock, started_at)
            try:
                response = OpenAlexClaimScopeAdapterResponse.model_validate(
                    raw_response
                )
            except ValidationError as exc:
                execution = _failure_execution(
                    case,
                    failure_type="adapter_response_invalid",
                    failure_detail=_validation_detail(exc),
                    failure_retryable=False,
                    latency_ms=latency_ms,
                )
                case_stop_reason = "accounting_invalid"
            else:
                if response.idempotency_key != call.idempotency_key:
                    execution = _failure_execution(
                        case,
                        failure_type="adapter_identity_mismatch",
                        failure_detail=(
                            "adapter response idempotency key does not match the "
                            "authorized call"
                        ),
                        failure_retryable=False,
                        latency_ms=latency_ms,
                        response=response,
                        search_cost_usd=response.search_cost_usd,
                    )
                    case_stop_reason = "accounting_invalid"
                else:
                    execution = _completed_execution(case, response, latency_ms)

        # Commit the one-request journal before checking whether another case
        # may run.  If the process dies after this line, the spent request and
        # its disposition remain independently inspectable.
        _write_case_journal(output_dir, execution)
        executions.append(execution)
        if execution.search_cost_usd is None:
            stopped_reason = case_stop_reason or "cost_uninspectable"
            break
        known_cost += execution.search_cost_usd
        if case_stop_reason is not None:
            stopped_reason = case_stop_reason
            break

    cost_state, reported_cost = _provider_cost(executions)
    successful_case_count = sum(item.state == "completed" for item in executions)
    provider_summary = ScopeLinkProviderSummary(
        attempted_case_count=len(executions),
        successful_case_count=successful_case_count,
        request_count=sum(item.outbound_attempt_count for item in executions),
        cost_state=cost_state,
        reported_cost_usd=reported_cost,
        total_latency_ms=sum(item.latency_ms for item in executions),
        stopped_reason=stopped_reason,
    )
    evaluations = tuple(item for case in executions for item in case.evaluations)
    accepted_case_count = sum(
        any(item.decision.action == "ACCEPT" for item in case.evaluations)
        for case in executions
    )
    artifact = ScopeLinkExecutionArtifact(
        fixture_sha256=fixture_sha256,
        implementation_sha256=implementation_sha256,
        runner_sha256=runner_sha256,
        soft_stop_usd=soft_stop_usd,
        request_count=provider_summary.request_count,
        attempted_case_count=provider_summary.attempted_case_count,
        successful_case_count=provider_summary.successful_case_count,
        overall_state=(
            "completed" if stopped_reason == "completed" else "partial"
        ),
        scope_link_accepted_candidate_count=sum(
            item.decision.action == "ACCEPT" for item in evaluations
        ),
        scope_link_abstained_candidate_count=sum(
            item.decision.action == "ABSTAIN" for item in evaluations
        ),
        scope_link_accepted_case_count=accepted_case_count,
        review_packet_eligibility=_review_packet_eligibility(
            successful_case_count=successful_case_count,
            accepted_case_count=accepted_case_count,
            gates=challenge.source_value_gates,
        ),
        source_value_gates=challenge.source_value_gates,
        provider_summary=provider_summary,
        cases=tuple(executions),
    )
    _write_final_artifacts(output_dir, artifact)
    return artifact


def _stdout_json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
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
    print(_stdout_json(artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
