"""Contracts for the zero-network regulator-source title audit.

The important seam is the persisted result, not only the classifier return:
a dataset with no official titles must reach the output as not assessable, and
the known production failure must survive into the case CSV with its provenance.
"""

from __future__ import annotations

import csv
import json
import socket
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import regulator_title_audit
from academic_agent.evidence import EvidenceSource
from academic_agent.source_pipeline import SourceCollection


_CHALLENGE = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "regulator_title_quality"
    / "challenge-v1.json"
)
_KNOWN_BAD_TITLE = "'b, , 4 , I 'b, I - accessdata.fda.gov"
_KNOWN_BAD_URL = "https://www.accessdata.fda.gov/CDRH510K/K222658.pdf"


def _source(
    source_id: str,
    title: str,
    url: str,
    *,
    source_type: str = "government",
) -> EvidenceSource:
    return EvidenceSource(
        source_id=source_id,
        title=title,
        url=url,
        publisher="Example Authority",
        accessed_date=date(2026, 8, 25),
        source_type=source_type,
        credibility_tier="high",
        credibility_reason="Authority identity supplied for a deterministic test.",
        evidence_summary=(
            "This deterministic test summary is intentionally long enough to "
            "satisfy the production evidence contract without external data."
        ),
        summary_source="search_snippet",
    )


def _collection(*market_sources: EvidenceSource) -> SourceCollection:
    academic = _source(
        "A1",
        "A complete academic control title",
        "https://doi.org/10.1000/example",
        source_type="academic_paper",
    )
    return SourceCollection(
        topic="deterministic title audit topic",
        display_topic="deterministic title audit topic",
        collected_at=datetime(2026, 8, 25, tzinfo=UTC),
        academic_sources=[academic],
        patent_sources=[],
        market_sources=list(market_sources),
        academic_queries=["academic query"],
        patent_queries=["patent query"],
        market_queries=["market query"],
    )


def _write_run(root: Path, name: str, collection: SourceCollection) -> None:
    run = root / name
    run.mkdir()
    (run / "validated_sources.json").write_text(
        collection.model_dump_json(indent=2),
        encoding="utf-8",
    )


