"""A report in another language is read under headings in that language.

On 2026-11-18 a Chinese run on production was saved with English headings
over Chinese text: "Executive Summary", "1. Technology Overview & Maturity"
and so on, with only the reference list's heading in Chinese. The headings
were translated by a model call at the start of the run; the call failed
twice, the English originals came back looking like a translation, and the
resumed run reused them without asking again. Nothing on the page said so.

Held here:

- the table: the nine required headings in every language a report can be
  asked for, kept to evidence.py's list and to the words other code reads;
- the run: a language the table has makes no call, so nothing can fail; a
  language it lacks still asks the model, and a failure is told apart from a
  translation;
- the display: a report saved with the English headings is shown under the
  table's, on the page, in the PDF and in the decision card's own words, and
  the saved bytes stay as they are;
- the spelling: "GO/NO_GO" is shown as "GO / NO-GO", as the page writes it;
- the resume: the headings are asked for again only where no paid agent
  output would be thrown away for them;
- the page: a report still under English headings says so in one line.

The fixtures are excerpts of the two production runs, read back with the
maintainer's consent (tests/fixtures/report_headings/README.md): the resumed
run's saved report cut down to its title, paragraph, headings, eight lines of
text and seven reference entries, and the fields of both runs' status that
show the two failed attempts and what the resume reused.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
import textwrap
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from academic_agent import auxiliary_usage as aux
from academic_agent import language, llm_config, report_display
from academic_agent import llm_parameter_fallback as fallback
from academic_agent.decision_verdict import _SKIPPED_SECTIONS, card_text, find_verdict
from academic_agent.report_applicability import _MARKER, add_applicability_block
from academic_agent.report_display import (
    GO_NO_GO,
    HEADING_TRANSLATIONS,
    REPORT_HEADINGS,
    conclusion_for_display,
    display_parts,
    fixed_headings,
    report_for_display,
    text_for_display,
)
from academic_agent.run_spec import DecisionContext, RunSpec
from api import main, runs
from ui import pdf_export

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _ROOT / "tests" / "fixtures" / "report_headings"
_FIXTURE = _FIXTURES / "resumed_run_report_excerpt.md"
_RESULT_JS = _ROOT / "web" / "static" / "js" / "result.js"
_I18N_JS = _ROOT / "web" / "static" / "js" / "i18n.js"
_ZH = HEADING_TRANSLATIONS["Simplified Chinese"]
_SECTIONS = REPORT_HEADINGS[1:-1]


def _saved() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def _recorded(run: str) -> dict:
    """What the deployment's status showed for the failed run or the resumed one."""
    return json.loads((_FIXTURES / "run_status_excerpts.json").read_text(encoding="utf-8"))[run]


def _english_headed(topic: str = "sodium-ion batteries", legend: str = "") -> str:
    """A report body under the nine English headings, as a failed translation leaves it."""
    parts = [f"{REPORT_HEADINGS[0]} {topic}", ""]
    for heading in _SECTIONS:
        parts += [heading, "", "Texte du rapport [A1].", ""]
    parts += [REPORT_HEADINGS[-1], "", legend or "*Reference codes: **A** = Academic paper*", ""]
    return "\n".join(parts)


def _headings(text: str) -> list[str]:
    return [line for line in text.split("\n") if re.match(r"#{1,2} ", line)]


# ── The table ─────────────────────────────────────────────────────────────

def test_the_english_list_is_the_one_the_pipeline_requires():
    """A copy, because evidence.py imports CrewAI and this module is read for
    every report a page shows. A heading added there must be added here."""
    from academic_agent.evidence import _REQUIRED_REPORT_HEADINGS

    assert REPORT_HEADINGS == _REQUIRED_REPORT_HEADINGS


@pytest.mark.parametrize("name", sorted(HEADING_TRANSLATIONS))
def test_every_language_has_the_nine_with_their_marks_and_numbers(name):
    fixed = HEADING_TRANSLATIONS[name]
    assert len(fixed) == len(REPORT_HEADINGS) == 9
    assert len(set(fixed)) == 9
    for english, shown in zip(REPORT_HEADINGS, fixed, strict=True):
        marks = english.split(" ", 1)[0]
        assert shown.startswith(marks + " ") and not shown.startswith(marks + "#")
        assert shown == shown.strip() and "\n" not in shown
        assert shown != english
        number = re.match(r"## (\d)\. ", english)
        if number:
            assert shown.startswith(f"## {number[1]}. ")
        else:
            assert not re.match(r"#+ \d", shown)
    # The title is a prefix the topic is appended to.
    assert fixed[0].endswith((":", "："))


def test_the_table_has_every_language_a_report_can_be_asked_for():
    """The eleven a topic's language is detected among, and every choice in
    the page's menu. The worker turns the menu's "Chinese" into "Simplified
    Chinese" (pipeline_worker._UI_TO_API_LANG)."""
    detected = {info["name"] for info in language.LANGUAGE_REGISTRY.values()} - {"English"}
    assert detected <= set(HEADING_TRANSLATIONS)
    page = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    menu = re.search(r'<select class="chip-select" id="language".*?</select>', page, re.DOTALL)[0]
    offered = set(re.findall(r'<option value="([^"]+)"', menu)) - {"English"}
    assert len(offered) == 10
    assert {"Simplified Chinese" if value == "Chinese" else value for value in offered} <= set(HEADING_TRANSLATIONS)
    worker = (_ROOT / "src" / "academic_agent" / "pipeline_worker.py").read_text(encoding="utf-8")
    assert '_UI_TO_API_LANG: dict[str, str] = {"Chinese": "Simplified Chinese"}' in worker
    assert fixed_headings("English") is None and fixed_headings(None) is None and fixed_headings("") is None
    assert fixed_headings("Klingon") is None


def test_the_chinese_headings_are_the_words_the_other_readers_know():
    """consistency.py finds the conclusion sections by these words, the
    decision card skips the limitations and the reference list by them, and
    the page's brief finds the summary and the recommendations by them."""
    from academic_agent import consistency

    plain = [heading.lstrip("#").strip() for heading in _ZH]
    assert consistency._conclusion_headings(_ZH) == (plain[1], plain[6])
    assert any(word in plain[1] for word in consistency._CONCLUSION_SECTIONS["zh"])
    assert any(word in plain[6] for word in consistency._CONCLUSION_SECTIONS["zh"])
    assert _SKIPPED_SECTIONS.match(plain[7]) and _SKIPPED_SECTIONS.match(plain[8])
    page = _RESULT_JS.read_text(encoding="utf-8")
    summary = re.search(r"const SUMMARY_HEADINGS = /(.+?)/i;", page)[1]
    recommendations = re.search(r"const RECOMMENDATION_HEADINGS = /(.+?)/i;", page)[1]
    assert re.search(summary, _ZH[1]) and re.search(recommendations, _ZH[6])
    # The title is the product's name as the page's own header writes it.
    brand = re.findall(r'brand_full: "([^"]+)"', _I18N_JS.read_text(encoding="utf-8"))
    assert brand == ["Academic Commercialization Assessment", "学术成果商业化评估"]
    assert REPORT_HEADINGS[0] == f"# {brand[0]}:" and _ZH[0] == f"# {brand[1]}："


