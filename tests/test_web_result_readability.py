"""What a reader can open from the result page without leaving it.

Citations open a card built from the report's own reference list; each score
shows why; the scope line is a sentence, not a code. Run through Node against
the shipped result.js, like the other web tests.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO = Path(__file__).resolve().parent.parent
_RESULT_JS = _REPO / "web" / "static" / "js" / "result.js"
_I18N_JS = _REPO / "web" / "static" / "js" / "i18n.js"

_HARNESS = r"""
import fs from "node:fs";
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
class Node {
  constructor(tag) { Object.assign(this, { tagName: tag.toUpperCase(), children: [], dataset: {}, attributes: {},
    style: {}, className: "", textContent: "", open: false, title: "", type: "" }); }
  append(...items) { for (const item of items) this.children.push(typeof item === "string" ? { text: item } : item); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener() {}
  get childNodes() { return this.children; }
}
globalThis.document = { createElement: (tag) => new Node(tag), createTextNode: (text) => ({ text }),
  querySelectorAll: () => [], documentElement: {} };
const flat = (node) => [node, ...(node.children ?? []).flatMap(flat)];
const mod = await import("./result.mjs");
const i18n = await import("./i18n.js");
const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
if (input.language) i18n.setLanguage?.(input.language);
const out = {};
if (input.markdown !== undefined) out.index = Object.fromEntries(mod.citationIndex(input.markdown));
if (input.estimates !== undefined) {
  const found = mod.marketEstimates(input.estimates);
  out.estimates = {
    rows: found.rows.map(r => ({ id: r.id, firm: r.firm, scope: r.scope?.key ?? null, year: r.year,
                                 currency: r.currency, billions: r.billions, figure: r.figure })),
    groups: found.groups.map(g => ({ key: g.scope.key, label: g.scope.label, ids: g.rows.map(r => `${r.id}:${r.year}`) })),
    unscoped: found.unscoped.map(r => r.id), firms: found.firms, scopes: found.scopes, ratio: found.sameScopeYearRatio,
  };
}
if (input.scores) {
  const nodes = flat(mod._testRenderScorecard(input.scores, input.sources_for_scorecard ?? null));
  const block = nodes.find(n => n.className === "market-estimates");
  out.market_block = block ? {
    figures: block.dataset.figures, scopes: block.dataset.scopes,
    lede: flat(block).find(n => n.className === "market-estimates__lede")?.textContent,
    headings: flat(block).filter(n => n.className === "market-estimates__scope").map(n => n.textContent),
    rows: flat(block).filter(n => n.className === "market-estimates__row").length,
    cites: flat(block).filter(n => n.className === "cite").map(n => n.dataset.cite),
    note: flat(block).find(n => n.className === "market-estimates__note")?.textContent,
  } : null;
  out.why = nodes.filter(n => n.className === "dim__why").map(n => ({
    summary: n.children[0].textContent, rationale: n.children[1].textContent,
    cites: flat(n).filter(c => c.className === "cite").map(c => c.dataset.cite) }));
  const caveat = nodes.find(n => (n.className ?? "").includes("scorecard__market-caveat"));
  out.caveat = { tag: caveat.tagName, open: caveat.open,
                 title: flat(caveat).find(n => n.className === "notes__title")?.textContent,
                 status: nodes.find(n => n.className === "scorecard__market-status")?.textContent,
                 receipt: nodes.some(n => n.className === "scorecard__cap-receipt") };
}
if (input.card) {
  const index = mod.citationIndex(input.card.markdown);
  const nodes = flat(mod._testRenderCitationCard(input.card.ids, index, null));
  out.card_meta = nodes.filter(n => n.className === "cite-card__meta").map(n => n.textContent);
}
if (input.sources) {
  const rows = mod._testAdmitSavedSources(input.sources).rows;
  out.ages = rows.map(row => flat(mod._testRenderSavedSource(row))
    .filter(n => n.className === "source__age").map(n => n.textContent));
}
if (input.feedback) {
  const clicks = [];
  const nodes = flat(mod._testFeedbackView(input.feedback, (answer, part) => clicks.push([answer, part])));
  const button = (n) => ({ text: n.textContent, pressed: n.attributes["aria-pressed"] });
  out.feedback = {
    recorded: nodes[0].dataset.recorded,
    title: nodes.find(n => n.className === "feedback__title").textContent,
    answers: nodes.filter(n => n.className.includes("feedback__answer")).map(button),
    parts_hidden: nodes.find(n => n.className === "feedback__parts").hidden,
    parts: nodes.filter(n => n.className.includes("feedback__part ") || n.className.endsWith("feedback__part")).map(button),
    status: nodes.find(n => n.className === "feedback__status").textContent,
  };
}
if (input.gate) {
  const nodes = flat(mod._testRenderDecisionApplicability(input.gate));
  out.scope = { text: nodes.filter(n => n.className === "decision-applicability__detail").map(n => n.textContent),
                mode: nodes[0].dataset.mode, codes: nodes.filter(n => n.tagName === "CODE").length };
}
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ResultReadabilityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        work = Path(cls._tmp.name)
        source = _RESULT_JS.read_text(encoding="utf-8").replace(
            'import * as api from "./api.js";', "const api = {};")
        source += "\nexport const _testRenderScorecard = renderScorecard;\n"
        source += "export const _testRenderDecisionApplicability = renderDecisionApplicability;\n"
        source += "export const _testRenderCitationCard = renderCitationCard;\n"
        source += "export const _testAdmitSavedSources = admitSavedSources;\n"
        source += "export const _testRenderSavedSource = renderSavedSource;\n"
        source += "export const _testFeedbackView = feedbackView;\n"
        (work / "result.mjs").write_text(source, encoding="utf-8")
        shutil.copy2(_I18N_JS, work / "i18n.js")
        (work / "harness.mjs").write_text(textwrap.dedent(_HARNESS), encoding="utf-8")
        cls._work = work

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run(self, **payload):
        # A file, not argv: a whole report exceeds the Windows command-line limit.
        (self._work / "input.json").write_text(json.dumps(payload), encoding="utf-8")
        result = subprocess.run(
            [shutil.which("node"), str(self._work / "harness.mjs"), str(self._work / "input.json")],
            capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=self._work,
        )
        self.assertEqual(result.returncode, 0, result.stderr[:800])
        return json.loads(result.stdout)

