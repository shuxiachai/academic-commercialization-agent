"""What a reader can open from the result page without leaving it.

Citations open a card built from the report's own reference list; each score
shows why; the scope line is a sentence, not a code. Run through Node against
the shipped result.js, like the other web tests.
"""

from __future__ import annotations

import json
import re
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
const printing = { listeners: {}, notes: [] };
globalThis.window = { addEventListener: (type, heard) => { (printing.listeners[type] ??= []).push(heard); } };
globalThis.document = { createElement: (tag) => new Node(tag), createTextNode: (text) => ({ text }),
  querySelectorAll: (selector) => (selector === "details.reviewer-notes" ? printing.notes : []), documentElement: {} };
const flat = (node) => [node, ...(node.children ?? []).flatMap(flat)];
const mod = await import("./result.mjs");
const i18n = await import("./i18n.js");
const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
if (input.language) i18n.setLanguage?.(input.language);
const out = {};
if (input.render !== undefined) out.html = mod.renderMarkdown(input.render);
if (input.summary !== undefined) {
  const view = (node) => {
    const nodes = flat(node);
    const one = (name) => nodes.find(n => n.className === name);
    return { classes: node.className, tone: one("scorecard__figure")?.dataset.tone, value: one("scorecard__value tabular")?.textContent,
      denom: one("scorecard__denom")?.textContent, band: one("scorecard__band")?.textContent,
      rows: nodes.filter(n => n.className === "dim").map(n => [n.children[0].textContent, n.children[2].textContent,
        n.children[1].children[0].style.width, n.children.length]),
      folds: nodes.filter(n => n.tagName === "DETAILS").length, cites: nodes.filter(n => n.className === "cite").length,
      notes: nodes.filter(n => (n.className ?? "").split(" ").includes("notes")).length };
  };
  const node = mod.renderScoreSummary(input.summary);
  out.summary = node && view(node);
  out.full = view(mod._testRenderScorecard(input.summary));
}
if (input.print) {
  // Two folds on the page: one the reader has opened, one they have not.
  const [opened, folded] = [{ open: true, dataset: {} }, { open: false, dataset: {} }];
  printing.notes = [opened, folded];
  const state = () => [opened.open, folded.open];
  const fire = (type) => (printing.listeners[type] ?? []).forEach((heard) => heard());
  out.print = { heard: Object.fromEntries(Object.entries(printing.listeners).map(([k, v]) => [k, v.length])) };
  fire("beforeprint"); out.print.printing = state();
  fire("beforeprint"); out.print.printing_twice = state();
  fire("afterprint"); out.print.after = state();
  out.print.marks = [opened, folded].map((node) => Object.keys(node.dataset).length);
  fire("afterprint"); out.print.after_twice = state();
}
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
if (input.sample_facts) out.sample_facts = input.sample_facts.map(sample => mod.sampleFacts(sample));
if (input.brief) {
  // A sample page hands the brief the reference list it already parsed for the citation cards.
  if (input.brief.references === true) input.brief.references = mod.citationIndex(input.brief.markdown);
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
                 receipt: nodes.some(n => n.className === "scorecard__cap-receipt"),
                 receipt_text: nodes.find(n => n.className === "scorecard__cap-receipt")?.textContent ?? null };
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
        # Unfolded, the receipt says why in a reader's words. What it must
        # still say (docs/results-2026-09-11-market-score-delivery-disclosure.md):
        # the figures may not measure the same thing, so the spread is not a
        # verified disagreement; and it never sizes them in a currency.
        why = ("Why: the market figures collected differ by more than 5×. They may not measure the same thing "
               "(metric, currency, year or scope), so this is not a verified disagreement between sources.")
        self.assertTrue(caveat["receipt_text"].endswith("The cap reduced the score. " + why), caveat["receipt_text"])
        self.assertTrue(zh["receipt_text"].endswith(
            "本次封顶降低了分数。 原因：收集到的市场相关数字相差 5 倍以上。它们的口径可能不同（指标、币种、年份或范围），所以这不是已核实的分歧。"),
            zh["receipt_text"])
        for text in (caveat["receipt_text"], zh["receipt_text"]):
            self.assertNotRegex(text, r"USD|legacy|untyped|旧版|未分类")

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

    def test_a_page_with_no_registry_picks_the_evidence_from_the_reports_own_reference_list(self):
        """A sample page has the report and its scorecard, not the run's source
        registry, so its brief named the first source the strongest dimension
        cited, with no title: for the glucose-monitoring sample a 2020
        syndicated market story rated medium, beside a Lancet consensus rated
        high. The report's own reference list states each source's rating, and
        the page already parses it for the citation cards. Over 196 saved runs
        (2026-11-13) the first id was a lower-rated source than the best one
        in 39; the reference list named the same source as the registry in
        195."""
        refs = ("\n## References\n\n"
                "[P1] Older cell patent. Google Patents. Published: 2019-01-01. Accessed: 2026-11-08. Type: patent. "
                "Credibility: medium. Rationale: snippet only. https://example.org/p1\n"
                "[P2] All-solid-state battery system. Google Patents. Published: 2023-05-04. Accessed: 2026-11-08. "
                "Type: patent. Credibility: high. Rationale: granted. https://example.org/p2\n")
        named = {"id": "P2", "title": "All-solid-state battery system. Google Patents", "tier": "high", "year": "2023"}
        sample = self._brief(sources=None, markdown=_REPORT + refs, references=True)
        self.assertEqual(sample["brief"]["evidence"], named)
        self.assertIn("All-solid-state battery system. Google Patents · high · 2023", sample["brief_view"]["cards"]["evidence"])
        # Nothing else in the brief follows from having the references.
        plain = self._brief(sources=None, markdown=_REPORT + refs)
        self.assertEqual(plain["brief"]["evidence"], {"id": "P1"}, "without them, the first id as before")
        for line in ("summary", "risk", "next", "changers", "band", "strongest", "weakest"):
            self.assertEqual(sample["brief"][line], plain["brief"][line], line)
        self.assertEqual(sample["brief_view"]["changers"], plain["brief_view"]["changers"])
        # A run page has the registry, and it is still what decides there.
        registry = {**_SOURCES, "patent_sources": [
            {"source_id": "P1", "title": "Older cell patent", "credibility_tier": "high", "published_date": "2019-01-01"},
            {"source_id": "P2", "title": "All-solid-state battery system", "credibility_tier": "low", "published_date": "2023-05-04"}]}
        self.assertEqual(self._brief(sources=registry, markdown=_REPORT + refs, references=True)["brief"]["evidence"]["id"], "P1")
        # Equally rated sources stay in the order the scorecard cites them. The
        # newer one first was measured and not adopted: it would change 78 of
        # 196 picks, often a cited review for a paper published that week.
        level = refs.replace("Credibility: medium", "Credibility: high")
        self.assertEqual(self._brief(sources=None, markdown=_REPORT + level, references=True)["brief"]["evidence"]["id"], "P1")
        # A cited source the report does not list is rated last, not first.
        only_second = "\n## References\n\n" + refs.split("\n")[4] + "\n"
        self.assertEqual(self._brief(sources=None, markdown=_REPORT + only_second, references=True)["brief"]["evidence"], named)
        # With none of them listed, or no reference list at all, the first id stands.
        self.assertEqual(self._brief(sources=None, markdown=_REPORT, references=True)["brief"]["evidence"], {"id": "P1"})
        # The Chinese display of a reference list is read the same way.
        chinese = ("\n## 参考文献\n\n[P1] 旧电池专利。Google Patents。发布：2019-01-01 · 访问：2026-11-08 · 类型：专利 · 可信度：中\n"
                   "[P2] 全固态电池系统。Google Patents。发布：2023-05-04 · 访问：2026-11-08 · 类型：专利 · 可信度：高\n")
        picked = self._brief(sources=None, markdown=_REPORT + chinese, references=True)["brief"]["evidence"]
        self.assertEqual((picked["id"], picked["tier"], picked["year"]), ("P2", "high", "2023"))

    def test_a_sample_card_says_the_verdict_the_readiness_level_and_the_language(self):
        """The six samples run from 48.6 to 74.9, which is the tool telling an
        early technology from a mature one, and a visitor had to open each to
        see it. The band is the scorecard's own: one function, no second copy
        of the thresholds."""
        facts = self._run(sample_facts=[
            {"overall_score": 74.9, "trl_score": 9, "language": "Simplified Chinese"},
            {"overall_score": 48.6, "trl_score": 5.5, "language": "English"},
            {"overall_score": 70, "trl_score": None, "language": "English"},
            {"overall_score": 39.99, "trl_score": 2, "language": "Klingon"},
            {"overall_score": None, "trl_score": 9, "language": "English"},
            {"overall_score": "74", "trl_score": 0, "language": None},
            {"title": "An entry from before scores were listed"},
        ])["sample_facts"]
        self.assertEqual(facts[0], {"verdict": "74.9 / 100 · Strong", "tone": "success", "trl": "TRL 9",
                                    "language": "Report in Chinese"})
        self.assertEqual(facts[1], {"verdict": "48.6 / 100 · Early", "tone": "warning", "trl": "TRL 5.5",
                                    "language": "Report in English"})
        self.assertEqual((facts[2]["verdict"], facts[2]["trl"]), ("70.0 / 100 · Strong", None))
        self.assertEqual((facts[3]["verdict"], facts[3]["tone"], facts[3]["language"]), ("40.0 / 100 · Nascent", "muted", None))
        self.assertEqual(facts[4], {"verdict": None, "tone": None, "trl": "TRL 9", "language": "Report in English"})
        self.assertEqual(facts[5], {"verdict": None, "tone": None, "trl": None, "language": None})
        self.assertEqual(facts[6], {"verdict": None, "tone": None, "trl": None, "language": None})
        # The same words as the scorecard above a report uses for the same score.
        for score, name in ((74.9, "Strong"), (55, "Moderate"), (48.6, "Early"), (12, "Nascent")):
            brief = self._brief(scores={**_SCORES, "overall_score": score})["brief"]
            card = self._run(sample_facts=[{"overall_score": score}])["sample_facts"][0]
            self.assertEqual(brief["band"], name)
            self.assertTrue(card["verdict"].endswith(f"· {name}"), card["verdict"])
        chinese = self._run(language="Simplified Chinese", sample_facts=[
            {"overall_score": 74.9, "trl_score": 9, "language": "Simplified Chinese"},
            {"overall_score": 48.6, "trl_score": 5, "language": "English"}])["sample_facts"]
        self.assertEqual(chinese[0], {"verdict": "74.9 / 100 · 较强", "tone": "success", "trl": "TRL 9", "language": "中文报告"})
        self.assertEqual(chinese[1]["language"], "英文报告")

    def test_the_first_step_is_the_recommendations_sections_first_item_and_falls_back_to_the_first_opportunity(self):
        data = self._brief()["brief"]
        self.assertEqual(data["next"], "Semi-solid-state batteries as an entry point.")
        listed = self._brief(markdown=_REPORT.replace("**Semi-solid-state batteries as an entry point.** Semi-solid",
                                                      "1. **Build a pilot line.** Semi-solid"))["brief"]
        self.assertEqual(listed["next"], "Build a pilot line.")
        fallback = self._brief(markdown="## Executive Summary\n\nShort.\n")["brief"]
        self.assertEqual(fallback["next"], "Patent white space in manufacturing scalability [P4].")

    def _next(self, section):
        report = ("## Executive Summary\n\nShort.\n\n## 5. Commercialization Opportunities & Recommendations\n\n"
                  + section + "\n\n## Evidence Limitations\n\nSparse.\n")
        return self._brief(markdown=report)["brief"]["next"]

    def test_the_first_step_is_not_the_statement_of_what_the_section_is(self):
        """The writer's contract opens the recommendations with the assessment
        mode and the decision owner. Read as the first item, "Assessment Mode:
        Orientation." was the first recommended step of 80 of 193 saved runs
        (2026-11-11). The forms below are the ones those reports use."""
        route = "A partnership-based integration strategy is preferred over competing on sensor hardware."
        opening = ("**Assessment Mode**: Orientation. A GO/NO-GO decision is not assessed.\n\n"
                   "**Decision Owner**: Not established. No actor has been identified.\n\n")
        # The label over the route is not part of the step either (2026-11-12).
        self.assertEqual(self._next(opening + f"**Primary Commercialization Route**: {route} More follows."), route)
        # Each spelling of the opening that the saved reports carry.
        for mode in ("**Assessment Mode: ORIENTATION**\nThis is an orientation brief for a transfer office.",
                     "**Assessment Mode:** Orientation. The responsible decision owner is **not established**.",
                     "- **Assessment Mode Statement:** This section is written in orientation mode.",
                     "**Assessment mode: orientation.**\n\n**Responsible decision owner: not established.**"):
            with self.subTest(mode=mode):
                self.assertEqual(self._next(f"{mode}\n\n1. **Build a pilot line.** Semi-solid cells first."),
                                 "Build a pilot line.")
        chinese = self._brief(markdown=(
            "## 执行摘要\n\n很短。\n\n## 5. 商业化机遇与建议\n"
            "**评估模式**：本报告为**定向评估**。未进行决策评估。\n\n"
            "**决策主体**：未确定。\n\n"
            "**首选商业化路线：通过技术许可向现有市场领导者提供关键技术**\n此路线是首选。\n"))["brief"]
        self.assertEqual(chinese["next"], "通过技术许可向现有市场领导者提供关键技术")
        # A section that says only what it is recommends nothing: the brief
        # falls back to the scorecard's first opportunity, as with no section.
        self.assertEqual(self._next(opening.strip()), "Patent white space in manufacturing scalability [P4].")
        # The words are skipped only where they open a line, not wherever they occur.
        self.assertEqual(self._next("1. **Confirm the decision owner's budget before the assessment mode changes.**"),
                         "Confirm the decision owner's budget before the assessment mode changes.")

    def test_a_label_on_its_own_line_hands_the_step_to_the_line_under_it(self):
        """"**Primary Commercialization Route:**" alone was the first step of 13
        more of the 193: a heading for the sentence below it."""
        route = "The preferred primary route is B2G infrastructure development for regional governments."
        self.assertEqual(self._next(f"**Primary Commercialization Route:**\n{route} It suits freight.\n1. A reason."), route)
        self.assertEqual(self._next(f"**Primary Commercialization Route**\n\n{route}"), route, "the same heading without its colon")
        self.assertEqual(self._next("**首选商业化路线**\n\n建议与电网公司合作开发。其余从略。"), "建议与电网公司合作开发。")
        self.assertEqual(self._next("**Opportunities:**\n\n1. **Build a pilot line.** Then scale."), "Build a pilot line.")
        # A whole paragraph that ends in a colon is the recommendation, not a
        # label for the list under it (the Hyperloop sample is written so).
        paragraph = (f"**Primary Commercialization Route:**\n{route} This route is preferred over "
                     "private-only development for three reasons that the sources support and that follow:\n"
                     "1. Regulatory frameworks are being developed.")
        self.assertEqual(self._next(paragraph), route)
        lone = ("The preferred route is licensing to incumbent equipment makers rather than entering as a vendor, "
                "which the evidence supports in three ways:")
        self.assertEqual(self._next(f"**Primary Commercialization Route:**\n{lone}\n1. Order books are full."), lone)
        # A label with nothing under it before the section ends.
        self.assertEqual(self._next("**Primary Commercialization Route:**"), "Patent white space in manufacturing scalability [P4].")
        # A sub-heading is not the text a label was waiting for.
        self.assertEqual(self._next("**Opportunities:**\n\n### 5.1 Near term\n\n- Build a pilot line."), "Build a pilot line.")

    def test_the_first_step_is_what_to_do_not_a_label_over_it(self):
        """What was still shown as the first step after the two changes above,
        over the 193 saved runs with a scorecard (2026-11-12). The run on the
        public deployment read "Primary commercialization route (one route,
        alternatives secondary)." The forms below are the ones those reports use."""
        # A route label written as a sentence, or too long to be taken for a label.
        single = "The single route advanced is integrated project development sold through long-term offtake."
        self.assertEqual(self._next(
            f"**Primary commercialization route (one route, alternatives secondary).** {single} Reasons follow."), single)
        self.assertEqual(self._next(
            "**Primary commercialization route (analyst inference — one route, with alternatives secondary):**\n"
            "*Subsystem and enabling-layer commercialization* — supplying levitation components to operators.\n"
            "**Secondary alternatives (subordinated):**\n- A full line."),
            "Subsystem and enabling-layer commercialization — supplying levitation components to operators.")
        self.assertEqual(self._next("**首要商业化路径（唯一主要路径）。** 本报告提出以数字化运维软件作为首要商业化路径。理由如下。"),
                         "本报告提出以数字化运维软件作为首要商业化路径。")
        self.assertEqual(self._next("**主导商业化路径：针对电信运营商的混合QKD城域安全服务。**"), "针对电信运营商的混合QKD城域安全服务。")
        self.assertEqual(self._next("**Preferred route:** License the coating process to cell makers. Then scale."),
                         "License the coating process to cell makers.")
        self.assertEqual(self._next("**主要商业化路线：高价值多用途集成平台（风电+X）**"), "高价值多用途集成平台（风电+X）")
        # A sentence that only mentions a route is no label.
        whole = "A potential primary commercialization route is out-licensing the sensor hardware."
        self.assertEqual(self._next(f"1. {whole} More."), whole)
        named = "Primary route selection should wait for the pilot data."
        self.assertEqual(self._next(f"1. {named} More."), named)

        # What the section is, or what it rests on: neither is a step.
        notes = ("**Mode:** Orientation\n\n**GO/NO_GO Status:** Not assessed.\n\n"
                 "**责任决策者**：未确立（not established）。\n\n"
                 "**Note:** The following opportunities are analyst inferences drawn from the evidence.\n\n")
        self.assertEqual(self._next(notes + "1. Build a pilot line with a partner. Then scale."),
                         "Build a pilot line with a partner.")
        self.assertEqual(self._next(notes.strip()), "Patent white space in manufacturing scalability [P4].")
        # A paragraph after such a statement is not a step the statement was labelling.
        self.assertEqual(self._next("**Note:** Analyst inferences follow.\n\nThis section is short.\n\n1. Build a pilot line."),
                         "Build a pilot line.")
        for basis, advice, step in (
            ("**Evidence basis:** All nine marketed products use an autologous approach [M2].",
             "**Recommendation:** Companies could prioritise allogeneic platforms. More follows.",
             "Companies could prioritise allogeneic platforms."),
            ("**Evidence basis.** All nine marketed products use an autologous approach [M2].",
             "**Recommendation.** There may be an opening for allogeneic therapies. More follows.",
             "There may be an opening for allogeneic therapies."),
            ("**Evidence Base:** The ambient-air process achieved 16.13% efficiency.",
             "**Recommendations**: Scale the ambient-air process first.", "Scale the ambient-air process first."),
            ("**证据基础**：六件专利均未涉及界面层或涂层技术。", "**建议**：围绕界面涂层提交专利申请。其余从略。", "围绕界面涂层提交专利申请。"),
            ("**Rationale:** Adoption is expected to hinge on price.", "1. Cut the cost of the membrane first.",
             "Cut the cost of the membrane first."),
            ("**推荐理由：** 该路径在技术和经济上更具近期可行性。", "- 先做示范项目。", "先做示范项目。"),
        ):
            with self.subTest(basis=basis):
                self.assertEqual(self._next(f"{basis}\n\n{advice}"), step)
        self.assertEqual(self._next("**Analyst inference:** Stakeholders may wish to prioritise stable chemistries. More."),
                         "Stakeholders may wish to prioritise stable chemistries.")
        # The same words inside a recommendation are left alone.
        for step in ("Note the regulatory path before filing.", "Recommend two partners early.",
                     "Rationale-driven licensing suits this field.", "Mode switching hardware is the entry point."):
            with self.subTest(step=step):
                self.assertEqual(self._next(f"1. {step} More follows."), step)

        # A heading over a list is the list's heading; the step is its first item.
        self.assertEqual(self._next("**5.1 战略机遇**\n1. **BIPV与建筑市场**：柔性组件可直接满足轻质需求。其余从略。"),
                         "BIPV与建筑市场：柔性组件可直接满足轻质需求。")
        self.assertEqual(self._next("**A. 短期（0-2年）：聚焦已产生收入的先行者**\n- 关注头部企业的产能释放。\n- 其余从略。"),
                         "关注头部企业的产能释放。")
        self.assertEqual(self._next(
            "**Near-Term Opportunities (0–3 Years)**\n\n"
            "*Independent Validation Services*: Given the need for reproducibility, there may be an opening. More."),
            "Independent Validation Services: Given the need for reproducibility, there may be an opening.")
        # A numbered opportunity's title over its own evidence and reasons is the step.
        self.assertEqual(self._next("**Opportunity 1: Lead-Free Perovskite BIPV**\n- **Evidence:** Lead toxicity restricts deployment.\n"
                                    "- **Target:** Building facades."), "Opportunity 1: Lead-Free Perovskite BIPV")
        for title in ("机遇一：干法制造与低温致密化工艺开发", "机遇1：医疗辅助通信设备", "机会一：差异化性能定位", "路径一：技术许可（短期可行）"):
            with self.subTest(title=title):
                self.assertEqual(self._next(f"**{title}**\n- 证据支持：学术文献将干法加工列为关键策略。"), title)
        # Without a number it names no one opportunity: it is the list's heading again.
        self.assertEqual(self._next("**机遇与建议**\n1. 先做示范项目。\n2. 其余从略。"), "先做示范项目。")
        # Over a paragraph, or over nothing, the bold line is the recommendation's own title.
        self.assertEqual(self._next("**Strategic Partnership Model**\nThe HELENA project shows the value of consortia [M1]."),
                         "Strategic Partnership Model")
        self.assertEqual(self._next("**高性能仿真驱动的工程优化与服务。**\n理由：仿真工具有显著优势。"), "高性能仿真驱动的工程优化与服务。")
        self.assertEqual(self._next("**Strategic Partnership Model**"), "Strategic Partnership Model")
        self.assertEqual(self._next("**Strategic Partnership Model**\n\n### 5.2 Later\n\n- Build a pilot line."),
                         "Strategic Partnership Model")

        # A table under a label is not the text the label was waiting for.
        self.assertEqual(self._next("**Opportunities:**\n\n| 机遇 | 短期可行性 |\n|---|---|\n| 健康监测贴片 | 中 |\n\n1. 先开发健康监测贴片。"),
                         "先开发健康监测贴片。")

    def test_the_first_step_is_the_route_wherever_the_section_names_it(self):
        """Since October 2026 the writer's contract has the section name exactly
        one primary commercialization route, among statements of mode, owner,
        cost and provenance in whatever order the model writes them. Of the 88
        saved reports made since then, 83 showed that route as the first step
        and 5 showed something else (2026-11-13), all five with the route under
        a sub-heading: three showed the first reason listed under a heading that
        named the route, two a statement with a label nobody had listed. The
        forms below are the ones those five reports use."""
        mode = "### 评估模式声明\n本章节处于**导向模式**。本报告**不评估**针对特定主体的 GO/NO_GO 决策。\n\n"
        # The route's name is in the sub-heading and its reasons are listed under it.
        self.assertEqual(self._next(
            mode + "### 首选商业化路径：面向新兴市场的离岸绿色氢能独立供电系统\n"
            "**推荐理由：** 相比于传统的深远海并网发电，该路径可能更具近期可行性。\n"
            "1.  **规避电网瓶颈：** 可直接在离岸生产氢气 [A2][A3]。\n2.  **环境适配性：** 水动力条件温和 [A3]。"),
            "面向新兴市场的离岸绿色氢能独立供电系统")
        self.assertEqual(self._next(
            mode + "### 首选商业化路径：高价值化学品生物制造\n**理由**：\n"
            "1.  **技术可行性与差异化**：已实现2-3倍增产 [A3]。\n2.  **经济优势**：单位质量价值更高。"),
            "高价值化学品生物制造")
        for heading in ("### Primary Commercialization Route: Component licensing to incumbents",
                        "### 5.1 Primary Commercialization Route: Component licensing to incumbents",
                        "#### Preferred route (analyst inference): Component licensing to incumbents",
                        "### **Primary Commercialization Route:** Component licensing to incumbents"):
            with self.subTest(heading=heading):
                self.assertEqual(self._next(
                    f"{heading}\n\n**Rationale:**\n1. **Lower capital need.** Licensing avoids a plant.\n2. More."),
                    "Component licensing to incumbents")

        # The sub-heading is the label alone and the route is the line under it,
        # after a statement about cost that is not a step.
        opening = ("**Assessment mode: orientation.** No decision context was supplied. **Actor-specific GO/NO_GO is not "
                   "assessed.**\n\n**Decision owner:** not established.\n\n")
        self.assertEqual(self._next(
            opening + "**Cost, capital and time:** not established. The registry contains no cost figures [A5][A6].\n\n"
            "### Primary route (analyst inference)\n\n"
            "**Route: a platform-agnostic training and assessment layer** (simulation content sold to hospitals). "
            "It rests on the strongest evidence.\n\n*Why this route is preferred (analyst inference).*\n"
            "- It rests on the strongest-rated evidence in the registry."),
            "a platform-agnostic training and assessment layer (simulation content sold to hospitals).")
        self.assertEqual(self._next(
            opening + "**Provenance legend.** *Observed facts* are statements in cited source summaries. "
            "*Estimates* are market-report figures.\n\n### Primary commercialization route\n\n"
            "**Primary route (analyst orientation recommendation): an enabling-technology layer sold to every "
            "platform maker.**\n\nRationale from evidence:\n- The fastest-growing value pool is digital [M5]."),
            "an enabling-technology layer sold to every platform maker.")
        self.assertEqual(self._next(
            "### Primary commercialization route\n\nThe preferred route is licensing to cell makers. It needs no plant.\n\n"
            "- Order books are full."), "The preferred route is licensing to cell makers.")
        self.assertEqual(self._next("### 首选商业化路线\n\n建议与电网公司合作开发。其余从略。\n\n- 订单充足。"), "建议与电网公司合作开发。")

        # The route is the step even when something else stands before it in the
        # section: a statement nobody listed, or a list of gates.
        self.assertEqual(self._next(
            "**Scope of this section.** Orientation only; no owner has approved a gate.\n\n"
            "1. Gate one is a pilot line with a partner.\n\n"
            "**Primary Commercialization Route:** License the coating process to cell makers. Then scale."),
            "License the coating process to cell makers.")
        self.assertEqual(self._next(
            "1. Gate one is a pilot line with a partner.\n\n### Primary commercialization route\n\n"
            "The preferred route is licensing to cell makers. It needs no plant."),
            "The preferred route is licensing to cell makers.", "a list before the route's sub-heading")
        # A name in a sub-heading is read as any step is: without its citations.
        self.assertEqual(self._next("### Primary Commercialization Route: Licensing to incumbents [M1][M2]\n\n- A reason."),
                         "Licensing to incumbents")
        # A route's name over its own reasons is the step, as an opportunity's title is.
        self.assertEqual(self._next(
            "**Primary Commercialization Route: Component licensing to incumbents**\n"
            "1. **Lower capital need.** Licensing avoids a plant.\n2. More."), "Component licensing to incumbents")

        # Without a route, the two statements are still not steps.
        notes = ("**Cost, capital and time:** not established. No source gives a figure.\n\n"
                 "**Provenance legend.** Observed facts are cited; estimates are marked.\n\n")
        self.assertEqual(self._next(notes + "1. Build a pilot line with a partner. Then scale."),
                         "Build a pilot line with a partner.")
        self.assertEqual(self._next(notes.strip()), "Patent white space in manufacturing scalability [P4].")
        for step in ("Cost, capital and time are the three limits to plan around.",
                     "Provenance legends on each figure would help a reviewer."):
            with self.subTest(step=step):
                self.assertEqual(self._next(f"1. {step} More follows."), step)

        # What is not a route's label.
        self.assertEqual(self._next("### Primary route options compared\n\n1. Build a pilot line. Then scale."),
                         "Build a pilot line.", "a sub-heading that only mentions a route")
        self.assertEqual(self._next("### Primary commercialization route\n\n### Alternatives\n\n- A full line of vehicles."),
                         "A full line of vehicles.", "a route sub-heading with nothing under it hands on to what follows")
        self.assertEqual(self._next("1. Build a pilot line. Then scale.\n2. **Route:** direct sales to utilities."),
                         "Build a pilot line.", "a bare 'Route:' further down is one entry's detail")
        self.assertEqual(self._next("1. Route selection should wait for the pilot data. More."),
                         "Route selection should wait for the pilot data.")
        self.assertEqual(self._next("1. Build a pilot line. Then scale.\n2. Primary route selection should wait for the pilot data."),
                         "Build a pilot line.", "a sentence that opens with the words is not labelled as the route")
        # A statement of what the section is does not become the route by standing under its sub-heading.
        self.assertEqual(self._next("### Primary commercialization route\n\n**Assessment mode: orientation.** No context.\n\n"
                                    "1. License the process to cell makers. Then scale."),
                         "License the process to cell makers.")
        elsewhere = self._brief(markdown=(
            "## Executive Summary\n\nShort.\n\n## 4. Target Industries\n\n### Primary Commercialization Route: Wrong place\n\n"
            "## 5. Commercialization Opportunities & Recommendations\n\n1. Build a pilot line. Then scale.\n"))["brief"]
        self.assertEqual(elsewhere["next"], "Build a pilot line.", "only the recommendations section is read")
        # A table row or a quotation under a route sub-heading is not the route.
        self.assertEqual(self._next("### Primary commercialization route\n\n| Route | Fit |\n|---|---|\n| Licensing | High |\n\n"
                                    "> Quoted remark.\n\nLicense the process to cell makers. Then scale."),
                         "License the process to cell makers.")

    def test_the_summary_line_is_about_the_technology_not_about_the_report(self):
        """The brief quotes the executive summary's first sentence that is not
        about the report. Of the 88 saved reports made since October 2026, 21
        showed a sentence about the report instead and one showed nothing
        (2026-11-13): an opener the rule did not know ("This orientation brief
        synthesizes…"), a statement of the assessment mode standing second, a
        first paragraph with nothing else in it, and a summary written as a
        list. The forms below are the ones those reports use."""
        finding = "The technology is moving from early clinical adoption to procedure-specific optimization."
        # An opener that names the report by another word, or with a word in between.
        for opener in (
            "This orientation brief synthesizes findings from academic research, patent analysis, and market intelligence.",
            "This orientation assessment evaluates the commercialization potential based on a validated registry.",
            "This orientation report synthesizes validated academic, patent, and market intelligence regarding SBSP.",
            "This is an orientation brief built from three small, validated evidence registries: academic, patent and market.",
            "This commercialization assessment covers three evidence registries.",
        ):
            with self.subTest(opener=opener):
                self.assertEqual(self._summary(f"{opener} {finding} More follows."), finding)
        # The mode, stated as the sentence after the opener.
        for mode in (
            "It is an orientation-mode assessment: no actor-specific decision context was supplied, so GO/NO_GO is not assessed.",
            "It is an orientation-mode brief: no actor-specific GO/NO_GO decision is assessed.",
            "It is written in orientation mode: no actor-specific decision context was supplied.",
            "No actor-specific decision context was supplied, so **actor-specific GO/NO_GO is not assessed**.",
            "Conclusions are provisional because the evidence is abstract-, snippet- and market-report-level.",
            "The report is an evidence-linked orientation brief, not a recommendation for any particular investor.",
        ):
            with self.subTest(mode=mode):
                self.assertEqual(self._summary(
                    f"This report synthesizes three validated evidence registries. {mode} {finding} More follows."), finding)

        # A first paragraph with nothing but the report in it: the next one is read.
        self.assertEqual(self._summary(
            "This report synthesizes three validated evidence registries — academic [A1, A2], patent [P1] and market [M1] — "
            "into an orientation brief. It is an orientation-mode assessment: no decision context was supplied.\n\n"
            f"{finding} In gynecologic applications, outcomes are comparable [A1]."), finding)
        self.assertEqual(self._summary(
            "本报告基于三个已校验的证据报告（学术文献 A1–A7、专利记录 P1–P8）编制，对特高压直流输电技术的商业化前景进行定向评估。"
            "**本报告处于定向（orientation）模式，未评估任何特定主体的 GO/NO_GO 决策。**\n\n主要判断如下：\n\n"
            "- **技术成熟度**：特高压直流输电已是运行中的大规模技术 [A1]。但成熟度判断属分析者推断。\n- **市场**：其余从略。"),
            "技术成熟度：特高压直流输电已是运行中的大规模技术。")
        for mode in ("需要明确的是，本报告处于**方向性指导模式（orientation mode）**，未针对任何特定决策主体进行GO/NO_GO评估。",
                     "评估模式为**方向性指导（orientation）**，未对任何特定参与者进行GO/NO_GO决策评估。"):
            with self.subTest(mode=mode):
                self.assertEqual(self._summary(
                    f"本报告基于经过验证的学术研究、专利分析与市场情报数据，对量子密钥分发网络的商业化前景进行综合评估。{mode}"
                    "当前证据表明，QKD网络正处于从点对点实验链路向多层级网络过渡的阶段。其余从略。"),
                    "当前证据表明，QKD网络正处于从点对点实验链路向多层级网络过渡的阶段。")
        # A paragraph that states the mode under its own label is about the mode to its end.
        self.assertEqual(self._summary(
            "**Assessment Mode:** Orientation. General next steps are identified, but they are not a recommendation.\n\n"
            f"{finding} More follows."), finding)

        # A summary written as a list. The first point states the mode; the next
        # one's bold title is the heading of its first sentence, so both are quoted.
        points = ("- **Assessment mode: orientation.** No actor-specific decision context was supplied, so GO/NO_GO is not "
                  "assessed. The report is an evidence-linked orientation brief, not a recommendation.\n"
                  "- **Maturity is uneven across sub-fields.** Reviews describe RAS as having transformed surgical practice "
                  "[A2][A6]. Reconstructive microsurgery is described as maturing.\n"
                  "- **Patent evidence is thin.** Eight records, with snippet-level evidence only.")
        self.assertEqual(self._summary(points),
                         "Maturity is uneven across sub-fields. Reviews describe RAS as having transformed surgical practice.")
        self.assertEqual(self._summary(
            "This is an orientation brief built from three small registries. No actor-specific decision context was supplied.\n\n"
            "- **Maturity is uneven.** Robotic-assisted surgery (RAS) appears established in gynecologic applications. More.\n"
            "- **Persistent barriers** include high installation and maintenance costs [A1]."),
            "Maturity is uneven. Robotic-assisted surgery (RAS) appears established in gynecologic applications.")
        self.assertEqual(self._summary(
            "核心发现如下：\n\n- **市场机遇明确但尚处早期。** 美国BCI市场正处于关键转折点 [A6]。其余从略。\n- **其余从略。**"),
            "市场机遇明确但尚处早期。美国BCI市场正处于关键转折点。")
        # A point that is one sentence, or opens with a long one, is quoted as it stands.
        self.assertEqual(self._summary("1. Solid-state cells are early [A1]. Pilot lines exist.\n2. More."), "Solid-state cells are early.")
        self.assertEqual(self._summary("- **Persistent barriers** include high installation and maintenance costs [A1]. More."),
                         "Persistent barriers include high installation and maintenance costs.")
        self.assertEqual(self._summary("- **Maturity is uneven.**\n- **Patents are thin.** Eight records only."), "Maturity is uneven.")
        long_title = "The incumbent position is strong across every high-volume specialty that the registry covers today."
        self.assertEqual(self._summary(f"- **{long_title}** One report relays 3.1 million procedures."), long_title)
        # A plain paragraph before the list is still read first.
        self.assertEqual(self._summary(f"{finding}\n\n- **Maturity is uneven.** RAS appears established."), finding)

        # What is not read: a sub-heading, a quotation, a table row, a line that only leads in.
        self.assertEqual(self._summary(
            "### Overview\n\n> Quoted remark about the field.\n\n| Field | State |\n|---|---|\n| Urology | Mature |\n\n"
            f"Key findings:\n\n{finding} More."), finding)
        # A summary with nothing but the report in it still shows its first sentence.
        only = "This orientation brief synthesizes validated academic, patent, and market intelligence regarding hyperloop."
        self.assertEqual(self._summary(f"{only} It is an orientation-mode assessment: no decision context was supplied."), only)
        self.assertIsNone(self._summary("- **Assessment mode: orientation.** No decision context was supplied."))
        # That fallback is the first paragraph's, not a later one's and not a list item's.
        self.assertEqual(self._summary(f"{only}\n\nIt is an orientation-mode assessment: no decision context was supplied."), only)
        self.assertIsNone(self._summary(f"- {only}\n- It is an orientation-mode assessment: no decision context was supplied."))
        # Only the executive summary is read, wherever it stands in the report.
        placed = self._brief(markdown=(
            "## 1. Technology Overview & Maturity\n\nThe incumbent is commercially available today.\n\n"
            f"## Executive Summary\n\n{only} {finding}\n\n## Evidence Limitations\n\nSources are sparse.\n"))["brief"]
        self.assertEqual(placed["summary"], finding)
        # A long sentence is cut at a word, and so is a title with the sentence it heads.
        long_finding = ("The technology is moving from early clinical adoption to procedure-specific optimization, "
                        + "with platform diversification beyond the incumbent in urology, gynecology and general surgery, " * 3
                        + "and more.")
        cut = self._summary(f"{only} {long_finding}")
        self.assertTrue(cut.endswith("…") and 200 < len(cut) <= 240 and long_finding.startswith(cut[:-1]), cut)
        self.assertRegex(long_finding[len(cut) - 1:], r"^[\s,;:]", "the cut falls between words")
        joined = self._summary(f"- **Maturity is uneven.** {long_finding}")
        self.assertTrue(joined.startswith("Maturity is uneven. The technology is moving") and joined.endswith("…")
                        and len(joined) <= 240, joined)
        # Sentences that only share a word with the rules are findings.
        for kept in ("The brief window before the core patents expire favours licensing.",
                     "It is an established modality in urology.",
                     "This is a mature technology in gynecologic surgery.",
                     "No actor has yet shipped a commercial system.",
                     "Conclusions from two randomized trials favour the robotic approach.",
                     "Assessment of 30 trials shows comparable outcomes.",
                     "评估结果显示该技术已进入示范阶段。"):
            with self.subTest(kept=kept):
                self.assertEqual(self._summary(f"{kept} More follows."), kept)

    def _summary(self, paragraph):
        return self._brief(markdown=f"## Executive Summary\n\n{paragraph}\n")["brief"]["summary"]

    def test_a_full_stop_inside_a_number_or_an_abbreviation_does_not_end_the_sentence(self):
        """Every full stop used to end a sentence. Over the 193 saved runs with
        a scorecard (2026-11-12) that cut 33 of the 374 brief lines short: the
        summary 14 times, 12 of them inside a number ("...a global market
        estimated at USD 5,206."), and the first step 19 times. The forms below
        are the ones those reports use."""
        # Inside a number: a decimal point has no space after it.
        self.assertEqual(
            self._summary("The market is estimated at USD 5,206.15 million in 2025 [M1]. However, none is approved."),
            "The market is estimated at USD 5,206.15 million in 2025.")
        self.assertEqual(self._summary("司美格鲁肽在2025年占据最大的收入份额，达52.83%，市场集中。其余从略。"),
                         "司美格鲁肽在2025年占据最大的收入份额，达52.83%，市场集中。")
        self.assertEqual(self._summary("超薄陶瓷电解质膜（25微米厚Li₀.₃₄La₀.₅₆TiO₃）已有报道。其余从略。"),
                         "超薄陶瓷电解质膜（25微米厚Li₀.₃₄La₀.₅₆TiO₃）已有报道。")
        # Inside an abbreviation, whatever follows it.
        shipped = "Oxford PV began commercial sale, shipping to a U.S.-based customer in September 2024."
        self.assertEqual(self._summary(f"{shipped} This milestone matters."), shipped)
        agency = "The device was cleared by the U.S. Food and Drug Administration in 2023."
        self.assertEqual(self._summary(f"{agency} Sales followed."), agency)
        interface = "The preferred route is the non-penetrating cortical interface (e.g., thin-film arrays or stentrodes)."
        self.assertEqual(self._next(f"1. {interface} It avoids surgery."), interface)
        named = "License the subsystem tools (e.g. Toyota's degradation models) to equipment makers."
        self.assertEqual(self._next(f"1. {named} Then scale."), named)
        enabling = "Sell cost-of-ownership enablement for established platforms, i.e., products that improve their economics."
        self.assertEqual(self._next(f"1. {enabling} More follows."), enabling)
        against = "Position the cell on cycle life vs. the incumbent lithium iron phosphate chemistry."
        self.assertEqual(self._next(f"1. {against} More follows."), against)
        numbered = "File a continuation of U.S. Patent No. 5 before the grace period ends."
        self.assertEqual(self._next(f"1. {numbered} More follows."), numbered)
        # Each abbreviation the rule names, before a capitalised word, where
        # nothing but the name keeps the sentence whole.
        for abbreviation in ("e.g.", "i.e.", "vs.", "cf.", "et al.", "approx.", "ca.", "Dr.", "Inc.", "Ltd.",
                             "Corp.", "Co.", "No.", "Nos.", "Fig.", "Figs.", "U.S.", "U.K."):
            with self.subTest(abbreviation=abbreviation):
                whole = f"Compare the cell design {abbreviation} Zeta Works before scaling."
                self.assertEqual(self._next(f"1. {whole} More follows."), whole)
        # A closing quotation mark or bracket belongs to the sentence it closes.
        corridors = 'Target the fixed regional "green corridors."'
        self.assertEqual(self._next(f"1. {corridors} This route is preferred."), corridors)
        self.assertEqual(self._next("1. 首选路线是与电网公司合作（见下文。）其余从略。"), "首选路线是与电网公司合作（见下文。）")
        # A heading's own number or letter is not a sentence: "A." alone was
        # the first step of seven runs.
        self.assertEqual(self._next("**A. 短期（0-2年）：聚焦已产生收入的先行者**\n\n其余从略。"),
                         "A. 短期（0-2年）：聚焦已产生收入的先行者")
        self.assertEqual(self._next("**1. Build a pilot line with a partner.** Semi-solid first."),
                         "1. Build a pilot line with a partner.")

    def test_a_full_stop_that_does_end_a_sentence_still_does(self):
        """What the rule above must not swallow. Where it cannot tell, it keeps
        the two sentences together and the length limit trims them; it never
        cuts inside one."""
        for text, first in (
            ("Build a pilot line. Then scale.", "Build a pilot line."),
            # A sentence that ends on a number, before one that starts with one.
            ("Costs fell by half in 2024. 15 firms now ship cells.", "Costs fell by half in 2024."),
            # Before a word that only looks lowercase.
            ("Start with the cancer vaccine. mRNA platforms follow.", "Start with the cancer vaccine."),
            ("Sell films, coatings, etc. The margins differ.", "Sell films, coatings, etc."),
            ("Is the market ready? Not yet.", "Is the market ready?"),
            ("Raise a Series A. Investors expect it.", "Raise a Series A."),
            # One word is a sentence; only a heading's single letter or number is not.
            ("Partner. Do not build alone.", "Partner."),
            # A word that merely ends like an abbreviation ("ca.", "co.").
            ("Enter North America. The margins differ.", "Enter North America."),
            ("建议与电网公司合作开发。其余从略。", "建议与电网公司合作开发。"),
            # "No" is a word as well as an abbreviation.
            ("The answer is no. 15 firms tried.", "The answer is no."),
        ):
            with self.subTest(text=text):
                self.assertEqual(self._next(f"1. {text}"), first)
        # An abbreviation that goes on in lower case does not end the sentence.
        self.assertEqual(self._next("1. Sell films, coatings, etc. and license the process. More follows."),
                         "Sell films, coatings, etc. and license the process.")

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
        self.assertEqual(shown["note"], "取自本次评估自己的评分卡、报告和检查结果，不产生额外费用；每一行都能在下方打开。")
        english = self._run(brief={"scores": _SCORES, "markdown": _REPORT, "sources": _SOURCES,
                                   "progress": _PROGRESS})["brief_view"]
        self.assertEqual(english["note"], "Drawn from this assessment's own scorecard, report and checks, "
                                          "at no extra cost. Every line can be opened below.")
        # Under "what would change this verdict": the figures may not measure
        # the same thing, which is as much as the run established.
        market = next(text for reason, text in shown["changers"] if reason == "market")
        self.assertEqual(market, "同一口径的市场规模数据：现有数字口径可能不一，无法直接比较。")
        self.assertEqual(next(text for reason, text in english["changers"] if reason == "market"),
                         "Market figures that measure the same thing: the ones collected may not, "
                         "so they cannot be compared directly.")


