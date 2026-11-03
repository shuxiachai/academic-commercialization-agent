"""One over-long reviewer edit must not fail a whole run.

Regression: held-out v2 V02 rep 2 returned a correction whose find exceeded
the 2,000-character bound. The pinned evidence.py guardrail rejected the whole
plan, the single retry repeated it, and the run ended with no report.
reviewer_plan_bounds skips such an edit like an absent target instead.
"""

import json
import unittest
from types import SimpleNamespace

from academic_agent.evidence import ReviewerCorrection, make_reviewer_guardrail
from academic_agent.pipeline_worker import _review_quality_from_outputs
from academic_agent.reviewer_plan_bounds import (
    OVERSIZED_NOTE_PREFIX,
    bound_reviewer_guardrail,
    neutralize_oversized_corrections,
    reviewer_quality_summary,
)
from tests.test_reviewer_guardrail import _EVIDENCE_TASKS, _Output, _Task, _complete_report, _plan

EXACT_FIND = "Single-source market estimates."
EXACT_REPLACE = "The market estimate relies on one public source."
ABSENT = "- Not applied (exact target absent):"


def _run(plan: str, *, bounded: bool = True):
    guardrail = make_reviewer_guardrail(_Task(_complete_report()), context_tasks=_EVIDENCE_TASKS)
    if bounded:
        guardrail = bound_reviewer_guardrail(guardrail)
    ok, result = guardrail(_Output(plan))
    return ok, (result.raw if ok else result)


class OversizedCorrectionTests(unittest.TestCase):

    def test_long_find_is_skipped_and_the_other_corrections_still_apply(self):
        ok, report = _run(_plan(
            {"find": EXACT_FIND, "replace": EXACT_REPLACE, "reason": "Qualify the market evidence boundary."},
            {"find": "x" * 2001, "replace": "y", "reason": "Rewrite the whole technology section."},
            {"find": "A sentence absent from the draft.", "replace": "z", "reason": "Qualify a claim."},
        ))

        self.assertTrue(ok, report)
        self.assertIn(EXACT_REPLACE, report)
        self.assertNotIn(EXACT_FIND, report)
        notes = report.rpartition("## Reviewer Notes")[2]
        # Numbers follow the model's own plan, so the third item stays "Correction 3".
        self.assertIn(f"- {OVERSIZED_NOTE_PREFIX} Correction 2: Rewrite the whole technology section.", notes)
        self.assertIn(f"{ABSENT} Correction 3: Qualify a claim.", notes)
        self.assertIn("- Applied: Qualify the market evidence boundary.", notes)
        self.assertEqual(reviewer_quality_summary(report), {"status": "partial", "unapplied_corrections": 2})

    def test_long_replace_is_skipped_and_its_target_kept(self):
        ok, report = _run(_plan({"find": EXACT_FIND, "replace": "w" * 2001, "reason": "Expand the limitation."}))

        self.assertTrue(ok, report)
        self.assertIn(EXACT_FIND, report)
        self.assertNotIn("w" * 2001, report)
        notes = report.rpartition("## Reviewer Notes")[2]
        self.assertNotIn("No corrections required.", notes)
        self.assertIn(f"- {OVERSIZED_NOTE_PREFIX} Correction 1: Expand the limitation.", notes)
        self.assertEqual(reviewer_quality_summary(report), {"status": "partial", "unapplied_corrections": 1})

    def test_pinned_guardrail_alone_still_rejects_the_plan(self):
        """evidence.py is unchanged (frozen OpenAlex runners pin its bytes); the wrapper salvages."""
        plan = _plan({"find": "x" * 2001, "replace": "y", "reason": "Too long."})
        ok, message = _run(plan, bounded=False)
        self.assertFalse(ok)
        self.assertIn("string_too_long", message)

    def test_any_other_defect_still_rejects_the_plan(self):
        for other in (
            {"find": EXACT_FIND, "replace": "q"},                                   # missing reason
            {"find": EXACT_FIND, "replace": "q", "reason": "ok reason", "x": 1},    # extra field
            {"find": EXACT_FIND, "replace": "q", "reason": "r" * 301},              # reason too long
        ):
            with self.subTest(other=other):
                ok, message = _run(_plan({"find": "x" * 2001, "replace": "y", "reason": "Too long."}, other))
                self.assertFalse(ok)
                self.assertIn("Reviewer patch plan is invalid JSON", message)

    def test_valid_plans_and_legacy_markdown_pass_through_untouched(self):
        valid = _plan({"find": EXACT_FIND, "replace": EXACT_REPLACE, "reason": "Qualify the boundary."})
        for raw in (valid, "# Legacy full Markdown review", '{"corrections": []}', "{not json"):
            with self.subTest(raw=raw[:30]):
                self.assertEqual(neutralize_oversized_corrections(raw), (raw, []))

    def test_skipped_edit_becomes_a_noop_at_its_own_position(self):
        raw = _plan(
            {"find": "a", "replace": "b", "reason": "First edit."},
            {"find": "x" * 2001, "replace": "y", "reason": "Too long."},
        )
        rewritten, notes = neutralize_oversized_corrections(raw)
        items = json.loads(rewritten)["corrections"]
        self.assertEqual(items[0], {"find": "a", "replace": "b", "reason": "First edit."})
        self.assertEqual(items[1]["find"], items[1]["replace"])
        self.assertEqual(notes, [f"{OVERSIZED_NOTE_PREFIX} Correction 2: Too long."])

    def test_note_states_the_bound_the_model_enforces(self):
        for name in ("find", "replace"):
            bounds = {getattr(m, "max_length", None) for m in ReviewerCorrection.model_fields[name].metadata}
            self.assertIn(2000, bounds)
        self.assertIn("2,000 characters", OVERSIZED_NOTE_PREFIX)


class WiringTests(unittest.TestCase):

    def test_worker_status_counts_skipped_edits_as_partial(self):
        tasks = [SimpleNamespace(raw=f"t{i}") for i in range(4)]
        tasks.append(SimpleNamespace(raw=(
            "reviewed report\n\n## Reviewer Notes\n\n"
            f"- {OVERSIZED_NOTE_PREFIX} Correction 1: Rewrite the whole section."
        )))
        self.assertEqual(_review_quality_from_outputs(tasks), {"status": "partial", "unapplied_corrections": 1})

    def test_the_crew_reviewer_uses_the_bounded_guardrail(self):
        import os
        from unittest import mock

        from academic_agent.crew import AcademicAgent
        from tests.test_crew_wiring import _make_collection

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "deepseek-chat"}):
            reviewer = AcademicAgent(_make_collection()).crew().tasks[4]
        self.assertEqual(reviewer.guardrail.__qualname__, "bound_reviewer_guardrail.<locals>.validate_review")


if __name__ == "__main__":
    unittest.main()
