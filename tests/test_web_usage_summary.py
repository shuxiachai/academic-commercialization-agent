"""Tests for how the client renders a run's token and cost figures.

Run through Node against the shipped run.js, for the same reason the markdown
tests are: a Python transcription of the formatting would pass while the file
users actually load was broken.

The server is careful to say "cost unknown" rather than "$0.00" (see
token_usage.py). That care is worth nothing if the client renders the unknown
as a zero anyway, so the assertions here are about the same distinction one
layer up: an unpriced run must show its tokens and no dollar figure, and a
partial total must not be presented as a total.
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
_RUN_JS = _REPO / "web" / "static" / "js" / "run.js"
_I18N_JS = _REPO / "web" / "static" / "js" / "i18n.js"


def _node() -> str | None:
    return shutil.which("node")


@unittest.skipUnless(_node(), "node not installed")
class UsageSummaryTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        work = Path(cls._tmp.name)

        # api.js reaches the network and i18n.js touches localStorage, neither
        # of which resolves outside a browser. Stubbing the imports keeps the
        # formatting code itself untouched.
        source = _RUN_JS.read_text(encoding="utf-8")
        source = source.replace('import * as api from "./api.js";', "const api = {};")
        (work / "run.mjs").write_text(source, encoding="utf-8")
        shutil.copy2(_I18N_JS, work / "i18n.js")

        # i18n.js reads the stored language at import time. Dynamic import so
        # the shim is installed first -- a static import is hoisted above it
        # and the module crashes before the stub exists. Returning null also
        # pins the interface to its English default, so the assertions below
        # do not depend on whatever language a developer last selected.
        (work / "harness.mjs").write_text(textwrap.dedent("""
            globalThis.localStorage = { getItem: () => null, setItem: () => {} };
            const { usageSummary, usageTitle } = await import("./run.mjs");
            const usage = JSON.parse(process.argv[2]);
            console.log(JSON.stringify({
                summary: usageSummary(usage),
                title: usageTitle(usage),
            }));
        """), encoding="utf-8")
        cls._work = work

        # Cold-start cost paid here, not inside whichever test sorts first.
        # See test_web_markdown.py for the failure this prevents.
        warm = subprocess.run(
            [_node(), str(work / "harness.mjs"), "null"],
            capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=work,
        )
        if warm.returncode != 0:
            raise RuntimeError(f"run.js failed to load: {warm.stderr[:400]}")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _render(self, usage) -> dict:
        result = subprocess.run(
            [_node(), str(self._work / "harness.mjs"), json.dumps(usage)],
            capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=self._work,
        )
        if result.returncode != 0:
            self.fail(f"harness failed: {result.stderr[:400]}")
        return json.loads(result.stdout)

    def test_priced_run_shows_tokens_and_cost(self):
        out = self._render({
            "total_tokens": 12_345, "cost_usd": 0.0123, "cost_complete": True,
            "price_basis": "built-in table (as of 2026-05)", "agents": [],
        })
        self.assertIn("12.3k", out["summary"])
        self.assertIn("$0.0123", out["summary"])

    def test_unpriced_run_shows_tokens_and_no_dollar_figure(self):
        """The server said cost is unknown. Rendering that as $0.00 would put
        the lie back in at the last possible moment."""
        out = self._render({
            "total_tokens": 900, "cost_usd": None, "cost_complete": False,
            "unpriced_models": ["model-from-the-future"], "agents": [],
        })
        self.assertIn("900", out["summary"])
        self.assertNotIn("$", out["summary"])

    def test_partial_total_is_marked_approximate(self):
        out = self._render({
            "total_tokens": 5000, "cost_usd": 0.01, "cost_complete": False,
            "unpriced_models": ["mystery-model"], "agents": [],
        })
        self.assertIn("~$0.01", out["summary"])
        self.assertIn("mystery-model", out["title"])

    def test_tooltip_carries_the_price_basis(self):
        """A cost with no stated basis cannot be judged for staleness."""
        out = self._render({
            "total_tokens": 5000, "cost_usd": 0.01, "cost_complete": True,
            "price_basis": "built-in table (as of 2026-05)", "agents": [],
        })
        self.assertIn("2026-05", out["title"])

    def test_tooltip_breaks_down_by_agent(self):
        out = self._render({
            "total_tokens": 300, "cost_usd": 0.02, "cost_complete": True,
            "price_basis": "x",
            "agents": [
                {"role": "Academic", "total_tokens": 100, "cost_usd": 0.005},
                {"role": "Patent", "total_tokens": 200, "cost_usd": 0.015},
            ],
        })
        self.assertIn("Academic", out["title"])
        self.assertIn("$0.0150", out["title"])

    def test_agent_without_a_price_shows_a_dash_not_a_zero(self):
        out = self._render({
            "total_tokens": 100, "cost_usd": None, "cost_complete": False,
            "agents": [{"role": "Academic", "total_tokens": 100, "cost_usd": None}],
        })
        self.assertIn("—", out["title"])
        self.assertNotIn("$0.0000", out["title"])

    def test_absent_or_empty_usage_renders_nothing(self):
        """Runs that predate this feature, and runs that died before the crew
        started, both arrive with no usage at all."""
        for usage in (None, {}, {"total_tokens": 0}):
            with self.subTest(usage=usage):
                self.assertEqual(self._render(usage)["summary"], "")


@unittest.skipUnless(_node(), "node not installed")
class LocaleParityTests(unittest.TestCase):
    """Every key the English table defines must exist in the Chinese one.

    i18n.js falls back to English for a missing key, so the failure is not a
    bare identifier in the interface — it is a Chinese page with an English
    phrase in it, which nobody reports as a bug and nobody notices in review.
    """

    def test_locales_define_the_same_keys(self):
        # STRINGS is module-private and the module touches localStorage on
        # import, so the table is read by evaluating just the literal rather
        # than by exporting it purely for a test's benefit.
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "parse.mjs").write_text(textwrap.dedent("""
                import { readFileSync } from "node:fs";
                const src = readFileSync(process.argv[2], "utf-8");
                const start = src.indexOf("const STRINGS = {");
                const end = src.indexOf("\\n};", start);
                const literal = src.slice(start + "const STRINGS =".length, end + 2);
                const table = new Function(`return ${literal}`)();
                console.log(JSON.stringify(Object.fromEntries(
                    Object.entries(table).map(([lang, v]) => [lang, Object.keys(v)])
                )));
            """), encoding="utf-8")
            result = subprocess.run(
                [_node(), str(work / "parse.mjs"), str(_I18N_JS)],
                capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=work,
            )
            self.assertEqual(result.returncode, 0, result.stderr[:400])

        keys = json.loads(result.stdout)
        self.assertGreaterEqual(len(keys), 2, f"expected several locales, got {list(keys)}")
        # English is the source language per the module's own header, and the
        # locales are named in full ("English", "Simplified Chinese") because
        # those strings are also what the language picker displays.
        source = "English"
        self.assertIn(source, keys)
        self.assertGreater(len(keys[source]), 50, "parsed table looks truncated")

        # Compared against every other locale rather than a hardcoded second
        # one, so adding a third language is covered the day it lands.
        for locale, defined in keys.items():
            if locale == source:
                continue
            with self.subTest(locale=locale):
                self.assertFalse(
                    set(keys[source]) - set(defined),
                    f"untranslated: {sorted(set(keys[source]) - set(defined))}")
                self.assertFalse(
                    set(defined) - set(keys[source]),
                    f"defined only in {locale}: {sorted(set(defined) - set(keys[source]))}")


@unittest.skipUnless(_node(), "node not installed")
class GroundingPanelTests(unittest.TestCase):
    """The panel exists so a reader learns what was *not* verified.

    The server is careful to keep "figure absent from the source" and "no
    source text to check against" apart, and the whole chain is wasted if the
    last step renders a large unverifiable count as if it were a pass. These
    assertions are about that presentation, run through the shipped result.js
    rather than a transcription of it.
    """

    _RESULT_JS = _REPO / "web" / "static" / "js" / "result.js"

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        work = Path(cls._tmp.name)

        source = cls._RESULT_JS.read_text(encoding="utf-8")
        source = source.replace('import * as api from "./api.js";', "const api = {};")
        (work / "result.mjs").write_text(source, encoding="utf-8")
        shutil.copy2(_I18N_JS, work / "i18n.js")

        # renderGrounding is exported for this, as renderMarkdown already is
        # in the same module. The DOM stub is thin enough to record what was
        # built without pulling in a browser.
        (work / "harness.mjs").write_text(textwrap.dedent("""
            globalThis.localStorage = { getItem: () => null, setItem: () => {} };

            function makeNode(tag) {
                const node = {
                    tagName: tag, className: "", textContent: "", hidden: false,
                    dataset: {}, children: [], innerHTML: "",
                    append(...kids) { this.children.push(...kids); },
                    addEventListener() {},
                    querySelector() { return makeNode("div"); },
                };
                return node;
            }
            globalThis.document = { createElement: makeNode };

            const { renderGrounding } = await import("./result.mjs");
            const node = renderGrounding(JSON.parse(process.argv[2]));

            function flatten(n, out = []) {
                out.push({ cls: n.className || "", text: n.textContent || "" });
                for (const kid of n.children || []) flatten(kid, out);
                return out;
            }
            console.log(JSON.stringify(flatten(node)));
        """), encoding="utf-8")
        cls._work = work

        warm = subprocess.run(
            [_node(), str(work / "harness.mjs"), '{"checked":0}'],
            capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=work,
        )
        if warm.returncode != 0:
            raise RuntimeError(f"result.js failed to load: {warm.stderr[:500]}")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _render(self, data) -> list[dict]:
        result = subprocess.run(
            [_node(), str(self._work / "harness.mjs"), json.dumps(data)],
            capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=self._work,
        )
        if result.returncode != 0:
            self.fail(f"harness failed: {result.stderr[:400]}")
        return json.loads(result.stdout)

    def _texts(self, nodes) -> str:
        return " | ".join(n["text"] for n in nodes if n["text"])

    def test_all_three_counts_are_shown_together(self):
        """A reader given only "0 unsupported" would conclude the report was
        verified, when in this run almost nothing could be checked."""
        nodes = self._render({"checked": 2, "ungrounded": 0, "unverifiable": 205})
        text = self._texts(nodes)
        for value in ("2", "0", "205"):
            with self.subTest(value=value):
                self.assertIn(value, text)

    def test_an_ungrounded_finding_is_marked(self):
        nodes = self._render({
            "checked": 1, "ungrounded": 1, "unverifiable": 0,
            "findings": [{"domain": "academic", "finding_id": "AF1",
                          "status": "ungrounded", "claim": "efficiency reached 26.1%",
                          "ungrounded_figures": ["26.1"]}],
        })
        classes = " ".join(n["cls"] for n in nodes)
        self.assertIn("grounding__item--ungrounded", classes)
        self.assertIn("26.1", self._texts(nodes))

    def test_an_unverifiable_finding_states_why(self):
        """Not styled or worded as a failure: the source text was missing, not
        contradictory, and conflating the two is the error this whole feature
        is built to avoid."""
        nodes = self._render({
            "checked": 0, "ungrounded": 0, "unverifiable": 1,
            "findings": [{"domain": "market", "finding_id": "MF1",
                          "status": "unverifiable", "claim": "the market reached $12.5bn",
                          "unverifiable_reason": "every cited source carries only a "
                                                 "search snippet"}],
        })
        classes = " ".join(n["cls"] for n in nodes)
        self.assertNotIn("grounding__item--ungrounded", classes)
        self.assertIn("search snippet", self._texts(nodes))

    def test_per_domain_breakdown_is_rendered(self):
        nodes = self._render({
            "checked": 2, "ungrounded": 0, "unverifiable": 3,
            "by_domain": {
                "academic": {"checked": 2, "ungrounded": 0, "unverifiable": 0},
                "market": {"checked": 0, "ungrounded": 0, "unverifiable": 3},
            },
        })
        text = self._texts(nodes)
        self.assertIn("2/2", text)
        self.assertIn("0/3", text)

    def test_a_clean_run_renders_without_a_detail_list(self):
        """Everything grounded means no rows; the panel should still show the
        counts rather than an empty list."""
        nodes = self._render({"checked": 5, "ungrounded": 0, "unverifiable": 0,
                              "findings": []})
        classes = " ".join(n["cls"] for n in nodes)
        self.assertIn("grounding__stats", classes)
        self.assertNotIn("grounding__list", classes)
