"""Offline seam tests for the blinded user-utility audit artifacts."""

from __future__ import annotations
import csv
import json
from pathlib import Path

import pytest

from user_utility_audit import (
    FORM_FIELDS,
    PROFILE_FIELDS,
    UtilityAuditError,
    discover_cases,
    prepare_packet,
    summarize_packet,
    write_summary,
)


def _write_cell(
    experiment_dir: Path,
    *,
    topic_num: int,
    repetition: int,
    variant: str,
    fixture_digest: str | None = None,
) -> None:
    cell = experiment_dir / f"{topic_num:02d}-r{repetition}-{variant}"
    cell.mkdir(parents=True)
    topic = f"Benchmark research topic {topic_num:02d}"
    digest = fixture_digest or f"digest-{topic_num:02d}-r{repetition}"
    meta = {
        "num": f"{topic_num:02d}",
        "rep": repetition,
        "variant": variant,
        "topic": topic,
        "fixture_digest": digest,
        "status": "success",
    }
    (cell / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    label = "Detailed evidence synthesis" if variant == "full" else "Compact synthesis"
    report = (
        f"# Assessment: {topic}\n\n"
        f"{label} for repetition {repetition}. "
        "The evidence, caveats, and decision implications are intentionally comparable."
    )
    if variant == "full":
        report += "\n\n## Reviewer Notes\n\nNo corrections required."
    (cell / "commercialization_report.md").write_text(report, encoding="utf-8")


def _experiment(tmp_path: Path, *, repetitions: tuple[int, ...] = (1,)) -> Path:
    experiment_dir = tmp_path / "experiment"
    for topic_num in range(1, 11):
        for repetition in repetitions:
            for variant in ("monolith", "full"):
                _write_cell(
                    experiment_dir,
                    topic_num=topic_num,
                    repetition=repetition,
                    variant=variant,
                )
    return experiment_dir


def _prepare(tmp_path: Path, *, reviewer_count: int = 3) -> tuple[Path, Path, dict[str, object]]:
    packet = tmp_path / "packet"
    key_path = tmp_path / "private" / "answer-key.json"
    prepare_packet(
        _experiment(tmp_path),
        packet,
        key_path,
        reviewer_count=reviewer_count,
        seed=20260822,
    )
    key = json.loads(key_path.read_text(encoding="utf-8"))
    return packet, key_path, key


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _fill_profiles(packet: Path, reviewer_count: int, *, substantive: str | None = None) -> None:
    for index in range(1, reviewer_count + 1):
        reviewer_id = f"R{index:02d}"
        path = packet / "round-1" / reviewer_id / "reviewer_profile.csv"
        ai_use = "SUBSTANTIVE" if reviewer_id == substantive else "NONE"
        row = {
            "reviewer_id": reviewer_id,
            "role_category": "TARGET_USER",
            "relevant_experience_years": "3",
            "generative_ai_use": ai_use,
            "generative_ai_notes": ("AI generated substantive judgments." if ai_use == "SUBSTANTIVE" else ""),
        }
        _write_csv(path, PROFILE_FIELDS, [row])


def _fill_round(packet: Path, key: dict[str, object], round_num: int) -> None:
    assignments = {
        (item["reviewer_id"], item["case_id"]): item for item in key["assignments"] if item["round"] == round_num
    }
    for reviewer_id in sorted({item[0] for item in assignments}):
        path = packet / f"round-{round_num}" / reviewer_id / "review_form.csv"
        rows = _read_csv(path)
        for row in rows:
            assignment = assignments[(reviewer_id, row["case_id"])]
            full_side = assignment["full_side"]
            other_side = "B" if full_side == "A" else "A"
            row.update(
                {
                    "initial_decision": "DEFER",
                    "decision_after_a": "GO",
                    "decision_after_b": "GO",
                    "overall_preference": full_side,
                    "decision_usefulness": full_side,
                    "information_gain": full_side,
                    "actionability": full_side,
                    "citation_trust": full_side,
                    "recommendation_acceptance_a": "5" if full_side == "A" else "3",
                    "recommendation_acceptance_b": "5" if full_side == "B" else "3",
                    "reading_minutes_a": "12",
                    "reading_minutes_b": "12",
                    "revision_minutes_a": "2" if full_side == "A" else "8",
                    "revision_minutes_b": "2" if full_side == "B" else "8",
                    "citation_check": "SOME",
                    "factual_errors_a": "0",
                    "factual_errors_b": "0",
                    "confidence": "4",
                    "rationale": (
                        f"Version {full_side} provided clearer evidence and more actionable "
                        f"decision support than version {other_side}."
                    ),
                }
            )
        _write_csv(path, FORM_FIELDS, rows)


def test_discovery_uses_earliest_pair_and_strips_reviewer_appendix(
    tmp_path: Path,
) -> None:
    cases = discover_cases(_experiment(tmp_path, repetitions=(1, 2)))

    assert len(cases) == 10
    assert {case.repetition for case in cases} == {1}
    assert all("Reviewer Notes" not in case.full.body for case in cases)
    assert all(case.monolith.fixture_digest == case.full.fixture_digest for case in cases)


def test_discovery_rejects_a_mismatched_frozen_evidence_digest(
    tmp_path: Path,
) -> None:
    experiment_dir = _experiment(tmp_path)
    meta_path = experiment_dir / "01-r1-full" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["fixture_digest"] = "different-evidence"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    with pytest.raises(UtilityAuditError, match="mismatched fixture digests"):
        discover_cases(experiment_dir)


@pytest.mark.parametrize(
    ("reviewer_count", "expected_loads"),
    [(3, [3, 3, 4]), (4, [2, 2, 3, 3]), (5, [2, 2, 2, 2, 2])],
)
def test_packet_is_balanced_blinded_and_rotated_at_the_file_seam(
    tmp_path: Path, reviewer_count: int, expected_loads: list[int]
) -> None:
    packet, key_path, key = _prepare(tmp_path, reviewer_count=reviewer_count)
    manifest_text = (packet / "manifest.json").read_text(encoding="utf-8").lower()
    manifest = json.loads(manifest_text)

    assert key_path.parent != packet
    assert "monolith" not in manifest_text
    assert '"full"' not in manifest_text
    assert manifest["review_status"] == "not_started"

    assignments = key["assignments"]
    for round_num in (1, 2):
        selected = [item for item in assignments if item["round"] == round_num]
        assert len(selected) == 10
        assert len({item["case_id"] for item in selected}) == 10
        loads = sorted(manifest["rounds"][str(round_num)]["reviewer_loads"].values())
        assert loads == expected_loads

    for case in key["cases"]:
        reviewers = {item["reviewer_id"] for item in assignments if item["case_id"] == case["case_id"]}
        assert len(reviewers) == 2

    for assignment in assignments:
        case_dir = packet / f"round-{assignment['round']}" / assignment["reviewer_id"] / "cases" / assignment["case_id"]
        for side in ("A", "B"):
            body = (case_dir / f"{side}.md").read_text(encoding="utf-8")
            assert "Reviewer Notes" not in body


def test_prepare_rejects_bad_reviewer_count_key_leak_and_overwrite(
    tmp_path: Path,
) -> None:
    experiment_dir = _experiment(tmp_path)

    with pytest.raises(UtilityAuditError, match="between 3 and 5"):
        prepare_packet(
            experiment_dir,
            tmp_path / "bad-count",
            tmp_path / "bad-count-key.json",
            reviewer_count=2,
            seed=1,
        )
    with pytest.raises(UtilityAuditError, match="outside"):
        prepare_packet(
            experiment_dir,
            tmp_path / "leaky",
            tmp_path / "leaky" / "answer-key.json",
            reviewer_count=3,
            seed=1,
        )

    packet = tmp_path / "once"
    key = tmp_path / "private" / "once-key.json"
    prepare_packet(experiment_dir, packet, key, reviewer_count=3, seed=1)
    with pytest.raises(UtilityAuditError, match="must not already exist"):
        prepare_packet(experiment_dir, packet, key, reviewer_count=3, seed=1)


def test_blank_packet_is_not_started_instead_of_a_tie_or_pass(
    tmp_path: Path,
) -> None:
    packet, key_path, _ = _prepare(tmp_path)

    result = summarize_packet(packet, key_path)

    assert result["protocol_status"] == "not_started"
    assert result["primary_criterion_passed"] is None
    primary = result["rounds"][0]
    assert primary["raw_completed_count"] == 0
    assert primary["eligible_completed_count"] == 0
    assert sum(primary["outcomes"]["decision_usefulness"].values()) == 0


def test_complete_primary_round_is_unblinded_against_the_frozen_criterion(
    tmp_path: Path,
) -> None:
    packet, key_path, key = _prepare(tmp_path)
    _fill_profiles(packet, 3)
    _fill_round(packet, key, 1)

    result = summarize_packet(packet, key_path)

    assert result["protocol_status"] == "complete"
    assert result["primary_criterion_passed"] is True
    primary = result["rounds"][0]
    assert primary["eligible_completed_count"] == 10
    assert primary["eligible_reviewer_count"] == 3
    assert primary["outcomes"]["decision_usefulness"]["full"] == 10
    assert result["rounds"][1]["protocol_status"] == "not_started"


def test_substantive_ai_judgments_are_retained_but_excluded(tmp_path: Path) -> None:
    packet, key_path, key = _prepare(tmp_path)
    _fill_profiles(packet, 3, substantive="R01")
    _fill_round(packet, key, 1)

    result = summarize_packet(packet, key_path)

    primary = result["rounds"][0]
    assert result["protocol_status"] == "ai_excluded"
    assert result["primary_criterion_passed"] is None
    assert primary["eligible_completed_count"] == 6
    assert len(primary["excluded_assignment_ids"]) == 4
    assert result["substantive_ai_reviewers"] == ["R01"]


def test_unchecked_citations_cannot_be_reported_as_zero_errors(tmp_path: Path) -> None:
    packet, key_path, key = _prepare(tmp_path)
    _fill_profiles(packet, 3)
    _fill_round(packet, key, 1)
    path = packet / "round-1" / "R01" / "review_form.csv"
    rows = _read_csv(path)
    rows[0]["citation_check"] = "NONE"
    rows[0]["citation_trust"] = "NOT_CHECKED"
    rows[0]["factual_errors_a"] = "0"
    rows[0]["factual_errors_b"] = "NOT_CHECKED"
    _write_csv(path, FORM_FIELDS, rows)

    with pytest.raises(UtilityAuditError, match="without checking"):
        summarize_packet(packet, key_path)


def test_partial_response_is_an_error_not_an_incomplete_row(tmp_path: Path) -> None:
    packet, key_path, _ = _prepare(tmp_path)
    path = packet / "round-1" / "R01" / "review_form.csv"
    rows = _read_csv(path)
    rows[0]["initial_decision"] = "DEFER"
    _write_csv(path, FORM_FIELDS, rows)

    with pytest.raises(UtilityAuditError, match="partially completed"):
        summarize_packet(packet, key_path)


def test_summary_rejects_report_and_assignment_drift(tmp_path: Path) -> None:
    packet, key_path, key = _prepare(tmp_path)
    first = key["assignments"][0]
    report = packet / f"round-{first['round']}" / first["reviewer_id"] / "cases" / first["case_id"] / "A.md"
    report.write_text(report.read_text(encoding="utf-8") + "changed", encoding="utf-8")
    with pytest.raises(UtilityAuditError, match="drifted"):
        summarize_packet(packet, key_path)

    packet_two, key_path_two, key_two = _prepare(tmp_path / "second", reviewer_count=3)
    key_two["assignments"][1] = dict(key_two["assignments"][0])
    key_path_two.write_text(json.dumps(key_two), encoding="utf-8")
    with pytest.raises(UtilityAuditError, match="duplicate assignment"):
        summarize_packet(packet_two, key_path_two)


def test_summary_output_is_immutable(tmp_path: Path) -> None:
    output = tmp_path / "summary.json"
    write_summary(output, {"protocol_status": "not_started"})

    with pytest.raises(UtilityAuditError, match="refusing to overwrite"):
        write_summary(output, {"protocol_status": "complete"})
