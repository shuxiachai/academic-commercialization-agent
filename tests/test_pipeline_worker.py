"""Tests for pipeline_worker.py — the subprocess entry point every run executes.

Most of this module lived as closures inside main(), unreachable from outside
it and so untestable, which is the actual reason it sat at 0% coverage rather
than nobody having gotten to it. Two pieces of internal logic were pulled out
as module-level functions with no behaviour change, and are tested directly
here; main() itself is tested end to end with the crew mocked out, since it is
an orchestration function and its job is to call the right things in the right
order, not to compute anything.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from academic_agent.pipeline_worker import (
    _IDX_REVIEW,
    _IDX_SCORING,
    _merge_status_fields,
    _select_report_and_scores,
)


def _task(raw: str) -> SimpleNamespace:
    return SimpleNamespace(raw=raw)


class SelectReportAndScoresTests(unittest.TestCase):
    """The branch a real bug would hide in: picking the wrong element out of
    tasks_output silently persists the wrong text with no exception anywhere."""

    def test_full_run_reads_review_and_scoring(self):
        tasks = [_task(f"t{i}") for i in range(6)]
        report, scores = _select_report_and_scores(tasks, fallback_raw="unused")
        self.assertEqual(report, tasks[_IDX_REVIEW].raw)
        self.assertEqual(scores, tasks[_IDX_SCORING].raw)

    def test_indices_are_not_accidentally_swapped(self):
        """Review and scoring must come from distinct, correctly-ordered tasks."""
        tasks = [_task(f"t{i}") for i in range(6)]
        report, scores = _select_report_and_scores(tasks, fallback_raw="unused")
        self.assertEqual(report, "t4")
        self.assertEqual(scores, "t5")

    def test_scoring_crashed_report_still_saved(self):
        """Exactly 5 tasks: the reviewer finished, the scorer did not run."""
        tasks = [_task(f"t{i}") for i in range(5)]
        report, scores = _select_report_and_scores(tasks, fallback_raw="unused")
        self.assertEqual(report, tasks[_IDX_REVIEW].raw)
        self.assertIsNone(scores)

    def test_review_crashed_falls_back_to_last_available_task(self):
        """Fewer than 5 tasks but at least 2: no reviewer output exists yet,
        so the best available text is whatever the last task produced."""
        tasks = [_task(f"t{i}") for i in range(3)]
        report, scores = _select_report_and_scores(tasks, fallback_raw="unused")
        self.assertEqual(report, tasks[-1].raw)
        self.assertIsNone(scores)

    def test_almost_nothing_completed_uses_the_crew_result(self):
        """Fewer than 2 tasks: fall back to the crew's own top-level raw text
        rather than indexing into a list that cannot answer the question."""
        report, scores = _select_report_and_scores([], fallback_raw="crew-level")
        self.assertEqual(report, "crew-level")
        self.assertIsNone(scores)

    def test_single_task_also_uses_the_fallback(self):
        report, scores = _select_report_and_scores([_task("t0")], fallback_raw="crew-level")
        self.assertEqual(report, "crew-level")
        self.assertIsNone(scores)

    def test_extra_tasks_do_not_shift_the_indices(self):
        """A task appended after scoring must not be mistaken for it."""
        tasks = [_task(f"t{i}") for i in range(7)]
        report, scores = _select_report_and_scores(tasks, fallback_raw="unused")
        self.assertEqual(report, "t4")
        self.assertEqual(scores, "t5")


class MergeStatusFieldsTests(unittest.TestCase):
    """topic and source_counts are set once, early, and must survive every
    later status write that does not repeat them."""

    def _merge(self, existing, **overrides):
        base = dict(stage="s", done=False, error=None, output_language=None,
                    source_counts=None, topic=None)
        base.update(overrides)
        return _merge_status_fields(existing, **base)

    def test_sticky_fields_survive_a_call_that_omits_them(self):
        existing = {"topic": "batteries", "source_counts": {"academic": 5}}
        data = self._merge(existing, stage="Phase 2")
        self.assertEqual(data["topic"], "batteries")
        self.assertEqual(data["source_counts"], {"academic": 5})
        self.assertEqual(data["stage"], "Phase 2")

    def test_a_new_value_overwrites_the_sticky_one(self):
        existing = {"topic": "old topic"}
        data = self._merge(existing, topic="new topic")
        self.assertEqual(data["topic"], "new topic")

    def test_first_call_has_nothing_to_stick(self):
        data = self._merge({}, topic="batteries")
        self.assertEqual(data["topic"], "batteries")

    def test_absent_sticky_fields_are_not_fabricated(self):
        """No prior topic and none passed now: the key must not appear as None
        and overwrite a value a concurrent writer might still be setting."""
        data = self._merge({})
        self.assertNotIn("topic", data)
        self.assertNotIn("source_counts", data)

    def test_terminal_fields_are_always_set_from_the_call(self):
        existing = {"done": True, "error": "stale error"}
        data = self._merge(existing, stage="Done", done=True)
        self.assertTrue(data["done"])
        self.assertIsNone(data["error"])   # not stuck from a previous failed run


class MainEndToEndTests(unittest.TestCase):
    """main() is an orchestrator: these check that it calls the right things
    in the right order and leaves the right artifacts, with the crew itself
    mocked out entirely."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output_root = Path(self._tmp.name)

        self._source_collection = MagicMock()
        self._source_collection.academic_sources = []
        self._source_collection.patent_sources = []
        self._source_collection.market_sources = []
        self._source_collection.output_language = "English"
        self._source_collection.localized_headings = []
        self._source_collection.display_topic = "a topic"
        self._source_collection.model_dump_json.return_value = "{}"
        self._source_collection.crew_inputs.return_value = {}

    def _run(self, run_id="20260101T000000Z-abcdef01"):
        argv = ["pipeline_worker.py", run_id, "a topic"]
        with patch.object(sys, "argv", argv), \
             patch("academic_agent.run_output.DEFAULT_OUTPUT_ROOT", self.output_root), \
             patch("academic_agent.source_pipeline.collect_source_collection",
                   return_value=self._source_collection):
            from academic_agent.pipeline_worker import main
            try:
                main()
            except SystemExit:
                pass
        return self.output_root / run_id

    def _crew_result(self, n_tasks=6):
        tasks = [_task(f"t{i}") for i in range(n_tasks)]
        return SimpleNamespace(tasks_output=tasks, raw="fallback")

    def test_successful_run_writes_done_and_all_artifacts(self):
        crew = MagicMock()
        crew.agents = []
        crew.kickoff.return_value = self._crew_result()

        with patch("academic_agent.crew.AcademicAgent") as agent_cls:
            agent_cls.return_value.crew.return_value = crew
            run_dir = self._run()

        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["stage"], "Done")
        self.assertTrue(status["done"])
        self.assertTrue((run_dir / "commercialization_report.md").exists())
        self.assertTrue((run_dir / "commercialization_scores.json").exists())

    def test_source_collection_failure_writes_error_not_a_crash(self):
        with patch("academic_agent.source_pipeline.collect_source_collection",
                   side_effect=RuntimeError("no API key")):
            argv = ["pipeline_worker.py", "20260101T000000Z-abcdef01", "a topic"]
            with patch.object(sys, "argv", argv), \
                 patch("academic_agent.run_output.DEFAULT_OUTPUT_ROOT", self.output_root):
                from academic_agent.pipeline_worker import main
                with self.assertRaises(SystemExit):
                    main()

        run_dir = self.output_root / "20260101T000000Z-abcdef01"
        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["stage"], "Error")
        self.assertIn("no API key", status["error"])
        self.assertTrue((run_dir / "error.log").exists())

    def test_crew_failure_after_sources_collected_still_reports_the_topic(self):
        """status.json must keep the topic even though the crew never finished
        — a client polling this run needs a title to show, not just an error."""
        with patch("academic_agent.crew.AcademicAgent",
                   side_effect=RuntimeError("guardrail exhausted retries")):
            run_dir = self._run()

        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["stage"], "Error")
        self.assertEqual(status["topic"], "a topic")

    def test_partial_completion_still_saves_the_report(self):
        """Five tasks: the reviewer produced a report, the scorer never ran.
        The report must be saved even though scoring did not complete."""
        crew = MagicMock()
        crew.agents = []
        crew.kickoff.return_value = self._crew_result(n_tasks=5)

        with patch("academic_agent.crew.AcademicAgent") as agent_cls:
            agent_cls.return_value.crew.return_value = crew
            run_dir = self._run()

        self.assertTrue((run_dir / "commercialization_report.md").exists())
        self.assertFalse((run_dir / "commercialization_scores.json").exists())

    def test_evidence_artifact_failure_does_not_fail_the_run(self):
        """save_evidence_reports is documented as best-effort; a run that
        already has a report and scorecard must not be marked failed because
        writing the inspection files hit a disk error."""
        crew = MagicMock()
        crew.agents = []
        crew.kickoff.return_value = self._crew_result()

        with patch("academic_agent.crew.AcademicAgent") as agent_cls, \
             patch("academic_agent.run_output.save_evidence_reports",
                   side_effect=OSError("disk full")):
            agent_cls.return_value.crew.return_value = crew
            run_dir = self._run()

        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["stage"], "Done")


if __name__ == "__main__":
    unittest.main()
