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
]


def _node() -> str | None:
    return shutil.which("node")


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

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _render(self, inputs: list[str]) -> list[str]:
        result = subprocess.run(
            [_node(), str(self._work / "run.mjs"), json.dumps(inputs)],
            capture_output=True, text=True, timeout=60, cwd=self._work,
        )
        if result.returncode != 0:
            self.fail(f"renderer failed: {result.stderr[:400]}")
        return json.loads(result.stdout)

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
