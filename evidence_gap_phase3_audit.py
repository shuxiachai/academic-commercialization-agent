"""Frozen five-case live-provider compatibility audit for evidence-gap search.

Dry-run is the default and validates every collection and plan identity without
constructing a provider adapter. Live execution remains production-disconnected
and requires a separate command switch, environment credential, bounded soft
stop, and write-once output directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from academic_agent.evidence import EvidenceSource
from academic_agent.evidence_gap import (
    GapContext,
    GapPlanProposal,
    GapSearchIntent,
    ValidatedGapPlan,
    build_gap_context,
    source_collection_sha256,
    validate_gap_plan,
)
from academic_agent.evidence_gap_execution import (
    EvidenceGapExecutionAudit,
    execute_gap_plan,
)
from academic_agent.source_pipeline import AuthorityCoverage, SourceCollection
from academic_agent.tools.evidence_search import ReadOnlySearchAdapter
from academic_agent.tools.tavily_evidence_search import (
    TAVILY_BASIC_USD_PER_CREDIT,
    TavilyEvidenceSearchAdapter,
)


_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = _ROOT / "tests/fixtures/evidence_gap_phase3_manifest.json"
# This is the SHA-256 of the bytes stored by the manifest's first committed Git
# blob, not the pre-commit working-tree draft. A live pilot must bind to bytes
# another reviewer can reproduce from the repository.
EXPECTED_FIXTURE_SHA256 = (
    "4f216d5a7ad0f44db0b973a10087fc6075ac1a2dddddde0430faf62595ca377f"
)
_COLLECTED_AT = datetime(2026, 8, 25, tzinfo=UTC)
_ACCESSED_DATE = date(2026, 8, 25)
_EXPECTED_CASE_TOOLS = {
    "L01": "academic_search",
    "L02": "patent_search",
    "L03": "market_search",
    "L04": "authority_search",
    "L05": "authority_search",
}
_CSV_COLUMNS = (
    "case_id",
    "tool",
    "provider_request_id",
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
    "accepted_source_id",
    "title",
    "url",
    "relevant",
    "novel",
    "review_note",
)


class Phase3AuditError(ValueError):
    """Raised before a provider request when a frozen contract does not join."""


class Phase3CaseSpec(BaseModel):
    """Small deterministic recipe whose expanded identities are frozen."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^L0[1-5]$")
    tool: Literal[
        "academic_search",
        "patent_search",
        "market_search",
        "authority_search",
    ]
    topic: str = Field(min_length=20, max_length=300)
    gap_code: Literal["retrieval_domain_failed", "authority_category_missing"]
    gap_subject: Literal[
        "academic",
        "patent",
        "market",
        "regulatory",
        "clinical_registry",
    ]
    query: str = Field(min_length=20, max_length=500)
    result_limit: Literal[5] = 5
    expected_collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_gap_shape(self) -> "Phase3CaseSpec":
        if self.gap_code == "retrieval_domain_failed":
            if self.gap_subject not in {"academic", "patent", "market"}:
                raise ValueError("retrieval failure must name an evidence domain")
        elif self.gap_subject not in {"regulatory", "clinical_registry"}:
            raise ValueError("authority gap must name a supported authority category")
        return self


class Phase3Manifest(BaseModel):
    """Frozen pilot fixture with no credential or mutable runtime settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    provider: Literal["tavily"] = "tavily"
    usd_per_credit: Literal[0.008] = TAVILY_BASIC_USD_PER_CREDIT
    maximum_requests: Literal[5] = 5
    cases: tuple[Phase3CaseSpec, ...] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def _validate_frozen_case_set(self) -> "Phase3Manifest":
        case_ids = [case.case_id for case in self.cases]
        if case_ids != list(_EXPECTED_CASE_TOOLS):
            raise ValueError("phase-3 cases must remain ordered L01 through L05")
        if any(
            case.tool != _EXPECTED_CASE_TOOLS[case.case_id]
            for case in self.cases
        ):
            raise ValueError("phase-3 capability assignment drifted")
        return self


@dataclass(frozen=True)
class PreparedPhase3Case:
    spec: Phase3CaseSpec
    collection: SourceCollection
    context: GapContext
    plan: ValidatedGapPlan
    collection_sha256: str
    plan_sha256: str


class Phase3FrozenCaseArtifact(BaseModel):
    """Expanded frozen case persisted for independent identity inspection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: Phase3CaseSpec
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_collection: SourceCollection
    validated_plan: ValidatedGapPlan

    @model_validator(mode="after")
    def _validate_expanded_identities(self) -> "Phase3FrozenCaseArtifact":
        if (
            source_collection_sha256(self.source_collection)
            != self.collection_sha256
        ):
            raise ValueError("expanded source collection hash does not match")
        if _plan_sha256(self.validated_plan) != self.plan_sha256:
            raise ValueError("expanded validated plan hash does not match")
        return self


