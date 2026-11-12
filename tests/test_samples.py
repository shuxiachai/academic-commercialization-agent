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

from academic_agent.report_display import report_for_display
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
            self.assertEqual(set(item), {"slug", "title", "topic", "committed", "commit", "model"})

    def test_unknown_slug_is_a_key_error_not_a_path_lookup(self):
        for slug in ("nope", "../pyproject.toml", "..\\README.md", "README"):
            with self.subTest(slug=slug), self.assertRaises(KeyError):
                samples.read_sample(slug)
            with self.subTest(slug=slug, what="scores"), self.assertRaises(KeyError):
                samples.read_sample_scores(slug)

    def test_every_sample_has_the_scorecard_of_its_own_run(self):
        """A report without its score is half of what a run delivers.

        The scorecard is the file the run wrote beside the report. That it is
        this report's and not another run's is checked against the one place
        that recorded both at the time: examples/README.md, written when each
        sample was added, states every sample's readiness level and overall.
        """
        readme = (_REPO / "examples" / "README.md").read_text(encoding="utf-8")
        for sample in samples.SAMPLES:
            with self.subTest(slug=sample.slug):
                scores = samples.read_sample_scores(sample.slug)
                self.assertIsInstance(scores, dict)
                section = readme.split(f"]({sample.file})", 1)[1].split("\n---", 1)[0]
                recorded = re.search(r"TRL (\d+).*?overall ([\d.]+) / 100", section, re.S)
                self.assertEqual(f"{scores['overall_score']:.1f}", recorded[2])
                self.assertEqual(int(scores["trl_score"]), int(recorded[1]))
                # What the brief and the scorecard read.
                for key in ("mrl_score", "patent_strength", "market_accessibility", "evidence_confidence"):
                    self.assertIsInstance(scores[key], float, key)
                self.assertTrue(scores["key_risks"] and scores["key_opportunities"])

    def test_the_scorecard_sits_beside_its_report_and_nowhere_else(self):
        """Its name is the report's with another ending: no second list to keep in step."""
        for sample in samples.SAMPLES:
            with self.subTest(slug=sample.slug):
                self.assertTrue(sample.file.endswith(".md"))
                path = _REPO / "examples" / (sample.file[:-3] + ".scores.json")
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), samples.read_sample_scores(sample.slug))
        listed = {p.name for p in (_REPO / "examples").glob("*.scores.json")}
        self.assertEqual(listed, {s.file[:-3] + ".scores.json" for s in samples.SAMPLES},
                         "a scorecard here belongs to a listed sample")


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

    def test_samples_show_the_applicability_paragraph_without_its_markup(self):
        """The newer production samples carry the code-owned paragraph, which
        the shared renderer would show behind a raw comment and a stray '>'."""
        marker = "<!-- decision-applicability:v1 -->"
        self.assertIn(marker, samples.read_sample("hyperloop"))
        for sample in samples.SAMPLES:
            with self.subTest(slug=sample.slug):
                served = self.client.get(f"/api/samples/{sample.slug}").text
                self.assertNotIn(marker, served)
                self.assertTrue(served.startswith("# "))
        served = self.client.get("/api/samples/hyperloop").text
        self.assertIn("\n\n**Scope of this assessment:** An orientation brief: no decision context", served)
        self.assertNotIn("`orientation`", served.split("## Executive Summary", 1)[0])

    def test_saved_view_is_the_committed_file_for_every_sample(self):
        """The download link asks for view=saved. Served display text differs
        from the committed file for all five samples (rewritten applicability
        paragraph, cleaned references, localized labels), so a download that
        used the default would not be the file the issue asks for."""
        with patch.object(access, "ACCESS_CODE", "secret123"):
            for sample in samples.SAMPLES:
                with self.subTest(slug=sample.slug):
                    served = self.client.get(f"/api/samples/{sample.slug}", params={"view": "saved"})
                    self.assertEqual(served.status_code, 200)
                    self.assertTrue(served.headers["content-type"].startswith("text/markdown"))
                    self.assertEqual(served.text, samples.read_sample(sample.slug))

    def test_display_stays_the_default_view_the_reader_fetches(self):
        for sample in samples.SAMPLES:
            with self.subTest(slug=sample.slug):
                expected = report_for_display(samples.read_sample(sample.slug))
                default = self.client.get(f"/api/samples/{sample.slug}")
                explicit = self.client.get(f"/api/samples/{sample.slug}", params={"view": "display"})
                self.assertEqual(default.text, expected)
                self.assertEqual(explicit.text, expected)

    def test_unknown_view_is_rejected_not_silently_displayed(self):
        served = self.client.get("/api/samples/hyperloop", params={"view": "raw"})
        self.assertEqual(served.status_code, 422)

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
        missing = samples.Sample("gone", "does-not-exist.md", "t", "t", "2026-01-01", "0000000", "model-x")
        with patch.object(samples, "_BY_SLUG", {"gone": missing}):
            self.assertEqual(self.client.get("/api/samples/gone").status_code, 404)

    def test_a_samples_scorecard_needs_no_code_and_is_the_committed_file(self):
        with patch.object(access, "ACCESS_CODE", "secret123"):
            for sample in samples.SAMPLES:
                with self.subTest(slug=sample.slug):
                    served = self.client.get(f"/api/samples/{sample.slug}/scores")
                    self.assertEqual(served.status_code, 200)
                    self.assertTrue(served.headers["content-type"].startswith("application/json"))
                    self.assertEqual(served.json(), samples.read_sample_scores(sample.slug))
            # Control: a run's scorecard is still behind the gate's own rules,
            # and nothing but GET is let through.
            self.assertEqual(self.client.post("/api/samples/hyperloop/scores", json={}).status_code, 401)
            self.assertEqual(self.client.get("/api/runs").status_code, 401)

    def test_no_scorecard_is_a_404_whatever_the_reason(self):
        """Unknown sample, a path instead of a name, a file missing from the
        image, a file that is not a scorecard: the page shows the report
        without a brief for each, so each must be a plain 404, never a 500."""
        for path in ("/api/samples/nope/scores", "/api/samples/..%2Fpyproject.toml/scores",
                     "/api/samples/hyperloop/other", "/api/samples/hyperloop/scores/extra"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
        missing = samples.Sample("gone", "does-not-exist.md", "t", "t", "2026-01-01", "0000000", "model-x")
        with patch.object(samples, "_BY_SLUG", {"gone": missing}):
            self.assertEqual(self.client.get("/api/samples/gone/scores").status_code, 404)
        with TemporaryDirectory() as tmp:
            for body in ("[1, 2]", "not json", '"a string"'):
                (Path(tmp) / "broken.scores.json").write_text(body, encoding="utf-8")
                broken = samples.Sample("broken", "broken.md", "t", "t", "2026-01-01", "0000000", "model-x")
                with self.subTest(body=body), patch.object(samples, "_EXAMPLES_ROOT", Path(tmp)), \
                        patch.object(samples, "_BY_SLUG", {"broken": broken}):
                    self.assertEqual(self.client.get("/api/samples/broken/scores").status_code, 404)

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

    def test_cards_show_when_a_sample_was_added_not_its_commit(self):
        source = (_REPO / "web/static/js/samples.js").read_text(encoding="utf-8")
        meta = re.search(r'el\("span", "sample-card__meta", (.+)\),', source)[1]
        self.assertIn('t("samples_added")', meta)
        self.assertNotRegex(meta, r"sample\.commit\b")

    def test_each_sample_offers_its_markdown_as_a_plain_download_link(self):
        source = (_REPO / "web/static/js/samples.js").read_text(encoding="utf-8")
        body = re.search(r"function downloadLink\(sample\) \{(.+?)\n\}", source, re.S)[1]
        # The committed file, not the display text the reader renders, saved
        # under the sample's name.
        self.assertIn("`/api/samples/${encodeURIComponent(sample.slug)}?view=saved`", body)
        self.assertIn("link.download = `${sample.slug}.md`", body)
        self.assertIn('t("samples_download")', body)
        # A plain same-origin anchor: no extra request, nothing credentialed.
        self.assertNotIn("fetch(", body)
        self.assertNotIn("X-Access-Code", body)
        # Built with the report, so it follows the sample on screen.
        self.assertRegex(
            source,
            r"reader\.replaceChildren\(\s*historicalNotice\(sample\), downloadLink\(sample\)",
        )

    def test_download_filenames_are_clean_and_the_target_needs_no_code(self):
        client = TestClient(app)
        with patch.object(access, "ACCESS_CODE", "secret123"):
            for sample in samples.SAMPLES:
                with self.subTest(slug=sample.slug):
                    self.assertRegex(f"{sample.slug}.md", r"^[a-z0-9-]+\.md$")
                    served = client.get(f"/api/samples/{sample.slug}?view=saved")
                    self.assertEqual(served.status_code, 200)
                    self.assertTrue(served.headers["content-type"].startswith("text/markdown"))

    def test_main_page_links_to_samples_from_gate_and_composer(self):
        page = (_REPO / "web/index.html").read_text(encoding="utf-8")
        gate = page[page.index('id="gate"'):]
        self.assertIn('href="/samples"', gate)
        compose = page[page.index('id="pane-compose"'):page.index('id="compose-form"')]
        self.assertIn('href="/samples"', compose)

    def test_both_languages_define_every_sample_string(self):
        # A separate table, written while i18n.js was hash-locked; see the
        # header of samples_i18n.js.
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

    def test_the_intro_names_no_way_in_that_a_deployment_may_not_have(self):
        # The page said "without an access code". A deployment signs visitors in
        # by account, by access code or by their own keys, and production has
        # used accounts alone since 2026-11-07: a visitor there has never been
        # offered a code, and was told they need none. "Without an account" is
        # what the landing page's link to this page says, and it holds in every
        # mode. Five places carry the sentence: both languages, the text served
        # before the script runs, and the two descriptions a search result or a
        # link preview shows.
        page = (_REPO / "web/samples.html").read_text(encoding="utf-8")
        strings = (_REPO / "web/static/js/samples_i18n.js").read_text(encoding="utf-8")
        english, chinese = strings.split('"Simplified Chinese": {', 1)
        english_sub = re.search(r'samples_sub: "([^"]+)"', english)[1]
        chinese_sub = re.search(r'samples_sub: "([^"]+)"', chinese)[1]
        served = re.search(r'data-samples-i18n="samples_sub">([^<]+)<', page)[1]
        description = re.search(r'<meta name="description" content="([^"]+)">', page)[1]
        preview = re.search(r'<meta property="og:description" content="([^"]+)">', page)[1]

        for name, text in (("english", english_sub), ("served", served),
                           ("description", description), ("preview", preview)):
            with self.subTest(place=name):
                self.assertNotRegex(text, r"(?i)access code|invit")
                self.assertIn("without an account or API keys", text)
        self.assertNotRegex(chinese_sub, r"访问口令|访问码|邀请")
        self.assertIn("无需账号或 API Key", chinese_sub)
        # The served text is the opening of the string that replaces it, so the
        # sentence does not change under a reader when the script runs.
        self.assertTrue(english_sub.startswith(served))
        self.assertEqual(description, preview)


_ALLOWED_TAGS = {
    "p", "strong", "em", "code", "ul", "li", "h1", "h2", "h3", "h4",
    "div", "table", "thead", "tbody", "tr", "th", "td", "span", "a",
    "button",  # citation chips, which open the source cards
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
            # As served by /api/samples/{slug}, which the reader renders.
            reports = [report_for_display(samples.read_sample(s.slug)) for s in samples.SAMPLES]
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


    def test_every_sample_yields_a_brief_and_a_scorecard_through_the_shipped_renderer(self):
        """The run page's own functions on the committed files: the verdict,
        the report's first sentence, a risk and a first step for all six, and
        five readable dimensions each with its reason."""
        harness = textwrap.dedent("""
            import { readFileSync } from "node:fs";
            globalThis.localStorage = { getItem: () => null, setItem: () => {} };
            class Node {
              constructor(tag) { Object.assign(this, { tagName: tag.toUpperCase(), children: [], dataset: {},
                attributes: {}, style: {}, className: "", textContent: "", open: false, title: "", type: "" }); }
              append(...items) { for (const item of items) this.children.push(typeof item === "string" ? { text: item } : item); }
              setAttribute(name, value) { this.attributes[name] = value; }
              addEventListener() {}
            }
            globalThis.document = { createElement: (tag) => new Node(tag), createTextNode: (text) => ({ text }),
              querySelectorAll: () => [], documentElement: {} };
            const flat = (node) => [node, ...(node.children ?? []).flatMap(flat)];
            const cls = (node) => node.className ?? "";
            const mod = await import("./result.mjs");
            const inputs = JSON.parse(readFileSync(process.argv[2], "utf-8"));
            console.log(JSON.stringify(inputs.map(({ scores, markdown }) => {
              const data = mod.decisionBrief({ scores, markdown });
              const brief = flat(mod.renderDecisionBrief(data, { note: "said by the sample page" }));
              const card = flat(mod.renderScorecard(scores));
              return {
                verdict: brief.find((n) => cls(n) === "brief__verdict").textContent,
                summary: data.summary, risk: data.risk, next: data.next,
                changers: data.changers.map((c) => c.key),
                empty: brief.filter((n) => cls(n).includes("brief__empty")).length,
                note: brief.find((n) => cls(n) === "brief__note").textContent,
                value: card.find((n) => cls(n).startsWith("scorecard__value")).textContent,
                dims: card.filter((n) => cls(n).startsWith("dim__value")).map((n) => n.textContent),
                why: card.filter((n) => cls(n) === "dim__why").length,
                lists: card.filter((n) => cls(n) === "notes__list").map((n) => n.children.length),
              };
            })));
        """)
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            source = (_REPO / "web/static/js/result.js").read_text(encoding="utf-8")
            source = source.replace('import * as api from "./api.js";', "const api = {};")
            (work / "result.mjs").write_text(source, encoding="utf-8")
            shutil.copy2(_REPO / "web/static/js/i18n.js", work / "i18n.js")
            (work / "run.mjs").write_text(harness, encoding="utf-8")
            inputs = [{"scores": samples.read_sample_scores(s.slug),
                       "markdown": report_for_display(samples.read_sample(s.slug))} for s in samples.SAMPLES]
            (work / "inputs.json").write_text(json.dumps(inputs), encoding="utf-8")
            result = subprocess.run(
                [shutil.which("node"), str(work / "run.mjs"), str(work / "inputs.json")],
                capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=work,
            )
        self.assertEqual(result.returncode, 0, result.stderr[:600])
        for sample, shown, given in zip(samples.SAMPLES, json.loads(result.stdout), inputs, strict=True):
            with self.subTest(slug=sample.slug):
                overall = f"{given['scores']['overall_score']:.1f}"
                self.assertIn(f"{overall} / 100", shown["verdict"])
                self.assertEqual(shown["value"], overall)
                for line in ("summary", "risk", "next"):
                    self.assertTrue(shown[line], line)
                # All six open their recommendations by naming the assessment
                # mode; that sentence was each one's "first recommended step".
                self.assertNotRegex(shown["next"], r"(?i)^(assessment mode|decision owner|评估模式)")
                self.assertNotRegex(shown["next"], r"[:：]$")
                self.assertEqual(shown["empty"], 0, "no card of the brief is left saying there is nothing")
                # No decision context was given to any of these runs, and a
                # sample keeps no checks: the context line is the one that
                # is always true of them.
                self.assertIn("brief_change_context", shown["changers"])
                self.assertEqual(shown["note"], "said by the sample page")
                self.assertEqual(len(shown["dims"]), 5)
                self.assertNotIn("—", shown["dims"])
                self.assertEqual(shown["why"], 5, "each dimension says why")
                self.assertEqual(len(shown["lists"]), 2, "risks and opportunities")
                self.assertTrue(all(shown["lists"]))


class SampleProvenanceTests(unittest.TestCase):
    """The page and the folder tell the same story about where each sample came from."""

    def test_the_examples_readme_documents_every_listed_sample(self):
        readme = (_REPO / "examples" / "README.md").read_text(encoding="utf-8")
        for sample in samples.SAMPLES:
            with self.subTest(slug=sample.slug):
                self.assertIn(f"]({sample.file})", readme, "a listed sample is described in examples/README.md")
                self.assertIn(f"`{sample.model}`", readme, "...with the model it was run on")
        self.assertIn("Six complete", readme)

    def test_every_sample_names_a_model_and_a_revision(self):
        for sample in samples.SAMPLES:
            with self.subTest(slug=sample.slug):
                self.assertRegex(sample.commit, r"^[0-9a-f]{7}$")
                self.assertRegex(sample.model, r"^[a-z0-9][a-z0-9.-]+$")
                self.assertRegex(sample.committed, r"^\d{4}-\d{2}-\d{2}$")
        # The notice on the page says all three.
        strings = (_REPO / "web/static/js/samples_i18n.js").read_text(encoding="utf-8")
        self.assertEqual(strings.count("{model}"), 2)
        source = (_REPO / "web/static/js/samples.js").read_text(encoding="utf-8")
        self.assertIn('.replace("{model}", sample.model)', source)
