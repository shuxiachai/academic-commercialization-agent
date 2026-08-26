"""Production-disconnected live runner for the frozen Phase 4 value study.

Dry-run delegates to the byte-frozen Phase 4 preflight. Live execution is a
separate, explicitly acknowledged path that verifies the exact adapter and
executor bytes before constructing a provider client. Results remain isolated
from the report workflow and are persisted as write-once experimental evidence.
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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from academic_agent.evidence_gap import ValidatedGapPlan, source_collection_sha256
from academic_agent.evidence_gap_execution import (
    EvidenceGapExecutionAudit,
    execute_gap_plan,
)
from academic_agent.source_pipeline import SourceCollection
from academic_agent.tools.evidence_search import ReadOnlySearchAdapter
from evidence_gap_phase4_audit import (
    EXPECTED_FIXTURE_SHA256,
    PreparedPhase4Case,
    Phase4CaseSpec,
    dry_run,
    load_frozen_cases,
)


_ROOT = Path(__file__).resolve().parent
_IMPLEMENTATION_PATHS = {
    "domain_evidence_search.py": (
        _ROOT / "src/academic_agent/tools/domain_evidence_search.py"
    ),
    "evidence_gap_execution.py": (
        _ROOT / "src/academic_agent/evidence_gap_execution.py"
    ),
    "evidence_gap_phase4_audit.py": _ROOT / "evidence_gap_phase4_audit.py",
}
EXPECTED_IMPLEMENTATION_SHA256 = {
    "domain_evidence_search.py": (
        "ae79c38378321f6ce4481e682787ee49f930ec4c34b696d404fcf78d97b2eeab"
    ),
    "evidence_gap_execution.py": (
        "5b1b94ebd8130834603567f25336dcf106d58653e6bdd2b862509d396639e8fe"
    ),
    "evidence_gap_phase4_audit.py": (
        "e70c2e015ffc5a01b1f9e35634dd65b9a37062bc561b9deaff8fbfa3bfb09477"
    ),
}
MAXIMUM_REQUESTS = 8
_CASES_PER_PROVIDER = 4
_PROVIDER_ORDER = ("openalex", "lens")
_CASE_ORDER = tuple(f"D{index:02d}" for index in range(1, 9))
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
    "local_disposition",
    "accepted_source_id",
    "title",
    "url",
    "provider_rejection_code",
    "local_rejection_code",
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

AdapterFactory = Callable[[], Mapping[str, ReadOnlySearchAdapter]]
ProviderName = Literal["openalex", "lens"]
ProviderStopReason = Literal[
    "completed",
    "soft_stop",
    "cost_uninspectable",
    "request_failed",
    "accounting_invalid",
]


class Phase4LiveError(ValueError):
    """Raised before provider work when a frozen live-study boundary fails."""


class Phase4FrozenCaseArtifact(BaseModel):
    """Complete deterministic input persisted before the first request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: Phase4CaseSpec
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_collection: SourceCollection
    validated_plan: ValidatedGapPlan

    @model_validator(mode="after")
    def _validate_expanded_identities(self) -> "Phase4FrozenCaseArtifact":
        if source_collection_sha256(self.source_collection) != self.collection_sha256:
            raise ValueError("expanded source collection hash does not match")
        observed_plan_sha256 = _sha256_bytes(
            self.validated_plan.model_dump_json(exclude_none=False).encode("utf-8")
        )
        if observed_plan_sha256 != self.plan_sha256:
            raise ValueError("expanded validated plan hash does not match")
        return self


class Phase4ManifestArtifact(BaseModel):
    """Write-once expansion of every frozen case and implementation identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["phase4_frozen_domain_value_study"] = (
        "phase4_frozen_domain_value_study"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    maximum_requests: Literal[8] = MAXIMUM_REQUESTS
    cases: tuple[Phase4FrozenCaseArtifact, ...] = Field(
        min_length=8,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_frozen_contract(self) -> "Phase4ManifestArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("manifest fixture identity does not match the preregistration")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("manifest implementation identities do not match")
        if [case.spec.case_id for case in self.cases] != list(_CASE_ORDER):
            raise ValueError("manifest cases must remain ordered D01 through D08")
        return self


class Phase4CaseExecution(BaseModel):
    """One provider attempt joined back to its frozen collection and plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^D0[1-8]$")
    provider: ProviderName
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit: EvidenceGapExecutionAudit


