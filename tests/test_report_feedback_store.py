"""Boundaries of the feedback store itself, below the HTTP seam.

tests/test_api_feedback.py covers the endpoint contract. These pin what the
store does with answers outside the vocabulary, a second responder, and the
two kinds of damage a file can carry.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from academic_agent import report_feedback as fb


class FeedbackStoreBoundaryTests(unittest.TestCase):

    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp())

    def test_an_answer_outside_the_vocabulary_is_refused_before_anything_is_written(self):
        for changed_view, part in (("maybe", None), ("yes", "cover"), ("", None), ("yes", "")):
            with self.subTest(changed_view=changed_view, part=part), self.assertRaises(ValueError):
                fb.record(self.run_dir, "holder", changed_view, part)
        self.assertFalse((self.run_dir / fb.FILE_NAME).exists())

    def test_no_owner_and_an_empty_owner_are_both_the_holder(self):
        self.assertEqual(fb.responder_key(None), fb.HOLDER)
        self.assertEqual(fb.responder_key(""), fb.HOLDER)

    def test_a_second_responder_does_not_disturb_the_first(self):
        fb.record(self.run_dir, "holder", "yes", None)
        fb.record(self.run_dir, "owner-abc", "no", "sources")
        stored = json.loads((self.run_dir / fb.FILE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(sorted(stored["responses"]), ["holder", "owner-abc"])
        self.assertEqual(fb.read(self.run_dir, "holder")["changed_view"], "yes")
        self.assertEqual(fb.read(self.run_dir, "owner-abc")["part"], "sources")

    def test_a_responses_list_instead_of_a_map_is_damage_for_every_reader(self):
        (self.run_dir / fb.FILE_NAME).write_text('{"schema_version": 1, "responses": []}', encoding="utf-8")
        with self.assertRaises(fb.FeedbackUnreadable):
            fb.read(self.run_dir, "holder")
        with self.assertRaises(fb.FeedbackUnreadable):
            fb.record(self.run_dir, "holder", "yes", None)
        self.assertIsNone(fb.responses(self.run_dir))

    def test_a_malformed_record_raises_for_its_owner_and_is_skipped_by_the_ops_report(self):
        (self.run_dir / fb.FILE_NAME).write_text(json.dumps(
            {"schema_version": 1, "responses": {"holder": {"changed_view": "yes", "part": None}}}),
            encoding="utf-8")
        with self.assertRaises(fb.FeedbackUnreadable):
            fb.read(self.run_dir, "holder")
        self.assertIsNone(fb.read(self.run_dir, "someone-else"))
        self.assertEqual(fb.responses(self.run_dir), [])

    def test_the_temporary_file_does_not_linger(self):
        fb.record(self.run_dir, "holder", "unsure", "checks")
        self.assertEqual(sorted(p.name for p in self.run_dir.iterdir()), [fb.FILE_NAME])


if __name__ == "__main__":
    unittest.main()
