"""What the PDF says beside the report (report_summary.py), field by field.

The summary block, the header and footer, the document information and the
download name. Words the page also says are held to i18n.js here, so the
PDF and the page cannot name a dimension, a grade or a draft differently.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

from academic_agent import report_summary
from academic_agent.report_summary import (
    COPY,
    TRL_LEVELS_ZH,
    content_disposition,
    download_names,
    fixed1,
    js_number,
    page_text,
    report_date,
    summary,
)
from academic_agent.decision_verdict import _CARD_COPY
from api import samples

_ROOT = Path(__file__).resolve().parents[1]
_STRINGS = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
# The PDF's own words; every other key of COPY is the page's.
_PDF_ONLY = {"summary_title", "score_unit", "sources", "sources_line", "no_score", "score_unreadable", "header",
             "page", "generated", "model", "run", "title", "title_draft", "subject", "subject_draft", "author"}


def _page_says(key: str) -> tuple[str, str]:
    said = re.findall(rf'^    {key}: (".*"),$', _STRINGS, re.MULTILINE)
    assert len(said) == 2, key
    english, chinese = (json.loads(text) for text in said)
    return english, chinese


def test_the_words_the_page_also_says_are_the_page_s():
    assert set(COPY["English"]) == set(COPY["Simplified Chinese"])
    shared = set(COPY["English"]) - _PDF_ONLY
    assert len(shared) >= 25
    for key in shared:
        english, chinese = _page_says(key)
        assert COPY["English"][key] == english, key
        assert COPY["Simplified Chinese"][key] == chinese, key


def test_the_chinese_readiness_levels_are_the_page_s():
    for level, sentence in TRL_LEVELS_ZH.items():
        assert _page_says(f"trl_level_{level}")[1] == sentence


def test_the_author_is_the_product_s_name():
    english, chinese = _page_says("brand_full")
    assert COPY["English"]["author"] == english and COPY["Simplified Chinese"]["author"] == chinese


_SCORES = {
    "overall_score": 69.3, "trl_score": 7.3, "mrl_score": 6.5, "patent_strength": 2.5,
    "market_accessibility": 3.5, "evidence_confidence": 4.0,
    "trl_label": "TRL 7 (system prototype in operational environment)",
    "key_risks": ["Durability is unproven [A1]."], "key_opportunities": ["License it."],
}
_SOURCES = {"academic_sources": [{}] * 8, "patent_sources": [{}] * 7, "market_sources": [{}] * 9}
_REPORT = ("# T\n\n## Executive Summary\n\nPilot lines exist in Europe [A1].\n\n"
           "## 5. Commercialization Opportunities & Recommendations\n\n- License to a module maker [A1].\n")


def _summary(**overrides):
    given = {"state": "completed", "scores": _SCORES, "sources": _SOURCES, "mode": "decision_support",
             "question": {"decision_owner": "A transfer office", "decision_type": "License it"},
             "markdown": _REPORT, "language": "English"}
    given.update(overrides)
    return summary(**given)


def test_the_summary_of_a_scored_run():
    shown = _summary()
    assert (shown["score"], shown["unit"], shown["band"], shown["band_key"]) == ("69.3", "/ 100", "Moderate", "moderate")
    assert shown["rows"] == [
        ("Technology readiness", "7.3 / 9", "TRL 7 (system prototype in operational environment)"),
        ("Manufacturing readiness", "6.5 / 10", ""),
        ("Patent position", "2.5 / 5", ""),
        ("Market accessibility", "3.5 / 5", ""),
        # As the page writes the number: 4.0 is "4".
        ("Evidence confidence", "4 / 5", ""),
    ]
    assert shown["sources"] == ("Sources", "24 in all · 8 academic · 7 patents · 9 market")
    assert shown["context"] == ("Decision context", "Given: decision support",
                                ["Decision owner: A transfer office", "Decision to make: License it"])
    assert shown["brief"] == [
        ("The report's own summary:", "Pilot lines exist in Europe.", True),
        ("Biggest risk", "Durability is unproven [A1].", False),
        ("First recommended step", "License to a module maker.", False),
    ]


def test_the_summary_in_chinese():
    shown = _summary(language="Simplified Chinese")
    assert shown["band"] == "中等" and shown["title"] == "评估概要"
    assert shown["rows"][0] == ("技术就绪度", "7.3 / 9", "TRL 7（系统原型在实际运行环境中完成演示）")
    assert shown["sources"] == ("来源", "共 24 个 · 学术 8 · 专利 7 · 市场 9")
    assert shown["context"][2] == [f"{_CARD_COPY['Simplified Chinese']['owner']}：A transfer office",
                                   f"{_CARD_COPY['Simplified Chinese']['decision']}：License it"]


@pytest.mark.parametrize(("mode", "line"), [
    ("decision_support", "Given: decision support"), ("orientation", "None given: an orientation brief"),
    ("decision_context_incomplete", "Incomplete: not all four required fields were given"),
    (None, "Not recorded"), ("something else", "Not recorded"),
])
def test_the_decision_context_line(mode, line):
    assert _summary(mode=mode, question=None)["context"] == ("Decision context", line, [])


def test_a_run_that_stopped_before_scoring_says_so_and_nothing_else():
    for state in ("failed", "cancelled", "timeout"):
        assert _summary(state=state, scores=None) == {"note": "This run stopped before scoring, so it has no score."}
    assert _summary(state="failed", scores=None, language="Simplified Chinese") == {"note": "这次运行在评分前停止，没有分数。"}


def test_a_finished_run_whose_scorecard_cannot_be_read_says_that_instead():
    for scores in (None, {}, {"overall_score": "69"}, {"overall_score": 140}, {"overall_score": float("nan")},
                   {"overall_score": True}, ["not", "a", "record"]):
        assert _summary(scores=scores) == {"note": "This run's scorecard could not be read, so no score is shown."}


def test_an_unreadable_dimension_or_registry_costs_only_itself():
    shown = _summary(scores={**_SCORES, "mrl_score": 0, "patent_strength": "3", "market_accessibility": 9},
                     sources={"academic_sources": [], "patent_sources": "x", "market_sources": []})
    assert [row[1] for row in shown["rows"]] == ["7.3 / 9", "—", "—", "—", "4 / 5"]
    assert shown["sources"] is None


def test_a_report_without_a_summary_sentence_still_gives_risk_and_step():
    shown = _summary(markdown="", scores={**_SCORES, "key_risks": [], "key_opportunities": []})
    assert shown["brief"] == [("Biggest risk", "The scorecard lists no risk.", False),
                              ("First recommended step", "The report gives no numbered recommendation.", False)]


def test_numbers_as_javascript_writes_them():
    assert [js_number(v) for v in (4.0, 4, 6.5, 7.3, 10)] == ["4", "4", "6.5", "7.3", "10"]
    # toFixed(1) takes the larger tenth on an exact tie; Python's format would take the even one.
    assert fixed1(68.25) == "68.3" and f"{68.25:.1f}" == "68.2"
    assert [fixed1(v) for v in (69.3, 54.0, 100, 0.05)] == ["69.3", "54.0", "100.0", "0.1"]


def test_every_public_sample_has_a_summary():
    for sample in samples.SAMPLES:
        shown = summary(state="completed", scores=samples.read_sample_scores(sample.slug), sources=None,
                        mode=None, question=None, markdown=samples.read_sample(sample.slug),
                        language=sample.language)
        assert "note" not in shown, sample.slug
        assert all(row[1] != "—" for row in shown["rows"]), sample.slug


@pytest.mark.parametrize(("run_id", "ended", "day"), [
    ("20261118T083403Z-e434f298d40b911342d46653c7c88b74", "2026-11-18T09:01:00+00:00", "2026-11-18"),
    # Ended after midnight UTC: the day the report was made.
    ("20261118T233000Z-e434f298d40b911342d46653c7c88b74", "2026-11-19T00:20:00+00:00", "2026-11-19"),
    # An offset is turned into UTC.
    ("20261118T233000Z-e434f298d40b911342d46653c7c88b74", "2026-11-19T10:20:00+11:00", "2026-11-18"),
    ("20261118T233000Z-e434f298d40b911342d46653c7c88b74", None, "2026-11-18"),
    ("20261118T233000Z-e434f298d40b911342d46653c7c88b74", "not a time", "2026-11-18"),
    ("not-a-run-id", None, ""),
])
def test_report_date(run_id, ended, day):
    assert report_date(run_id, ended) == day


def test_the_page_text_in_english_and_chinese():
    english = page_text(topic="  perovskite\nsolar  cells ", run_id="20261118T083403Z-x",
                        run_link="https://example.test/run/20261118T083403Z-x", date="2026-11-18",
                        model="qwen3.8", language="English")
    assert english["header"] == "ACA · perovskite solar cells"
    assert english["page"].format(page=1, pages=11) == "Page 1 of 11"
    assert english["link_text"] == english["link"] == "https://example.test/run/20261118T083403Z-x"
    assert english["footer"] == "Generated 2026-11-18 UTC · Model: qwen3.8"
    assert english["title"] == "ACA assessment: perovskite solar cells"
    assert "report-display" not in english["subject"] and "perovskite solar cells" in english["subject"]
    chinese = page_text(topic="特高压直流输电", run_id="r", run_link=None, date="2026-11-08", model=None,
                        language="Simplified Chinese", draft=True)
    assert chinese["page"].format(page=1, pages=9) == "第 1 页，共 9 页"
    assert chinese["link"] is None and chinese["link_text"] == "运行 r"
    assert chinese["footer"] == "生成于 2026-11-08（UTC）"
    assert chinese["title"] == "ACA 评估（草稿）：特高压直流输电"


def test_the_download_name_of_an_english_topic():
    assert download_names("Perovskite-silicon tandem solar cells", "2026-11-18") == (
        "ACA-perovskite-silicon-tandem-solar-cells-2026-11-18.pdf",
        "ACA-perovskite-silicon-tandem-solar-cells-2026-11-18.pdf")
    assert download_names("x", "2026-11-18", draft=True)[0] == "ACA-x-2026-11-18-draft.pdf"


def test_the_download_name_of_a_chinese_topic_keeps_its_characters():
    fallback, name = download_names("特高压直流输电", "2026-11-08")
    assert fallback == "ACA-report-2026-11-08.pdf"
    assert name == "ACA-特高压直流输电-2026-11-08.pdf"
    header = content_disposition("特高压直流输电", "2026-11-08")
    assert header.startswith('attachment; filename="ACA-report-2026-11-08.pdf"; filename*=UTF-8\'\'')
    assert unquote(header.split("UTF-8''", 1)[1]) == name
    assert header.isascii()


def test_a_name_never_carries_what_a_file_name_cannot():
    topic = 'a/b\\c:d*e?f"g<h>i|j\tk\x00l 钙钛矿'
    fallback, name = download_names(topic, "2026-11-18")
    for forbidden in '/\\:*?"<>|\t\x00':
        assert forbidden not in name.removesuffix(".pdf") and forbidden not in fallback
    assert fallback.isascii()


def test_a_long_topic_is_cut():
    topic = "an extremely long topic about " + "perovskite silicon tandem photovoltaic modules " * 4
    fallback, name = download_names(topic, "2026-11-18")
    middle = fallback.removeprefix("ACA-").removesuffix("-2026-11-18.pdf")
    assert len(middle) <= 60 and not middle.endswith("-")
    long_chinese = "钙钛矿" * 40
    assert len(download_names(long_chinese, "2026-11-18")[1].removeprefix("ACA-").removesuffix("-2026-11-18.pdf")) <= 60


def test_the_draft_note_is_the_reader_s():
    """A PDF is passed on to people who cannot resume the run, so the notice is
    the one the page shows a reader, not the owner's ("Resuming the run...")."""
    assert report_summary.draft_note("reviewer", "English") == COPY["English"]["draft_reviewed_note"]
    assert report_summary.draft_note("writer", "Simplified Chinese") == COPY["Simplified Chinese"]["draft_note"]
    assert report_summary.draft_note("something", "English") == COPY["English"]["draft_note"]
    for note in (COPY["English"]["draft_note"], COPY["English"]["draft_reviewed_note"]):
        assert "Resuming" not in note
