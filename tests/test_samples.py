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
            self.assertEqual(set(item), {"slug", "title", "title_zh", "topic", "committed", "commit", "model",
                                         "language", "decision", "overall_score", "trl_score"})

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

    def test_the_list_carries_each_samples_score_readiness_and_language_to_the_page(self):
        """What a card shows beside the title comes with the list, in one
        request, from the scorecard the sample's run wrote. Asserted on the
        HTTP answer: a field the response model did not declare would be
        dropped here and nowhere else."""
        with patch.object(access, "ACCESS_CODE", "secret123"):
            listed = self.client.get("/api/samples")
        self.assertEqual(listed.status_code, 200)
        by_slug = {item["slug"]: item for item in listed.json()}
        self.assertEqual(list(by_slug), [sample.slug for sample in samples.SAMPLES])
        for sample in samples.SAMPLES:
            with self.subTest(slug=sample.slug):
                scores = samples.read_sample_scores(sample.slug)
                item = by_slug[sample.slug]
                self.assertEqual(item["overall_score"], scores["overall_score"])
                self.assertEqual(item["trl_score"], scores["trl_score"])
                # The language is the report's own: Chinese exactly where its headings are.
                headings = re.findall(r"^## (.+)$", samples.read_sample(sample.slug), re.M)
                chinese = any(re.search(r"[\u4e00-\u9fff]", heading) for heading in headings)
                self.assertEqual(item["language"], "Simplified Chinese" if chinese else "English")
                self.assertNotIn("band", item, "the grade is the scorecard's function in the page, not a second copy here")
        overalls = [item["overall_score"] for item in by_slug.values()]
        self.assertLess(min(overalls), 50)
        self.assertGreater(max(overalls), 70, "the samples span an early technology and a mature one")
        self.assertEqual(sum(item["language"] == "Simplified Chinese" for item in by_slug.values()), 1)

    def test_the_list_declares_what_it_returns(self):
        schema = app.openapi()
        answer = schema["paths"]["/api/samples"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertEqual(answer["type"], "array")
        model = schema["components"]["schemas"][answer["items"]["$ref"].rsplit("/", 1)[-1]]
        self.assertEqual(set(model["properties"]),
                         {"slug", "title", "title_zh", "topic", "committed", "commit", "model", "language",
                          "decision", "overall_score", "trl_score"})
        self.assertNotIn("file", model["properties"])

    def test_a_sample_whose_scorecard_cannot_be_read_is_listed_without_a_score(self):
        """Missing from the image, not JSON, not an object, or holding something
        that is not a score: the card shows the title alone, and the list is
        still a 200."""
        bodies = {
            "missing": None, "not-json": "<html>no</html>", "a-list": "[74.0]", "words": '{"overall_score": "high", "trl_score": "9"}',
            "out-of-range": '{"overall_score": 150, "trl_score": 12}', "booleans": '{"overall_score": true, "trl_score": false}',
            "not-finite": '{"overall_score": NaN, "trl_score": Infinity}', "negative": '{"overall_score": -1, "trl_score": 0}',
            "whole": '{"overall_score": 61, "trl_score": 6.5}', "half": '{"overall_score": 48.6}',
        }
        listed = [samples.Sample(name, f"{name}.md", name, name, "2026-01-01", "0000000", "model-x") for name in bodies]
        with TemporaryDirectory() as tmp:
            for name, body in bodies.items():
                if body is not None:
                    (Path(tmp) / f"{name}.scores.json").write_text(body, encoding="utf-8")
            with patch.object(samples, "_EXAMPLES_ROOT", Path(tmp)), patch.object(samples, "SAMPLES", tuple(listed)), \
                    patch.object(samples, "_BY_SLUG", {sample.slug: sample for sample in listed}):
                answer = self.client.get("/api/samples")
        self.assertEqual(answer.status_code, 200)
        shown = {item["slug"]: (item["overall_score"], item["trl_score"]) for item in answer.json()}
        for name in ("missing", "not-json", "a-list", "words", "out-of-range", "booleans", "not-finite", "negative"):
            self.assertEqual(shown[name], (None, None), name)
        self.assertEqual(shown["whole"], (61, 6.5))
        self.assertEqual(shown["half"], (48.6, None))
        self.assertEqual({item["language"] for item in answer.json()}, {"English"}, "an entry that names no language is English")

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

    def test_a_sample_carries_a_decision_context_exactly_where_its_report_was_permitted_a_conclusion(self):
        """The entry is the only record of what the run was asked, so it is held
        to the report's own code-written applicability paragraph: decision
        support with a GO / NO-GO permitted where the entry has a context, and
        not otherwise. The owner it names is the one the report names."""
        decided = [sample for sample in samples.SAMPLES if sample.decision is not None]
        self.assertEqual([sample.slug for sample in decided], ["perovskite-silicon-tandem"])
        for sample in samples.SAMPLES:
            with self.subTest(slug=sample.slug):
                report = samples.read_sample(sample.slug)
                block = report.split("## ", 1)[0]
                permitted = "Mode `decision_support`" in block and "`GO/NO_GO` is permitted" in block
                self.assertEqual(permitted, sample.decision is not None)
                if sample.decision is not None:
                    for field in ("asset_description", "target_application", "decision_owner", "decision_type"):
                        self.assertTrue(getattr(sample.decision, field).strip(), field)
                    self.assertIn(sample.decision.decision_owner.lower(), report.lower())

    def test_the_conclusion_is_read_from_the_committed_report_and_needs_no_code(self):
        """What the run page's card shows for a run, on the committed file: the
        owner and the decision the entry records, and the conclusion the
        report states, found in it now by the run page's reader. A sample run
        without a decision context is answered `asked: false` and nothing else."""
        from academic_agent.decision_verdict import find_verdict
        from academic_agent.report_display import conclusion_for_display

        with patch.object(access, "ACCESS_CODE", "secret123"):
            answers = {sample.slug: self.client.get(f"/api/samples/{sample.slug}/decision") for sample in samples.SAMPLES}
            # Control: nothing but GET is let through.
            self.assertEqual(self.client.post("/api/samples/perovskite-silicon-tandem/decision", json={}).status_code, 401)
        for sample in samples.SAMPLES:
            with self.subTest(slug=sample.slug):
                answer = answers[sample.slug]
                self.assertEqual(answer.status_code, 200)
                body = answer.json()
                if sample.decision is None:
                    self.assertEqual(body, {"asked": False, "question": None, "conclusion": None})
                    continue
                self.assertTrue(body["asked"])
                self.assertEqual(body["question"], {"decision_owner": sample.decision.decision_owner,
                                                    "decision_type": sample.decision.decision_type})
                report = samples.read_sample(sample.slug)
                self.assertEqual(body["conclusion"], json.loads(json.dumps(
                    conclusion_for_display(find_verdict(report), report))))
        perovskite = answers["perovskite-silicon-tandem"].json()["conclusion"]
        self.assertEqual((perovskite["status"], perovskite["verdict"]), ("stated", "defer"))
        self.assertEqual(perovskite["statement"], "Decision applicability and conclusion: DEFER.")
        # The section is named as the displayed report heads it, so the card's
        # link finds it on the page the reader draws.
        self.assertIn(f"## {perovskite['section']}\n", self.client.get("/api/samples/perovskite-silicon-tandem").text)
        self.assertEqual({item["verdict"] for item in perovskite["statements"]}, {"defer"})

    def test_the_card_quotes_words_the_served_report_contains(self):
        """The rule the card's link depends on: the statement, its needle and
        its section are in the words of the report the page draws, which is
        the display text, not the committed bytes. The committed sample reads
        the same either way, so a report whose display text differs stands in:
        "GO/NO_GO" is shown as "GO / NO-GO", and a quote of the saved bytes
        would match nothing on the page."""
        report = ("# T\n\n## Executive Summary\n\nText here.\n\n"
                  "## 5. Commercialization Opportunities & Recommendations\n\n"
                  "Conclusion: DEFER, pending evidence for each GO/NO_GO gate.\n")
        entry = samples.Sample("shown", "shown.md", "t", "t", "2026-01-01", "0000000", "model-x",
                               decision=samples.SampleDecision("a", "b", "Owner", "Decide"))
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "shown.md").write_text(report, encoding="utf-8")
            with patch.object(samples, "_EXAMPLES_ROOT", Path(tmp)), patch.object(samples, "_BY_SLUG", {"shown": entry}):
                conclusion = self.client.get("/api/samples/shown/decision").json()["conclusion"]
                served = self.client.get("/api/samples/shown").text
        flat = " ".join(served.split())
        self.assertEqual(conclusion["status"], "stated")
        self.assertIn("GO / NO-GO", conclusion["statement"])
        for key in ("statement", "needle"):
            self.assertIn(" ".join(conclusion[key].split()), flat, key)
        self.assertIn(f"## {conclusion['section']}\n", served)

    def test_no_conclusion_is_a_404_for_an_unknown_or_missing_sample(self):
        for path in ("/api/samples/nope/decision", "/api/samples/..%2Fpyproject.toml/decision",
                     "/api/samples/perovskite-silicon-tandem/decision/extra"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
        gone = samples.Sample("gone", "does-not-exist.md", "t", "t", "2026-01-01", "0000000", "model-x",
                              decision=samples.SampleDecision("a", "b", "c", "d"))
        with patch.object(samples, "_BY_SLUG", {"gone": gone}):
            self.assertEqual(self.client.get("/api/samples/gone/decision").status_code, 404)

    def test_the_conclusion_endpoint_declares_what_it_returns(self):
        """Declared, so a field the model left out cannot be dropped silently
        on its way to the page (AGENTS.md: test the seam)."""
        schema = app.openapi()
        answer = schema["paths"]["/api/samples/{slug}/decision"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        model = schema["components"]["schemas"][answer["$ref"].rsplit("/", 1)[-1]]
        self.assertEqual(set(model["properties"]), {"asked", "question", "conclusion"})
        listed = self.client.get("/api/samples").json()
        self.assertEqual(listed[0]["decision"], {
            "asset_description": "Lab-scale perovskite-silicon tandem solar cell technology from a university research group",
            "target_application": "Utility-scale photovoltaic modules",
            "decision_owner": "Technology transfer office",
            "decision_type": "License the technology",
        })
        self.assertEqual([item["slug"] for item in listed if item["decision"] is None],
                         [sample.slug for sample in samples.SAMPLES if sample.decision is None])

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

    def test_the_page_says_what_a_sample_is_not_once(self):
        """The introduction also said "Opening one makes no model or search
        request", and the note under the brief said "no new model call" and
        "by the same code as a run's page": the builder's assurances, to a
        reader who has no reason to wonder. What a sample is not (a measure
        of accuracy, a current market view, re-verified) is said once, in the
        dated notice over each report, which names the date, the model and
        the pipeline. The note under the brief says only why it is shorter
        than a run's."""
        strings = (_REPO / "web/static/js/samples_i18n.js").read_text(encoding="utf-8")
        english, chinese = strings.split('"Simplified Chinese": {', 1)
        caution = re.compile(r"not a measure|historical|not current|up-to-date|re-verified|model call|model or search"
                             r"|same code|不代表|历史|最新|核验|模型调用|模型或检索|同一段代码")
        for name, table in (("english", english), ("chinese", chinese)):
            with self.subTest(language=name):
                found = dict(re.findall(r'^\s+(samples_\w+): "((?:[^"\\]|\\.)*)",?\s*$', table, re.M))
                self.assertGreaterEqual(len(found), 14)
                self.assertEqual([key for key, text in found.items() if caution.search(text)], ["samples_historical"])
                for part in ("{date}", "{model}"):
                    self.assertIn(part, found["samples_historical"])
                # "On pipeline 9bd948c" was a term to a reader: the commit is
                # under "Technical details" (samples_revision), not in the sentence.
                self.assertNotIn("{commit}", found["samples_historical"])
                self.assertNotRegex(found["samples_historical"], r"(?i)pipeline|流水线")
                self.assertIn("{commit}", found["samples_revision"])
        self.assertEqual(re.search(r'samples_sub: "([^"]+)"', english)[1],
                         "Finished assessments you can read without an account or API keys.")
        self.assertEqual(re.search(r'samples_sub: "([^"]+)"', chinese)[1], "无需账号或 API Key 即可阅读的完整评估。")


class SampleListLayoutTests(unittest.TestCase):
    """Seen at 717 px on 2026-11-21: the cards were one row that scrolled
    sideways, two and a half of them showed, and the one sample with a
    decision conclusion was the seventh. The page also said "Choose a report
    above." before there was anything above to choose."""

    def test_the_sample_with_a_decision_conclusion_comes_first(self):
        self.assertIsNotNone(samples.SAMPLES[0].decision)
        self.assertEqual(samples.list_samples()[0]["slug"], "perovskite-silicon-tandem")
        self.assertEqual(sum(1 for sample in samples.SAMPLES if sample.decision), 1)

    def test_every_card_is_on_the_page_at_every_width(self):
        css = (_REPO / "web/static/css/samples.css").read_text(encoding="utf-8")
        listing = css[css.index(".samples__list {"):]
        self.assertNotRegex(css, r"\.samples__list \{[^}]*overflow-x", "no row that scrolls sideways")
        self.assertNotIn("scroll-snap", css)
        self.assertRegex(listing, r"^\.samples__list \{\s*display: grid;")
        narrow = css[css.index("@media (max-width: 767px)"):]
        narrow = narrow[:narrow.index("\n}\n")]
        self.assertRegex(narrow, r"\.samples__list \{[^}]*grid-template-columns: repeat\(auto-fill, minmax\(")
        reader = (_REPO / "web/static/js/samples.js").read_text(encoding="utf-8")
        self.assertNotIn("scrollLeft", reader, "nothing scrolls sideways to bring a card into view")

    def test_the_page_holds_placeholders_until_the_list_arrives(self):
        page = (_REPO / "web/samples.html").read_text(encoding="utf-8")
        listing = page[page.index('id="sample-list"'):page.index("</nav>")]
        self.assertIn('aria-busy="true"', listing)
        self.assertEqual(listing.count('class="sample-card sample-card--placeholder" aria-hidden="true"'), 4)
        reader = page[page.index('id="sample-reader"'):]
        reader = reader[:reader.index("</main>")]
        self.assertNotIn("samples_choose", reader)
        self.assertIn('<div class="skeleton"></div>', reader)
        css = (_REPO / "web/static/css/samples.css").read_text(encoding="utf-8")
        self.assertIn(".sample-card--placeholder", css)

    def test_the_reader_is_the_main_landmark_with_a_skip_link(self):
        # #446: no <main> meant a screen reader could not jump to the report
        # and a keyboard Tabbed through the header, the language selector and
        # every sample card first. The privacy page has the same shape: its
        # two policy articles sit in one <main>.
        for name in ("web/samples.html", "web/privacy.html"):
            page = (_REPO / name).read_text(encoding="utf-8")
            self.assertEqual(page.count("<main"), 1, name)
            self.assertEqual(page.count("</main>"), 1, name)
        page = (_REPO / "web/samples.html").read_text(encoding="utf-8")
        body = page[page.index("<body>") + len("<body>"):]
        first = re.search(r"<(\w+)[ >]", body).group(1)
        self.assertEqual(first, "a", "the skip link is the first element in the body")
        link = re.search(r'<a class="samples__skip"[^>]*>([^<]+)</a>', body)
        self.assertIsNotNone(link, "no skip link found")
        self.assertIn('href="#sample-reader"', link.group(0))
        self.assertIn('data-samples-i18n="samples_skip"', link.group(0))
        self.assertEqual(link.group(1), "Skip to the report")
        # Following the link must move focus to the reader: a plain anchor
        # only scrolls to a target it cannot focus, so the reader carries
        # tabindex="-1" (focusable, not in the Tab order) and keeps its id
        # and class.
        reader = re.search(r'<main class="samples__reader" id="sample-reader"[^>]*>', page)
        self.assertIsNotNone(reader)
        self.assertIn('tabindex="-1"', reader.group(0))
        css = (_REPO / "web/static/css/samples.css").read_text(encoding="utf-8")
        self.assertIn(".samples__skip", css)
        self.assertIn(".samples__skip:focus-visible", css)


_ALLOWED_TAGS = {
    "p", "strong", "em", "code", "ul", "li", "h1", "h2", "h3", "h4",
    "div", "table", "thead", "tbody", "tr", "th", "td", "span", "a",
    "button",  # citation chips, which open the source cards
    "details", "summary",  # the fold around the reviewer's notes
}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SampleRenderingTests(unittest.TestCase):
    """Every committed sample through the shipped renderer, as the page does."""

    def test_samples_render_with_only_renderer_tags(self):
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            source = (_REPO / "web/static/js/result.js").read_text(encoding="utf-8")
            source = source.replace('import * as api from "./api.js";', "const api = {};")
            source = source.replace('import { language, t } from "./i18n.js";',
                                    'const t = (k) => k; const language = () => "English";')
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
        the report's first sentence, a risk and a first step for every sample, and
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
            console.log(JSON.stringify(inputs.map(({ scores, markdown, decided }) => {
              // As samples.js does for a sample whose run was given a decision context.
              const progress = decided ? { decision_gate: { mode: "decision_support" } } : null;
              const data = mod.decisionBrief({ scores, markdown, progress });
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
                       "markdown": report_for_display(samples.read_sample(s.slug)),
                       "decided": s.decision is not None} for s in samples.SAMPLES]
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
                # Every one opens its recommendations by naming the assessment
                # mode; that sentence was each one's "first recommended step".
                self.assertNotRegex(shown["next"], r"(?i)^(assessment mode|decision owner|评估模式)")
                self.assertNotRegex(shown["next"], r"[:：]$")
                self.assertEqual(shown["empty"], 0, "no card of the brief is left saying there is nothing")
                # A sample keeps no checks, so the context line is what tells
                # a reader what a decision context would add; the one run
                # that was given a context is not told it would help.
                if sample.decision is None:
                    self.assertIn("brief_change_context", shown["changers"])
                else:
                    self.assertNotIn("brief_change_context", shown["changers"])
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
        self.assertIn("Seven complete", readme)

    def test_every_sample_names_a_model_and_a_revision(self):
        for sample in samples.SAMPLES:
            with self.subTest(slug=sample.slug):
                self.assertRegex(sample.commit, r"^[0-9a-f]{7}$")
                self.assertRegex(sample.model, r"^[a-z0-9][a-z0-9.-]+$")
                self.assertRegex(sample.committed, r"^\d{4}-\d{2}-\d{2}$")
        # The notice on the page says all three: the date and the model in its
        # sentence, the revision under "Technical details".
        strings = (_REPO / "web/static/js/samples_i18n.js").read_text(encoding="utf-8")
        self.assertEqual(strings.count("{model}"), 2)
        self.assertEqual(strings.count("{commit}"), 2)
        source = (_REPO / "web/static/js/samples.js").read_text(encoding="utf-8")
        self.assertIn('.replace("{model}", () => sample.model)', source)
        self.assertIn('t("samples_revision").replace("{commit}", () => sample.commit)', source)