    def test_the_reference_list_of_a_delivered_report_is_the_card_index(self):
        markdown = (_REPO / "examples" / "hyperloop.md").read_text(encoding="utf-8")
        index = self._run(markdown=markdown)["index"]
        self.assertEqual(len(index), 22)  # A1-A8, P1-P8, M1-M6
        a4 = index["A4"]
        self.assertTrue(a4["label"].startswith("A Reality Check on Maglev Technology"))
        self.assertIn("IEEE Access", a4["label"])
        self.assertEqual((a4["published"], a4["credibility"]), ("2024-01-01", "high"))
        self.assertEqual(a4["url"], "https://doi.org/10.1109/access.2024.3491904")
        self.assertIsNone(index["M1"]["published"])  # "n.d." is not a date
        self.assertEqual(index["M1"]["credibility"], "low")

    def test_the_chinese_display_of_a_reference_list_is_read_too(self):
        from academic_agent.report_display import report_for_display
        shown = report_for_display((_REPO / "examples" / "solid-state-batteries-ev-zh.md").read_text(encoding="utf-8"))
        self.assertIn("可信度：", shown)
        index = self._run(markdown=shown)["index"]
        a1 = index["A1"]
        self.assertTrue(a1["label"].startswith("Configuring solid-state batteries"))
        self.assertNotIn("发布", a1["label"])
        self.assertEqual((a1["published"], a1["credibility"]), ("2021-11-01", "high"))
        self.assertIsNone(index["M1"]["published"])  # 未注明 is not a date
        self.assertEqual(index["M1"]["credibility"], "medium")

    _AGED = ("## References\n\n"
             "[M1] Old hire news. Example News. Published: 2023-05-01. Accessed: 2026-10-21. "
             "Type: reputable_news. Credibility: medium. https://e.test/m1\n\n"
             "[M2] Fresh news. Example News. Published: 2026-03-01. Accessed: 2026-10-21. https://e.test/m2\n\n"
             "[M3] Undated report. Firm. Published: n.d.. Accessed: 2026-10-21. https://e.test/m3\n\n"
             "[A1] Seminal paper. Journal. Published: 2012-01-01. Accessed: 2026-10-21. https://e.test/a1\n")

