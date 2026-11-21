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
from api import main, runs, samples
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
    # Two ties in one sentence, and the first leads nowhere.
    ("defer", "In decision-support mode the preferred route is a field-limited licence; however, the "
              "actor-specific conclusion is DEFER because module-scale evidence is missing [A2]."),
    ("no_go", "We recommend a field trial for the sensor line and conclude NO_GO for the licensing decision [M1]."),
    ("defer", "建议优先考虑技术许可路线，但针对该决策的结论是暂缓，原因是证据不足 [A2]。"),
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


def test_a_conclusion_repeated_is_one_conclusion_and_its_own_line_is_the_one_quoted():
    """The shape of the one production report read for this, in other words:
    DEFER in passing at the end of a summary sentence about the route, then a
    labelled line in the recommendations with the reasons and what would
    reopen the decision. The card quotes the second, where a reader finds why
    and under what condition."""
    report = _report(
        "Tandem cells are efficient in the laboratory [A1].",
        "In decision-support mode the preferred route is a field-limited licence to a module maker; however, "
        "the actor-specific conclusion is DEFER because module-scale evidence is missing [A2][P1].",
    ) + ("\n## 5. Recommendations\n\n- **Gate 1 — module transfer:** obtain module-level evidence [A2].\n\n"
         "**Conclusion: DEFER.** The office should defer a full licence until module transfer and legal diligence "
         "are evidenced [A2][P1, P2]. If the gates above are met within the decision window, the office may "
         "revisit a field-limited licence [M2]. A third sentence.\n")
    found = find_verdict(report)
    assert (found["status"], found["verdict"]) == ("stated", "defer")
    assert (found["statement"], found["section"]) == ("Conclusion: DEFER.", "5. Recommendations")
    assert found["follows"] == [
        "The office should defer a full licence until module transfer and legal diligence are evidenced [A2][P1, P2].",
        "If the gates above are met within the decision window, the office may revisit a field-limited licence [M2].",
    ]
    assert found["needle"] == "Conclusion: DEFER."
    # Every place is still listed, in the report's order.
    assert [item["section"] for item in found["statements"]] == ["Executive Summary", "5. Recommendations"]
    # With no line of its own, the first place it is said.
    twice = find_verdict(_report(_DEFER) + "\n## 5. Recommendations\n\nWe recommend DEFER for now [A2].\n")
    assert (twice["section"], twice["statement"]) == ("Executive Summary", _DEFER)
    # The word alone at the head of a paragraph is such a line too.
    headed = find_verdict(_report(_DEFER) + "\n## 5. Recommendations\n\n**DEFER.** Module data are missing [A2].\n")
    assert (headed["section"], headed["statement"]) == ("5. Recommendations", "DEFER.")


_ALONE = "**Conclusion:** **DEFER**"
_REASONS = ("**Evidence conditions behind the conclusion:** Module-scale stability data are missing [A2]. "
            "No freedom-to-operate opinion has been obtained [P1]. A third sentence [M1].")


def _recommendations(*paragraphs: str) -> str:
    return _report("Tandem cells are efficient in the laboratory [A1].") + (
        "\n## 6. Recommendations\n\n" + "\n\n".join(paragraphs) + "\n")


def test_a_conclusion_alone_in_its_paragraph_takes_its_reasons_from_the_next_one():
    """Production run 20261120T131247Z-55c7… (2026-11-20) wrote the conclusion
    as a paragraph of its own and its reasons in the next. The rule took
    follows from the statement's own paragraph only, and the card, the
    comparison and the PDF said "The report says: Conclusion: DEFER"."""
    found = find_verdict(_recommendations(_ALONE, _REASONS))
    assert (found["status"], found["verdict"], found["statement"]) == ("stated", "defer", "Conclusion: DEFER")
    assert found["follows"] == [
        "Evidence conditions behind the conclusion: Module-scale stability data are missing [A2].",
        "No freedom-to-operate opinion has been obtained [P1].",
    ]
    assert found["bare"] is True
    # The paragraph is still found by the conclusion's own line.
    assert found["needle"] == "Conclusion: DEFER"
    # The card quotes both, the line with no stop broken from what follows it.
    card = card_text(None, found, "English")
    assert card["quotes"] == [("The report says:", "Conclusion: DEFER\nEvidence conditions behind the conclusion: "
                               "Module-scale stability data are missing [A2]. No freedom-to-operate opinion has been "
                               "obtained [P1].")]
    # With its stop, joined by a space as every other passage is.
    stopped = card_text(None, find_verdict(_recommendations("**Conclusion: DEFER.**", _REASONS)), "English")
    assert stopped["quotes"][0][1].startswith("Conclusion: DEFER. Evidence conditions behind the conclusion:")
    # A citation after the stop is not the end of the line; one before it is no stop.
    assert decision_verdict.joined(["Conclusion: DEFER. [A2]", "Next."]) == "Conclusion: DEFER. [A2] Next."
    assert decision_verdict.joined(["Conclusion: DEFER [A2]", "Next."]) == "Conclusion: DEFER [A2]\nNext."
    assert decision_verdict.joined(["结论：暂缓", "原因如下。"]) == "结论：暂缓\n原因如下。"


