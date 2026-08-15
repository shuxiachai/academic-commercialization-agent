"""Tests for the report-versus-scorecard check.

Nothing in the pipeline compares those two: the reviewer never sees the
scorecard, the scorer never sees the reviewed report. So a report can urge
moving quickly to market beside a scorecard reading 40 and every existing
guardrail passes, because each output is internally consistent.

An external review proposed adding a seventh agent to read both. This is the
same check in code, which is what the review actually asked for — every
comparison it listed is deterministic.

What these mostly pin is where it must stay silent. The first version also
compared maturity language against TRL, and on all 30 baseline reports it
produced two flags, both wrong: a paragraph attributes properties to several
subjects and a phrase match cannot tell which one carries it. That axis was
dropped rather than shipped, and the tests below exist so the surviving one
does not acquire the same problem.
"""

from __future__ import annotations

import unittest

from academic_agent.consistency import check, conclusion_text

_REPORT = """# Assessment: Example Technology

## Executive Summary

{summary}

## 1. Technology Overview & Maturity

The incumbent process is commercially available and widely deployed today,
which is the benchmark any new entrant must beat.

## 5. Commercialization Opportunities & Recommendations

{recommendation}

## Evidence Limitations

Sources are sparse.
"""


def _report(summary: str = "The field is early.", recommendation: str = "Proceed carefully.") -> str:
    return _REPORT.format(summary=summary, recommendation=recommendation)


class ScopeTests(unittest.TestCase):
    """Only the sections where the report speaks in its own voice."""

    def test_evidence_sections_are_not_read(self):
        """Sections 1-4 describe what the evidence says, competitors included.
        "the incumbent is commercially available" is a fact about somebody
        else, and reading it as this report's claim is how the dropped axis
        produced both of its false positives."""
        text = conclusion_text(_report())
        self.assertNotIn("incumbent", text)

    def test_the_summary_and_recommendations_are_read(self):
        text = conclusion_text(_report(summary="SUMMARY MARK",
                                       recommendation="RECOMMENDATION MARK"))
        self.assertIn("SUMMARY MARK", text)
        self.assertIn("RECOMMENDATION MARK", text)


class RecommendationVersusScoreTests(unittest.TestCase):

    def test_a_strong_recommendation_under_a_low_score_is_flagged(self):
        result = check(
            _report(recommendation="We recommend immediate commercialization."),
            {"overall_score": 40.0})
        self.assertEqual(result.blockers, 1)
        self.assertEqual(result.findings[0].kind, "recommendation_exceeds_score")

    def test_one_sentence_is_one_finding(self):
        """That sentence matches three entries in the phrase table. Reporting
        it three times makes one disagreement look like three."""
        result = check(
            _report(recommendation="We strongly recommend immediate "
                                   "commercialization of this technology."),
            {"overall_score": 40.0})
        self.assertEqual(len(result.findings), 1)

    def test_the_same_recommendation_under_a_high_score_is_not(self):
        """The check is about disagreement, not about the words. A strong
        recommendation on a strong assessment is the system working."""
        result = check(
            _report(recommendation="We recommend immediate commercialization."),
            {"overall_score": 82.0})
        self.assertEqual(result.findings, ())

    def test_a_measured_recommendation_under_a_low_score_is_not_flagged(self):
        result = check(
            _report(recommendation="Further laboratory validation is required "
                                   "before any commercial step."),
            {"overall_score": 40.0})
        self.assertEqual(result.findings, ())

    def test_the_finding_names_both_numbers(self):
        """A reader has to be able to check the call without rerunning it."""
        result = check(_report(recommendation="Strongly recommend proceeding."),
                       {"overall_score": 41.0})
        self.assertIn("41", result.findings[0].detail)
        self.assertIn("55", result.findings[0].detail)


class NegationTests(unittest.TestCase):
    """An honest report about an immature technology says these words in
    order to deny them. Reading the denial as the claim would flag precisely
    the reports being careful."""

    def test_a_denied_recommendation_is_not_a_recommendation(self):
        for phrasing in (
            "We do not recommend immediate commercialization.",
            "The evidence cannot support immediate commercialization.",
            "Further work is required before immediate commercialization.",
            "This is not ready for commercialization.",
        ):
            with self.subTest(phrasing=phrasing):
                result = check(_report(recommendation=phrasing),
                               {"overall_score": 30.0})
                self.assertEqual(result.findings, (), phrasing)


class RobustnessTests(unittest.TestCase):

    def test_a_missing_scorecard_means_no_verdict(self):
        result = check(_report(), {})
        self.assertFalse(result.checked)
        self.assertEqual(result.findings, ())

    def test_a_report_without_the_expected_sections_means_no_verdict(self):
        """Not silently "consistent". A report whose structure changed is a
        case this cannot judge, and saying so beats implying it passed."""
        result = check("# Title\n\nSome prose with no sections.",
                       {"overall_score": 10.0})
        self.assertFalse(result.checked)

    def test_a_scorecard_without_an_overall_score_is_survived(self):
        result = check(_report(recommendation="Strongly recommend proceeding."),
                       {"trl_score": 3.0})
        self.assertTrue(result.checked)
        self.assertEqual(result.findings, ())

    def test_it_never_raises(self):
        """It runs beside a finished assessment; an audit bug must not destroy
        the thing it was auditing. The recommendation has to match, or the
        comparison that would raise is never reached."""
        result = check(_report(recommendation="We recommend immediate action."),
                       {"overall_score": object()})
        self.assertFalse(result.checked)
        self.assertIn("TypeError", result.error or "")

    def test_the_payload_is_json_serialisable(self):
        import json

        result = check(_report(recommendation="We recommend immediate action."),
                       {"overall_score": 20.0})
        self.assertIsInstance(json.dumps(result.as_dict()), str)


class RealReportsTests(unittest.TestCase):
    """Precision on the corpus this was tuned against."""

    def test_no_baseline_report_is_flagged(self):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "outputs" / "benchmark"
        if not root.is_dir():
            self.skipTest("no benchmark runs on disk")
        checked = 0
        for directory in sorted(root.iterdir()):
            report = directory / "commercialization_report.md"
            scores = directory / "commercialization_scores.json"
            if not (report.exists() and scores.exists()):
                continue
            checked += 1
            result = check(report.read_text(encoding="utf-8"),
                           json.loads(scores.read_text(encoding="utf-8")))
            with self.subTest(run=directory.name):
                self.assertEqual(
                    [f.detail for f in result.findings], [],
                    "a real report was flagged; check precision before shipping")
        if not checked:
            self.skipTest("no complete runs on disk")
