"""benchmark_check must judge report structure the way production does.

The held-out batch reported 24/30 complete reports. All six "incomplete"
ones were the Chinese reports, which carried every section under localized
headings: the checker compared every run with the English list, while
production's validate_final_report checks a run's own localized headings.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import benchmark_check
from academic_agent.evidence import _REQUIRED_REPORT_HEADINGS, validate_final_report

_ZH = [
    "# 学术成果商业化评估：", "## 执行摘要", "## 1. 技术概述与成熟度",
    "## 2. 专利格局与空白领域", "## 3. 目标行业与应用场景", "## 4. 竞争格局",
    "## 5. 商业化机会与建议", "## 证据局限性", "## 参考文献",
]


def _report(headings: list[str]) -> str:
    return "\n\n".join(f"{h}漂浮式海上风电\n正文。" for h in headings)


def _zh_report(drop: str | None = None) -> str:
    # References is always written in English by the canonical section.
    headings = [h for h in _ZH[:-1] if h != drop] + ["## References"]
    return _report(headings)


def _production_missing(markdown: str, localized: list[str] | None) -> set[str]:
    errors = validate_final_report(
        markdown, {}, required_headings=tuple(localized) if localized else None,
        output_language="Chinese" if localized else "English")
    prefix = "Missing required heading: "
    return {e[len(prefix):] for e in errors if e.startswith(prefix)}


class RequiredHeadingTests(unittest.TestCase):

    def test_complete_chinese_report_passes_with_its_localized_headings(self):
        complete, missing = benchmark_check._check_sections(_zh_report(), _ZH)
        self.assertTrue(complete, missing)

    def test_previous_behaviour_marked_it_incomplete(self):
        """Pins the regression: the English list fails a complete Chinese report."""
        complete, _missing = benchmark_check._check_sections(_zh_report())
        self.assertFalse(complete)

    def test_a_missing_localized_section_is_still_caught(self):
        complete, missing = benchmark_check._check_sections(_zh_report(drop="## 4. 竞争格局"), _ZH)
        self.assertFalse(complete)
        self.assertEqual(missing, ["## 4. 竞争格局"])

    def test_english_runs_keep_the_english_list(self):
        self.assertEqual(benchmark_check._required_headings([]), _REQUIRED_REPORT_HEADINGS)
        self.assertEqual(benchmark_check._required_headings(None), _REQUIRED_REPORT_HEADINGS)

    def test_same_missing_headings_as_the_production_validator(self):
        cases = [
            (_zh_report(), _ZH),
            (_zh_report(drop="## 执行摘要"), _ZH),
            (_zh_report(drop="## 证据局限性"), _ZH),
            (_report(list(_REQUIRED_REPORT_HEADINGS)), None),
            (_report([h for h in _REQUIRED_REPORT_HEADINGS if "Executive" not in h]), None),
        ]
        for markdown, localized in cases:
            with self.subTest(localized=bool(localized), size=len(markdown)):
                _ok, missing = benchmark_check._check_sections(markdown, localized)
                self.assertEqual(set(missing), _production_missing(markdown, localized))


class AnalyseRunTests(unittest.TestCase):
    """End to end through analyse_run, reading validated_sources.json."""

    def test_localized_headings_are_read_from_the_run_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "meta.json").write_text(json.dumps(
                {"num": "H06", "rep": 1, "topic": "漂浮式海上风电", "industry": "x",
                 "status": "success", "expected_trl_range": [8, 9]}), encoding="utf-8")
            (run / "validated_sources.json").write_text(json.dumps(
                {"localized_headings": _ZH, "academic_sources": [], "patent_sources": [],
                 "market_sources": []}, ensure_ascii=False), encoding="utf-8")
            (run / "commercialization_report.md").write_text(_zh_report(), encoding="utf-8")
            row = benchmark_check.analyse_run(run)
        self.assertTrue(row["sections_complete"], row["missing_sections"])
        self.assertEqual(row["missing_sections"], "")
