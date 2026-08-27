"""Zero-network seams for the claim-scope v3 live harness."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

import openalex_claim_scope_live as live
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.openalex_claim_scope import OpenAlexClaimScopeCandidate
from academic_agent.tools.evidence_search import (
    ProviderResultRejection,
    ToolAdapterFailure,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from academic_agent.tools.openalex_claim_scope_search import (
    OpenAlexClaimScopeAdapterResponse,
)
from openalex_claim_scope_live import (
    OpenAlexClaimScopeLiveError,
    execute_live_study,
)
from openalex_claim_scope_unseen import PreparedClaimScopeCase, load_frozen_cases


def _accepted_candidate(
    case: PreparedClaimScopeCase,
    index: int,
) -> OpenAlexClaimScopeCandidate:
    required = [
        group.text_phrases[0] for group in case.spec.profile.required_groups
    ]
    supporting = [
        group.text_phrases[0]
        for group in case.spec.profile.supporting_groups[
            : case.spec.profile.minimum_supporting_groups
        ]
    ]
    return OpenAlexClaimScopeCandidate(
        evidence=ToolEvidenceCandidate(
            title=f"{' '.join(required)} controlled study",
            url=f"https://openalex.org/W{case.spec.case_id[1:]}00000001",
            publisher="OpenAlex zero-network claim-scope fixture",
            evidence_summary=(
                f"{' '.join(required + supporting)}. The study reports a direct "
                f"measurement for {case.spec.query}."
            ),
            summary_source="abstract",
            provider_result_index=index,
        ),
        aboutness=(),
    )


def _abstained_candidate(
    case: PreparedClaimScopeCase,
    index: int,
) -> OpenAlexClaimScopeCandidate:
    first_required = case.spec.profile.required_groups[0].text_phrases[0]
    supporting = [
        group.text_phrases[0]
        for group in case.spec.profile.supporting_groups
    ]
    return OpenAlexClaimScopeCandidate(
        evidence=ToolEvidenceCandidate(
            title=f"{first_required} broad application review",
            url=f"https://openalex.org/W{case.spec.case_id[1:]}00000002",
            publisher="OpenAlex zero-network claim-scope review",
            evidence_summary=(
                f"{first_required} {' '.join(supporting)}. This broad review "
                "intentionally omits the second required concept."
            ),
            summary_source="abstract",
            provider_result_index=index,
        ),
        aboutness=(),
    )


def _response(
    case: PreparedClaimScopeCase,
    call: ValidatedGapCall,
    *,
    reported_cost_usd: float,
    include_rejection: bool,
    only_abstained: bool,
    identity_mismatch: bool,
) -> OpenAlexClaimScopeAdapterResponse:
    candidates = (
        (_abstained_candidate(case, 0),)
        if only_abstained
        else (
            _accepted_candidate(case, 0),
            _abstained_candidate(case, 1),
        )
    )
    rejection_index = len(candidates)
    rejections = (
        (
            ProviderResultRejection(
                provider_result_index=rejection_index,
                code="provider_result_not_object",
                detail="zero-network fixture row is not an object",
            ),
        )
        if include_rejection
        else ()
    )
    idempotency_key = "0" * 64 if identity_mismatch else call.idempotency_key
    usage = ToolProviderUsage(
        provider="openalex",
        request_id=f"client-openalex-claim-scope-{call.idempotency_key[:12]}",
        request_id_source="client_generated",
        result_count=len(candidates) + len(rejections),
        cost_basis="reported_usd",
        reported_cost_usd=reported_cost_usd,
    )
    return OpenAlexClaimScopeAdapterResponse(
        idempotency_key=idempotency_key,
        candidates=candidates,
        provider_rejections=rejections,
        search_cost_usd=reported_cost_usd,
        provider_request_id=usage.request_id,
        provider_usage=usage,
    )


class RecordingFactory:
    """Injected adapter proving construction and request journal ordering."""

    def __init__(
        self,
        output_dir: Path,
        *,
        reported_cost_usd: float = 0.001,
        include_rejection: bool = False,
        fail: bool = False,
        invalid_response: bool = False,
        identity_mismatch: bool = False,
        only_abstained: bool = False,
    ) -> None:
        self.output_dir = output_dir
        self.reported_cost_usd = reported_cost_usd
        self.include_rejection = include_rejection
        self.fail = fail
        self.invalid_response = invalid_response
        self.identity_mismatch = identity_mismatch
        self.only_abstained = only_abstained
        self.constructed = 0
        self.calls: list[str] = []
        _, _, cases = load_frozen_cases()
        self.case_by_key = {
            case.plan.calls[0].idempotency_key: case for case in cases
        }

    def __call__(self):
        # The manifest is the durable authorization and identity boundary.  A
        # socket-capable adapter must never exist before these bytes do.
        assert (self.output_dir / "manifest.json").is_file()
        self.constructed += 1

        def run(call: ValidatedGapCall):
            case = self.case_by_key[call.idempotency_key]
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
            if self.invalid_response:
                return {
                    "tool": "academic_search",
                    "idempotency_key": call.idempotency_key,
                    "outbound_request_count": 1,
                }
            return _response(
                case,
                call,
                reported_cost_usd=self.reported_cost_usd,
                include_rejection=self.include_rejection,
                only_abstained=self.only_abstained,
                identity_mismatch=self.identity_mismatch,
            )

        return run


def _run(tmp_path: Path, *, monotonic_clock=None, **factory_options):
    output = tmp_path / "claim-scope-v3"
    factory = RecordingFactory(output, **factory_options)
    artifact = execute_live_study(
        output_dir=output,
        soft_stop_usd=0.01,
        acknowledge_anonymous_daily_budget=True,
        adapter_factory=factory,
        monotonic_clock=monotonic_clock,
    )
    return output, factory, artifact


def test_protocol_dry_run_locks_eight_cases_without_live_authority():
    result = live.protocol_dry_run()

    assert result["case_count"] == 8
    assert [case["case_id"] for case in result["cases"]] == [
        f"V{index:02d}" for index in range(1, 9)
    ]
    assert result["implementation_sha256"] == live.EXPECTED_IMPLEMENTATION_SHA256
    assert result["live_provider_requests_authorized"] is False
    assert result["real_network_calls_performed"] is False
    assert result["production_connected"] is False
    assert result["report_workflow_connected"] is False


def test_complete_run_reaches_decision_and_artifact_seams(tmp_path):
    output, factory, artifact = _run(tmp_path)

    assert factory.constructed == 1
    assert factory.calls == [f"V{index:02d}" for index in range(1, 9)]
    assert artifact.overall_state == "completed"
    assert artifact.request_count == 8
    assert artifact.successful_case_count == 8
    assert artifact.claim_scope_accepted_candidate_count == 8
    assert artifact.claim_scope_abstained_candidate_count == 8
    assert artifact.claim_scope_accepted_case_count == 8
    assert artifact.review_packet_eligibility == "eligible_for_source_lock"
    assert artifact.provider_summary.reported_cost_usd == pytest.approx(0.008)
    assert {path.name for path in (output / "case-executions").glob("*.json")} == {
        f"V{index:02d}.json" for index in range(1, 9)
    }
    assert (output / "artifact-index.json").is_file()


def test_request_latency_reaches_journal_csv_and_provider_summary(tmp_path):
    ticks = iter(float(value) for value in range(16))
    output, _, artifact = _run(
        tmp_path,
        monotonic_clock=lambda: next(ticks),
    )

    assert artifact.provider_summary.total_latency_ms == pytest.approx(8000.0)
    assert {case.latency_ms for case in artifact.cases} == {1000.0}
    first_journal = (
        output / "case-executions" / "V01.json"
    ).read_text(encoding="utf-8")
    assert '"latency_ms": 1000.0' in first_journal
    with (output / "candidates.csv").open(
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert {row["latency_ms"] for row in rows} == {"1000.0"}


def test_every_provider_row_and_decision_reaches_csv_boundary(tmp_path):
    output, _, _ = _run(tmp_path, include_rejection=True)

    with (output / "candidates.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with (output / "review.csv").open(encoding="utf-8", newline="") as handle:
        reviews = list(csv.DictReader(handle))

    assert len(rows) == 24
    assert len(reviews) == 8
    actions = [row["claim_scope_action"] for row in rows]
    assert actions.count("ACCEPT") == 8
    assert actions.count("ABSTAIN") == 8
    assert actions.count("NOT_EVALUATED") == 8
    assert all(
        row["missing_required_groups"] != "[]"
        for row in rows
        if row["claim_scope_action"] == "ABSTAIN"
    )
    assert all(
        row["required_match_provenance"] != "[]"
        for row in rows
        if row["claim_scope_action"] in {"ACCEPT", "ABSTAIN"}
    )
    assert {row["case_id"] for row in reviews} == {
        f"V{index:02d}" for index in range(1, 9)
    }
    assert all(row["candidate_sha256"] for row in reviews)


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

    with pytest.raises(OpenAlexClaimScopeLiveError):
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

    with pytest.raises(OpenAlexClaimScopeLiveError, match="refuses"):
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
        "openalex_claim_scope.py",
        "0" * 64,
    )

    with pytest.raises(OpenAlexClaimScopeLiveError, match="identity drifted"):
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

    assert factory.calls == ["V01"]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "soft_stop"
    assert artifact.review_packet_eligibility == "incomplete"
    assert (output / "case-executions" / "V01.json").is_file()
    assert not (output / "case-executions" / "V02.json").exists()


def test_provider_failure_remains_an_inspectable_partial_result(tmp_path):
    output, factory, artifact = _run(tmp_path, fail=True)

    assert factory.calls == ["V01"]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "request_failed"
    assert artifact.provider_summary.cost_state == "uninspectable"
    assert artifact.cases[0].failure_type == "provider_authentication"
    assert (output / "case-executions" / "V01.json").is_file()


def test_invalid_response_is_not_reported_as_a_provider_pass(tmp_path):
    output, factory, artifact = _run(tmp_path, invalid_response=True)

    assert factory.calls == ["V01"]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "accounting_invalid"
    assert artifact.cases[0].failure_type == "adapter_response_invalid"
    assert artifact.review_packet_eligibility == "incomplete"
    assert (output / "case-executions" / "V01.json").is_file()


def test_identity_mismatch_preserves_response_but_blocks_evaluation(tmp_path):
    output, factory, artifact = _run(tmp_path, identity_mismatch=True)

    assert factory.calls == ["V01"]
    assert artifact.provider_summary.stopped_reason == "accounting_invalid"
    assert artifact.cases[0].response is not None
    assert artifact.cases[0].evaluations == ()
    assert artifact.cases[0].failure_type == "adapter_identity_mismatch"
    with (output / "candidates.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["claim_scope_action"] for row in rows} == {"NOT_EVALUATED"}


def test_completed_mechanical_failure_is_not_a_source_value_pass(tmp_path):
    _, _, artifact = _run(tmp_path, only_abstained=True)

    assert artifact.overall_state == "completed"
    assert artifact.claim_scope_accepted_case_count == 0
    assert artifact.review_packet_eligibility == "mechanical_gate_failed"
    assert artifact.human_review_state == "not_prepared"
    assert artifact.source_value_state == "not_evaluated"


def test_artifacts_expose_no_key_or_unrelated_process_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("UNRELATED_PROCESS_SECRET", "must-not-reach-artifacts")
    output, _, _ = _run(tmp_path)

    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.rglob("*")
        if path.is_file()
    )
    assert "must-not-reach-artifacts" not in rendered
    assert "configured-secret" not in rendered
    assert '"api_key_used": false' in rendered


def test_production_worker_does_not_import_claim_scope_live_components():
    worker = Path("src/academic_agent/pipeline_worker.py").read_text(encoding="utf-8")

    assert "openalex_claim_scope_live" not in worker
    assert "openalex_claim_scope_unseen" not in worker
    assert "openalex_claim_scope_search" not in worker
    assert "openalex_claim_scope" not in worker