def test_a_title_in_either_chinese_wording_gives_the_history_its_topic(tmp_path):
    from ui.run_reader import _extract_topic_from_report

    for title in (_ZH[0] + "钠离子电池", "# 学术商业化评估：钠离子电池", "# 学术成果商业化评估:钠离子电池"):
        path = tmp_path / "report.md"
        path.write_text(title + "\n\n正文。\n", encoding="utf-8")
        assert _extract_topic_from_report(path) == "钠离子电池"


# ── The run: which headings the writer is given ───────────────────────────

@pytest.mark.allow_llm
@pytest.mark.parametrize("name", sorted(HEADING_TRANSLATIONS))
def test_a_language_the_table_has_asks_no_model(name, tmp_path, monkeypatch):
    """The call that failed on production cannot fail if it is not made."""
    def refused(*_args, **_kwargs):
        raise AssertionError("no request may be sent for a language the table has")

    monkeypatch.setattr(language, "urlopen", refused)
    monkeypatch.setattr(language, "_llm_call", refused)
    ledger = aux.Collector(tmp_path / aux.FILE_NAME)
    with aux.bind(ledger):
        headings = language.translate_headings(REPORT_HEADINGS, name)
    assert headings == HEADING_TRANSLATIONS[name]
    assert isinstance(headings, tuple)
    assert ledger.snapshot()["calls"] == []
    assert not language.headings_untranslated(headings, name)


def test_the_writer_is_told_the_table_headings_with_the_topic_on_the_title():
    """The seam: what reaches the crew's inputs, not what the table holds."""
    from tests.test_checkpoint_worker import _source_collection

    collection = _source_collection()
    collection.output_language = "Simplified Chinese"
    collection.display_topic = "钠离子电池用于电网储能"
    collection.localized_headings = list(language.translate_headings(REPORT_HEADINGS, "Simplified Chinese"))
    told = collection.crew_inputs()["localized_headings"].split("\n")
    assert told == ["# 学术成果商业化评估：钠离子电池用于电网储能", *_ZH[1:]]


@pytest.fixture
def thinking_only(monkeypatch):
    """The deployment of the production run: a model that refuses thinking-off."""
    fallback.reset()
    monkeypatch.setattr(llm_config, "resolve_provider_config", lambda: llm_config.ProviderConfig(
        "qwen", "qwen3.8-2.4t-a95b", "https://provider.invalid/v1", "offline-key"))
    monkeypatch.setattr(language.time, "sleep", lambda _seconds: None)
    yield
    fallback.reset()


def _transport(monkeypatch, *outcomes):
    sent: list[dict] = []
    queue = list(outcomes)

    @contextmanager
    def urlopen(request, *, timeout):
        sent.append(json.loads(request.data))
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        yield SimpleNamespace(read=lambda: json.dumps(
            {"usage": {"prompt_tokens": 120, "completion_tokens": 90, "total_tokens": 210},
             "choices": [{"message": {"content": outcome}}]}).encode())

    monkeypatch.setattr(language, "urlopen", urlopen)
    return sent


def _thinking_refusal() -> HTTPError:
    body = {"error": {"message": "<400> InternalError.Algo.InvalidParameter: The value of the "
                                 "enable_thinking parameter is restricted to True.",
                      "type": "invalid_request_error", "code": "invalid_parameter_error"}}
    return HTTPError("https://provider.invalid/v1/chat/completions", 400, "error", {},
                     io.BytesIO(json.dumps(body).encode()))


@pytest.mark.allow_llm
def test_the_two_failed_attempts_of_the_production_run_leave_english_headings(monkeypatch, thinking_only, tmp_path):
    """What the run's ledger showed: heading_translation twice, call_failed twice.

    A fresh worker has learned nothing about its model, so the first request
    is the refusal of thinking-off; the adapted request then fails by itself.
    The helper returns the originals, which nothing told apart from a
    translation. A language the table lacks still takes this path, so the
    failure has to be recognisable."""
    sent = _transport(monkeypatch, _thinking_refusal(), TimeoutError("timed out"))
    ledger = aux.Collector(tmp_path / aux.FILE_NAME)
    with aux.bind(ledger), pytest.warns(UserWarning, match="TimeoutError"):
        headings = language.translate_headings(REPORT_HEADINGS, "Vietnamese")
    calls = ledger.snapshot()["calls"]
    assert [(call["stage"], call["outcome"]) for call in calls] == [("heading_translation", "call_failed")] * 2
    # The same record the failed run left, field for field.
    recorded = _recorded("failed_run")["auxiliary_usage"]
    assert recorded["call_count"] == 2
    kept = ("sequence", "stage", "unit", "model", "state", "outcome", "tokens")
    assert [{key: call[key] for key in kept} for call in calls] == [
        {key: call[key] for key in kept} for call in recorded["calls"]]
    assert [body["enable_thinking"] for body in sent] == [False, True]
    assert headings == REPORT_HEADINGS
    assert language.headings_untranslated(headings, "Vietnamese")
    assert language.headings_untranslated([], "Vietnamese")
    # An English report is under English headings by design.
    assert not language.headings_untranslated(headings, "English")
    assert not language.headings_untranslated([], "English") and not language.headings_untranslated([], "")


@pytest.mark.allow_llm
def test_a_language_the_table_lacks_is_still_translated_by_the_model(monkeypatch, thinking_only):
    answer = "\n".join(f"{heading.split(' ', 1)[0]} tiêu đề {index}" for index, heading in enumerate(REPORT_HEADINGS))
    sent = _transport(monkeypatch, _thinking_refusal(), answer)
    headings = language.translate_headings(REPORT_HEADINGS, "Vietnamese")
    assert headings == tuple(answer.split("\n"))
    assert "Vietnamese" in sent[-1]["messages"][-1]["content"]
    assert not language.headings_untranslated(headings, "Vietnamese")


def test_headings_other_than_the_required_nine_are_not_taken_from_the_table():
    with patch("academic_agent.language._llm_call", return_value="# 标题\n## 摘要") as call:
        assert language.translate_headings(("# Title", "## Summary"), "Simplified Chinese") == ("# 标题", "## 摘要")
    call.assert_called_once()


