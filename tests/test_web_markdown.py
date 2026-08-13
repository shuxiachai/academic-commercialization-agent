"""Tests for the client-side Markdown renderer.

renderMarkdown is the only place in the web client where untrusted text
reaches innerHTML: reports carry model output and third-party source titles.
Its escaping was verified by hand once, which is exactly the situation these
tests exist to replace — the next edit to one of its regexes would otherwise
break the escaping with nothing to notice.

Run through Node so the assertions exercise the shipped file rather than a
Python transcription of it. Skipped when Node is unavailable; the check runs
in CI, where it is present.
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
_RENDERER = _REPO / "web" / "static" / "js" / "result.js"

# Tags the renderer is allowed to emit. Anything else in the output came from
# the input, which means an escape was missed.
_ALLOWED_TAGS = {
    "p", "strong", "em", "code", "ul", "li",
    "h1", "h2", "h3", "h4",
    "div", "table", "thead", "tbody", "tr", "th", "td",
    "span", "a",
}

_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
    "<iframe src=//evil.example></iframe>",
    "**<svg onload=alert(1)>**",
    "# <iframe src=//evil.example>",
    "| <b>x</b> |\n|---|\n| <i>y</i> |",
    "- <script>alert(1)</script>",
    "`<script>alert(1)</script>`",
    "[click](javascript:alert(1))",
    "[click](JaVaScRiPt:alert(1))",
    "<a href='x' onmouseover='alert(1)'>y</a>",
    "A1 &lt;already escaped&gt; text",
    # Attribute injection: the link target closes href and opens an event
    # handler beside it. Distinct from every payload above because it produces
    # no new tag and no javascript: scheme, so neither of the original two
    # checks noticed it — inline() builds <a href="..."> by substitution, and
    # escapeHtml did not escape quotes.
    '[click](https://e.test/" onmouseover="alert(1))',
    "[click](https://e.test/' onmouseover='alert(1))",
    '![x](https://e.test/i.png" onerror="alert(1))',
]

# Attributes the renderer legitimately emits.
_ALLOWED_ATTRS = {"href", "target", "rel", "class", "colspan", "scope"}


def _node() -> str | None:
    return shutil.which("node")


def _parse_attributes(html: str) -> list[tuple[str, str, str]]:
    """Every (tag, attribute, value) a real parser resolves out of `html`.

    Uses an HTML parser rather than a regex so the assertions see what a
    browser would: entity-encoded quotes stay inside an attribute's value
    instead of being read as the delimiter that ends it.
    """
    from html.parser import HTMLParser

    found: list[tuple[str, str, str]] = []

    class _Collector(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for name, value in attrs:
                found.append((tag, name, value or ""))

    parser = _Collector()
    parser.feed(html)
    parser.close()
    return found


@unittest.skipUnless(_node(), "node not installed")
class MarkdownEscapingTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        work = Path(cls._tmp.name)

        # The module imports i18n and the api client, neither of which resolve
        # outside a browser. Stubbing them keeps the renderer itself untouched.
        source = _RENDERER.read_text(encoding="utf-8")
        source = source.replace('import * as api from "./api.js";', "const api = {};")
        source = source.replace('import { t } from "./i18n.js";', "const t = (k) => k;")
        (work / "renderer.mjs").write_text(source, encoding="utf-8")

        (work / "run.mjs").write_text(textwrap.dedent("""
            import { renderMarkdown } from "./renderer.mjs";
            const inputs = JSON.parse(process.argv[2]);
            console.log(JSON.stringify(inputs.map((md) => renderMarkdown(md))));
        """), encoding="utf-8")
        cls._work = work
        cls._cache = {}

        # Spawn Node once here, before any assertion depends on the timing.
        # The first spawn on a cold CI runner is far slower than the rest --
        # observed 60s, then 2.2s, then ~60ms -- because loading node.exe and
        # scanning a freshly written .mjs are one-time OS-level costs. Paying
        # them inside the first test made whichever test happened to run first
        # fail on a slow runner, which reads as "the escaping broke" rather
        # than "the machine was busy". Generous timeout: this measures the
        # runner, not the renderer.
        warmup = subprocess.run(
            [_node(), str(work / "run.mjs"), '["warmup"]'],
            capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=work,
        )
        # Not check=True: a syntax error in result.js exits non-zero here now
        # rather than in the first test, and CalledProcessError would report
        # only the exit code. The stderr is the whole diagnosis.
        if warmup.returncode != 0:
            raise RuntimeError(f"renderer failed to load: {warmup.stderr[:400]}")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _render(self, inputs: list[str]) -> list[str]:
        # Memoised because four tests render the identical payload list, each
        # asking a different question about the same HTML. The renderer is a
        # pure function of its input, so re-spawning Node for it bought
        # nothing and multiplied the exposure to a slow spawn.
        key = json.dumps(inputs)
        if key not in self._cache:
            result = subprocess.run(
                [_node(), str(self._work / "run.mjs"), key],
                capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=self._work,
            )
            if result.returncode != 0:
                self.fail(f"renderer failed: {result.stderr[:400]}")
            self._cache[key] = json.loads(result.stdout)
        return self._cache[key]

    def test_no_payload_produces_an_unexpected_tag(self):
        """The check: every tag in the output is one the renderer emits."""
        import re

        for payload, html in zip(_PAYLOADS, self._render(_PAYLOADS), strict=True):
            with self.subTest(payload=payload[:40]):
                tags = {m.lower() for m in re.findall(r"<\/?([a-zA-Z0-9]+)", html)}
                rogue = tags - _ALLOWED_TAGS
                self.assertFalse(
                    rogue, f"{payload!r} produced unexpected tag(s) {rogue}: {html[:160]}"
                )

    def test_no_payload_produces_a_javascript_href(self):
        for payload, html in zip(_PAYLOADS, self._render(_PAYLOADS), strict=True):
            with self.subTest(payload=payload[:40]):
                self.assertNotRegex(html, r'href\s*=\s*["\']?\s*javascript:')

    def test_no_payload_produces_an_unexpected_attribute(self):
        """Parsed rather than pattern-matched, because the bug this covers is
        invisible to both checks above: an injected event handler adds no new
        tag and uses no javascript: scheme. Only looking at the attributes a
        parser actually resolves — the way a browser would — shows it.
        """
        for payload, html in zip(_PAYLOADS, self._render(_PAYLOADS), strict=True):
            with self.subTest(payload=payload[:40]):
                for tag, attr, _value in _parse_attributes(html):
                    self.assertIn(
                        attr, _ALLOWED_ATTRS,
                        f"{payload!r} produced <{tag} {attr}=...>: {html[:200]}",
                    )

    def test_link_targets_stay_http(self):
        """A resolved href must still be a web URL after escaping — proving
        the fix did not merely mangle links into something inert."""
        for payload, html in zip(_PAYLOADS, self._render(_PAYLOADS), strict=True):
            with self.subTest(payload=payload[:40]):
                for _tag, attr, value in _parse_attributes(html):
                    if attr == "href":
                        self.assertRegex(value, r"^https?://")

    def test_angle_brackets_are_entity_encoded(self):
        [html] = self._render(["<script>alert(1)</script>"])
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)

    def test_ordinary_markdown_still_renders(self):
        """Escaping must not have been achieved by rendering nothing."""
        html, = self._render([
            "# Title\n\n"
            "**bold** and *italic* and `code`\n\n"
            "- one\n- two\n\n"
            "| a | b |\n|---|---|\n| 1 | 2 |\n"
        ])
        for fragment in ["<h1>", "<strong>", "<em>", "<code>", "<ul>", "<li>", "<table>"]:
            self.assertIn(fragment, html)

    def test_citation_markers_get_their_own_element(self):
        """They are what makes the report auditable, so they are marked up."""
        html, = self._render(["Efficiency reached 26% [A1] and [P2, P3]."])
        self.assertIn('<span class="cite">[A1]</span>', html)
        self.assertIn('<span class="cite">[P2, P3]</span>', html)

    def test_http_links_are_kept_and_made_safe(self):
        html, = self._render(["See [the paper](https://example.com/a)."])
        self.assertIn('href="https://example.com/a"', html)
        self.assertIn('rel="noopener noreferrer"', html)


if __name__ == "__main__":
    unittest.main()