@pytest.mark.parametrize(("between", "after"), [
    # The next paragraph is in another section, read or skipped.
    ("", "## 7. Next steps\n\n" + _REASONS),
    ("", "## 7. Evidence Limitations\n\n" + _REASONS),
    # A paragraph with no word in it.
    ("", "— —"),
    # A sub-heading, a table, a fenced block or a rule stands between.
    ("### Next steps", _REASONS),
    ("| Gate | Owner |\n|---|---|\n| 1 | TTO |", _REASONS),
    ("```\nnote\n```", _REASONS),
    ("---", _REASONS),
    # What comes next is not a paragraph: a list, a quote, a bold label alone.
    ("", "- Module-scale stability data are missing [A2].\n- No opinion has been obtained [P1]."),
    ("", "> Module-scale stability data are missing [A2]."),
    ("", "**Stop criteria:**"),
    ("", "**Next steps.**"),
    ("", "* * *"),
])
def test_nothing_is_taken_past_a_boundary_or_from_what_is_not_the_next_paragraph(between, after):
    report = _recommendations(_ALONE, *([between] if between else []), after)
    found = find_verdict(report)
    assert (found["status"], found["statement"]) == ("stated", "Conclusion: DEFER")
    assert found["follows"] == []


def test_only_a_conclusion_that_is_its_whole_paragraph_reads_the_next_one():
    # Its own paragraph goes on: the sentences beside it, not the next paragraph.
    beside = find_verdict(_recommendations("**Conclusion: DEFER.** The office should wait [A2].", _REASONS))
    assert beside["follows"] == ["The office should wait [A2]."]
    assert beside["bare"] is True
    # A list item, a quoted line or a sub-heading is not a paragraph of its own.
    for alone in ("- **Conclusion:** DEFER", "> **Conclusion:** DEFER", "### Conclusion: DEFER"):
        found = find_verdict(_recommendations(alone, _REASONS))
        assert (found["verdict"], found["follows"]) == ("defer", []), alone
    # A paragraph with a line break inside is still one paragraph.
    wrapped = find_verdict(_recommendations("**Conclusion:**\n**DEFER**", _REASONS))
    assert wrapped["follows"][0].startswith("Evidence conditions")
    # The conclusion closing a longer paragraph is not a paragraph of its own either.
    closing = find_verdict(_recommendations("Module data are missing [A2]. **Conclusion: DEFER.**", _REASONS))
    assert (closing["statement"], closing["follows"]) == ("Conclusion: DEFER.", [])
    # A rule with the next paragraph right under it, no blank line between: still a rule.
    for rule in ("---", "***", "___"):
        ruled = find_verdict(_recommendations(_ALONE, f"{rule}\n{_REASONS}"))
        assert ruled["follows"] == [], rule


def test_bare_is_a_conclusion_line_that_says_the_verdict_and_nothing_else():
    for line, bare in [
        ("**Conclusion:** **DEFER**", True), ("**Conclusion: DEFER.**", True),
        ("**Decision applicability and conclusion: DEFER.**", True), ("**DEFER.** Module data are missing.", True),
        ("Recommendation: Conditional GO.", True), ("结论：暂缓。", True), ("**Decision:** NO_GO [P1].", True),
        ("**Decision:** DEFER until module-scale data are available [A2].", False),
        # Its reason between the label and the word.
        ("**Decision for the office:** given the missing module data, DEFER.", False),
        ("Recommendation: GO, subject to an independent durability test [A3].", False),
        ("结论：暂缓推进该许可。", False),
        # Not a line of its own: what it says beside the verdict is the point.
        (_DEFER, False), ("The recommendation is NO-GO.", False),
    ]:
        found = _one(line)
        assert found["status"] == "stated", line
        assert found["bare"] is bare, line
    assert find_verdict("")["bare"] is False


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


