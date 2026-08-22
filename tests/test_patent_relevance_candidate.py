"""Contracts for the frozen, label-blind patent topic-slot candidate."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import patent_relevance_candidate as candidate
import patent_relevance_eval as patent_eval


def _case(
    *,
    topic: str,
    title: str,
    summary: str,
    case_id: str = "PR-SYNTHETIC",
    corpus: str = "synthetic",
) -> patent_eval.PatentCase:
    return patent_eval.PatentCase(
        case_id=case_id,
        corpus=corpus,
        topic=topic,
        source_id="P1",
        title=title,
        url=f"https://patents.example/{case_id}",
        evidence_summary=summary,
        provenance="synthetic.json",
    )


def test_missing_technology_anchor_is_the_only_auto_drop_path() -> None:
    decision = candidate.screen_case(
        _case(
            topic="room temperature ambient pressure superconductors",
            title="Friction activated adhesive solid at room temperature",
            summary="A crystalline polymer adhesive is activated by friction.",
        )
    )

    assert decision.action == "DROP"
    assert decision.technology_anchor == "superconductor"
    assert not decision.technology_in_title
    assert not decision.technology_in_evidence


def test_missing_application_slot_routes_to_review_instead_of_drop() -> None:
    decision = candidate.screen_case(
        _case(
            topic="sodium-ion batteries for grid energy storage",
            title="Safe transport of sodium-ion battery cells",
            summary="Rechargeable sodium cells can be shipped and stored in a warehouse.",
        )
    )

    assert decision.action == "REVIEW"
    assert decision.application_tokens == ("grid", "energy", "storage")
    assert "no bounded support" in decision.reason


def test_generic_application_list_routes_to_review() -> None:
    decision = candidate.screen_case(
        _case(
            topic="quantum computing for drug discovery",
            title="Modular quantum computing system",
            summary=(
                "Merely by way of example, the invention can be applied to a variety "
                "of applications such as cryptography, drug discovery, finance, and weather."
            ),
        )
    )

    assert decision.action == "REVIEW"
    assert decision.application_in_evidence
    assert "merely by way of example" in decision.weak_context_markers


def test_application_supported_in_title_is_kept_even_if_summary_lists_examples() -> None:
    decision = candidate.screen_case(
        _case(
            topic="quantum computing for drug discovery",
            title="Quantum computing method for drug discovery",
            summary="Applications include cryptography, finance, and drug discovery.",
        )
    )

    assert decision.action == "KEEP"
    assert decision.application_in_title


def test_focused_application_support_in_evidence_is_kept() -> None:
    decision = candidate.screen_case(
        _case(
            topic="sodium-ion batteries for grid energy storage",
            title="Sodium ion battery architecture",
            summary=(
                "The battery is integrated with grid energy storage controls for "
                "stationary utility operation."
            ),
        )
    )

    assert decision.action == "KEEP"
    assert decision.application_in_evidence
    assert not decision.weak_context_markers


def test_topic_without_for_skips_the_application_slot() -> None:
    decision = candidate.screen_case(
        _case(
            topic="graphene-based flexible electronics",
            title="Conformal graphene electronic sensor",
            summary="A flexible conductor is fabricated on a polymer substrate.",
        )
    )

    assert decision.action == "KEEP"
    assert decision.application_tokens == ()


def _write_fixture(path: Path) -> None:
    payload = {
        "topic": "alpha platforms for clinical disease",
        "patent_sources": [
            {
                "source_id": "P1",
                "title": "Alpha platform for clinical disease",
                "url": "https://patents.example/keep",
                "evidence_summary": "A focused clinical disease alpha platform.",
            },
            {
                "source_id": "P2",
                "title": "Alpha platform",
                "url": "https://patents.example/review",
                "evidence_summary": "A general alpha platform for laboratory use.",
            },
            {
                "source_id": "P3",
                "title": "Unrelated mechanical fixture",
                "url": "https://patents.example/drop",
                "evidence_summary": "A mechanical fixture for joining two beams.",
            },
        ],
    }
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _complete_packet(tmp_path: Path) -> tuple[Path, Path, Path]:
    fixtures = tmp_path / "fixtures"
    _write_fixture(fixtures / "01-alpha.json")
    packet = tmp_path / "packet"
    patent_eval.prepare_packet(fixtures, packet)
    with (packet / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row, label in zip(rows, ("RELEVANT", "WEAK", "IRRELEVANT"), strict=True):
        row.update(
            {
                "label": label,
                "confidence": "5",
                "rationale": f"Synthetic {label.lower()} case.",
            }
        )
    with (packet / "labels.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=patent_eval.LABEL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return fixtures, packet / "labels.csv", packet / "manifest.json"


def test_evaluation_preserves_every_decision_at_the_output_boundary(
    tmp_path: Path,
) -> None:
    fixtures, labels, manifest = _complete_packet(tmp_path)
    result, rows = candidate.evaluate_candidate(fixtures, labels, manifest)
    output = tmp_path / "result"
    candidate.write_evaluation(output, result, rows)

    with (output / "decisions.csv").open(encoding="utf-8", newline="") as handle:
        delivered = list(csv.DictReader(handle))
    delivered_result = json.loads((output / "result.json").read_text(encoding="utf-8"))

    assert [row["action"] for row in delivered] == ["KEEP", "REVIEW", "DROP"]
    assert {row["case_id"] for row in delivered} == {
        case["case_id"]
        for case in json.loads(manifest.read_text(encoding="utf-8"))["cases"]
    }
    assert delivered_result == result
    assert result["metrics"]["action_counts"] == {
        "KEEP": 1,
        "REVIEW": 1,
        "DROP": 1,
    }
    assert result["metrics"]["keep_direct_precision"] == 1.0
    assert not result["qualified_for_held_out_challenge"]
    assert not result["production_change_authorized"]


def test_evaluation_refuses_case_content_drift(tmp_path: Path) -> None:
    fixtures, labels, manifest = _complete_packet(tmp_path)
    payload_path = fixtures / "01-alpha.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["patent_sources"][0]["evidence_summary"] = "Changed after human review."
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(candidate.PatentCandidateError, match="changed="):
        candidate.evaluate_candidate(fixtures, labels, manifest)


def test_evaluation_distinguishes_incomplete_labels_from_a_clean_result(
    tmp_path: Path,
) -> None:
    fixtures, labels, manifest = _complete_packet(tmp_path)
    with labels.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[-1].update({"label": "", "confidence": "", "rationale": ""})
    with labels.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=patent_eval.LABEL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(candidate.PatentCandidateError, match="requires a complete"):
        candidate.evaluate_candidate(fixtures, labels, manifest)


def test_writer_refuses_to_replace_a_previous_candidate_result(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()

    with pytest.raises(candidate.PatentCandidateError, match="overwrite"):
        candidate.write_evaluation(output, {}, [])