# ── The display: a report saved with English headings ─────────────────────

def test_the_saved_chinese_report_is_shown_under_chinese_headings():
    saved = _saved()
    assert _headings(saved)[:8] == ["# Academic Commercialization Assessment: 钠离子电池用于电网储能", *_SECTIONS]
    shown = report_for_display(saved)
    assert _headings(shown) == [
        "# 学术成果商业化评估：钠离子电池用于电网储能",
        "## 执行摘要",
        "## 1. 技术概述与成熟度",
        "## 2. 专利布局与空白领域",
        "## 3. 目标行业与应用场景",
        "## 4. 竞争格局",
        "## 5. 商业化机遇与建议",
        "## 证据局限性",
        "## 参考文献",
    ]
    for english in REPORT_HEADINGS:
        assert english not in shown
    # The text under them is the saved text.
    for line in ("以下专利空白讨论为初步研究，不构成法律意见、权利有效性判断或自由实施（FTO）意见。",
                 "- 钠离子电池用于电网储能已不再只是概念：一项研究对三款商用18650钠离子电芯进行了拆解、"
                 "电化学测试和事后分析，并明确指出商用钠离子电池正在进入市场 [A4]。"):
        assert line in saved.split("\n") and line in shown.split("\n")
    # The report's own words run straight into the identifier, with no space.
    assert "不评估任何特定主体的GO/NO_GO；actor-specific GO/NO_GO is not assessed。" in saved
    assert "不评估任何特定主体的GO / NO-GO；actor-specific GO / NO-GO is not assessed。" in shown
    assert "GO/NO_GO" not in shown and "NO_GO" not in shown
    assert _saved() == saved


def test_the_display_of_the_fixture_differs_from_the_saved_file_only_where_it_should():
    saved, shown = _saved(), report_for_display(_saved())
    before = [line for line in saved.split("\n") if line.strip() and line != _MARKER]
    after = [line for line in shown.split("\n") if line.strip()]
    assert len(before) == len(after)
    changed = [(a, b) for a, b in zip(before, after, strict=True) if a != b]
    kinds = {
        "heading": [pair for pair in changed if pair[0].startswith("#")],
        "scope": [pair for pair in changed if pair[0].startswith(">")],
        "reference": [pair for pair in changed if re.match(r"\[[APM]\d+\]", pair[0])],
        "spelling": [pair for pair in changed if "GO/NO_GO" in pair[0] and not pair[0].startswith(">")],
    }
    assert len(kinds["heading"]) == 9 and len(kinds["scope"]) == 1 and len(kinds["reference"]) == 7
    assert len(kinds["spelling"]) == 3
    assert sum(len(pairs) for pairs in kinds.values()) == len(changed)
    for a, b in kinds["spelling"]:
        assert b == a.replace("GO/NO_GO", GO_NO_GO)


def test_the_two_parts_meet_where_the_displayed_report_is_cut():
    """The title stands before the scope paragraph and changes length when it
    is translated, which the old cut, counted in the saved text, ignored."""
    saved = _saved()
    head, rest = display_parts(saved)
    assert head + rest == report_for_display(saved)
    assert head.startswith("# 学术成果商业化评估：钠离子电池用于电网储能\n\n**评估范围：**")
    assert head.endswith("报告中的决策门槛均为分析者建议。")
    assert rest.startswith("\n\n## 执行摘要\n")
    for report in (_english_headed(), "# Title\n\nBody.\n", "Body only.\n", "", "# T\n## References\n\n*x*\n"):
        for hint in (None, "Portuguese", "Simplified Chinese"):
            head, rest = display_parts(report, hint)
            assert head + rest == report_for_display(report, hint)
    head, rest = display_parts(_english_headed("painéis solares"), "Portuguese")
    assert head == "# Avaliação da comercialização da pesquisa acadêmica: painéis solares\n"
    assert rest.startswith("\n## Resumo executivo\n")


@pytest.mark.parametrize("name", sorted(HEADING_TRANSLATIONS))
def test_the_runs_recorded_language_names_the_headings_of_a_report_that_names_none(name):
    """A Portuguese or Hindi report has an English paragraph and an English
    legend: only the run knows its language. The API passes it."""
    report = _english_headed("topic words")
    fixed = HEADING_TRANSLATIONS[name]
    shown = report_for_display(report, name)
    gap = " " if fixed[0].endswith(":") else ""
    # The reference list is the report's own business: its heading is shown in
    # Chinese only where the report itself (paragraph or legend) is Chinese.
    assert _headings(shown) == [f"{fixed[0]}{gap}topic words", *fixed[1:-1], "## References"]
    # Without it the report is taken for English, as a sample or a file is.
    assert _headings(report_for_display(report)) == _headings(report)
    assert _headings(report_for_display(report, "English")) == _headings(report)
    assert _headings(report_for_display(report, "Klingon")) == _headings(report)
    # A record the table does not know names no language at all.
    assert report_display._heading_language(report, name) == name
    assert report_display._heading_language(report, "Klingon") == "English"
    assert report_display._heading_language(report) == "English"


def test_what_the_report_itself_says_comes_before_the_runs_record():
    korean = _english_headed(legend=report_display._LEGENDS["Korean"])
    assert _headings(report_for_display(korean))[1] == "## 요약"
    assert _headings(report_for_display(korean, "Japanese"))[1] == "## 요약"
    # A delivered Korean report has an English paragraph over that legend.
    delivered = add_applicability_block(korean, decision_gate=DecisionContext().gate_snapshot(),
                                        output_language="Korean")
    shown = report_for_display(delivered)
    assert "**Scope of this assessment:**" in shown and _headings(shown)[1] == "## 요약"
    # Its own legend names it before the run's record does.
    assert _headings(report_for_display(delivered, "Portuguese"))[1] == "## 요약"
    # The reference list is translated for a Chinese report only, heading included.
    assert _headings(shown)[-1] == "## References"
    # An English paragraph leaves room only for a language it has no copy in:
    # with a Chinese or a Japanese legend, or record, the report is English.
    for name in ("Simplified Chinese", "Japanese"):
        forged = add_applicability_block(_english_headed(legend=report_display._LEGENDS[name]),
                                         decision_gate=DecisionContext().gate_snapshot(), output_language="English")
        assert _headings(report_for_display(forged))[1] == "## Executive Summary"
        assert _headings(report_for_display(forged, name))[1] == "## Executive Summary"
    english = add_applicability_block(_english_headed(), decision_gate=DecisionContext().gate_snapshot(),
                                      output_language="English")
    assert _headings(report_for_display(english, "Portuguese"))[1] == "## Resumo executivo"
    assert _headings(report_for_display(english, "Hindi"))[1] == "## कार्यकारी सारांश"
    german = add_applicability_block(_english_headed(), decision_gate=DecisionContext().gate_snapshot(),
                                     output_language="German")
    assert _headings(report_for_display(german))[1] == "## Zusammenfassung"
    assert _headings(report_for_display(german, "French"))[1] == "## Zusammenfassung"


