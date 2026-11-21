"""The PDF's brief lines are the page's: report_brief.py against result.js.

The page finds the report's own summary sentence and its first recommended
step by rules in result.js; the PDF is made on the server, so the rules are
ported to Python. If the two drift, the PDF a technology-transfer office
forwards says something the page does not. These tests run result.js's own
`decisionBrief` in Node on every public sample and on a set of reports built
to exercise each rule's edge, and require the same five lines from
`brief_lines`. Measured once more widely (2026-11-21, not part of the suite):
the 1,820 reports saved on the maintainer's machine, 0 differences.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from academic_agent.report_brief import BAND_THRESHOLDS, band, brief_lines, sentences_of
from academic_agent.report_display import report_for_display
from api import samples

_ROOT = Path(__file__).resolve().parents[1]
_FIELDS = ("summary", "summary_whole", "risk", "next", "next_whole")

_HARNESS = """
import { readFileSync } from "node:fs";
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
globalThis.document = { createElement: () => ({}), querySelectorAll: () => [], documentElement: {} };
const mod = await import("./result.mjs");
const inputs = JSON.parse(readFileSync(process.argv[2], "utf-8"));
console.log(JSON.stringify(inputs.map(({ scores, markdown }) => {
  const d = mod.decisionBrief({ scores, markdown });
  return d && { summary: d.summary, summary_whole: d.summaryWhole, risk: d.risk,
                next: d.next, next_whole: d.nextWhole, band: d.band.name };
})));
"""


def _page(cases: list[dict]) -> list[dict]:
    """result.js decisionBrief on each {scores, markdown}, in Node."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        source = (_ROOT / "web/static/js/result.js").read_text(encoding="utf-8")
        source = source.replace('import * as api from "./api.js";', "const api = {};")
        (work / "result.mjs").write_text(source, encoding="utf-8")
        shutil.copy2(_ROOT / "web/static/js/i18n.js", work / "i18n.js")
        (work / "run.mjs").write_text(_HARNESS, encoding="utf-8")
        (work / "inputs.json").write_text(json.dumps(cases), encoding="utf-8")
        result = subprocess.run([node, str(work / "run.mjs"), str(work / "inputs.json")],
                                capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=work)
    assert result.returncode == 0, result.stderr[:600]
    return json.loads(result.stdout)


def _same(cases: list[dict]) -> None:
    for case, page in zip(cases, _page(cases), strict=True):
        ours = brief_lines(case["scores"], case["markdown"])
        for field in _FIELDS:
            assert ours[field] == page[field], (field, case["markdown"][:120])


def test_every_public_sample_gives_the_page_s_lines():
    cases = [{"scores": samples.read_sample_scores(s.slug),
              "markdown": report_for_display(samples.read_sample(s.slug))} for s in samples.SAMPLES]
    pages = _page(cases)
    for case, page in zip(cases, pages, strict=True):
        ours = brief_lines(case["scores"], case["markdown"])
        assert {field: ours[field] for field in _FIELDS} == {field: page[field] for field in _FIELDS}
        # Every sample yields all three, so none of this is agreement on nothing.
        assert ours["summary"] and ours["risk"] and ours["next"]


def _report(summary: str = "", recommendations: str = "") -> str:
    return (f"# Academic Commercialization Assessment: x\n\n## Executive Summary\n\n{summary}\n\n"
            f"## 1. Technology Overview & Maturity\n\nBody text [A1].\n\n"
            f"## 5. Commercialization Opportunities & Recommendations\n\n{recommendations}\n\n"
            f"## References\n\n[A1] A paper. https://example.test/a1\n")


_LONG = ("The technology has moved from laboratory demonstrations to early pilot lines across three continents, "
         "with certified efficiencies above thirty percent, independent stability tests in the thousands of hours, "
         "and a growing number of manufacturers announcing capacity plans for the second half of the decade [A1].")
_LONG_NO_CLAUSE = "Word " * 70 + "end."

