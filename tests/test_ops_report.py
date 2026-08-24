"""Tests for the operational report.

Its whole purpose is to not mislead, so these pin the ways earlier versions
silently changed the denominator or grouped the wrong fault.

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

import io
import json
import unittest
from contextlib import redirect_stdout
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

    def test_unreadable_status_files_are_unknown_not_silently_skipped(self):
        """A half-written status must remain visible without becoming a pass.

        The first collector skipped it, which made the reported denominator
        depend on whether the system could inspect its own failures.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "20260810T041910Z-abc123def0"
            directory.mkdir()
            (directory / "status.json").write_text("{not json", encoding="utf-8")
            self._run_dir(root, "20260811T041910Z-abc123def1", {"topic": "y", "done": True})
            collected = ops_report.collect(root)
            self.assertEqual(len(collected), 2)
            self.assertEqual(collected[0]["outcome"], "unknown")
            self.assertEqual(collected[0]["outcome_basis"], "unreadable status.json")

    def test_legacy_terminal_artifacts_are_included(self):
        """Forty-two real directories predate status.json.

        A report and an error log are strong, mutually exclusive terminal
        evidence in that legacy layout; dropping both erased 36 known outcomes
        from the operational history on disk.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            completed = root / "20260705T041910Z-abc123def0"
            completed.mkdir()
            (completed / "commercialization_report.md").write_text(
                "report", encoding="utf-8"
            )
            failed = root / "20260706T041910Z-abc123def1"
            failed.mkdir()
            (failed / "error.log").write_text("provider failed", encoding="utf-8")

            outcomes = [run["outcome"] for run in ops_report.collect(root)]
            self.assertEqual(outcomes, ["completed", "failed"])

    def test_a_directory_without_terminal_evidence_is_unknown(self):
        """No error found is not equivalent to a successful run."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "20260705T041910Z-abc123def0").mkdir()
            [run] = ops_report.collect(root)
            self.assertEqual(run["outcome"], "unknown")
            self.assertFalse(run["failed"])

    def test_timeout_and_user_cancellation_are_not_ordinary_failures(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeout = root / "20260705T041910Z-abc123def0"
            timeout.mkdir()
            (timeout / "error.log").write_text(
                "Analysis timed out after 20 minutes.", encoding="utf-8"
            )
            cancelled = root / "20260706T041910Z-abc123def1"
            cancelled.mkdir()
            (cancelled / "cancelled.marker").write_text("now", encoding="utf-8")

            outcomes = [run["outcome"] for run in ops_report.collect(root)]
            self.assertEqual(outcomes, ["timeout", "cancelled"])

    def test_missing_quality_telemetry_is_not_reported_as_passed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run_dir(root, "20260810T041910Z-abc123def0", {
                "topic": "x", "done": True,
                "claim_grounding": {"status": "partial"},
                "checkpointing": {"state": "healthy"},
            })
            self._run_dir(root, "20260811T041910Z-abc123def1", {
                "topic": "y", "done": True,
            })

            checks = [run["checks"] for run in ops_report.collect(root)]
            self.assertEqual(checks[0]["claim grounding"], "partial")
            self.assertEqual(checks[0]["checkpointing"], "healthy")
            self.assertEqual(checks[1]["claim grounding"], "not recorded")
            self.assertEqual(checks[1]["checkpointing"], "not recorded")

            output = io.StringIO()
            with redirect_stdout(output):
                ops_report._print_check_coverage(ops_report.collect(root))
            rendered = output.getvalue()
            self.assertIn("partial=1", rendered)
            self.assertIn("not recorded=1", rendered)

    def test_success_rate_excludes_cancelled_and_unknown_runs(self):
        """Assert the CLI seam, not only the correctly classified fields.

        One completed and one failed run is a 50% resolved completion rate.
        The cancelled and unknown directories must remain visible in their own
        columns without moving that rate to 25%.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run_dir(root, "20260810T041910Z-abc123def0", {
                "topic": "complete", "done": True,
            })
            self._run_dir(root, "20260811T041910Z-abc123def1", {
                "topic": "failed", "done": True, "error": "provider failed",
            })
            unknown = root / "20260812T041910Z-abc123def2"
            unknown.mkdir()
            cancelled = root / "20260813T041910Z-abc123def3"
            cancelled.mkdir()
            (cancelled / "cancelled.marker").write_text("now", encoding="utf-8")

            output = io.StringIO()
            with redirect_stdout(output):
                ops_report._print_outcomes(ops_report.collect(root))
            rendered = output.getvalue()

            week = next(line for line in rendered.splitlines()
                        if line.startswith("2026-W33"))
            self.assertIn("50%", week)
            self.assertIn("unknown directories", rendered)

    def test_failure_heading_names_timeouts_in_its_denominator(self):
        output = io.StringIO()
        with redirect_stdout(output):
            ops_report._print_causes([{
                "outcome": "timeout",
                "cause": "deadline exceeded",
                "date": "2026-08-24",
            }])
        self.assertIn("failed or timed-out runs", output.getvalue())

    def test_missing_cost_is_not_assumed_to_mean_legacy(self):
        """A current run can fail before usage exists; its age is unknowable."""
        runs = [
            {"usage": {"cost_usd": 0.01}},
            {"usage": None},
        ]
        output = io.StringIO()
        with redirect_stdout(output):
            ops_report._print_cost(runs)
        rendered = output.getvalue()
        self.assertIn("without recorded cost", rendered)
        self.assertIn("failures before usage accounting", rendered)
        self.assertNotIn("predate cost accounting", rendered)



    def test_the_date_comes_from_the_run_id(self):
        """Not from the file's mtime, which a later PDF render would move."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run_dir(root, "20260714T041910Z-abc123def0", {"topic": "x", "done": True})
            self.assertEqual(ops_report.collect(root)[0]["date"], "2026-07-14")
