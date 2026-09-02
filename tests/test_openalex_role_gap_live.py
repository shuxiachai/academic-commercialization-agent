"""Zero-network seams for the adaptive role-gap closure v8 live runner."""

from __future__ import annotations

import csv
import json
import socket
from pathlib import Path

import pytest

import openalex_role_gap_live as live
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.evidence_search import (
    ProviderResultRejection,
    ToolAdapterFailure,
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from openalex_role_gap_unseen import (
    PreparedRoleGapCase,
    RoleGapClosureOption,
    load_frozen_cases,
)


def _work_id(case_id: str, lane_id: live.LaneId, suffix: int) -> str:
    lane_digit = 1 if lane_id == "anchor_search" else 2
    return (
        f"https://openalex.org/W{int(case_id[2:]):02d}"
        f"{lane_digit}{suffix:05d}"
    )


def _all_role_signal_text(case: PreparedRoleGapCase) -> str:
    phrases = [
        phrase
        for _, role in case.spec.roles.ordered_roles()
        for phrase in role.signal_groups[0]
    ]
    return (
        "This synthetic anchor contains every frozen role signal in one "
        f"candidate: {'; '.join(phrases)}."
    )


def _candidate(
    case: PreparedRoleGapCase,
    lane_id: live.LaneId,
    index: int,
    *,
    shared: bool,
    anchor_has_all_roles: bool,
) -> ToolEvidenceCandidate:
    if shared:
        doi = f"10.5555/{case.spec.case_id.casefold()}.shared"
        label = "shared DOI candidate"
    else:
        doi = None
        label = f"{lane_id} unique candidate"
    if lane_id == "anchor_search" and anchor_has_all_roles:
        summary = _all_role_signal_text(case)
    else:
        summary = (
            f"This synthetic {lane_id} abstract for {case.spec.case_id} "
            "contains generic evidence text for persistence testing but no "
            "claim about real source relevance or commercial value."
        )
    return ToolEvidenceCandidate(
        title=f"{case.spec.case_id} {label} for adaptive retrieval",
        url=_work_id(case.spec.case_id, lane_id, index + 1),
        doi=doi,
        publisher="OpenAlex zero-network adaptive fixture",
        evidence_summary=summary,
        summary_source="abstract",
        citation_count=index + 1,
        provider_result_index=index,
    )


def _response(
    case: PreparedRoleGapCase,
    lane_id: live.LaneId,
    call: ValidatedGapCall,
    *,
    reported_cost_usd: float,
    include_rejection: bool,
    identity_mismatch: bool,
    anchor_has_all_roles: bool,
) -> ToolAdapterResponse:
    candidates = (
        _candidate(
            case,
            lane_id,
            0,
            shared=True,
            anchor_has_all_roles=anchor_has_all_roles,
        ),
    )
    if lane_id == "role_closure":
        candidates += (
            _candidate(
                case,
                lane_id,
                1,
                shared=False,
                anchor_has_all_roles=anchor_has_all_roles,
            ),
        )
    rejections = (
        (
            ProviderResultRejection(
                provider_result_index=len(candidates),
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
        request_id=f"client-v8-{call.idempotency_key[:16]}",
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
    """Injected adapter proving manifest, route, and journal ordering."""

    def __init__(
        self,
        output_dir: Path,
        *,
        reported_cost_usd: float = 0.001,
        include_rejection: bool = False,
        anchor_has_all_roles: bool = False,
        fail_at: int | None = None,
        invalid_at: int | None = None,
        identity_mismatch_at: int | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.reported_cost_usd = reported_cost_usd
        self.include_rejection = include_rejection
        self.anchor_has_all_roles = anchor_has_all_roles
        self.fail_at = fail_at
        self.invalid_at = invalid_at
        self.identity_mismatch_at = identity_mismatch_at
        self.constructed = 0
        self.calls: list[tuple[str, live.LaneId, str | None]] = []
        _, _, cases = load_frozen_cases("development")
        self.by_key: dict[
            str,
            tuple[PreparedRoleGapCase, live.LaneId, RoleGapClosureOption | None],
        ] = {}
        for case in cases:
            self.by_key[case.anchor_call.idempotency_key] = (
                case,
                "anchor_search",
                None,
            )
            for option in case.closure_options:
                self.by_key[option.call.idempotency_key] = (
                    case,
                    "role_closure",
                    option,
                )

    def __call__(self):
        # A socket-capable object cannot predate the complete durable method.
        assert (self.output_dir / "manifest.json").is_file()
        self.constructed += 1

        def run(call: ValidatedGapCall):
            case, lane_id, option = self.by_key[call.idempotency_key]
            if self.calls:
                previous_case, previous_lane, _ = self.calls[-1]
                assert (
                    self.output_dir
                    / "lane-executions"
                    / f"{previous_case}--{previous_lane}.json"
                ).is_file()
                if previous_case != case.spec.case_id:
                    assert (
                        self.output_dir
                        / "case-portfolios"
                        / f"{previous_case}.json"
                    ).is_file()
            if lane_id == "role_closure":
                assert (
                    self.output_dir
                    / "lane-executions"
                    / f"{case.spec.case_id}--anchor_search.json"
                ).is_file()
                assert (
                    self.output_dir
                    / "route-executions"
                    / f"{case.spec.case_id}.json"
                ).is_file()
            ordinal = len(self.calls)
            role_id = option.role_id if option else None
            self.calls.append((case.spec.case_id, lane_id, role_id))
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
                anchor_has_all_roles=self.anchor_has_all_roles,
            )

        return run


def _run(tmp_path: Path, *, monotonic_clock=None, **factory_options):
    output = tmp_path / "role-gap-v8"
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


def test_protocol_dry_run_locks_adaptive_options_without_live_authority(
    monkeypatch,
):
    def block_socket(*args, **kwargs):
        raise AssertionError("dry-run attempted to create a socket")

    monkeypatch.setattr(socket, "socket", block_socket)
    result = live.protocol_dry_run()

    assert result["case_count"] == 8
    assert result["potential_call_identity_count"] == 48
    assert result["maximum_executed_search_request_count"] == 16
    assert result["implementation_sha256"] == live.EXPECTED_IMPLEMENTATION_SHA256
    assert len(result["runner_sha256"]) == 64
    assert result["live_runner_maximum_requests"] == 16
    assert result["live_runner_maximum_soft_stop_usd"] == 0.02
    assert result["live_provider_requests_authorized"] is False
    assert result["real_network_calls_performed"] is False
    assert result["real_model_calls_performed"] is False
    assert result["production_connected"] is False


def test_complete_search_routes_reach_all_write_once_boundaries(tmp_path):
    output, factory, artifact = _run(tmp_path)

    assert factory.constructed == 1
    assert len(factory.calls) == 16
    assert [lane for _, lane, _ in factory.calls] == [
        lane for _ in range(8) for lane in live._LANE_ORDER  # noqa: SLF001
    ]
    assert all(role_id for _, lane, role_id in factory.calls if lane == "role_closure")
    assert artifact.overall_state == "completed"
    assert artifact.request_count == 16
    assert artifact.successful_request_count == 16
    assert artifact.route_decision_count == 8
    assert artifact.closure_request_count == 8
    assert artifact.completed_portfolio_count == 8
    assert artifact.provider_candidate_count == 24
    assert artifact.unique_candidate_count == 16
    assert artifact.model_call_count == 0
    assert artifact.review_packet_eligibility == "eligible_for_source_lock"
    assert artifact.provider_summary.reported_cost_usd == pytest.approx(0.016)
    assert all(route.decision.action == "search" for route in artifact.route_executions)
    assert len(list((output / "lane-executions").glob("*.json"))) == 16
    assert len(list((output / "route-executions").glob("*.json"))) == 8
    assert len(list((output / "case-portfolios").glob("*.json"))) == 8
    assert (output / "artifact-index.json").is_file()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    execution = json.loads((output / "execution.json").read_text(encoding="utf-8"))
    assert manifest["runner_sha256"] == artifact.runner_sha256
    assert execution["runner_sha256"] == artifact.runner_sha256


def test_no_gap_routes_complete_with_only_eight_anchor_requests(tmp_path):
    output, factory, artifact = _run(tmp_path, anchor_has_all_roles=True)

    assert len(factory.calls) == 8
    assert {lane for _, lane, _ in factory.calls} == {"anchor_search"}
    assert artifact.overall_state == "completed"
    assert artifact.request_count == 8
    assert artifact.closure_request_count == 0
    assert artifact.completed_portfolio_count == 8
    assert all(
        route.decision.action == "abstain"
        and route.decision.reason == "abstain_no_mechanical_role_gap"
        and route.decision.selected_closure is None
        for route in artifact.route_executions
    )
    assert len(list((output / "lane-executions").glob("*.json"))) == 8
    assert len(list((output / "route-executions").glob("*.json"))) == 8
    assert len(list((output / "case-portfolios").glob("*.json"))) == 8


def test_provider_route_and_review_lineage_reaches_every_csv(tmp_path):
    output, _, artifact = _run(tmp_path, include_rejection=True)
    provider_rows = _read_csv(output / "provider-rows.csv")
    route_rows = _read_csv(output / "route-decisions.csv")
    unique_rows = _read_csv(output / "unique-candidates.csv")
    candidate_review = _read_csv(output / "candidate-review.csv")
    case_review = _read_csv(output / "case-review.csv")

    assert artifact.provider_row_count == 40
    assert len(provider_rows) == 40
    assert len(route_rows) == artifact.route_decision_count == 8
    assert len(unique_rows) == len(candidate_review) == 16
    assert len(case_review) == artifact.completed_portfolio_count == 8
    candidates = [
        row for row in provider_rows if row["adapter_disposition"] == "candidate"
    ]
    rejections = [
        row
        for row in provider_rows
        if row["adapter_disposition"] == "provider_rejected"
    ]
    assert len(candidates) == 24
    assert len(rejections) == 16
    assert all(row["occurrence_sha256"] for row in candidates)
    assert all(row["unique_candidate_sha256"] for row in candidates)
    assert all(not row["occurrence_sha256"] for row in rejections)
    assert all(len(json.loads(row["observations"])) == 5 for row in route_rows)
    assert all(row["selected_role_id"] for row in route_rows)
    shared = [
        row
        for row in unique_rows
        if len(json.loads(row["occurrence_sha256s"])) == 2
    ]
    assert len(shared) == 8
    assert all(
        json.loads(row["lane_memberships"])
        == ["anchor_search", "role_closure"]
        for row in shared
    )
    assert all(
        not row["directly_relevant"]
        and not row["baseline_novel"]
        and not row["supported_role_ids"]
        and not row["closure_contributed_selected_role"]
        and not row["review_note"]
        for row in candidate_review
    )
    assert all(row["frozen_route_decision"] for row in candidate_review)
    assert all(row["frozen_baseline_sources"] for row in candidate_review)
    assert all(
        not row["routing_decision_correct"]
        and not row["anchor_human_coverable_within_three"]
        and not row["union_human_coverable_within_three"]
        for row in case_review
    )


def test_doi_precedence_registers_secondary_identity_without_false_merge():
    _, _, cases = load_frozen_cases("development")
    case = cases[0]

    def candidate(
        title: str,
        url: str,
        index: int,
        *,
        doi: str | None = None,
    ) -> ToolEvidenceCandidate:
        return ToolEvidenceCandidate(
            title=title,
            url=url,
            doi=doi,
            publisher="OpenAlex adaptive deduplication fixture",
            evidence_summary=(
                "A sufficiently long synthetic abstract for deterministic "
                "DOI and canonical OpenAlex URL identity testing."
            ),
            summary_source="abstract",
            provider_result_index=index,
        )

    anchor_candidates = (
        candidate("URL-only first owner", "https://openalex.org/W100000001", 0),
        candidate(
            "DOI first owner",
            "https://openalex.org/W100000002",
            1,
            doi="10.5555/doi-owner",
        ),
    )

    def response(
        call: ValidatedGapCall,
        candidates: tuple[ToolEvidenceCandidate, ...],
    ) -> ToolAdapterResponse:
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

    anchor = live._completed_execution(  # noqa: SLF001
        case,
        "anchor_search",
        None,
        response(case.anchor_call, anchor_candidates),
        1.0,
    )
    route = live._route_execution(case, anchor)  # noqa: SLF001
    selected = route.decision.selected_closure
    assert selected is not None
    closure_candidates = (
        candidate(
            "URL duplicate adds DOI",
            "https://openalex.org/W100000001",
            0,
            doi="10.5555/url-owner-later-doi",
        ),
        candidate(
            "DOI duplicate has another URL",
            "https://openalex.org/W100000003",
            1,
            doi="10.5555/doi-owner",
        ),
        candidate(
            "Conflicting DOI on owner URL",
            "https://openalex.org/W100000002",
            2,
            doi="10.5555/conflicting-doi",
        ),
        candidate(
            "Secondary DOI joins original URL owner",
            "https://openalex.org/W100000004",
            3,
            doi="10.5555/url-owner-later-doi",
        ),
    )
    closure = live._completed_execution(  # noqa: SLF001
        case,
        "role_closure",
        selected,
        response(selected.call, closure_candidates),
        1.0,
    )

    portfolio = live.build_case_portfolio(case, route, (anchor, closure))

    assert len(portfolio.occurrences) == 6
    assert len(portfolio.unique_candidates) == 3
    assert [item.deduplication_basis for item in portfolio.occurrences] == [
        "new_unique",
        "new_unique",
        "canonical_openalex_url",
        "normalized_doi",
        "new_unique",
        "normalized_doi",
    ]


def test_request_latency_reaches_journal_csv_and_provider_summary(tmp_path):
    ticks = iter(float(value) for value in range(32))
    output, _, artifact = _run(
        tmp_path,
        monotonic_clock=lambda: next(ticks),
    )

    assert artifact.provider_summary.total_latency_ms == pytest.approx(16000.0)
    assert {item.latency_ms for item in artifact.lane_executions} == {1000.0}
    first_journal = (
        output / "lane-executions" / "AC01--anchor_search.json"
    ).read_text(encoding="utf-8")
    assert '"latency_ms": 1000.0' in first_journal
    assert {
        row["latency_ms"] for row in _read_csv(output / "provider-rows.csv")
    } == {"1000.0"}


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

    with pytest.raises(live.OpenAlexRoleGapLiveError):
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

    with pytest.raises(live.OpenAlexRoleGapLiveError, match="refuses"):
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
        "openalex_role_gap_unseen.py",
        "0" * 64,
    )

    with pytest.raises(live.OpenAlexRoleGapLiveError, match="identity drifted"):
        live.execute_live_study(
            output_dir=output,
            soft_stop_usd=0.02,
            acknowledge_anonymous_daily_budget=True,
            adapter_factory=factory,
        )

    assert factory.constructed == 0
    assert not output.exists()


def test_soft_stop_preserves_anchor_and_route_without_fabricating_portfolio(
    tmp_path,
):
    output, factory, artifact = _run(tmp_path, reported_cost_usd=0.02)

    assert factory.calls == [("AC01", "anchor_search", None)]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "soft_stop"
    assert artifact.route_decision_count == 1
    assert artifact.route_executions[0].decision.action == "search"
    assert artifact.review_packet_eligibility == "incomplete"
    assert len(artifact.lane_executions) == 1
    assert not artifact.portfolios
    assert (output / "lane-executions" / "AC01--anchor_search.json").is_file()
    assert (output / "route-executions" / "AC01.json").is_file()
    assert not (output / "case-portfolios" / "AC01.json").exists()
    provider_rows = _read_csv(output / "provider-rows.csv")
    assert len(provider_rows) == 1
    assert {row["deduplication_basis"] for row in provider_rows} == {
        "NOT_EVALUATED"
    }


def test_provider_failure_remains_inspectable_without_route_or_retry(tmp_path):
    output, factory, artifact = _run(tmp_path, fail_at=0)

    assert factory.calls == [("AC01", "anchor_search", None)]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "request_failed"
    assert artifact.provider_summary.cost_state == "uninspectable"
    assert artifact.lane_executions[0].failure_type == "provider_authentication"
    assert not artifact.route_executions
    assert not artifact.portfolios
    assert (output / "lane-executions" / "AC01--anchor_search.json").is_file()


def test_invalid_response_is_not_reported_as_provider_pass(tmp_path):
    output, factory, artifact = _run(tmp_path, invalid_at=0)

    assert factory.calls == [("AC01", "anchor_search", None)]
    assert artifact.overall_state == "partial"
    assert artifact.provider_summary.stopped_reason == "accounting_invalid"
    assert artifact.lane_executions[0].failure_type == "adapter_response_invalid"
    assert artifact.review_packet_eligibility == "incomplete"
    assert (output / "execution.json").is_file()


def test_identity_mismatch_preserves_response_but_blocks_routing(tmp_path):
    output, factory, artifact = _run(tmp_path, identity_mismatch_at=0)

    assert factory.calls == [("AC01", "anchor_search", None)]
    assert artifact.provider_summary.stopped_reason == "accounting_invalid"
    assert artifact.lane_executions[0].response is not None
    assert artifact.lane_executions[0].failure_type == "adapter_identity_mismatch"
    assert not artifact.route_executions
    assert not artifact.portfolios
    provider_rows = _read_csv(output / "provider-rows.csv")
    assert len(provider_rows) == 1
    assert {row["deduplication_basis"] for row in provider_rows} == {
        "NOT_EVALUATED"
    }


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


def test_cli_json_projection_survives_strict_gbk_stdout():
    payload = {"title": "Adaptive role-gap evidence • completed"}

    rendered = live._stdout_json(payload)  # noqa: SLF001
    encoded = rendered.encode("gbk", errors="strict")

    assert "\\u2022" in rendered
    assert json.loads(encoded.decode("gbk")) == payload


def test_production_worker_does_not_import_role_gap_components():
    worker = Path("src/academic_agent/pipeline_worker.py").read_text(encoding="utf-8")

    assert "openalex_role_gap_live" not in worker
    assert "openalex_role_gap_unseen" not in worker
    assert "AnonymousOpenAlexEvidenceSearchAdapter" not in worker
