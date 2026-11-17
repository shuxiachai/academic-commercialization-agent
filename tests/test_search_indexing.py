"""What a search engine is told: robots.txt, the sitemap, noindex, sample heads.

Until 2026-11-17 the deployment answered 404 to /robots.txt and /sitemap.xml,
every /samples/<slug> was served with the list's title and og:url, and a run
page said nothing to a crawler at all. A run URL is a read capability
(AGENTS.md), so a share link pasted on a public page could end up in a search
result, which hands the report to anyone who searches.

Every failure here is silent, as with the link-preview tags: a page that is
wrongly indexable still renders, and a page a crawler cannot render still
opens in a browser. So the tests fetch through the app as a crawler would,
with the gate on and no code, and read robots.txt with two independent
readers, because crawlers do not agree on how to read it.
"""

from __future__ import annotations

import json
import re
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from fastapi.testclient import TestClient

from api import access, crawlers, samples
from api import main as api_main
from api.main import _is_page_asset, app

_REPO = Path(__file__).resolve().parent.parent
_WEB = _REPO / "web"
_RUN = "20261106T000000Z-" + "a" * 32
_OTHER = "20261107T000000Z-" + "b" * 32
_NOINDEX = "noindex, nofollow"
# The same document as "/", at addresses that are not the home page.
_UNLISTED_DOCUMENTS = (f"/run/{_RUN}", f"/compare/{_RUN}/{_OTHER}", "/history", "/verify", "/reset")
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_CARD_TAGS = ("description", "og:type", "og:site_name", "og:title", "og:description", "og:url",
              "og:image", "og:image:width", "og:image:height", "og:image:alt", "twitter:card")
_CJK = re.compile(r"[一-鿿]")


