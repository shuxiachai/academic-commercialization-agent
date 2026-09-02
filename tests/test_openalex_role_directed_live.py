"""Zero-network seams for the frozen role-directed retrieval v7 live runner."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import socket

import pytest

import openalex_role_directed_live as live
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.evidence_search import (
    ProviderResultRejection,
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from openalex_role_directed_unseen import (
    PreparedRoleDirectedCase,
    RetrievalLaneId,
    load_frozen_cases,
)


def _work_id(case_id: str, suffix: int) -> str:
    return f"https://openalex.org/W{int(case_id[2:]):02d}{suffix:06d}"


def _candidate(
    case_id: str,
    lane_id: RetrievalLaneId,
    index: int,
    *,
    shared: bool,
) -> ToolEvidenceCandidate:
    if shared:
        # Deliberately use a different OpenAlex record in the second lane.  The
        # shared DOI, rather than a coincident URL, must own this merge.
        suffix = 1 if lane_id == "technology_scope" else 9
        doi = f"10.5555/{case_id.casefold()}.shared"
        label = "shared DOI candidate"
    else:
        suffix = 2 if lane_id == "technology_scope" else 3
        doi = None
        label = f"{lane_id} unique candidate"
    return ToolEvidenceCandidate(
        title=f"{case_id} {label} for role-directed retrieval",
        url=_work_id(case_id, suffix),
        doi=doi,
        publisher="OpenAlex zero-network role-directed fixture",
        evidence_summary=(
            f"This synthetic {lane_id} abstract for {case_id} preserves enough "
            "content to exercise portfolio persistence without asserting source value."
        ),
        summary_source="abstract",
        citation_count=index + 1,
        provider_result_index=index,
    )


def _response(
    case: PreparedRoleDirectedCase,
    lane_id: RetrievalLaneId,
    call: ValidatedGapCall,
    *,
    reported_cost_usd: float,
    include_rejection: bool,
    identity_mismatch: bool,
) -> ToolAdapterResponse:
    candidates = (
        _candidate(case.spec.case_id, lane_id, 0, shared=True),
        _candidate(case.spec.case_id, lane_id, 1, shared=False),
    )
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
    idempotency_key = "0" * 64 if identity_mismatch else call.idempotency_key
    usage = ToolProviderUsage(
        provider="openalex",
        request_id=f"client-v7-{call.idempotency_key[:16]}",
        request_id_source="client_generated",
        result_count=len(candidates) + len(rejections),
        cost_basis="reported_usd",
        reported_cost_usd=reported_cost_usd,
    )
    return ToolAdapterResponse(
        tool="academic_search",
        idempotency_key=idempotency_key,
        candidates=candidates,
        provider_rejections=rejections,
        search_cost_usd=reported_cost_usd,
        provider_request_id=usage.request_id,
        provider_usage=usage,
    )


class RecordingFactory:
    """Injected adapter proving construction, request, and portfolio ordering."""

    def __init__(
        self,
        output_dir: Path,
        *,
        reported_cost_usd: float = 0.001,
        include_rejection: bool = False,
        fail_at: int | None = None,
        invalid_at: int | None = None,
        identity_mismatch_at: int | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.reported_cost_usd = reported_cost_usd
        self.include_rejection = include_rejection
        self.fail_at = fail_at
        self.invalid_at = invalid_at
        self.identity_mismatch_at = identity_mismatch_at
        self.constructed = 0
        self.calls: list[tuple[str, RetrievalLaneId]] = []
        _, _, cases = load_frozen_cases("development")
        self.by_key = {
            call.idempotency_key: (case, lane.lane_id)
            for case in cases
            for lane, call in zip(case.spec.lanes, case.plan.calls, strict=True)
        }

    def __call__(self):
        # A socket-capable object cannot predate the complete durable method.
        assert (self.output_dir / "manifest.json").is_file()
        self.constructed += 1

        def run(call: ValidatedGapCall):
            case, lane_id = self.by_key[call.idempotency_key]
            for previous_case, previous_lane in self.calls:
                assert (self.output_dir / "lane-executions" / f"{previous_case}--{previous_lane}.json").is_file()
            if self.calls and self.calls[-1][0] != case.spec.case_id:
                assert (self.output_dir / "case-portfolios" / f"{self.calls[-1][0]}.json").is_file()
            ordinal = len(self.calls)
            self.calls.append((case.spec.case_id, lane_id))
            if ordinal == self.fail_at:
                raise ToolAdapterFailure(
                    "offline injected provider failure",
                    retryable=False,
                    failure_type="provider_authentication",
                    search_cost_usd=None,
                )
            if ordinal == self.invalid_at:
                return {
                    "tool": "academic_search",
                    "idempotency_key": call.idempotency_key,
                    "outbound_request_count": 1,
                }
            return _response(
                case,
                lane_id,
                call,
                reported_cost_usd=self.reported_cost_usd,
                include_rejection=self.include_rejection,
                identity_mismatch=ordinal == self.identity_mismatch_at,
            )

        return run


def _run(tmp_path: Path, *, monotonic_clock=None, **factory_options):
    output = tmp_path / "role-directed-v7"
    factory = RecordingFactory(output, **factory_options)
    artifact = live.execute_live_study(
        output_dir=output,
        soft_stop_usd=0.02,
        acknowledge_anonymous_daily_budget=True,
        adapter_factory=factory,
        monotonic_clock=monotonic_clock,
    )
    return output, factory, artifact


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_protocol_dry_run_locks_sixteen_lanes_without_live_authority(monkeypatch):
    def block_socket(*args, **kwargs):
        raise AssertionError("dry-run attempted to create a socket")

    monkeypatch.setattr(socket, "socket", block_socket)
    result = live.protocol_dry_run()

    assert result["case_count"] == 8
    assert sum(len(case["lanes"]) for case in result["cases"]) == 16
    assert result["implementation_sha256"] == live.EXPECTED_IMPLEMENTATION_SHA256
    assert len(result["runner_sha256"]) == 64
    assert result["live_runner_maximum_requests"] == 16
    assert result["live_runner_maximum_soft_stop_usd"] == 0.02
    assert result["live_provider_requests_authorized"] is False
    assert result["real_network_calls_performed"] is False
    assert result["real_model_calls_performed"] is False
    assert result["production_connected"] is False


def test_complete_run_reaches_all_write_once_boundaries(tmp_path):
    output, factory, artifact = _run(tmp_path)
    expected_calls = [
        (f"AA{index:02d}", lane_id)
        for index in range(1, 9)
        for lane_id in live._LANE_ORDER  # noqa: SLF001
    ]

    assert factory.constructed == 1
    assert factory.calls == expected_calls
    assert artifact.overall_state == "completed"
    assert artifact.request_count == 16
    assert artifact.successful_lane_count == 16
    assert artifact.completed_portfolio_count == 8
    assert artifact.provider_candidate_count == 32
    assert artifact.unique_candidate_count == 24
    assert artifact.model_call_count == 0
    assert artifact.review_packet_eligibility == "eligible_for_source_lock"
    assert artifact.provider_summary.reported_cost_usd == pytest.approx(0.016)
    assert len(list((output / "lane-executions").glob("*.json"))) == 16
    assert len(list((output / "case-portfolios").glob("*.json"))) == 8
    assert (output / "artifact-index.json").is_file()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    execution = json.loads((output / "execution.json").read_text(encoding="utf-8"))
    assert manifest["runner_sha256"] == artifact.runner_sha256
    assert execution["runner_sha256"] == artifact.runner_sha256


def test_every_provider_row_occurrence_and_lane_membership_reaches_csv(tmp_path):
    output, _, artifact = _run(tmp_path, include_rejection=True)
    provider_rows = _read_csv(output / "provider-rows.csv")
    unique_rows = _read_csv(output / "unique-candidates.csv")
    review_rows = _read_csv(output / "review.csv")

    assert artifact.provider_row_count == 48
    assert len(provider_rows) == 48
    assert len(unique_rows) == len(review_rows) == 24
    candidates = [row for row in provider_rows if row["adapter_disposition"] == "candidate"]
    rejections = [row for row in provider_rows if row["adapter_disposition"] == "provider_rejected"]
    assert len(candidates) == 32
    assert len(rejections) == 16
    assert all(row["occurrence_sha256"] for row in candidates)
    assert all(row["unique_candidate_sha256"] for row in candidates)
    assert all(not row["occurrence_sha256"] for row in rejections)
    shared = [row for row in unique_rows if len(json.loads(row["occurrence_sha256s"])) == 2]
    assert len(shared) == 8
    assert all(json.loads(row["lane_memberships"]) == ["technology_scope", "technology_evidence"] for row in shared)
    assert all(
        not row["directly_relevant"]
        and not row["baseline_novel"]
        and not row["supported_role_ids"]
        and not row["review_note"]
        for row in review_rows
    )
    assert all(row["frozen_baseline_sources"] for row in review_rows)
    assert all(row["frozen_role_profile"] for row in review_rows)


def test_doi_precedes_url_and_conflicting_nonempty_dois_do_not_merge():
    _, _, cases = load_frozen_cases("development")
    case = cases[0]
    scope_call, evidence_call = case.plan.calls

    scope_candidates = (
        ToolEvidenceCandidate(
            title="No DOI owner candidate",
            url="https://openalex.org/W100000001",
            publisher="OpenAlex fixture",
            evidence_summary="A sufficiently long synthetic abstract for URL identity testing.",
            summary_source="abstract",
            provider_result_index=0,
        ),
        ToolEvidenceCandidate(
            title="DOI owner candidate",
            url="https://openalex.org/W100000002",
            doi="10.5555/doi-owner",
            publisher="OpenAlex fixture",
            evidence_summary="A sufficiently long synthetic abstract for DOI identity testing.",
            summary_source="abstract",
            provider_result_index=1,
        ),
    )
    evidence_candidates = (
        ToolEvidenceCandidate(
            title="URL duplicate gains DOI",
            url="https://openalex.org/W100000001",
            doi="10.5555/url-owner-later-doi",
            publisher="OpenAlex fixture",
            evidence_summary="A sufficiently long synthetic abstract for URL fallback testing.",
            summary_source="abstract",
            provider_result_index=0,
        ),
        ToolEvidenceCandidate(
            title="DOI duplicate has another URL",
            url="https://openalex.org/W100000003",
            doi="10.5555/doi-owner",
            publisher="OpenAlex fixture",
            evidence_summary="A sufficiently long synthetic abstract for DOI precedence testing.",
            summary_source="abstract",
            provider_result_index=1,
        ),
        ToolEvidenceCandidate(
            title="Conflicting DOI on owner URL",
            url="https://openalex.org/W100000002",
            doi="10.5555/conflicting-doi",
            publisher="OpenAlex fixture",
            evidence_summary="A sufficiently long synthetic abstract for DOI conflict testing.",
            summary_source="abstract",
            provider_result_index=2,
        ),
    )

    def response(call, candidates):
        usage = ToolProviderUsage(
            provider="openalex",
            request_id=f"request-{call.idempotency_key[:12]}",
            request_id_source="client_generated",
            result_count=len(candidates),
            cost_basis="reported_usd",
            reported_cost_usd=0.001,
        )
        return ToolAdapterResponse(
            tool="academic_search",
            idempotency_key=call.idempotency_key,
            candidates=candidates,
            search_cost_usd=0.001,
            provider_request_id=usage.request_id,
            provider_usage=usage,
        )

    scope_execution = live._completed_execution(  # noqa: SLF001
        case,
        "technology_scope",
        0,
        scope_call,
        response(scope_call, scope_candidates),
        1.0,
    )
    evidence_execution = live._completed_execution(  # noqa: SLF001
        case,
        "technology_evidence",
        1,
        evidence_call,
        response(evidence_call, evidence_candidates),
        1.0,
    )
    portfolio = live.build_case_portfolio(
        case,
        (scope_execution, evidence_execution),
    )

    assert len(portfolio.occurrences) == 5
    assert len(portfolio.unique_candidates) == 3
    assert [item.deduplication_basis for item in portfolio.occurrences] == [
        "new_unique",
        "new_unique",
        "canonical_openalex_url",
        "normalized_doi",
        "new_unique",
    ]


def test_request_latency_reaches_journal_csv_and_provider_summary(tmp_path):
    ticks = iter(float(value) for value in range(32))
    output, _, artifact = _run(
        tmp_path,
        monotonic_clock=lambda: next(ticks),
    )

    assert artifact.provider_summary.total_latency_ms == pytest.approx(16000.0)
    assert {item.latency_ms for item in artifact.lane_executions} == {1000.0}
    first_journal = (output / "lane-executions" / "AA01--technology_scope.json").read_text(encoding="utf-8")
    assert '"latency_ms": 1000.0' in first_journal
    assert {row["latency_ms"] for row in _read_csv(output / "provider-rows.csv")} == {"1000.0"}


@pytest.mark.parametrize(
    ("soft_stop", "acknowledge"),
    [(0.0, True), (0.0201, True), (0.02, False)],
)
def test_invalid_authorization_fails_before_adapter_and_output(
    tmp_path,
    soft_stop,
    acknowledge,
):
    output = tmp_path / "forbidden"
    factory = RecordingFactory(output)

    with pytest.raises(live.OpenAlexRoleDirectedLiveError):
        live.execute_live_study(
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

    with pytest.raises(live.OpenAlexRoleDirectedLiveError, match="refuses"):
        live.execute_live_study(
            output_dir=output,
            soft_stop_usd=0.02,
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
        live.execute_live_study(
            output_dir=output,
            soft_stop_usd=0.02,
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
        "openalex_role_directed_unseen.py",
        "0" * 64,
    )

    with pytest.raises(live.OpenAlexRoleDirectedLiveError, match="identity drifted"):
        live.execute_live_study(
            output_dir=output,
            soft_stop_usd=0.02,
            acknowledge_anonymous_daily_budget=True,
            adapter_factory=factory,
        )

    assert factory.constructed == 0
    assert not output.exists()


def test_soft_stop_commits_one_lane_without_fabricating_a_portfolio(tmp_path):
    output, factory, artifact = _run(tmp_path, reported_cost_usd=0.02)

    assert factory.calls == [("AA01", "technology_scope")]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "soft_stop"
    assert artifact.review_packet_eligibility == "incomplete"
    assert len(artifact.lane_executions) == 1
    assert not artifact.portfolios
    assert (output / "lane-executions" / "AA01--technology_scope.json").is_file()
    assert not (output / "case-portfolios" / "AA01.json").exists()
    provider_rows = _read_csv(output / "provider-rows.csv")
    assert len(provider_rows) == 2
    assert {row["deduplication_basis"] for row in provider_rows} == {"NOT_EVALUATED"}


def test_provider_failure_remains_an_inspectable_partial_result(tmp_path):
    output, factory, artifact = _run(tmp_path, fail_at=0)

    assert factory.calls == [("AA01", "technology_scope")]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "request_failed"
    assert artifact.provider_summary.cost_state == "uninspectable"
    assert artifact.lane_executions[0].failure_type == "provider_authentication"
    assert (output / "lane-executions" / "AA01--technology_scope.json").is_file()


def test_invalid_response_is_not_reported_as_a_provider_pass(tmp_path):
    output, factory, artifact = _run(tmp_path, invalid_at=0)

    assert factory.calls == [("AA01", "technology_scope")]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "accounting_invalid"
    assert artifact.lane_executions[0].failure_type == "adapter_response_invalid"
    assert artifact.review_packet_eligibility == "incomplete"
    assert (output / "execution.json").is_file()


def test_identity_mismatch_preserves_response_but_blocks_portfolio(tmp_path):
    output, factory, artifact = _run(tmp_path, identity_mismatch_at=0)

    assert factory.calls == [("AA01", "technology_scope")]
    assert artifact.provider_summary.stopped_reason == "accounting_invalid"
    assert artifact.lane_executions[0].response is not None
    assert artifact.lane_executions[0].failure_type == "adapter_identity_mismatch"
    assert not artifact.portfolios
    provider_rows = _read_csv(output / "provider-rows.csv")
    assert len(provider_rows) == 2
    assert {row["deduplication_basis"] for row in provider_rows} == {"NOT_EVALUATED"}


def test_artifacts_expose_no_key_or_unrelated_process_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("UNRELATED_PROCESS_SECRET", "must-not-reach-artifacts")
    output, _, _ = _run(tmp_path)

    rendered = "\n".join(path.read_text(encoding="utf-8") for path in output.rglob("*") if path.is_file())
    assert "must-not-reach-artifacts" not in rendered
    assert "configured-secret" not in rendered
    assert '"api_key_used": false' in rendered


def test_cli_json_projection_survives_strict_gbk_stdout():
    """The completed AA run reached disk before a bullet broke GBK stdout."""

    payload = {"title": "Role-directed evidence • completed"}

    rendered = live._stdout_json(payload)
    encoded = rendered.encode("gbk", errors="strict")

    assert "\\u2022" in rendered
    assert json.loads(encoded.decode("gbk")) == payload


def test_production_worker_does_not_import_role_directed_components():
    worker = Path("src/academic_agent/pipeline_worker.py").read_text(encoding="utf-8")

    assert "openalex_role_directed_live" not in worker
    assert "openalex_role_directed_unseen" not in worker
    assert "AnonymousOpenAlexEvidenceSearchAdapter" not in worker
