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
if (input.brief) {
  const data = mod.decisionBrief(input.brief);
  out.brief = data && {
    band: data.band.name, overall: data.overall, trl: data.trl, mrl: data.mrl,
    strongest: data.strongest && [data.strongest.key, data.strongest.value],
    weakest: data.weakest && [data.weakest.key, data.weakest.value],
    summary: data.summary, evidence: data.evidence, risk: data.risk, next: data.next, changers: data.changers,
  };
  if (data) {
    const nodes = flat(mod._testRenderDecisionBrief(data));
    const text = (node) => flat(node).map(n => n.textContent || n.text || "").join("");
    out.brief_view = {
      tone: nodes[0].dataset.tone,
      title: nodes.find(n => n.className === "brief__title")?.textContent,
      verdict: nodes.find(n => n.className === "brief__verdict")?.textContent,
      readiness: nodes.find(n => n.className === "brief__readiness")?.textContent ?? null,
      lines: nodes.filter(n => (n.className ?? "").startsWith("brief__line ")).map(text),
      cards: Object.fromEntries(nodes.filter(n => n.className === "brief__card").map(n => [n.dataset.card, text(n)])),
      cites: nodes.filter(n => n.className === "cite").map(n => n.dataset.cite),
      changers: nodes.filter(n => n.className === "brief__changer").map(n => [n.dataset.reason, n.textContent]),
      note: nodes.find(n => n.className === "brief__note")?.textContent,
    };
  }
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
if (input.checks) {
  const c = input.checks;
  const texts = (node, cls) => flat(node).filter(n => n.className === cls).map(n => n.textContent);
  out.checks = {};
  if (c.consistency) out.checks.consistency = texts(mod.renderConsistency(c.consistency), "consistency__detail");
  if (c.grounding) out.checks.grounding = texts(mod.renderGrounding(c.grounding), "grounding__why");
  if (c.retrieval) {
    const nodes = flat(mod.renderRetrievalDiagnostics(c.retrieval));
    out.checks.retrieval = {
      summaries: nodes.filter(n => n.className === "source__meta").map(n => n.textContent),
      reasons: nodes.filter(n => n.tagName === "LI" && n.className === "").map(n => n.textContent),
    };
  }
  if (c.progress) out.checks.rows = Object.fromEntries(mod.reliabilityRows(c.progress).map(r => [r.id, r.detail]));
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
        source += "export const _testRenderDecisionBrief = renderDecisionBrief;\n"
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


_SCORES = {
    "overall_score": 50.0, "trl_score": 4.0, "trl_label": "TRL 4 (component validated in laboratory)",
    "mrl_score": 3.5, "patent_strength": 3.0, "market_accessibility": 2.5, "evidence_confidence": 2.0,
    "patent_source_ids": ["P1", "P2"], "market_uncertainty": None,
    "key_risks": ["No named commercial actors in the market registry (M2, M3)."],
    "key_opportunities": ["Patent white space in manufacturing scalability [P4]."],
}
_REPORT = """# Academic Commercialization Assessment: solid-state batteries

## Executive Summary

This assessment synthesizes evidence from four papers [A1, A2], eight patents and eight market sources to evaluate solid-state batteries. The technology shows promise for higher energy density [A1][A3], yet barriers remain unresolved. More text.

## 1. Technology Overview & Maturity

The incumbent is commercially available today.

## 5. Commercialization Opportunities & Recommendations

> **Analyst inference note:** Recommendations are analyst inferences.

### 5.1 Near-Term Opportunities

**Semi-solid-state batteries as an entry point.** Semi-solid cells appear in production EVs [M2]. *Analyst inference:* early share.

## Evidence Limitations

Sources are sparse.
"""
_SOURCES = {"academic_sources": [], "market_sources": [],
            "patent_sources": [{"source_id": "P1", "title": "Older cell patent", "credibility_tier": "medium", "published_date": "2019-01-01"},
                               {"source_id": "P2", "title": "All-solid-state battery system", "credibility_tier": "high", "published_date": "2023-05-04"}]}
_PROGRESS = {"state": "completed", "source_counts": {"academic": 4, "patent": 8, "market": 8},
             "claim_grounding": {"checked": 0, "ungrounded": 0, "unverifiable": 2}, "consistency": {"blockers": 0},
             "decision_gate": {"mode": "orientation"}}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DecisionBriefTests(unittest.TestCase):
    """One screen above the tabs, read from the run's own artifacts: the verdict,
    the strongest evidence, the biggest risk, the first step, and what would
    move the number. No sentence is new and no model is called."""

    @classmethod
    def setUpClass(cls):
        ResultReadabilityTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run(self, **payload):
        return ResultReadabilityTests._run(self, **payload)

    def _brief(self, **over):
        payload = {"scores": _SCORES, "markdown": _REPORT, "sources": _SOURCES, "progress": _PROGRESS}
        payload.update(over)
        return self._run(brief=payload)

    def test_the_verdict_names_the_band_the_score_and_both_readiness_levels(self):
        shown = self._brief()["brief_view"]
        self.assertEqual(shown["title"], "Decision brief")
        self.assertEqual(shown["verdict"], "Early · 50.0 / 100")
        self.assertEqual(shown["readiness"], "TRL 4 (component validated in laboratory) · Manufacturing readiness 3.5 / 10")
        self.assertEqual(shown["tone"], "warning")

    def test_the_strongest_and_weakest_dimensions_are_compared_by_their_share_of_the_scale(self):
        data = self._brief()["brief"]
        self.assertEqual(data["strongest"], ["patent_strength", 3.0])      # 3/5 beats 4/9 and 3.5/10
        self.assertEqual(data["weakest"], ["mrl_score", 3.5])
        line = self._brief()["brief_view"]["lines"][0]
        self.assertEqual(line, "Strongest dimension: Patent position 3 / 5. Weakest: Manufacturing readiness 3.5 / 10.")

    def test_the_reports_own_summary_skips_the_methodological_opener_and_its_citations(self):
        data = self._brief()["brief"]
        self.assertEqual(data["summary"], "The technology shows promise for higher energy density, yet barriers remain unresolved.")
        plain = self._brief(markdown="## Executive Summary\n\nSolid-state cells are early [A1].\n")["brief"]
        self.assertEqual(plain["summary"], "Solid-state cells are early.")
        self.assertIsNone(self._brief(markdown="")["brief"]["summary"])

    def test_the_strongest_evidence_is_the_best_rated_source_cited_by_the_strongest_dimension(self):
        data = self._brief()["brief"]
        self.assertEqual(data["evidence"], {"id": "P2", "title": "All-solid-state battery system", "tier": "high", "year": "2023"})
        without_registry = self._brief(sources=None)["brief"]
        self.assertEqual(without_registry["evidence"], {"id": "P1"})
        uncited = self._brief(scores={**_SCORES, "patent_source_ids": []})["brief"]
        self.assertIsNone(uncited["evidence"])
        card = self._brief()["brief_view"]["cards"]["evidence"]
        self.assertIn("All-solid-state battery system · high · 2023", card)

    def test_the_first_step_is_the_recommendations_sections_first_item_and_falls_back_to_the_first_opportunity(self):
        data = self._brief()["brief"]
        self.assertEqual(data["next"], "Semi-solid-state batteries as an entry point.")
        listed = self._brief(markdown=_REPORT.replace("**Semi-solid-state batteries as an entry point.** Semi-solid",
                                                      "1. **Build a pilot line.** Semi-solid"))["brief"]
        self.assertEqual(listed["next"], "Build a pilot line.")
        fallback = self._brief(markdown="## Executive Summary\n\nShort.\n")["brief"]
        self.assertEqual(fallback["next"], "Patent white space in manufacturing scalability [P4].")

    def test_a_report_saved_with_windows_line_endings_reads_the_same(self):
        """The benchmark corpus is CRLF; a bold-led recommendation there was
        missed because "." never matches a carriage return."""
        crlf = _REPORT.replace("\n", "\r\n")
        data = self._brief(markdown=crlf)["brief"]
        self.assertEqual(data["next"], "Semi-solid-state batteries as an entry point.")
        self.assertEqual(data["summary"], "The technology shows promise for higher energy density, yet barriers remain unresolved.")

    def test_the_risk_and_the_step_keep_their_citations_as_buttons(self):
        shown = self._brief(markdown="")["brief_view"]
        self.assertEqual(shown["cards"]["risk"], "Biggest riskNo named commercial actors in the market registry [M2, M3].")
        self.assertEqual(shown["cites"], ["P2", "M2 M3", "P4"])

    def test_what_would_change_the_verdict_is_read_from_the_checks(self):
        data = self._brief()["brief"]
        self.assertEqual(data["changers"], [
            {"key": "brief_change_evidence", "value": 2.0},
            {"key": "brief_change_market"},
            {"key": "brief_change_grounding", "n": 2},
            {"key": "brief_change_context"},
        ])
        shown = self._brief()["brief_view"]["changers"]
        self.assertEqual([reason for reason, _ in shown], ["evidence", "market", "grounding", "context"])
        self.assertEqual(shown[0][1], "More high-credibility sources: evidence confidence is 2 / 5.")

    def test_a_clean_run_with_a_decision_context_says_nothing_qualifies_the_score(self):
        scores = {**_SCORES, "evidence_confidence": 4.0, "market_accessibility": 4.0}
        progress = {**_PROGRESS, "claim_grounding": {"checked": 5, "ungrounded": 0, "unverifiable": 0},
                    "decision_gate": {"mode": "decision_support"}}
        data = self._brief(scores=scores, progress=progress)["brief"]
        self.assertEqual(data["changers"], [])
        shown = self._brief(scores=scores, progress=progress)["brief_view"]["changers"]
        self.assertEqual(shown, [["none", "Nothing in the checks qualifies the score; new evidence in any domain would still move it."]])

    def test_ungrounded_claims_and_thin_domains_are_named_before_the_context_line(self):
        progress = {**_PROGRESS, "claim_grounding": {"checked": 3, "ungrounded": 1, "unverifiable": 0},
                    "consistency": {"blockers": 1}, "source_counts": {"academic": 2, "patent": 8, "market": 8}}
        data = self._brief(progress=progress)["brief"]
        self.assertEqual([c["key"] for c in data["changers"]],
                         ["brief_change_evidence", "brief_change_market", "brief_change_ungrounded", "brief_change_consistency"])
        shown = self._brief(progress=progress, scores={**_SCORES, "evidence_confidence": 4.0, "market_accessibility": 4.0})
        self.assertEqual([r for r, _ in shown["brief_view"]["changers"]], ["ungrounded", "consistency", "sources", "context"])
        self.assertEqual(shown["brief_view"]["changers"][2][1], "More Academic sources: only 2 were found.")

    def test_without_a_readable_scorecard_there_is_no_brief(self):
        self.assertIsNone(self._run(brief={"scores": {"overall_score": "n/a"}, "markdown": _REPORT})["brief"])
        self.assertIsNone(self._run(brief={"scores": None})["brief"])

    def test_the_chinese_brief_uses_chinese_labels_around_the_reports_own_words(self):
        shown = self._run(language="Simplified Chinese",
                          brief={"scores": _SCORES, "markdown": _REPORT, "sources": _SOURCES, "progress": _PROGRESS})["brief_view"]
        self.assertEqual(shown["title"], "决策简报")
        self.assertEqual(shown["verdict"], "早期 · 50.0 / 100")
        self.assertTrue(shown["lines"][0].startswith("最强维度：专利地位 3 / 5；最弱维度：制造就绪度 3.5 / 10。"))
        self.assertEqual(shown["changers"][0][1], "更多高可信度来源：证据可信度目前 2 / 5。")
        self.assertIn("没有新的模型调用", shown["note"])


class CheckWordingTests(unittest.TestCase):
    """The checks write their reasons into the artifacts as English sentences.
    The page says them again in the reader's language from their parts, and
    shows anything it does not recognise exactly as written."""

    @classmethod
    def setUpClass(cls):
        ResultReadabilityTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run(self, **payload):
        return ResultReadabilityTests._run(self, **payload)

    def _checks(self, language=None, **checks):
        payload = {"checks": checks}
        if language:
            payload["language"] = language
        return self._run(**payload)["checks"]

    _EXCEEDS = ("The conclusions say 'ready for market' while the overall score is 42.5, "
                "below the 70 this phrasing implies.")

    def _consistency(self, detail=_EXCEEDS, kind="recommendation_exceeds_score"):
        return {"checked": True, "blockers": 1, "warnings": 0,
                "findings": [{"severity": "blocker", "kind": kind, "detail": detail,
                              "excerpt": "The technology is ready for market."}]}

    def test_the_consistency_finding_is_said_in_chinese_from_its_parts(self):
        shown = self._checks("Simplified Chinese", consistency=self._consistency())["consistency"]
        self.assertEqual(shown, ["报告结论中出现“ready for market”，而总分为 42.5，低于这种措辞所隐含的 70 分。"])

    def test_the_consistency_finding_is_unchanged_in_english(self):
        shown = self._checks(consistency=self._consistency())["consistency"]
        self.assertEqual(shown, [self._EXCEEDS])

    def test_a_phrase_with_an_apostrophe_is_read_from_its_double_quotes(self):
        detail = ("The conclusions say \"it's ready\" while the overall score is 42, "
                  "below the 70 this phrasing implies.")
        shown = self._checks("Simplified Chinese", consistency=self._consistency(detail))["consistency"]
        self.assertEqual(shown, ["报告结论中出现“it's ready”，而总分为 42，低于这种措辞所隐含的 70 分。"])

    def test_a_finding_the_page_does_not_recognise_stays_as_written(self):
        other = "The report promises a timeline the scorecard does not support."
        shown = self._checks("Simplified Chinese",
                             consistency=self._consistency(other, kind="timeline_exceeds_score"))["consistency"]
        self.assertEqual(shown, [other])
        # The right kind with a differently worded sentence is not guessed at either.
        shown = self._checks("Simplified Chinese", consistency=self._consistency(other))["consistency"]
        self.assertEqual(shown, [other])

    _REASONS = [
        "cites no source present in the registry",
        "every cited source carries only a search snippet, which is a fragment — "
        "a figure missing from it is not evidence the source lacks it",
        "unrecognised numeric or unit notation prevents numeric comparison",
        "every cited source carries only a search snippet",  # a truncated historical note
    ]

    def _grounding(self):
        return {"checked": 0, "ungrounded": 0, "unverifiable": len(self._REASONS),
                "findings": [{"finding_id": f"MF{i}", "status": "unverifiable", "claim": "x",
                              "unverifiable_reason": reason} for i, reason in enumerate(self._REASONS, 1)]}

    def test_each_grounding_reason_is_said_in_chinese_and_the_unknown_one_is_not(self):
        shown = self._checks("Simplified Chinese", grounding=self._grounding())["grounding"]
        self.assertEqual(shown, [
            "引用的来源不在来源登记表中",
            "所引来源都只有搜索摘要片段；片段里没有某个数字，不能说明来源本身没有",
            "数字或单位写法无法识别，无法做数值比对",
            "every cited source carries only a search snippet",
        ])

    def test_grounding_reasons_are_unchanged_in_english(self):
        self.assertEqual(self._checks(grounding=self._grounding())["grounding"], self._REASONS)

    _NOTES = [
        "score=2 (min=4) — removed 'Solid electrolytes: a review'",
        "query source limit reached (12); later results not read",
        "duplicate patent family (same invention as US1234): Battery cell B",
        "deferred (market-report cap): 'Market report 2026'",
        "evidence summary too thin (31 chars): 'Short'",
        "patent title not relevant to topic (score 0.1): 'Chair'",
        "no Crossref metadata matched title 'Some paper' (3 candidates)",
        "Crossref publication date is in the future",
        "OpenAlex work has no title",
        "S2 paper has no DOI: 'S2 paper'",
        "PubMed record has no DOI or PMID: 'PubMed paper'",
        "Lens patent has no lens_id: 'Lens patent'",
        "arXiv abstract too thin (9 chars): 'arXiv thin'",
        "abstract too thin (40 chars): 'Thin'",
        "S2 publication date in future: 2031",
        "duplicates academic title: A review of anodes",
        "duplicate academic title: A review of anodes",
        "official source title is structurally unusable (too short) and its URL has no supported identifier",
        "something the search layer has never said: 'kept: as is'",
    ]

    def _retrieval(self, domain="patent"):
        return {"accepted_sources": 1, "required_sources": 3, "input_topic": "anodes", "search_topic": "anodes",
                "aliases": [], "audit": [{"domain": domain, "query": "anode patents", "result_count": 20,
                                          "accepted_source_ids": ["P1"], "rejected_reasons": self._NOTES}]}

    def test_rejection_notes_are_said_in_chinese_with_the_source_left_as_written(self):
        shown = self._checks("Simplified Chinese", retrieval=self._retrieval())["retrieval"]
        self.assertEqual(shown["reasons"], [
            "相关度 2（最低要求 4）——已移除“Solid electrolytes: a review”",
            "单条查询的来源数已达上限（12），后续结果未读取",
            "同一专利族（与 US1234 是同一项发明）：Battery cell B",
            "暂缓（市场报告已达上限）：'Market report 2026'",
            "证据摘要过短（31 个字符）：'Short'",
            "专利标题与主题不相关（相关度 0.1）：'Chair'",
            "Crossref 中没有与该标题匹配的元数据 'Some paper' (3 candidates)",
            "Crossref 的发表日期在未来",
            "OpenAlex 记录没有标题",
            "Semantic Scholar 记录缺少 DOI：'S2 paper'",
            "PubMed 记录缺少 DOI 或 PMID：'PubMed paper'",
            "Lens 记录缺少 Lens ID：'Lens patent'",
            "arXiv 摘要过短（9 个字符）：'arXiv thin'",
            "摘要过短（40 个字符）：'Thin'",
            "Semantic Scholar 的发表日期在未来：2031",
            "与已有学术来源的标题重复：A review of anodes",
            "与已有学术来源的标题重复：A review of anodes",
            "官方来源的标题结构不可用（too short），且网址没有受支持的标识符",
            "something the search layer has never said: 'kept: as is'",
        ])
        self.assertEqual(shown["summaries"][0], "专利 · 20 个候选 · 1 个通过")

    def test_rejection_notes_are_unchanged_in_english(self):
        shown = self._checks(retrieval=self._retrieval())["retrieval"]
        self.assertEqual(shown["reasons"], self._NOTES)
        self.assertEqual(shown["summaries"][0], "Patents · 20 candidates · 1 accepted")

    def test_an_unknown_domain_key_is_shown_as_the_key(self):
        shown = self._checks("Simplified Chinese", retrieval=self._retrieval(domain="regulatory"))["retrieval"]
        self.assertTrue(shown["summaries"][0].startswith("regulatory · "))

    def test_domain_names_in_the_check_panel_follow_the_source_lists(self):
        progress = {"source_counts": {"academic": 4, "patent": 0, "market": 3}, "failed_domains": ["patent"],
                    "claim_grounding": {"status": "partial", "checked": 3, "ungrounded": 0, "unverifiable": 1,
                                        "unavailable_domains": ["market", "other"]}}
        rows = self._checks("Simplified Chinese", progress=progress)["rows"]
        self.assertIn("未包含 专利", rows["sources"])
        self.assertIn("市场, other", rows["grounding"])
        rows = self._checks(progress=progress)["rows"]
        self.assertIn("without Patents", rows["sources"])
        self.assertIn("Market, other", rows["grounding"])


if __name__ == "__main__":
    unittest.main()