def test_an_english_report_keeps_its_headings():
    english = add_applicability_block(_english_headed(), decision_gate=DecisionContext().gate_snapshot(),
                                      output_language="English")
    assert _headings(report_for_display(english)) == _headings(english)
    assert _headings(report_for_display(english, "English")) == _headings(english)
    assert _headings(report_for_display(english, None)) == _headings(english)


def test_a_report_whose_headings_were_translated_keeps_the_writers_words():
    sample = (_ROOT / "examples" / "uhvdc-transmission-zh.md").read_text(encoding="utf-8")
    written = _headings(sample)
    assert written[0] == "# 学术商业化评估：特高压直流输电" and written[1] == "## 执行摘要"
    shown = _headings(report_for_display(sample))
    assert shown[:8] == written[:8]
    assert shown[8:] == ["## 参考文献", "## 自动校对记录"]


def test_only_a_line_that_is_exactly_a_required_heading_changes():
    body = "\n".join([
        "# Academic Commercialization Assessment: 主题",
        "",
        "## Executive Summary ",          # a trailing space is still the heading
        "### Executive Summary",          # a sub-heading the writer made
        "## Executive Summary (draft)",   # not the required heading
        "正文提到 ## Executive Summary 这几个词。",
        "# Academic Commercialization Assessment: 第二个标题不是开头的标题",
        "## Evidence Limitations\r",
        "",
        "## References",
        "",
        report_display._LEGENDS["Simplified Chinese"],
        "",
        "## Reviewer Notes",
        "",
        "## Executive Summary",           # after the reference list: not a section of the report
    ])
    shown = report_for_display(body).split("\n")
    assert shown[0] == "# 学术成果商业化评估：主题"
    assert shown[2] == "## 执行摘要 "
    assert shown[3:7] == body.split("\n")[3:7]
    assert shown[7] == "## 证据局限性\r"
    assert shown[9] == "## 参考文献" and shown[13] == "## 自动校对记录"
    assert shown[15] == "## Executive Summary"
    # A title that is only the prefix, and one that is not the product's.
    assert report_for_display("# Academic Commercialization Assessment:\n\n## References\n\n"
                              + report_display._LEGENDS["Simplified Chinese"] + "\n").startswith("# 学术成果商业化评估：\n")
    other = "# 另一个标题\n\n## References\n\n" + report_display._LEGENDS["Simplified Chinese"] + "\n"
    assert report_for_display(other).startswith("# 另一个标题\n")


# ── The spelling ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(("saved", "shown"), [
    ("no actor-specific GO/NO_GO is assessed", "no actor-specific GO / NO-GO is assessed"),
    ("未评估针对具体决策者的 `GO/NO_GO`。", "未评估针对具体决策者的 GO / NO-GO。"),
    ("**GO/NO_GO Status:** Not assessed.", "**GO / NO-GO Status:** Not assessed."),
    ("a GO/NO-GO for this owner", "a GO / NO-GO for this owner"),
    ("GO / NO_GO and GO /NO-GO", "GO / NO-GO and GO / NO-GO"),
    ("未进行GO/NO_GO决策评估", "未进行GO / NO-GO决策评估"),
    ("already GO / NO-GO", "already GO / NO-GO"),
])
def test_the_verdict_vocabulary_is_written_the_pages_way(saved, shown):
    assert text_for_display(saved) == shown
    assert text_for_display(shown) == shown


@pytest.mark.parametrize("kept", [
    "a go/no-go decision at each stage gate",      # English prose, lower case
    "Go/No-Go criteria",
    "The conclusion is NO_GO.",                     # the verdict word alone is the report's
    "rGO/NO_GO is not a compound of graphene oxide",
    "ERGO/NO_GOAL",
    "GO/NO_GO_allowed",                             # an identifier that goes on
    "GO/NO_GOAL",
    "`go_no_go_allowed`",
    "GO or NO_GO",
])
def test_everything_else_is_left_as_written(kept):
    assert text_for_display(kept) == kept


def test_the_spelling_changes_in_the_prose_and_the_notes_and_not_in_a_sources_title():
    report = (
        "# Report\n\n## Executive Summary\n\nNo actor-specific GO/NO_GO is assessed [A1].\n\n"
        "## References\n\n*Reference codes: **A** = Academic paper*\n\n"
        "[A1] A GO/NO-GO framework for pilots. Some Journal. Published: 2021-05-01. Accessed: 2026-10-21. "
        "Type: academic_paper. Credibility: high. Rationale: Cited for its GO/NO_GO gates. https://doi.org/10.1/x\n\n"
        "## Reviewer Notes\n\n- Checked the GO/NO_GO sentence against [A1].\n"
    )
    shown = report_for_display(report)
    assert "No actor-specific GO / NO-GO is assessed [A1]." in shown
    assert "[A1] A GO/NO-GO framework for pilots. Some Journal." in shown
    assert "Rationale: Cited for its GO/NO_GO gates." in shown
    assert "- Checked the GO / NO-GO sentence against [A1]." in shown
    assert shown.count(GO_NO_GO) == 2


def test_the_scope_paragraph_says_it_the_same_way_in_every_form():
    gate = DecisionContext().gate_snapshot()
    for name, expected in (
        ("English", "so it gives no GO / NO-GO for a particular decision-maker."),
        ("Simplified Chinese", "因此不针对任何决策者给出 GO / NO-GO。"),
        # No sentences of ours in Japanese: the saved words, without their code marks.
        ("Japanese", "特定の担当者向け GO / NO-GO は評価していません。"),
    ):
        delivered = add_applicability_block("# 报告\n\n## 执行摘要\n\n正文。\n", decision_gate=gate, output_language=name)
        assert "`GO/NO_GO`" in delivered
        shown = report_for_display(delivered)
        assert expected in shown and "GO/NO_GO" not in shown
        head, rest = display_parts(delivered)
        assert head + rest == shown and expected in head
    for scope in report_display._SCOPE.values():
        assert all("GO/NO" not in sentence for sentence in scope.values())


# ── The decision card reads the saved report and speaks the displayed one ──

