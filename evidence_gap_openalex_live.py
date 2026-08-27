"""Frozen, anonymous OpenAlex value study disconnected from production.

Dry-run is the default and opens zero sockets.  Live execution requires an
explicit switch, a fresh output directory, a small provider-reported soft stop,
and acknowledgement that the request consumes OpenAlex's anonymous daily
budget even though no payment method or API key is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, model_validator

from academic_agent.evidence_gap_execution import (
    EvidenceGapExecutionAudit,
    ReadOnlySearchAdapter,
    execute_gap_plan,
)
from academic_agent.tools.anonymous_openalex_search import (
    AnonymousOpenAlexEvidenceSearchAdapter,
)
from evidence_gap_phase4_audit import (
    EXPECTED_FIXTURE_SHA256,
    PreparedPhase4Case,
    load_frozen_cases,
)
from evidence_gap_phase4_live import (
    Phase4CaseExecution,
    Phase4FrozenCaseArtifact,
    _CANDIDATE_COLUMNS,
    _REVIEW_COLUMNS,
    _candidate_rows,
    _case_succeeded,
    _csv_text,
    _json_text,
    _provider_accounting_issue,
    _write_case_journal,
    _write_new,
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
    "evidence_gap_phase4_audit.py": _ROOT / "evidence_gap_phase4_audit.py",
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
    "evidence_gap_phase4_audit.py": (
        "e70c2e015ffc5a01b1f9e35634dd65b9a37062bc561b9deaff8fbfa3bfb09477"
    ),
}
MAXIMUM_REQUESTS = 4
MAXIMUM_SOFT_STOP_USD = 0.01
ANONYMOUS_DAILY_BUDGET_USD = 0.10
_CASE_ORDER = ("D01", "D02", "D03", "D04")
_AGGREGATE_SOURCE_FILES = (
    "manifest.json",
    "execution.json",
    "candidates.csv",
    "review.csv",
)


AdapterFactory = Callable[[], ReadOnlySearchAdapter]
StopReason = Literal[
    "completed",
    "soft_stop",
    "cost_uninspectable",
    "request_failed",
    "accounting_invalid",
]


class AnonymousOpenAlexStudyError(ValueError):
    """Raised before provider work when an anonymous-study boundary fails."""


class AnonymousOpenAlexManifestArtifact(BaseModel):
    """Complete deterministic input persisted before the first request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["anonymous_openalex_value_study"] = (
        "anonymous_openalex_value_study"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    api_key_used: Literal[False] = False
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    maximum_requests: Literal[4] = MAXIMUM_REQUESTS
    anonymous_daily_budget_usd: Literal[0.1] = ANONYMOUS_DAILY_BUDGET_USD
    soft_stop_usd: float = Field(gt=0.0, le=MAXIMUM_SOFT_STOP_USD)
    cases: tuple[Phase4FrozenCaseArtifact, ...] = Field(
        min_length=4,
        max_length=4,
    )

    @model_validator(mode="after")
    def _validate_frozen_contract(self) -> "AnonymousOpenAlexManifestArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("anonymous study fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("anonymous study implementation identities do not match")
        if [case.spec.case_id for case in self.cases] != list(_CASE_ORDER):
            raise ValueError("anonymous study cases must remain ordered D01 through D04")
        if any(
            case.spec.provider != "openalex" or case.spec.tool != "academic_search"
            for case in self.cases
        ):
            raise ValueError("anonymous study may contain only OpenAlex academic cases")
        return self


class AnonymousOpenAlexProviderSummary(BaseModel):
    """Provider accounting where silence cannot masquerade as completion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openalex"] = "openalex"
    access_mode: Literal["anonymous_no_key"] = "anonymous_no_key"
    authorized_case_count: Literal[4] = MAXIMUM_REQUESTS
    attempted_case_count: int = Field(ge=0, le=4)
    successful_case_count: int = Field(ge=0, le=4)
    request_count: int = Field(ge=0, le=4)
    cost_state: Literal["known", "uninspectable", "not_observed"]
    reported_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    stopped_reason: StopReason

    @model_validator(mode="after")
    def _validate_accounting(self) -> "AnonymousOpenAlexProviderSummary":
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


class AnonymousOpenAlexExecutionArtifact(BaseModel):
    """Final write-once state; a partial study is never projected as a pass."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["anonymous_openalex_value_study"] = (
        "anonymous_openalex_value_study"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    api_key_used: Literal[False] = False
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    maximum_requests: Literal[4] = MAXIMUM_REQUESTS
    anonymous_daily_budget_usd: Literal[0.1] = ANONYMOUS_DAILY_BUDGET_USD
    soft_stop_usd: float = Field(gt=0.0, le=MAXIMUM_SOFT_STOP_USD)
    request_count: int = Field(ge=0, le=4)
    attempted_case_count: int = Field(ge=0, le=4)
    successful_case_count: int = Field(ge=0, le=4)
    overall_state: Literal["completed", "partial"]
    source_lock_state: Literal["not_created"] = "not_created"
    human_review_state: Literal["not_prepared"] = "not_prepared"
    source_value_state: Literal["not_evaluated"] = "not_evaluated"
    provider_summary: AnonymousOpenAlexProviderSummary
    cases: tuple[Phase4CaseExecution, ...] = Field(max_length=4)

    @model_validator(mode="after")
    def _validate_totals(self) -> "AnonymousOpenAlexExecutionArtifact":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("execution fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("execution implementation identities do not match")
        case_ids = [case.case_id for case in self.cases]
        if case_ids != list(_CASE_ORDER[: len(case_ids)]):
            raise ValueError("case executions must preserve the frozen prefix")
        if any(case.provider != "openalex" for case in self.cases):
            raise ValueError("anonymous execution may contain only OpenAlex cases")

        request_count = sum(case.audit.outbound_attempt_count for case in self.cases)
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
        if (self.overall_state == "completed") != (
            self.successful_case_count == MAXIMUM_REQUESTS
            and self.provider_summary.stopped_reason == "completed"
        ):
            raise ValueError("overall state does not match provider completion")
        return self


class _NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects because one adapter invocation authorizes one request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del req, fp, code, msg, headers, newurl
        return None


class _OneRequestTransport:
    """Concrete live transport with neither redirect following nor retry."""

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
        raise AnonymousOpenAlexStudyError(
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
        raise AnonymousOpenAlexStudyError(
            f"anonymous OpenAlex implementation identity drifted: {drift}"
        )
    return observed


def _openalex_cases() -> tuple[str, tuple[PreparedPhase4Case, ...]]:
    fixture_sha256, all_cases = load_frozen_cases()
    cases = tuple(case for case in all_cases if case.spec.provider == "openalex")
    if [case.spec.case_id for case in cases] != list(_CASE_ORDER):
        raise AnonymousOpenAlexStudyError(
            "frozen OpenAlex case selection drifted from D01 through D04"
        )
    return fixture_sha256, cases


def protocol_dry_run() -> dict[str, Any]:
    """Validate every frozen identity while constructing no network object."""

    fixture_sha256, cases = _openalex_cases()
    return {
        "mode": "anonymous_openalex_value_study_dry_run",
        "production_connected": False,
        "report_workflow_connected": False,
        "api_key_used": False,
        "real_network_calls_performed": False,
        "fixture_sha256": fixture_sha256,
        "implementation_sha256": verify_frozen_implementation(),
        "case_count": len(cases),
        "maximum_request_count": MAXIMUM_REQUESTS,
        "anonymous_daily_budget_usd": ANONYMOUS_DAILY_BUDGET_USD,
        "live_provider_requests_authorized": False,
        "cases": [
            {
                "case_id": case.spec.case_id,
                "provider": case.spec.provider,
                "tool": case.spec.tool,
                "collection_sha256": case.collection_sha256,
                "plan_sha256": case.plan_sha256,
                "idempotency_key": case.plan.calls[0].idempotency_key,
            }
            for case in cases
        ],
    }


def _manifest_artifact(
    cases: tuple[PreparedPhase4Case, ...],
    fixture_sha256: str,
    implementation_sha256: dict[str, str],
    soft_stop_usd: float,
) -> AnonymousOpenAlexManifestArtifact:
    return AnonymousOpenAlexManifestArtifact(
        fixture_sha256=fixture_sha256,
        implementation_sha256=implementation_sha256,
        soft_stop_usd=soft_stop_usd,
        cases=tuple(
            Phase4FrozenCaseArtifact(
                spec=case.spec,
                collection_sha256=case.collection_sha256,
                plan_sha256=case.plan_sha256,
                source_collection=case.collection,
                validated_plan=case.plan,
            )
            for case in cases
        ),
    )


def _provider_cost(
    executions: list[Phase4CaseExecution],
) -> tuple[Literal["known", "uninspectable", "not_observed"], float | None]:
    if not executions:
        return "not_observed", None
    values = [item.audit.incremental_search_cost_usd for item in executions]
    if any(value is None for value in values):
        return "uninspectable", None
    return "known", sum(value for value in values if value is not None)


def _write_final_artifacts(
    output_dir: Path,
    artifact: AnonymousOpenAlexExecutionArtifact,
) -> None:
    # Reuse the Phase 4 row projection so later human review sees exactly the
    # same candidate, rejection, accepted-source, cost and trace seams.  A new
    # study must not gain apparent quality from dropping difficult provider rows.
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
                "mode": "anonymous_openalex_artifact_index",
                "production_connected": False,
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
) -> AnonymousOpenAlexExecutionArtifact:
    """Run four frozen academic cases under a provider-reported soft stop."""

    if not 0.0 < soft_stop_usd <= MAXIMUM_SOFT_STOP_USD:
        raise AnonymousOpenAlexStudyError(
            "anonymous OpenAlex soft stop must be greater than zero and at most USD 0.01"
        )
    if not acknowledge_anonymous_daily_budget:
        raise AnonymousOpenAlexStudyError(
            "anonymous OpenAlex execution requires explicit daily-budget acknowledgement"
        )
    if (os.getenv("OPENALEX_API_KEY") or "").strip():
        raise AnonymousOpenAlexStudyError(
            "anonymous study refuses to start while OPENALEX_API_KEY is configured"
        )
    if output_dir.exists():
        raise FileExistsError(f"anonymous OpenAlex output already exists: {output_dir}")

    fixture_sha256, cases = _openalex_cases()
    implementation_sha256 = verify_frozen_implementation()
    # Reserve and identify the experiment before constructing the adapter.  A
    # later crash leaves an inspectable manifest, while path reuse always fails
    # before another request can spend even anonymous provider budget.
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = _manifest_artifact(
        cases,
        fixture_sha256,
        implementation_sha256,
        soft_stop_usd,
    )
    _write_new(output_dir / "manifest.json", _json_text(manifest))
    adapter = (
        adapter_factory()
        if adapter_factory is not None
        else AnonymousOpenAlexEvidenceSearchAdapter(transport=_OneRequestTransport())
    )

    executions: list[Phase4CaseExecution] = []
    known_cost = 0.0
    stopped_reason: StopReason = "completed"
    for case in cases:
        if known_cost + 1e-12 >= soft_stop_usd:
            stopped_reason = "soft_stop"
            break
        audit: EvidenceGapExecutionAudit = execute_gap_plan(
            case.collection,
            context=case.context,
            plan=case.plan,
            adapters={"academic_search": adapter},
            trace_id=f"anonymous-openalex-{case.spec.case_id.casefold()}-value",
            outbound_attempt_limit=1,
        )
        execution = Phase4CaseExecution(
            case_id=case.spec.case_id,
            provider="openalex",
            collection_sha256=case.collection_sha256,
            plan_sha256=case.plan_sha256,
            audit=audit,
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
    provider_summary = AnonymousOpenAlexProviderSummary(
        attempted_case_count=len(executions),
        successful_case_count=successful_case_count,
        request_count=sum(item.audit.outbound_attempt_count for item in executions),
        cost_state=cost_state,
        reported_cost_usd=reported_cost,
        stopped_reason=stopped_reason,
    )
    artifact = AnonymousOpenAlexExecutionArtifact(
        fixture_sha256=fixture_sha256,
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
