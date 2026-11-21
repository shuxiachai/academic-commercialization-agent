"""Codes in a report shown as words: source types, mode codes, the patent site's name.

The PDF review of 2026-11-20 (production 166130d) found the reference list
reading "Type: company_disclosure" and "Type: market_report", patent titles
ending " - Google Patents", and the prose saying "Assessment mode:
decision_support". All three are display rules in report_display.py, so the
page and the PDF show them alike and the saved file keeps every byte.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from academic_agent import evidence, report_display
from academic_agent.decision_verdict import find_verdict
from academic_agent.report_applicability import add_applicability_block
from academic_agent.report_display import (
    PATENT_SITE_SUFFIX,
    SOURCE_TYPES,
    conclusion_for_display,
    report_for_display,
    text_for_display,
    without_site_name,
)
from academic_agent.run_spec import DecisionContext
from api import samples

_ROOT = Path(__file__).resolve().parents[1]
_RESULT_JS = (_ROOT / "web" / "static" / "js" / "result.js").read_text(encoding="utf-8")


def _entry(source_id: str, title: str, publisher: str, kind: str) -> str:
    return (f"[{source_id}] {title}. {publisher}. Published: 2024-01-02. Accessed: 2026-11-20. "
            f"Type: {kind}. Credibility: medium. Rationale: A reason. https://example.test/{source_id.lower()}")


def _report(*entries: str, legend: str = "*Reference codes: **A** = Academic paper*") -> str:
    return ("# Academic Commercialization Assessment: a topic\n\n## Executive Summary\n\nThe evidence is thin [A1].\n\n"
            "## References\n\n" + legend + "\n\n" + "\n\n".join(entries) + "\n")


# ── Source types ───────────────────────────────────────────────────────────

def test_every_source_type_has_a_phrase_in_both_languages():
    """The table covers evidence.SourceType exactly: a type added there and
    not here would be shown as its code again."""
    codes = set(get_args(evidence.SourceType))
    for language, table in SOURCE_TYPES.items():
        assert set(table) == codes, language
        assert all(phrase and "_" not in phrase for phrase in table.values()), language


@pytest.mark.parametrize(("code", "phrase"), [
    ("academic_paper", "Academic paper"), ("company_disclosure", "Company disclosure"),
    ("market_report", "Market report"), ("reputable_news", "News report"), ("patent", "Patent"),
])
def test_an_english_reference_states_its_type_in_words(code, phrase):
    shown = report_for_display(_report(_entry("M1", "A page", "A publisher", code)))
    assert f"Type: {phrase}. Credibility: medium." in shown
    assert f"Type: {code}." not in shown


def test_a_chinese_reference_states_its_type_in_chinese():
    report = _report(_entry("M1", "某页", "某出版方", "company_disclosure"),
                     legend=report_display._LEGENDS["Simplified Chinese"])
    shown = report_for_display(report)
    assert "类型：公司披露" in shown and "company_disclosure" not in shown


def test_a_type_the_table_does_not_know_is_shown_as_saved():
    shown = report_for_display(_report(_entry("M1", "A page", "A publisher", "trade_press")))
    assert "Type: trade_press." in shown


def test_the_saved_report_keeps_its_codes():
    saved = _report(_entry("M1", "A page", "A publisher", "market_report"))
    before = saved
    report_for_display(saved)
    assert saved == before and "Type: market_report." in saved


# ── The patent site's name ─────────────────────────────────────────────────

def test_the_site_name_rule_is_the_one_result_js_uses():
    """One rule for the Sources tab and the brief (result.js) and for the
    reference list (here): a patent is named alike in both places."""
    js = re.search(r"const PATENT_SITE_SUFFIX = /(.+)/u;", _RESULT_JS)
    assert js is not None
    assert js.group(1) == PATENT_SITE_SUFFIX.pattern


@pytest.mark.parametrize(("title", "shown"), [
    ("US123B2 - Tandem solar cell - Google Patents", "US123B2 - Tandem solar cell"),
    ("Tandem cell - Google Patents.", "Tandem cell."),
    ("A survey of Google Patents data", "A survey of Google Patents data"),
    (" - Google Patents", " - Google Patents"),
])
def test_without_site_name(title, shown):
    assert without_site_name(title) == shown


def test_a_patent_reference_loses_the_site_name_and_keeps_its_publisher():
    entry = _entry("P1", "US123B2 - Tandem solar cell - Google Patents", "Google Patents", "patent")
    shown = report_for_display(_report(entry))
    assert "[P1] US123B2 - Tandem solar cell. Google Patents. Published: 2024-01-02." in shown
    assert " - Google Patents" not in shown


@pytest.mark.parametrize("slug", [s.slug for s in samples.SAMPLES])
def test_no_sample_shows_the_site_name_or_a_type_code(slug):
    saved = samples.read_sample(slug)
    shown = report_for_display(saved)
    assert " - Google Patents" not in shown
    assert not re.search(r"(?:Type: |类型：)[a-z]", shown), slug
    # Each sample's list was rewritten, not skipped: it had codes to replace.
    assert re.search(r"Type: [a-z]", saved), slug


# ── Mode codes ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("saved", "shown"), [
    # The two lines of the 1,820 saved reports that use one (2026-11-21).
    ("**Assessment mode: decision_support.**", "**Assessment mode: decision support.**"),
    ("this is an orientation-mode assessment, not a decision_support verdict.",
     "this is an orientation-mode assessment, not a decision support verdict."),
    # As the production run of 2026-11-18 wrote it.
    ("The report uses decision_support mode.", "The report uses decision support mode."),
    ("Mode `decision_support`.", "Mode decision support."),
    ("Mode `decision_context_incomplete` or decision_context_incomplete.",
     "Mode decision context incomplete or decision context incomplete."),
    ("Mode `orientation`.", "Mode orientation."),
    # "orientation" is a word; only the code is replaced.
    ("An orientation brief.", "An orientation brief."),
    # Not the code: part of a longer name.
    ("decision_support_mode and my_decision_support and decision_supports",
     "decision_support_mode and my_decision_support and decision_supports"),
])
def test_english_prose_says_the_mode_in_words(saved, shown):
    assert text_for_display(saved) == shown
    assert text_for_display(saved, "English") == shown


@pytest.mark.parametrize(("saved", "shown"), [
    ("本报告为 decision_support 模式。", "本报告为决策支持模式。"),
    ("模式：`decision_support`。", "模式：决策支持。"),
    ("评估模式为 `orientation`，", "评估模式为方向性简报，"),
    ("Mode decision_context_incomplete.", "Mode 决策背景不完整."),
    # The model's own gloss after a Chinese term stays (15 of 15 bare uses).
    ("本报告为定位性（orientation）简报。", "本报告为定位性（orientation）简报。"),
])
def test_chinese_prose_says_the_mode_in_chinese(saved, shown):
    assert text_for_display(saved, "Simplified Chinese") == shown


def test_the_reference_list_keeps_a_code_in_a_title():
    """A source's title is the source's: a code in it is not respelt."""
    entry = _entry("A1", "On decision_support systems", "A journal", "academic_paper")
    shown = report_for_display(_report(entry))
    assert "[A1] On decision_support systems. A journal." in shown


def test_a_delivered_report_says_its_mode_in_words_and_keeps_the_gate_paragraph():
    gate = DecisionContext(asset_description="An asset", target_application="An application",
                           decision_owner="An office", decision_type="License it").gate_snapshot()
    body = ("# Academic Commercialization Assessment: a topic\n\n## Executive Summary\n\n"
            "This report uses decision_support mode. Conclusion: DEFER [A1].\n\n## References\n\n"
            + _entry("A1", "A paper", "A journal", "academic_paper") + "\n")
    saved = add_applicability_block(body, decision_gate=gate, output_language="English")
    shown = report_for_display(saved)
    assert "This report uses decision support mode." in shown
    assert "Scope of this assessment:" in shown and "decision_support" not in shown


def test_the_conclusion_card_quotes_the_words_the_report_shows():
    """The page finds the quoted sentence in the report it drew; both say the
    mode in words, or the card's link would find nothing."""
    saved = ("# Report\n\n## 5. Commercialization Opportunities & Recommendations\n\n"
             "In decision_support mode the conclusion is DEFER [A1].\n")
    card = conclusion_for_display(find_verdict(saved), saved)
    assert card["statement"].startswith("In decision support mode the conclusion is DEFER")
    assert card["needle"] in report_for_display(saved)
