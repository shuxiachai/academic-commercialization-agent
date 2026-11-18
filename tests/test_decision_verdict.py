"""The conclusion a decision-support report states reaches its reader.

On 2026-11-18 a run asked "should the technology transfer office license
this?", its scope line promised a GO/NO-GO, and the report answered in the
last paragraph of its executive summary: "the actor-specific conclusion is
DEFER because ...". The brief, the comparison and the PDF never showed it.

Three things are held here:

- the rule that finds the statement (decision_verdict.find_verdict): what it
  takes for a conclusion, and the far longer list of what it must not;
- the seam: every field the rule returns reaches GET /api/runs/{id}/decision,
  only for a run that was asked and finished, and the PDF carries the card;
- the words: the PDF's copy and the page's say the same thing.

The rule's negatives are the lines that 1,797 saved reports actually contain
(none of them a conclusion), so a rule that starts reading them fails here
before it reaches a reader.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from academic_agent import decision_verdict
from academic_agent.decision_verdict import card_text, find_verdict
from academic_agent.report_applicability import add_applicability_block
from academic_agent.report_display import display_parts, report_for_display
from academic_agent.run_spec import DecisionContext, RunSpec
from api import main, runs
from ui import pdf_export

_ROOT = Path(__file__).resolve().parents[1]
_STRINGS = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")

# The sentence of the production run, as its report wrote it.
_DEFER = ("In sum, the actor-specific conclusion is DEFER because module-scale validation, "
          "reliability evidence, and patent/legal clarity remain insufficient [A2][P1].")


def _report(*paragraphs: str, section: str = "Executive Summary") -> str:
    return f"# Report\n\n## {section}\n\n" + "\n\n".join(paragraphs) + "\n"


def _one(sentence: str) -> dict:
    return find_verdict(_report(sentence))


# ── What is a conclusion ──────────────────────────────────────────────────

@pytest.mark.parametrize(("verdict", "sentence"), [
    ("defer", _DEFER),
    ("defer", "**Decision:** DEFER. Revisit after module data [A2]."),
    ("defer", "**GO/NO_GO Status:** DEFER"),
    ("defer", "**Decision:** Defer."),
    ("defer", "**Decision:** Defer until module-scale data are available [A2]."),
    ("no_go", "**Decision:** NO_GO unless freedom to operate is confirmed [P1]."),
    ("defer", "Recommendation: DEFER, and revisit when module data exist [A2]."),
    ("defer", "**DEFER.** Module-scale validation is not yet in the evidence [A1]."),
    ("defer", "- **Conclusion for the technology transfer office:** DEFER until reliability data exist."),
    ("defer", "This report concludes DEFER for the licensing decision."),
    ("defer", "The actor-specific GO/NO_GO conclusion is DEFER."),
    ("defer", "Accordingly, the evidence-conditioned verdict for the committee is a clear DEFER."),
    ("no_go", "We recommend a NO_GO on licensing at this stage [M1]."),
    ("no_go", "The recommendation is NO-GO."),
    ("no_go", "**NO_GO** — the patent position cannot be cleared [P3]."),
    ("go", "The decision is GO, bounded by the evidence [A1]."),
    ("go", "**Recommendation:** GO."),
    ("conditional_go", "The conclusion is a CONDITIONAL GO: license only if freedom to operate is confirmed [P1]."),
    ("conditional_go", "Recommendation: GO, subject to an independent durability test [A3]."),
    ("conditional_go", "The recommendation is a conditional GO."),
    ("defer", "结论：DEFER（暂缓）。组件级验证证据不足 [A1]。"),
    ("defer", "针对技术转移办公室的决策结论为暂缓许可，原因是可靠性证据不足 [A2]。"),
    ("conditional_go", "决策结论：有条件通过，前提是完成自由实施分析 [P1]。"),
    ("no_go", "结论为 NO_GO。"),
])
def test_a_sentence_that_ties_a_verdict_word_to_the_conclusion_states_it(verdict, sentence):
    found = _one(sentence)
    assert (found["status"], found["verdict"]) == ("stated", verdict), found


def test_a_sub_heading_states_it_as_well_as_a_paragraph():
    found = find_verdict("## 5. Recommendations\n\n### Decision: DEFER\n\nModule data are missing [A1].\n")
    assert (found["status"], found["verdict"], found["section"]) == ("stated", "defer", "5. Recommendations")


# ── What is not ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("sentence", [
    # The mode, said as the writer's contract has every other report say it.
    "Actor-specific GO/NO_GO is not assessed.",
    "**GO/NO_GO Status:** Not assessed.",
    "As this is an orientation assessment, no GO/NO_GO decision is rendered.",
    "It is not a GO, NO_GO or DEFER conclusion, and no recommendation is made for any specific actor.",
    "未评估针对具体决策者的 GO/NO_GO。",
    "由于处于导向模式，**不给出 GO/NO_GO 结论**。",
    "- **GO/NO_GO**：未评估。",
    # What may be concluded is not what was.
    "A GO, NO_GO, or DEFER conclusion is permitted, but every gate must be bounded by evidence.",
    "Decision support: the context given allows a GO/NO_GO for this decision-maker; the cited evidence still governs it.",
    # Graphene oxide and a product's name, from the saved reports.
    "GO's 35.53% forecast CAGR [M7] suggests near-term adoption.",
    "Monitor graphene oxide (GO) high-growth trajectory.",
    "We recommend GO inks for printed sensors [A2].",
    "The recommendation is GO films over CVD graphene.",
    "The conclusion is that GO-based inks are closer to market than CVD films.",
    "**GO**: graphene oxide.",
    "The decision was to launch the Carbyon GO machine in 2025 [M2].",
    # Criteria and conditionals name a verdict without reaching one.
    "Direct R&D funding with clear go/no-go criteria at 18-month intervals.",
    "Stop criterion (analyst proposal): NO_GO if certified efficiency stays below 28% [A4].",
    "The decision would be GO if the pilot passes its durability gate.",
    "A decision on whether to GO cannot be made from this report.",
    "The committee will conclude whether to DEFER after the pilot.",
    # A gate of the action plan every report is asked for: the word with its trigger.
    "**Gate 2 decision:** NO_GO if outdoor loss exceeds 3% a year [A2].",
    "The decision is DEFER if the second-year data are not delivered by the licensee.",
    "- Gate 1 decision: GO when certified module efficiency reaches 28% [A1].",
    "**Decision:** NO_GO, should the freedom-to-operate opinion be adverse [P1].",
    "The conclusion is not GO.",
    "若18个月内未获得付费合同，则可能需暂缓商业化进程。",
    # The three that only one guard each stands against (found by putting the defects back).
    "The decision is GO, NO_GO, or DEFER for the committee to make.",
    "**Conclusion:** a DEFER is not given for an unspecified actor.",
    "No conclusion is DEFER-able here.",
    "The conclusion is that a NO_GO would be premature at this stage.",
    "**Recommendation:** defer to the registry record for legal status [P1].",
    # The word far from the tie belongs to another clause.
    "The decision is the committee's to take once the second year of outdoor data has been reviewed "
    "by the licensing team; a DEFER today costs nothing.",
    # The words in lower case are ordinary English.
    "Recommendation: Go to market through an OEM licence [M2].",
    "We recommend that the office defer to the registry record for legal status.",
    "The decision owner is the technology transfer office.",
    # An argument for waiting that never says the word is not read as one.
    "The evidence does not yet support licensing; the office should wait for module data [A2].",
])
def test_a_verdict_word_anywhere_else_is_not_a_conclusion(sentence):
    found = _one(sentence)
    assert found["status"] == "not_stated", found
    assert found["verdict"] is None and found["statement"] is None and found["statements"] == []


def test_the_code_owned_applicability_paragraph_is_never_read_as_the_conclusion():
    """It says a GO/NO_GO is permitted. A model that copies the marker and
    writes its own "GO is approved" under it (the smoke fixture does exactly
    this) still states nothing: the reserved paragraph is taken out whole."""
    gate = DecisionContext(asset_description="a", target_application="b", decision_owner="c",
                           decision_type="d").gate_snapshot()
    delivered = add_applicability_block("# R\n\n## Executive Summary\n\nEarly stage [A1].\n",
                                        decision_gate=gate, output_language="English")
    assert "permitted" in delivered
    assert find_verdict(delivered)["status"] == "not_stated"
    assert find_verdict(report_for_display(delivered))["status"] == "not_stated"
    copied = ("# R\n\n<!-- decision-applicability:v1 -->\n\n> **Assessment applicability (code-derived):** "
              "Mode `decision_support`. The conclusion is GO.\n\nBody [A1].\n")
    assert find_verdict(copied)["status"] == "not_stated"


@pytest.mark.parametrize("section", ["References", "参考文献", "Reviewer Notes", "自动校对记录"])
def test_reference_titles_and_proofreading_notes_are_not_the_report_speaking(section):
    report = _report("Early stage [A1].") + f"\n## {section}\n\n- Applied: the conclusion is DEFER.\n"
    assert find_verdict(report)["status"] == "not_stated"


def test_a_fenced_example_is_not_the_report_speaking():
    report = _report("Early stage [A1].", "```\nDecision: DEFER\n```")
    assert find_verdict(report)["status"] == "not_stated"


# ── What is returned with it ──────────────────────────────────────────────

def test_the_statement_comes_with_its_section_what_follows_it_and_a_way_to_find_it():
    report = _report(
        "Tandem cells exceed 33.9% certified efficiency, e.g. in the laboratory [A1].",
        f"Bankability is open [M1]. {_DEFER} Licensing should be revisited once outdoor module data "
        "of at least one year exist [A3]. A second route is a field-limited option [P2]. A fourth sentence.",
    ) + "\n## 5. Commercialization Opportunities & Recommendations\n\nNext steps [A1].\n"
    found = find_verdict(report)
    assert found["status"] == "stated" and found["verdict"] == "defer"
    assert found["statement"] == _DEFER
    assert found["section"] == "Executive Summary"
    # Two sentences, in the paragraph's order, and no more.
    assert found["follows"] == [
        "Licensing should be revisited once outdoor module data of at least one year exist [A3].",
        "A second route is a field-limited option [P2].",
    ]
    # No citation in it and no emphasis mark: it is matched against drawn text.
    assert found["needle"] and found["needle"] in _DEFER and "[" not in found["needle"]
    assert len(found["needle"]) <= 80
    # The longest stretch between citations, wherever in the statement it stands.
    early = find_verdict(_report("Per the durability study [A2], the conclusion is DEFER because module data are missing."))
    assert early["needle"] == ", the conclusion is DEFER because module data are missing."
    assert [item["verdict"] for item in found["statements"]] == ["defer"]


def test_emphasis_is_dropped_and_a_decimal_or_an_abbreviation_does_not_end_the_statement():
    found = _one("The **conclusion** is `DEFER` because efficiency fell 2.5% in the U.S. trial, "
                 "i.e. below the 28.0% gate [A4]. Next sentence.")
    assert found["statement"] == ("The conclusion is DEFER because efficiency fell 2.5% in the U.S. trial, "
                                  "i.e. below the 28.0% gate [A4].")
    assert found["follows"] == ["Next sentence."]


def test_a_conclusion_repeated_is_one_conclusion_and_the_first_place_is_shown():
    report = _report(_DEFER) + "\n## 5. Recommendations\n\n**Decision:** DEFER.\n"
    found = find_verdict(report)
    assert (found["status"], found["verdict"], found["section"]) == ("stated", "defer", "Executive Summary")
    assert [item["section"] for item in found["statements"]] == ["Executive Summary", "5. Recommendations"]


def test_statements_that_disagree_are_reported_as_disagreeing_and_none_is_chosen():
    report = _report(_DEFER) + "\n## 5. Recommendations\n\n**Decision:** GO, subject to a durability test [A3].\n"
    found = find_verdict(report)
    assert found["status"] == "conflicting"
    assert found["verdict"] is None and found["statement"] is None and found["needle"] is None
    assert [(item["verdict"], item["section"]) for item in found["statements"]] == [
        ("defer", "Executive Summary"), ("conditional_go", "5. Recommendations")]


def test_the_gates_of_the_action_plan_do_not_disagree_with_the_conclusion():
    """The contract asks for a gated plan with pass thresholds and stop
    criteria beside the conclusion. Read as conclusions, its gates would turn
    the one DEFER into "the report states conclusions that disagree"."""
    report = _report(_DEFER) + (
        "\n## 5. Commercialization Opportunities & Recommendations\n\n"
        "**Gated action plan (analyst proposals requiring owner confirmation):**\n\n"
        "1. Gate 1 decision: GO if a second year of outdoor data shows less than 3% loss [A2].\n"
        "2. **Gate 2 decision:** NO_GO if the freedom-to-operate opinion is adverse [P1].\n"
        "3. Stop criterion: NO_GO when certified module efficiency stays below 28% [A1].\n\n"
        # A table's cells are not prose: a row is never read as a sentence.
        "| Gate | Decision |\n|---|---|\n| 3 | The decision is GO for the pilot line |\n"
    )
    found = find_verdict(report)
    assert (found["status"], found["verdict"]) == ("stated", "defer")
    assert [item["section"] for item in found["statements"]] == ["Executive Summary"]


def test_windows_line_endings_and_an_empty_report_read_the_same():
    assert find_verdict(_report(_DEFER).replace("\n", "\r\n"))["verdict"] == "defer"
    for empty in ("", None):
        assert find_verdict(empty)["status"] == "not_stated"


# ── The seam: the page and the PDF get what the rule found ────────────────

_CONTEXT = DecisionContext(
    asset_description="Two-terminal tandem cell results", target_application="Utility-scale modules",
    decision_owner="Technology transfer office", decision_type="License the technology",
)


@pytest.fixture
def run(monkeypatch, tmp_path):
    """A finished run on disk, in decision-support mode unless told otherwise."""
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    runs._registry.clear()

    def make(report=None, *, context=_CONTEXT, done=True, spec=True, run_id="20261118T083403Z-e434f298d40b", language="English"):
        directory = tmp_path / run_id
        directory.mkdir()
        gate = (context or DecisionContext()).gate_snapshot()
        status = {"stage": "Done" if done else "Agent 5", "done": done, "topic": "tandem cells",
                  "output_language": language, "decision_gate": gate}
        if not done:
            status["error"] = "The reviewer did not answer."
        (directory / "status.json").write_text(json.dumps(status), encoding="utf-8")
        if spec:
            RunSpec(topic="tandem cells", decision_context=context).save(directory)
        if report is not None:
            delivered = add_applicability_block(report, decision_gate=gate, output_language=language)
            (directory / "commercialization_report.md").write_text(delivered, encoding="utf-8")
        return run_id, directory

    yield make
    runs._registry.clear()


def test_every_field_the_rule_returns_reaches_the_endpoint(run):
    """response_model drops what it does not declare, silently: a field added
    to find_verdict would be computed, tested here below, and never arrive."""
    report = _report(f"{_DEFER} Revisit after module data [A3].")
    run_id, directory = run(report)
    body = TestClient(main.app).get(f"/api/runs/{run_id}/decision").json()
    assert body["run_id"] == run_id and body["asked"] is True
    assert body["question"] == {"decision_owner": "Technology transfer office",
                                "decision_type": "License the technology"}
    expected = find_verdict((directory / "commercialization_report.md").read_text(encoding="utf-8"))
    assert expected["status"] == "stated"
    assert body["conclusion"] == expected
    assert set(body["conclusion"]) == set(expected)
    for sent, found in zip(body["conclusion"]["statements"], expected["statements"], strict=True):
        assert set(sent) == set(found)

    conflicting = find_verdict(_report(_DEFER, "**Decision:** GO."))
    declared = set(main.RunDecision.model_fields["conclusion"].annotation.__args__[0].model_fields)
    assert set(conflicting) == declared == set(find_verdict(""))


def test_a_report_with_no_stated_conclusion_says_so_and_is_not_left_empty(run):
    run_id, _ = run(_report("The office should wait for module data [A2]."))
    body = TestClient(main.app).get(f"/api/runs/{run_id}/decision").json()
    assert body["asked"] is True
    assert body["conclusion"]["status"] == "not_stated"
    assert body["conclusion"]["verdict"] is None and body["conclusion"]["statements"] == []


@pytest.mark.parametrize("context", [
    None,
    DecisionContext(asset_description="only the asset"),
])
def test_a_run_that_was_not_asked_gets_no_conclusion_whatever_its_report_says(run, context):
    """Orientation and incomplete-context reports are told to give none. One
    that says "DEFER" anyway is not promoted by this endpoint."""
    run_id, _ = run(_report(_DEFER), context=context)
    body = TestClient(main.app).get(f"/api/runs/{run_id}/decision").json()
    assert body == {"run_id": run_id, "asked": False, "question": None, "conclusion": None}


@pytest.mark.parametrize("gate", [
    {"mode": "decision_support", "go_no_go_allowed": False},
    {"mode": "orientation", "go_no_go_allowed": True},
    {"mode": "decision_support"},
])
def test_the_label_and_the_permission_are_both_needed(run, gate):
    """A support label without the permission is not upgraded, and a
    permission the mode does not carry is not honoured: the page's scope line
    reads a gate the same way (renderDecisionApplicability)."""
    run_id, directory = run(_report(_DEFER))
    status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
    status["decision_gate"] = gate
    (directory / "status.json").write_text(json.dumps(status), encoding="utf-8")
    body = TestClient(main.app).get(f"/api/runs/{run_id}/decision").json()
    assert body["asked"] is False and body["conclusion"] is None and body["question"] is None


def test_a_run_that_did_not_finish_gets_none_from_its_unreviewed_report(run):
    run_id, _ = run(_report(_DEFER), done=False)
    body = TestClient(main.app).get(f"/api/runs/{run_id}/decision").json()
    assert body["asked"] is False and body["conclusion"] is None


def test_an_unreadable_request_costs_the_question_and_not_the_conclusion(run):
    run_id, directory = run(_report(_DEFER), spec=False)
    assert TestClient(main.app).get(f"/api/runs/{run_id}/decision").json()["question"] is None
    (directory / ".run-spec.json").write_text("{not json", encoding="utf-8")
    body = TestClient(main.app).get(f"/api/runs/{run_id}/decision").json()
    assert body["question"] is None and body["conclusion"]["verdict"] == "defer"


def test_the_route_is_its_own_and_answers_like_the_report_it_reads(run):
    client = TestClient(main.app)
    assert client.get("/api/runs/20260101T000000Z-deadbeef/decision").status_code == 404
    run_id, _ = run(None)
    assert client.get(f"/api/runs/{run_id}/decision").status_code == 409
    # Not the artifact route's "Unknown artifact 'decision'".
    paths = [route.path for route in main.app.routes]
    assert paths.index("/api/runs/{run_id}/decision") < paths.index("/api/runs/{run_id}/{artifact}")


# ── The PDF ───────────────────────────────────────────────────────────────

def _pdf_text(path: Path) -> str:
    import fitz  # PyMuPDF, already a dependency of the uploads path

    with fitz.open(path) as document:
        return re.sub(r"\s+", " ", " ".join(page.get_text() for page in document))


def test_the_pdf_of_a_decision_support_run_opens_with_the_same_card(run):
    run_id, directory = run(_report(f"{_DEFER} Revisit after module data [A3]."))
    response = TestClient(main.app).get(f"/api/runs/{run_id}/report.pdf")
    assert response.status_code == 200
    pdf = directory / "commercialization_report.pdf"
    assert pdf_export.pdf_carries_decision_card(pdf)
    text = _pdf_text(pdf)
    card_at = text.index("Decision conclusion")
    # Under the scope paragraph, above the report's first section.
    assert text.index("Scope of this assessment") < card_at < text.index("Executive Summary")
    card = text[card_at:text.index("Executive Summary")]
    assert "Decision owner: Technology transfer office" in card
    assert "Decision to make: License the technology" in card
    assert "DEFER" in card and "the actor-specific conclusion is DEFER because" in card
    assert "Revisit after module data" in card


def test_the_pdf_says_when_the_report_states_no_conclusion(run):
    run_id, directory = run(_report("The office should wait for module data [A2]."))
    assert TestClient(main.app).get(f"/api/runs/{run_id}/report.pdf").status_code == 200
    text = _pdf_text(directory / "commercialization_report.pdf")
    assert "The report states no clear conclusion" in text
    assert "infers nothing" in text


def test_a_pdf_cached_before_the_card_existed_is_built_once_more_and_then_kept(run):
    """pdf_cache_complete alone called the old file good, so the run whose
    reader went looking for the conclusion would have kept a PDF without it."""
    run_id, directory = run(_report(_DEFER))
    old = pdf_export._generate_pdf(_report(_DEFER), directory)
    assert pdf_export.pdf_cache_complete(old) and not pdf_export.pdf_carries_decision_card(old)
    client = TestClient(main.app)
    assert client.get(f"/api/runs/{run_id}/report.pdf").status_code == 200
    assert pdf_export.pdf_carries_decision_card(old)
    built = old.read_bytes()
    from unittest.mock import patch

    with patch.object(pdf_export, "_generate_pdf", wraps=pdf_export._generate_pdf) as render:
        assert client.get(f"/api/runs/{run_id}/report.pdf").content == built
    render.assert_not_called()


def test_a_run_that_was_not_asked_keeps_the_pdf_it_always_had(run):
    run_id, directory = run(_report(_DEFER), context=None)
    assert TestClient(main.app).get(f"/api/runs/{run_id}/report.pdf").status_code == 200
    pdf = directory / "commercialization_report.pdf"
    assert not pdf_export.pdf_carries_decision_card(pdf)
    assert "Decision conclusion" not in _pdf_text(pdf)


def test_the_card_is_cut_in_where_the_displayed_report_is_whole():
    """display_parts splits what report_for_display returns and changes nothing in it."""
    gate = _CONTEXT.gate_snapshot()
    for language, body in (("English", _report(_DEFER)), ("Simplified Chinese", "# 报告\n\n## 执行摘要\n\n正文 [A1]。\n")):
        delivered = add_applicability_block(body, decision_gate=gate, output_language=language)
        head, rest = display_parts(delivered)
        assert head + rest == report_for_display(delivered)
        assert head.rstrip().endswith(("proposals.", "建议。")) and rest.lstrip().startswith("## ")
    # No delivered paragraph: after the title, or nothing.
    assert display_parts("# Title\n\nBody.\n") == ("# Title\n", "\nBody.\n")
    assert display_parts("Body only.\n") == ("", "Body only.\n")
    for legacy in ("# T\n## References\n\n*x*\n", ""):
        head, rest = display_parts(legacy)
        assert head + rest == report_for_display(legacy)


def test_a_chinese_report_gets_the_card_in_chinese_and_other_languages_in_english():
    stated = find_verdict(_report(_DEFER))
    question = {"decision_owner": "技术转移办公室", "decision_type": "是否许可这项技术"}
    zh = card_text(question, stated, "Simplified Chinese")
    assert zh["title"] == "决策结论" and zh["headline"] == "暂缓" and zh["tone"] == "defer"
    assert zh["asked"] == ["决策负责人：技术转移办公室", "待作决策：是否许可这项技术"]
    assert zh["where"] == "出自报告“Executive Summary”一节。"
    assert card_text(None, stated, "Japanese")["title"] == "Decision conclusion"
    assert card_text(None, stated, "English")["asked"] == []
    # Chinese sentences follow one another without a space; English ones with one.
    chinese = find_verdict(_report("决策结论为暂缓许可，证据不足 [A2]。待取得户外数据后重新评估 [A3]。"))
    assert card_text(question, chinese, "Simplified Chinese")["quotes"] == [
        ("报告原文：", "决策结论为暂缓许可，证据不足 [A2]。待取得户外数据后重新评估 [A3]。")]
    english = find_verdict(_report(f"{_DEFER} Revisit after module data [A3]."))
    assert card_text(None, english, "English")["quotes"] == [("The report says:", f"{_DEFER} Revisit after module data [A3].")]
    none = card_text(question, find_verdict(""), "Simplified Chinese")
    assert none["headline"] == "报告没有给出明确结论" and none["quotes"] == [] and none["where"] is None
    both = card_text(None, find_verdict(_report(_DEFER, "**Decision:** GO.")), "English")
    assert both["tone"] == "conflicting"
    assert [lead for lead, _ in both["quotes"]] == ["DEFER, in “Executive Summary”:", "GO, in “Executive Summary”:"]


# ── The words ─────────────────────────────────────────────────────────────

_SHARED = {  # the PDF's key -> the page's
    "title": "verdict_title", "owner": "verdict_owner", "decision": "verdict_decision",
    "go": "verdict_go", "conditional_go": "verdict_conditional_go", "defer": "verdict_defer",
    "no_go": "verdict_no_go", "says": "verdict_says", "where": "verdict_where",
    "not_stated": "verdict_not_stated", "not_stated_detail": "verdict_not_stated_detail",
    "conflicting": "verdict_conflicting", "conflicting_detail": "verdict_conflicting_detail",
    "in_section": "verdict_in_section", "note": "verdict_note",
}


def test_the_pdf_and_the_page_say_the_card_in_the_same_words():
    """Two copies, because the PDF is in the report's language and the page in
    the reader's. A sentence changed in one and not the other fails here."""
    assert set(_SHARED) == set(decision_verdict._CARD_COPY["English"]) == set(decision_verdict._CARD_COPY["Simplified Chinese"])
    for key, page_key in _SHARED.items():
        said = re.findall(rf'^    {page_key}: (".*"),$', _STRINGS, re.MULTILINE)
        assert len(said) == 2, page_key
        english, chinese = (json.loads(text) for text in said)
        assert decision_verdict._CARD_COPY["English"][key] == english, key
        assert decision_verdict._CARD_COPY["Simplified Chinese"][key] == chinese, key


