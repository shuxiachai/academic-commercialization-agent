"""Production-disconnected runner for the precision-v2 unseen challenge.

The default command is a zero-network dry-run.  Live execution is a separate,
explicitly acknowledged path that locks the original fixture, its transparent
pre-provider correction, and every reused implementation file before output
reservation or adapter construction.  Results never enter report evidence:
the legacy quarantine remains intact and precision-v2 creates a second,
separately reviewable ACCEPT/ABSTAIN delta.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, model_validator

from academic_agent.evidence_gap import ValidatedGapPlan, source_collection_sha256
from academic_agent.evidence_gap_execution import (
    EvidenceGapExecutionAudit,
    execute_gap_plan,
)
from academic_agent.openalex_precision import (
    AcademicPrecisionDecision,
    AcademicPrecisionProfile,
    evaluate_academic_candidate,
)
from academic_agent.source_pipeline import SourceCollection
from academic_agent.tools.evidence_search import (
    ReadOnlySearchAdapter,
    ToolEvidenceCandidate,
)
from openalex_precision_unseen import (
    EXPECTED_CORRECTION_SHA256,
    EXPECTED_FIXTURE_SHA256,
    PreparedUnseenCase,
    UnseenChallengeCaseSpec,
    UnseenSourceValueGates,
    dry_run,
    load_frozen_cases,
)


_ROOT = Path(__file__).resolve().parent
_IMPLEMENTATION_PATHS = {
    "anonymous_openalex_search.py": (
        _ROOT / "src/academic_agent/tools/anonymous_openalex_search.py"
    ),
    "domain_evidence_search.py": (
        _ROOT / "src/academic_agent/tools/domain_evidence_search.py"
    ),
    "evidence_gap_execution.py": (
        _ROOT / "src/academic_agent/evidence_gap_execution.py"
    ),
    "openalex_precision.py": (
        _ROOT / "src/academic_agent/openalex_precision.py"
    ),
    "openalex_precision_unseen.py": _ROOT / "openalex_precision_unseen.py",
}
EXPECTED_IMPLEMENTATION_SHA256 = {
    "anonymous_openalex_search.py": (
        "bcaa201622fe5241115661cd9d5a6f7616761eddfedb9acf364b3693e7a044c9"
    ),
    "domain_evidence_search.py": (
        "ae79c38378321f6ce4481e682787ee49f930ec4c34b696d404fcf78d97b2eeab"
    ),
    "evidence_gap_execution.py": (
        "5b1b94ebd8130834603567f25336dcf106d58653e6bdd2b862509d396639e8fe"
    ),
    "openalex_precision.py": (
        "7c6e0f2999aae68a9caa042584c886bc5273037a2eaf2e95d80c553b7a503029"
    ),
    "openalex_precision_unseen.py": (
        "7dbe457aca2185d6daa4f51602e3683f60ca59a1c8dda01dec9204c3093332e7"
    ),
}
MAXIMUM_REQUESTS = 8
MAXIMUM_SOFT_STOP_USD = 0.01
ANONYMOUS_DAILY_BUDGET_USD = 0.10
_CASE_ORDER = tuple(f"U{index:02d}" for index in range(1, 9))
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
    "legacy_local_disposition",
    "legacy_accepted_source_id",
    "precision_action",
    "precision_abstention_reasons",
    "matched_required_groups",
    "missing_required_groups",
    "matched_supporting_groups",
    "title_required_groups",
    "candidate_sha256",
    "profile_sha256",
    "title",
    "url",
    "provider_rejection_code",
    "legacy_rejection_code",
    "rejection_detail",
    "trace_id",
)
_REVIEW_COLUMNS = (
    "case_id",
    "provider",
    "accepted_source_id",
    "title",
    "url",
    "relevant",
    "novel",
    "review_note",
)


AdapterFactory = Callable[[], ReadOnlySearchAdapter]
StopReason = Literal[
    "completed",
    "soft_stop",
    "cost_uninspectable",
    "request_failed",
    "accounting_invalid",
]


class OpenAlexPrecisionLiveError(ValueError):
    """Raised before provider work when a frozen live boundary fails."""


class PrecisionFrozenCaseArtifact(BaseModel):
    """Complete deterministic case input persisted before the first request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: UnseenChallengeCaseSpec
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_collection: SourceCollection
    validated_plan: ValidatedGapPlan

    @model_validator(mode="after")
    def _validate_expanded_identities(self) -> "PrecisionFrozenCaseArtifact":
        if source_collection_sha256(self.source_collection) != self.collection_sha256:
            raise ValueError("expanded source collection hash does not match")
        plan_sha256 = _sha256_bytes(
            self.validated_plan.model_dump_json(exclude_none=False).encode("utf-8")
        )
        if plan_sha256 != self.plan_sha256:
            raise ValueError("expanded validated plan hash does not match")
        if self.spec.profile.sha256() != self.profile_sha256:
            raise ValueError("expanded precision profile hash does not match")
        return self