class ScoreSummaryTests(unittest.TestCase):
    """The landing shows what a finished assessment looks like. It was a
    picture of a scorecard; it is now the scorecard of one sample, drawn by
    the function that draws a run's: the verdict and the five bars, without
    the reasons, the market note and the risks, which belong to someone
    reading that report and are one click away on its sample page."""

    @classmethod
    def setUpClass(cls):
        ResultReadabilityTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run(self, **payload):
        return ResultReadabilityTests._run(self, **payload)

    # The glucose-monitoring sample's scores, with what the full card adds.
    _SCORES = {"overall_score": 74.0, "trl_score": 9, "mrl_score": 9, "patent_strength": 3,
               "market_accessibility": 3.5, "evidence_confidence": 4,
               "trl_rationale": "Cleared devices are on the market [A1].", "trl_source_ids": ["A1"],
               "mrl_rationale": "Produced at volume [M2].",
               "market_uncertainty": "high (91× spread: 0.058–5.3 bn USD)",
               "key_risks": ["Reimbursement differs by country."], "key_opportunities": ["Non-invasive sensing."]}

    def test_the_summary_is_the_verdict_and_the_five_bars_of_the_full_card(self):
        seen = self._run(summary=self._SCORES)
        summary, full = seen["summary"], seen["full"]
        self.assertEqual(summary["classes"], "scorecard scorecard--summary")
        self.assertEqual(full["classes"], "scorecard")
        # The same verdict in the same colour as the card a run shows, and as a sample's card says.
        for part in ("tone", "value", "denom", "band"):
            self.assertEqual(summary[part], full[part], part)
        self.assertEqual((summary["value"], summary["denom"], summary["band"], summary["tone"]),
                         ("74.0", "/ 100", "Strong", "success"))
        self.assertEqual([row[:3] for row in summary["rows"]], [
            ["Technology readiness", "9 / 9", "100%"], ["Manufacturing readiness", "9 / 10", "90%"],
            ["Patent position", "3 / 5", "60%"], ["Market accessibility", "3.5 / 5", "70%"],
            ["Evidence confidence", "4 / 5", "80%"]])
        self.assertEqual([row[:3] for row in summary["rows"]], [row[:3] for row in full["rows"]])
        # What it leaves out: the reasons, their citations, the market note, the risks.
        self.assertEqual((summary["folds"], summary["cites"], summary["notes"]), (0, 0, 0))
        self.assertTrue(all(row[3] == 3 for row in summary["rows"]), "a row is its label, bar and figure")
        self.assertGreaterEqual(full["folds"], 3)
        self.assertGreaterEqual(full["notes"], 1)

    def test_the_summary_is_said_in_the_readers_language_and_grade(self):
        zh = self._run(summary={**self._SCORES, "overall_score": 48.6}, language="Simplified Chinese")["summary"]
        self.assertEqual((zh["value"], zh["band"], zh["tone"]), ("48.6", "早期", "warning"))
        self.assertEqual(zh["rows"][0][0], "技术就绪度")

    def test_a_dimension_that_cannot_be_read_is_a_dash_and_nothing_more(self):
        summary = self._run(summary={**self._SCORES, "mrl_score": 0, "patent_strength": "3"})["summary"]
        self.assertEqual([row[1:] for row in summary["rows"][1:3]], [["—", "0%", 3], ["—", "0%", 3]])
        self.assertEqual(summary["rows"][0][1], "9 / 9")

    def test_without_a_readable_verdict_there_is_no_summary(self):
        """The landing then says one line of its own; a card reading
        "detail unavailable" is for someone who has a run to ask about."""
        for scores in (None, [], "74", {}, {"overall_score": None}, {"overall_score": "74"}, {"overall_score": 101},
                       {"overall_score": -1}, {"overall_score": True}, {"trl_score": 9}):
            with self.subTest(scores=scores):
                self.assertIsNone(self._run(summary=scores)["summary"])
        self.assertIsNotNone(self._run(summary={"overall_score": 0})["summary"], "a score of zero is a score")


