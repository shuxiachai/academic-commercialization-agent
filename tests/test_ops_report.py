"""Tests for the operational report.

Its whole purpose is to not mislead, so what these pin are the two ways the
first version of it did.

It reported the guardrail's generic retry hint as the cause, which puts
unrelated faults in one bucket — and reading that bucket sends you to fix
formatting when the real error was a schema minimum no output could satisfy.
That is not hypothetical: it is the mistake this tool was written after
making by hand.

And it counted runs whose status.json predates the topic field as "empty
input", which would send someone to add validation for a submission nobody
ever made. Every such run in the directory turned out to be absent, not
blank.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import ops_report


class CauseExtractionTests(unittest.TestCase):

    def test_the_specific_validation_error_beats_the_generic_hint(self):
        """Every scoring failure opens with the same sentence about Markdown
        fences. Grouping on it hides which fault you actually have."""
        error = (
            "Task failed guardrail validation after 2 retries. Last error: "
            "Return exactly one valid JSON object matching the scoring schema "
            "with no Markdown fences or prose. Validation error: 1 validation "
            "error for CommercializationScore\npatent_source_ids\n  List should "
            "have at least 1 item after validation, not 0 [type=too_short]"
        )
        cause = ops_report._specific_cause(error)
        self.assertIn("CommercializationScore.patent_source_ids", cause)
        self.assertNotIn("Markdown", cause)

    def test_one_fault_with_varying_detail_groups_as_one(self):
        """Two runs failed patent retrieval for different reasons in the tail.
        Split, they read as two rare faults instead of one recurring one."""
        a = "patent retrieval produced 0 validated sources; at least 3 are required. Rejections: non-primary host"
        b = "patent retrieval produced 0 validated sources; at least 3 are required. Rejections: no usable results"
        self.assertEqual(ops_report._specific_cause(a), ops_report._specific_cause(b))

    def test_distinct_faults_stay_distinct(self):
        """The grouping must not be so aggressive that it merges everything."""
        a = "patent retrieval produced 0 validated sources"
        b = "Failed to connect to OpenAI API. Connection error."
        self.assertNotEqual(ops_report._specific_cause(a), ops_report._specific_cause(b))

    def test_a_missing_error_is_labelled_not_guessed(self):
        self.assertIn("no error", ops_report._specific_cause(""))


class TopicClassificationTests(unittest.TestCase):

    def test_an_absent_topic_is_not_reported_as_empty_input(self):
        """The distinction the first version lost. All fourteen 'empty' runs
        in the real directory were runs recorded before the field existed."""
        self.assertEqual(ops_report._classify_topic(None), "not recorded")
        self.assertEqual(ops_report._classify_topic(""), "empty submission")

    def test_cjk_and_latin_are_told_apart(self):
        self.assertEqual(ops_report._classify_topic("铀235制取和储存"), "CJK")
        self.assertEqual(
            ops_report._classify_topic("solid-state batteries for vehicles"), "latin")

    def test_a_trivial_topic_is_its_own_shape(self):
        """'test' is not a research topic and its failure says nothing about
        the pipeline's handling of real ones."""
        self.assertEqual(ops_report._classify_topic("test"), "trivial (<8 chars)")


class CollectionTests(unittest.TestCase):

    def _run_dir(self, root: Path, run_id: str, status: dict) -> None:
        directory = root / run_id
        directory.mkdir()
        (directory / "status.json").write_text(
            json.dumps(status), encoding="utf-8")

    def test_benchmark_runs_are_not_counted_as_real_ones(self):
        """outputs/benchmark holds curated topics run deliberately; mixing them
        in would drown the handful of real runs this exists to look at."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run_dir(root, "20260810T041910Z-abc123def0", {"topic": "x", "done": True})
            (root / "benchmark").mkdir()
            self.assertEqual(len(ops_report.collect(root)), 1)

    def test_a_run_is_failed_when_it_carries_an_error(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run_dir(root, "20260810T041910Z-abc123def0",
                          {"topic": "x", "error": "boom", "stage": "Error"})
            self.assertTrue(ops_report.collect(root)[0]["failed"])

    def test_unreadable_status_files_are_skipped_not_fatal(self):
        """A half-written status.json from a killed run must not stop the
        report that exists to explain killed runs."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "20260810T041910Z-abc123def0"
            directory.mkdir()
            (directory / "status.json").write_text("{not json", encoding="utf-8")
            self._run_dir(root, "20260811T041910Z-abc123def1", {"topic": "y", "done": True})
            self.assertEqual(len(ops_report.collect(root)), 1)

    def test_the_date_comes_from_the_run_id(self):
        """Not from the file's mtime, which a later PDF render would move."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run_dir(root, "20260714T041910Z-abc123def0", {"topic": "x", "done": True})
            self.assertEqual(ops_report.collect(root)[0]["date"], "2026-07-14")
