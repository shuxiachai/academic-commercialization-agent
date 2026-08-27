"""Artifact-boundary tests for the OpenAlex precision-v2 audit."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openalex_precision_audit as audit


_LABEL_COLUMNS = (
    "case_id",
    "provider",
    "accepted_source_id",
    "title",
    "url",
    "relevant",
    "novel",
    "review_note",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source(
    source_id: str,
    title: str,
    url: str,
    summary: str,
    provider_result_index: int,
) -> tuple[dict[str, object], dict[str, object]]:
    accepted = {
        "source_id": source_id,
        "title": title,
        "url": url,
        "doi": None,
        "publisher": "Frozen Test Publisher",
        "published_date": "2026-01-01",
        "evidence_summary": summary,
        "summary_source": "abstract",
        "citation_count": 1,
    }
    record = {
        key: value for key, value in accepted.items() if key != "source_id"
    }
    record["provider_result_index"] = provider_result_index
    return accepted, record


def _build_artifacts(
    root: Path,
    *,
    duplicate_label: bool = False,
) -> tuple[Path, Path, Path, str]:
    source_root = root / "source"
    source_root.mkdir()
    relevant, relevant_record = _source(
        "A2",
        "Plasma synthesis of ammonia",
        "https://openalex.org/W1111111111",
        "Catalyst-free production reports energy efficiency.",
        0,
    )
    irrelevant, irrelevant_record = _source(
        "A3",
        "Plasma catalyst review",
        "https://openalex.org/W2222222222",
        "The review discusses plasma energy efficiency.",
        1,
    )
    journal_path = source_root / "case-executions/D01.json"
    _write_json(
        journal_path,
        {
            "case_id": "D01",
            "audit": {
                "accepted_sources": [relevant, irrelevant],
                "call_audits": [
                    {"candidate_records": [relevant_record, irrelevant_record]}
                ],
            },
        },
    )

    candidates_path = source_root / "candidates.csv"
    with candidates_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "case_id",
                "accepted_source_id",
                "title",
                "url",
                "local_disposition",
            ),
        )
        writer.writeheader()
        for source in (relevant, irrelevant):
            writer.writerow(
                {
                    "case_id": "D01",
                    "accepted_source_id": source["source_id"],
                    "title": source["title"],
                    "url": source["url"],
                    "local_disposition": "quarantined_accepted",
                }
            )

    labels_path = root / "labels.csv"
    label_rows = [
        {
            "case_id": "D01",
            "provider": "openalex",
            "accepted_source_id": "A2",
            "title": relevant["title"],
            "url": relevant["url"],
            "relevant": "YES",
            "novel": "YES",
            "review_note": "Private prose must not enter public output.",
        },
        {
            "case_id": "D01",
            "provider": "openalex",
            "accepted_source_id": "A3",
            "title": irrelevant["title"],
            "url": irrelevant["url"],
            "relevant": "NO",
            "novel": "N/A",
            "review_note": "Another private note.",
        },
    ]
    if duplicate_label:
        label_rows[1] = dict(label_rows[0])
    with labels_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_LABEL_COLUMNS)
        writer.writeheader()
        writer.writerows(label_rows)

    fixture_path = root / "fixture.json"
    _write_json(
        fixture_path,
        {
            "schema_version": 1,
            "mode": "openalex_precision_v2_unseen_challenge",
            "production_connected": False,
            "development_source": {
                "labels_sha256": _sha256(labels_path),
                "candidate_rows_sha256": _sha256(candidates_path),
                "row_count": 2,
                "case_execution_sha256": {"D01": _sha256(journal_path)},
            },
            "development_profiles": [
                {
                    "case_id": "D01",
                    "required_groups": [
                        {"group_id": "plasma_route", "phrases": ["plasma"]},
                        {
                            "group_id": "ammonia_product",
                            "phrases": ["ammonia"],
                        },
                    ],
                    "supporting_groups": [
                        {
                            "group_id": "synthesis",
                            "phrases": ["synthesis", "production"],
                        },
                        {
                            "group_id": "performance",
                            "phrases": ["efficiency"],
                        },
                    ],
                    "minimum_supporting_groups": 1,
                    "minimum_title_required_groups": 1,
                }
            ],
        },
    )
    return fixture_path, source_root, labels_path, _sha256(fixture_path)


class OpenAlexPrecisionAuditTests(unittest.TestCase):
    def test_audit_materializes_decisions_and_aggregate_at_output_seam(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            fixture, source_root, labels, fixture_hash = _build_artifacts(root)
            output = root / "result"

            result = audit.run_development_audit(
                fixture_path=fixture,
                source_root=source_root,
                labels_path=labels,
                output_dir=output,
                expected_fixture_sha256=fixture_hash,
            )

            self.assertTrue(result["metrics"]["qualified"])
            self.assertEqual(result["decision_count"], 2)
            self.assertFalse(result["network_calls_performed"])
            self.assertFalse(result["production_connected"])
            persisted = json.loads(
                (output / "result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted, result)
            with (output / "decisions.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                rows = tuple(csv.DictReader(handle))
            self.assertEqual(
                [(row["accepted_source_id"], row["action"]) for row in rows],
                [("A2", "ACCEPT"), ("A3", "ABSTAIN")],
            )
            self.assertNotIn("review_note", rows[0])
            self.assertNotIn("Private prose", (output / "result.json").read_text())

    def test_decisions_are_complete_before_label_file_is_opened(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            fixture, source_root, labels, fixture_hash = _build_artifacts(root)
            events: list[str] = []
            original_make = audit.make_blind_decisions
            original_read = audit._read_labels  # noqa: SLF001

            def make(*args: object, **kwargs: object) -> object:
                value = original_make(*args, **kwargs)
                events.append("decisions_complete")
                return value

            def read(*args: object, **kwargs: object) -> object:
                self.assertEqual(events, ["decisions_complete"])
                events.append("labels_opened")
                return original_read(*args, **kwargs)

            with (
                patch.object(audit, "make_blind_decisions", side_effect=make),
                patch.object(audit, "_read_labels", side_effect=read),
            ):
                audit.run_development_audit(
                    fixture_path=fixture,
                    source_root=source_root,
                    labels_path=labels,
                    output_dir=root / "result",
                    expected_fixture_sha256=fixture_hash,
                )

            self.assertEqual(events, ["decisions_complete", "labels_opened"])

    def test_label_byte_drift_fails_before_scoring(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            fixture, source_root, labels, fixture_hash = _build_artifacts(root)
            labels.write_text(
                labels.read_text(encoding="utf-8") + " ",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                audit.OpenAlexPrecisionAuditError,
                "label file byte identity drifted",
            ):
                audit.run_development_audit(
                    fixture_path=fixture,
                    source_root=source_root,
                    labels_path=labels,
                    output_dir=root / "result",
                    expected_fixture_sha256=fixture_hash,
                )

    def test_duplicate_label_identity_fails_even_with_matching_file_hash(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            fixture, source_root, labels, fixture_hash = _build_artifacts(
                root,
                duplicate_label=True,
            )

            with self.assertRaisesRegex(
                audit.OpenAlexPrecisionAuditError,
                "duplicate source identity",
            ):
                audit.run_development_audit(
                    fixture_path=fixture,
                    source_root=source_root,
                    labels_path=labels,
                    output_dir=root / "result",
                    expected_fixture_sha256=fixture_hash,
                )

    def test_output_directory_is_write_once(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            fixture, source_root, labels, fixture_hash = _build_artifacts(root)
            arguments = {
                "fixture_path": fixture,
                "source_root": source_root,
                "labels_path": labels,
                "output_dir": root / "result",
                "expected_fixture_sha256": fixture_hash,
            }
            audit.run_development_audit(**arguments)

            with self.assertRaises(FileExistsError):
                audit.run_development_audit(**arguments)


if __name__ == "__main__":
    unittest.main()
