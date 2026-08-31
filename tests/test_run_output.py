"""Tests for isolated per-run report output."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from academic_agent.run_output import save_error, save_report


class RunOutputTests(TestCase):
    def test_each_save_uses_an_independent_directory(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_id, first_path = save_report("first", run_id="test-run-1", output_root=root)
            second_id, second_path = save_report("second", run_id="test-run-2", output_root=root)

            self.assertNotEqual(first_id, second_id)
            self.assertNotEqual(first_path.parent, second_path.parent)
            self.assertEqual(first_path.read_text(encoding="utf-8"), "first")
            self.assertEqual(second_path.read_text(encoding="utf-8"), "second")

    def test_error_log_uses_run_directory(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            error_path = save_error("traceback details", "run-123", output_root=root)

            self.assertEqual(error_path, root / "run-123" / "error.log")
            self.assertEqual(
                error_path.read_text(encoding="utf-8"),
                "traceback details",
            )

    def test_source_collection_uses_run_directory(self) -> None:
        from academic_agent.run_output import save_source_collection

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = save_source_collection('{"sources":[]}', "run-123", output_root=root)

            self.assertEqual(path, root / "run-123" / "validated_sources.json")
            self.assertEqual(path.read_text(encoding="utf-8"), '{"sources":[]}')

    def test_scores_uses_run_directory(self) -> None:
        from academic_agent.run_output import save_scores

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = save_scores('{"overall_score":65}', "run-123", output_root=root)

            self.assertEqual(path, root / "run-123" / "commercialization_scores.json")
            self.assertEqual(path.read_text(encoding="utf-8"), '{"overall_score":65}')

    def test_scores_normalize_qwen_rated_at_form_at_persistence_seam(self) -> None:
        """The first paid Qwen phrase must not reach the client score artifact."""
        from academic_agent.run_output import save_scores

        payload = {
            "market_accessibility": 2.5,
            "market_rationale": (
                "Market accessibility is rated at 25, reflecting active private "
                "investment without a verified commercial product."
            ),
        }
        with TemporaryDirectory() as temporary_directory:
            path = save_scores(
                json.dumps(payload),
                "run-qwen-rated",
                output_root=Path(temporary_directory),
            )

            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertIn("rated at 2.5", saved["market_rationale"])
        self.assertNotIn("rated at 25", saved["market_rationale"])

    def test_scores_normalize_qwen_parenthetical_form_at_persistence_seam(self) -> None:
        """A qualitative score label must use the delivered decimal scale."""
        from academic_agent.run_output import save_scores

        payload = {
            "evidence_confidence": 3.5,
            "evidence_rationale": (
                "Confidence is moderate (35) because the evidence domains "
                "remain only indirectly correlated."
            ),
        }
        with TemporaryDirectory() as temporary_directory:
            path = save_scores(
                json.dumps(payload),
                "run-qwen-parenthetical",
                output_root=Path(temporary_directory),
            )

            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertIn("moderate (3.5)", saved["evidence_rationale"])
        self.assertNotIn("moderate (35)", saved["evidence_rationale"])

    def test_scores_leave_percentages_and_candidate_counts_unchanged(self) -> None:
        """Precision-first normalization must not rewrite evidence quantities."""
        from academic_agent.run_output import save_scores

        rationale = "Confidence is moderate (35%) after review of 35 candidate sources."
        payload = {
            "evidence_confidence": 3.5,
            "evidence_rationale": rationale,
        }
        with TemporaryDirectory() as temporary_directory:
            path = save_scores(
                json.dumps(payload),
                "run-qwen-percentage",
                output_root=Path(temporary_directory),
            )

            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(saved["evidence_rationale"], rationale)

    def test_reviewer_notes_uses_run_directory(self) -> None:
        from academic_agent.run_output import save_reviewer_notes

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = save_reviewer_notes("## Reviewer Notes\n\nLooks good.", "run-456", output_root=root)

            self.assertEqual(path, root / "run-456" / "reviewer_notes.md")
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "## Reviewer Notes\n\nLooks good.",
            )

    def test_save_report_requires_run_id(self) -> None:
        """save_report must use the provided run_id as the output directory name."""
        from academic_agent.run_output import save_report

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            returned_id, report_path = save_report("content", run_id="my-run-id", output_root=root)

            self.assertEqual(returned_id, "my-run-id")
            self.assertEqual(report_path, root / "my-run-id" / "commercialization_report.md")
            self.assertEqual(report_path.read_text(encoding="utf-8"), "content")