    def test_an_old_market_source_says_how_old_it_was_when_collected(self):
        index = self._run(markdown=self._AGED)["index"]
        self.assertEqual({k: v["age"] for k, v in index.items()}, {"M1": 3, "M2": None, "M3": None, "A1": None})
        self.assertEqual(index["M1"]["accessed"], "2026-10-21")
        meta = self._run(card={"ids": ["M1", "A1"], "markdown": self._AGED})["card_meta"]
        self.assertEqual(meta[0], "Published 2023-05-01 · Over 3 years old when collected · Credibility medium")
        self.assertNotIn("old when collected", meta[1])

    def test_the_chinese_reference_list_gives_the_age_in_chinese(self):
        shown = ("## 参考文献\n\n[M1] 旧新闻。示例新闻。发布：2025-06-01 · 访问：2026-10-21 · "
                 "类型：权威新闻 · 可信度：中。https://e.test/m1\n")
        index = self._run(markdown=shown, language="Simplified Chinese")["index"]
        self.assertEqual((index["M1"]["published"], index["M1"]["accessed"], index["M1"]["age"]),
                         ("2025-06-01", "2026-10-21", 1))
        meta = self._run(card={"ids": ["M1"], "markdown": shown}, language="Simplified Chinese")["card_meta"]
        self.assertIn("收集时已发布超过 1 年", meta[0])

    def test_the_sources_tab_marks_old_market_sources_only(self):
        def row(source_id, published, accessed="2026-10-21"):
            return {"source_id": source_id, "title": f"Title {source_id}", "publisher": "Publisher",
                    "published_date": published, "accessed_date": accessed, "url": f"https://e.test/{source_id}",
                    "evidence_summary": "Saved text.", "summary_source": "search_snippet"}
        sources = {"academic_sources": [row("A1", "2010-01-01")], "patent_sources": [],
                   "market_sources": [row("M1", "2024-08-09"), row("M2", "2026-09-01"), row("M3", None),
                                      row("M4", "2024-08-09", accessed=None)]}
        self.assertEqual(self._run(sources=sources)["ages"],
                         [[], ["Over 2 years old when collected"], [], [], []])

    def test_prose_citations_are_not_mistaken_for_references(self):
        index = self._run(markdown="Efficiency rose [A1].\n\n## References\n\n[A1] Title. Venue. Published: 2021-05-01. https://e.test/a")["index"]
        self.assertEqual(list(index), ["A1"])

    def test_a_non_http_link_is_not_offered(self):
        index = self._run(markdown="[A1] Title. Published: 2021. javascript:alert(1)")["index"]
        self.assertIsNone(index["A1"]["url"])

    def test_each_score_says_why_and_on_what(self):
        scores = {"overall_score": 41.9, "trl_score": 4, "mrl_score": 1, "patent_strength": 2,
                  "market_accessibility": 2.5, "evidence_confidence": 3,
                  "trl_rationale": "Component validation only.", "trl_source_ids": ["A2", "M3", "not-an-id"],
                  "mrl_rationale": "No manufacturing line.", "mrl_source_ids": []}
        why = self._run(scores=scores)["why"]
        self.assertEqual([w["summary"] for w in why], ["Why 4 / 9", "Why 1 / 10"])
        self.assertEqual(why[0]["rationale"], "Component validation only.")
        self.assertEqual(why[0]["cites"], ["A2 M3"])
        self.assertEqual(why[1]["cites"], [])

    def test_a_run_without_a_cap_record_says_so_rather_than_unreadable(self):
        """A run from before the receipt existed never wrote one. "Record
        unreadable" read as a fault; a damaged record still says unreadable."""
        caveat = self._run(scores={"overall_score": 50, "market_accessibility": 3})["caveat"]
        self.assertEqual((caveat["tag"], caveat["open"]), ("DETAILS", False))
        self.assertEqual(caveat["title"], "Market comparison: not assessed")
        self.assertEqual(caveat["status"], "No adjustment record for this run")
        damaged = self._run(scores={"overall_score": 50, "market_accessibility": 3,
                                    "market_cap_audit": {"version": "legacy-market-cap-audit-v1"}})["caveat"]
        self.assertEqual(damaged["status"], "Adjustment record unreadable")