_SUPPORT = DecisionContext(
    asset_description="钠离子电池正极材料", target_application="电网储能",
    decision_owner="技术转移办公室", decision_type="是否对外许可",
)
_VERDICT_REPORT = (
    "# Academic Commercialization Assessment: 钠离子电池\n\n"
    "## Executive Summary\n\n钠离子电池已进入示范阶段 [A1]。\n\n"
    "## 5. Commercialization Opportunities & Recommendations\n\n"
    "关于 GO/NO_GO 的问题，结论为 DEFER：循环寿命数据不足 [A1]。中试数据出来后再回答 GO/NO_GO [A1]。\n\n"
    "## Evidence Limitations\n\n数据有限 [A1]。\n\n"
    "## References\n\n" + report_display._LEGENDS["Simplified Chinese"] + "\n"
)


def _delivered_verdict_report() -> str:
    return add_applicability_block(_VERDICT_REPORT, decision_gate=_SUPPORT.gate_snapshot(),
                                   output_language="Simplified Chinese")


def test_the_card_names_the_section_and_quotes_the_sentence_as_the_page_shows_them():
    saved = _delivered_verdict_report()
    read = find_verdict(saved)
    assert read["status"] == "stated" and read["verdict"] == "defer"
    assert read["section"] == "5. Commercialization Opportunities & Recommendations"
    assert "GO/NO_GO" in read["statement"] and "GO/NO_GO" in read["needle"]
    said = conclusion_for_display(read, saved)
    assert said["section"] == "5. 商业化机遇与建议"
    assert said["statement"] == read["statement"].replace("GO/NO_GO", GO_NO_GO)
    assert said["needle"] == read["needle"].replace("GO/NO_GO", GO_NO_GO)
    assert len(read["follows"]) == 1 and "GO/NO_GO" in read["follows"][0]
    assert said["follows"] == [read["follows"][0].replace("GO/NO_GO", GO_NO_GO)]
    assert [item["section"] for item in said["statements"]] == ["5. 商业化机遇与建议"]
    assert said["statements"][0]["needle"] == said["needle"]
    # Nothing about the verdict moves, and the answer the rule gave is not edited in place.
    assert (said["status"], said["verdict"]) == (read["status"], read["verdict"])
    assert set(said) == set(read) and read["section"].startswith("5. Commercialization")
    # The page finds the passage by these words in the report it drew.
    shown = report_for_display(saved)
    plain = re.sub(r"\*\*|`", "", shown)
    assert said["needle"] in plain and read["needle"] not in plain
    assert f"## {said['section']}" in shown.split("\n") and f"## {read['section']}" not in shown


def test_a_conclusion_in_an_english_report_or_under_a_heading_of_the_writers_is_left_alone():
    english = "# Report\n\n## Executive Summary\n\nThe conclusion is DEFER because data are thin [A1].\n"
    read = find_verdict(english)
    assert conclusion_for_display(read, english) == read
    own = _VERDICT_REPORT.replace("## 5. Commercialization Opportunities & Recommendations", "## 结论与建议")
    assert conclusion_for_display(find_verdict(own), own)["section"] == "结论与建议"
    nothing = find_verdict("# Report\n\nNo verdict here.\n")
    assert conclusion_for_display(nothing, "# Report\n") == nothing
    disagreeing = find_verdict(_VERDICT_REPORT.replace("数据有限 [A1]。", "数据有限 [A1]。")
                               .replace("钠离子电池已进入示范阶段 [A1]。", "**Decision:** GO."))
    assert disagreeing["status"] == "conflicting"
    said = conclusion_for_display(disagreeing, _VERDICT_REPORT)
    assert [item["section"] for item in said["statements"]] == ["执行摘要", "5. 商业化机遇与建议"]


@pytest.fixture
def run(monkeypatch, tmp_path):
    """A finished run on disk whose report is the given saved text."""
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    runs._registry.clear()

    def make(saved: str, *, language_name="Simplified Chinese", context=None,
             run_id="20261118T094559Z-6a59d6f9d435d933a1411169f222436e"):
        directory = tmp_path / run_id
        directory.mkdir()
        gate = (context or DecisionContext()).gate_snapshot()
        status = {"stage": "Done", "done": True, "topic": "钠离子电池用于电网储能",
                  "output_language": language_name, "decision_gate": gate}
        (directory / "status.json").write_text(json.dumps(status), encoding="utf-8")
        RunSpec(topic="钠离子电池用于电网储能", decision_context=context).save(directory)
        (directory / "commercialization_report.md").write_text(saved, encoding="utf-8", newline="\n")
        return run_id, directory

    yield make
    runs._registry.clear()


def test_the_page_gets_chinese_headings_and_the_download_gets_every_saved_byte(run):
    saved = _saved()
    run_id, directory = run(saved)
    client = TestClient(main.app)
    shown = client.get(f"/api/runs/{run_id}/report", params={"view": "display"})
    assert shown.status_code == 200
    assert shown.text == report_for_display(saved)
    assert "## 执行摘要" in shown.text.split("\n") and "## Executive Summary" not in shown.text
    for view in ({}, {"view": "saved"}):
        assert client.get(f"/api/runs/{run_id}/report", params=view).content == saved.encode("utf-8")
    assert (directory / "commercialization_report.md").read_bytes() == saved.encode("utf-8")


def test_the_runs_language_reaches_the_report_the_page_asks_for(run):
    """The seam: a hint computed and never passed would leave a Portuguese
    report under English headings with every unit test green."""
    report = _english_headed("painéis solares")
    run_id, _ = run(report, language_name="Portuguese")
    shown = TestClient(main.app).get(f"/api/runs/{run_id}/report", params={"view": "display"}).text
    assert _headings(shown)[:2] == ["# Avaliação da comercialização da pesquisa acadêmica: painéis solares",
                                    "## Resumo executivo"]


def test_the_decision_endpoint_speaks_the_displayed_report(run):
    saved = _delivered_verdict_report()
    run_id, _ = run(saved, context=_SUPPORT)
    body = TestClient(main.app).get(f"/api/runs/{run_id}/decision").json()
    assert body["asked"] is True
    assert body["conclusion"] == conclusion_for_display(find_verdict(saved), saved)
    assert body["conclusion"]["section"] == "5. 商业化机遇与建议"
    assert GO_NO_GO in body["conclusion"]["needle"] and "GO/NO_GO" not in json.dumps(body, ensure_ascii=False)


# ── The PDF ───────────────────────────────────────────────────────────────

def _pdf_text(path: Path) -> str:
    import fitz  # PyMuPDF, already a dependency of the uploads path

    with fitz.open(path) as document:
        return re.sub(r"\s+", " ", " ".join(page.get_text() for page in document))