class ReviewerNotesTests(unittest.TestCase):
    """A delivered report ends with the reviewer's notes: what the automatic
    proofreading changed and what it could not. They are a record, written
    for whoever audits the run: "Rule 6", "Not applied (exact target absent):
    Correction 9: Removed trailing space before the period". The page showed
    them as the report's last section, at full size. Of 1,783 saved reports
    (2026-11-13), 602 of the saved reports and drafts carry the section. 310
    say "No corrections required."; in 138 every entry opens "Applied:" or
    "Not applied", as the code that writes them has done since August (973
    and 78 entries); 154 are older, written by the model, and their entries
    include "No citation mismatches found", which is not a change. None mixes
    the two. On the web the section is folded under one line: a count of
    what was and was not applied where every entry says which, and a count
    of notes where they do not. Unfolded, every word is as saved. The saved
    file is not touched."""

    @classmethod
    def setUpClass(cls):
        ResultReadabilityTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run(self, **payload):
        return ResultReadabilityTests._run(self, **payload)

    _BODY = "## Executive Summary\n\nShort [A1].\n\n## References\n\n[A1] A paper. Published: 2024-01-01.\n"

    def _html(self, notes, language=None, heading="## Reviewer Notes", after=""):
        extra = {"language": language} if language else {}
        return self._run(render=f"{self._BODY}\n{heading}\n\n{notes}\n{after}", **extra)["html"]

    def _summary(self, notes, language=None):
        html = self._html(notes, language)
        found = re.search(r'<h2>Reviewer Notes</h2>\n<details class="reviewer-notes"><summary>([^<]*)</summary>', html)
        self.assertIsNotNone(found, html[-400:])
        return found[1]

    def test_the_notes_are_folded_under_a_count_of_what_was_and_was_not_applied(self):
        notes = ("- Applied: Changed \"will enable\" to \"could enable\" in Section 1 [A1].\n"
                 "- Applied: Removed an empty citation bracket.\n"
                 "- Not applied (exact target absent): Correction 9: Removed trailing space before the period.")
        html = self._html(notes)
        self.assertEqual(self._summary(notes), "Automatic proofreading: 2 corrections applied, 1 not applied.")
        fold = html[html.index('<details class="reviewer-notes">'):]
        self.assertTrue(fold.rstrip().endswith("</details>"), "the fold runs to the end of the report")
        self.assertNotIn(" open", fold[:40], "folded until the reader opens it")
        # Unfolded, every entry is there as saved, its citation still a chip.
        for words in ("Applied: Changed &quot;will enable&quot; to &quot;could enable&quot; in Section 1",
                      "Applied: Removed an empty citation bracket.",
                      "Not applied (exact target absent): Correction 9: Removed trailing space before the period."):
            self.assertIn(words, fold)
        self.assertEqual(fold.count("<li>"), 3)
        self.assertIn('class="cite"', fold)
        # The heading stays outside, so the contents list still links the section.
        self.assertEqual(html.count("<h2>"), 3)
        self.assertLess(html.index("<h2>Reviewer Notes</h2>"), html.index("<details"))
        # Everything before the notes is rendered as it would be without them.
        self.assertTrue(html.startswith(self._run(render=self._BODY)["html"].rstrip()))

    def test_the_count_is_said_in_the_readers_words_in_both_languages(self):
        applied, skipped = "- Applied: One.", "- Not applied (exact target absent): Two."
        cases = (
            (applied, "Automatic proofreading: 1 correction applied.", "自动校对：采纳了 1 处修改。"),
            ("\n".join([applied] * 12), "Automatic proofreading: 12 corrections applied.", "自动校对：采纳了 12 处修改。"),
            (skipped, "Automatic proofreading: 1 not applied.", "自动校对：1 处未采纳。"),
            ("\n".join([applied, skipped, skipped]), "Automatic proofreading: 1 correction applied, 2 not applied.",
             "自动校对：采纳了 1 处修改，2 处未采纳。"),
            ("No corrections required.", "Automatic proofreading: no corrections were needed.", "自动校对：没有需要修改的地方。"),
            ("All corrections were applied silently in the report text above.", "Automatic proofreading notes.", "自动校对说明。"),
        )
        for notes, english, chinese in cases:
            with self.subTest(notes=notes[:30]):
                self.assertEqual(self._summary(notes), english)
                self.assertEqual(self._summary(notes, "Simplified Chinese"), chinese)

    def test_older_notes_that_do_not_say_what_was_applied_are_counted_as_notes(self):
        """Reports from July 2026 number their notes and name the rule, and
        some entries report that nothing was wrong. Calling each one a
        correction that was applied would say more than the notes do."""
        notes = ("All corrections were applied silently in the report text above. The following changes were made:\n\n"
                 "1. **Rule 2 – Unsupported numerical claim:** Added the citation on the same line.\n"
                 "2. **Rule 3 – Overconfident language:** Changed \"projected to reach\" to \"could reach\".\n"
                 "   - A nested remark that is part of entry two.\n"
                 "* No citation mismatches (Rule 1) were found.")
        self.assertEqual(self._summary(notes), "Automatic proofreading: 3 notes.")
        self.assertEqual(self._summary(notes, "Simplified Chinese"), "自动校对：3 条记录。")
        self.assertEqual(self._summary("1) Section 2: removed a duplicate citation."), "Automatic proofreading: 1 note.")
        html = self._html(notes)
        for words in ("Rule 2 – Unsupported numerical claim:", "Rule 3 – Overconfident language:", "(Rule 1) were found."):
            self.assertIn(words, html[html.index("<details"):])
        # One entry that does not say which, among entries that do: still notes.
        mixed = "- Applied: One.\n- Not applied (exact target absent): Two.\n- Checked the tables."
        self.assertEqual(self._summary(mixed), "Automatic proofreading: 3 notes.")
        # The words are read as written: bold, or a different case, is the same statement.
        self.assertEqual(self._summary("- **Applied:** One.\n* **Not applied** (absent): Two."),
                         "Automatic proofreading: 1 correction applied, 1 not applied.")
        self.assertEqual(self._summary("- applied: One.\n- NOT APPLIED (absent): Two.\n- APPLIED : Three."),
                         "Automatic proofreading: 2 corrections applied, 1 not applied.")
        # "Applied" has to be the entry's own opening word, followed by its colon.
        self.assertEqual(self._summary("- Applied research was renamed.\n- Applied: One."), "Automatic proofreading: 2 notes.")
        # Something other than the one sentence the pipeline writes is not "nothing needed".
        self.assertEqual(self._summary("No corrections required.\n\nSee the plan."), "Automatic proofreading notes.")

    def test_printing_unfolds_the_notes_and_folds_them_again(self):
        """A folded section prints as its summary alone, and paper has nothing
        to click. The notes are unfolded for the print and folded again after
        it; one the reader had opened stays open."""
        seen = self._run(print=True)["print"]
        self.assertEqual(seen["heard"], {"beforeprint": 1, "afterprint": 1})
        self.assertEqual(seen["printing"], [True, True])
        self.assertEqual(seen["printing_twice"], [True, True])
        self.assertEqual(seen["after"], [True, False])
        self.assertEqual(seen["marks"], [0, 0], "nothing is left on the page afterwards")
        self.assertEqual(seen["after_twice"], [True, False])

    def test_only_the_section_itself_is_folded(self):
        plain = self._run(render=self._BODY)["html"]
        self.assertNotIn("<details", plain, "a report without the section has no fold")
        for heading in ("### Reviewer Notes", "## Reviewer Notes on scope", "## Notes", "Reviewer Notes"):
            with self.subTest(heading=heading):
                self.assertNotIn("<details", self._html("- Applied: One.", heading=heading))
        # A section after the notes, which no saved report has, would stay outside the fold.
        html = self._html("- Applied: One.", after="\n## Appendix\n\nMore.\n")
        self.assertLess(html.index("</details>"), html.index("<h2>Appendix</h2>"))
        self.assertIn("<p>More.</p>", html[html.index("</details>"):])
        # A sub-heading inside the notes is part of them, not the end of the fold.
        inside = self._html("- Applied: One.\n\n### Not applied\n\n- Not applied (exact target absent): Two.")
        self.assertTrue(inside.rstrip().endswith("</details>"))
        self.assertLess(inside.index("<details"), inside.index("<h3>Not applied</h3>"))
        self.assertIn("1 correction applied, 1 not applied", inside)
        # Two such sections: the last one is the reviewer's, as the pipeline reads it.
        twice = self._html("- Applied: One.", after="\n## Reviewer Notes\n\n- Applied: Two.\n- Applied: Three.\n")
        self.assertEqual(twice.count("<details"), 1)
        self.assertIn("2 corrections applied", twice)

    def test_what_a_note_says_is_escaped_like_the_rest_of_the_report(self):
        html = self._html("- Applied: Removed <script>alert(1)</script> and <img src=x onerror=alert(1)>.")
        self.assertNotIn("<script", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertEqual(self._summary("- Applied: <b>x</b>"), "Automatic proofreading: 1 correction applied.")


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
        "deferred (site share: yahoo.com already holds 2): 'A third release'",
        "duplicate story (same address as the copy at finance.yahoo.com): 'A release'",
        "duplicate story (same headline); the copy at www.prnewswire.com replaces the one at "
        "finance.yahoo.com: 'A release: with a colon'",
        "duplicate story (mirror as the copy at www.congress.gov): 'A report'",
        "encyclopedia entry is not market evidence: 'Topic - Wikipedia'",
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
            "暂缓（yahoo.com 已占 2 条市场来源）：'A third release'",
            "同一篇稿件（同一文章地址，已收录 finance.yahoo.com 上的那一份）：'A release'",
            "同一篇稿件（同一标题）；改用 www.prnewswire.com 上的那一份，替换 finance.yahoo.com 上的："
            "'A release: with a colon'",
            "同一篇稿件（整篇转载，已收录 www.congress.gov 上的那一份）：'A report'",
            "百科条目不作为市场证据：'Topic - Wikipedia'",
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
