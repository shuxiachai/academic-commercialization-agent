"""Regression tests for the blinded Reviewer-value audit boundary."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import reviewer_audit


def _write_cell(
    root: Path,
    name: str,
    *,
    corrections: int = 2,
    status: str = "success",
) -> Path:
    cell = root / name
    cell.mkdir(parents=True)
    meta = {
        "variant": "full",
        "status": status,
        "topic": f"Topic for {name}",
        "reviewer_corrections": corrections,
        "usage": {
            "agents": [
                {
                    "role": "Scientific Report Quality Reviewer",
                    "cost_usd": 0.0123,
                }
            ]
        },
    }
    (cell / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (cell / "draft_report.md").write_text(
        f"# Report {name}\n\nA claim without a citation.\n", encoding="utf-8"
    )
    (cell / "commercialization_report.md").write_text(
        f"# Report {name}\n\nA claim with a citation [A1].\n\n"
        "## Reviewer Notes\n\n- Added support.\n",
        encoding="utf-8",
    )
    return cell


def _read_form(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_form(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=reviewer_audit.FORM_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_prepare_packet_blinds_identity_at_every_reviewer_seam(tmp_path: Path) -> None:
    """Regression: a hidden key is useless if identity leaks into the packet."""

    experiment = tmp_path / "experiment"
    _write_cell(experiment, "001-topic-full-r1", corrections=2)
    _write_cell(experiment, "002-topic-full-r2", corrections=3)
    packet = tmp_path / "packet"
    key_path = tmp_path / "private" / "answer-key.json"

    manifest = reviewer_audit.prepare_packet(
        experiment, packet, key_path, seed=42
    )

    assert manifest["case_count"] == 2
    assert manifest["declared_correction_count"] == 5
    assert "reviewed_side" not in (packet / "manifest.json").read_text(encoding="utf-8")
    assert "source_cell" not in (packet / "manifest.json").read_text(encoding="utf-8")
    assert "Reviewer Notes" not in (packet / "R01" / "A.md").read_text(encoding="utf-8")
    assert "Reviewer Notes" not in (packet / "R01" / "B.md").read_text(encoding="utf-8")

    rows = _read_form(packet / "review_form.csv")
    key = json.loads(key_path.read_text(encoding="utf-8"))
    assert [row["sample_id"] for row in rows] == ["R01", "R02"]
    assert {case["sample_id"] for case in key["cases"]} == {"R01", "R02"}
    assert all(row["preferred_version"] == "" for row in rows)
    for case in key["cases"]:
        sample = packet / case["sample_id"]
        for side in ("A", "B"):
            body = (sample / f"{side}.md").read_text(encoding="utf-8").rstrip()
            assert reviewer_audit._sha256(body) == case["report_sha256"][side]


def test_prepare_packet_rejects_answer_key_inside_blinded_packet(tmp_path: Path) -> None:
    experiment = tmp_path / "experiment"
    _write_cell(experiment, "001-topic-full-r1")

    with pytest.raises(reviewer_audit.AuditDataError, match="outside"):
        reviewer_audit.prepare_packet(
            experiment,
            tmp_path / "packet",
            tmp_path / "packet" / "answer-key.json",
            seed=1,
        )


def test_discovery_distinguishes_missing_artifact_from_no_change(tmp_path: Path) -> None:
    """A declared correction with no delivered file is not an empty audit."""

    experiment = tmp_path / "experiment"
    cell = _write_cell(experiment, "001-topic-full-r1")
    (cell / "commercialization_report.md").unlink()

    with pytest.raises(reviewer_audit.AuditDataError, match="missing"):
        reviewer_audit.discover_review_cases(experiment)


def test_summary_keeps_unfilled_rows_distinct_from_ties(tmp_path: Path) -> None:
    experiment = tmp_path / "experiment"
    _write_cell(experiment, "001-topic-full-r1")
    packet = tmp_path / "packet"
    key_path = tmp_path / "answer-key.json"
    reviewer_audit.prepare_packet(experiment, packet, key_path, seed=7)

    summary = reviewer_audit.summarize_form(packet / "review_form.csv", key_path)

    assert summary["protocol_status"] == "incomplete"
    assert summary["completed_case_count"] == 0
    assert summary["incomplete_sample_ids"] == ["R01"]
    assert summary["outcomes"]["preferred_version"]["tie"] == 0
    assert summary["pre_registered_criterion_passed"] is None


def test_summary_unblinds_relative_outcomes_without_changing_labels(
    tmp_path: Path,
) -> None:
    experiment = tmp_path / "experiment"
    _write_cell(experiment, "001-topic-full-r1")
    packet = tmp_path / "packet"
    key_path = tmp_path / "answer-key.json"
    reviewer_audit.prepare_packet(experiment, packet, key_path, seed=9)
    key = json.loads(key_path.read_text(encoding="utf-8"))
    reviewed = key["cases"][0]["reviewed_side"]
    draft = "B" if reviewed == "A" else "A"
    rows = _read_form(packet / "review_form.csv")
    rows[0].update(
        {
            "preferred_version": reviewed,
            "citation_support": reviewed,
            "decision_usefulness": "TIE",
            "harmful_version": draft,
            "confidence": "4",
            "notes": "The reviewed side adds support without changing the claim.",
        }
    )
    _write_form(packet / "review_form.csv", rows)

    summary = reviewer_audit.summarize_form(packet / "review_form.csv", key_path)

    assert summary["protocol_status"] == "complete"
    assert summary["outcomes"]["preferred_version"]["reviewed"] == 1
    assert summary["outcomes"]["citation_support"]["reviewed"] == 1
    assert summary["outcomes"]["decision_usefulness"]["tie"] == 1
    assert summary["outcomes"]["harmful_version"]["draft"] == 1


def test_summary_rejects_form_with_missing_or_extra_samples(tmp_path: Path) -> None:
    experiment = tmp_path / "experiment"
    _write_cell(experiment, "001-topic-full-r1")
    packet = tmp_path / "packet"
    key_path = tmp_path / "answer-key.json"
    reviewer_audit.prepare_packet(experiment, packet, key_path, seed=11)
    _write_form(packet / "review_form.csv", [])

    with pytest.raises(reviewer_audit.AuditDataError, match="do not match"):
        reviewer_audit.summarize_form(packet / "review_form.csv", key_path)

def test_summary_rejects_duplicate_sample_that_would_inflate_outcome(
    tmp_path: Path,
) -> None:
    experiment = tmp_path / "experiment"
    _write_cell(experiment, "001-topic-full-r1")
    packet = tmp_path / "packet"
    key_path = tmp_path / "answer-key.json"
    reviewer_audit.prepare_packet(experiment, packet, key_path, seed=13)
    rows = _read_form(packet / "review_form.csv")
    _write_form(packet / "review_form.csv", [rows[0], rows[0]])

    with pytest.raises(reviewer_audit.AuditDataError, match="do not match"):
        reviewer_audit.summarize_form(packet / "review_form.csv", key_path)