def test_the_runs_language_reaches_the_card_and_both_pdfs_too(run):
    """Four call sites take the run's recorded language: the page's report,
    the decision card, and the PDF with and without the card. A Portuguese
    report names its language nowhere, so each of them shows which it is."""
    portuguese = HEADING_TRANSLATIONS["Portuguese"]
    body = "\n".join([
        f"{REPORT_HEADINGS[0]} painéis solares", "", REPORT_HEADINGS[1], "", "Resumo do relatório [A1].", "",
        REPORT_HEADINGS[6], "", "The conclusion is DEFER because pilot data are missing [A1].", "",
        REPORT_HEADINGS[-1], "", "*Reference codes: **A** = Academic paper*", "",
    ])
    asked = add_applicability_block(body, decision_gate=_SUPPORT.gate_snapshot(), output_language="Portuguese")
    client = TestClient(main.app)

    run_id, directory = run(asked, language_name="Portuguese", context=_SUPPORT)
    conclusion = client.get(f"/api/runs/{run_id}/decision").json()["conclusion"]
    assert conclusion["status"] == "stated"
    assert conclusion["section"] == portuguese[6].lstrip("# ") == "5. Oportunidades de comercialização e recomendações"
    assert client.get(f"/api/runs/{run_id}/report.pdf").status_code == 200
    text = _pdf_text(directory / "commercialization_report.pdf")
    assert "Resumo executivo" in text and "5. Oportunidades de comercialização e recomendações" in text
    assert "Executive Summary" not in text and "Commercialization Opportunities" not in text

    plain_id, plain = run(_english_headed("painéis solares"), language_name="Portuguese",
                          run_id="20261118T101500Z-0123456789abcdef0123456789abcdef")
    assert client.get(f"/api/runs/{plain_id}/report.pdf").status_code == 200
    text = _pdf_text(plain / "commercialization_report.pdf")
    assert "Resumo executivo" in text and "Executive Summary" not in text


def test_the_pdf_of_the_saved_chinese_report_has_chinese_headings(run):
    run_id, directory = run(_saved())
    assert TestClient(main.app).get(f"/api/runs/{run_id}/report.pdf").status_code == 200
    pdf = directory / "commercialization_report.pdf"
    text = _pdf_text(pdf)
    for heading in ("学术成果商业化评估：钠离子电池用于电网储能", "执行摘要", "1. 技术概述与成熟度",
                    "5. 商业化机遇与建议", "证据局限性", "参考文献"):
        assert heading in text
    assert "Executive Summary" not in text and "Evidence Limitations" not in text
    assert GO_NO_GO in text and "GO/NO_GO" not in text
    assert pdf_export.pdf_carries_display(pdf) and not pdf_export.pdf_carries_decision_card(pdf)


def test_a_pdf_exported_before_the_headings_were_shown_in_chinese_is_built_once_more(run):
    """An export is cached for good. One made of this report before the
    heading table has its English headings, and pdf_cache_complete alone
    calls that file good."""
    saved = _saved()
    run_id, directory = run(saved)
    with patch.object(pdf_export, "DISPLAY_MARK", "report-display:v1"):
        old = pdf_export._generate_pdf(saved, directory, output_language="Simplified Chinese")
    assert pdf_export.pdf_cache_complete(old) and not pdf_export.pdf_carries_display(old)
    assert "Executive Summary" in _pdf_text(old)
    client = TestClient(main.app)
    assert client.get(f"/api/runs/{run_id}/report.pdf").status_code == 200
    assert pdf_export.pdf_carries_display(old)
    assert "Executive Summary" not in _pdf_text(old) and "执行摘要" in _pdf_text(old)
    built = old.read_bytes()
    with patch.object(pdf_export, "_generate_pdf", wraps=pdf_export._generate_pdf) as render:
        assert client.get(f"/api/runs/{run_id}/report.pdf").content == built
    render.assert_not_called()


def test_a_decision_support_pdf_carries_both_marks_and_the_card_in_the_displayed_words(run):
    saved = _delivered_verdict_report()
    run_id, directory = run(saved, context=_SUPPORT)
    pdf = directory / "commercialization_report.pdf"
    # One with the card and without the display mark is stale too.
    head, rest = display_parts(saved)
    with patch.object(pdf_export, "DISPLAY_MARK", "report-display:v1"):
        pdf_export._generate_pdf(head + rest, directory, output_language="Simplified Chinese",
                                 decision_card=card_text(None, find_verdict(saved), "Simplified Chinese"),
                                 card_at=len(head))
    assert pdf_export.pdf_carries_decision_card(pdf) and not pdf_export.pdf_carries_display(pdf)
    assert "出自报告“5. Commercialization Opportunities & Recommendations”一节" in _pdf_text(pdf)
    client = TestClient(main.app)
    assert client.get(f"/api/runs/{run_id}/report.pdf").status_code == 200
    assert pdf_export.pdf_carries_decision_card(pdf) and pdf_export.pdf_carries_display(pdf)
    text = _pdf_text(pdf)
    assert "出自报告“5. 商业化机遇与建议”一节" in text
    assert "Commercialization Opportunities" not in text and "GO/NO_GO" not in text
    built = pdf.read_bytes()
    with patch.object(pdf_export, "_generate_pdf", wraps=pdf_export._generate_pdf) as render:
        assert client.get(f"/api/runs/{run_id}/report.pdf").content == built
    render.assert_not_called()


# ── The resume ────────────────────────────────────────────────────────────

def _untranslated_collection():
    from tests.test_checkpoint_worker import _source_collection

    collection = _source_collection()
    collection.output_language = "Simplified Chinese"
    collection.display_topic = "钠离子电池用于电网储能"
    collection.localized_headings = list(REPORT_HEADINGS)
    return collection


class _ListeningCrew:
    """tests.test_checkpoint_worker._FakeCrew, remembering what the crew was told."""

    def __new__(cls):
        from tests.test_checkpoint_worker import _FakeCrew

        class Listening(_FakeCrew):
            def kickoff(self, *, inputs):
                self.told = dict(inputs)
                return super().kickoff(inputs=inputs)

        return Listening()


def _resume(tmp_path, parent_directory: Path, parent_id: str, child_id: str, *, keep: tuple[str, ...]):
    from academic_agent.run_spec import RESUME_SNAPSHOT_DIRECTORY
    from tests.test_checkpoint_worker import _run_worker

    snapshot = tmp_path / child_id / RESUME_SNAPSHOT_DIRECTORY / "checkpoints"
    for node in keep:
        shutil.copytree(parent_directory / "checkpoints" / node, snapshot / node)
    shutil.rmtree(parent_directory)
    crew = _ListeningCrew()
    # The child reads its collection from the snapshot; a fresh search would be this one.
    directory = _run_worker(tmp_path, child_id, _untranslated_collection(), crew, resume_from=parent_id)
    return crew, directory


