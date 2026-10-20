"""The browser's BYOK credentials: chosen model, Tavily or Serper, old tabs.

Run through Node against the shipped api.js so the assertions exercise the
real client. Skipped when Node is unavailable; CI has it.
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

from academic_agent import llm_config
from api.models import BYOK_PROVIDERS

_WEB = Path(__file__).resolve().parents[1] / "web" / "static" / "js"

_HARNESS = textwrap.dedent("""
    const store = new Map();
    globalThis.sessionStorage = {
      getItem: k => store.has(k) ? store.get(k) : null,
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: k => store.delete(k),
    };
    globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
    const api = await import("./api.mjs");
    const out = {};
    const attempt = (name, fn) => {
      try { out[name] = { ok: true, value: fn() }; }
      catch (e) { out[name] = { ok: false, code: e.code ?? String(e) }; }
    };
    const current = { provider: "qwen", llmKey: "k", search: "tavily", searchKey: "t", model: "qwen3.7-plus" };
    attempt("store_current", () => { api.setByok(current); return api.getByok(); });
    attempt("body_current", () => api.byokBody(api.getByok()));
    attempt("body_serper", () => api.byokBody({ provider: "openai", llmKey: "k", search: "serper", searchKey: "s" }));
    const legacy = { provider: "deepseek", llmKey: "k", serperKey: "s" };
    attempt("store_legacy", () => { api.setByok(legacy); return api.getByok(); });
    attempt("body_legacy", () => api.byokBody(api.getByok()));
    for (const [name, creds] of Object.entries({
      mixed: { provider: "qwen", llmKey: "k", search: "tavily", searchKey: "t", serperKey: "s" },
      no_search_key: { provider: "qwen", llmKey: "k", search: "tavily", searchKey: " " },
      bad_search: { provider: "qwen", llmKey: "k", search: "google", searchKey: "t" },
      bad_model: { provider: "qwen", llmKey: "k", search: "tavily", searchKey: "t", model: "../evil" },
      legacy_with_model: { provider: "qwen", llmKey: "k", serperKey: "s", model: "qwen3.7-plus" },
    })) attempt("reject_" + name, () => api.setByok(creds));
    attempt("payer_kept", () => api.getByok());
    console.log(JSON.stringify(out));
""")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ByokClientTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "api.mjs").write_text((_WEB / "api.js").read_text(encoding="utf-8"), encoding="utf-8")
            (work / "run.mjs").write_text(_HARNESS, encoding="utf-8")
            result = subprocess.run([shutil.which("node"), str(work / "run.mjs")], cwd=work,
                                    capture_output=True, text=True, encoding="utf-8", timeout=300)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:500])
        cls.out = json.loads(result.stdout)

    def test_current_shape_is_stored_as_given(self):
        self.assertTrue(self.out["store_current"]["ok"])
        self.assertEqual(self.out["store_current"]["value"]["model"], "qwen3.7-plus")

    def test_current_shape_sends_the_model_and_the_chosen_search_key(self):
        self.assertEqual(self.out["body_current"]["value"], {
            "llm_provider": "qwen", "llm_api_key": "k", "tavily_api_key": "t", "llm_model": "qwen3.7-plus"})
        self.assertEqual(self.out["body_serper"]["value"], {
            "llm_provider": "openai", "llm_api_key": "k", "serper_api_key": "s"})

    def test_an_earlier_tab_shape_still_works_unchanged(self):
        """A tab opened before this change holds {serperKey}."""
        self.assertEqual(self.out["store_legacy"]["value"],
                         {"provider": "deepseek", "llmKey": "k", "serperKey": "s"})
        self.assertEqual(self.out["body_legacy"]["value"], {
            "llm_provider": "deepseek", "llm_api_key": "k", "serper_api_key": "s"})

    def test_mixed_partial_or_malformed_credentials_are_invalid_not_absent(self):
        for name in ("mixed", "no_search_key", "bad_search", "bad_model", "legacy_with_model"):
            with self.subTest(name=name):
                self.assertFalse(self.out["reject_" + name]["ok"])
                self.assertEqual(self.out["reject_" + name]["code"], "invalid_byok")

    def test_a_rejected_change_keeps_the_previous_payer(self):
        self.assertEqual(self.out["payer_kept"]["value"]["serperKey"], "s")


class RequiredModelTests(unittest.TestCase):

    def test_the_form_requires_a_model_and_only_suggests_one(self):
        """No default model anywhere: the field is required, the example a hint."""
        self.assertFalse(hasattr(llm_config, "DEFAULT_MODELS"))
        source = (_WEB / "byok_fields.js").read_text(encoding="utf-8")
        self.assertNotIn("DEFAULT_MODELS", source)
        block = re.search(r"MODEL_EXAMPLES = \{(.*?)\};", source, re.S).group(1)
        self.assertEqual(set(re.findall(r"(\w+):\s*\"[^\"]+\"", block)), set(BYOK_PROVIDERS))
        index = (_WEB.parents[1] / "index.html").read_text(encoding="utf-8")
        self.assertRegex(index, r'<input[^>]*id="byok-model"[^>]*\srequired\b')
        app = (_WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("if (!llmKey || !model || !searchKey) return;", app)

    def test_the_browser_model_check_matches_the_server_pattern(self):
        from academic_agent.llm_config import BYOK_MODEL_PATTERN

        source = (_WEB / "api.js").read_text(encoding="utf-8")
        browser = re.search(r"const BYOK_MODEL = /\^(.*?)\$/;", source).group(1)
        self.assertEqual(browser, BYOK_MODEL_PATTERN.pattern)
