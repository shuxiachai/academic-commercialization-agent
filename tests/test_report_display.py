"""The report as the page and PDF show it: sentences for codes, a clean reference list.

The saved file is the audit record and is never changed here; what changes is
only what a reader sees. Nothing shown may claim more than the saved gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from academic_agent.report_applicability import _MARKER, add_applicability_block, applicability_for_display
from academic_agent.report_display import report_for_display
from academic_agent.run_spec import DecisionContext

ROOT = Path(__file__).resolve().parents[1]
BODY = "## Executive Summary\n\nEvidence is thin [A1].\n"
REFERENCES = (
    "\n\n## References\n\n*Reference codes: **A** = Academic paper*\n\n"
    "[A1] A title ending in a stop.. Some Journal. Published: 2021-05-01. Accessed: 2026-10-21. "
    "Type: academic_paper. Credibility: high. Rationale: OpenAlex record, 12 citations.. https://doi.org/10.1/x\n\n"
    "[M1] A market page. Yahoo. Published: n.d.. Accessed: 2026-10-21. Type: market_report. "
    "Credibility: medium. Rationale: Commercial market estimate.. https://e.test/m1\n"
)


def _delivered(language="English", **context):
    gate = DecisionContext(**context).gate_snapshot()
    return add_applicability_block("# Report\n\n" + BODY + REFERENCES, decision_gate=gate,
                                   output_language=language)


SUPPORT = {
    "asset_description": "A benchtop nitrate-removal prototype",
    "target_application": "Small municipal water treatment plants",
    "decision_owner": "University technology transfer manager",
    "decision_type": "Whether to fund a six-month field pilot",
}


def test_an_orientation_brief_reads_as_sentences():
    shown = report_for_display(_delivered())
    assert shown.startswith("# Report\n\n**Scope of this assessment:** An orientation brief: no decision "
                            "context was given, so it gives no GO/NO_GO for a particular decision-maker. "
                            "No success criteria were given, so any thresholds in the report are the "
                            "analyst's proposals.\n\n## Executive Summary")
    assert _MARKER not in shown and "`orientation`" not in shown and "`not_established`" not in shown


def test_the_chinese_paragraph_is_chinese():
    shown = report_for_display(_delivered("Simplified Chinese"))
    assert "**评估范围：**方向性简报：没有提供具体决策场景，因此不针对任何决策者给出 GO/NO_GO。" in shown
    assert "未提供成功标准，报告中的决策门槛均为分析者建议。" in shown
    assert "Mode `" not in shown


def test_decision_support_says_so_and_keeps_the_caveat():
    shown = report_for_display(_delivered(**SUPPORT, success_criteria="Nitrate below 10 mg/L",
                                          success_criteria_authority="owner_approved"))
    assert "Decision support: the context given allows a GO/NO_GO for this decision-maker" in shown
    assert "The decision-maker approved the success criteria." in shown
    assert "a cited benchmark does not establish owner approval" in shown


def test_a_support_label_without_the_permission_is_not_upgraded():
    delivered = _delivered(**SUPPORT)
    allowed = "Actor-specific `GO/NO_GO` is permitted by context completeness; the conclusion still depends on the cited evidence."
    forged = delivered.replace(allowed, "Actor-specific `GO/NO_GO` is not assessed.")
    assert forged != delivered
    shown = report_for_display(forged)
    assert "No GO/NO_GO is given for a particular decision-maker." in shown
    assert "allows a GO/NO_GO" not in shown


def test_a_permission_the_mode_does_not_carry_keeps_the_saved_words():
    delivered = _delivered()
    forged = delivered.replace("Actor-specific `GO/NO_GO` is not assessed.",
                               "Actor-specific `GO/NO_GO` is permitted by context completeness; "
                               "the conclusion still depends on the cited evidence.")
    shown = report_for_display(forged)
    assert "Mode `orientation`" in shown and "Scope of this assessment" not in shown


@pytest.mark.parametrize("language", ["Japanese", "German", "French", "Spanish"])
def test_other_languages_keep_the_saved_paragraph(language):
    delivered = _delivered(language)
    shown = report_for_display(delivered)
    assert shown.split("## References")[0] == applicability_for_display(delivered).split("## References")[0]


def test_a_paragraph_outside_the_preamble_is_left_alone():
    gate = DecisionContext().gate_snapshot()
    block = add_applicability_block("", decision_gate=gate, output_language="English").strip()
    report = "# Report\n\n" + BODY + "\n\n" + block + "\n"
    assert report_for_display(report).split("## References")[0] == report


def test_the_reference_list_loses_its_doubled_stops():
    shown = report_for_display(_delivered())
    refs = shown.split("## References", 1)[1]
    assert ".." not in refs
    assert ("[A1] A title ending in a stop. Some Journal. Published: 2021-05-01. Accessed: 2026-10-21. "
            "Type: academic_paper. Credibility: high. Rationale: OpenAlex record, 12 citations. "
            "https://doi.org/10.1/x") in refs
    assert "Published: n.d. Accessed:" in refs


def test_a_chinese_report_gets_chinese_reference_labels():
    shown = report_for_display(_delivered("Simplified Chinese"))
    assert "## 参考文献" in shown and "## References" not in shown
    assert ("[A1] A title ending in a stop. Some Journal. 发布：2021-05-01 · 访问：2026-10-21 · 类型：学术论文 · "
            "可信度：高 · 依据：OpenAlex record, 12 citations. https://doi.org/10.1/x") in shown
    assert "发布：未注明" in shown and "类型：市场报告" in shown


def test_an_unrecognised_reference_line_is_kept():
    odd = "# Report\n\nText.\n\n## References\n\n[A1] Something in another shape https://e.test/a\n"
    assert report_for_display(odd) == odd


@pytest.mark.parametrize("name", ["hyperloop.md", "solid-state-batteries-ev-zh.md"])
def test_the_production_samples_keep_every_reference_and_link(name):
    saved = (ROOT / "examples" / name).read_text(encoding="utf-8")
    shown = report_for_display(saved)
    ids = lambda text: [line.split("]")[0] for line in text.splitlines() if line[:2] in ("[A", "[P", "[M")]  # noqa: E731
    links = lambda text: [line.rsplit(" ", 1)[-1] for line in text.splitlines() if line[:2] in ("[A", "[P", "[M")]  # noqa: E731
    assert ids(shown) == ids(saved) and links(shown) == links(saved)
    assert ".." not in shown.split("## ", 999)[-1]
    assert saved == (ROOT / "examples" / name).read_text(encoding="utf-8")