class Phase4ProviderSummary(BaseModel):
    """Provider-local accounting; unknown Lens cost never contaminates USD."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: ProviderName
    authorized_case_count: Literal[4] = _CASES_PER_PROVIDER
    attempted_case_count: int = Field(ge=0, le=4)
    successful_case_count: int = Field(ge=0, le=4)
    request_count: int = Field(ge=0, le=4)
    cost_state: Literal["known", "uninspectable", "not_observed"]
    reported_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    stopped_reason: ProviderStopReason

    @model_validator(mode="after")
    def _validate_accounting(self) -> "Phase4ProviderSummary":
        if self.successful_case_count > self.attempted_case_count:
            raise ValueError("successful cases cannot exceed attempted cases")
        if self.request_count != self.attempted_case_count:
            raise ValueError("every attempted case must own exactly one request")
        if self.cost_state == "known" and self.reported_cost_usd is None:
            raise ValueError("known provider cost requires a numeric total")
        if self.cost_state != "known" and self.reported_cost_usd is not None:
            raise ValueError("non-numeric provider cost states must keep USD null")
        if self.stopped_reason == "completed" and self.successful_case_count != 4:
            raise ValueError("completed provider state requires four successful cases")
        if self.successful_case_count == 4 and self.stopped_reason != "completed":
            raise ValueError("four successful cases must be reported as completed")
        if self.provider == "lens" and self.request_count:
            if self.cost_state != "uninspectable":
                raise ValueError("Lens request cost must remain uninspectable")
        return self


class Phase4ExecutionArtifact(BaseModel):
    """Final run state; partial and uninspectable are first-class outcomes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["phase4_live_domain_value_study"] = (
        "phase4_live_domain_value_study"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    maximum_requests: Literal[8] = MAXIMUM_REQUESTS
    openalex_soft_stop_usd: float = Field(gt=0.0, le=0.05)
    lens_cost_acknowledged: Literal[True] = True
    request_count: int = Field(ge=0, le=8)
    attempted_case_count: int = Field(ge=0, le=8)
    successful_case_count: int = Field(ge=0, le=8)
    overall_state: Literal["completed", "partial"]
    source_lock_state: Literal["not_created"] = "not_created"
    human_review_state: Literal["not_prepared"] = "not_prepared"
    source_value_state: Literal["not_evaluated"] = "not_evaluated"
    provider_summaries: tuple[Phase4ProviderSummary, ...] = Field(
        min_length=2,
        max_length=2,
    )
    cases: tuple[Phase4CaseExecution, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def _validate_totals_and_provider_seams(self) -> "Phase4ExecutionArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("execution fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("execution implementation identities do not match")
        if [summary.provider for summary in self.provider_summaries] != list(
            _PROVIDER_ORDER
        ):
            raise ValueError("provider summaries must remain ordered OpenAlex then Lens")

        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case executions must have unique identities")
        if case_ids != sorted(case_ids, key=_CASE_ORDER.index):
            raise ValueError("case executions must preserve frozen case order")

        request_count = sum(
            case.audit.outbound_attempt_count for case in self.cases
        )
        successful_count = sum(_case_succeeded(case) for case in self.cases)
        if request_count != self.request_count:
            raise ValueError("request count must equal the executor audit total")
        if len(self.cases) != self.attempted_case_count:
            raise ValueError("attempted case count must equal persisted case audits")
        if successful_count != self.successful_case_count:
            raise ValueError("successful case count must equal validated case audits")

        for summary in self.provider_summaries:
            provider_cases = [
                case for case in self.cases if case.provider == summary.provider
            ]
            if len(provider_cases) != summary.attempted_case_count:
                raise ValueError("provider attempted-case count drifted")
            if sum(_case_succeeded(case) for case in provider_cases) != (
                summary.successful_case_count
            ):
                raise ValueError("provider successful-case count drifted")
            if sum(
                case.audit.outbound_attempt_count for case in provider_cases
            ) != summary.request_count:
                raise ValueError("provider request count drifted")

        completed = self.successful_case_count == 8 and all(
            summary.stopped_reason == "completed"
            for summary in self.provider_summaries
        )
        if (self.overall_state == "completed") != completed:
            raise ValueError("overall state does not match provider completion")
        return self


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise Phase4LiveError(f"could not read frozen implementation file {path}: {exc}") from exc


def verify_frozen_implementation() -> dict[str, str]:
    """Fail closed on code drift before a provider adapter can be constructed."""

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
        raise Phase4LiveError(f"phase-4 implementation identity drifted: {drift}")
    return observed


def protocol_dry_run() -> dict[str, Any]:
    """Validate fixture and implementation identities while opening zero sockets."""

    result = dict(dry_run())
    result["implementation_sha256"] = verify_frozen_implementation()
    result["live_provider_requests_authorized"] = False
    return result


def _build_live_adapters() -> Mapping[str, ReadOnlySearchAdapter]:
    # Keep the live clients out of module import and dry-run. The import and
    # credential-bearing construction happen only after every frozen identity,
    # acknowledgement and output-path check has passed.
    from academic_agent.tools.domain_evidence_search import (
        LensEvidenceSearchAdapter,
        OpenAlexEvidenceSearchAdapter,
    )

    return {
        "openalex": OpenAlexEvidenceSearchAdapter(),
        "lens": LensEvidenceSearchAdapter(),
    }


def _manifest_artifact(
    prepared: tuple[PreparedPhase4Case, ...],
    fixture_sha256: str,
    implementation_sha256: dict[str, str],
) -> Phase4ManifestArtifact:
    return Phase4ManifestArtifact(
        fixture_sha256=fixture_sha256,
        implementation_sha256=implementation_sha256,
        cases=tuple(
            Phase4FrozenCaseArtifact(
                spec=case.spec,
                collection_sha256=case.collection_sha256,
                plan_sha256=case.plan_sha256,
                source_collection=case.collection,
                validated_plan=case.plan,
            )
            for case in prepared
        ),
    )


def _case_succeeded(case: Phase4CaseExecution) -> bool:
    if case.audit.evidence_delta_state == "failed":
        return False
    if len(case.audit.call_audits) != 1:
        return False
    call = case.audit.call_audits[0]
    return call.outbound_attempt_count == 1 and call.state != "failed"


def _provider_accounting_issue(
    execution: Phase4CaseExecution,
) -> str | None:
    """Validate provider lineage that the generic executor cannot specialize."""

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
    if usage.provider != execution.provider:
        return "provider_identity_mismatch"
    if execution.provider == "openalex":
        if usage.cost_basis != "reported_usd" or call.cost_state != "known":
            return "openalex_reported_cost_missing"
    elif usage.cost_basis != "uninspectable" or call.cost_state != "uninspectable":
        return "lens_cost_state_misreported"
    return None


def _provider_cost(
    executions: list[Phase4CaseExecution],
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
        raise Phase4LiveError(f"could not create write-once artifact {path}: {exc}") from exc


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
    execution: Phase4CaseExecution,
) -> None:
    journal_dir = output_dir / "case-executions"
    journal_dir.mkdir(exist_ok=True)
    _write_new(journal_dir / f"{execution.case_id}.json", _json_text(execution))


def _candidate_rows(
    executions: tuple[Phase4CaseExecution, ...],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    reviews: list[dict[str, str]] = []
    for execution in executions:
        for call in execution.audit.call_audits:
            usage = call.provider_usage
            local_rejections = {
                item.candidate_index: item for item in call.rejections
            }
            accepted_ids = iter(call.accepted_source_ids)
            for candidate_index, candidate in enumerate(call.candidate_records):
                local_rejection = local_rejections.get(candidate_index)
                if local_rejection is not None:
                    accepted_source_id = ""
                    local_disposition = "quarantine_rejected"
                elif call.state == "accepted":
                    accepted_source_id = next(accepted_ids)
                    local_disposition = "quarantined_accepted"
                else:
                    accepted_source_id = ""
                    local_disposition = "call_failed_before_registration"
                row = {
                    "case_id": execution.case_id,
                    "provider": execution.provider,
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
                    "local_disposition": local_disposition,
                    "accepted_source_id": accepted_source_id,
                    "title": candidate.title,
                    "url": candidate.url,
                    "provider_rejection_code": "",
                    "local_rejection_code": (
                        local_rejection.code if local_rejection else ""
                    ),
                    "rejection_detail": (
                        local_rejection.detail if local_rejection else ""
                    ),
                    "trace_id": call.trace_id,
                }
                rows.append(row)
                if accepted_source_id:
                    reviews.append(
                        {
                            "case_id": execution.case_id,
                            "provider": execution.provider,
                            "accepted_source_id": accepted_source_id,
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
                        "provider": execution.provider,
                        "tool": call.tool,
                        "provider_request_id": usage.request_id if usage else "",
                        "provider_request_id_source": (
                            usage.request_id_source if usage else ""
                        ),
                        "provider_cost_basis": usage.cost_basis if usage else "",
                        "provider_result_index": str(
                            rejection.provider_result_index
                        ),
                        "adapter_disposition": "provider_rejected",
                        "local_disposition": "not_checked",
                        "accepted_source_id": "",
                        "title": rejection.title or "",
                        "url": rejection.url or "",
                        "provider_rejection_code": rejection.code,
                        "local_rejection_code": "",
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
    artifact: Phase4ExecutionArtifact,
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
    index = {
        "schema_version": 1,
        "mode": "phase4_live_artifact_index",
        "production_connected": False,
        "source_file_sha256": file_hashes,
    }
    _write_new(output_dir / "artifact-index.json", _json_text(index))


def execute_live_study(
    *,
    output_dir: Path,
    openalex_soft_stop_usd: float,
    acknowledge_lens_cost_uninspectable: bool,
    adapter_factory: AdapterFactory | None = None,
) -> Phase4ExecutionArtifact:
    """Run the frozen cases under provider-local stop and write-once boundaries."""

    if not 0.0 < openalex_soft_stop_usd <= 0.05:
        raise Phase4LiveError(
            "OpenAlex soft stop must be greater than zero and at most USD 0.05"
        )
    if not acknowledge_lens_cost_uninspectable:
        raise Phase4LiveError(
            "Lens execution requires explicit acknowledgement of uninspectable cost"
        )
    if output_dir.exists():
        raise FileExistsError(f"phase-4 live output already exists: {output_dir}")

    fixture_sha256, prepared = load_frozen_cases()
    implementation_sha256 = verify_frozen_implementation()
    if adapter_factory is None:
        missing = [
            name
            for name in ("OPENALEX_API_KEY", "LENS_API_KEY")
            if not (os.getenv(name) or "").strip()
        ]
        if missing:
            raise Phase4LiveError(
                "missing live provider credentials: " + ", ".join(missing)
            )

    # Reserve and identify the study before provider construction. A process
    # killed later leaves an inspectable frozen manifest and per-case journals,
    # while a duplicate path always fails before another paid attempt.
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = _manifest_artifact(
        prepared,
        fixture_sha256,
        implementation_sha256,
    )
    _write_new(output_dir / "manifest.json", _json_text(manifest))
    adapters = dict((adapter_factory or _build_live_adapters)())
    if set(adapters) != set(_PROVIDER_ORDER):
        raise Phase4LiveError(
            "adapter factory must provide exactly openalex and lens"
        )

    executions: list[Phase4CaseExecution] = []
    summaries: list[Phase4ProviderSummary] = []
    for provider in _PROVIDER_ORDER:
        provider_cases = [case for case in prepared if case.spec.provider == provider]
        provider_executions: list[Phase4CaseExecution] = []
        known_openalex_cost = 0.0
        stopped_reason: ProviderStopReason = "completed"
        for case in provider_cases:
            if (
                provider == "openalex"
                and known_openalex_cost + 1e-12 >= openalex_soft_stop_usd
            ):
                stopped_reason = "soft_stop"
                break
            audit = execute_gap_plan(
                case.collection,
                context=case.context,
                plan=case.plan,
                adapters={case.spec.tool: adapters[provider]},
                trace_id=f"phase4-{case.spec.case_id.casefold()}-{provider}-value",
                outbound_attempt_limit=1,
            )
            execution = Phase4CaseExecution(
                case_id=case.spec.case_id,
                provider=provider,
                collection_sha256=case.collection_sha256,
                plan_sha256=case.plan_sha256,
                audit=audit,
            )
            # The journal is committed before any later request. Append to the
            # in-memory aggregate only after the disk seam succeeds.
            _write_case_journal(output_dir, execution)
            executions.append(execution)
            provider_executions.append(execution)

            issue = _provider_accounting_issue(execution)
            if issue == "provider_request_failed":
                stopped_reason = "request_failed"
                break
            if issue is not None:
                stopped_reason = "accounting_invalid"
                break
            if provider == "openalex":
                if audit.incremental_search_cost_usd is None:
                    stopped_reason = "cost_uninspectable"
                    break
                known_openalex_cost += audit.incremental_search_cost_usd

        cost_state, reported_cost = _provider_cost(provider_executions)
        summaries.append(
            Phase4ProviderSummary(
                provider=provider,
                attempted_case_count=len(provider_executions),
                successful_case_count=sum(
                    _case_succeeded(item) for item in provider_executions
                ),
                request_count=sum(
                    item.audit.outbound_attempt_count
                    for item in provider_executions
                ),
                cost_state=cost_state,
                reported_cost_usd=reported_cost,
                stopped_reason=stopped_reason,
            )
        )

    executions.sort(key=lambda item: _CASE_ORDER.index(item.case_id))
    successful_case_count = sum(_case_succeeded(item) for item in executions)
    overall_state = (
        "completed"
        if successful_case_count == 8
        and all(item.stopped_reason == "completed" for item in summaries)
        else "partial"
    )
    artifact = Phase4ExecutionArtifact(
        fixture_sha256=fixture_sha256,
        implementation_sha256=implementation_sha256,
        openalex_soft_stop_usd=openalex_soft_stop_usd,
        lens_cost_acknowledged=True,
        request_count=sum(
            item.audit.outbound_attempt_count for item in executions
        ),
        attempted_case_count=len(executions),
        successful_case_count=successful_case_count,
        overall_state=overall_state,
        provider_summaries=tuple(summaries),
        cases=tuple(executions),
    )
    _write_final_artifacts(output_dir, artifact)
    return artifact


def _stdout_json(value: object) -> str:
    # Artifacts retain UTF-8 provider text. Stdout is only a reversible
    # projection and must remain writable under a strict legacy Windows codec.
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--openalex-soft-stop-usd", type=float)
    parser.add_argument(
        "--acknowledge-lens-cost-uninspectable",
        action="store_true",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.execute_live:
        print(_stdout_json(protocol_dry_run()))
        return 0
    if args.output_dir is None or args.openalex_soft_stop_usd is None:
        raise SystemExit(
            "--execute-live requires --output-dir and --openalex-soft-stop-usd"
        )
    artifact = execute_live_study(
        output_dir=args.output_dir,
        openalex_soft_stop_usd=args.openalex_soft_stop_usd,
        acknowledge_lens_cost_uninspectable=(
            args.acknowledge_lens_cost_uninspectable
        ),
    )
    print(_stdout_json(artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