# ── A passage that ends with a colon: the list it introduces ──────────────

_CONDITIONS = ("This report recommends DEFER on the decision to license the technology, based on four "
               "evidence conditions [A1][A3]:")
_FOUR = ("1. The asset's certified performance is not in the validated evidence [A1].\n"
         "2. Field durability, yield and cost data are absent [A1][M6].\n"
         "3. The patent evidence is snippet-level [P1, P2].\n"
         "4. The market estimates diverge widely [M3][M8].")


def test_a_passage_that_ends_with_a_colon_brings_the_list_right_under_it():
    """The public sample perovskite-silicon-tandem (2026-11-21): the card read
    "…based on four evidence conditions [A1][A3][M6][P1–P8]:" and stopped. The
    four conditions are the list under that sentence; they are quoted as
    written, numbered as the report numbers them."""
    found = find_verdict(_recommendations("**Decision applicability and conclusion: DEFER.**", _CONDITIONS, _FOUR,
                                          "The decision could move to GO if gates G1 and G2 pass [A1]."))
    assert (found["status"], found["statement"], found["follows"]) == (
        "stated", "Decision applicability and conclusion: DEFER.", [_CONDITIONS])
    assert found["items"] == ["The asset's certified performance is not in the validated evidence [A1].",
                              "Field durability, yield and cost data are absent [A1][M6].",
                              "The patent evidence is snippet-level [P1, P2].",
                              "The market estimates diverge widely [M3][M8]."]
    assert (found["ordered"], found["listed"]) == (True, 4)
    # A statement that ends its own paragraph with the colon, over bullets.
    summary = find_verdict(_report("The decision is whether to license. This report concludes **DEFER** for "
                                   "three reasons [A1][M6]:\n\n- The asset's own data are missing.\n"
                                   "- There is no field durability data.\n- There is no yield or cost data [M6]."))
    assert summary["items"] == ["The asset's own data are missing.", "There is no field durability data.",
                                "There is no yield or cost data [M6]."]
    assert (summary["ordered"], summary["listed"]) == (False, 3)
    # A list item whose text runs onto a second line is one item.
    wrapped = find_verdict(_report(f"{_CONDITIONS}\n\n- The asset's data\n  are missing [A1].\n- Second."))
    assert wrapped["items"] == ["The asset's data are missing [A1].", "Second."]
    # The public sample itself.
    sample = find_verdict(samples.read_sample("perovskite-silicon-tandem"))
    assert sample["listed"] == 4 and len(sample["items"]) == 4
    assert sample["items"][0].startswith("The asset's certified performance, stability protocol, reproducibility")


def test_a_list_that_cannot_be_shown_whole_is_counted_and_never_cut():
    """Precision over recall: four entries at most, and only a flat list. A
    longer list, or one with entries nested under its entries, is not shown in
    part; the card says how many the report lists and points to it."""
    five = _FOUR + "\n5. A fifth condition [A2]."
    found = find_verdict(_recommendations(_ALONE + ".", _CONDITIONS, five))
    assert (found["items"], found["listed"]) == ([], 5)
    nested = find_verdict(_recommendations(_ALONE + ".", _CONDITIONS,
                                           "- Academic evidence:\n  - Only abstracts were read [A1].\n- Patents [P1]."))
    assert (nested["items"], nested["listed"]) == ([], 2)


@pytest.mark.parametrize("after", [
    # Something other than a list right under the passage.
    "A paragraph instead [A2].",
    "> A quoted line [A2].",
    "| Gate | Owner |\n|---|---|\n| 1 | TTO |",
    "## 7. Evidence Limitations\n\n- Only abstracts were read.",
    "---\n\n- An item after a rule.",
    "### Conditions\n\n- An item under a sub-heading.",
])
def test_a_passage_ending_with_a_colon_and_no_list_under_it_says_so_and_takes_nothing(after):
    found = find_verdict(_recommendations(_ALONE + ".", _CONDITIONS, after))
    assert (found["items"], found["listed"]) == ([], 0)


