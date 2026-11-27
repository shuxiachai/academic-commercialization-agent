"""The failed-run page of an academic source shortfall, in both languages.

Seen on 2026-11-27 on run 20261125T014549Z-7d39…, "passive daytime radiative
cooling coatings for warehouse roofs": the header said 2 of 3 sources were
retained and offered one button, "Edit topic and retry"; the query audit
showed [OA-Recent] and [OA-Cited] each at "32 candidates · 4 accepted" with
nothing between those eight and the two kept; and above the tabs sat a
"Scope of this assessment" box and "No saved sources artifact is listed for
this run; no source read was requested." on a run that never wrote a report.
The same topic, run again unchanged, collected eight academic sources.

Run through Node against the shipped run.js, result.js and i18n.js.
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
_JS = _REPO / "web" / "static" / "js"

_HARNESS = r"""
import fs from "node:fs";
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
class Node {
  constructor(tag) { Object.assign(this, { tagName: tag.toUpperCase(), children: [], dataset: {}, attributes: {},
    style: {}, className: "", textContent: "", open: false, title: "", type: "", hidden: false,
    scrollLeft: 0, scrollWidth: 0, clientWidth: 0, classList: { add() {}, remove() {}, toggle() {} } }); }
  append(...items) { for (const item of items) this.children.push(typeof item === "string" ? { text: item } : item); }
  setAttribute(name, value) { this.attributes[name] = value; }
  replaceChildren(...items) { this.children = []; this.append(...items); }
  addEventListener(type, heard) { (this.listeners ??= {})[type] = heard; }
  get childNodes() { return this.children; }
  set innerHTML(value) { if (value === "") this.children = []; }
  remove() {}
  replaceWith() {}
  querySelector(selector) {
    const viewMatch = selector.match(/\[data-view="([^"]+)"\]/);
    return viewMatch ? flat(this).find(n => n.dataset?.view === viewMatch[1]) ?? null : null;
  }
  querySelectorAll() { return []; }
}
globalThis.window = { addEventListener() {} };
globalThis.document = { createElement: (tag) => new Node(tag), createTextNode: (text) => ({ text }),
  querySelectorAll: () => [], documentElement: {} };
