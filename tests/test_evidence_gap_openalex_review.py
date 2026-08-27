"""Zero-network source-lock and Schema v2 tests for anonymous OpenAlex."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import evidence_gap_openalex_review as openalex_review
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.tools.evidence_search import (
    ToolAdapterResponse,
    ToolEvidenceCandidate,
    ToolProviderUsage,
)
from evidence_gap_openalex_live import execute_live_study
from evidence_gap_openalex_review import (
    DECLARATION_FIELDS,
    REVIEW_FIELDS,
    AnonymousOpenAlexReviewError,
    create_source_lock,
    prepare_packet,
    summarize_packet,
    write_summary,
)
from evidence_gap_phase4_audit import load_frozen_cases


def _response(
    call: ValidatedGapCall,
    case_id: str,
    candidate_count: int,
    *,
    reported_cost_usd: float,
) -> ToolAdapterResponse:
    candidates = tuple(
        ToolEvidenceCandidate(
            title=(
                f"{call.query} controlled experimental evidence "
                f"replication {index + 1}"
            ),
            url=f"https://openalex.org/W420000{case_id[1:]}{index + 1}",
            publisher="OpenAlex offline review fixture",
            evidence_summary=(
                f"This source directly investigates {call.query} and reports "
                f"controlled comparative evidence for replication {index + 1}."
            ),
            summary_source="abstract",
            provider_result_index=index,
        )
        for index in range(candidate_count)
    )
    usage = ToolProviderUsage(
        provider="openalex",
        request_id=f"client-openalex-{case_id.casefold()}",
        request_id_source="client_generated",
        result_count=candidate_count,
        cost_basis="reported_usd",
        reported_cost_usd=reported_cost_usd,
    )
    return ToolAdapterResponse(
        tool=call.tool,
        idempotency_key=call.idempotency_key,
        candidates=candidates,
        search_cost_usd=reported_cost_usd,
        provider_request_id=usage.request_id,
        provider_usage=usage,
    )


class AnonymousReviewFactory:
    """Create the frozen 1/2/3/3 denominator without opening a socket."""

    def __init__(
        self,
        *,
        candidate_counts: dict[str, int] | None = None,
        reported_cost_usd: float = 0.0001,
    ) -> None:
        self.candidate_counts = candidate_counts or {
            "D01": 1,
            "D02": 2,
            "D03": 3,
            "D04": 3,
        }
        self.reported_cost_usd = reported_cost_usd
        _, cases = load_frozen_cases()
        self.case_by_key = {
            case.plan.calls[0].idempotency_key: case.spec.case_id for case in cases
        }

    def __call__(self):
        def run(call: ValidatedGapCall) -> ToolAdapterResponse:
            case_id = self.case_by_key[call.idempotency_key]
            return _response(
                call,
                case_id,
                self.candidate_counts[case_id],
                reported_cost_usd=self.reported_cost_usd,
            )

        return run


def _source(
    tmp_path: Path,
    monkeypatch,
    *,
    candidate_counts: dict[str, int] | None = None,
    reported_cost_usd: float = 0.0001,
) -> Path:
    source = tmp_path / "anonymous-source"
    execute_live_study(
        output_dir=source,
        soft_stop_usd=0.01,
        acknowledge_anonymous_daily_budget=True,
        adapter_factory=AnonymousReviewFactory(
            candidate_counts=candidate_counts,
            reported_cost_usd=reported_cost_usd,
        ),
    )
    hashes = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in openalex_review.SOURCE_FILES
    }
    monkeypatch.setattr(openalex_review, "EXPECTED_SOURCE_FILE_SHA256", hashes)
    return source


def _lock(source: Path, tmp_path: Path) -> Path:
    source_lock = tmp_path / "private" / "source-lock.json"
    create_source_lock(
        source,
        source_lock,
        study_owner_id="offline-study-owner",
        confirm_authorized_output=True,
        authorized_at=datetime(2026, 8, 27, 3, 0, tzinfo=UTC),
    )
    return source_lock


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _complete_declaration(
    packet: Path,
    *,
    ai_use: str = "NONE",
    external_sources_checked: str = "ALL_ATTEMPTED",
) -> None:
    _write_csv(
        packet / "reviewer_declaration.csv",
        DECLARATION_FIELDS,
        [
            {
                "reviewer_id": "human-reviewer-oa1",
                "reviewed_all": "YES",
                "generative_ai_use": ai_use,
                "external_sources_checked": external_sources_checked,
                "elapsed_minutes": "55",
                "expertise": "academic evidence review",
                "completed_date": "2026-08-27",
                "limitations": "Novelty is relative to the frozen baseline only.",
            }
        ],
    )


def _complete_labels(
    packet: Path,
    *,
    first_pair: tuple[str, str] | None = None,
) -> None:
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for index, row in enumerate(rows):
        relevant, novel = (
            first_pair if index == 0 and first_pair is not None else ("YES", "YES")
        )
        row["relevant"] = relevant
        row["novel"] = novel
        row["review_note"] = (
            "The opened source directly addresses the declared academic gap, and "
            "its measured contribution was compared with the visible frozen baseline."
        )
    _write_csv(packet / "labels.csv", REVIEW_FIELDS, rows)


def test_source_lock_and_packet_preserve_exact_nine_rows_and_baselines(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"

    manifest = prepare_packet(source, source_lock, packet)
    lock = json.loads(source_lock.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 2
    assert manifest["mode"] == "anonymous_openalex_value_review_packet"
    assert manifest["executed_revision"] == openalex_review.EXPECTED_EXECUTED_REVISION
    assert manifest["production_connected"] is False
    assert manifest["report_workflow_connected"] is False
    assert len(manifest["baseline_contexts"]) == 4
    assert len(manifest["rows"]) == 9
    assert {row["provider"] for row in manifest["rows"]} == {"openalex"}
    assert all(
        context["baseline_sources"] for context in manifest["baseline_contexts"]
    )
    assert lock["source_file_sha256"] == openalex_review.EXPECTED_SOURCE_FILE_SHA256
    assert set(lock["source_file_sha256"]) == set(openalex_review.SOURCE_FILES)
    assert source_lock.parent != packet
    assert (packet / "README.md").is_file()


def test_blank_packet_is_incomplete_not_a_zero_error_pass(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "incomplete"
    assert result["decision"] == "not_evaluated"
    assert result["completed_row_count"] == 0
    assert result["provider_results"]["openalex"]["metrics"] is None
    assert result["planner_trigger_study_eligible"] is False
    assert result["production_connection_authorized"] is False


def test_complete_human_review_applies_both_remaining_value_gates(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    _complete_labels(packet)
    _complete_declaration(packet)

    result = summarize_packet(source, source_lock, packet)

    provider = result["provider_results"]["openalex"]
    assert result["protocol_status"] == "complete"
    assert result["decision"] == "pass"
    assert provider["metrics"]["accepted_candidate_count"] == 9
    assert provider["metrics"]["accepted_case_count"] == 4
    assert provider["metrics"]["wrong_source_rate"] == 0.0
    assert provider["metrics"]["novel_relevant_case_count"] == 4
    assert set(provider["threshold_results"].values()) == {"pass"}
    assert result["planner_trigger_study_eligible"] is True
    assert result["production_connection_authorized"] is False


def test_one_wrong_source_out_of_nine_fails_the_frozen_five_percent_gate(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    _complete_labels(packet, first_pair=("NO", "N/A"))
    _complete_declaration(packet)

    result = summarize_packet(source, source_lock, packet)
    provider = result["provider_results"]["openalex"]

    assert result["protocol_status"] == "complete"
    assert result["decision"] == "fail"
    assert provider["metrics"]["wrong_source_count"] == 1
    assert provider["metrics"]["wrong_source_rate"] == pytest.approx(1 / 9)
    assert provider["threshold_results"]["wrong_source_rate"] == "fail"


def test_unverifiable_source_is_not_inspectable_and_never_a_pass(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    _complete_labels(packet, first_pair=("UNVERIFIABLE", "UNVERIFIABLE"))
    _complete_declaration(packet)

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "not_inspectable"
    assert result["decision"] == "not_evaluated"
    assert result["uninspectable_row_ids"]
    assert result["provider_results"]["openalex"]["metrics"] is None


def test_substantive_ai_review_is_retained_but_excluded(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    _complete_labels(packet)
    _complete_declaration(packet, ai_use="SOME_SUBSTANTIVE")

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "excluded_substantive_ai"
    assert result["decision"] == "not_evaluated"
    assert result["reviewer_declaration"]["generative_ai_use"] == (
        "SOME_SUBSTANTIVE"
    )


def test_not_all_urls_attempted_is_not_inspectable(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    _complete_labels(packet)
    _complete_declaration(packet, external_sources_checked="SOME")

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "not_inspectable"
    assert result["method_issues"] == ["not_all_external_sources_were_attempted"]
    assert result["decision"] == "not_evaluated"


def test_source_drift_after_lock_is_rejected_before_labels(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    (source / "review.csv").write_text("changed after lock\n", encoding="utf-8")

    with pytest.raises(AnonymousOpenAlexReviewError, match="frozen anonymous"):
        prepare_packet(source, source_lock, tmp_path / "packet")


def test_packet_baseline_context_drift_is_rejected_before_labels(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    manifest_path = packet / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["baseline_contexts"][0]["gap_state"] = "rewritten after preparation"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(AnonymousOpenAlexReviewError, match="baseline context drifted"):
        summarize_packet(source, source_lock, packet)


def test_label_identity_drift_is_rejected_even_when_row_count_matches(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["title"] = "Rewritten candidate identity"
    _write_csv(packet / "labels.csv", REVIEW_FIELDS, rows)

    with pytest.raises(AnonymousOpenAlexReviewError, match="label identity drifted"):
        summarize_packet(source, source_lock, packet)


def test_partial_anonymous_execution_cannot_be_source_locked(tmp_path, monkeypatch):
    del monkeypatch
    source = tmp_path / "partial-anonymous-source"
    execute_live_study(
        output_dir=source,
        soft_stop_usd=0.01,
        acknowledge_anonymous_daily_budget=True,
        adapter_factory=AnonymousReviewFactory(reported_cost_usd=0.01),
    )

    with pytest.raises(AnonymousOpenAlexReviewError, match="could not read artifact"):
        create_source_lock(
            source,
            tmp_path / "source-lock.json",
            study_owner_id="offline-owner",
            confirm_authorized_output=True,
        )


def test_source_lock_requires_explicit_owner_confirmation(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)

    with pytest.raises(AnonymousOpenAlexReviewError, match="explicit"):
        create_source_lock(
            source,
            tmp_path / "source-lock.json",
            study_owner_id="offline-owner",
            confirm_authorized_output=False,
        )


def test_other_completed_run_cannot_claim_the_observed_execution_identity(tmp_path):
    source = tmp_path / "different-completed-run"
    execute_live_study(
        output_dir=source,
        soft_stop_usd=0.01,
        acknowledge_anonymous_daily_budget=True,
        adapter_factory=AnonymousReviewFactory(),
    )

    with pytest.raises(AnonymousOpenAlexReviewError, match="frozen anonymous"):
        create_source_lock(
            source,
            tmp_path / "source-lock.json",
            study_owner_id="offline-owner",
            confirm_authorized_output=True,
        )


def test_summary_is_write_once_and_keeps_production_disconnected(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    output = tmp_path / "result.json"
    prepare_packet(source, source_lock, packet)
    result = summarize_packet(source, source_lock, packet)

    write_summary(output, result)
    persisted = json.loads(output.read_text(encoding="utf-8"))

    assert persisted["production_connected"] is False
    assert persisted["report_workflow_connected"] is False
    assert persisted["production_connection_authorized"] is False
    with pytest.raises(AnonymousOpenAlexReviewError, match="could not create"):
        write_summary(output, result)


def test_production_worker_does_not_import_anonymous_review_boundary():
    worker = Path("src/academic_agent/pipeline_worker.py").read_text(encoding="utf-8")

    assert "evidence_gap_openalex_review" not in worker