def test_every_string_the_card_and_the_comparison_rows_use_exists_in_both_languages():
    result = (_ROOT / "web" / "static" / "js" / "result.js").read_text(encoding="utf-8")
    compare = (_ROOT / "web" / "static" / "js" / "compare.js").read_text(encoding="utf-8")
    keys = set(re.findall(r'"((?:verdict|compare_context|compare_verdict)_[a-z_]+)"', result + compare))
    keys |= {f"verdict_{code}" for code in decision_verdict.VERDICTS}
    assert {"verdict_title", "verdict_unread", "compare_context_orientation", "compare_verdict_not_asked"} <= keys
    for key in sorted(keys):
        assert _STRINGS.count(f"    {key}: ") == 2, key


def test_the_audit_counts_modes_lines_and_what_the_rule_finds(tmp_path, capsys):
    """scripts/audits/decision_conclusion_audit.py is what the result document's
    figures come from; it reads the same function the page does."""
    from scripts.audits import decision_conclusion_audit as audit

    def saved(name, text, gate=None):
        directory = tmp_path / "batch" / name
        directory.mkdir(parents=True)
        (directory / "commercialization_report.md").write_text(text, encoding="utf-8")
        if gate is not None:
            (directory / "status.json").write_text(json.dumps({"decision_gate": gate}), encoding="utf-8")

    saved("orientation", _report("Actor-specific GO/NO_GO is not assessed.", "GO's forecast CAGR is high [M7]."),
          DecisionContext().gate_snapshot())
    saved("cli", _report("**GO/NO_GO Statement:**", "由于处于导向模式，不给出 GO/NO_GO 结论。"))
    saved("asked", _report(_DEFER), _CONTEXT.gate_snapshot())
    found = audit.audit(tmp_path)
    assert found["reports"] == 3
    assert found["modes"] == {"orientation": 1, "not recorded": 1, "decision_support": 1}
    assert found["lines"] == 5
    assert found["kinds"] == {"none assessed": 2, "a name": 1, "other": 2}
    assert [line for _, line in found["rest"]] == [_DEFER, "**GO/NO_GO Statement:**"]  # runs in name order
    assert found["rule"] == {"not_stated": 2, "stated": 1}
    assert [(item["mode"], item["verdict"]) for item in found["statements"]] == [("decision_support", "defer")]
    assert audit.main([str(tmp_path), "--lines"]) == 0
    printed = capsys.readouterr().out
    assert "3 reports" in printed and "5 lines use GO, NO_GO or DEFER" in printed
    assert "FOUND in a decision_support report" in printed


def test_the_scores_and_the_applicability_rule_are_not_touched_by_reading_the_conclusion():
    source = (_ROOT / "src" / "academic_agent" / "decision_verdict.py").read_text(encoding="utf-8")
    imports = re.findall(r"^(?:from|import) (\S+)", source, re.MULTILINE)
    assert sorted(imports) == ["__future__", "academic_agent.report_applicability", "re", "typing"]
    assert "os.environ" not in source and "open(" not in source
