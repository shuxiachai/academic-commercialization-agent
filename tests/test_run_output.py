"""Tests for isolated per-run report output."""

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
