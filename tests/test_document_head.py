"""A HEAD request for a page, robots.txt or the sitemap is answered as its GET is.

Measured on https://academic-agent.cc on 2026-11-18: HEAD was answered 405 at
every page address (the home page, the sample reader and each sample, the
privacy page, a run, a comparison, /history, /verify, /reset, /admin) and at
/robots.txt and /sitemap.xml, while the same addresses answered GET with 200.
Only the files under /static, which Starlette serves, and FastAPI's own
/docs answered HEAD. A route declared with `@app.get` takes GET and nothing
else.

Search engines fetch with GET, so nothing was lost there. Link checkers,
uptime monitors, sitemap validators and some link-preview fetchers ask with
HEAD first, and they were told the page does not allow the method they
asked with, which reads as a broken link.

The tests state the rule over the routes rather than a list of addresses,
so a page added later is covered, and they ask with the gate on and no code,
as such a tool would.
"""

from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import access, crawlers, samples
from api import main as api_main
from api.main import app

_RUN = "20261106T000000Z-" + "a" * 32
_OTHER = "20261107T000000Z-" + "b" * 32
# What the answer to a HEAD must say exactly as the GET says it. Content-Length
# is among them: a HEAD states the size of the body the GET would send.
_SAME = ("content-type", "content-length", "cache-control", "x-robots-tag", "content-security-policy",
         "x-content-type-options", "referrer-policy")


def _document_paths() -> list[str]:
    """Every address the app serves as a document: each GET route outside the
    API and the health checks, with a real name where the route takes one."""
    names = {"run_id": _RUN, "other_run_id": _OTHER, "slug": samples.SAMPLES[0].slug}
    paths = []
    for route in app.routes:
        if "GET" not in (getattr(route, "methods", None) or ()):
            continue
        if route.path.startswith(("/api/", "/health")):
            continue
        paths.append(re.sub(r"\{([^}:]*)[^}]*\}", lambda match: names.get(match[1], "x"), route.path))
    return paths


class DocumentHeadTests(unittest.TestCase):
    def setUp(self):
        self._code = patch.object(access, "ACCESS_CODE", "secret123")
        self._code.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self._code.stop()

    def test_every_document_answers_head_as_it_answers_get(self):
        paths = _document_paths()
        # The walk must reach the pages and the two files a crawler reads.
        for expected in ("/", "/history", f"/run/{_RUN}", f"/compare/{_RUN}/{_OTHER}", "/verify", "/reset",
                         "/samples", f"/samples/{samples.SAMPLES[0].slug}", "/privacy", "/admin",
                         "/robots.txt", "/sitemap.xml"):
            self.assertIn(expected, paths)
        for path in paths:
            with self.subTest(path=path):
                got = self.client.get(path)
                head = self.client.head(path)
                self.assertEqual(got.status_code, 200)
                self.assertEqual(head.status_code, 200)
                for name in _SAME:
                    self.assertEqual(head.headers.get(name), got.headers.get(name), name)
                self.assertEqual(int(head.headers["content-length"]), len(got.content))

    def test_each_sample_and_an_unlisted_name_answer_head(self):
        """The route is one; the three answers behind it are built differently
        (the committed file, a rewritten head, a noindex page)."""
        for path in ("/samples", *(f"/samples/{sample.slug}" for sample in samples.SAMPLES), "/samples/no-such-sample"):
            with self.subTest(path=path):
                got, head = self.client.get(path), self.client.head(path)
                self.assertEqual((got.status_code, head.status_code), (200, 200))
                self.assertEqual(int(head.headers["content-length"]), len(got.content))
                self.assertEqual(head.headers.get("x-robots-tag"), got.headers.get("x-robots-tag"))

    def test_a_head_says_what_a_search_engine_is_told(self):
        """A crawler that asks with HEAD reads the same instruction as one
        that asks with GET: noindex on a run, none on a public page."""
        for path in (f"/run/{_RUN}", f"/compare/{_RUN}/{_OTHER}", "/history", "/admin", "/samples/no-such-sample"):
            with self.subTest(path=path):
                self.assertEqual(self.client.head(path).headers.get("x-robots-tag"), crawlers.NOINDEX)
        for path, _ in crawlers.public_paths():
            with self.subTest(path=path):
                self.assertIsNone(self.client.head(path).headers.get("x-robots-tag"))
        self.assertTrue(self.client.head("/robots.txt").headers["content-type"].startswith("text/plain"))
        self.assertTrue(self.client.head("/sitemap.xml").headers["content-type"].startswith("application/xml"))

    def test_it_holds_where_the_saved_source_locator_rewrites_the_page(self):
        registered = type("Registered", (), {"page_reachable": staticmethod(lambda _request: True)})()
        with patch.object(api_main, "_source_locator", registered):
            for path in ("/", f"/run/{_RUN}"):
                with self.subTest(path=path):
                    got, head = self.client.get(path), self.client.head(path)
                    self.assertEqual((got.status_code, head.status_code), (200, 200))
                    self.assertEqual(head.headers["cache-control"], "no-store")
                    self.assertEqual(int(head.headers["content-length"]), len(got.content))

    def test_a_sitemap_that_cannot_be_written_is_missing_to_head_as_to_get(self):
        with patch.object(crawlers, "origin_of", lambda _page: None):
            self.assertEqual(self.client.get("/sitemap.xml").status_code, 404)
            self.assertEqual(self.client.head("/sitemap.xml").status_code, 404)

    def test_nothing_else_about_what_these_addresses_accept_changed(self):
        """Only HEAD was added. A page still refuses a write, and the gate
        still answers an anonymous HEAD under /api/ itself: what it lets
        through without a code is GET on the sample reads, not HEAD."""
        for path in ("/", "/samples", "/privacy", "/robots.txt", "/sitemap.xml", f"/run/{_RUN}"):
            for method in ("POST", "PUT", "DELETE", "PATCH"):
                with self.subTest(path=path, method=method):
                    answer = self.client.request(method, path)
                    self.assertEqual(answer.status_code, 405)
                    self.assertEqual(sorted(answer.headers["allow"].replace(" ", "").split(",")), ["GET", "HEAD"])
        self.assertEqual(self.client.head("/api/runs").status_code, 401)
        self.assertEqual(self.client.head("/api/samples").status_code, 401)


if __name__ == "__main__":
    unittest.main()
