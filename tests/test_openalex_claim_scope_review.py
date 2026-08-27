"""Zero-network source-lock and Schema v2 tests for claim-scope v3."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import openalex_claim_scope_review as claim_review
from academic_agent.evidence_gap import ValidatedGapCall
from academic_agent.openalex_claim_scope import OpenAlexClaimScopeCandidate
from academic_agent.tools.evidence_search import ToolEvidenceCandidate, ToolProviderUsage
from academic_agent.tools.openalex_claim_scope_search import (
    OpenAlexClaimScopeAdapterResponse,
)
from openalex_claim_scope_live import execute_live_study
from openalex_claim_scope_review import (
    DECLARATION_FIELDS,
    REVIEW_FIELDS,
    ClaimScopeReviewError,
    create_source_lock,
    prepare_packet,
    summarize_packet,
)
from openalex_claim_scope_unseen import PreparedClaimScopeCase, load_frozen_cases


def _candidate(
    case: PreparedClaimScopeCase,
    *,
    accepted: bool,
) -> OpenAlexClaimScopeCandidate:
    """Build one deterministic candidate without importing test-only helpers."""

    required = [
        group.text_phrases[0] for group in case.spec.profile.required_groups
    ]
    supporting = [
        group.text_phrases[0]
        for group in case.spec.profile.supporting_groups[
            : case.spec.profile.minimum_supporting_groups
        ]
    ]
    included_required = required if accepted else []
    title = (
        f"{' '.join(included_required)} controlled study"
        if accepted
        else "Broad adjacent application review"
    )
    summary = (
        f"{' '.join(included_required + supporting)}. The study reports "
        f"direct comparative evidence for {case.spec.query}."
        if accepted
        else (
            f"{' '.join(supporting)}. This broad review intentionally omits "
            "every required concept from the frozen profile."
        )
    )
    return OpenAlexClaimScopeCandidate(
        evidence=ToolEvidenceCandidate(
            title=title,
            url=f"https://openalex.org/W{case.spec.case_id[1:]}00000001",
            publisher="OpenAlex zero-network claim-scope review fixture",
            evidence_summary=summary,
            summary_source="abstract",
            provider_result_index=0,
        ),
        aboutness=(),
    )


class ReviewFactory:
    """Return one accepted or abstained source for each frozen case."""

    def __init__(self, *, accepted: bool = True) -> None:
        self.accepted = accepted
        _, _, cases = load_frozen_cases()
        self.case_by_key = {
            case.plan.calls[0].idempotency_key: case for case in cases
        }

    def __call__(self):
        def run(call: ValidatedGapCall) -> OpenAlexClaimScopeAdapterResponse:
            case = self.case_by_key[call.idempotency_key]
            candidate = _candidate(case, accepted=self.accepted)
            request_id = f"client-openalex-review-{case.spec.case_id.casefold()}"
            usage = ToolProviderUsage(
                provider="openalex",
                request_id=request_id,
                request_id_source="client_generated",
                result_count=1,
                cost_basis="reported_usd",
                reported_cost_usd=0.001,
            )
            return OpenAlexClaimScopeAdapterResponse(
                idempotency_key=call.idempotency_key,
                candidates=(candidate,),
                search_cost_usd=0.001,
                provider_request_id=request_id,
                provider_usage=usage,
            )

        return run


def _source(
    tmp_path: Path,
    monkeypatch,
    *,
    accepted: bool = True,
) -> Path:
    """Materialize a complete offline execution and bind test-local hashes."""

    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    source = tmp_path / "claim-scope-source"
    execute_live_study(
        output_dir=source,
        soft_stop_usd=0.01,
        acknowledge_anonymous_daily_budget=True,
        adapter_factory=ReviewFactory(accepted=accepted),
    )
    hashes = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in claim_review.SOURCE_FILES
    }
    monkeypatch.setattr(claim_review, "EXPECTED_SOURCE_FILE_SHA256", hashes)
    if accepted:
        monkeypatch.setattr(
            claim_review,
            "EXPECTED_ACCEPTED_PER_CASE",
            {case_id: 1 for case_id in claim_review.CASE_IDS},
        )
        monkeypatch.setattr(claim_review, "EXPECTED_REVIEW_ROW_COUNT", 8)
    return source


def _lock(source: Path, tmp_path: Path) -> Path:
    source_lock = tmp_path / "private" / "source-lock.json"
    create_source_lock(
        source,
        source_lock,
        study_owner_id="offline-claim-scope-owner",
        confirm_authorized_output=True,
        authorized_at=datetime(2026, 8, 27, 11, 0, tzinfo=UTC),
    )
    return source_lock


def _write_csv(
    path: Path,
    fields: tuple[str, ...],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _complete_declaration(
    packet: Path,
    *,
    ai_use: str = "NONE",
    external_sources_checked: str = "ALL_ATTEMPTED",
    reviewed_all: str = "YES",
) -> None:
    _write_csv(
        packet / "reviewer_declaration.csv",
        DECLARATION_FIELDS,
        [
            {
                "reviewer_id": "human-reviewer-v3",
                "reviewed_all": reviewed_all,
                "generative_ai_use": ai_use,
                "external_sources_checked": external_sources_checked,
                "elapsed_minutes": "70",
                "expertise": "academic evidence synthesis",
                "completed_date": "2026-08-27",
                "limitations": (
                    "Novelty is relative to the visible frozen baseline only."
                ),
            }
        ],
    )


def _complete_labels(
    packet: Path,
    *,
    pairs_by_case: dict[str, tuple[str, str]] | None = None,
) -> None:
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        relevant, novel = (pairs_by_case or {}).get(
            row["case_id"],
            ("YES", "YES"),
        )
        row["relevant"] = relevant
        row["novel"] = novel
        row["review_note"] = (
            "The opened source directly addresses the declared academic gap, "
            "and its contribution was compared with the visible frozen baseline."
        )
    _write_csv(packet / "labels.csv", REVIEW_FIELDS, rows)


def test_source_lock_and_packet_preserve_every_identity_and_baseline(
    tmp_path,
    monkeypatch,
):
    """The reviewer sees the exact denominator, source context, and baseline."""

    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"

    manifest = prepare_packet(source, source_lock, packet)
    lock = json.loads(source_lock.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 2
    assert manifest["mode"] == "openalex_claim_scope_v3_value_review_packet"
    assert manifest["executed_revision"] == claim_review.EXPECTED_EXECUTED_REVISION
    assert manifest["production_connected"] is False
    assert manifest["report_workflow_connected"] is False
    assert len(manifest["baseline_contexts"]) == 8
    assert len(manifest["rows"]) == 8
    assert all(row["source_context"]["evidence_summary"] for row in manifest["rows"])
    assert all(
        context["claim_scope_profile"] for context in manifest["baseline_contexts"]
    )
    assert lock["source_file_sha256"] == claim_review.EXPECTED_SOURCE_FILE_SHA256
    assert set(lock["source_file_sha256"]) == set(claim_review.SOURCE_FILES)
    assert source_lock.parent != packet
    assert (packet / "README.md").is_file()


def test_blank_packet_is_incomplete_not_a_zero_error_pass(tmp_path, monkeypatch):
    """No labels must remain visibly unmeasured rather than become zero errors."""

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


def test_complete_human_review_applies_all_frozen_value_gates(
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
    assert provider["metrics"]["accepted_candidate_count"] == 8
    assert provider["metrics"]["accepted_case_count"] == 8
    assert provider["metrics"]["wrong_source_rate"] == 0.0
    assert provider["metrics"]["novel_relevant_case_count"] == 8
    assert all(
        value == "pass" for value in provider["threshold_results"].values()
    )
    assert result["planner_trigger_study_eligible"] is True
    assert result["production_connection_authorized"] is False


def test_one_wrong_source_fails_the_precision_first_gate(tmp_path, monkeypatch):
    """One false positive out of eight exceeds the frozen five-percent ceiling."""

    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    _complete_labels(packet, pairs_by_case={"V01": ("NO", "N/A")})
    _complete_declaration(packet)

    result = summarize_packet(source, source_lock, packet)
    provider = result["provider_results"]["openalex"]

    assert result["decision"] == "fail"
    assert provider["metrics"]["wrong_source_count"] == 1
    assert provider["metrics"]["wrong_source_rate"] == pytest.approx(0.125)
    assert provider["threshold_results"]["wrong_source_rate"] == "fail"


def test_fewer_than_six_novel_cases_fails_without_rewriting_labels(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    _complete_labels(
        packet,
        pairs_by_case={
            "V01": ("YES", "NO"),
            "V02": ("YES", "NO"),
            "V03": ("YES", "NO"),
        },
    )
    _complete_declaration(packet)

    result = summarize_packet(source, source_lock, packet)
    provider = result["provider_results"]["openalex"]

    assert result["decision"] == "fail"
    assert provider["metrics"]["novel_relevant_case_count"] == 5
    assert provider["threshold_results"]["novel_relevant_cases"] == "fail"


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
    assert result["completed_row_count"] == 8
    assert result["observed_label_counts"] is not None
    assert result["provider_results"]["openalex"]["metrics"] is None


@pytest.mark.parametrize(
    ("external", "reviewed_all"),
    [("SOME", "YES"), ("ALL_ATTEMPTED", "NO")],
)
def test_method_declaration_failure_is_not_a_pass(
    tmp_path,
    monkeypatch,
    external,
    reviewed_all,
):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    _complete_labels(packet)
    _complete_declaration(
        packet,
        external_sources_checked=external,
        reviewed_all=reviewed_all,
    )

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "not_inspectable"
    assert result["decision"] == "not_evaluated"
    assert result["method_issues"]


def test_unverifiable_source_keeps_the_result_not_inspectable(
    tmp_path,
    monkeypatch,
):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    _complete_labels(
        packet,
        pairs_by_case={"V01": ("UNVERIFIABLE", "UNVERIFIABLE")},
    )
    _complete_declaration(packet)

    result = summarize_packet(source, source_lock, packet)

    assert result["protocol_status"] == "not_inspectable"
    assert result["decision"] == "not_evaluated"
    assert result["uninspectable_row_ids"]


def test_source_lock_requires_explicit_owner_confirmation(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)

    with pytest.raises(ClaimScopeReviewError, match="explicit"):
        create_source_lock(
            source,
            tmp_path / "source-lock.json",
            study_owner_id="offline-owner",
            confirm_authorized_output=False,
        )


def test_mechanical_failure_cannot_be_source_locked(tmp_path, monkeypatch):
    """A complete provider run is still ineligible when no case has an ACCEPT."""

    source = _source(tmp_path, monkeypatch, accepted=False)

    with pytest.raises(ClaimScopeReviewError, match="mechanical gate"):
        create_source_lock(
            source,
            tmp_path / "source-lock.json",
            study_owner_id="offline-owner",
            confirm_authorized_output=True,
        )


def test_source_drift_after_lock_blocks_packet_preparation(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    journal = source / "case-executions" / "V01.json"
    journal.write_text(
        journal.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ClaimScopeReviewError, match="identity drifted"):
        prepare_packet(source, source_lock, tmp_path / "packet")


def test_case_journal_drift_blocks_source_lock(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    journal = source / "case-executions" / "V01.json"
    payload = json.loads(journal.read_text(encoding="utf-8"))
    payload["latency_ms"] += 1.0
    journal.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ClaimScopeReviewError, match="journal does not match"):
        create_source_lock(
            source,
            tmp_path / "source-lock.json",
            study_owner_id="offline-owner",
            confirm_authorized_output=True,
        )


def test_packet_baseline_drift_blocks_summary(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    manifest_path = packet / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["baseline_contexts"][0]["gap_state"] = "silently changed"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ClaimScopeReviewError, match="baseline context drifted"):
        summarize_packet(source, source_lock, packet)


def test_label_identity_drift_blocks_summary(tmp_path, monkeypatch):
    source = _source(tmp_path, monkeypatch)
    source_lock = _lock(source, tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, source_lock, packet)
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["candidate_sha256"] = "0" * 64
    _write_csv(packet / "labels.csv", REVIEW_FIELDS, rows)

    with pytest.raises(ClaimScopeReviewError, match="identities do not match"):
        summarize_packet(source, source_lock, packet)


def test_production_worker_stays_disconnected_from_review_and_live_paths():
    worker = Path("src/academic_agent/pipeline_worker.py").read_text(encoding="utf-8")

    assert "openalex_claim_scope_review" not in worker
    assert "openalex_claim_scope_live" not in worker