    # The scores a 2026-10-23 production run delivered: the cap moved 4 -> 3.5.
    _CAPPED = {"overall_score": 71.3, "trl_score": 7, "mrl_score": 7.5, "patent_strength": 3,
               "market_accessibility": 3.5, "evidence_confidence": 3.5,
               "market_uncertainty": "high (91× spread: 0.058–5.3 bn USD)",
               "market_cap_audit": {"version": "legacy-market-cap-audit-v1", "pre_cap_score": 4.0,
                                    "post_cap_score": 3.5, "cap": 3.5, "triggered": True, "applied": True,
                                    "deduction": 0.5, "reason": "legacy_untyped_spread_gt_5"}}

    def test_a_cap_that_moved_the_score_is_one_plain_line_with_the_receipt_folded(self):
        """It used to open, putting the legacy-rule wording above the risks on
        the runs a reader worries about most. Folded, the summary still says
        that comparability was not assessed (the title), that the score moved
        and why (the status). The receipt is still there, one click away."""
        caveat = self._run(scores=self._CAPPED)["caveat"]
        self.assertEqual((caveat["tag"], caveat["open"], caveat["receipt"]), ("DETAILS", False, True))
        self.assertEqual(caveat["title"], "Market comparison: not assessed")
        self.assertEqual(caveat["status"],
                         "Capped at 3.5 / 5 (was 4): the market figures in the sources differ by more than 5×")
        # The untyped amounts behind the legacy flag never appear as USD sizes.
        self.assertNotIn("USD", caveat["status"])
        zh = self._run(scores=self._CAPPED, language="Simplified Chinese")["caveat"]
        self.assertEqual(zh["title"], "市场估值可比性：未核实")
        self.assertEqual(zh["status"], "市场分数封顶为 3.5 / 5（原为 4）：来源中的市场相关数字相差超过 5 倍")

    def test_the_scope_line_is_a_sentence_with_the_codes_kept_aside(self):
        gate = {"mode": "orientation", "go_no_go_allowed": False,
                "threshold_provenance": {"status": "not_established"}}
        scope = self._run(gate=gate)["scope"]
        self.assertEqual(scope["codes"], 0)
        self.assertEqual(scope["mode"], "orientation")
        self.assertIn("orientation brief", scope["text"][0])
        self.assertIn("analyst's proposals", scope["text"][0])
        zh = self._run(gate=gate, language="Simplified Chinese")["scope"]
        self.assertIn("方向性简报", zh["text"][0])

    # ── Reader feedback ───────────────────────────────────────────────────

    def test_an_unanswered_report_asks_one_question_and_holds_the_second(self):
        view = self._run(feedback={"recorded": False})["feedback"]
        self.assertEqual(view["recorded"], "false")
        self.assertEqual(view["title"], "Did this report change how you see the decision?")
        self.assertEqual([a["text"] for a in view["answers"]], ["Yes", "No", "Not sure"])
        self.assertTrue(all(a["pressed"] == "false" for a in view["answers"]))
        self.assertTrue(view["parts_hidden"])
        self.assertIn("nothing else is collected", view["status"])

    def test_a_recorded_answer_is_shown_as_pressed_with_the_part_question(self):
        view = self._run(feedback={"recorded": True, "changed_view": "no", "part": "sources",
                                   "recorded_at": "2026-10-24T10:00:00+00:00"})["feedback"]
        self.assertEqual(view["recorded"], "true")
        self.assertEqual([a["pressed"] for a in view["answers"]], ["false", "true", "false"])
        self.assertFalse(view["parts_hidden"])
        self.assertEqual([p["text"] for p in view["parts"]], ["Scorecard", "Report", "Sources", "Automated checks"])
        self.assertEqual([p["pressed"] for p in view["parts"]], ["false", "false", "true", "false"])
        self.assertEqual(view["status"], "Recorded with this run. Click another answer to change it.")

    def test_a_failed_save_keeps_the_answer_and_says_so(self):
        view = self._run(feedback={"recorded": True, "changed_view": "yes", "part": None, "failed": True})["feedback"]
        self.assertEqual([a["pressed"] for a in view["answers"]], ["true", "false", "false"])
        self.assertEqual(view["status"], "Your answer could not be saved. Try again.")