# Each case is aimed at one rule of result.js; the comment names it.
_EDGE_REPORTS = [
    # A sentence about the report is passed over (ABOUT_THE_REPORT).
    _report("This assessment synthesizes four papers. The cell reached 33% efficiency [A1]."),
    _report("It is written in decision support mode. Pilot lines exist [A1]."),
    _report("本报告综合了公开证据。该技术已进入试点生产阶段 [A1]。"),
    # A decimal, an abbreviation and a heading letter do not end a sentence (fullStopEnds).
    _report("Efficiency rose to 33.9% in the U.S. and e.g. Japan. Next sentence here [A1]."),
    _report("A. Pilot lines exist in Europe. They are small [A1]."),
    _report("Costs fell, i.e. modules are cheaper. etc. and more. The end [A1]."),
    # A lower-case word after a full stop goes on with the sentence (LOWERCASE_WORD).
    _report("Prices fell to 3 c. per watt in 2025 across Europe [A1]. A second sentence."),
    # A bold title heads its first sentence (TITLE_LIMIT).
    _report("**Maturity is uneven.** Robotic systems are established in urology [A1]."),
    _report("- **Key finding:** The market is nascent [A1]."),
    # Too long for the brief: cut at a clause, or at a word (quotedAtClause, quoted).
    _report(_LONG),
    _report(_LONG_NO_CLAUSE),
    # A clause that ends too early to leave much is not where it is cut (CLAUSE_MIN).
    _report("In short, " + "the technology moves from laboratory records toward pilot lines " * 4 + "now [A1]."),
    # A comma inside brackets is not a clause's end (the open/closed check).
    _report("The cells reached record efficiencies in several independent laboratories across three continents, "
            "while manufacturers (including long-established crystalline module makers and new entrants alike, "
            "by their own account) announced pilot capacity across Europe and Asia within the same year [A1]."),
    # A length counted in UTF-16 units: an astral character counts twice.
    _report("𝐂" * 125 + " ends here."),
    # The first recommended step: the labelled route wins (ROUTE_LEAD).
    _report("Pilot lines exist [A1].", "- **Assessment Mode**: Orientation.\n- Build a partnership.\n"
            "- **Primary Commercialization Route:** License to a module maker [A1]."),
    # A route named by a sub-heading (ROUTE_HEADING).
    _report("Pilot lines exist [A1].", "### Primary route: Field-limited licence to a manufacturer\n\n- Reason one."),
    _report("Pilot lines exist [A1].", "### 首选商业化路径\n\n以技术许可为主 [A1]。\n"),
    # A bold-only line over a list is a heading, not a step (BOLD_ONLY, headsAList).
    _report("Pilot lines exist [A1].", "**5.1 Strategic opportunities**\n\n- Partner with a utility [A1].\n"),
    # A statement about the section is not a step (SECTION_NOTE, RECOMMENDATION_PREAMBLE).
    _report("Pilot lines exist [A1].", "- **GO/NO_GO Status:** Not assessed.\n- **Decision Owner**: not given.\n"
            "- Run a pilot with a utility [A1]."),
    # A label on a line of its own waits for the next line (BARE_LABEL).
    _report("Pilot lines exist [A1].", "**Primary Commercialization Route:**\n\nA joint venture with an incumbent [A1].\n"),
    # A step too long for the brief keeps its whole sentence.
    _report("Pilot lines exist [A1].", "- " + _LONG),
    # Nothing to find.
    _report("", ""),
    "No headings at all.",
]


def test_each_rule_s_edge_gives_the_page_s_lines():
    scores = {"overall_score": 61.0, "key_risks": ["  Durability is unproven [A1].  "],
              "key_opportunities": ["A fallback opportunity."]}
    _same([{"scores": scores, "markdown": markdown} for markdown in _EDGE_REPORTS])


def test_a_scorecard_without_risks_or_opportunities():
    _same([
        {"scores": {"overall_score": 50, "key_risks": [], "key_opportunities": []}, "markdown": _report("", "")},
        {"scores": {"overall_score": 50, "key_risks": "not a list"}, "markdown": _report("A line [A1].", "")},
        {"scores": {"overall_score": 50, "key_risks": ["   "], "key_opportunities": ["  An opportunity. "]},
         "markdown": _report("A line [A1].", "")},
    ])


def test_the_grade_thresholds_are_result_js_s():
    """One set of thresholds, so the PDF and the page never grade a run differently."""
    source = (_ROOT / "web/static/js/result.js").read_text(encoding="utf-8")
    body = re.search(r"export function band\(score\) \{(.+?)\n\}", source, re.DOTALL).group(1)
    page = [(float(floor), name) for floor, name in re.findall(r"score >= (\d+)\) return \{ name: t\(\"band_(\w+)\"", body)]
    assert tuple(page) == tuple((float(f), n) for f, n in BAND_THRESHOLDS)
    assert 'name: t("band_nascent")' in body


@pytest.mark.parametrize(("score", "name"), [
    (100, "strong"), (70, "strong"), (69.9, "moderate"), (55, "moderate"), (54.9, "early"),
    (40, "early"), (39.9, "nascent"), (0, "nascent"),
])
def test_band(score, name):
    assert band(score) == name


def test_the_page_grades_the_same_scores_alike():
    scores = [100, 70, 69.9, 55, 54.9, 40, 39.9, 0]
    pages = _page([{"scores": {"overall_score": s}, "markdown": ""} for s in scores])
    english = {"strong": "Strong", "moderate": "Moderate", "early": "Early", "nascent": "Nascent"}
    assert [page["band"] for page in pages] == [english[band(s)] for s in scores]


def test_sentences_of_keeps_a_decimal_and_drops_citations():
    assert sentences_of("It rose to 33.9% [A1, A2]. Then it fell (M3).") == ["It rose to 33.9%.", "Then it fell."]