class TitleScreenTests(unittest.TestCase):
    def test_frozen_challenge_signatures_are_precision_first(self):
        cases = [
            (
                _KNOWN_BAD_TITLE,
                _KNOWN_BAD_URL,
                "review_required",
                ["fragmented_single_letter_tokens"],
            ),
            (
                "K222658 - Accurate 24 - 510(k) Premarket Notification",
                _KNOWN_BAD_URL,
                "clean",
                [],
            ),
            (
                "NCT01234567: Continuous Blood Pressure Monitoring Study",
                "https://clinicaltrials.gov/study/NCT01234567",
                "clean",
                [],
            ),
            (
                "Device Summary � K123456",
                "https://www.accessdata.fda.gov/CDRH510K/K123456.pdf",
                "review_required",
                ["encoding_replacement_character"],
            ),
        ]
        for title, url, expected_status, expected_reasons in cases:
            with self.subTest(title=title):
                status, reasons = regulator_title_audit.assess_title(title, url)
                self.assertEqual(status, expected_status)
                self.assertEqual(reasons, expected_reasons)

    def test_authority_scope_rejects_attacker_suffixes(self):
        cases = {
            "https://www.accessdata.fda.gov/file.pdf": "regulatory",
            "https://clinicaltrials.gov/study/NCT1": "clinical_registry",
            "https://fda.gov.attacker.example/file.pdf": "out_of_scope",
            "https://example.com/?next=fda.gov": "out_of_scope",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(
                    regulator_title_audit.authority_scope_for_url(url),
                    expected,
                )


class FrozenCollectionAuditTests(unittest.TestCase):
    def test_zero_denominator_is_not_rendered_as_a_clean_pass(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            _write_run(root, "01", _collection())
            _write_run(root, "02", _collection())
            # The implementation imports no networking client. The patch makes
            # that an executable contract rather than an inference from imports.
            with mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("audit attempted network access"),
            ):
                first, first_rows = regulator_title_audit.evaluate_audit(
                    root,
                    expected_count=2,
                    challenge_path=_CHALLENGE,
                )
                second, second_rows = regulator_title_audit.evaluate_audit(
                    root,
                    expected_count=2,
                    challenge_path=_CHALLENGE,
                )

        self.assertEqual(first, second)
        self.assertEqual(first_rows, second_rows)
        self.assertEqual(
            first["benchmark"]["state"],
            "not_assessable_zero_denominator",
        )
        self.assertEqual(first["benchmark"]["official_source_count"], 0)
        self.assertNotIn("passed", first["benchmark"])
        self.assertEqual(first["challenge"]["state"], "matched")
        self.assertTrue(first["contract_checks_passed"])
        self.assertTrue(
            all(item["official_source_count"] == 0 for item in first["fixture_manifest"])
        )

    def test_official_titles_reach_case_rows_and_aggregate_state(self):
        clean = _source(
            "M1",
            "K222658 - Accurate 24 - 510(k) Premarket Notification",
            _KNOWN_BAD_URL,
        )
        broken = _source("M2", _KNOWN_BAD_TITLE, _KNOWN_BAD_URL)
        attacker = _source(
            "M3",
            "A B C D - fda.gov.attacker.example",
            "https://fda.gov.attacker.example/fake.pdf",
        )
        with TemporaryDirectory() as temp:
            root = Path(temp)
            _write_run(root, "01", _collection(clean, broken, attacker))
            result, rows = regulator_title_audit.evaluate_audit(
                root,
                expected_count=1,
            )

        benchmark_rows = [row for row in rows if row["dataset"] == "benchmark"]
        self.assertEqual(result["benchmark"]["state"], "review_required")
        self.assertEqual(result["benchmark"]["official_source_count"], 2)
        self.assertEqual(result["benchmark"]["review_required_source_count"], 1)
        self.assertEqual({row["source_id"] for row in benchmark_rows}, {"M1", "M2"})
        broken_row = next(row for row in benchmark_rows if row["source_id"] == "M2")
        self.assertEqual(broken_row["title"], _KNOWN_BAD_TITLE)
        self.assertEqual(
            broken_row["reason_codes"],
            "fragmented_single_letter_tokens",
        )

    def test_flat_tracked_fixture_layout_excludes_manifest(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "01-topic.json").write_text(
                _collection().model_dump_json(indent=2),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text("{}\n", encoding="utf-8")
            result, _ = regulator_title_audit.evaluate_audit(
                root,
                expected_count=1,
            )
        self.assertEqual(result["collection_count"], 1)
        self.assertEqual(result["fixture_manifest"][0]["fixture"], "01-topic.json")

    def test_partial_or_invalid_fixture_sets_fail_closed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(
                regulator_title_audit.RegulatorTitleAuditError,
                "no source collections",
            ):
                regulator_title_audit.evaluate_audit(root)
            _write_run(root, "01", _collection())
            with self.assertRaisesRegex(
                regulator_title_audit.RegulatorTitleAuditError,
                "expected exactly 2",
            ):
                regulator_title_audit.evaluate_audit(root, expected_count=2)
            (root / "01" / "validated_sources.json").write_text(
                "{\"truncated\": true}",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                regulator_title_audit.RegulatorTitleAuditError,
                "could not load",
            ):
                regulator_title_audit.evaluate_audit(root)

    def test_writer_persists_case_seam_and_refuses_overwrite(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            _write_run(fixtures, "01", _collection())
            result, rows = regulator_title_audit.evaluate_audit(
                fixtures,
                expected_count=1,
                challenge_path=_CHALLENGE,
            )
            output = root / "audit"
            regulator_title_audit.write_audit(output, result, rows)
            persisted = json.loads((output / "result.json").read_text(encoding="utf-8"))
            with (output / "cases.csv").open(encoding="utf-8", newline="") as handle:
                case_rows = list(csv.DictReader(handle))
            with self.assertRaisesRegex(
                regulator_title_audit.RegulatorTitleAuditError,
                "refusing to overwrite",
            ):
                regulator_title_audit.write_audit(output, result, rows)

        self.assertEqual(persisted["benchmark"]["state"], "not_assessable_zero_denominator")
        known = next(row for row in case_rows if row["fixture"] == "production-m7-fragmented-title")
        self.assertEqual(known["title"], _KNOWN_BAD_TITLE)
        self.assertEqual(known["matches_expectation"], "True")


if __name__ == "__main__":
    unittest.main()
