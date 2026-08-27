"""Zero-network seams for the anonymous OpenAlex value-study runner."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

import evidence_gap_openalex_live as openalex_live
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.evidence_search import (
    ProviderResultRejection,
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from evidence_gap_openalex_live import (
    AnonymousOpenAlexStudyError,
    execute_live_study,
)
from evidence_gap_phase4_audit import load_frozen_cases


def _candidate(call: ValidatedGapCall) -> ToolEvidenceCandidate:
    return ToolEvidenceCandidate(
        title=f"{call.query} controlled experimental study",
        url="https://openalex.org/W4200000999",
        publisher="OpenAlex test journal",
        evidence_summary=(
            f"Experimental evidence directly measures {call.query} under "
            "controlled conditions and reports comparative performance."
        ),
        summary_source="abstract",
        provider_result_index=0,
    )


def _response(
    call: ValidatedGapCall,
    *,
    reported_cost_usd: float,
    include_rejection: bool,
) -> ToolAdapterResponse:
    rejections = (
        (
            ProviderResultRejection(
                provider_result_index=1,
                code="provider_result_not_object",
                detail="fixture row is not an object",
            ),
        )
        if include_rejection
        else ()
    )
    usage = ToolProviderUsage(
        provider="openalex",
        request_id=f"client-openalex-{call.idempotency_key[:12]}",
        request_id_source="client_generated",
        result_count=1 + len(rejections),
        cost_basis="reported_usd",
        reported_cost_usd=reported_cost_usd,
    )
    return ToolAdapterResponse(
        tool=call.tool,
        idempotency_key=call.idempotency_key,
        candidates=(_candidate(call),),
        provider_rejections=rejections,
        search_cost_usd=reported_cost_usd,
        provider_request_id=usage.request_id,
        provider_usage=usage,
    )


class RecordingFactory:
    """Injected provider seam that proves ordering without opening a socket."""

    def __init__(
        self,
        output_dir: Path,
        *,
        reported_cost_usd: float = 0.001,
        include_rejection: bool = False,
        fail: bool = False,
    ) -> None:
        self.output_dir = output_dir
        self.reported_cost_usd = reported_cost_usd
        self.include_rejection = include_rejection
        self.fail = fail
        self.constructed = 0
        self.calls: list[str] = []
        _, cases = load_frozen_cases()
        self.case_by_key = {
            case.plan.calls[0].idempotency_key: case.spec.case_id for case in cases
        }

    def __call__(self):
        self.constructed += 1

        def run(call: ValidatedGapCall) -> ToolAdapterResponse:
            case_id = self.case_by_key[call.idempotency_key]
            assert (self.output_dir / "manifest.json").is_file()
            for previous_case in self.calls:
                assert (
                    self.output_dir / "case-executions" / f"{previous_case}.json"
                ).is_file()
            self.calls.append(case_id)
            if self.fail:
                raise ToolAdapterFailure(
                    "offline injected provider failure",
                    retryable=False,
                    failure_type="provider_authentication",
                    search_cost_usd=None,
                )
            return _response(
                call,
                reported_cost_usd=self.reported_cost_usd,
                include_rejection=self.include_rejection,
            )

        return run


def _run(tmp_path: Path, **factory_options):
    output = tmp_path / "anonymous-openalex"
    factory = RecordingFactory(output, **factory_options)
    artifact = execute_live_study(
        output_dir=output,
        soft_stop_usd=0.01,
        acknowledge_anonymous_daily_budget=True,
        adapter_factory=factory,
    )
    return output, factory, artifact


def test_protocol_dry_run_locks_four_cases_without_live_authority():
    result = openalex_live.protocol_dry_run()

    assert result["case_count"] == 4
    assert [case["case_id"] for case in result["cases"]] == [
        "D01",
        "D02",
        "D03",
        "D04",
    ]
    assert result["implementation_sha256"] == (
        openalex_live.EXPECTED_IMPLEMENTATION_SHA256
    )
    assert result["api_key_used"] is False
    assert result["live_provider_requests_authorized"] is False
    assert result["real_network_calls_performed"] is False


def test_complete_run_reaches_journal_accounting_and_artifact_seams(tmp_path):
    output, factory, artifact = _run(tmp_path)

    assert factory.constructed == 1
    assert factory.calls == ["D01", "D02", "D03", "D04"]
    assert artifact.overall_state == "completed"
    assert artifact.request_count == 4
    assert artifact.successful_case_count == 4
    assert artifact.provider_summary.access_mode == "anonymous_no_key"
    assert artifact.provider_summary.reported_cost_usd == pytest.approx(0.004)
    assert {path.name for path in (output / "case-executions").glob("*.json")} == {
        "D01.json",
        "D02.json",
        "D03.json",
        "D04.json",
    }
    assert (output / "artifact-index.json").is_file()


def test_every_provider_row_and_accepted_candidate_reaches_csv_boundary(tmp_path):
    output, _, _ = _run(tmp_path, include_rejection=True)

    with (output / "candidates.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with (output / "review.csv").open(encoding="utf-8", newline="") as handle:
        reviews = list(csv.DictReader(handle))

    assert len(rows) == 8
    assert len(reviews) == 4
    assert [row["adapter_disposition"] for row in rows].count("candidate") == 4
    assert [row["adapter_disposition"] for row in rows].count(
        "provider_rejected"
    ) == 4
    for case_id in ("D01", "D02", "D03", "D04"):
        case_rows = [row for row in rows if row["case_id"] == case_id]
        assert [row["provider_result_index"] for row in case_rows] == ["0", "1"]
    assert {row["case_id"] for row in reviews} == {"D01", "D02", "D03", "D04"}
    assert all(row["accepted_source_id"] for row in reviews)


@pytest.mark.parametrize(
    ("soft_stop", "acknowledge"),
    [(0.0, True), (0.0101, True), (0.01, False)],
)
def test_invalid_authorization_fails_before_adapter_and_output(
    tmp_path,
    soft_stop,
    acknowledge,
):
    output = tmp_path / "forbidden"
    factory = RecordingFactory(output)

    with pytest.raises(AnonymousOpenAlexStudyError):
        execute_live_study(
            output_dir=output,
            soft_stop_usd=soft_stop,
            acknowledge_anonymous_daily_budget=acknowledge,
            adapter_factory=factory,
        )

    assert factory.constructed == 0
    assert not output.exists()


def test_configured_key_fails_before_adapter_and_output(tmp_path, monkeypatch):
    output = tmp_path / "configured-key"
    factory = RecordingFactory(output)
    monkeypatch.setenv("OPENALEX_API_KEY", "configured-secret")

    with pytest.raises(AnonymousOpenAlexStudyError, match="refuses to start"):
        execute_live_study(
            output_dir=output,
            soft_stop_usd=0.01,
            acknowledge_anonymous_daily_budget=True,
            adapter_factory=factory,
        )

    assert factory.constructed == 0
    assert not output.exists()


def test_existing_output_fails_before_adapter_construction(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    factory = RecordingFactory(output)

    with pytest.raises(FileExistsError, match="already exists"):
        execute_live_study(
            output_dir=output,
            soft_stop_usd=0.01,
            acknowledge_anonymous_daily_budget=True,
            adapter_factory=factory,
        )

    assert factory.constructed == 0


def test_implementation_hash_drift_fails_before_factory_and_output(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "hash-drift"
    factory = RecordingFactory(output)
    monkeypatch.setitem(
        openalex_live.EXPECTED_IMPLEMENTATION_SHA256,
        "anonymous_openalex_search.py",
        "0" * 64,
    )

    with pytest.raises(AnonymousOpenAlexStudyError, match="identity drifted"):
        execute_live_study(
            output_dir=output,
            soft_stop_usd=0.01,
            acknowledge_anonymous_daily_budget=True,
            adapter_factory=factory,
        )

    assert factory.constructed == 0
    assert not output.exists()


def test_soft_stop_commits_the_attempted_case_before_stopping(tmp_path):
    output, factory, artifact = _run(tmp_path, reported_cost_usd=0.01)

    assert factory.calls == ["D01"]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "soft_stop"
    assert artifact.provider_summary.reported_cost_usd == pytest.approx(0.01)
    assert (output / "case-executions" / "D01.json").is_file()
    assert not (output / "case-executions" / "D02.json").exists()


def test_provider_failure_remains_an_inspectable_partial_result(tmp_path):
    output, factory, artifact = _run(tmp_path, fail=True)

    assert factory.calls == ["D01"]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "request_failed"
    assert artifact.provider_summary.cost_state == "uninspectable"
    assert (output / "case-executions" / "D01.json").is_file()


def test_artifacts_expose_no_key_or_local_sentinel(tmp_path, monkeypatch):
    monkeypatch.setenv("UNRELATED_PROCESS_SECRET", "must-not-reach-artifacts")
    output, _, _ = _run(tmp_path)

    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.rglob("*")
        if path.is_file()
    )
    assert "must-not-reach-artifacts" not in rendered
    assert "anonymous-openalex-key-must-not-reach-network" not in rendered
    assert '"api_key_used": false' in rendered


def test_production_worker_does_not_import_the_anonymous_study():
    worker = Path("src/academic_agent/pipeline_worker.py").read_text(encoding="utf-8")

    assert "anonymous_openalex_search" not in worker
    assert "evidence_gap_openalex_live" not in worker
