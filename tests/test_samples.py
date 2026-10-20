"""Sample reports readable without credentials (api/samples.py, /samples).

The point of the feature is that a visitor with no access code can see a
finished report, so the gate exemption is the behaviour under test. The
exemption is also the risk: it must cover only GET on the allowlisted
sample paths, and a slug must never become a filesystem path.
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
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import access, samples
from api.main import app

_REPO = Path(__file__).resolve().parent.parent


class SampleCatalogTests(unittest.TestCase):

    def test_every_allowlisted_file_exists_and_is_a_report(self):
        for sample in samples.SAMPLES:
            with self.subTest(slug=sample.slug):
                text = samples.read_sample(sample.slug)
                self.assertTrue(text.startswith("# "), text[:40])

    def test_listing_does_not_expose_file_paths(self):
        listed = samples.list_samples()
        self.assertEqual([item["slug"] for item in listed], [s.slug for s in samples.SAMPLES])
        for item in listed:
            self.assertNotIn("file", item)
            self.assertEqual(set(item), {"slug", "title", "topic", "committed", "commit"})

    def test_unknown_slug_is_a_key_error_not_a_path_lookup(self):
        for slug in ("nope", "../pyproject.toml", "..\\README.md", "README"):
            with self.subTest(slug=slug), self.assertRaises(KeyError):
                samples.read_sample(slug)


class SampleHttpTests(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_list_and_read_need_no_code_on_a_gated_deployment(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            listed = self.client.get("/api/samples")
            first = listed.json()[0]["slug"]
            report = self.client.get(f"/api/samples/{first}")
            # Control: the exemption did not open the rest of /api/.
            history = self.client.get("/api/runs")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(report.status_code, 200)
        self.assertTrue(report.headers["content-type"].startswith("text/markdown"))
        self.assertTrue(report.text.startswith("# "))
        self.assertEqual(history.status_code, 401)

    def test_only_get_is_exempt(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            r = self.client.post("/api/samples", json={})
        self.assertEqual(r.status_code, 401)

    def test_unknown_and_traversal_slugs_are_404(self):
        for path in ("/api/samples/nope", "/api/samples/..%2Fpyproject.toml",
                     "/api/samples/..%5CREADME.md"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_missing_file_on_this_deployment_is_404_not_500(self):
        missing = samples.Sample("gone", "does-not-exist.md", "t", "t", "2026-01-01", "0000000")
        with patch.object(samples, "_BY_SLUG", {"gone": missing}):
            self.assertEqual(self.client.get("/api/samples/gone").status_code, 404)

    def test_reader_page_is_served_for_list_and_deep_links(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            for path in ("/samples", "/samples/solid-state-batteries-ev"):
                with self.subTest(path=path):
                    r = self.client.get(path)
                    self.assertEqual(r.status_code, 200)
                    self.assertIn("/static/js/samples.js", r.text)
                    self.assertIn("script-src 'self'", r.headers["content-security-policy"])


class SampleClientTests(unittest.TestCase):
    """Static checks on the shipped client files."""

    def test_reader_does_not_use_the_credentialed_api_client(self):
        source = (_REPO / "web/static/js/samples.js").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"from\s+[\"']\./api\.js[\"']")
        self.assertNotIn("X-Access-Code", source)

    def test_main_page_links_to_samples_from_gate_and_composer(self):
        page = (_REPO / "web/index.html").read_text(encoding="utf-8")
        gate = page[page.index('id="gate"'):]
        self.assertIn('href="/samples"', gate)
        compose = page[page.index('id="pane-compose"'):page.index('id="compose-form"')]
        self.assertIn('href="/samples"', compose)

    def test_both_languages_define_every_sample_string(self):
        # A separate table because i18n.js is hash-locked by a frozen
        # experiment; see the header of samples_i18n.js.
        source = (_REPO / "web/static/js/samples_i18n.js").read_text(encoding="utf-8")
        english, chinese = source.split('"Simplified Chinese": {', 1)
        keys = set(re.findall(r"^\s+(samples_\w+):", english, re.M))
        self.assertGreaterEqual(len(keys), 5)
        self.assertEqual(keys, set(re.findall(r"^\s+(samples_\w+):", chinese, re.M)))

        used = set()
        for page in ("web/index.html", "web/samples.html"):
            html = (_REPO / page).read_text(encoding="utf-8")
            used |= set(re.findall(r'data-samples-i18n="(\w+)"', html))
        for script in ("web/static/js/samples.js",):
            js = (_REPO / script).read_text(encoding="utf-8")
            used |= set(re.findall(r'\bt\("(samples_\w+)"\)', js))
            used |= set(re.findall(r'\bnote\("(samples_\w+)"\)', js))
        self.assertTrue(used)
        self.assertLessEqual(used, keys)


_ALLOWED_TAGS = {
    "p", "strong", "em", "code", "ul", "li", "h1", "h2", "h3", "h4",
    "div", "table", "thead", "tbody", "tr", "th", "td", "span", "a",
}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SampleRenderingTests(unittest.TestCase):
    """Every committed sample through the shipped renderer, as the page does."""

    def test_samples_render_with_only_renderer_tags(self):
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            source = (_REPO / "web/static/js/result.js").read_text(encoding="utf-8")
            source = source.replace('import * as api from "./api.js";', "const api = {};")
            source = source.replace('import { t } from "./i18n.js";', "const t = (k) => k;")
            (work / "renderer.mjs").write_text(source, encoding="utf-8")
            (work / "run.mjs").write_text(textwrap.dedent("""
                import { readFileSync } from "node:fs";
                import { renderMarkdown } from "./renderer.mjs";
                const inputs = JSON.parse(readFileSync(process.argv[2], "utf-8"));
                console.log(JSON.stringify(inputs.map((md) => renderMarkdown(md))));
            """), encoding="utf-8")
            reports = [samples.read_sample(s.slug) for s in samples.SAMPLES]
            (work / "inputs.json").write_text(json.dumps(reports), encoding="utf-8")
            result = subprocess.run(
                [shutil.which("node"), str(work / "run.mjs"), str(work / "inputs.json")],
                capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=work,
            )
        self.assertEqual(result.returncode, 0, result.stderr[:400])
        for sample, html in zip(samples.SAMPLES, json.loads(result.stdout), strict=True):
            with self.subTest(slug=sample.slug):
                tags = {m.lower() for m in re.findall(r"<\/?([a-zA-Z0-9]+)", html)}
                self.assertFalse(tags - _ALLOWED_TAGS)
                self.assertIn("<h2>", html)
                self.assertIn('class="cite"', html)