class _Head(HTMLParser):
    """The title and the meta tags of a served document, as a crawler reads them."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: dict[str, list[str]] = {}
        self.titles: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
            self.titles.append("")
        if tag != "meta":
            return
        attributes = dict(attrs)
        key = attributes.get("property") or attributes.get("name")
        if key and attributes.get("content") is not None:
            self.tags.setdefault(key, []).append(attributes["content"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.titles[-1] += data


def _head(text: str) -> _Head:
    parser = _Head()
    parser.feed(text)
    return parser


def _longest_match_allows(robots: str, path: str) -> bool:
    """RFC 9309 as Google and Bing read it: the longest matching rule decides,
    and Allow wins a tie. urllib.robotparser takes the first match in file
    order instead, so a file both readers agree on does not depend on which
    of the two a crawler implements."""
    best = (0, True)
    in_group = False
    for line in robots.splitlines():
        field, _, value = line.split("#", 1)[0].partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            in_group = value == "*"
        elif in_group and field in ("allow", "disallow") and value and path.startswith(value):
            allowed = field == "allow"
            if len(value) > best[0] or (len(value) == best[0] and allowed):
                best = (len(value), allowed)
    return best[1]


def _script_strings(key: str) -> dict[str, str]:
    """A string of the sample reader, in each language, from the shipped module."""
    source = (_WEB / "static/js/samples_i18n.js").read_text(encoding="utf-8")
    found = re.findall(rf'^\s*{key}: "([^"]*)",$', source, flags=re.M)
    assert len(found) == 2, key
    return {"English": found[0], "Simplified Chinese": found[1]}


class _Case(unittest.TestCase):
    def setUp(self):
        # Gated, as the public deployment is, and no code: a crawler has none.
        self._code = patch.object(access, "ACCESS_CODE", "secret123")
        self._code.start()
        self.client = TestClient(app)
        self.origin = crawlers.origin_of((_WEB / "index.html").read_text(encoding="utf-8"))

    def tearDown(self):
        self.client.close()
        self._code.stop()

    def _robots(self) -> str:
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        return response.text

    def _allowed(self, path: str) -> bool:
        robots = self._robots()
        reader = RobotFileParser()
        reader.parse(robots.splitlines())
        first_match = reader.can_fetch("Googlebot", path)
        longest = _longest_match_allows(robots, path)
        self.assertEqual(first_match, longest, f"the two readings of robots.txt disagree about {path}")
        return longest


class RobotsTests(_Case):

    def test_it_is_served_as_text_without_a_code_and_never_rate_limited(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        # A crawler that is refused robots.txt (429 or 5xx) treats the whole
        # site as closed until it can read it again.
        self.assertTrue(_is_page_asset("/robots.txt"))
        self.assertTrue(_is_page_asset("/sitemap.xml"))

    def test_the_public_pages_may_be_fetched(self):
        for path in ("/", "/samples", "/privacy", "/static/js/samples.js", "/static/brand/social-preview.png",
                     *(f"/samples/{sample.slug}" for sample in samples.SAMPLES)):
            with self.subTest(path=path):
                self.assertTrue(self._allowed(path))

    def test_what_has_nothing_to_show_a_crawler_is_closed(self):
        for path in ("/api/runs", "/api/auth/config", "/api/auth/me", "/api/admin/accounts", "/api/quota",
                     "/api/plan", "/api/keys/check", "/api/papers", "/admin", "/source-locator", "/api/"):
            with self.subTest(path=path):
                self.assertFalse(self._allowed(path))

    def test_what_the_public_pages_fetch_is_open_to_a_crawler_that_renders_them(self):
        """The sample reader, the privacy page and the landing page are drawn by
        script from these reads. Loaded in Chromium with all of /api/
        refused, the sample page read "The sample list could not be loaded."
        and the home page lost its landing: app.js puts the landing away
        when the access check fails with anything other than a 401."""
        for path in ("/api/samples", "/api/samples/hyperloop", "/api/samples/hyperloop/scores",
                     "/api/site", "/api/access/check"):
            with self.subTest(path=path):
                self.assertTrue(self._allowed(path))
        # The rule, for the two pages that use plain fetch: every address they name.
        for name in ("samples.js", "privacy.js"):
            source = (_WEB / "static/js" / name).read_text(encoding="utf-8")
            reads = re.findall(r'fetch\(\s*[`"](/[^`"$?]*)', source)
            self.assertTrue(reads, name)
            for path in reads:
                with self.subTest(module=name, path=path):
                    self.assertTrue(self._allowed(path))
        # ...and the landing's two, which go through api.js.
        client = (_WEB / "static/js/api.js").read_text(encoding="utf-8")
        self.assertIn('request("/api/access/check"', client)
        self.assertIn('request("/api/samples")', client)

    def test_a_shared_assessment_is_left_open_so_that_its_noindex_is_read(self):
        """A crawler told not to fetch an address never reads the noindex on
        it, and may then list the bare address once someone links to it. The
        address of a run is the permission to read it, so that listing is the
        leak. The two share addresses are therefore open in robots.txt and
        closed by the header, and the two must hold together."""
        for path in (f"/run/{_RUN}", f"/compare/{_RUN}/{_OTHER}"):
            with self.subTest(path=path):
                self.assertTrue(self._allowed(path))
                self.assertEqual(self.client.get(path).headers.get("x-robots-tag"), _NOINDEX)

    def test_the_content_of_a_run_is_closed_to_a_crawler_and_says_noindex_as_well(self):
        """Under /api/runs/ the answer is the report itself. A crawler that
        keeps what it fetches obeys a Disallow, not a noindex; the header is
        there for the one that fetches regardless."""
        for path in (f"/api/runs/{_RUN}/report", f"/api/runs/{_RUN}/report.pdf", f"/api/runs/{_RUN}",
                     f"/api/runs/{_RUN}/scores"):
            with self.subTest(path=path):
                self.assertFalse(self._allowed(path))
                self.assertEqual(self.client.get(path).headers.get("x-robots-tag"), _NOINDEX)

    def test_it_names_the_sitemap_at_the_address_the_cards_name(self):
        lines = [line for line in self._robots().splitlines() if line.lower().startswith("sitemap:")]
        self.assertEqual(lines, [f"Sitemap: {self.origin}/sitemap.xml"])
        served = _head(self.client.get("/").text).tags["og:url"]
        self.assertEqual(served, [f"{self.origin}/"])

    def test_a_page_that_names_no_address_gets_rules_and_no_sitemap_line(self):
        robots = crawlers.robots_txt(None)
        self.assertNotIn("sitemap", robots.lower())
        self.assertIn("Disallow: /api/", robots)
        for page in ("", "<meta property=\"og:url\" content=\"/relative\">",
                     "<meta property=\"og:url\" content=\"javascript:alert(1)\">"):
            self.assertIsNone(crawlers.origin_of(page))


class SitemapTests(_Case):

    def _entries(self) -> list[tuple[str, str | None]]:
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("application/xml"))
        root = ET.fromstring(response.content)
        self.assertEqual(root.tag, f"{_SITEMAP_NS}urlset")
        return [(url.findtext(f"{_SITEMAP_NS}loc"), url.findtext(f"{_SITEMAP_NS}lastmod")) for url in root]

    def test_it_lists_the_home_page_the_samples_and_the_privacy_page(self):
        expected = [(f"{self.origin}/", None), (f"{self.origin}/samples", None),
                    *((f"{self.origin}/samples/{sample.slug}", sample.committed) for sample in samples.SAMPLES),
                    (f"{self.origin}/privacy", None)]
        self.assertEqual(self._entries(), expected)
        self.assertEqual(len(samples.SAMPLES), 6, "the walk must reach the samples")

    def test_it_follows_the_allowlist_and_is_not_a_second_list(self):
        added = samples.Sample("a-new-one", "a-new-one.md", "A new one", "a new one", "2026-11-17", "0000000", "model-x")
        listed = (*samples.SAMPLES, added)
        with patch.object(samples, "SAMPLES", listed), \
                patch.object(samples, "_BY_SLUG", {sample.slug: sample for sample in listed}):
            entries = self._entries()
            self.assertIn((f"{self.origin}/samples/a-new-one", "2026-11-17"), entries)
            self.assertIsNone(self.client.get("/samples/a-new-one").headers.get("x-robots-tag"))
        with patch.object(samples, "SAMPLES", ()), patch.object(samples, "_BY_SLUG", {}):
            self.assertEqual([loc for loc, _ in self._entries()],
                             [f"{self.origin}/", f"{self.origin}/samples", f"{self.origin}/privacy"])

    def test_every_address_it_lists_is_a_page_a_crawler_may_fetch_and_index(self):
        """A sitemap that names a page robots.txt closes, or one that answers
        noindex, is a contradiction a search console reports and a crawler
        resolves against the page."""
        entries = self._entries()
        for loc, _ in entries:
            path = urlsplit(loc).path
            with self.subTest(path=path):
                self.assertTrue(loc.startswith(f"{self.origin}/"))
                self.assertTrue(self._allowed(path))
                page = self.client.get(path)
                self.assertEqual(page.status_code, 200)
                self.assertIsNone(page.headers.get("x-robots-tag"))
                self.assertNotIn("robots", _head(page.text).tags)

    def test_no_run_address_can_be_listed(self):
        for path, _ in crawlers.public_paths():
            self.assertNotRegex(path, r"^/(run|compare|api|admin|history|verify|reset|source-locator)")


class NoindexTests(_Case):

    def test_a_run_page_says_noindex_in_the_header_and_in_the_page(self):
        for path in _UNLISTED_DOCUMENTS:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get("x-robots-tag"), _NOINDEX)
                head = _head(response.text)
                self.assertEqual(head.tags.get("robots"), [_NOINDEX])
                # In the head, where a crawler looks for it.
                self.assertLess(response.text.index('name="robots"'), response.text.index("</head>"))

    def test_the_home_page_is_the_committed_file_and_says_nothing_of_the_kind(self):
        response = self.client.get("/")
        self.assertIsNone(response.headers.get("x-robots-tag"))
        self.assertEqual(response.content, (_WEB / "index.html").read_bytes())
        self.assertNotIn("robots", _head(response.text).tags)

    def test_a_run_page_is_the_home_page_but_for_the_two_tags(self):
        """The card of a shared run stays the site's general one until the
        owner of the deployment decides otherwise; og:url, which named the
        home page and made some sites open that instead of the run, is gone."""
        home = self.client.get("/").text
        for path in _UNLISTED_DOCUMENTS:
            with self.subTest(path=path):
                served = self.client.get(path).text
                head = _head(served)
                self.assertNotIn("og:url", head.tags)
                self.assertEqual(head.titles, _head(home).titles)
                for key in ("og:title", "og:description", "og:image", "description"):
                    self.assertEqual(head.tags[key], _head(home).tags[key])
                self.assertNotIn(_RUN, served, "the run's address is not written into the page")
                # Exactly that: the robots tag after the charset, the address line gone.
                expected = home.replace(f'<meta property="og:url" content="{self.origin}/">\n', "", 1).replace(
                    '<meta charset="utf-8">\n', f'<meta charset="utf-8">\n<meta name="robots" content="{_NOINDEX}">\n', 1)
                self.assertNotEqual(expected, home)
                self.assertEqual(served, expected)

    def test_it_holds_where_the_saved_source_locator_rewrites_the_page(self):
        registered = type("Registered", (), {"page_reachable": staticmethod(lambda _request: True)})()
        with patch.object(api_main, "_source_locator", registered):
            run = self.client.get(f"/run/{_RUN}")
            home = self.client.get("/")
        self.assertEqual(run.headers.get("x-robots-tag"), _NOINDEX)
        self.assertEqual(_head(run.text).tags.get("robots"), [_NOINDEX])
        self.assertIn(f'href="/source-locator#{_RUN}"', run.text)
        self.assertEqual(run.headers["cache-control"], "no-store")
        self.assertIsNone(home.headers.get("x-robots-tag"))
        self.assertNotIn("robots", _head(home.text).tags)
        self.assertIn('href="/source-locator"', home.text)

    def test_every_route_but_the_listed_public_ones_says_noindex(self):
        """The rule, not the instances: what may be indexed is a list, and a
        route added later is closed until someone puts it on that list."""
        public = {path for path, _ in crawlers.public_paths()} | {"/robots.txt", "/sitemap.xml"}
        asked = 0
        for route in app.routes:
            methods = getattr(route, "methods", None) or ()
            if "GET" not in methods:
                continue
            path = re.sub(r"\{[^}]*\}", "x", route.path)
            if path in public:
                continue
            asked += 1
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).headers.get("x-robots-tag"), _NOINDEX)
        self.assertGreater(asked, 30, "the walk must reach the API")
        for path in ("/static/js/app.js", "/static/brand/social-preview.png", "/robots.txt", "/sitemap.xml",
                     *public):
            with self.subTest(path=path):
                self.assertIsNone(self.client.get(path).headers.get("x-robots-tag"))

    def test_an_address_that_is_almost_a_public_one_is_not(self):
        for path in ("/samples/", "/samples/no-such-sample", "/samples/hyperloop/extra", "/privacy/",
                     "/Samples", "/nothing-here", "/run/", "/samples/solid-state-batteries-ev"):
            with self.subTest(path=path):
                self.assertFalse(crawlers.indexable(path))
                # Not followed: "/samples/" redirects to the list, and it is
                # the answer at this address that is asked about.
                answer = self.client.get(path, follow_redirects=False)
                self.assertEqual(answer.headers.get("x-robots-tag"), _NOINDEX)

    def test_a_sample_that_is_not_listed_gets_the_reader_and_a_noindex(self):
        """A removed sample's old address still opens the reader, which says
        there is no such sample; it must not be indexed as a copy of the list."""
        response = self.client.get("/samples/solid-state-batteries-ev")
        self.assertEqual(response.status_code, 200)
        head = _head(response.text)
        self.assertEqual(head.tags.get("robots"), [_NOINDEX])
        self.assertNotIn("og:url", head.tags)
        self.assertEqual(head.titles, _head((_WEB / "samples.html").read_text(encoding="utf-8")).titles)
        self.assertIn("/static/js/samples.js", response.text)


class SampleHeadTests(_Case):

    def _scores(self, sample) -> dict:
        return json.loads((_REPO / "examples" / sample.file).with_suffix(".scores.json").read_text(encoding="utf-8"))

    def test_the_list_page_is_the_committed_file(self):
        self.assertEqual(self.client.get("/samples").content, (_WEB / "samples.html").read_bytes())

    def test_each_sample_is_served_with_its_own_title_and_card(self):
        list_head = _head(self.client.get("/samples").text)
        names = _script_strings("samples_title")
        seen = set()
        for sample in samples.SAMPLES:
            with self.subTest(sample=sample.slug):
                response = self.client.get(f"/samples/{sample.slug}")
                self.assertEqual(response.status_code, 200)
                head = _head(response.text)
                scores = self._scores(sample)
                overall, trl = f"{scores['overall_score']:.1f} / 100", f"TRL {scores['trl_score']:g}"
                # The tab's name is the one the reader's script gives it
                # where the interface is in the report's language. (In an
                # English interface the script renames the Chinese sample
                # "… · Sample reports"; that is the script's and not pinned here.)
                self.assertEqual(head.titles, [f"{sample.title} · {names[sample.language]}"])
                for key in _CARD_TAGS:
                    self.assertEqual(len(head.tags.get(key, [])), 1, key)
                self.assertEqual(head.tags["og:url"], [f"{self.origin}/samples/{sample.slug}"])
                self.assertEqual(head.tags["description"], head.tags["og:description"])
                description, card_title = head.tags["description"][0], head.tags["og:title"][0]
                for text in (description, card_title):
                    self.assertIn(overall, text)
                    self.assertIn(trl, text)
                self.assertIn(sample.title, card_title)
                # What a sample is: an old run kept as written, with its date and model.
                self.assertIn(sample.committed, description)
                self.assertIn(sample.model, description)
                # Nothing else about the card moved.
                for key in ("og:type", "og:site_name", "og:image", "og:image:width", "og:image:height",
                            "og:image:alt", "twitter:card"):
                    self.assertEqual(head.tags[key], list_head.tags[key], key)
                self.assertNotIn("robots", head.tags)
                # The document below the head is the reader, byte for byte.
                self.assertEqual(response.text.split("</head>", 1)[1],
                                 self.client.get("/samples").text.split("</head>", 1)[1])
                seen.add((head.titles[0], card_title, description, head.tags["og:url"][0]))
        self.assertEqual(len(seen), len(samples.SAMPLES), "no two samples share a head")

    def test_a_sample_is_described_in_the_language_of_its_report(self):
        chinese = [sample for sample in samples.SAMPLES if sample.language == "Simplified Chinese"]
        self.assertEqual([sample.slug for sample in chinese], ["uhvdc-transmission-zh"])
        for sample in samples.SAMPLES:
            head = _head(self.client.get(f"/samples/{sample.slug}").text)
            written = " ".join((head.titles[0], head.tags["description"][0], head.tags["og:title"][0]))
            with self.subTest(sample=sample.slug):
                if sample in chinese:
                    self.assertIn(sample.title, head.tags["description"][0])
                    self.assertIn("示例报告", head.titles[0])
                    # The model's name and the abbreviation are Latin in either language.
                    left = written.replace(sample.model, "").replace("TRL", "")
                    self.assertNotRegex(left, r"[A-Za-z]{3,}")
                else:
                    self.assertIn(sample.topic, head.tags["description"][0])
                    self.assertNotRegex(written, _CJK)

    def test_the_numbers_are_the_ones_the_card_in_the_list_shows(self):
        """One reading of the scorecard: the head states what /api/samples
        hands the page for the same sample."""
        listed = {item["slug"]: item for item in self.client.get("/api/samples").json()}
        for sample in samples.SAMPLES:
            description = _head(self.client.get(f"/samples/{sample.slug}").text).tags["description"][0]
            with self.subTest(sample=sample.slug):
                self.assertIn(f"{listed[sample.slug]['overall_score']:.1f} / 100", description)
                self.assertIn(f"TRL {listed[sample.slug]['trl_score']:g}", description)

    def test_a_sample_without_a_readable_scorecard_is_still_named_and_states_no_number(self):
        bodies = {"missing": None, "not-json": "<html>no</html>", "out-of-range": '{"overall_score": 150, "trl_score": 12}',
                  "half": '{"overall_score": 48.6}', "whole": '{"overall_score": 61, "trl_score": 6.5}'}
        listed = [samples.Sample(name, f"{name}.md", f"Title of {name}", f"topic of {name}", "2026-01-01", "0000000", "model-x")
                  for name in bodies]
        heads = {}
        with TemporaryDirectory() as tmp:
            for name, body in bodies.items():
                if body is not None:
                    (Path(tmp) / f"{name}.scores.json").write_text(body, encoding="utf-8")
            with patch.object(samples, "_EXAMPLES_ROOT", Path(tmp)), patch.object(samples, "SAMPLES", tuple(listed)), \
                    patch.object(samples, "_BY_SLUG", {sample.slug: sample for sample in listed}):
                for name in bodies:
                    response = self.client.get(f"/samples/{name}")
                    self.assertEqual(response.status_code, 200, name)
                    heads[name] = _head(response.text)
        for name in ("missing", "not-json", "out-of-range"):
            with self.subTest(scorecard=name):
                head = heads[name]
                written = head.tags["description"][0] + head.tags["og:title"][0]
                self.assertNotRegex(written, r"/ 100|TRL|None|null|nan")
                self.assertEqual(head.titles, [f"Title of {name} · Sample reports"])
                self.assertIn(f"topic of {name}", head.tags["description"][0])
                self.assertEqual(head.tags["og:url"], [f"{self.origin}/samples/{name}"])
        self.assertIn("48.6 / 100", heads["half"].tags["description"][0])
        self.assertNotIn("TRL", heads["half"].tags["description"][0])
        self.assertIn("61.0 / 100", heads["whole"].tags["description"][0])
        self.assertIn("TRL 6.5", heads["whole"].tags["description"][0])

    def test_a_name_with_markup_in_it_stays_text(self):
        hostile = '"><script>alert(1)</script> & <b>'
        sample = samples.Sample("odd", "odd.md", hostile, hostile, "2026-01-01", "0000000", 'm"<x>')
        with patch.object(samples, "SAMPLES", (sample,)), patch.object(samples, "_BY_SLUG", {"odd": sample}):
            text = self.client.get("/samples/odd").text
        head = _head(text)
        self.assertEqual(head.titles, [f"{hostile} · Sample reports"])
        self.assertIn(hostile, head.tags["description"][0])
        self.assertIn('m"<x>', head.tags["description"][0])
        self.assertIn(hostile, head.tags["og:title"][0])
        self.assertEqual(text.count("<script"), self.client.get("/samples").text.count("<script"))
        self.assertNotIn("<b>", text)
        # A backslash or a group reference in a name is text to the rewrite too.
        for name in (r"a\1b", r"\g<0>", "100% $1"):
            page = crawlers.sample_page((_WEB / "samples.html").read_text(encoding="utf-8"),
                                        {"slug": "odd", "title": name, "topic": name, "committed": "2026-01-01",
                                         "model": "m", "language": "English", "overall_score": None, "trl_score": None})
            self.assertEqual(_head(page).titles, [f"{name} · Sample reports"])

    def test_the_comment_in_the_page_no_longer_says_every_sample_shares_the_lists_address(self):
        """Prose is not covered by tests (AGENTS.md); this sentence was true
        until this change and would have been left behind by it."""
        page = (_WEB / "samples.html").read_text(encoding="utf-8")
        self.assertNotIn("rather than\n     whichever sample a shared link opens", page)
        self.assertIn("api/crawlers.py", page)


if __name__ == "__main__":
    unittest.main()