class PrecisionManifestArtifact(BaseModel):
    """Write-once expansion of all frozen inputs and implementation identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_precision_v2_unseen_manifest"] = (
        "openalex_precision_v2_unseen_manifest"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    api_key_used: Literal[False] = False
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    correction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    maximum_requests: Literal[8] = MAXIMUM_REQUESTS
    anonymous_daily_budget_usd: Literal[0.1] = ANONYMOUS_DAILY_BUDGET_USD
    soft_stop_usd: float = Field(gt=0.0, le=MAXIMUM_SOFT_STOP_USD)
    source_value_gates: UnseenSourceValueGates
    cases: tuple[PrecisionFrozenCaseArtifact, ...] = Field(
        min_length=8,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_frozen_contract(self) -> "PrecisionManifestArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("manifest fixture identity does not match")
        if self.correction_sha256 != EXPECTED_CORRECTION_SHA256:
            raise ValueError("manifest correction identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("manifest implementation identities do not match")
        if tuple(case.spec.case_id for case in self.cases) != _CASE_ORDER:
            raise ValueError("manifest cases must remain ordered U01 through U08")
        return self


class PrecisionCandidateEvaluation(BaseModel):
    """One legacy-accepted candidate joined to its v2 decision at the seam."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_index: int = Field(ge=0, le=9)
    accepted_source_id: str = Field(pattern=r"^A[2-9][0-9]*$")
    candidate: ToolEvidenceCandidate
    decision: AcademicPrecisionDecision

    @model_validator(mode="after")
    def _validate_candidate_identity(self) -> "PrecisionCandidateEvaluation":
        if _candidate_sha256(self.candidate) != self.decision.candidate_sha256:
            raise ValueError("precision decision is attached to another candidate")
        return self


