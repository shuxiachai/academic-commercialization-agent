"""What a person who was sent a link is shown when there is nothing at it.

A shared link is how a report travels: a technology transfer office or an
investor forwards it to a colleague. Measured on https://academic-agent.cc on
2026-11-21:

- An address that is no page (``/pricing``) was answered 404 with the bare
  JSON ``{"detail":"Not Found"}`` and a tab with no title, in a browser as to
  a script.
- A link to a run that is gone (deleted by its owner, past the deployment's
  retention, or cut short when it was copied) opened the run page with "…",
  "UNKNOWN" and "— · Usage & cost" in its header and one small line under it:
  "The server could not find this run. Automatic polling has stopped."

These hold the server's half: a browser that asks for a page at an address
that matches no route gets the site's own 404 page, in both languages and
still with status 404, and everything else keeps the answer it had. The run
page's half is in tests/js/landing_contract.mjs (the scenarios named in
tests/test_landing_page.py) and in e2e/browser_smoke.py.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import access, crawlers
from api import main as api_main
from api.main import app

_ROOT = Path(__file__).resolve().parents[1]
_PAGE = _ROOT / "web" / "not_found.html"
_MODULE = _ROOT / "web" / "static" / "js" / "not_found.js"
# What Chromium sends when the address bar is used: a document is asked for.
_BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"}
_SECURITY = {name.lower(): value for name, value in api_main._SECURITY_HEADERS.items()}
_A_RUN = "20260101T000000Z-" + "0" * 32


class _Gated(unittest.TestCase):
    """As the public deployment is: gated, and asked by someone with no code."""

    def setUp(self):
        self._code = patch.object(access, "ACCESS_CODE", "secret123")
        self._code.start()
        self.addCleanup(self._code.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)


class BrowserNotFoundPageTests(_Gated):

    def test_a_browser_asking_for_a_page_that_is_not_there_gets_the_sites_404_page(self):
        for path in ("/pricing", "/run/", "/samples/hyperloop/extra", "/about/team"):
            with self.subTest(path=path):
                response = self.client.get(path, headers=_BROWSER)
                self.assertEqual(response.status_code, 404, "Still a 404 to the browser and to a crawler")
                self.assertTrue(response.headers["content-type"].startswith("text/html"))
                self.assertEqual(response.text, _PAGE.read_text(encoding="utf-8"), "The committed page, as it is")

    def test_the_page_names_itself_in_both_languages_and_leads_home_and_to_the_samples(self):
        page = _PAGE.read_text(encoding="utf-8")
        self.assertRegex(page, r"<title>[^<]*Academic Commercialization Assessment</title>")
        self.assertIn('lang="en" data-lang-block="en"', page)
        self.assertIn('lang="zh-CN" data-lang-block="zh"', page)
        self.assertIn("Page not found", page)
        self.assertIn("找不到这个页面", page)
        # Both ways on, in both blocks, and the brand back to the home page.
        self.assertEqual(page.count('href="/samples"'), 2)
        self.assertEqual(page.count('href="/"'), 3)
        # Never kept or shown as a result: the tag in the page, and the header (below) with it.
        self.assertIn('<meta name="robots" content="noindex, nofollow">', page)
        self.assertNotIn("polling", page.lower())

    def test_it_carries_the_security_headers_and_says_noindex(self):
        response = self.client.get("/pricing", headers=_BROWSER)
        self.assertEqual({name: response.headers.get(name) for name in _SECURITY}, _SECURITY)
        self.assertEqual(response.headers.get("x-robots-tag"), crawlers.NOINDEX)

    def test_head_is_answered_as_the_get_is(self):
        response = self.client.head("/pricing", headers=_BROWSER)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response.headers["content-type"].startswith("text/html"))
        self.assertEqual(response.headers.get("x-robots-tag"), crawlers.NOINDEX)

    def test_its_script_and_styles_are_files_the_server_has(self):
        page = _PAGE.read_text(encoding="utf-8")
        assets = re.findall(r'(?:src|href)="(/static/[^"]+)"', page)
        self.assertIn("/static/js/not_found.js", assets)
        for asset in assets:
            with self.subTest(asset=asset):
                self.assertEqual(self.client.get(asset).status_code, 200)
        # A module the page loads is one the production smoke allows (AGENTS.md conventions).
        smoke = (_ROOT / "e2e" / "source_locator_production_smoke.py").read_text(encoding="utf-8")
        self.assertIn('"not_found"', smoke)
        # It reads nothing from the server: a page about a wrong address asks for no more of them.
        module = _MODULE.read_text(encoding="utf-8")
        self.assertNotIn("fetch(", module)


class EverythingElseKeepsItsAnswerTests(_Gated):

    def test_a_client_that_did_not_ask_for_a_page_still_gets_json(self):
        for headers in ({"Accept": "application/json"}, {"Accept": "*/*"}, {}):
            with self.subTest(headers=headers):
                response = self.client.get("/pricing", headers=headers)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": "Not Found"})

    def test_nothing_under_api_turns_into_a_page(self):
        # Without a code the gate still answers first, as it did: the address
        # says nothing about whether such an endpoint exists.
        refused = self.client.get("/api/pricing", headers=_BROWSER)
        self.assertEqual(refused.status_code, 401)
        self.assertTrue(refused.headers["content-type"].startswith("application/json"))
        known = self.client.get("/api/runs", headers=_BROWSER)
        self.assertEqual(known.status_code, 401, "...and answers an endpoint that exists the same way")
        # With a code, a wrong /api/ address is the JSON 404 it always was.
        response = self.client.get("/api/pricing", headers={**_BROWSER, "X-Access-Code": "secret123"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Not Found"})

    def test_a_404_an_endpoint_gives_keeps_its_own_words(self):
        """Only an address no route matches is a missing page. A run that is
        not there is the run page's to say (it reads this JSON); the API's
        own 404s keep their detail."""
        response = self.client.get(f"/api/runs/{_A_RUN}/progress", headers=_BROWSER)
        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.json())
        self.assertNotEqual(response.json(), {"detail": "Not Found"})
        # A run's page is the run page, whether or not the run exists.
        page = self.client.get(f"/run/{_A_RUN}", headers=_BROWSER)
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="run-gone"', page.text)

    def test_a_missing_file_under_static_is_answered_as_before(self):
        response = self.client.get("/static/js/not-a-module.js", headers=_BROWSER)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Not Found"})

    def test_health_robots_and_the_sitemap_are_untouched(self):
        health = self.client.get("/health", headers=_BROWSER)
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.headers["content-type"].startswith("application/json"))
        robots = self.client.get("/robots.txt", headers=_BROWSER)
        self.assertEqual(robots.status_code, 200)
        self.assertTrue(robots.headers["content-type"].startswith("text/plain"))
        sitemap = self.client.get("/sitemap.xml", headers=_BROWSER)
        self.assertEqual(sitemap.status_code, 200)
        self.assertTrue(sitemap.headers["content-type"].startswith("application/xml"))

    def test_a_wrong_method_is_still_a_405(self):
        self.assertEqual(self.client.post("/privacy", headers=_BROWSER).status_code, 405)


def _strings(path: Path, key: str) -> list[str]:
    """Every value written for `key` in a strings table: one per language."""
    text = path.read_text(encoding="utf-8")
    return re.findall(rf'^\s*{re.escape(key)}: "((?:[^"\\]|\\.)*)"', text, flags=re.M)


class WordingTests(unittest.TestCase):
    """The sentences a reader of a gone or shared run is shown, in both languages."""

    I18N = _ROOT / "web" / "static" / "js" / "i18n.js"
    RUN = _ROOT / "web" / "static" / "js" / "run.js"

    def test_the_gone_page_is_said_in_both_languages(self):
        keys = ("gone_title", "gone_lede", "gone_deleted", "gone_retention_days", "gone_retention",
                "gone_link", "gone_samples", "gone_own")
        for key in keys:
            with self.subTest(key=key):
                values = _strings(self.I18N, key)
                self.assertEqual(len(values), 2, "English and Chinese")
                self.assertTrue(re.search(r"[一-鿿]", values[1]), "The second is the Chinese one")
                for value in values:
                    self.assertNotIn("polling", value.lower())
                    self.assertNotIn("UNKNOWN", value)
        english, chinese = _strings(self.I18N, "gone_retention_days")
        self.assertIn("{days}", english)
        self.assertIn("{days}", chinese)

    def test_the_gone_page_offers_the_samples_and_an_assessment_of_ones_own(self):
        index = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        block = index[index.index('id="run-gone"'):index.index('id="run-body"')]
        self.assertIn('<a class="btn btn--primary" id="run-gone-samples" href="/samples" data-i18n="gone_samples">', block)
        self.assertIn('<a class="btn btn--secondary" id="run-gone-own" href="/" data-i18n="gone_own">', block)
        for key in ("gone_title", "gone_lede", "gone_deleted", "gone_link"):
            self.assertIn(f'data-i18n="{key}"', block)

    def test_the_polling_sentence_is_gone_from_the_page(self):
        self.assertEqual(_strings(self.I18N, "run_connection_missing"), [])
        self.assertNotIn("run_connection_missing", (_ROOT / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8"))

    def test_the_readers_header_is_said_in_both_languages(self):
        keys = ("reader_assessed", "reader_started", "reader_assessed_range", "reader_started_range",
                "reader_dates_title", "reader_model", "reader_took", "reader_took_all", "reader_ran",
                "reader_ran_all", "reader_running", "reader_running_all")
        for key in keys:
            with self.subTest(key=key):
                values = _strings(self.RUN, key)
                self.assertEqual(len(values), 2, "English and Chinese")
                self.assertTrue(re.search(r"[一-鿿]", values[1]))
                for value in values:
                    self.assertNotIn("console", value)
                    self.assertNotIn("token", value.lower())


# ── In Node: the reader's header in both languages, and the 404 page's script ──

_JS = _ROOT / "web" / "static" / "js"

_READER_HARNESS = """
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
globalThis.document = { querySelectorAll: () => [], documentElement: {} };
const run = await import("./run.mjs");
const i18n = await import("./i18n.js");
const out = JSON.parse(process.argv[2]).map(([language, facts]) => {
  i18n.setLanguage(language);
  const view = run.readerHeader(facts);
  return [view.assessed, view.title, view.model, view.seconds === null ? null : run.readerTime(view.timeKey, view.seconds)];
});
console.log(JSON.stringify(out));
"""

_NOT_FOUND_HARNESS = """
const store = new Map();
globalThis.localStorage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
class Node {
  constructor(dataset = {}) { Object.assign(this, { dataset, hidden: false, textContent: "", listeners: {}, value: "" }); }
  addEventListener(type, handler) { this.listeners[type] = handler; }
  setAttribute(name, value) { this[name] = value; }
}
const blocks = [new Node({ langBlock: "en" }), new Node({ langBlock: "zh" })];
const select = new Node();
globalThis.document = {
  title: "", documentElement: {},
  querySelector: (selector) => (selector === "#ui-lang" ? select : null),
  querySelectorAll: (selector) => (selector === "[data-lang-block]" ? blocks : []),
};
await import("./not_found.js");
const state = () => [document.title, document.documentElement.lang, blocks.map((b) => b.hidden), select.value];
const first = state();
select.value = "Simplified Chinese";
select.listeners.change();
const switched = [...state(), store.get("ui-language")];
console.log(JSON.stringify([first, switched]));
"""


def _node(tmp_path: Path, harness: str, files: dict[str, str], *args: str) -> object:
    node = shutil.which("node")
    assert node, "Node is required for the page's scripts"
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "harness.mjs").write_text(harness, encoding="utf-8")
    # A zone far from UTC, where a run started late on a UTC day is already the next day.
    env = {**os.environ, "TZ": "Pacific/Kiritimati"}
    done = subprocess.run([node, "harness.mjs", *args], capture_output=True, text=True, encoding="utf-8",
                          cwd=tmp_path, env=env)
    assert done.returncode == 0, done.stderr or done.stdout
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_readers_header_says_the_same_in_both_languages_and_its_dates_in_utc(tmp_path):
    run_js = (_JS / "run.js").read_text(encoding="utf-8").replace('import * as api from "./api.js";', "const api = {};")
    files = {"run.mjs": run_js, "i18n.js": (_JS / "i18n.js").read_text(encoding="utf-8")}
    # Started at 23:30 UTC on 20 November: already the 21st where this runs.
    late = "20261120T233000Z-" + "a" * 32
    resume = {
        "run_id": late, "state": "completed", "llm_model": "qwen3.8-2.4t-a95b", "elapsed_seconds": 237,
        "recovery": {"state": "reused", "source_run_id": "20261118T120000Z-" + "b" * 32},
        "lineage": {"earlier": [{"run_id": "20261118T120000Z-" + "b" * 32, "record": "available"}],
                    "combined": {"elapsed_seconds": 1768, "elapsed_complete": True}},
    }
    plain = {"run_id": late, "state": "completed", "llm_model": "qwen3.8-2.4t-a95b", "elapsed_seconds": 237}
    going = {**plain, "state": "running", "elapsed_seconds": 75}
    cases = [[language, facts] for language in ("English", "Simplified Chinese") for facts in (resume, plain, going)]
    assert _node(tmp_path, _READER_HARNESS, files, json.dumps(cases)) == [
        ["Assessed 18 Nov 2026 – 20 Nov 2026", "Dates are in UTC.", "Model: qwen3.8-2.4t-a95b", "took 29:28 in all"],
        ["Assessed 20 Nov 2026", "Dates are in UTC.", "Model: qwen3.8-2.4t-a95b", "took 3:57"],
        ["Started 20 Nov 2026", "Dates are in UTC.", "Model: qwen3.8-2.4t-a95b", "running for 1:15"],
        ["评估于 2026年11月18日至2026年11月20日", "日期按 UTC 计。", "模型：qwen3.8-2.4t-a95b", "合计用时 29:28"],
        ["评估于 2026年11月20日", "日期按 UTC 计。", "模型：qwen3.8-2.4t-a95b", "用时 3:57"],
        ["开始于 2026年11月20日", "日期按 UTC 计。", "模型：qwen3.8-2.4t-a95b", "已运行 1:15"],
    ]


def test_the_404_page_shows_the_readers_language_and_switches(tmp_path):
    files = {"not_found.js": _MODULE.read_text(encoding="utf-8"),
             "i18n.js": (_JS / "i18n.js").read_text(encoding="utf-8")}
    first, switched = _node(tmp_path, _NOT_FOUND_HARNESS, files)
    assert first == ["Page not found · Academic Commercialization Assessment", "en", [False, True], "English"]
    assert switched == ["找不到这个页面 · 学术成果商业化评估", "zh-CN", [True, False], "Simplified Chinese",
                        "Simplified Chinese"], "The choice is kept, as on every page"
