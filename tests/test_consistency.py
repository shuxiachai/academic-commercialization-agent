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


_REPORT_ZH = """# 学术成果商业化评估：示例技术

## 执行摘要

{summary}

## 1. 技术概述与成熟度

现有工艺已商业化并广泛部署，是任何新进入者必须超越的基准。

## 5. {heading}

{recommendation}

## 证据局限性

来源稀少。
"""


def _report_zh(summary: str = "该领域尚处早期。", recommendation: str = "建议谨慎推进。",
               heading: str = "商业化机遇与建议") -> str:
    return _REPORT_ZH.format(summary=summary, recommendation=recommendation, heading=heading)


class ChineseReportTests(unittest.TestCase):
    """A Chinese report used to be unreadable: its headings never matched, so
    the result page said the check did not run. The phrases below were
    chosen against the 39 Chinese runs on disk, where the obvious words
    ("立即", "低风险", "进入市场", "值得投资") all turned out to carry other
    subjects; each phrase is therefore bound to commercialisation itself."""

    def test_the_chinese_summary_and_recommendations_are_read_and_section_one_is_not(self):
        text = conclusion_text(_report_zh(summary="摘要句。", recommendation="建议句。"))
        self.assertIn("摘要句", text)
        self.assertIn("建议句", text)
        self.assertNotIn("已商业化并广泛部署", text)

    def test_a_strong_chinese_recommendation_under_a_low_score_is_flagged(self):
        result = check(_report_zh(recommendation="综合评估，建议立即启动商业化。"),
                       {"overall_score": 40.0})
        self.assertTrue(result.checked)
        self.assertEqual(len(result.findings), 1)
        finding = result.findings[0]
        self.assertEqual(finding.severity, "blocker")
        self.assertEqual(finding.kind, "recommendation_exceeds_score")
        self.assertIn("40", finding.detail)
        self.assertIn("60", finding.detail)
        self.assertIn("建议立即启动商业化", finding.excerpt)

    def test_each_chinese_phrase_is_caught(self):
        for phrasing in (
            "立即推进产业化是最优选择。",
            "该技术已具备商业化条件。",
            "商业化条件已成熟。",
            "建议尽快进入市场。",
            "强烈建议投资该方向。",
            "这是极具投资价值的机会。",
            "对投资者而言这是低风险投资。",
        ):
            with self.subTest(phrasing=phrasing):
                result = check(_report_zh(recommendation=phrasing), {"overall_score": 40.0})
                self.assertEqual(len(result.findings), 1, phrasing)

    def test_the_same_recommendation_under_a_high_score_is_not(self):
        result = check(_report_zh(recommendation="建议立即启动商业化。"), {"overall_score": 72.0})
        self.assertEqual(result.findings, ())
        self.assertTrue(result.checked)

    def test_the_other_heading_translation_is_read_too(self):
        result = check(_report_zh(recommendation="建议立即启动商业化。", heading="商业化机会与建议"),
                       {"overall_score": 40.0})
        self.assertEqual(len(result.findings), 1)

    def test_denied_or_conditional_chinese_recommendations_are_not_recommendations(self):
        for phrasing in (
            "目前尚不建议立即商业化。",
            "在完成中试验证之前，不宜立即推进商业化。",
            "该技术尚未具备商业化条件。",
            "若成本问题得到解决，可立即商业化。",
            "只有在界面稳定性验证后才能进入市场。",
        ):
            with self.subTest(phrasing=phrasing):
                result = check(_report_zh(recommendation=phrasing), {"overall_score": 30.0})
                self.assertEqual(result.findings, (), phrasing)

    def test_advice_about_patents_research_or_adjacent_technology_is_not_a_verdict(self):
        """Every one of these sentences is from the runs on disk, scored 50-64."""
        for phrasing in (
            "建议立即在以下方向启动专利申请。",
            "立即启动研发计划，开发连续学习算法。",
            "第二阶段：低风险场景市场切入（12-24个月）。",
            "成功进入市场的可行路径可能是提供集成平台。",
            "这些技术进步可能发挥关键作用，值得投资。",
            "固态锂电池电解质技术已具备基础科学验证，但仍需重大突破。",
        ):
            with self.subTest(phrasing=phrasing):
                result = check(_report_zh(recommendation=phrasing), {"overall_score": 40.0})
                self.assertTrue(result.checked)
                self.assertEqual(result.findings, (), phrasing)

    def test_the_runs_own_translated_headings_are_read(self):
        """The heading translator is a model; the next run may render the two
        headings a third way. The worker hands over the run's own list."""
        report = _report_zh(recommendation="建议立即启动商业化。", heading="商业化路径建议")
        report = report.replace("## 执行摘要", "## 摘要")
        localized = ("# 学术成果商业化评估：", "## 摘要", "## 1. 技术概述与成熟度",
                     "## 2. 专利布局与空白领域", "## 3. 目标行业与应用场景", "## 4. 竞争格局",
                     "## 5. 商业化路径建议", "## 证据局限性", "## 参考文献")
        unaided = check(report, {"overall_score": 40.0})
        self.assertFalse(unaided.checked)
        aided = check(report, {"overall_score": 40.0},
                      output_language="Simplified Chinese", localized_headings=localized)
        self.assertTrue(aided.checked)
        self.assertEqual(len(aided.findings), 1)

    def test_an_incomplete_heading_list_is_ignored(self):
        report = _report_zh(recommendation="建议立即启动商业化。", heading="商业化路径建议")
        report = report.replace("## 执行摘要", "## 摘要")
        result = check(report, {"overall_score": 40.0}, localized_headings=("## 摘要", "## 5. 商业化路径建议"))
        self.assertFalse(result.checked)

    def test_a_language_without_a_phrase_table_is_unchecked_not_consistent(self):
        japanese = ("# 学術成果商業化評価：", "## エグゼクティブサマリー", "## 1. 技術概要", "## 2. 特許",
                    "## 3. 対象産業", "## 4. 競合", "## 5. 商業化の機会と提言", "## 証拠の限界", "## 参考文献")
        report = "\n".join(f"{h}\n\n本文。" for h in japanese)
        for language in ("Japanese", "Traditional Chinese", "German"):
            with self.subTest(language=language):
                result = check(report, {"overall_score": 40.0},
                               output_language=language, localized_headings=japanese)
                self.assertFalse(result.checked)
                self.assertEqual(result.findings, ())

    def test_english_reports_read_exactly_as_before(self):
        flagged = check(_report(recommendation="We recommend immediate commercialization."),
                        {"overall_score": 40.0}, output_language="English")
        self.assertEqual(len(flagged.findings), 1)
        self.assertNotIn("立即", flagged.findings[0].detail)
        clean = check(_report(), {"overall_score": 40.0}, output_language="English")
        self.assertTrue(clean.checked)
        self.assertEqual(clean.findings, ())