def test_only_the_line_that_closes_its_paragraph_can_introduce_a_list():
    # The colon is mid-paragraph: what follows it is the sentence after it, not the list.
    middle = find_verdict(_recommendations("**Conclusion: DEFER.** It rests on these conditions: [A1] none is met. "
                                           "More follows [A2].", "- An item."))
    assert (middle["items"], middle["listed"]) == ([], None)
    # Three sentences in the paragraph after a bare line: the card quotes two, so the
    # passage does not end where the paragraph does.
    long = find_verdict(_recommendations(_ALONE, f"First reason [A1]. Second reason [A2]. {_CONDITIONS}", _FOUR))
    assert (long["items"], long["listed"]) == ([], None)
    # No colon, no list, whatever is under it.
    plain = find_verdict(_recommendations(_ALONE, "The office should wait [A2].", _FOUR))
    assert (plain["items"], plain["listed"], plain["ordered"]) == ([], None, False)
    assert find_verdict("")["items"] == [] and find_verdict("")["listed"] is None
    # A Chinese colon counts as one.
    chinese = find_verdict(_report("本报告的结论是暂缓许可，理由如下 [A1]：\n\n1. 缺少组件数据 [A1]。\n2. 专利状态未核实 [P1]。"))
    assert (chinese["items"], chinese["ordered"]) == (["缺少组件数据 [A1]。", "专利状态未核实 [P1]。"], True)


def test_the_pdf_card_quotes_the_list_or_says_where_it_is():
    found = find_verdict(_recommendations(_ALONE + ".", _CONDITIONS, _FOUR))
    card = card_text(None, found, "English")
    assert card["items"] == [("1.", "The asset's certified performance is not in the validated evidence [A1]."),
                             ("2.", "Field durability, yield and cost data are absent [A1][M6]."),
                             ("3.", "The patent evidence is snippet-level [P1, P2]."),
                             ("4.", "The market estimates diverge widely [M3][M8].")]
    assert card["listed_note"] is None
    bullets = card_text(None, find_verdict(_report(f"{_CONDITIONS}\n\n- One.\n- Two.")), "English")
    assert [mark for mark, _ in bullets["items"]] == ["•", "•"]
    five = card_text(None, find_verdict(_recommendations(_ALONE + ".", _CONDITIONS, _FOUR + "\n5. Five.")), "English")
    assert five["items"] == [] and five["listed_note"] == "(The report lists 5 points here: see them in the report.)"
    none = card_text(None, find_verdict(_recommendations(_ALONE + ".", _CONDITIONS, "A paragraph.")), "Simplified Chinese")
    assert none["listed_note"] == "（报告在这里接着写了下去，在报告中查看）"
    many = card_text(None, find_verdict(_recommendations(_ALONE + ".", _CONDITIONS, _FOUR + "\n5. Five.")),
                     "Simplified Chinese")
    assert many["listed_note"] == "（报告在这里列出了 5 项，在报告中查看）"
    assert card_text(None, find_verdict(_report(_DEFER)), "English")["listed_note"] is None


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


def test_the_pdf_card_breaks_the_line_after_a_conclusion_line_with_no_stop(run):
    """The PDF draws the card from card_text, whose passage carries a line
    break where the conclusion line had no stop; drawn as text, that break
    collapses to a space and the PDF reads "Conclusion: DEFER Evidence ..."."""
    run_id, directory = run(_recommendations(_ALONE, _REASONS))
    assert TestClient(main.app).get(f"/api/runs/{run_id}/report.pdf").status_code == 200
    import fitz

    with fitz.open(directory / "commercialization_report.pdf") as document:
        lines = [line.strip() for line in document[0].get_text().splitlines()]
    # The card only: the report below it has the same two paragraphs as lines of their own.
    card = lines[lines.index("Decision conclusion"):]
    card = card[:next(index for index, line in enumerate(card) if line.startswith("Stated in the report"))]
    at = next(index for index, line in enumerate(card) if line.endswith("Conclusion: DEFER"))
    assert card[at].startswith("The report says:")
    assert card[at + 1].startswith("Evidence conditions behind the conclusion:")


def test_the_pdf_card_carries_the_list_its_passage_introduces(run):
    run_id, directory = run(_recommendations(_ALONE + ".", _CONDITIONS, _FOUR))
    assert TestClient(main.app).get(f"/api/runs/{run_id}/report.pdf").status_code == 200
    text = _pdf_text(directory / "commercialization_report.pdf")
    card = text[text.index("Decision conclusion"):text.index("Stated in the report")]
    assert "based on four evidence conditions [A1][A3]:”" in card
    assert "1. The asset's certified performance is not in the validated evidence [A1]." in card
    assert "4. The market estimates diverge widely [M3][M8]." in card


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
    "listed": "verdict_listed", "continues": "verdict_continues",
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
