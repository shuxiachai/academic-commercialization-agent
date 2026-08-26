"""Zero-network seams for the frozen Phase-3 human evidence-value review."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path

import pytest

import evidence_gap_phase3_review as phase3_review
from evidence_gap_phase3_review import (
    CANDIDATE_FIELDS,
    DECLARATION_FIELDS,
    FROZEN_CASES,
    REVIEW_FIELDS,
    SOURCE_FILES,
    Phase3ReviewError,
    prepare_packet,
    summarize_packet,
    write_summary,
)


def _write_csv(
    path: Path,
    fields: tuple[str, ...],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _source_hashes(source: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in SOURCE_FILES
    }


def _source_case(case_id: str, context: dict[str, str]) -> dict[str, object]:
    """Expose the same synthetic baseline shape that the real reviewer must see."""

    gap_subject = context["gap_subject"]
    retrieval_failed = context["gap_code"] == "retrieval_domain_failed"
    return {
        "collection_sha256": hashlib.sha256(case_id.encode()).hexdigest(),
        "source_collection": {
            "academic_sources": [
                {
                    "source_id": "A1",
                    "title": f"{case_id} frozen baseline placeholder",
                    "url": f"https://doi.org/10.5555/{case_id.lower()}",
                    "evidence_summary": (
                        "Synthetic schema-valid baseline evidence that explicitly does "
                        "not answer the declared gap."
                    ),
                }
            ],
            "patent_sources": [],
            "market_sources": [],
            "failed_domains": (
                {gap_subject: "frozen provider-compatibility retrieval failure"}
                if retrieval_failed
                else {}
            ),
            "authority_coverage": {
                "status": "not_applicable" if retrieval_failed else "incomplete",
                "required_categories": [] if retrieval_failed else [gap_subject],
                "missing_categories": [] if retrieval_failed else [gap_subject],
                "covered_source_ids": {},
            },
        },
        "spec": {"case_id": case_id, **context},
    }


def _build_source(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Build a synthetic source with the same frozen seams, never the network."""

    source = tmp_path / "source"
    source.mkdir()
    manifest = {
        "mode": "phase3_frozen_provider_compatibility",
        "production_connected": False,
        "cases": [
            _source_case(case_id, context)
            for case_id, context in FROZEN_CASES.items()
        ],
    }
    execution = {
        "mode": "phase3_live_provider_compatibility",
        "request_count": 5,
        "completed_case_count": 5,
        "review_state": "not_inspected",
        "production_connected": False,
        "report_workflow_connected": False,
    }
    (source / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    (source / "execution.json").write_text(
        json.dumps(execution, indent=2),
        encoding="utf-8",
    )

    candidate_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    for case_id in FROZEN_CASES:
        for index in range(1, 6):
            source_id = f"SRC-{case_id}-{index}"
            title = f"{case_id} accepted evidence candidate {index}"
            url = f"https://example.com/{case_id.lower()}/{index}"
            candidate_rows.append(
                {
                    "case_id": case_id,
                    "tool": "academic_search",
                    "provider_request_id": f"request-{case_id}",
                    "provider_result_index": str(index - 1),
                    "adapter_disposition": "candidate",
                    "local_disposition": "quarantined_accepted",
                    "accepted_source_id": source_id,
                    "title": title,
                    "url": url,
                    "provider_rejection_code": "",
                    "local_rejection_code": "",
                    "rejection_detail": "",
                    "trace_id": f"trace-{case_id}",
                }
            )
            review_rows.append(
                {
                    "case_id": case_id,
                    "accepted_source_id": source_id,
                    "title": title,
                    "url": url,
                    "relevant": "",
                    "novel": "",
                    "review_note": "",
                }
            )
    _write_csv(source / "candidates.csv", CANDIDATE_FIELDS, candidate_rows)
    _write_csv(source / "review.csv", REVIEW_FIELDS, review_rows)
    return source, _source_hashes(source)


def _prepare(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    source, hashes = _build_source(tmp_path)
    packet = tmp_path / "packet"
    prepare_packet(source, packet, expected_hashes=hashes)
    return source, packet, hashes


def _write_declaration(
    packet: Path,
    *,
    ai_use: str = "NONE",
    reviewed_all: str = "YES",
    external_sources_checked: str = "ALL_ATTEMPTED",
) -> None:
    _write_csv(
        packet / "reviewer_declaration.csv",
        DECLARATION_FIELDS,
        [
            {
                "reviewer_id": "reviewer-a",
                "reviewed_all": reviewed_all,
                "generative_ai_use": ai_use,
                "external_sources_checked": external_sources_checked,
                "elapsed_minutes": "90",
                "expertise": "Technology transfer",
                "completed_date": "2026-08-25",
                "limitations": "Single-reviewer exploratory assessment.",
            }
        ],
    )


def _complete_labels(
    packet: Path,
    *,
    wrong_source_count: int = 1,
    novel_cases: tuple[str, ...] = ("L01", "L02", "L03"),
    unverifiable_indices: tuple[int, ...] = (),
) -> None:
    rows = _read_csv(packet / "labels.csv")
    first_in_case: set[str] = set()
    for row in rows:
        row["relevant"] = "YES"
        row["novel"] = "NO"
        if row["case_id"] in novel_cases and row["case_id"] not in first_in_case:
            row["novel"] = "YES"
            first_in_case.add(row["case_id"])
        row["review_note"] = (
            "Opened the source and checked its content against the declared evidence gap."
        )
    for row in rows[len(rows) - wrong_source_count :] if wrong_source_count else ():
        row["relevant"] = "NO"
        row["novel"] = "N/A"
    for index in unverifiable_indices:
        rows[index]["relevant"] = "UNVERIFIABLE"
        rows[index]["novel"] = "UNVERIFIABLE"
    _write_csv(packet / "labels.csv", REVIEW_FIELDS, rows)


def test_prepare_packet_preserves_source_and_freezes_every_review_identity(tmp_path):
    source, hashes = _build_source(tmp_path)
    packet = tmp_path / "packet"

    manifest = prepare_packet(source, packet, expected_hashes=hashes)

    assert _source_hashes(source) == hashes
    assert {path.name for path in packet.iterdir()} == {
        "README.md",
        "labels.csv",
        "packet_manifest.json",
        "reviewer_declaration.csv",
    }
    assert manifest["source_file_sha256"] == hashes
    assert manifest["schema_version"] == 2
    assert len(manifest["baseline_contexts"]) == 5
    assert all(context["baseline_sources"] for context in manifest["baseline_contexts"])
    assert "Frozen baseline visible to the reviewer" in (
        packet / "README.md"
    ).read_text(encoding="utf-8")
    assert manifest["row_count"] == 25
    assert len({row["identity_sha256"] for row in manifest["rows"]}) == 25
    assert all(
        row["relevant"] == row["novel"] == row["review_note"] == ""
        for row in _read_csv(packet / "labels.csv")
    )
    assert all(
        row["relevant"] == row["novel"] == row["review_note"] == ""
        for row in _read_csv(source / "review.csv")
    )
    with pytest.raises(Phase3ReviewError, match="refusing to overwrite"):
        prepare_packet(source, packet, expected_hashes=hashes)


def test_blank_packet_is_incomplete_not_a_zero_error_pass(tmp_path):
    source, packet, hashes = _prepare(tmp_path)

    result = summarize_packet(source, packet, expected_hashes=hashes)

    assert result["protocol_status"] == "incomplete"
    assert result["decision"] == "not_evaluated"
    assert result["completed_row_count"] == 0
    assert len(result["incomplete_row_ids"]) == 25
    assert result["metrics"] is None
    assert result["observed_label_counts"] is None
    assert result["production_connection_authorized"] is False


def test_complete_labels_pass_only_at_both_frozen_boundaries(tmp_path):
    source, packet, hashes = _prepare(tmp_path)
    _complete_labels(packet)
    _write_declaration(packet)

    result = summarize_packet(source, packet, expected_hashes=hashes)

    assert result["protocol_status"] == "complete"
    assert result["decision"] == "pass"
    assert result["metrics"] == {
        "wrong_source_count": 1,
        "wrong_source_rate": pytest.approx(0.04),
        "novel_relevant_case_ids": ["L01", "L02", "L03"],
        "novel_relevant_case_count": 3,
    }
    assert result["threshold_results"] == {
        "wrong_source_rate": "pass",
        "novel_relevant_cases": "pass",
    }
    assert result["remaining_production_blockers"] == [
        "planner_trigger_precision",
        "disabled_path_regression",
    ]
    assert result["production_connection_authorized"] is False


def test_legacy_packet_without_baseline_context_is_not_inspectable(tmp_path):
    """The returned v1 packet cannot support an eligible novelty headline."""

    source, packet, hashes = _prepare(tmp_path)
    manifest_path = packet / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 1
    manifest.pop("baseline_contexts")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _complete_labels(packet)
    _write_declaration(packet)

    result = summarize_packet(source, packet, expected_hashes=hashes)

    assert result["protocol_status"] == "not_inspectable"
    assert result["decision"] == "not_evaluated"
    assert result["metrics"] is None
    assert result["baseline_context_exposed_to_reviewer"] is False
    assert result["method_issues"] == ["baseline_context_not_exposed_to_reviewer"]


def test_packet_baseline_context_drift_is_rejected(tmp_path):
    source, packet, hashes = _prepare(tmp_path)
    manifest_path = packet / "packet_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["baseline_contexts"][0]["gap_state"] = "Rewritten after packet preparation"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(Phase3ReviewError, match="baseline contexts do not match"):
        summarize_packet(source, packet, expected_hashes=hashes)


@pytest.mark.parametrize(
    ("wrong_source_count", "novel_cases", "failed_threshold"),
    [
        (2, ("L01", "L02", "L03"), "wrong_source_rate"),
        (1, ("L01", "L02"), "novel_relevant_cases"),
    ],
)
def test_either_failed_threshold_keeps_the_exploratory_decision_failed(
    tmp_path,
    wrong_source_count,
    novel_cases,
    failed_threshold,
):
    source, packet, hashes = _prepare(tmp_path)
    _complete_labels(
        packet,
        wrong_source_count=wrong_source_count,
        novel_cases=novel_cases,
    )
    _write_declaration(packet)

    result = summarize_packet(source, packet, expected_hashes=hashes)

    assert result["protocol_status"] == "complete"
    assert result["decision"] == "fail"
    assert result["threshold_results"][failed_threshold] == "fail"
    assert result["remaining_production_blockers"][0] == "human_value_thresholds"


def test_unverifiable_row_is_not_inspectable_and_never_becomes_a_pass(tmp_path):
    source, packet, hashes = _prepare(tmp_path)
    _complete_labels(packet, unverifiable_indices=(0,))
    _write_declaration(packet)

    result = summarize_packet(source, packet, expected_hashes=hashes)

    assert result["protocol_status"] == "not_inspectable"
    assert result["decision"] == "not_evaluated"
    assert result["uninspectable_row_ids"] == ["L01/SRC-L01-1"]
    assert result["metrics"] is None
    assert result["threshold_results"] == {
        "wrong_source_rate": "not_evaluated",
        "novel_relevant_cases": "not_evaluated",
    }


def test_substantive_ai_declaration_is_retained_but_excluded(tmp_path):
    source, packet, hashes = _prepare(tmp_path)
    _complete_labels(packet)
    _write_declaration(packet, ai_use="SOME_SUBSTANTIVE")

    result = summarize_packet(source, packet, expected_hashes=hashes)

    assert result["protocol_status"] == "excluded_substantive_ai"
    assert result["decision"] == "not_evaluated"
    assert result["reviewer_declaration"]["generative_ai_use"] == "SOME_SUBSTANTIVE"
    assert result["observed_label_counts"] is not None
    assert result["metrics"] is None


def test_label_title_drift_is_rejected_even_when_the_key_still_matches(tmp_path):
    """A row can keep its join key while silently referring to another source."""

    source, packet, hashes = _prepare(tmp_path)
    rows = _read_csv(packet / "labels.csv")
    rows[0]["title"] = "A different source hidden behind the same key"
    _write_csv(packet / "labels.csv", REVIEW_FIELDS, rows)

    with pytest.raises(Phase3ReviewError, match="label identity drifted"):
        summarize_packet(source, packet, expected_hashes=hashes)


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate"])
def test_label_key_set_must_match_the_frozen_packet_exactly(tmp_path, mutation):
    source, packet, hashes = _prepare(tmp_path)
    rows = _read_csv(packet / "labels.csv")
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows[-1]["accepted_source_id"] = "UNREGISTERED"
    else:
        rows[-1] = dict(rows[0])
    _write_csv(packet / "labels.csv", REVIEW_FIELDS, rows)

    message = "duplicate" if mutation == "duplicate" else "do not match packet manifest"
    with pytest.raises(Phase3ReviewError, match=message):
        summarize_packet(source, packet, expected_hashes=hashes)


@pytest.mark.parametrize(
    ("relevant", "novel", "note", "message"),
    [
        ("YES", "", "This row has only two completed fields.", "partially completed"),
        ("NO", "YES", "Opened and inspected the source content directly.", "invalid relevant/novel pair"),
        ("YES", "NO", "too short", "review_note is too short"),
    ],
)
def test_partial_invalid_or_ungrounded_labels_are_rejected(
    tmp_path,
    relevant,
    novel,
    note,
    message,
):
    source, packet, hashes = _prepare(tmp_path)
    rows = _read_csv(packet / "labels.csv")
    rows[0].update(relevant=relevant, novel=novel, review_note=note)
    _write_csv(packet / "labels.csv", REVIEW_FIELDS, rows)

    with pytest.raises(Phase3ReviewError, match=message):
        summarize_packet(source, packet, expected_hashes=hashes)


def test_source_artifact_drift_is_rejected_again_at_the_summary_boundary(tmp_path):
    source, packet, hashes = _prepare(tmp_path)
    original = (source / "execution.json").read_text(encoding="utf-8")
    (source / "execution.json").write_text(original + "\n", encoding="utf-8")

    with pytest.raises(Phase3ReviewError, match="source artifact identity drifted"):
        summarize_packet(source, packet, expected_hashes=hashes)


def test_summary_payload_reaches_an_immutable_file_boundary(tmp_path):
    source, packet, hashes = _prepare(tmp_path)
    result = summarize_packet(source, packet, expected_hashes=hashes)
    output = tmp_path / "result" / "summary.json"

    write_summary(output, result)

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted == result
    assert persisted["protocol_status"] == "incomplete"
    assert persisted["production_connection_authorized"] is False
    with pytest.raises(Phase3ReviewError, match="could not create"):
        write_summary(output, result)


def test_review_module_has_no_provider_or_network_dependency():
    source = Path(phase3_review.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )

    # Inspect imports rather than prose: the module's opening docstring says
    # "socket" to explain the invariant and must not become a false positive.
    assert imported_roots.isdisjoint({"requests", "urllib", "socket", "httpx"})
    assert "academic_agent" not in imported_roots