class RealChineseReportsTests(unittest.TestCase):
    """Precision on the Chinese corpus the phrases were chosen against."""

    def test_every_chinese_run_on_disk_is_read_and_none_is_flagged(self):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "outputs"
        if not root.is_dir():
            self.skipTest("no runs on disk")
        checked = 0
        for directory in sorted(root.iterdir()):
            report = directory / "commercialization_report.md"
            scores = directory / "commercialization_scores.json"
            if not (report.exists() and scores.exists()):
                continue
            text = report.read_text(encoding="utf-8")
            if "执行摘要" not in text:
                continue
            checked += 1
            result = check(text, json.loads(scores.read_text(encoding="utf-8")))
            with self.subTest(run=directory.name):
                self.assertTrue(result.checked, "a Chinese report was not read")
                self.assertEqual(
                    [f.detail for f in result.findings], [],
                    "a real report was flagged; check precision before shipping")
        if not checked:
            self.skipTest("no Chinese runs on disk")


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


class ScoreBoundaryTests(unittest.TestCase):
    """The thresholds are floors: a score exactly at one is not a contradiction."""

    def test_a_score_exactly_at_the_floor_passes_and_just_below_does_not(self):
        strong = _report(recommendation="We recommend immediate commercialization.")
        self.assertEqual(check(strong, {"overall_score": 60}).findings, ())
        self.assertEqual(len(check(strong, {"overall_score": 59.999}).findings), 1)
        measured = _report(recommendation="We strongly recommend a pilot.")
        self.assertEqual(check(measured, {"overall_score": 55}).findings, ())
        self.assertEqual(len(check(measured, {"overall_score": 54.9}).findings), 1)

    def test_a_numeric_string_score_is_read_and_a_non_numeric_one_is_survived(self):
        strong = _report(recommendation="We recommend immediate commercialization.")
        self.assertEqual(len(check(strong, {"overall_score": "45"}).findings), 1)
        broken = check(strong, {"overall_score": "n/a"})
        self.assertFalse(broken.checked)
        self.assertIn("ValueError", broken.error or "")

    def test_a_missing_or_null_overall_score_checks_nothing_but_is_not_unchecked(self):
        strong = _report(recommendation="We recommend immediate commercialization.")
        for scores in ({"overall_score": None}, {"trl_score": 3}):
            with self.subTest(scores=scores):
                result = check(strong, scores)
                self.assertTrue(result.checked)
                self.assertEqual(result.findings, ())

    def test_only_a_level_two_heading_with_a_space_opens_a_conclusion_section(self):
        body = "We recommend immediate commercialization.\n"
        self.assertEqual(len(check("## EXECUTIVE SUMMARY\n" + body, {"overall_score": 10}).findings), 1)
        self.assertFalse(check("### Executive Summary\n" + body, {"overall_score": 10}).checked)
        self.assertFalse(check("##Executive Summary\n" + body, {"overall_score": 10}).checked)
