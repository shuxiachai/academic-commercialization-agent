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
const input = JSON.parse(process.argv[2]);
if (input.language) i18n.setLanguage?.(input.language);
const out = {};
if (input.markdown !== undefined) out.index = Object.fromEntries(mod.citationIndex(input.markdown));
if (input.scores) {
  const nodes = flat(mod._testRenderScorecard(input.scores));
  out.why = nodes.filter(n => n.className === "dim__why").map(n => ({
    summary: n.children[0].textContent, rationale: n.children[1].textContent,
    cites: flat(n).filter(c => c.className === "cite").map(c => c.dataset.cite) }));
  const caveat = nodes.find(n => (n.className ?? "").includes("scorecard__market-caveat"));
  out.caveat = { tag: caveat.tagName, open: caveat.open };
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
        (work / "result.mjs").write_text(source, encoding="utf-8")
        shutil.copy2(_I18N_JS, work / "i18n.js")
        (work / "harness.mjs").write_text(textwrap.dedent(_HARNESS), encoding="utf-8")
        cls._work = work

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _run(self, **payload):
        result = subprocess.run(
            [shutil.which("node"), str(self._work / "harness.mjs"), json.dumps(payload)],
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

    def test_the_market_disclosure_folds_unless_the_cap_moved_the_score(self):
        caveat = self._run(scores={"overall_score": 50, "market_accessibility": 3})["caveat"]
        self.assertEqual(caveat, {"tag": "DETAILS", "open": False})

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

    def test_a_support_label_without_permission_is_not_upgraded(self):
        gate = {"mode": "decision_support", "go_no_go_allowed": False,
                "threshold_provenance": {"status": "owner_approved"}}
        text = self._run(gate=gate)["scope"]["text"][0]
        self.assertIn("is not assessed", text)
        self.assertNotIn("allows a GO/NO_GO", text)


if __name__ == "__main__":
    unittest.main()