def test_a_resumed_run_gets_its_headings_when_no_agent_output_is_lost_for_them(tmp_path):
    """The production parent kept English headings in its saved collection,
    which read as "already translated", so the child asked nothing."""
    from academic_agent.checkpoint_runtime import TASK_NODES
    from tests.test_checkpoint_worker import _FakeCrew, _run_worker

    parent_id, child_id = "20261118T090017Z-parentwithenglish", "20261118T094559Z-childaskedagain"
    parent = _run_worker(tmp_path, parent_id, _untranslated_collection(), _FakeCrew())
    saved = json.loads((parent / "checkpoints" / "retrieval" / "manifest.json").read_text(encoding="utf-8"))
    crew, child = _resume(tmp_path, parent, parent_id, child_id, keep=("retrieval",))

    assert crew.executed == list(TASK_NODES)
    assert crew.told["localized_headings"].split("\n") == ["# 学术成果商业化评估：钠离子电池用于电网储能", *_ZH[1:]]
    status = json.loads((child / "status.json").read_text(encoding="utf-8"))
    # The searches were reused; only the headings were asked for again.
    assert status["recovery"]["state"] == "reused" and status["recovery"]["reused_nodes"] == ["retrieval"]
    collection = json.loads((child / "validated_sources.json").read_text(encoding="utf-8"))
    assert collection["localized_headings"] == list(_ZH)
    # The child's own retrieval commit is the collection the crew was given.
    committed = json.loads((child / "checkpoints" / "retrieval" / "manifest.json").read_text(encoding="utf-8"))
    assert committed["output_sha256"] != saved["output_sha256"]
    payload, = (child / "checkpoints" / "retrieval").glob("output-*.json")
    assert json.loads(payload.read_text(encoding="utf-8"))["localized_headings"] == list(_ZH)


def test_a_resumed_run_that_can_reuse_agent_output_keeps_the_headings_it_was_written_under(tmp_path):
    """The headings are in every agent's checkpoint identity. Asking again
    here would throw away the paid work the resume exists to save; the
    report is shown under the table's headings instead."""
    from academic_agent.checkpoint_runtime import TASK_NODES
    from tests.test_checkpoint_worker import _FakeCrew, _run_worker

    parent_id, child_id = "20261118T090017Z-parentwithagents", "20261118T094559Z-childreusesthem"
    parent = _run_worker(tmp_path, parent_id, _untranslated_collection(), _FakeCrew())
    # What the production resume reused: everything but the scorer, the writer's report included.
    recorded = _recorded("resumed_run")
    reused = recorded["recovery"]["reused_nodes"]
    assert reused == ["retrieval", *TASK_NODES[:-1]] and "writer" in reused
    assert _recorded("failed_run")["checkpointing"]["committed_nodes"] == reused
    crew, child = _resume(tmp_path, parent, parent_id, child_id, keep=tuple(reused))

    assert crew.executed == [recorded["recovery"]["next_node"]] == ["scorer"]
    status = json.loads((child / "status.json").read_text(encoding="utf-8"))
    assert status["recovery"]["reused_nodes"] == reused
    # No auxiliary call, as the resumed run's record shows: none is needed, and none is made.
    assert recorded["auxiliary_usage"]["calls"] == []
    assert json.loads((child / "auxiliary_usage.json").read_text(encoding="utf-8"))["calls"] == []
    collection = json.loads((child / "validated_sources.json").read_text(encoding="utf-8"))
    assert collection["localized_headings"] == list(REPORT_HEADINGS)


def test_the_retry_is_made_only_for_untranslated_headings_of_a_resumed_run(tmp_path):
    from academic_agent.pipeline_worker import _retry_untranslated_headings

    empty = tmp_path / "parent"
    empty.mkdir()
    collection = _untranslated_collection()
    assert _retry_untranslated_headings(collection, None) is False            # not a resume
    assert collection.localized_headings == list(REPORT_HEADINGS)
    translated = _untranslated_collection()
    translated.localized_headings = ["# 学术商业化评估：", *_ZH[1:]]             # the model's own wording
    assert _retry_untranslated_headings(translated, empty) is False
    assert translated.localized_headings[0] == "# 学术商业化评估："
    english = _untranslated_collection()
    english.output_language = "English"
    english.localized_headings = []
    assert _retry_untranslated_headings(english, empty) is False and english.localized_headings == []
    # Nothing saved yet, as after a run that failed before retrieval ended.
    missing = _untranslated_collection()
    missing.localized_headings = []
    assert _retry_untranslated_headings(missing, empty) is True and missing.localized_headings == list(_ZH)
    # A language the table lacks: the model is asked again, and a second failure changes nothing.
    other = _untranslated_collection()
    other.output_language = "Vietnamese"
    with patch("academic_agent.language._llm_call", return_value="") as call:
        assert _retry_untranslated_headings(other, empty) is False
    call.assert_called_once()
    assert other.localized_headings == list(REPORT_HEADINGS)
    answer = "\n".join(f"{heading.split(' ', 1)[0]} tiêu đề {index}" for index, heading in enumerate(REPORT_HEADINGS))
    with patch("academic_agent.language._llm_call", return_value=answer):
        assert _retry_untranslated_headings(other, empty) is True
    assert other.localized_headings == answer.split("\n")


# ── The page ──────────────────────────────────────────────────────────────

