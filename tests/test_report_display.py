"""The report as the page and PDF show it: sentences for codes, a clean reference list.

The saved file is the audit record and is never changed here; what changes is
only what a reader sees. Nothing shown may claim more than the saved gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from academic_agent.report_applicability import _MARKER, add_applicability_block, applicability_for_display
from academic_agent.report_display import HEADING_TRANSLATIONS, report_for_display
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
                            "context was given, so it gives no GO / NO-GO for a particular decision-maker. "
                            "No success criteria were given, so any thresholds in the report are the "
                            "analyst's proposals.\n\n## Executive Summary")
    assert _MARKER not in shown and "`orientation`" not in shown and "`not_established`" not in shown


def test_the_chinese_paragraph_is_chinese():
    shown = report_for_display(_delivered("Simplified Chinese"))
    assert "**评估范围：**方向性简报：没有提供具体决策场景，因此不针对任何决策者给出 GO / NO-GO。" in shown
    assert "未提供成功标准，报告中的决策门槛均为分析者建议。" in shown
    assert "Mode `" not in shown


def test_decision_support_says_so_and_keeps_the_caveat():
    shown = report_for_display(_delivered(**SUPPORT, success_criteria="Nitrate below 10 mg/L",
                                          success_criteria_authority="owner_approved"))
    assert "Decision support: the context given allows a GO / NO-GO for this decision-maker" in shown
    assert "The decision-maker approved the success criteria." in shown
    assert "a cited benchmark does not establish owner approval" in shown


def test_a_support_label_without_the_permission_is_not_upgraded():
    delivered = _delivered(**SUPPORT)
    allowed = "Actor-specific `GO/NO_GO` is permitted by context completeness; the conclusion still depends on the cited evidence."
    forged = delivered.replace(allowed, "Actor-specific `GO/NO_GO` is not assessed.")
    assert forged != delivered
    shown = report_for_display(forged)
    assert "No GO / NO-GO is given for a particular decision-maker." in shown
    assert "allows a GO / NO-GO" not in shown and "GO/NO_GO" not in shown


def test_a_permission_the_mode_does_not_carry_keeps_the_saved_words():
    delivered = _delivered()
    forged = delivered.replace("Actor-specific `GO/NO_GO` is not assessed.",
                               "Actor-specific `GO/NO_GO` is permitted by context completeness; "
                               "the conclusion still depends on the cited evidence.")
    shown = report_for_display(forged)
    assert "Mode `orientation`" in shown and "Scope of this assessment" not in shown


@pytest.mark.parametrize("language", ["Japanese", "German", "French", "Spanish"])
def test_other_languages_keep_the_saved_paragraph(language):
    """Its words as saved, with the verdict vocabulary spelt as the page spells
    it; the English heading under it is shown in the paragraph's language
    (tests/test_report_headings.py)."""
    delivered = _delivered(language)
    shown = report_for_display(delivered)
    saved_words = applicability_for_display(delivered).split("## References")[0]
    assert "`GO/NO_GO`" in saved_words and "`not_established`" in saved_words
    heading = HEADING_TRANSLATIONS[language][1]
    assert shown.split("## References")[0] == (
        saved_words.replace("`GO/NO_GO`", "GO / NO-GO").replace("## Executive Summary", heading))


def test_a_paragraph_outside_the_preamble_is_left_alone():
    gate = DecisionContext().gate_snapshot()
    block = add_applicability_block("", decision_gate=gate, output_language="English").strip()
    report = "# Report\n\n" + BODY + "\n\n" + block + "\n"
    # Not turned into the scope sentences and still under its marker; only the
    # spelling every line of prose gets: the verdict vocabulary, and the mode
    # code as a word (the provenance code is not one of those and stays).
    assert "`GO/NO_GO`" in report and "Mode `orientation`" in report
    assert report_for_display(report).split("## References")[0] == (
        report.replace("`GO/NO_GO`", "GO / NO-GO").replace("Mode `orientation`", "Mode orientation"))


def test_the_reference_list_loses_its_doubled_stops():
    shown = report_for_display(_delivered())
    refs = shown.split("## References", 1)[1]
    assert ".." not in refs
    assert ("[A1] A title ending in a stop. Some Journal. Published: 2021-05-01. Accessed: 2026-10-21. "
            "Type: Academic paper. Credibility: high. Rationale: OpenAlex record, 12 citations. "
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


# ── A report with no applicability paragraph ─────────────────────────────
# The paragraph is added on delivery by the web application. A report made
# from the command line has none, and until 2026-11-15 such a report was
# taken for English whatever it was written in: the committed Chinese sample
# (examples/uhvdc-transmission-zh.md) was shown with "References" and
# "Published: ... Type: academic_paper. Credibility: medium" under Chinese
# prose. What does say the language of every delivered report is the legend
# evidence.py writes as the first line under the heading.

ZH_LEGEND = "*文献编码说明：**A** = 学术论文 · **P** = 专利 · **M** = 市场/行业来源*"
EN_LEGEND = "*Reference codes: **A** = Academic paper · **P** = Patent · **M** = Market/industry source*"
ENTRIES = (
    "[A1] A title ending in a stop.. Some Journal. Published: 2021-05-01. Accessed: 2026-10-21. "
    "Type: academic_paper. Credibility: high. Rationale: OpenAlex record, 12 citations.. https://doi.org/10.1/x\n\n"
    "[M1] A market page. Yahoo. Published: n.d.. Accessed: 2026-10-21. Type: market_report. "
    "Credibility: medium. Rationale: Commercial market estimate.. https://e.test/m1\n"
)
NOTES = "\n## Reviewer Notes\n\nNo corrections required.\n"


def _bare(legend, body="## 执行摘要\n\n证据不足 [A1]。\n"):
    """A report as the command line writes it: no applicability paragraph."""
    return "# 报告\n\n" + body + "\n\n## References\n\n" + legend + "\n\n" + ENTRIES + NOTES


def test_a_chinese_report_without_the_paragraph_is_known_by_its_legend():
    shown = report_for_display(_bare(ZH_LEGEND))
    assert "\n## 参考文献\n" in shown and "## References" not in shown
    assert ("[A1] A title ending in a stop. Some Journal. 发布：2021-05-01 · 访问：2026-10-21 · 类型：学术论文 · "
            "可信度：高 · 依据：OpenAlex record, 12 citations. https://doi.org/10.1/x") in shown
    assert "发布：未注明" in shown and "类型：市场报告" in shown
    assert ZH_LEGEND in shown, "The legend is the report's own line and stays"
    for label in ("Published:", "Accessed:", "Type:", "Credibility:", "Rationale:"):
        assert label not in shown, label


def test_an_english_report_without_the_paragraph_is_as_before():
    saved = _bare(EN_LEGEND, "## Executive Summary\n\nEvidence is thin [A1].\n")
    shown = report_for_display(saved)
    assert "\n## References\n" in shown and "参考文献" not in shown
    assert ("[A1] A title ending in a stop. Some Journal. Published: 2021-05-01. Accessed: 2026-10-21. "
            "Type: Academic paper. Credibility: high. Rationale: OpenAlex record, 12 citations. "
            "https://doi.org/10.1/x") in shown
    assert "\n## Reviewer Notes\n" in shown
    # No legend at all (a report older than the legend): English, as before.
    older = saved.replace(EN_LEGEND + "\n\n", "")
    assert "\n## References\n" in report_for_display(older) and "发布：" not in report_for_display(older)


def test_the_paragraph_still_decides_where_there_is_one():
    """The legend is asked only when the paragraph is absent, so a delivered
    report is shown exactly as it was before the legend was read."""
    gate = DecisionContext().gate_snapshot()
    for block_language, legend, chinese in (("English", ZH_LEGEND, False), ("Simplified Chinese", EN_LEGEND, True),
                                            ("Japanese", ZH_LEGEND, False)):
        delivered = add_applicability_block(_bare(legend), decision_gate=gate, output_language=block_language)
        shown = report_for_display(delivered)
        assert ("## 参考文献" in shown) is chinese, (block_language, legend)
        assert ("发布：2021-05-01" in shown) is chinese, (block_language, legend)


def test_only_the_line_under_the_heading_is_the_legend():
    # The same words quoted in the body of an English report say nothing about it.
    quoted = _bare(EN_LEGEND, "## Executive Summary\n\nA Chinese report would say:\n\n" + ZH_LEGEND + "\n\nEvidence [A1].\n")
    assert "## References" in report_for_display(quoted) and "发布：" not in report_for_display(quoted)
    # ...and neither does a legend further down the list than its first line.
    moved = _bare(EN_LEGEND).replace(ENTRIES, ENTRIES + "\n" + ZH_LEGEND + "\n")
    assert "## References" in report_for_display(moved)


def test_the_other_legends_name_languages_the_list_is_not_translated_into():
    from academic_agent import report_display

    japanese = "*引用コード：**A** = 学術論文 · **P** = 特許 · **M** = 市場/業界情報*"
    assert report_display._report_language(_bare(japanese)) == "Japanese"
    shown = report_for_display(_bare(japanese))
    assert "## References" in shown and "Published: 2021-05-01. Accessed: 2026-10-21." in shown
    assert "\n## Reviewer Notes\n" in shown


def test_the_legends_are_the_ones_the_pipeline_writes():
    """report_display keeps its own copy, because evidence.py imports CrewAI
    and the display code is read on every page load. This holds the copy to
    the original: a legend reworded there must be reworded here."""
    from academic_agent import evidence, report_display

    assert report_display._LEGENDS == evidence._REF_LEGEND
    assert ZH_LEGEND == evidence._REF_LEGEND["Simplified Chinese"] and EN_LEGEND == evidence._REF_LEGEND_EN
    written = evidence._canonical_reference_section("正文 [A1]。", {}, output_language="Simplified Chinese")
    assert written.split("\n## References\n", 1)[1].lstrip("\n").split("\n", 1)[0] == ZH_LEGEND


def test_a_chinese_report_names_its_proofreading_record_in_chinese():
    """The notes are a record written by code in English and stay as saved;
    their heading is the one word of them a reader of the report sees (the
    page folds the rest under a Chinese line)."""
    shown = report_for_display(_bare(ZH_LEGEND))
    assert shown.endswith("\n## 自动校对记录\n\nNo corrections required.\n") and "Reviewer Notes" not in shown
    # Only the last such heading is the pipeline's; one in the prose is the author's.
    twice = _bare(ZH_LEGEND, "## Reviewer Notes\n\n正文 [A1]。\n")
    shown = report_for_display(twice)
    assert shown.count("## Reviewer Notes") == 1 and shown.count("## 自动校对记录") == 1
    assert shown.index("## Reviewer Notes") < shown.index("## 参考文献") < shown.index("## 自动校对记录")
    # The page's fold finds the section by its heading, in either language.
    script = (ROOT / "web/static/js/result.js").read_text(encoding="utf-8")
    assert "const NOTES_HEADING = /^##\\s+(?:Reviewer Notes|自动校对记录)\\s*$/;" in script


def test_the_committed_chinese_sample_reads_in_chinese_and_is_not_changed():
    path = ROOT / "examples" / "uhvdc-transmission-zh.md"
    saved = path.read_text(encoding="utf-8")
    assert "Decision applicability" not in saved and "决策适用性" not in saved, "The sample has no paragraph"
    shown = report_for_display(saved)
    assert "\n## 参考文献\n" in shown and "\n## References\n" not in shown
    assert "\n## 自动校对记录\n" in shown and "## Reviewer Notes" not in shown
    references = shown.split("\n## 参考文献\n", 1)[1].split("\n## ", 1)[0]
    entries = [line for line in references.splitlines() if line[:2] in ("[A", "[P", "[M")]
    assert len(entries) == 22
    for line in entries:
        assert " 发布：" in line and " · 访问：2026-11-08 · 类型：" in line and " · 可信度：" in line and " · 依据：" in line, line
        for label in ("Published:", "Accessed:", "Type:", "Credibility:", "Rationale:"):
            assert label not in line, line
    ids = lambda text: [line.split("]")[0] for line in text.splitlines() if line[:2] in ("[A", "[P", "[M")]  # noqa: E731
    links = lambda text: [line.rsplit(" ", 1)[-1] for line in text.splitlines() if line[:2] in ("[A", "[P", "[M")]  # noqa: E731
    assert ids(shown) == ids(saved) and links(shown) == links(saved)
    # Everything above the list is as saved.
    assert shown.split("\n## 参考文献\n", 1)[0] == saved.split("\n## References\n", 1)[0]
    assert saved == path.read_text(encoding="utf-8")
