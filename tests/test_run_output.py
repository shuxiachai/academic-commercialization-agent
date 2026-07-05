"""Tests for isolated per-run report output."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from academic_agent.run_output import save_error, save_report


class RunOutputTests(TestCase):
    def test_each_save_uses_an_independent_directory(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_id, first_path = save_report("first", output_root=root)
            second_id, second_path = save_report("second", output_root=root)

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
