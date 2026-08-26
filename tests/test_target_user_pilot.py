"""Offline seam tests for the two-stage target-user decision pilot."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from target_user_pilot import (
    BASELINE_FIELDS,
    FOLLOWUP_FIELDS,
    PROFILE_FIELDS,
    SLOT_FIELDS,
    TargetUserPilotError,
    discover_reports,
    materialize_followup,
    prepare_pilot,
    summarize_pilot,
    write_summary,
    write_summaries,
)


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_cell(
    experiment_dir: Path,
    *,
    topic_num: int,
    repetition: int = 1,
    variant: str = "full",
    status: str = "success",
    suffix: str = "",
) -> Path:
    cell = experiment_dir / f"cell-{topic_num:02d}-{variant}-r{repetition}{suffix}"
    cell.mkdir(parents=True)
    topic = f"Commercialization topic {topic_num:02d}"
    meta = {
        "num": f"{topic_num:02d}",
        "rep": repetition,
        "variant": variant,
        "topic": topic,
        "industry": f"Industry {topic_num:02d}",
        "fixture_digest": f"fixture-{topic_num:02d}",
        "status": status,
    }
    (cell / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (cell / "commercialization_report.md").write_text(
        f"# {topic}\n\nFROZEN_REPORT_{topic_num:02d}\n", encoding="utf-8"
    )
    return cell


def _experiment(tmp_path: Path) -> Path:
    experiment = tmp_path / "frozen-experiment"
    for topic_num in range(1, 11):
        _write_cell(experiment, topic_num=topic_num)
        # These distractors prove that discovery is frozen to full/r1 rather
        # than whichever report happens to sort first on disk.
        _write_cell(experiment, topic_num=topic_num, variant="monolith")
        _write_cell(experiment, topic_num=topic_num, repetition=2)
    return experiment


def _prepare(tmp_path: Path) -> tuple[Path, Path, Path]:
    experiment = _experiment(tmp_path)
    packet = tmp_path / "packet"
    source_lock = tmp_path / "private" / "source-lock.json"
    prepare_pilot(experiment, packet, source_lock)
    return experiment, packet, source_lock


def _fill_intake(
    packet: Path,
    reviewer_id: str,
    *,
    topic_num: str,
    role: str = "TTO_COMMERCIALIZATION",
    ai_use: str = "NONE",
    consent: str = "YES",
) -> None:
    reviewer_dir = packet / "stage-1" / reviewer_id
    topic = f"Commercialization topic {topic_num}"
    _write_csv(
        reviewer_dir / "reviewer_profile.csv",
        PROFILE_FIELDS,
        [
            {
                "reviewer_id": reviewer_id,
                "role_category": role,
                "experience_band": "3_5",
                "professional_context": "I evaluate research commercialization opportunities.",
                "domain_experience": f"Direct experience with topic {topic_num}.",
                "generative_ai_use": ai_use,
                "generative_ai_notes": (
                    "AI generated substantive judgments." if ai_use == "SUBSTANTIVE" else ""
                ),
                "anonymous_aggregate_consent": consent,
                "compensation": "NONE",
                "compensation_notes": "",
            }
        ],
    )
    _write_csv(
        reviewer_dir / "baseline_form.csv",
        BASELINE_FIELDS,
        [
            {
                "reviewer_id": reviewer_id,
                "selected_topic_num": topic_num,
                "selected_topic": topic,
                "selection_reason": "This topic overlaps my professional decisions.",
                "current_workflow_summary": "I search primary sources and compare alternatives.",
                "expected_research_minutes": "180",
                "initial_decision": "DEFER",
                "initial_confidence": "2",
                "information_needed": "Evidence quality, IP constraints, and market timing.",
            }
        ],
    )


def _fill_followup(
    packet: Path,
    reviewer_id: str,
    *,
    usefulness: int = 4,
    citation_check: str = "NONE",
    factual_error_state: str = "NOT_CHECKED",
) -> None:
    path = packet / "stage-2" / reviewer_id / "followup_form.csv"
    row = _read_csv(path)[0]
    row.update(
        {
            "post_report_decision": "GO",
            "post_report_confidence": "4",
            "decision_usefulness": str(usefulness),
            "information_gain": "4",
            "actionability": "4",
            "evidence_trust": "3",
            "recommendation_acceptance": "4",
            "reading_minutes": "35",
            "estimated_revision_minutes": "25",
            "would_use_again": "YES",
            "citation_check": citation_check,
            "factual_error_state": factual_error_state,
            "blocking_error": "NO",
            "blocking_error_details": "",
            "most_useful_content": "The evidence boundaries made the decision easier to frame.",
            "missing_information": "More customer-specific economics would improve the report.",
            "required_corrections": "Prioritize the top two actions and shorten background sections.",
            "rationale": "The report added structured evidence while retaining visible uncertainty.",
        }
    )
    _write_csv(path, FOLLOWUP_FIELDS, [row])


def _close_slot(packet: Path, reviewer_id: str, *, state: str = "CLOSED_NO_RESPONSE") -> None:
    path = packet / "coordinator" / "slot_status.csv"
    rows = _read_csv(path)
    for row in rows:
        if row["reviewer_id"] == reviewer_id:
            row["slot_status"] = state
            row["closure_reason"] = "Recruitment ended before this slot started."
    _write_csv(path, SLOT_FIELDS, rows)


def test_prepare_freezes_sources_and_keeps_stage_one_report_free(tmp_path: Path) -> None:
    experiment, packet, source_lock = _prepare(tmp_path)

    lock = json.loads(source_lock.read_text(encoding="utf-8"))
    manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
    assert source_lock.parent != packet
    assert len(lock["sources"]) == 10
    assert manifest["stage_1_contains_reports"] is False
    assert manifest["human_response_count"] == 0

    for reviewer_id in ("T01", "T02"):
        stage_one = packet / "stage-1" / reviewer_id
        assert len(_read_csv(stage_one / "case_catalog.csv")) == 10
        assert not (stage_one / "report.md").exists()
        stage_one_text = "\n".join(
            path.read_text(encoding="utf-8") for path in stage_one.rglob("*") if path.is_file()
        )
        assert "FROZEN_REPORT_" not in stage_one_text
        assert "commercialization_report.md" not in stage_one_text

    with pytest.raises(TargetUserPilotError, match="must not already exist"):
        prepare_pilot(experiment, packet, source_lock)
    with pytest.raises(TargetUserPilotError, match="outside"):
        prepare_pilot(experiment, tmp_path / "leaky", tmp_path / "leaky" / "source-lock.json")


def test_discovery_rejects_duplicate_or_drifting_frozen_sources(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path)
    _write_cell(experiment, topic_num=1, suffix="-duplicate")
    with pytest.raises(TargetUserPilotError, match="duplicate"):
        discover_reports(experiment)

    duplicate = experiment / "cell-01-full-r1-duplicate"
    for path in duplicate.iterdir():
        path.unlink()
    duplicate.rmdir()
    packet = tmp_path / "packet"
    source_lock = tmp_path / "private" / "source-lock.json"
    prepare_pilot(experiment, packet, source_lock)
    report = experiment / "cell-01-full-r1" / "commercialization_report.md"
    report.write_text("changed after source lock", encoding="utf-8")
    with pytest.raises(TargetUserPilotError, match="source report or metadata drifted"):
        materialize_followup(experiment, packet, source_lock, "T01")


def test_materialize_requires_baseline_and_delivers_only_the_selected_report(tmp_path: Path) -> None:
    experiment, packet, source_lock = _prepare(tmp_path)
    with pytest.raises(TargetUserPilotError, match="intake must be complete"):
        materialize_followup(experiment, packet, source_lock, "T01")

    _fill_intake(packet, "T01", topic_num="03")
    snapshot = materialize_followup(experiment, packet, source_lock, "T01")
    delivered = (packet / "stage-2" / "T01" / "report.md").read_text(encoding="utf-8")
    assert snapshot["selected_topic_num"] == "03"
    assert "FROZEN_REPORT_03" in delivered
    assert "FROZEN_REPORT_01" not in delivered
    assert snapshot["source_report_sha256"] == snapshot["delivered_report_sha256"]
    assert not (packet / "stage-2" / "T02").exists()

    with pytest.raises(TargetUserPilotError, match="already exists"):
        materialize_followup(experiment, packet, source_lock, "T01")


def test_summary_distinguishes_open_stages_and_single_target_user(tmp_path: Path) -> None:
    experiment, packet, source_lock = _prepare(tmp_path)
    initial = summarize_pilot(experiment, packet, source_lock)
    assert initial["status"] == "in_progress"
    assert {row["status"] for row in initial["reviewers"]} == {"not_started"}

    _fill_intake(packet, "T01", topic_num="01")
    awaiting_report = summarize_pilot(experiment, packet, source_lock)
    assert awaiting_report["reviewers"][0]["status"] == "report_not_materialized"

    materialize_followup(experiment, packet, source_lock, "T01")
    awaiting_followup = summarize_pilot(experiment, packet, source_lock)
    assert awaiting_followup["reviewers"][0]["status"] == "followup_incomplete"

    _fill_followup(packet, "T01")
    _close_slot(packet, "T02")
    result = summarize_pilot(experiment, packet, source_lock)
    assert result["status"] == "single_target_user_observation"
    assert result["eligible_target_user_count"] == 1
    assert result["decision_changed_count"] == 1
    assert result["eligible_medians"]["decision_usefulness"] == 4.0
    assert result["reviewers"][0]["derived"]["source_truth_status"] == "not_evaluated"


def test_two_target_users_complete_but_public_projection_respects_consent(tmp_path: Path) -> None:
    experiment, packet, source_lock = _prepare(tmp_path)
    _fill_intake(packet, "T01", topic_num="01", consent="YES")
    _fill_intake(packet, "T02", topic_num="02", consent="NO")
    materialize_followup(experiment, packet, source_lock, "T01")
    materialize_followup(experiment, packet, source_lock, "T02")
    _fill_followup(packet, "T01", usefulness=5)
    _fill_followup(packet, "T02", usefulness=2)

    result = summarize_pilot(experiment, packet, source_lock)
    public = result["public_projection"]
    assert result["status"] == "descriptive_pilot_complete"
    assert result["eligible_target_user_count"] == 2
    assert result["eligible_medians"]["decision_usefulness"] == 3.5
    assert public["publicly_reportable_count"] == 1
    assert public["eligible_medians"]["decision_usefulness"] == 5.0
    assert public["status"] == "descriptive_pilot_complete"
    assert public["publication_status"] == "partial_public_consent"
    assert public["complete_observation_count"] == 2
    assert public["closed_slot_count"] == 0
    assert public["incomplete_slot_count"] == 0
    assert public["reportable_role_mix"] == {"TTO_COMMERCIALIZATION": 1}
    assert public["reportable_ai_use"] == {"NONE": 1}
    assert public["reportable_selected_topics"] == [
        {"topic_num": "01", "topic": "Commercialization topic 01"}
    ]
    assert public["source_material"] == {
        "report_generation_date": "2026-08-21",
        "evidence_state": "frozen_historical",
        "fresh_retrieval": False,
        "topic_assignment": "reviewer_self_selected_before_report",
    }


def test_proxy_and_substantive_ai_rows_do_not_become_target_user_evidence(tmp_path: Path) -> None:
    experiment, packet, source_lock = _prepare(tmp_path)
    _fill_intake(packet, "T01", topic_num="01", role="PROXY")
    _fill_intake(packet, "T02", topic_num="02", ai_use="SUBSTANTIVE")
    for reviewer_id in ("T01", "T02"):
        materialize_followup(experiment, packet, source_lock, reviewer_id)
        _fill_followup(packet, reviewer_id)

    result = summarize_pilot(experiment, packet, source_lock)
    assert result["status"] == "no_eligible_target_user_observation"
    assert result["eligible_target_user_count"] == 0
    assert result["proxy_completed_count"] == 1
    assert result["substantive_ai_excluded_count"] == 1


def test_unchecked_sources_cannot_be_reported_as_zero_errors(tmp_path: Path) -> None:
    experiment, packet, source_lock = _prepare(tmp_path)
    _fill_intake(packet, "T01", topic_num="01")
    materialize_followup(experiment, packet, source_lock, "T01")
    _fill_followup(packet, "T01", citation_check="NONE", factual_error_state="NONE_FOUND")

    with pytest.raises(TargetUserPilotError, match="without source checking"):
        summarize_pilot(experiment, packet, source_lock)


def test_snapshot_and_delivered_report_drift_fail_at_the_summary_seam(tmp_path: Path) -> None:
    experiment, packet, source_lock = _prepare(tmp_path)
    _fill_intake(packet, "T01", topic_num="01")
    materialize_followup(experiment, packet, source_lock, "T01")
    _fill_followup(packet, "T01")
    _close_slot(packet, "T02")

    delivered = packet / "stage-2" / "T01" / "report.md"
    original = delivered.read_text(encoding="utf-8")
    delivered.write_text(original + "\nmutated after delivery\n", encoding="utf-8")
    with pytest.raises(TargetUserPilotError, match="delivered report drifted"):
        summarize_pilot(experiment, packet, source_lock)

    delivered.write_text(original, encoding="utf-8")
    baseline_path = packet / "stage-1" / "T01" / "baseline_form.csv"
    baseline = _read_csv(baseline_path)[0]
    baseline["initial_confidence"] = "3"
    _write_csv(baseline_path, BASELINE_FIELDS, [baseline])
    with pytest.raises(TargetUserPilotError, match="baseline_sha256"):
        summarize_pilot(experiment, packet, source_lock)


def test_summary_files_are_immutable_and_public_output_drops_free_text(tmp_path: Path) -> None:
    experiment, packet, source_lock = _prepare(tmp_path)
    _fill_intake(packet, "T01", topic_num="01")
    materialize_followup(experiment, packet, source_lock, "T01")
    _fill_followup(packet, "T01")
    _close_slot(packet, "T02")
    result = summarize_pilot(experiment, packet, source_lock)

    private_path = tmp_path / "private-result.json"
    public_path = tmp_path / "public-result.json"
    write_summaries(private_path, public_path, result)
    assert "most_useful_content" in private_path.read_text(encoding="utf-8")
    assert "most_useful_content" not in public_path.read_text(encoding="utf-8")
    with pytest.raises(TargetUserPilotError, match="already exists"):
        write_summary(private_path, result)

    unwritten_private = tmp_path / "must-not-be-partially-written.json"
    with pytest.raises(TargetUserPilotError, match="already exists"):
        write_summaries(unwritten_private, public_path, result)
    assert not unwritten_private.exists()

    same_path = tmp_path / "same-output.json"
    with pytest.raises(TargetUserPilotError, match="must be distinct"):
        write_summaries(same_path, same_path, result)