const flat = (node) => [node, ...(node.children ?? []).flatMap(flat)];
const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const i18n = await import("./i18n.js");
if (input.language) i18n.setLanguage(input.language);
const run = await import("./run.mjs");
const result = await import("./result.mjs");
const out = {};
if (input.outcome) out.outcome = run.outcomeSummary(input.outcome);
if (input.panel) {
  const nodes = flat(result.renderRetrievalDiagnostics(input.panel.data, input.panel.shortfall));
  const texts = (cls) => nodes.filter(n => n.className === cls).map(n => n.textContent);
  out.panel = {
    flow: texts("retrieval-flow__line"),
    removed: texts("retrieval-flow__item"),
    // Each audit row's own counts line; the "Rejected candidates" label shares the class.
    summaries: texts("source__meta").filter(text => text.includes(" · ")),
  };
}
if (input.render) {
  globalThis.__stubApi = {
    getArtifact: async (_runId, kind) => (kind === "retrieval" ? input.render.retrieval : null),
    getReport: async () => "",
    getDecision: async () => undefined,
    getFeedback: async () => ({}),
  };
  const root = new Node("div");
  await result.render(root, input.render.progress.run_id, input.render.progress);
  await new Promise(r => setTimeout(r, 0));
  out.render = {
    top: root.children.map(n => n.className),
    flow: flat(root).filter(n => n.className === "retrieval-flow__line").map(n => n.textContent),
  };
}
if (input.keys) out.keys = Object.fromEntries(input.keys.map(key => [key, i18n.t(key)]));
process.stdout.write(JSON.stringify(out));
"""


def _node() -> str | None:
    return shutil.which("node")


# The production failure's counts as the API now reads them from its audit.
_SHORTFALL = {
    "stage": "academic_relevance_filter", "accepted_sources": 2, "required_sources": 3,
    "passed_sources": 8, "filter_removed": 6, "filter_removed_off_setting": 6, "abstract_unavailable": 7,
}
_FAILED = {
    "state": "failed", "error_code": "insufficient_evidence",
    "error": "academic relevance filtering retained 2 validated sources; at least 3 are required.",
    "artifacts": ["retrieval"], "retrieval_shortfall": _SHORTFALL,
}


def _diagnostics(*, setting_terms=None) -> dict:
    thin = [f"abstract too thin (0 chars): 'On-topic coating paper {i}'" for i in range(7)]
    data = {
        "version": 1, "stage": "academic_relevance_filter",
        "input_topic": "仓库屋顶用被动辐射制冷涂层", "search_topic": "PDRC coatings for warehouse roofs",
        "aliases": [], "accepted_sources": 2, "required_sources": 3,
        "audit": [
            {"domain": "academic", "query": "[OA-Recent] PDRC coatings for warehouse roofs", "result_count": 32,
             "accepted_source_ids": ["A1", "A2", "A3", "A4"], "rejected_reasons": thin},
            {"domain": "academic", "query": "[OA-Cited] PDRC coatings for warehouse roofs", "result_count": 32,
             "accepted_source_ids": ["A5", "A6", "A7", "A8"], "rejected_reasons": []},
            {"domain": "academic", "query": "[Relevance-Filter]", "result_count": 0, "accepted_source_ids": [],
             "rejected_reasons": [
                 *(f"score=-1 (min=3) — removed 'Removed paper {i}'" for i in range(5)),
                 "score=2 (min=3) — removed 'Weak paper'",
             ]},
            {"domain": "academic", "query": "[Relaxed-Title-Gate] PDRC coatings for warehouse roofs",
             "result_count": 64, "accepted_source_ids": [], "rejected_reasons": []},
        ],
    }
    if setting_terms is not None:
        data["setting_terms"] = setting_terms
    return data


@unittest.skipUnless(_node(), "node not installed")
class AcademicShortfallPageTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        work = Path(cls._tmp.name)
        run = (_JS / "run.js").read_text(encoding="utf-8").replace('import * as api from "./api.js";', "const api = {};")
        (work / "run.mjs").write_text(run, encoding="utf-8")
        result = (_JS / "result.js").read_text(encoding="utf-8").replace(
            'import * as api from "./api.js";',
            "const api = new Proxy({}, { get: (_, prop) => globalThis.__stubApi?.[prop] });")
        (work / "result.mjs").write_text(result, encoding="utf-8")
        shutil.copy2(_JS / "i18n.js", work / "i18n.js")
        (work / "harness.mjs").write_text(textwrap.dedent(_HARNESS), encoding="utf-8")
        cls._work = work

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run(self, **payload):
        (self._work / "input.json").write_text(json.dumps(payload), encoding="utf-8")
        done = subprocess.run(
            [_node(), str(self._work / "harness.mjs"), str(self._work / "input.json")],
            capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=self._work,
        )
        self.assertEqual(done.returncode, 0, done.stderr[:1200])
        return json.loads(done.stdout)

    # ── The header's reason ───────────────────────────────────────────

    def test_the_header_names_what_final_filtering_removed(self):
        """The header used to stop at "2 retained, minimum 3"; the reason for the
        six removed is what tells an owner the topic itself was not wrong."""
        self.assertEqual(
            self._run(outcome={**_FAILED, "daily_charge": "charged"})["outcome"],
            "Academic sources fell short after final filtering (2 retained, minimum 3). "
            "The 6 papers it removed made no mention of the setting named in the topic. "
            "The assessment stopped before a report was written. This run counted toward today's quota.")
        self.assertEqual(
            self._run(language="Simplified Chinese", outcome={**_FAILED, "daily_charge": "charged"})["outcome"],
            "最终筛选后保留了 2 条学术来源，至少需要 3 条。被筛掉的 6 篇论文没有提到题目里的使用场景。"
            "评估在写报告前停止。 本次运行已计入今日额度。")

    def test_low_scores_and_mixed_removals_are_said_as_they_are(self):
        low = {**_SHORTFALL, "filter_removed": 1, "filter_removed_off_setting": 0}
        mixed = {**_SHORTFALL, "filter_removed_off_setting": 4}
        cases = (
            (None, low, "The 1 paper it removed scored too low for relevance to the topic."),
            (None, mixed, "Of the 6 papers it removed, 4 made no mention of the setting named in the topic."),
            ("Simplified Chinese", low, "被筛掉的 1 篇论文与题目的相关度不够。"),
            ("Simplified Chinese", mixed, "被筛掉的 6 篇论文中，有 4 篇没有提到题目里的使用场景。"),
        )
        for language, shortfall, sentence in cases:
            with self.subTest(language=language, shortfall=shortfall):
                outcome = self._run(language=language, outcome={**_FAILED, "retrieval_shortfall": shortfall})
                self.assertIn(sentence, outcome["outcome"])

    def test_missing_abstracts_are_the_reason_only_where_they_cut_the_count(self):
        """Before final filtering every acceptable paper was taken, so seven
        papers without an abstract are seven fewer sources. After it, the
        queries had already filled their slots: the abstracts were not why."""
        early = {**_SHORTFALL, "stage": "academic_validation", "accepted_sources": 1, "passed_sources": 1,
                 "filter_removed": 0, "filter_removed_off_setting": 0}
        self.assertEqual(
            self._run(outcome={**_FAILED, "retrieval_shortfall": early})["outcome"],
            "Academic sources fell short after validation (1 passed, minimum 3). "
            "7 more papers with on-topic titles could not be used because no usable abstract was available. "
            "The assessment stopped before a report was written.")
        self.assertEqual(
            self._run(language="Simplified Chinese", outcome={**_FAILED, "retrieval_shortfall": early})["outcome"],
            "有 1 条学术来源通过验证，至少需要 3 条。另有 7 篇标题对题的论文因为拿不到摘要没有采用。评估在写报告前停止。")
        self.assertNotIn("abstract", self._run(outcome=_FAILED)["outcome"])
        one = {**early, "abstract_unavailable": 1}
        self.assertIn("1 more paper with an on-topic title could not be used",
                      self._run(outcome={**_FAILED, "retrieval_shortfall": one})["outcome"])

    def test_unknown_tallies_add_nothing(self):
        """An audit the API could not read leaves the reason as #506 left it."""
        unknown = {**_SHORTFALL, **dict.fromkeys(
            ("passed_sources", "filter_removed", "filter_removed_off_setting", "abstract_unavailable"))}
        self.assertEqual(
            self._run(outcome={**_FAILED, "retrieval_shortfall": unknown})["outcome"],
            "Academic sources fell short after final filtering (2 retained, minimum 3). "
            "The assessment stopped before a report was written.")
        for bad in (-1, 1.5, "6", True):
            with self.subTest(bad=bad):
                shortfall = {**_SHORTFALL, "filter_removed": bad}
                self.assertNotIn("removed", self._run(outcome={**_FAILED, "retrieval_shortfall": shortfall})["outcome"])

    # ── The retrieval tab: from passed to kept ────────────────────────

    def test_the_panel_reconciles_passed_removed_and_kept(self):
        shown = self._run(panel={"data": _diagnostics(setting_terms=["roofs", "warehouse"]),
                                 "shortfall": _SHORTFALL})["panel"]
        self.assertEqual(shown["flow"], [
            "The queries passed 8 academic papers; final filtering removed 6; 2 remained (3 needed).",
            "Removed by final filtering:",
            "7 more papers with on-topic titles were not used because no usable abstract was available; "
            "the query audit below lists them.",
        ])
        self.assertEqual(shown["removed"], [
            *(f"Removed paper {i} — no mention of the topic's setting (roofs, warehouse)" for i in range(5)),
            "Weak paper — relevance 2, below 3",
        ])
        # Each query row counts its own candidates; a filter row is not a query.
        self.assertEqual(shown["summaries"][:3], [
            "Academic · 32 candidates · 4 accepted",
            "Academic · 32 candidates · 4 accepted",
            "Academic · final filtering removed 6",
        ])
        self.assertEqual(shown["summaries"][-1], "Academic · rechecked 64 candidates the other queries fetched · 0 accepted")

    def test_the_panel_in_chinese(self):
        shown = self._run(language="Simplified Chinese",
                          panel={"data": _diagnostics(setting_terms=["roofs", "warehouse"]), "shortfall": _SHORTFALL})["panel"]
        self.assertEqual(shown["flow"], [
            "各查询共通过 8 篇学术论文；最终筛选去掉 6 篇；保留 2 篇（至少需要 3 篇）。",
            "最终筛选去掉的论文：",
            "另有 7 篇标题对题的论文因为拿不到摘要没有采用，见下方查询审计。",
        ])
        self.assertEqual(shown["removed"][0], "Removed paper 0 —— 没有提到题目里的使用场景（roofs、warehouse）")
        self.assertEqual(shown["removed"][-1], "Weak paper —— 相关度 2，低于 3")
        self.assertEqual(shown["summaries"][2], "学术 · 最终筛选去掉 6 篇")
        self.assertEqual(shown["summaries"][-1], "学术 · 复查其他查询取回的 64 个候选 · 0 个通过")

    def test_an_old_run_without_setting_words_and_counts_that_do_not_add_up(self):
        """Runs saved before this change have no setting words; a tally that does
        not add up is shown as three facts, never as a chain it is not."""
        off = self._run(panel={"data": _diagnostics(), "shortfall": {**_SHORTFALL, "passed_sources": 9}})["panel"]
        self.assertEqual(off["flow"][0],
                         "The queries passed 9 academic papers; final filtering removed 6; 2 remained (3 needed). "
                         "These do not add up: the audit does not record every step between them.")
        self.assertEqual(off["removed"][0], "Removed paper 0 — no mention of the topic's setting")
        none = self._run(panel={"data": _diagnostics(), "shortfall": None})["panel"]
        self.assertEqual(none["flow"], ["Removed by final filtering:"])

    # ── Above the tabs, on a run with no report ───────────────────────

    def _render(self, progress, language=None):
        return self._run(language=language, render={"progress": {"run_id": "r1", **progress},
                                                     "retrieval": _diagnostics()})["render"]

    _GATE = {"mode": "decision_support", "go_no_go_allowed": True,
             "threshold_provenance": {"status": "not_established"}}

    def test_a_run_without_a_report_shows_no_scope_box_and_no_sources_note(self):
        shown = self._render({**_FAILED, "decision_gate": self._GATE})
        self.assertNotIn("decision-applicability", shown["top"])
        self.assertNotIn("empty-note sources__missing", shown["top"])
        self.assertEqual(shown["flow"][0],
                         "The queries passed 8 academic papers; final filtering removed 6; 2 remained (3 needed).")

    def test_a_report_keeps_both(self):
        shown = self._render({"state": "completed", "artifacts": ["report", "scores"], "decision_gate": self._GATE})
        self.assertIn("decision-applicability", shown["top"])
        self.assertIn("empty-note sources__missing", shown["top"])

    # ── The two ways to try again ─────────────────────────────────────

    def test_both_retry_buttons_are_named_in_both_languages(self):
        keys = ["run_retry_same", "run_retry_same_title", "run_again_edit_topic"]
        self.assertEqual(self._run(keys=keys)["keys"], {
            "run_retry_same": "Retry with the same topic",
            "run_retry_same_title": "Fill the form with the same topic and decision context. "
                                    "The new assessment starts only when you start it.",
            "run_again_edit_topic": "Edit the topic",
        })
        self.assertEqual(self._run(language="Simplified Chinese", keys=keys)["keys"], {
            "run_retry_same": "按原题重试",
            "run_retry_same_title": "用相同的题目和决策场景填好表单；你确认开始后才会发起新的评估。",
            "run_again_edit_topic": "调整题目",
        })

    def test_the_failed_page_offers_both_buttons_and_retry_reads_the_topic_again(self):
        """The wiring in app.js, read from its source: a shortfall gets the
        same-topic retry as the main button and the edit beside it, not behind
        More; the retry fills the form and asks for a free reading of the
        topic where the deployment offers one, and starts nothing paid."""
        source = (_JS / "app.js").read_text(encoding="utf-8")
        self.assertIn('retry.id = "run-retry";', source)
        self.assertIn('t("run_retry_same")', source)
        self.assertIn("if (previewApplies()) $(\"#compose-form\").requestSubmit();", source)
        self.assertIn("actions.append(retry, again);", source)
