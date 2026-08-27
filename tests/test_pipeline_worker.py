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
    _recover_from_reviewer_failure,
    _review_quality_from_outputs,
    _select_report_and_scores,
)
from academic_agent.run_spec import DecisionContext, RunSpec
from academic_agent.source_clients import SourceCollectionError


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


class ReviewQualityTests(unittest.TestCase):
    """Review completion must survive the task-output to status seam."""

    def test_unapplied_exact_target_is_partial_not_passed(self):
        tasks = [_task(f"t{i}") for i in range(4)]
        tasks.append(
            _task(
                "reviewed report\n\n## Reviewer Notes\n\n"
                "- Not applied (exact target absent): Correction 2: "
                "Qualify an unsupported statement."
            )
        )

        quality = _review_quality_from_outputs(tasks)

        self.assertEqual(quality["status"], "partial")
        self.assertEqual(quality["unapplied_corrections"], 1)

    def test_missing_reviewer_output_is_unavailable_not_passed(self):
        quality = _review_quality_from_outputs([_task(f"t{i}") for i in range(4)])

        self.assertEqual(quality["status"], "unavailable")

    def test_empty_reviewer_output_is_unavailable_not_passed(self):
        tasks = [_task(f"t{i}") for i in range(4)] + [_task("")]

        quality = _review_quality_from_outputs(tasks)

        self.assertEqual(quality["status"], "unavailable")