class PrecisionCaseExecution(BaseModel):
    """One request audit plus every eligible precision-v2 decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^U0[1-8]$")
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit: EvidenceGapExecutionAudit
    precision_evaluations: tuple[PrecisionCandidateEvaluation, ...] = Field(
        default=(),
        max_length=5,
    )

    @model_validator(mode="after")
    def _validate_every_eligible_candidate(self) -> "PrecisionCaseExecution":
        expected = _eligible_candidate_pairs(self.audit)
        observed = tuple(
            (
                item.candidate_index,
                item.accepted_source_id,
                item.candidate,
            )
            for item in self.precision_evaluations
        )
        if observed != expected:
            raise ValueError(
                "every legacy-accepted candidate must reach precision evaluation"
            )
        if any(
            item.decision.profile_sha256 != self.profile_sha256
            for item in self.precision_evaluations
        ):
            raise ValueError("precision decision profile identity drifted")
        return self


class PrecisionProviderSummary(BaseModel):
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
    stopped_reason: StopReason

    @model_validator(mode="after")
    def _validate_accounting(self) -> "PrecisionProviderSummary":
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


class PrecisionExecutionArtifact(BaseModel):
    """Final write-once state; human source value remains unevaluated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_precision_v2_unseen_execution"] = (
        "openalex_precision_v2_unseen_execution"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    api_key_used: Literal[False] = False
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    correction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    maximum_requests: Literal[8] = MAXIMUM_REQUESTS
    anonymous_daily_budget_usd: Literal[0.1] = ANONYMOUS_DAILY_BUDGET_USD
    soft_stop_usd: float = Field(gt=0.0, le=MAXIMUM_SOFT_STOP_USD)
    request_count: int = Field(ge=0, le=8)
    attempted_case_count: int = Field(ge=0, le=8)
    successful_case_count: int = Field(ge=0, le=8)
    overall_state: Literal["completed", "partial"]
    precision_accepted_candidate_count: int = Field(ge=0, le=40)
    precision_abstained_candidate_count: int = Field(ge=0, le=40)
    precision_accepted_case_count: int = Field(ge=0, le=8)
    source_lock_state: Literal["not_created"] = "not_created"
    human_review_state: Literal["not_prepared"] = "not_prepared"
    source_value_state: Literal["not_evaluated"] = "not_evaluated"
    provider_summary: PrecisionProviderSummary
    cases: tuple[PrecisionCaseExecution, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def _validate_totals(self) -> "PrecisionExecutionArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("execution fixture identity does not match")
        if self.correction_sha256 != EXPECTED_CORRECTION_SHA256:
            raise ValueError("execution correction identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("execution implementation identities do not match")
        case_ids = tuple(case.case_id for case in self.cases)
        if case_ids != _CASE_ORDER[: len(case_ids)]:
            raise ValueError("case executions must preserve the frozen prefix")
        request_count = sum(
            case.audit.outbound_attempt_count for case in self.cases
        )
        successful_count = sum(_case_succeeded(case) for case in self.cases)
        if request_count != self.request_count:
            raise ValueError("request count must equal the executor audit total")
        if len(self.cases) != self.attempted_case_count:
            raise ValueError("attempted cases must equal persisted case audits")
        if successful_count != self.successful_case_count:
            raise ValueError("successful cases must equal validated case audits")
        if self.provider_summary.request_count != self.request_count:
            raise ValueError("provider request count drifted from execution")
        if self.provider_summary.attempted_case_count != self.attempted_case_count:
            raise ValueError("provider attempted-case count drifted from execution")
        if self.provider_summary.successful_case_count != self.successful_case_count:
            raise ValueError("provider successful-case count drifted from execution")

        evaluations = tuple(
            item
            for case in self.cases
            for item in case.precision_evaluations
        )
        accepted = sum(item.decision.action == "ACCEPT" for item in evaluations)
        abstained = sum(item.decision.action == "ABSTAIN" for item in evaluations)
        accepted_cases = sum(
            any(
                item.decision.action == "ACCEPT"
                for item in case.precision_evaluations
            )
            for case in self.cases
        )
        if accepted != self.precision_accepted_candidate_count:
            raise ValueError("precision accepted-candidate count drifted")
        if abstained != self.precision_abstained_candidate_count:
            raise ValueError("precision abstained-candidate count drifted")
        if accepted_cases != self.precision_accepted_case_count:
            raise ValueError("precision accepted-case count drifted")
        completed = self.successful_case_count == MAXIMUM_REQUESTS
        if (self.overall_state == "completed") != completed:
            raise ValueError("overall state does not match provider completion")
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


def _candidate_sha256(candidate: ToolEvidenceCandidate) -> str:
    return _sha256_bytes(
        candidate.model_dump_json(exclude_none=False).encode("utf-8")
    )


def _file_sha256(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise OpenAlexPrecisionLiveError(
            f"could not read frozen implementation file {path}: {exc}"
        ) from exc


def verify_frozen_implementation() -> dict[str, str]:
    """Fail closed on implementation drift before constructing a transport."""

    observed = {
        name: _file_sha256(path) for name, path in _IMPLEMENTATION_PATHS.items()
    }
    if observed != EXPECTED_IMPLEMENTATION_SHA256:
        drift = {
            name: {
                "expected": EXPECTED_IMPLEMENTATION_SHA256[name],
                "observed": observed[name],
            }
            for name in EXPECTED_IMPLEMENTATION_SHA256
            if observed[name] != EXPECTED_IMPLEMENTATION_SHA256[name]
        }
        raise OpenAlexPrecisionLiveError(
            f"precision-v2 implementation identity drifted: {drift}"
        )
    return observed


def protocol_dry_run() -> dict[str, Any]:
    """Validate every frozen identity while constructing no network object."""

    result = dict(dry_run())
    result["implementation_sha256"] = verify_frozen_implementation()
    result["live_provider_requests_authorized"] = False
    return result


def _manifest_artifact(
    cases: tuple[PreparedUnseenCase, ...],
    fixture_sha256: str,
    correction_sha256: str,
    implementation_sha256: dict[str, str],
    gates: UnseenSourceValueGates,
    soft_stop_usd: float,
) -> PrecisionManifestArtifact:
    return PrecisionManifestArtifact(
        fixture_sha256=fixture_sha256,
        correction_sha256=correction_sha256,
        implementation_sha256=implementation_sha256,
        soft_stop_usd=soft_stop_usd,
        source_value_gates=gates,
        cases=tuple(
            PrecisionFrozenCaseArtifact(
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


def _eligible_candidate_pairs(
    audit: EvidenceGapExecutionAudit,
) -> tuple[tuple[int, str, ToolEvidenceCandidate], ...]:
    if len(audit.call_audits) != 1:
        return ()
    call = audit.call_audits[0]
    if call.state != "accepted":
        return ()
    rejected = {item.candidate_index for item in call.rejections}
    eligible = tuple(
        (index, candidate)
        for index, candidate in enumerate(call.candidate_records)
        if index not in rejected
    )
    if len(eligible) != len(call.accepted_source_ids):
        raise OpenAlexPrecisionLiveError(
            "legacy accepted IDs do not match eligible candidate order"
        )
    return tuple(
        (index, source_id, candidate)
        for (index, candidate), source_id in zip(
            eligible,
            call.accepted_source_ids,
            strict=True,
        )
    )


def _precision_evaluations(
    audit: EvidenceGapExecutionAudit,
    profile: AcademicPrecisionProfile,
) -> tuple[PrecisionCandidateEvaluation, ...]:
    return tuple(
        PrecisionCandidateEvaluation(
            candidate_index=index,
            accepted_source_id=source_id,
            candidate=candidate,
            decision=evaluate_academic_candidate(candidate, profile),
        )
        for index, source_id, candidate in _eligible_candidate_pairs(audit)
    )


def _case_succeeded(case: PrecisionCaseExecution) -> bool:
    if case.audit.evidence_delta_state == "failed":
        return False
    if len(case.audit.call_audits) != 1:
        return False
    call = case.audit.call_audits[0]
    return call.outbound_attempt_count == 1 and call.state != "failed"


def _provider_accounting_issue(execution: PrecisionCaseExecution) -> str | None:
    if len(execution.audit.call_audits) != 1:
        return "expected_exactly_one_call_audit"
    call = execution.audit.call_audits[0]
    if call.outbound_attempt_count != 1:
        return "expected_exactly_one_outbound_attempt"
    if call.state == "failed":
        return "provider_request_failed"
    usage = call.provider_usage
    if usage is None:
        return "provider_usage_missing"
    if usage.provider != "openalex":
        return "provider_identity_mismatch"
    if usage.cost_basis != "reported_usd" or call.cost_state != "known":
        return "openalex_reported_cost_missing"
    return None


def _provider_cost(
    executions: list[PrecisionCaseExecution],
) -> tuple[Literal["known", "uninspectable", "not_observed"], float | None]:
    if not executions:
        return "not_observed", None
    values = [item.audit.incremental_search_cost_usd for item in executions]
    if any(value is None for value in values):
        return "uninspectable", None
    return "known", sum(value for value in values if value is not None)


def _write_new(path: Path, value: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(value)
    except OSError as exc:
        raise OpenAlexPrecisionLiveError(
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
    execution: PrecisionCaseExecution,
) -> None:
    journal_dir = output_dir / "case-executions"
    journal_dir.mkdir(exist_ok=True)
    _write_new(journal_dir / f"{execution.case_id}.json", _json_text(execution))


def _json_tuple(values: tuple[str, ...]) -> str:
    return json.dumps(values, ensure_ascii=True, separators=(",", ":"))


def _candidate_rows(
    executions: tuple[PrecisionCaseExecution, ...],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    reviews: list[dict[str, str]] = []
    for execution in executions:
        evaluations = {
            item.candidate_index: item for item in execution.precision_evaluations
        }
        for call in execution.audit.call_audits:
            usage = call.provider_usage
            local_rejections = {
                item.candidate_index: item for item in call.rejections
            }
            for candidate_index, candidate in enumerate(call.candidate_records):
                local_rejection = local_rejections.get(candidate_index)
                evaluation = evaluations.get(candidate_index)
                if local_rejection is not None:
                    legacy_disposition = "quarantine_rejected"
                    source_id = ""
                elif evaluation is not None:
                    legacy_disposition = "quarantined_accepted"
                    source_id = evaluation.accepted_source_id
                else:
                    legacy_disposition = "call_failed_before_registration"
                    source_id = ""
                decision = evaluation.decision if evaluation is not None else None
                rows.append(
                    {
                        "case_id": execution.case_id,
                        "provider": "openalex",
                        "tool": call.tool,
                        "provider_request_id": usage.request_id if usage else "",
                        "provider_request_id_source": (
                            usage.request_id_source if usage else ""
                        ),
                        "provider_cost_basis": usage.cost_basis if usage else "",
                        "provider_result_index": str(
                            candidate.provider_result_index
                            if candidate.provider_result_index is not None
                            else candidate_index
                        ),
                        "adapter_disposition": "candidate",
                        "legacy_local_disposition": legacy_disposition,
                        "legacy_accepted_source_id": source_id,
                        "precision_action": (
                            decision.action if decision is not None else "NOT_EVALUATED"
                        ),
                        "precision_abstention_reasons": (
                            _json_tuple(decision.abstention_reasons)
                            if decision is not None
                            else "[]"
                        ),
                        "matched_required_groups": (
                            _json_tuple(decision.matched_required_groups)
                            if decision is not None
                            else "[]"
                        ),
                        "missing_required_groups": (
                            _json_tuple(decision.missing_required_groups)
                            if decision is not None
                            else "[]"
                        ),
                        "matched_supporting_groups": (
                            _json_tuple(decision.matched_supporting_groups)
                            if decision is not None
                            else "[]"
                        ),
                        "title_required_groups": (
                            _json_tuple(decision.title_required_groups)
                            if decision is not None
                            else "[]"
                        ),
                        "candidate_sha256": (
                            decision.candidate_sha256 if decision is not None else ""
                        ),
                        "profile_sha256": execution.profile_sha256,
                        "title": candidate.title,
                        "url": candidate.url,
                        "provider_rejection_code": "",
                        "legacy_rejection_code": (
                            local_rejection.code if local_rejection else ""
                        ),
                        "rejection_detail": (
                            local_rejection.detail if local_rejection else ""
                        ),
                        "trace_id": call.trace_id,
                    }
                )
                if evaluation is not None and decision.action == "ACCEPT":
                    reviews.append(
                        {
                            "case_id": execution.case_id,
                            "provider": "openalex",
                            "accepted_source_id": source_id,
                            "title": candidate.title,
                            "url": candidate.url,
                            "relevant": "",
                            "novel": "",
                            "review_note": "",
                        }
                    )
            for rejection in call.provider_rejections:
                rows.append(
                    {
                        "case_id": execution.case_id,
                        "provider": "openalex",
                        "tool": call.tool,
                        "provider_request_id": usage.request_id if usage else "",
                        "provider_request_id_source": (
                            usage.request_id_source if usage else ""
                        ),
                        "provider_cost_basis": usage.cost_basis if usage else "",
                        "provider_result_index": str(rejection.provider_result_index),
                        "adapter_disposition": "provider_rejected",
                        "legacy_local_disposition": "not_checked",
                        "legacy_accepted_source_id": "",
                        "precision_action": "NOT_EVALUATED",
                        "precision_abstention_reasons": "[]",
                        "matched_required_groups": "[]",
                        "missing_required_groups": "[]",
                        "matched_supporting_groups": "[]",
                        "title_required_groups": "[]",
                        "candidate_sha256": "",
                        "profile_sha256": execution.profile_sha256,
                        "title": rejection.title or "",
                        "url": rejection.url or "",
                        "provider_rejection_code": rejection.code,
                        "legacy_rejection_code": "",
                        "rejection_detail": rejection.detail,
                        "trace_id": call.trace_id,
                    }
                )
    rows.sort(key=lambda row: (row["case_id"], int(row["provider_result_index"])))
    reviews.sort(key=lambda row: (row["case_id"], row["accepted_source_id"]))
    return rows, reviews


def _csv_text(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _write_final_artifacts(
    output_dir: Path,
    artifact: PrecisionExecutionArtifact,
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
                "mode": "openalex_precision_v2_unseen_artifact_index",
                "production_connected": False,
                "report_workflow_connected": False,
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
) -> PrecisionExecutionArtifact:
    """Run U01-U08 under a provider-reported soft stop and write-once seams."""

    if not 0.0 < soft_stop_usd <= MAXIMUM_SOFT_STOP_USD:
        raise OpenAlexPrecisionLiveError(
            "precision-v2 soft stop must be greater than zero and at most USD 0.01"
        )
    if not acknowledge_anonymous_daily_budget:
        raise OpenAlexPrecisionLiveError(
            "precision-v2 execution requires explicit daily-budget acknowledgement"
        )
    if (os.getenv("OPENALEX_API_KEY") or "").strip():
        raise OpenAlexPrecisionLiveError(
            "anonymous precision-v2 study refuses a configured OPENALEX_API_KEY"
        )
    if output_dir.exists():
        raise FileExistsError(f"precision-v2 output already exists: {output_dir}")

    fixture_sha256, correction_sha256, gates, cases = load_frozen_cases()
    implementation_sha256 = verify_frozen_implementation()
    # Reserve the path and persist every identity before constructing the
    # adapter.  A later crash therefore leaves inspectable input, and path
    # reuse fails before another anonymous-budget request can start.
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = _manifest_artifact(
        cases,
        fixture_sha256,
        correction_sha256,
        implementation_sha256,
        gates,
        soft_stop_usd,
    )
    _write_new(output_dir / "manifest.json", _json_text(manifest))
    if adapter_factory is not None:
        adapter = adapter_factory()
    else:
        # Keep the network-capable import and client construction outside
        # module import and dry-run.  The explicit sentinel is removed at the
        # final outbound seam by the already frozen anonymous adapter.
        from academic_agent.tools.anonymous_openalex_search import (
            AnonymousOpenAlexEvidenceSearchAdapter,
        )

        adapter = AnonymousOpenAlexEvidenceSearchAdapter(
            transport=_OneRequestTransport()
        )

    executions: list[PrecisionCaseExecution] = []
    known_cost = 0.0
    stopped_reason: StopReason = "completed"
    for case in cases:
        if known_cost + 1e-12 >= soft_stop_usd:
            stopped_reason = "soft_stop"
            break
        audit = execute_gap_plan(
            case.collection,
            context=case.context,
            plan=case.plan,
            adapters={"academic_search": adapter},
            trace_id=f"openalex-precision-v2-{case.spec.case_id.casefold()}-unseen",
            outbound_attempt_limit=1,
        )
        execution = PrecisionCaseExecution(
            case_id=case.spec.case_id,
            collection_sha256=case.collection_sha256,
            plan_sha256=case.plan_sha256,
            profile_sha256=case.profile_sha256,
            audit=audit,
            precision_evaluations=_precision_evaluations(
                audit,
                case.spec.profile,
            ),
        )
        _write_case_journal(output_dir, execution)
        executions.append(execution)

        issue = _provider_accounting_issue(execution)
        if issue == "provider_request_failed":
            stopped_reason = "request_failed"
            break
        if issue is not None:
            stopped_reason = "accounting_invalid"
            break
        if audit.incremental_search_cost_usd is None:
            stopped_reason = "cost_uninspectable"
            break
        known_cost += audit.incremental_search_cost_usd

    cost_state, reported_cost = _provider_cost(executions)
    successful_case_count = sum(_case_succeeded(item) for item in executions)
    provider_summary = PrecisionProviderSummary(
        attempted_case_count=len(executions),
        successful_case_count=successful_case_count,
        request_count=sum(item.audit.outbound_attempt_count for item in executions),
        cost_state=cost_state,
        reported_cost_usd=reported_cost,
        stopped_reason=stopped_reason,
    )
    evaluations = tuple(
        item
        for execution in executions
        for item in execution.precision_evaluations
    )
    artifact = PrecisionExecutionArtifact(
        fixture_sha256=fixture_sha256,
        correction_sha256=correction_sha256,
        implementation_sha256=implementation_sha256,
        soft_stop_usd=soft_stop_usd,
        request_count=provider_summary.request_count,
        attempted_case_count=provider_summary.attempted_case_count,
        successful_case_count=provider_summary.successful_case_count,
        overall_state=(
            "completed"
            if provider_summary.stopped_reason == "completed"
            else "partial"
        ),
        precision_accepted_candidate_count=sum(
            item.decision.action == "ACCEPT" for item in evaluations
        ),
        precision_abstained_candidate_count=sum(
            item.decision.action == "ABSTAIN" for item in evaluations
        ),
        precision_accepted_case_count=sum(
            any(
                item.decision.action == "ACCEPT"
                for item in execution.precision_evaluations
            )
            for execution in executions
        ),
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