class Phase3ManifestArtifact(BaseModel):
    """Write-once expansion of the small fixture into complete frozen inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["phase3_frozen_provider_compatibility"] = (
        "phase3_frozen_provider_compatibility"
    )
    production_connected: Literal[False] = False
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: tuple[Phase3FrozenCaseArtifact, ...] = Field(
        min_length=5,
        max_length=5,
    )


class Phase3CaseExecution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^L0[1-5]$")
    collection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit: EvidenceGapExecutionAudit


class Phase3ExecutionArtifact(BaseModel):
    """Public live result; unknown and uninspectable are never clean passes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["phase3_live_provider_compatibility"] = (
        "phase3_live_provider_compatibility"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    provider: Literal["tavily"] = "tavily"
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    soft_stop_usd: float = Field(ge=0.04, le=0.05)
    usd_per_credit: Literal[0.008] = TAVILY_BASIC_USD_PER_CREDIT
    request_count: int = Field(ge=0, le=5)
    credit_state: Literal["known", "uninspectable"]
    credit_count: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    cost_state: Literal["known", "uninspectable"]
    conservative_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    completed_case_count: int = Field(ge=0, le=5)
    stopped_reason: Literal["completed", "soft_stop", "cost_uninspectable"]
    review_state: Literal["not_inspected"] = "not_inspected"
    cases: tuple[Phase3CaseExecution, ...] = Field(max_length=5)

    @model_validator(mode="after")
    def _validate_totals(self) -> "Phase3ExecutionArtifact":
        requests = sum(case.audit.outbound_attempt_count for case in self.cases)
        if requests != self.request_count:
            raise ValueError("request count must equal the executor audit total")
        if len(self.cases) != self.completed_case_count:
            raise ValueError("completed case count must equal persisted case audits")
        if self.credit_state == "known" and self.credit_count is None:
            raise ValueError("known credits require a numeric total")
        if self.credit_state == "uninspectable" and self.credit_count is not None:
            raise ValueError("uninspectable credits must be null")
        if self.cost_state == "known" and self.conservative_cost_usd is None:
            raise ValueError("known cost requires a numeric total")
        if self.cost_state == "uninspectable" and self.conservative_cost_usd is not None:
            raise ValueError("uninspectable cost must be null")
        return self


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _plan_sha256(plan: ValidatedGapPlan) -> str:
    return _sha256_bytes(plan.model_dump_json(exclude_none=False).encode("utf-8"))


def _seed_source(spec: Phase3CaseSpec) -> EvidenceSource:
    return EvidenceSource(
        source_id="A1",
        title=f"{spec.topic}: frozen baseline evidence source",
        url=f"https://doi.org/10.5555/phase3.{spec.case_id.casefold()}",
        publisher="Frozen Phase 3 Fixture",
        accessed_date=_ACCESSED_DATE,
        source_type="academic_paper",
        evidence_summary=(
            f"This frozen baseline source represents prior evidence for {spec.topic}. "
            "It exists only to make the synthetic collection schema-valid and "
            "does not answer the separately declared evidence gap."
        ),
        summary_source="abstract",
    )


def build_case(spec: Phase3CaseSpec) -> PreparedPhase3Case:
    """Expand one frozen recipe without clocks, network, models, or randomness."""

    authority_coverage = AuthorityCoverage()
    failed_domains: dict[str, str] = {}
    if spec.gap_code == "retrieval_domain_failed":
        failed_domains[spec.gap_subject] = (
            "frozen provider-compatibility retrieval failure"
        )
    else:
        authority_coverage = AuthorityCoverage(
            status="incomplete",
            required_categories=[spec.gap_subject],
            missing_categories=[spec.gap_subject],
        )
    collection = SourceCollection(
        topic=spec.topic,
        display_topic=spec.topic,
        output_language="English",
        weight_profile=(
            "biomedical" if spec.tool == "authority_search" else "industrial"
        ),
        collected_at=_COLLECTED_AT,
        academic_sources=[_seed_source(spec)],
        academic_queries=[spec.topic],
        patent_queries=[spec.topic],
        market_queries=[spec.topic],
        authority_coverage=authority_coverage,
        failed_domains=failed_domains,
    )
    context = build_gap_context(collection)
    trigger = next(
        (
            signal
            for signal in context.signals
            if signal.code == spec.gap_code and signal.subject == spec.gap_subject
        ),
        None,
    )
    if trigger is None:
        raise Phase3AuditError(f"{spec.case_id}: frozen gap signal was not produced")
    plan = validate_gap_plan(
        context,
        GapPlanProposal(
            decision="search",
            rationale=(
                "The frozen compatibility case authorizes one read-only provider "
                "request for its explicit evidence gap."
            ),
            calls=(
                GapSearchIntent(
                    tool=spec.tool,
                    query=spec.query,
                    trigger_ids=(trigger.signal_id,),
                    result_limit=spec.result_limit,
                ),
            ),
        ),
    )
    return PreparedPhase3Case(
        spec=spec,
        collection=collection,
        context=context,
        plan=plan,
        collection_sha256=source_collection_sha256(collection),
        plan_sha256=_plan_sha256(plan),
    )


def load_frozen_cases(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    *,
    enforce_hashes: bool = True,
) -> tuple[str, tuple[PreparedPhase3Case, ...]]:
    raw = manifest_path.read_bytes()
    fixture_sha256 = _sha256_bytes(raw)
    if enforce_hashes and fixture_sha256 != EXPECTED_FIXTURE_SHA256:
        # Check raw identity before parsing or expanding cases. Schema-valid
        # JSON with only whitespace changed is still a different frozen input.
        raise Phase3AuditError(
            "phase-3 fixture byte identity drifted: "
            f"expected {EXPECTED_FIXTURE_SHA256}, got {fixture_sha256}"
        )
    manifest = Phase3Manifest.model_validate_json(raw)
    prepared = tuple(build_case(spec) for spec in manifest.cases)
    if enforce_hashes:
        for case in prepared:
            if case.collection_sha256 != case.spec.expected_collection_sha256:
                raise Phase3AuditError(
                    f"{case.spec.case_id}: source collection identity drifted"
                )
            if case.plan_sha256 != case.spec.expected_plan_sha256:
                raise Phase3AuditError(
                    f"{case.spec.case_id}: validated plan identity drifted"
                )
    return fixture_sha256, prepared


def dry_run(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> dict:
    """Validate the complete frozen expansion while opening zero sockets."""

    fixture_sha256, cases = load_frozen_cases(manifest_path)
    return {
        "mode": "phase3_dry_run",
        "production_connected": False,
        "real_network_calls_performed": False,
        "fixture_sha256": fixture_sha256,
        "case_count": len(cases),
        "maximum_request_count": 5,
        "cases": [
            {
                "case_id": case.spec.case_id,
                "tool": case.spec.tool,
                "collection_sha256": case.collection_sha256,
                "plan_sha256": case.plan_sha256,
            }
            for case in cases
        ],
    }


def _credit_total(
    executions: list[Phase3CaseExecution],
) -> tuple[Literal["known", "uninspectable"], float | None]:
    credits: list[float] = []
    for execution in executions:
        for call in execution.audit.call_audits:
            if call.outbound_attempt_count == 0:
                continue
            if call.provider_usage is None:
                return "uninspectable", None
            credits.append(call.provider_usage.credit_count)
    return "known", sum(credits)


def _cost_total(
    executions: list[Phase3CaseExecution],
) -> tuple[Literal["known", "uninspectable"], float | None]:
    costs = [item.audit.incremental_search_cost_usd for item in executions]
    if any(cost is None for cost in costs):
        return "uninspectable", None
    return "known", sum(cost for cost in costs if cost is not None)


def execute_live_pilot(
    *,
    output_dir: Path,
    soft_stop_usd: float,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    adapter: ReadOnlySearchAdapter | None = None,
) -> Phase3ExecutionArtifact:
    """Execute at most one provider request per frozen case, never production."""

    if not 0.04 <= soft_stop_usd <= 0.05:
        raise Phase3AuditError("soft stop must be between USD 0.04 and USD 0.05")
    if output_dir.exists():
        raise FileExistsError(f"phase-3 output already exists: {output_dir}")
    fixture_sha256, prepared = load_frozen_cases(manifest_path)
    live_adapter = (
        adapter if adapter is not None else TavilyEvidenceSearchAdapter()
    )

    # Reserve the path only after every non-network prerequisite has passed.
    # A duplicate path therefore fails before adapter construction or billing.
    output_dir.mkdir(parents=True, exist_ok=False)
    executions: list[Phase3CaseExecution] = []
    known_cost = 0.0
    stopped_reason: Literal["completed", "soft_stop", "cost_uninspectable"] = (
        "completed"
    )
    for case in prepared:
        projected_cost = known_cost + TAVILY_BASIC_USD_PER_CREDIT
        if projected_cost > soft_stop_usd + 1e-12:
            stopped_reason = "soft_stop"
            break
        audit = execute_gap_plan(
            case.collection,
            context=case.context,
            plan=case.plan,
            adapters={case.spec.tool: live_adapter},
            trace_id=f"phase3-{case.spec.case_id.casefold()}-compatibility",
            outbound_attempt_limit=1,
        )
        executions.append(
            Phase3CaseExecution(
                case_id=case.spec.case_id,
                collection_sha256=case.collection_sha256,
                plan_sha256=case.plan_sha256,
                audit=audit,
            )
        )
        if audit.incremental_search_cost_usd is None:
            stopped_reason = "cost_uninspectable"
            break
        known_cost += audit.incremental_search_cost_usd

    credit_state, credit_count = _credit_total(executions)
    cost_state, conservative_cost = _cost_total(executions)
    artifact = Phase3ExecutionArtifact(
        fixture_sha256=fixture_sha256,
        soft_stop_usd=soft_stop_usd,
        request_count=sum(
            item.audit.outbound_attempt_count for item in executions
        ),
        credit_state=credit_state,
        credit_count=credit_count,
        cost_state=cost_state,
        conservative_cost_usd=conservative_cost,
        completed_case_count=len(executions),
        stopped_reason=stopped_reason,
        cases=tuple(executions),
    )
    write_artifacts(prepared, artifact, output_dir)
    return artifact


def _manifest_artifact(
    prepared: tuple[PreparedPhase3Case, ...],
    fixture_sha256: str,
) -> Phase3ManifestArtifact:
    return Phase3ManifestArtifact(
        fixture_sha256=fixture_sha256,
        cases=tuple(
            Phase3FrozenCaseArtifact(
                spec=case.spec,
                collection_sha256=case.collection_sha256,
                plan_sha256=case.plan_sha256,
                source_collection=case.collection,
                validated_plan=case.plan,
            )
            for case in prepared
        ),
    )


def _candidate_rows(
    artifact: Phase3ExecutionArtifact,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    reviews: list[dict[str, str]] = []
    for execution in artifact.cases:
        for call in execution.audit.call_audits:
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
                    # A call-level failure invalidates its entire delta. Keep
                    # the row inspectable without pretending it was accepted.
                    accepted_source_id = ""
                    local_disposition = "call_failed_before_registration"
                row = {
                    "case_id": execution.case_id,
                    "tool": call.tool,
                    "provider_request_id": (
                        call.provider_usage.request_id if call.provider_usage else ""
                    ),
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
                        "tool": call.tool,
                        "provider_request_id": (
                            call.provider_usage.request_id
                            if call.provider_usage
                            else ""
                        ),
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
    return rows, reviews


def _csv_text(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _write_new(path: Path, value: str) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(value)


def write_artifacts(
    prepared: tuple[PreparedPhase3Case, ...],
    artifact: Phase3ExecutionArtifact,
    output_dir: Path,
) -> None:
    """Write all public artifacts once; reruns need a new directory."""

    if not output_dir.is_dir():
        raise FileNotFoundError("phase-3 output directory must already be reserved")
    manifest = _manifest_artifact(prepared, artifact.fixture_sha256)
    rows, reviews = _candidate_rows(artifact)
    _write_new(
        output_dir / "manifest.json",
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _write_new(
        output_dir / "execution.json",
        artifact.model_dump_json(indent=2) + "\n",
    )
    _write_new(output_dir / "candidates.csv", _csv_text(_CSV_COLUMNS, rows))
    _write_new(output_dir / "review.csv", _csv_text(_REVIEW_COLUMNS, reviews))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--soft-stop-usd", type=float)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.execute_live:
        print(json.dumps(dry_run(args.manifest), indent=2, sort_keys=True))
        return 0
    if args.output_dir is None or args.soft_stop_usd is None:
        raise SystemExit(
            "--execute-live requires --output-dir and --soft-stop-usd"
        )
    artifact = execute_live_pilot(
        output_dir=args.output_dir,
        soft_stop_usd=args.soft_stop_usd,
        manifest_path=args.manifest,
    )
    print(artifact.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