class ReviewerFallbackTests(unittest.TestCase):
    """Recovery is allowed only at the Task 4 → Task 5 seam."""

    def _crew(self):
        tasks = [SimpleNamespace(output=_task(f"t{i}")) for i in range(4)]
        review = SimpleNamespace(output=None)
        scoring = SimpleNamespace(
            output=None,
            context=tasks[:3],
            callback=object(),
        )
        tasks.extend([review, scoring])
        crew_callback = object()
        crew = SimpleNamespace(tasks=tasks, task_callback=crew_callback)

        def execute_sync(*, context):
            self.assertEqual(context, "evidence context")
            self.assertIsNone(scoring.callback)
            self.assertIsNone(crew.task_callback)
            scoring.output = _task("score")
            return scoring.output

        scoring.execute_sync = execute_sync
        return crew, scoring, crew_callback

    @patch(
        "crewai.utilities.formatter.aggregate_raw_outputs_from_tasks",
        return_value="evidence context",
    )
    def test_validated_draft_and_independent_score_survive_reviewer_failure(self, _aggregate):
        crew, scoring, crew_callback = self._crew()
        original_scoring_callback = scoring.callback
        completed = []

        recovered = _recover_from_reviewer_failure(
            crew, RuntimeError("guardrail exhausted"), task_complete=completed.append
        )

        self.assertIsNotNone(recovered)
        outputs, quality = recovered
        self.assertEqual(outputs[_IDX_REVIEW].raw, "t3")
        self.assertEqual(outputs[_IDX_SCORING].raw, "score")
        self.assertEqual(quality["status"], "fallback")
        self.assertEqual(len(completed), 2)
        self.assertIs(scoring.callback, original_scoring_callback)
        self.assertIs(crew.task_callback, crew_callback)

    def test_missing_validated_draft_is_not_recoverable(self):
        crew, _scoring, _callback = self._crew()
        crew.tasks[3].output = None
        self.assertIsNone(
            _recover_from_reviewer_failure(crew, RuntimeError("writer failed"))
        )

    def test_completed_reviewer_is_not_misclassified_as_reviewer_failure(self):
        crew, _scoring, _callback = self._crew()
        crew.tasks[_IDX_REVIEW].output = _task("reviewed")
        self.assertIsNone(
            _recover_from_reviewer_failure(crew, RuntimeError("scorer failed"))
        )

    def _merge(self, existing, **overrides):
        base = dict(
            stage="s", done=False, error=None, output_language=None,
            source_counts=None, topic=None,
        )
        base.update(overrides)
        return _merge_status_fields(existing, **base)

    def test_output_language_survives_an_error_write_that_omits_it(self):
        existing = {"output_language": "Simplified Chinese"}
        data = self._merge(existing, stage="Error", done=True, error="review failed")
        self.assertEqual(data["output_language"], "Simplified Chinese")

    def test_explicit_output_language_still_overrides_the_sticky_value(self):
        existing = {"output_language": "Simplified Chinese"}
        data = self._merge(existing, output_language="English")
        self.assertEqual(data["output_language"], "English")

    def test_quality_review_state_survives_later_writes(self):
        existing = {"quality_review": {"status": "fallback"}}
        data = self._merge(existing, stage="Done", done=True)
        self.assertEqual(data["quality_review"]["status"], "fallback")

    @patch(
        "crewai.utilities.formatter.aggregate_raw_outputs_from_tasks",
        return_value="evidence context",
    )
    def test_callbacks_are_restored_when_fallback_scoring_fails(self, _aggregate):
        crew, scoring, crew_callback = self._crew()
        original_scoring_callback = scoring.callback

        def fail(*, context):
            raise RuntimeError(f"scorer failed with {context}")

        scoring.execute_sync = fail
        with self.assertRaisesRegex(RuntimeError, "scorer failed"):
            _recover_from_reviewer_failure(crew, RuntimeError("reviewer failed"))

        self.assertIs(scoring.callback, original_scoring_callback)
        self.assertIs(crew.task_callback, crew_callback)




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

    def test_pipeline_revision_is_first_write_wins(self):
        """A deployment cannot rewrite the identity of an already-started run.

        Status is rewritten at every stage, so both omission and an accidental
        conflicting update must preserve the worker revision recorded first.
        """
        original = "git:0123456789abcdef0123456789abcdef01234567"
        data = self._merge({"pipeline_revision": original}, stage="Agent 4")
        self.assertEqual(data["pipeline_revision"], original)

        conflicting = "git:fedcba9876543210fedcba9876543210fedcba98"
        data = self._merge(
            {"pipeline_revision": original}, pipeline_revision=conflicting
        )
        self.assertEqual(data["pipeline_revision"], original)

    def test_evidence_incomplete_warning_survives_later_writes(self):
        """It is set once, mid-run, by the only code that can discover it —
        every later status write would otherwise erase the warning."""
        existing = {"evidence_incomplete": True}
        data = self._merge(existing, stage="Agent 6")
        self.assertTrue(data["evidence_incomplete"])

    def test_observability_state_survives_every_stage_write(self):
        """The trace id is created before retrieval and finalized after the
        crew. Intermediate writes must not erase the only correlation key a
        polling client can receive."""
        existing = {
            "observability": {"state": "active", "trace_id": "a" * 32}
        }
        data = self._merge(existing, stage="Agent 4")
        self.assertEqual(data["observability"], existing["observability"])

    def test_authority_coverage_survives_every_stage_write(self):
        existing = {"authority_coverage": {"status": "incomplete"}}
        data = self._merge(existing, stage="Agent 4")
        self.assertEqual(data["authority_coverage"], existing["authority_coverage"])

    def test_component_coverage_survives_every_stage_write(self):
        existing = {"component_coverage": {"status": "incomplete"}}
        data = self._merge(existing, stage="Agent 4")
        self.assertEqual(data["component_coverage"], existing["component_coverage"])

    def test_evidence_gap_shadow_survives_every_stage_write(self):
        existing = {"evidence_gap_shadow": {"gate_state": "eligible"}}
        data = self._merge(existing, stage="Agent 4")
        self.assertEqual(data["evidence_gap_shadow"], existing["evidence_gap_shadow"])

    def test_decision_gate_survives_every_stage_write(self):
        existing = {"decision_gate": {"status": "checked", "mode": "orientation"}}
        data = self._merge(existing, stage="Agent 4")
        self.assertEqual(data["decision_gate"], existing["decision_gate"])

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
        self._source_collection.topic = "a topic"
        self._source_collection.failed_domains = {}
        self._source_collection.authority_coverage.model_dump.return_value = {
            "status": "not_applicable",
            "required_categories": [],
            "covered_source_ids": {},
            "missing_categories": [],
        }
        self._source_collection.authority_coverage.missing_categories = []
        self._source_collection.component_coverage.model_dump.return_value = {
            "status": "incomplete",
            "components": ["sensor networks", "edge AI inference"],
            "covered_source_ids": {"sensor networks": ["A1"]},
            "missing_components": ["edge AI inference"],
            "unchecked_components": [],
        }
        self._source_collection.model_dump_json.return_value = "{}"
        self._source_collection.component_coverage.status = "incomplete"
        self._source_collection.component_coverage.missing_components = ["edge AI inference"]
        self._source_collection.model_dump.return_value = {}
        self._source_collection.crew_inputs.return_value = {}

    def _run(self, run_id="20260101T000000Z-abcdef01", *, spec=None):
        argv = ["pipeline_worker.py", run_id, "a topic"]
        if spec is not None:
            run_dir = self.output_root / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            spec_path = spec.save(run_dir)
            argv.extend(["--run-spec", str(spec_path)])
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

        revision = "git:0123456789abcdef0123456789abcdef01234567"
        with patch(
            "academic_agent.checkpoint_runtime.pipeline_revision",
            return_value=revision,
        ), patch("academic_agent.crew.AcademicAgent") as agent_cls:
            agent_cls.return_value.crew.return_value = crew
            run_dir = self._run()

        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["stage"], "Done")
        self.assertTrue(status["done"])
        self.assertEqual(status["pipeline_revision"], revision)
        self.assertEqual(
            status["quality_review"],
            {"status": "passed", "unapplied_corrections": 0},
        )
        self.assertEqual(status["observability"]["state"], "disabled")
        self.assertEqual(status["observability"]["delivery"], "not_configured")
        self.assertTrue((run_dir / "commercialization_report.md").exists())
        self.assertEqual(status["component_coverage"]["status"], "incomplete")
        self.assertEqual(
            status["component_coverage"]["missing_components"],
            ["edge AI inference"],
        )
        self.assertTrue((run_dir / "commercialization_scores.json").exists())

        self.assertEqual(status["evidence_gap_shadow"]["gate_state"], "disabled")
        self.assertEqual(
            status["evidence_gap_shadow"]["persistence_state"], "written"
        )
        self.assertEqual(status["evidence_gap_shadow"]["executed_call_count"], 0)
        self.assertTrue((run_dir / "evidence_gap_shadow.json").exists())

    def test_decision_context_reaches_crew_kickoff_and_public_status(self):
        """The durable field must reach execution, not merely survive storage."""
        crew = MagicMock()
        crew.agents = []
        crew.kickoff.return_value = self._crew_result()
        context = DecisionContext(
            asset_description="A benchtop nitrate-removal prototype",
            target_application="Small municipal water treatment plants",
            decision_owner="University technology transfer manager",
            decision_type="Whether to fund a six-month field pilot",
            constraints="Board approval required before capital spend",
        )
        spec = RunSpec(topic="a topic", decision_context=context)

        with patch("academic_agent.crew.AcademicAgent") as agent_cls:
            agent_cls.return_value.crew.return_value = crew
            run_dir = self._run(spec=spec)

        inputs = crew.kickoff.call_args.kwargs["inputs"]
        self.assertEqual(inputs["assessment_mode"], "decision_support")
        prompt_context = json.loads(inputs["decision_context_json"])
        self.assertEqual(
            prompt_context["decision_owner"],
            "University technology transfer manager",
        )
        self.assertNotIn("jurisdiction", prompt_context)
        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["decision_gate"]["status"], "checked")
        self.assertEqual(status["decision_gate"]["mode"], "decision_support")
        self.assertEqual(
            status["decision_gate"]["provided_fields"],
            list(context.provided_fields),
        )

    def test_enabled_shadow_records_eligibility_without_search_calls(self):
        crew = MagicMock()
        crew.agents = []
        crew.kickoff.return_value = self._crew_result()

        with patch.dict(
            "os.environ", {"EVIDENCE_GAP_SHADOW_ENABLED": "true"}
        ), patch("academic_agent.crew.AcademicAgent") as agent_cls:
            agent_cls.return_value.crew.return_value = crew
            run_dir = self._run()

        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        shadow = status["evidence_gap_shadow"]
        self.assertEqual(shadow["gate_state"], "eligible")
        self.assertEqual(shadow["planner_state"], "not_run")
        self.assertTrue(shadow["checked"])
        self.assertEqual(shadow["proposed_call_count"], 0)
        self.assertEqual(shadow["executed_call_count"], 0)
        self.assertEqual(shadow["added_search_cost_usd"], 0.0)
        self.assertFalse(shadow["evidence_changed"])
        crew.kickoff.assert_called_once()

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

    def test_retrieval_failure_writes_machine_readable_diagnostics(self):
        """A failed collection used to discard its in-memory audit exactly
        when no validated_sources.json existed to preserve it."""
        diagnostics = {
            "version": 1,
            "stage": "academic_retrieval",
            "input_topic": "我们在做剧本创作相关的大模型",
            "search_topic": "large language models for screenplay creation",
            "aliases": ["LLM assisted screenwriting"],
            "accepted_sources": 1,
            "required_sources": 3,
            "audit": [],
        }
        failure = SourceCollectionError(
            "academic retrieval produced 1 validated source",
            diagnostics=diagnostics,
        )
        run_id = "20260101T000000Z-abcdef01"
        with patch("academic_agent.source_pipeline.collect_source_collection",
                   side_effect=failure):
            argv = ["pipeline_worker.py", run_id, "a topic"]
            with patch.object(sys, "argv", argv), \
                 patch("academic_agent.run_output.DEFAULT_OUTPUT_ROOT", self.output_root):
                from academic_agent.pipeline_worker import main
                with self.assertRaises(SystemExit):
                    main()

        payload = json.loads(
            (self.output_root / run_id / "retrieval_diagnostics.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(payload, diagnostics)

    def test_crew_failure_after_sources_collected_still_reports_the_topic(self):
        """status.json must keep the topic even though the crew never finished
        — a client polling this run needs a title to show, not just an error."""
        with patch("academic_agent.crew.AcademicAgent",
                   side_effect=RuntimeError("guardrail exhausted retries")):
            run_dir = self._run()

        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["stage"], "Error")
        self.assertEqual(status["topic"], "a topic")
        self.assertEqual(status["checkpointing"]["state"], "partial")
        self.assertEqual(
            status["checkpointing"]["committed_nodes"], ["retrieval"]
        )
        self.assertEqual(status["recovery"]["state"], "not_requested")

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
