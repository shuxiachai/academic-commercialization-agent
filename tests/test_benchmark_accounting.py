"""Tests for the benchmark harness's cost and citation accounting.

benchmark.py does not go through pipeline_worker and cannot: the worker has
no fixture replay path. That justified divergence is also how it ended up
without cost accounting or a citation screen for months, so what these
assert is that it calls the same accounting the worker calls — not that the
pipeline works, which is tested where the pipeline lives.

The batch total matters more than the per-run figure. Four rubric experiments
were run and justified without anyone being able to say what they cost.
"""

from __future__ import annotations

import inspect
from unittest import TestCase

import benchmark


class AccountingIsWiredTests(TestCase):

    def test_the_harness_collects_token_usage(self):
        source = inspect.getsource(benchmark.run_topic)
        self.assertIn("collect_usage", source)

    def test_the_harness_runs_the_citation_screen(self):
        source = inspect.getsource(benchmark.run_topic)
        self.assertIn("save_claim_grounding", source)

    def test_the_crew_object_is_kept_so_usage_can_be_read(self):
        """usage lives on the crew and is only readable after kickoff. Chaining
        .crew().kickoff() throws the object away and silently yields an empty
        usage report — which looks exactly like a free run."""
        source = inspect.getsource(benchmark.run_topic)
        self.assertNotIn(".crew().kickoff(", source)
        self.assertIn("crew_obj.kickoff(", source)

    def test_report_selection_uses_the_shared_explicit_index_helper(self):
        """The negative indices this replaced are what the worker's docstring
        warns about: a task inserted mid-pipeline shifts which output is saved
        as the report and nothing raises. Two copies of that bug existed; this
        was the second."""
        source = inspect.getsource(benchmark.run_topic)
        self.assertIn("_select_report_and_scores", source)
        for bad in ("tasks_output[-1]", "tasks_output[-2]"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, source)


class BatchTotalTests(TestCase):
    """The summary block, read as source: main() runs a whole batch, so
    exercising it for real would cost money to assert on formatting."""

    def _summary(self) -> str:
        source = inspect.getsource(benchmark.main)
        return source[source.index("Succeeded :"):]

    def test_the_batch_cost_is_totalled(self):
        self.assertIn("Cost      :", self._summary())

    def test_runs_without_usage_are_excluded_from_the_total(self):
        """A skipped run carries the previous batch's usage. Counting it would
        report an old bill as this one's."""
        summary = self._summary()
        self.assertIn('r["usage"].get("cost_usd") is not None', summary)
        self.assertIn("without ", summary)

    def test_a_partially_priced_run_is_flagged_in_the_total(self):
        """cost_complete is False when some model had no price; a total that
        hides that is an undercount presented as a total."""
        self.assertIn("cost_complete", self._summary())

    def test_citation_coverage_is_reported_for_the_batch(self):
        summary = self._summary()
        self.assertIn("Citations :", summary)
        for field in ("checked", "unverifiable", "ungrounded"):
            with self.subTest(field=field):
                self.assertIn(field, summary)