_HARNESS = r"""
import fs from "node:fs";
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
class Node {
  constructor(tag) { Object.assign(this, { tagName: tag.toUpperCase(), children: [], dataset: {}, attributes: {},
    style: {}, className: "", textContent: "" }); }
  append(...items) { for (const item of items) this.children.push(typeof item === "string" ? { text: item } : item); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener() {}
}
globalThis.window = { addEventListener: () => {} };
globalThis.document = { createElement: (tag) => new Node(tag), createTextNode: (text) => ({ text }),
  querySelectorAll: () => [], documentElement: {} };
const mod = await import("./result.mjs");
const i18n = await import("./i18n.js");
const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = { cases: [] };
for (const item of input.cases) {
  i18n.setLanguage(item.ui ?? "English");
  const note = mod.renderHeadingsNote(item.markdown, item.language);
  out.cases.push({
    left: mod.headingsLeftEnglish(item.markdown, item.language),
    note: note && { tag: note.tagName, className: note.className, text: note.textContent, role: note.attributes.role },
  });
}
if (input.brief) {
  const data = mod.decisionBrief(input.brief);
  out.brief = data && { summary: data.summary, next: data.next };
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    work = tmp_path_factory.mktemp("result-page")
    source = _RESULT_JS.read_text(encoding="utf-8").replace('import * as api from "./api.js";', "const api = {};")
    (work / "result.mjs").write_text(source, encoding="utf-8")
    shutil.copy2(_I18N_JS, work / "i18n.js")
    (work / "harness.mjs").write_text(textwrap.dedent(_HARNESS), encoding="utf-8")

    def ask(**payload):
        (work / "input.json").write_text(json.dumps(payload), encoding="utf-8")
        result = subprocess.run([shutil.which("node"), str(work / "harness.mjs"), str(work / "input.json")],
                                capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=work)
        assert result.returncode == 0, result.stderr[:800]
        return json.loads(result.stdout)

    return ask


def test_the_pages_list_of_english_headings_is_the_seven_sections():
    source = _RESULT_JS.read_text(encoding="utf-8")
    block = re.search(r"const ENGLISH_SECTION_HEADINGS = new Set\(\[(.*?)\]\);", source, re.DOTALL)[1]
    assert tuple(re.findall(r'"([^"]+)"', block)) == _SECTIONS


def test_a_report_still_under_english_headings_says_so_in_one_line(page):
    """A language the table lacks, saved after a failed translation: the page
    cannot translate it, and until now it said nothing."""
    vietnamese = report_for_display(_english_headed("pin natri-ion"), "Vietnamese")
    chinese = report_for_display(_saved(), "Simplified Chinese")
    answers = page(cases=[
        {"markdown": vietnamese, "language": "Vietnamese"},
        {"markdown": vietnamese, "language": "Vietnamese", "ui": "Simplified Chinese"},
        {"markdown": chinese, "language": "Simplified Chinese"},            # shown under the table's
        {"markdown": _english_headed(), "language": "English"},              # English by design
        {"markdown": _english_headed(), "language": None},
        {"markdown": _english_headed(), "language": ""},
        {"markdown": "# T\n\n### Executive Summary\n\ntext ## Executive Summary\n", "language": "Vietnamese"},
        {"markdown": "# T\n\n## Evidence Limitations  \n", "language": "Vietnamese"},
        {"markdown": None, "language": "Vietnamese"},
    ])["cases"]
    assert [case["left"] for case in answers] == [True, True, False, False, False, False, False, True, False]
    english, chinese_ui = answers[0]["note"], answers[1]["note"]
    assert english == {"tag": "P", "className": "report-note", "role": "note",
                       "text": "The section headings of this report are in English: translating them into the "
                               "report's language did not succeed when the run started. The text under them is "
                               "not affected."}
    assert chinese_ui["text"] == "这份报告的章节标题是英文：运行开始时，把标题译成报告语言的那一步没有成功。标题下的正文不受影响。"
    assert [case["note"] for case in answers[2:7]] == [None] * 5 and answers[8]["note"] is None


def test_the_line_is_drawn_above_the_report_from_the_runs_language():
    source = _RESULT_JS.read_text(encoding="utf-8")
    drawn = source[source.index('} else if (id === "report") {'):source.index('} else if (id === "checks") {')]
    assert "const headingsNote = renderHeadingsNote(md, progress.output_language);" in drawn
    assert drawn.index("panel.append(headingsNote)") < drawn.index("panel.append(article)")
    assert "output_language" in main.RunProgress.model_fields
    strings = _I18N_JS.read_text(encoding="utf-8")
    assert strings.count("report_headings_english:") == 2
    css = (_ROOT / "web" / "static" / "css" / "result.css").read_text(encoding="utf-8")
    rule = css[css.index(".report-note {"):].split("}", 1)[0]
    assert "#" not in rule and "rgb" not in rule


def test_the_brief_still_reads_the_summary_and_the_first_step_of_the_displayed_report(page):
    """The brief finds its sections by their headings in the displayed text:
    it read "Executive Summary" before, and must read "执行摘要" now. It also
    passes over a sentence about the report itself, spelt either way."""
    shown = report_for_display(_saved())
    scores = {"overall_score": 55.0, "trl_score": 6, "mrl_score": 5, "patent_score": 3, "market_score": 3,
              "evidence_confidence": 3}
    brief = page(cases=[], brief={"scores": scores, "markdown": shown})["brief"]
    # A quoted line carries no citation mark. The excerpt's recommendations are
    # two sentences about the report's mode, which are passed over: no first step.
    assert brief["summary"] == ("方向性结论：在现有证据下，若进行后续评估，唯一优先方向是面向公用事业级电网储能的"
                                "系统集成与示范验证路线，尤其关注被动冷却、低运维和宽温域系统集成。")
    assert brief["next"] is None
    stepped = ("# Academic Commercialization Assessment: 钠离子电池\n\n## Executive Summary\n\n"
               "钠离子电池已进入示范阶段 [A1]。\n\n## 5. Commercialization Opportunities & Recommendations\n\n"
               "- **示范验证：** 先验证循环寿命 [A1]。\n\n## References\n\n"
               + report_display._LEGENDS["Simplified Chinese"] + "\n")
    brief = page(cases=[], brief={"scores": scores, "markdown": report_for_display(stepped)})["brief"]
    assert brief == {"summary": "钠离子电池已进入示范阶段。", "next": "示范验证： 先验证循环寿命。"}
    english = ("# Report\n\n## Executive Summary\n\nActor-specific GO/NO_GO is not assessed for this brief. "
               "Sodium-ion cells reached grid pilots in 2025 [A1].\n\n"
               "## 5. Commercialization Opportunities & Recommendations\n\n"
               "**GO/NO_GO Status:** Not assessed.\n\n- **Pilot:** Run a 12-month cycling pilot first [A1].\n")
    spelt = report_for_display(english)
    assert "Actor-specific GO / NO-GO is not assessed" in spelt and "**GO / NO-GO Status:**" in spelt
    brief = page(cases=[], brief={"scores": scores, "markdown": spelt})["brief"]
    assert brief["summary"] == "Sodium-ion cells reached grid pilots in 2025."
    assert brief["next"] == "Pilot: Run a 12-month cycling pilot first."


def test_the_python_helpers_stay_importable_without_the_environment():
    """The display module is read for every report a page shows: it must not
    pull in CrewAI or read the environment at import."""
    code = ("import sys, os\n"
            "class Refuse(dict):\n"
            "    def __getitem__(self, key): raise AssertionError(key)\n"
            "    def get(self, key, default=None): raise AssertionError(key)\n"
            "import academic_agent.report_display as shown\n"
            "assert 'crewai' not in sys.modules and 'academic_agent.evidence' not in sys.modules\n"
            "print(len(shown.HEADING_TRANSLATIONS))\n")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                            cwd=_ROOT, env={**__import__("os").environ, "PYTHONPATH": str(_ROOT / "src")})
    assert result.returncode == 0, result.stderr[-600:]
    assert result.stdout.strip() == "12"