    def test_the_question_reads_in_chinese(self):
        view = self._run(feedback={"recorded": False}, language="Simplified Chinese")["feedback"]
        self.assertEqual(view["title"], "这份报告改变了你对这项决策的看法吗？")
        self.assertEqual([a["text"] for a in view["answers"]], ["改变了", "没有", "说不准"])

    def test_a_support_label_without_permission_is_not_upgraded(self):
        gate = {"mode": "decision_support", "go_no_go_allowed": False,
                "threshold_provenance": {"status": "owner_approved"}}
        text = self._run(gate=gate)["scope"]["text"][0]
        self.assertIn("is not assessed", text)
        self.assertNotIn("allows a GO/NO_GO", text)


def _market(*rows):
    """A sources artifact with the given market rows (title, summary, publisher)."""
    return {"market_sources": [
        {"source_id": f"M{i + 1}", "title": title, "evidence_summary": summary, "publisher": publisher,
         "url": "https://m.example/x", "source_type": "market_report"}
        for i, (title, summary, publisher) in enumerate(rows)]}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MarketEstimatesTests(unittest.TestCase):
    """Market-size figures are listed under the market their own source names.

    Measured on 181 saved runs before this was written: pooling every figure
    gave a median 157x spread, and the same title-scope and year still differ
    7x between firms. So the block is a reading aid: what each number is, who
    said it, for which year. It compares nothing across markets and leaves the
    score alone."""

    @classmethod
    def setUpClass(cls):
        ResultReadabilityTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run(self, **payload):
        return ResultReadabilityTests._run(self, **payload)

    def test_spelling_and_plural_variants_of_one_market_are_one_group_named_by_the_first(self):
        found = self._run(estimates=_market(
            ("CAR T-cell Therapy Market Size Report, 2026-2033", "valued at $5.8 billion in 2025", "Grandviewresearch"),
            ("CAR-T Cell Therapies Market to reach USD 42.61 billion by 2035", "USD 12.88 billion in 2025", "Yahoo"),
            ("Solid State Battery Market", "$1.6 billion in 2025", "Fortune"),
            ("Solid-State Battery Market Size", "USD 0.26 billion in 2025", "Sns"),
        ))["estimates"]
        self.assertEqual([g["label"] for g in found["groups"]], ["CAR T-cell Therapy", "Solid State Battery"])
        self.assertEqual(found["groups"][0]["ids"], ["M1:2025", "M2:2025"])
        self.assertEqual((found["scopes"], found["firms"]), (2, 4))

    def test_a_figure_repeated_in_one_summary_is_listed_once_with_its_own_year(self):
        found = self._run(estimates=_market(
            ("Hard Carbon Anode Materials Market", "valued at USD 500 million in 2024, growing from USD 500 million "
             "in 2025 to USD 1.2 billion by 2033", "Futuremarketinsights"),
        ))["estimates"]
        self.assertEqual([(r["figure"], r["year"]) for r in found["rows"]],
                         [("USD 500 million", "2024"), ("USD 1.2 billion", "2033")])

    def test_the_year_after_a_figure_wins_over_the_one_before_it(self):
        found = self._run(estimates=_market(
            ("Sodium-ion Battery Market", "In 2024 the market was USD 2 billion by 2030", "Mordor"),
            ("Sodium-ion Battery Market Size", "During 2023 analysts expected growth; revenue of USD 3 billion", "Sns"),
        ))["estimates"]
        self.assertEqual([r["year"] for r in found["rows"]], ["2030", "2023"])

    def test_the_only_comparison_is_within_one_market_year_and_currency(self):
        same = self._run(estimates=_market(
            ("Perovskite Solar Cell Market", "US$ 2 billion in 2025", "A"),
            ("Perovskite Solar Cells Market Report", "USD 4 billion in 2025", "B"),
            ("Perovskite Solar Cell Market", "€ 40 billion in 2025", "C"),            # another currency
            ("Perovskite Solar Cell Market", "USD 400 billion in 2030", "D"),         # another year
            ("Battery Market", "$1 billion in 2025", "E"),                           # another market
        ))["estimates"]
        self.assertEqual(same["ratio"], 2.0)
        self.assertEqual(sorted({r["currency"] for r in same["rows"]}), ["EUR", "USD"])
        alone = self._run(estimates=_market(("Perovskite Solar Cell Market", "USD 2 billion in 2025", "A"),
                                            ("Perovskite Solar Cell Market", "USD 9 billion in 2030", "B")))["estimates"]
        self.assertIsNone(alone["ratio"])

