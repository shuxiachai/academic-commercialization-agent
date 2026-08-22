"""Contract tests for the frozen-evidence patent relevance audit."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import patent_relevance_eval as patent_eval


def _patent(source_id: str, *, url: str | None = None) -> dict[str, str]:
    return {
        "source_id": source_id,
        "title": f"Patent {source_id}",
        "url": url or f"https://patents.example/{source_id}",
        "evidence_summary": f"Evidence summary for {source_id}.",
    }


def _write_payload(
    path: Path,
    *,
    topic: str,
    patents: list[dict[str, str]],
    corpus: str | None = None,
) -> None:
    payload: dict[str, object] = {"topic": topic, "patent_sources": patents}
    if corpus is not None:
        payload["corpus"] = corpus
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_labels(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=patent_eval.LABEL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_preregistered_public_census_remains_75_core_plus_6_challenge() -> None:
    """Fixture drift must not silently change the pre-registered denominator."""

    root = Path(__file__).resolve().parents[1]
    cases = patent_eval.discover_cases(
        root / "benchmark_fixtures",
        [
            root
            / "evals"
            / "patent_relevance"
            / "sodium-ion-grid-storage-challenge.json"
        ],
    )

    assert len(cases) == 81
    assert sum(case.corpus == "benchmark_core" for case in cases) == 75
    assert (
        sum(case.corpus == "sodium_ion_grid_storage_challenge" for case in cases)
        == 6
    )
    assert len({case.topic for case in cases}) == 11


def _packet(tmp_path: Path) -> Path:
    fixtures = tmp_path / "fixtures"
    _write_payload(
        fixtures / "01-alpha.json",
        topic="Alpha storage",
        patents=[_patent("P1"), _patent("P2")],
    )
    challenge = tmp_path / "challenge.json"
    _write_payload(
        challenge,
        topic="Beta sensing",
        patents=[_patent("P1", url="https://patents.example/beta")],
        corpus="post_hoc_challenge",
    )
    packet = tmp_path / "packet"
    patent_eval.prepare_packet(fixtures, packet, challenge_paths=[challenge])
    return packet


def test_prepare_packet_preserves_every_patent_at_the_human_label_seam(
    tmp_path: Path,
) -> None:
    """A source stored in fixtures is useless if it never reaches the label form."""

    packet = _packet(tmp_path)
    manifest = json.loads((packet / "manifest.json").read_text(encoding="utf-8"))
    index = _read_csv(packet / "case_index.csv")
    labels = _read_csv(packet / "labels.csv")

    assert manifest["case_count"] == 3
    assert manifest["corpus_counts"] == {"benchmark_core": 2, "post_hoc_challenge": 1}
    manifest_ids = {case["case_id"] for case in manifest["cases"]}
    assert {row["case_id"] for row in index} == manifest_ids
    assert {row["case_id"] for row in labels} == manifest_ids
    assert all(row["label"] == "" for row in labels)
    assert (packet / "reviewer_declaration.md").is_file()
    assert "corpus" not in index[0]
    for case in manifest["cases"]:
        case_path = packet / "cases" / f"{case['case_id']}.md"
        assert case_path.is_file()
        card = case_path.read_text(encoding="utf-8")
        assert "**Corpus:**" not in card
        assert patent_eval._sha256(card) == case[
            "content_sha256"
        ]


def test_discovery_rejects_duplicate_topic_url_that_would_inflate_precision(
    tmp_path: Path,
) -> None:
    fixtures = tmp_path / "fixtures"
    repeated_url = "https://patents.example/repeated"
    _write_payload(
        fixtures / "01-alpha.json",
        topic="Alpha storage",
        patents=[_patent("P1", url=repeated_url)],
    )
    _write_payload(
        fixtures / "02-alpha-again.json",
        topic="Alpha storage",
        patents=[_patent("P2", url=repeated_url)],
    )

    with pytest.raises(patent_eval.PatentAuditError, match="duplicate topic/URL"):
        patent_eval.discover_cases(fixtures)


def test_prepare_refuses_to_overwrite_a_started_human_audit(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    fixtures = tmp_path / "other-fixtures"
    _write_payload(fixtures / "01.json", topic="Other", patents=[_patent("P1")])

    with pytest.raises(patent_eval.PatentAuditError, match="overwrite"):
        patent_eval.prepare_packet(fixtures, packet)


def test_blank_rows_are_incomplete_and_never_become_zero_error_precision(
    tmp_path: Path,
) -> None:
    packet = _packet(tmp_path)

    summary = patent_eval.summarize_labels(
        packet / "labels.csv", packet / "manifest.json"
    )

    assert summary["protocol_status"] == "incomplete"
    assert summary["completed_case_count"] == 0
    assert len(summary["incomplete_case_ids"]) == 3
    assert summary["metrics"] is None
    assert summary["by_corpus"] is None


def test_summary_keeps_uncertain_in_every_headline_denominator(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    rows = _read_csv(packet / "labels.csv")
    labels = ["RELEVANT", "WEAK", "UNCERTAIN"]
    for row, label in zip(rows, labels, strict=True):
        row.update({"label": label, "confidence": "4", "rationale": f"Reason for {label}"})
    _write_labels(packet / "labels.csv", rows)

    summary = patent_eval.summarize_labels(
        packet / "labels.csv", packet / "manifest.json"
    )

    assert summary["protocol_status"] == "complete"
    assert summary["metrics"]["case_count"] == 3
    assert summary["metrics"]["direct_relevance_rate"] == pytest.approx(1 / 3)
    assert summary["metrics"]["usable_relevance_rate"] == pytest.approx(2 / 3)
    assert summary["metrics"]["uncertain_rate"] == pytest.approx(1 / 3)
    assert sum(group["case_count"] for group in summary["by_corpus"].values()) == 3
    assert sum(group["case_count"] for group in summary["by_topic"].values()) == 3


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate"])
def test_summary_rejects_case_id_drift_instead_of_changing_the_denominator(
    tmp_path: Path,
    mutation: str,
) -> None:
    packet = _packet(tmp_path)
    rows = _read_csv(packet / "labels.csv")
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append({"case_id": "PR-EXTRA", "label": "", "confidence": "", "rationale": ""})
    else:
        rows[-1] = rows[0].copy()
    _write_labels(packet / "labels.csv", rows)

    with pytest.raises(patent_eval.PatentAuditError, match="case IDs|duplicate"):
        patent_eval.summarize_labels(packet / "labels.csv", packet / "manifest.json")


def test_summary_rejects_a_partially_completed_row(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    rows = _read_csv(packet / "labels.csv")
    rows[0]["label"] = "RELEVANT"
    _write_labels(packet / "labels.csv", rows)

    with pytest.raises(patent_eval.PatentAuditError, match="partially completed"):
        patent_eval.summarize_labels(packet / "labels.csv", packet / "manifest.json")


def test_freeze_challenge_keeps_public_patents_and_drops_unrelated_run_data(
    tmp_path: Path,
) -> None:
    source = tmp_path / "run-123" / "validated_sources.json"
    payload = {
        "topic": "Sodium-ion storage",
        "collected_at": "2026-08-22T00:00:00Z",
        "patent_sources": [_patent("P1")],
        "academic_sources": [{"secret": "not part of this audit"}],
        "market_sources": [{"secret": "not part of this audit"}],
    }
    source.parent.mkdir()
    source.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "challenge.json"

    frozen = patent_eval.freeze_challenge(
        source,
        output,
        corpus="sodium_ion_challenge",
        selection_note="All accepted patents from the observed failure run.",
    )

    assert frozen["source_run_id"] == "run-123"
    assert frozen["patent_sources"] == payload["patent_sources"]
    assert "academic_sources" not in frozen
    assert "market_sources" not in frozen
    assert json.loads(output.read_text(encoding="utf-8")) == frozen


def test_freeze_challenge_refuses_to_replace_a_frozen_measurement(tmp_path: Path) -> None:
    source = tmp_path / "run" / "validated_sources.json"
    _write_payload(source, topic="Topic", patents=[_patent("P1")])
    output = tmp_path / "challenge.json"
    output.write_text("{}", encoding="utf-8")

    with pytest.raises(patent_eval.PatentAuditError, match="overwrite"):
        patent_eval.freeze_challenge(
            source,
            output,
            corpus="challenge",
            selection_note="Observed failure.",
        )
