"""Zero-network seams for the precision-v2 unseen live harness."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

import openalex_precision_live as live
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.evidence_search import (
    ProviderResultRejection,
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from openalex_precision_live import (
    OpenAlexPrecisionLiveError,
    execute_live_study,
)
from openalex_precision_unseen import PreparedUnseenCase, load_frozen_cases


def _accepted_candidate(
    case: PreparedUnseenCase,
    index: int,
) -> ToolEvidenceCandidate:
    required = [group.phrases[0] for group in case.spec.profile.required_groups]
    supporting = [
        group.phrases[0]
        for group in case.spec.profile.supporting_groups[
            : case.spec.profile.minimum_supporting_groups
        ]
    ]
    return ToolEvidenceCandidate(
        title=f"{' '.join(required)} controlled study",
        url=f"https://openalex.org/W{case.spec.case_id[1:]}00000001",
        publisher="OpenAlex zero-network fixture journal",
        evidence_summary=(
            f"{' '.join(required + supporting)}. The study reports a direct "
            f"measurement for {case.spec.query}."
        ),
        summary_source="abstract",
        provider_result_index=index,
    )


def _abstained_candidate(
    case: PreparedUnseenCase,
    index: int,
) -> ToolEvidenceCandidate:
    first_required = case.spec.profile.required_groups[0].phrases[0]
    # U05's legacy quarantine derives its hard domain terms entirely from the
    # application phrase.  Keep the neutral "delivery" anchor so this fixture
    # reaches the precision seam while still omitting every phrase in the
    # second required group (measles vaccine).
    domain_anchor = " delivery" if case.spec.case_id == "U05" else ""
    supporting = [
        group.phrases[0] for group in case.spec.profile.supporting_groups
    ]
    return ToolEvidenceCandidate(
        title=f"{first_required} broad application review",
        url=f"https://openalex.org/W{case.spec.case_id[1:]}00000002",
        publisher="OpenAlex zero-network fixture review",
        evidence_summary=(
            f"{first_required}{domain_anchor} {' '.join(supporting)}. This broad review "
            "intentionally omits the second required concept."
        ),
        summary_source="abstract",
        provider_result_index=index,
    )


def _response(
    case: PreparedUnseenCase,
    call: ValidatedGapCall,
    *,
    reported_cost_usd: float,
    include_rejection: bool,
) -> ToolAdapterResponse:
    rejections = (
        (
            ProviderResultRejection(
                provider_result_index=2,
                code="provider_result_not_object",
                detail="zero-network fixture row is not an object",
            ),
        )
        if include_rejection
        else ()
    )
    candidates = (
        _accepted_candidate(case, 0),
        _abstained_candidate(case, 1),
    )
    usage = ToolProviderUsage(
        provider="openalex",
        request_id=f"client-openalex-{call.idempotency_key[:12]}",
        request_id_source="client_generated",
        result_count=len(candidates) + len(rejections),
        cost_basis="reported_usd",
        reported_cost_usd=reported_cost_usd,
    )
    return ToolAdapterResponse(
        tool=call.tool,
        idempotency_key=call.idempotency_key,
        candidates=candidates,
        provider_rejections=rejections,
        search_cost_usd=reported_cost_usd,
        provider_request_id=usage.request_id,
        provider_usage=usage,
    )


class RecordingFactory:
    """Injected adapter proving request order without constructing a socket."""

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
        _, _, _, cases = load_frozen_cases()
        self.case_by_key = {
            case.plan.calls[0].idempotency_key: case for case in cases
        }

    def __call__(self):
        self.constructed += 1

        def run(call: ValidatedGapCall) -> ToolAdapterResponse:
            case = self.case_by_key[call.idempotency_key]
            assert (self.output_dir / "manifest.json").is_file()
            for previous_case in self.calls:
                assert (
                    self.output_dir
                    / "case-executions"
                    / f"{previous_case}.json"
                ).is_file()
            self.calls.append(case.spec.case_id)
            if self.fail:
                raise ToolAdapterFailure(
                    "offline injected provider failure",
                    retryable=False,
                    failure_type="provider_authentication",
                    search_cost_usd=None,
                )
            return _response(
                case,
                call,
                reported_cost_usd=self.reported_cost_usd,
                include_rejection=self.include_rejection,
            )

        return run


def _run(tmp_path: Path, **factory_options):
    output = tmp_path / "precision-v2-unseen"
    factory = RecordingFactory(output, **factory_options)
    artifact = execute_live_study(
        output_dir=output,
        soft_stop_usd=0.01,
        acknowledge_anonymous_daily_budget=True,
        adapter_factory=factory,
    )
    return output, factory, artifact


def test_protocol_dry_run_locks_eight_cases_without_live_authority():
    result = live.protocol_dry_run()

    assert result["case_count"] == 8
    assert [case["case_id"] for case in result["cases"]] == [
        f"U{index:02d}" for index in range(1, 9)
    ]
    assert result["implementation_sha256"] == live.EXPECTED_IMPLEMENTATION_SHA256
    assert result["live_provider_requests_authorized"] is False
    assert result["real_network_calls_performed"] is False
    assert result["production_connected"] is False
    assert result["report_workflow_connected"] is False


def test_complete_run_reaches_precision_and_artifact_seams(tmp_path):
    output, factory, artifact = _run(tmp_path)

    assert factory.constructed == 1
    assert factory.calls == [f"U{index:02d}" for index in range(1, 9)]
    assert artifact.overall_state == "completed"
    assert artifact.request_count == 8
    assert artifact.successful_case_count == 8
    assert artifact.precision_accepted_candidate_count == 8
    assert artifact.precision_abstained_candidate_count == 8
    assert artifact.precision_accepted_case_count == 8
    assert artifact.provider_summary.reported_cost_usd == pytest.approx(0.008)
    assert {path.name for path in (output / "case-executions").glob("*.json")} == {
        f"U{index:02d}.json" for index in range(1, 9)
    }
    assert (output / "artifact-index.json").is_file()


def test_every_provider_row_and_precision_decision_reaches_csv_boundary(tmp_path):
    output, _, _ = _run(tmp_path, include_rejection=True)

    with (output / "candidates.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with (output / "review.csv").open(encoding="utf-8", newline="") as handle:
        reviews = list(csv.DictReader(handle))

    assert len(rows) == 24
    assert len(reviews) == 8
    assert [row["precision_action"] for row in rows].count("ACCEPT") == 8
    assert [row["precision_action"] for row in rows].count("ABSTAIN") == 8
    assert [row["precision_action"] for row in rows].count("NOT_EVALUATED") == 8
    assert all(row["missing_required_groups"] != "[]" for row in rows if row["precision_action"] == "ABSTAIN")
    assert {row["case_id"] for row in reviews} == {
        f"U{index:02d}" for index in range(1, 9)
    }
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

    with pytest.raises(OpenAlexPrecisionLiveError):
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

    with pytest.raises(OpenAlexPrecisionLiveError, match="refuses"):
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
        live.EXPECTED_IMPLEMENTATION_SHA256,
        "openalex_precision.py",
        "0" * 64,
    )

    with pytest.raises(OpenAlexPrecisionLiveError, match="identity drifted"):
        execute_live_study(
            output_dir=output,
            soft_stop_usd=0.01,
            acknowledge_anonymous_daily_budget=True,
            adapter_factory=factory,
        )

    assert factory.constructed == 0
    assert not output.exists()


def test_soft_stop_commits_first_case_before_stopping(tmp_path):
    output, factory, artifact = _run(tmp_path, reported_cost_usd=0.01)

    assert factory.calls == ["U01"]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "soft_stop"
    assert (output / "case-executions" / "U01.json").is_file()
    assert not (output / "case-executions" / "U02.json").exists()


def test_provider_failure_remains_an_inspectable_partial_result(tmp_path):
    output, factory, artifact = _run(tmp_path, fail=True)

    assert factory.calls == ["U01"]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "request_failed"
    assert artifact.provider_summary.cost_state == "uninspectable"
    assert (output / "case-executions" / "U01.json").is_file()


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


def test_production_worker_does_not_import_precision_unseen_components():
    worker = Path("src/academic_agent/pipeline_worker.py").read_text(encoding="utf-8")

    assert "openalex_precision_live" not in worker
    assert "openalex_precision_unseen" not in worker
    assert "openalex_precision" not in worker
