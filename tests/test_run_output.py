"""Tests for isolated per-run report output."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from academic_agent.run_output import save_report


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
