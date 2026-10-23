"""Link-preview tags on the two public pages (web/index.html, web/samples.html).

A preview card is built by a crawler that runs no script, sends no access
code and resolves no relative URL. Every way these tags break is silent: a
relative image path, a file the app does not serve, or a page behind the gate
still parses, and the shared link just shows no card. So the tests fetch the
pages through the app as a crawler would and follow the image URL back to the
bytes the app serves.
"""

from __future__ import annotations

import struct
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from api import access
from api.main import app

_REPO = Path(__file__).resolve().parent.parent
_ORIGIN = "https://academic-commercialization-agent.up.railway.app"
# Route a crawler fetches → the URL its og:url must name.
_PAGES = {"/": f"{_ORIGIN}/", "/samples": f"{_ORIGIN}/samples"}
_REQUIRED = (
    "og:type", "og:site_name", "og:title", "og:description", "og:url",
    "og:image", "og:image:width", "og:image:height", "og:image:alt", "twitter:card",
)


class _MetaTags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        attributes = dict(attrs)
        key = attributes.get("property") or attributes.get("name")
        if key and attributes.get("content") is not None:
            self.tags.setdefault(key, []).append(attributes["content"])


def _png_size(data: bytes) -> tuple[int, int]:
    # Width and height are the first two fields of the IHDR chunk, which the
    # PNG format requires to come first; no imaging library needed.
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])


class SharePreviewTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def _served_tags(self, route: str) -> dict[str, list[str]]:
        # With the gate on, as on the public deployment: a crawler has no code.
        with patch.object(access, "ACCESS_CODE", "secret123"):
            response = self.client.get(route)
        self.assertEqual(response.status_code, 200, route)
        parser = _MetaTags()
        parser.feed(response.text)
        return parser.tags

    def test_each_page_declares_every_tag_once(self):
        """A missing or duplicated tag leaves the card to whichever value the
        site's crawler happens to pick."""
        for route in _PAGES:
            tags = self._served_tags(route)
            for key in _REQUIRED:
                with self.subTest(route=route, tag=key):
                    self.assertEqual(len(tags.get(key, [])), 1)
            self.assertEqual(tags["twitter:card"], ["summary_large_image"])

    def test_urls_are_absolute_and_name_the_page(self):
        """Crawlers do not resolve relative URLs; a relative og:image shows no picture."""
        for route, url in _PAGES.items():
            tags = self._served_tags(route)
            with self.subTest(route=route):
                self.assertEqual(tags["og:url"], [url])
                self.assertTrue(tags["og:image"][0].startswith(f"{_ORIGIN}/static/"))

    def test_image_is_served_without_a_code_and_matches_its_declared_size(self):
        """The image must be reachable at the URL the tags name, ungated, and
        be the repository's social preview at the size the tags declare."""
        expected = (_REPO / "assets" / "social-preview.png").read_bytes()
        for route in _PAGES:
            tags = self._served_tags(route)
            path = urlsplit(tags["og:image"][0]).path
            with self.subTest(route=route, image=path):
                with patch.object(access, "ACCESS_CODE", "secret123"):
                    response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["content-type"], "image/png")
                # One picture in two places: GitHub's social preview reads
                # assets/, the app serves only web/static/. Equal bytes stop
                # the card and the repository preview drifting apart.
                self.assertEqual(response.content, expected)
                width, height = _png_size(response.content)
                self.assertEqual(tags["og:image:width"], [str(width)])
                self.assertEqual(tags["og:image:height"], [str(height)])


if __name__ == "__main__":
    unittest.main()