    def test_a_source_whose_title_names_no_market_keeps_its_figures_apart(self):
        found = self._run(estimates=_market(
            ("UNIGRID Begins Commercial-Scale Deliveries of Sodium-Ion Batteries", "a USD 12 million order", "Yahoo"),
            ("Sodium-Ion Battery Market", "USD 2 billion in 2025", "Sns"),
        ))["estimates"]
        self.assertEqual(found["unscoped"], ["M1"])
        self.assertEqual(found["scopes"], 1)

    def test_malformed_sources_yield_no_figures_and_no_error(self):
        for bad in (None, [], {}, {"market_sources": "x"}, {"market_sources": [None, 3, {"source_id": "A1", "title": 1}]},
                    {"market_sources": [{"source_id": "M1", "title": None, "evidence_summary": None}]}):
            with self.subTest(bad=bad):
                found = self._run(estimates=bad)["estimates"]
                self.assertEqual((found["rows"], found["groups"], found["ratio"]), ([], [], None))

    def test_the_scorecard_lists_the_figures_inside_the_folded_market_disclosure(self):
        scores = {"overall_score": 50.0, "trl_score": 4.0, "mrl_score": 3.0, "patent_strength": 3.0,
                  "market_accessibility": 2.5, "evidence_confidence": 2.0, "market_uncertainty": None}
        sources = _market(("Hard Carbon Anode Materials Market", "USD 0.5 billion in 2024", "Futuremarketinsights"),
                          ("Sodium-ion Battery Market", "USD 2 billion in 2025 and USD 44 billion by 2035", "Yahoo"),
                          ("Sodium-ion Battery Market Size", "USD 4 billion in 2025", "Sns"))
        shown = self._run(scores=scores, sources_for_scorecard=sources)
        block = shown["market_block"]
        self.assertEqual((block["figures"], block["scopes"], block["rows"]), ("4", "2", 4))
        self.assertEqual(block["headings"], ["Sodium-ion Battery", "Hard Carbon Anode Materials"])
        self.assertEqual(block["lede"], "4 market-size figures from 3 sources cover 2 differently defined markets. "
                                        "Within one market and year, the figures differ by up to 2.0×.")
        self.assertEqual(block["cites"], ["M2", "M3", "M2", "M1"])  # by year within a market, then by id
        self.assertIn("score above is unchanged", block["note"])
        self.assertEqual(shown["caveat"]["title"], "Market comparison: not assessed")
        self.assertFalse(shown["caveat"]["open"])

    def test_without_the_sources_artifact_the_scorecard_is_as_before(self):
        scores = {"overall_score": 50.0, "market_accessibility": 2.5, "market_uncertainty": None}
        self.assertIsNone(self._run(scores=scores)["market_block"])

    def test_no_figure_and_the_chinese_wording_are_both_said(self):
        scores = {"overall_score": 50.0, "market_accessibility": 2.5, "market_uncertainty": None}
        none = self._run(scores=scores, sources_for_scorecard=_market(("Sodium-ion Battery Market", "no numbers here", "X")))
        self.assertEqual(none["market_block"]["lede"], "The saved market sources state no market-size figure.")
        zh = self._run(language="Simplified Chinese", scores=scores,
                       sources_for_scorecard=_market(("Sodium-ion Battery Market", "USD 2 billion in 2025", "Sns"),
                                                     ("Sodium-ion Battery Market", "USD 30 billion in 2025", "Yahoo")))
        self.assertEqual(zh["market_block"]["lede"], "2 个市场规模数字来自 2 个来源，涉及 1 个定义不同的市场。同一市场、同一年份的数字最大相差 15 倍。")
        self.assertIn("上方评分不变", zh["market_block"]["note"])


if __name__ == "__main__":
    unittest.main()
