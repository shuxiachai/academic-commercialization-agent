"""Offline tests for scripts/check_external_links.py.

The script itself talks to the network; these tests must not. Every case hands
``check_links`` a stub fetcher, so the suite keeps making no network request and
the ``error::UserWarning`` filter stays satisfied.
"""

from __future__ import annotations

import ast
import io
import tempfile
import unittest
from pathlib import Path

from scripts.check_external_links import (
    DOCUMENTS,
    ROOT,
    Link,
    check_links,
    collect_links,
    report,
)


def _documents_pinned_by_the_public_docs_test() -> tuple[str, ...]:
    """Read the guide list out of tests/test_public_docs.py without importing it."""
    tree = ast.parse((ROOT / "tests" / "test_public_docs.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "test_current_guide_relative_links_resolve":
            for inner in ast.walk(node):
                if isinstance(inner, ast.For) and isinstance(inner.iter, (ast.Tuple, ast.List)):
                    values = [
                        element.value
                        for element in inner.iter.elts
                        if isinstance(element, ast.Constant) and isinstance(element.value, str)
                    ]
                    if values and all(value.endswith(".md") for value in values):
                        return tuple(values)
    raise AssertionError("the guide list in tests/test_public_docs.py was not found")


class CollectLinksTests(unittest.TestCase):
    def test_collects_http_links_and_ignores_repository_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.md").write_text(
                "[guide](https://example.com/guide)\n"
                "[local](docs/other.md)\n"
                "![badge](https://img.example.com/badge.svg)\n"
                "[again](https://example.com/guide)\n"
                "[mail](mailto:someone@example.com)\n",
                encoding="utf-8",
            )
            (root / "b.md").write_text(
                "[angle](<https://example.com/angle>)\n"
                "[guide](https://example.com/guide)\n",
                encoding="utf-8",
            )

            links = collect_links(root, ("a.md", "b.md"))

        self.assertEqual(
            [link.url for link in links],
            [
                "https://example.com/angle",
                "https://example.com/guide",
                "https://img.example.com/badge.svg",
            ],
        )
        by_url = {link.url: link.documents for link in links}
        # A URL carried by two documents is requested once, and both are named.
        self.assertEqual(by_url["https://example.com/guide"], ("a.md", "b.md"))
        self.assertEqual(by_url["https://example.com/angle"], ("b.md",))

    def test_the_script_reads_the_documents_the_public_docs_test_checks(self):
        self.assertEqual(DOCUMENTS, _documents_pinned_by_the_public_docs_test())

    def test_every_named_guide_exists_and_links_outwards(self):
        links = collect_links(ROOT, DOCUMENTS)

        self.assertTrue(links, "the current guides carry no external link at all")
        for relative in DOCUMENTS:
            with self.subTest(document=relative):
                self.assertTrue((ROOT / relative).is_file())


class CheckLinksTests(unittest.TestCase):
    def test_requests_each_link_once_with_the_timeout(self):
        calls: list[tuple[str, float]] = []

        def fetcher(url: str, timeout: float) -> tuple[int | None, str | None]:
            calls.append((url, timeout))
            return 200, None

        links = [Link("https://a.example/1", ("README.md",)), Link("https://b.example/2", ("AGENTS.md",))]
        results = check_links(links, fetcher=fetcher, timeout=3.0, delay=0.0, clock=lambda: 0.0, sleep=lambda _: None)

        self.assertEqual(calls, [("https://a.example/1", 3.0), ("https://b.example/2", 3.0)])
        self.assertEqual([result.status for result in results], [200, 200])

    def test_pauses_between_two_requests_to_the_same_host_only(self):
        slept: list[float] = []
        now = [100.0]

        def fetcher(url: str, timeout: float) -> tuple[int | None, str | None]:
            now[0] += 0.2  # a request costs time; the delay is measured from its end
            return 200, None

        links = [
            Link("https://a.example/1", ("README.md",)),
            Link("https://a.example/2", ("README.md",)),
            Link("https://b.example/1", ("README.md",)),
        ]
        check_links(
            links,
            fetcher=fetcher,
            timeout=1.0,
            delay=0.5,
            clock=lambda: now[0],
            sleep=slept.append,
        )

        # Same host: the full 0.5s pause, since the previous request finished just now.
        # A different host: no wait at all.
        self.assertEqual(len(slept), 1)
        self.assertAlmostEqual(slept[0], 0.5)


class ReportTests(unittest.TestCase):
    def test_a_broken_link_fails_the_run_and_names_the_status_and_url(self):
        stream = io.StringIO()
        results = check_links(
            [Link("https://example.com/gone", ("README.md",)), Link("https://example.com/ok", ("README.md",))],
            fetcher=lambda url, timeout: (404, None) if url.endswith("gone") else (200, None),
            delay=0.0,
            clock=lambda: 0.0,
            sleep=lambda _: None,
        )

        exit_code = report(results, stream=stream)

        output = stream.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("FAIL 404 https://example.com/gone", output)
        self.assertIn("linked from: README.md", output)
        self.assertIn("1 failed, 0 warned", output)

    def test_bot_blocked_statuses_are_warnings_and_keep_the_run_green(self):
        stream = io.StringIO()
        statuses = {"https://img.example/1": 403, "https://api.example/2": 429}
        results = check_links(
            [Link(url, ("README.md",)) for url in statuses],
            fetcher=lambda url, timeout: (statuses[url], None),
            delay=0.0,
            clock=lambda: 0.0,
            sleep=lambda _: None,
        )

        exit_code = report(results, stream=stream)

        output = stream.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("WARN 403 https://img.example/1", output)
        self.assertIn("WARN 429 https://api.example/2", output)
        self.assertNotIn("FAIL", output)
        self.assertIn("0 failed, 2 warned", output)

    def test_a_network_error_is_a_failure_that_shows_the_reason(self):
        stream = io.StringIO()
        results = check_links(
            [Link("https://unreachable.example/", ("docs/README.md",))],
            fetcher=lambda url, timeout: (None, "nodename nor servname provided"),
            delay=0.0,
            clock=lambda: 0.0,
            sleep=lambda _: None,
        )

        exit_code = report(results, stream=stream)

        output = stream.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("FAIL no response (nodename nor servname provided)", output)

    def test_a_server_error_fails_even_though_a_status_came_back(self):
        stream = io.StringIO()
        results = check_links(
            [Link("https://example.com/broken", ("AGENTS.md",))],
            fetcher=lambda url, timeout: (500, None),
            delay=0.0,
            clock=lambda: 0.0,
            sleep=lambda _: None,
        )

        self.assertEqual(report(results, stream=stream), 1)
        self.assertIn("FAIL 500 https://example.com/broken", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
