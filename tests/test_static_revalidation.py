"""Browsers confirm the page's files before reusing them.

The page is many modules importing one another, each cached under its own
unversioned URL. Sent with a validator and no caching instruction, each was
kept for as long as the browser guessed, so after a deploy a returning
visitor could run a new module beside an old one. These tests pin the
instruction on every file the page is made of, and that confirming an
unchanged file costs no body.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import access
from api import main as api_main
from api.main import app

_STATIC = Path(__file__).resolve().parents[1] / "web" / "static"


class StaticRevalidationTests(unittest.TestCase):
    def setUp(self):
        # Page assets are public: a gated deployment serves them without a code.
        self._code = patch.object(access, "ACCESS_CODE", "a-code")
        self._code.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self._code.stop()

    def test_every_file_the_page_is_made_of_must_be_confirmed(self):
        files = sorted(path for path in _STATIC.rglob("*") if path.is_file())
        scripts = [path for path in files if path.suffix == ".js"]
        self.assertGreaterEqual(len(scripts), 15, "the walk must reach the page's modules")
        for path in files:
            url = "/static/" + path.relative_to(_STATIC).as_posix()
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-cache")
                # The instruction is only useful with something to confirm against.
                self.assertTrue(response.headers.get("etag"))

    def test_confirming_an_unchanged_file_sends_no_body_and_repeats_the_instruction(self):
        first = self.client.get("/static/js/app.js")
        again = self.client.get("/static/js/app.js", headers={"If-None-Match": first.headers["etag"]})
        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.content, b"")
        self.assertEqual(again.headers["cache-control"], "no-cache")
        # A copy that no longer matches is replaced, not confirmed.
        stale = self.client.get("/static/js/app.js", headers={"If-None-Match": '"not-the-current-file"'})
        self.assertEqual((stale.status_code, stale.content), (200, first.content))

    def test_the_documents_that_load_them_get_the_same_instruction(self):
        # A page kept longer than the modules it names is the same mismatch.
        # The main page had no instruction at all unless the locator rewrote it.
        for url in ("/", "/history", "/run/20261106T000000Z-" + "a" * 32,
                    "/samples", "/samples/hyperloop", "/privacy"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_a_policy_already_chosen_is_left_alone(self):
        # Where the locator rewrites the main page it is never stored, and that stands.
        with patch.object(api_main, "_source_locator", object()):
            self.assertEqual(self.client.get("/").headers["cache-control"], "no-store")
        # An API reply gets no caching instruction from this.
        for url in ("/api/site", "/api/samples", "/health"):
            with self.subTest(url=url):
                self.assertNotEqual(self.client.get(url).headers.get("cache-control"), "no-cache")

    def test_a_file_that_is_not_there_is_still_not_guessed_at(self):
        missing = self.client.get("/static/js/no-such-module.js")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.headers["cache-control"], "no-cache")

    def test_only_reads_are_marked(self):
        self.assertNotEqual(self.client.post("/static/js/app.js").headers.get("cache-control"), "no-cache")


if __name__ == "__main__":
    unittest.main()
