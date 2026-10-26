"""Report external links in the current guides that no longer resolve.

`tests/test_public_docs.py` resolves only repository-relative paths: it
deliberately makes no network request, so a link to a provider page, the live
app or a commit permalink can rot while the suite stays green. This script
covers that gap by hand — it is not part of the pytest run.

It reads the same nine documents the contract test checks, collects every
``http(s)`` link (markdown links and images alike), requests each one with a
timeout and a short pause per host, and prints what is broken.

A 403 or 429 is reported as a warning, not a failure: those statuses come from
hosts that block bots, and a bot-blocked page is not a dead page. Everything
else — a 4xx/5xx, a DNS failure, a timeout — fails the run.

Usage::

    uv run python scripts/check_external_links.py
"""

from __future__ import annotations

import argparse
import http.client
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent

# The documents named by
# tests/test_public_docs.py::PublicDocumentationNavigationTests::
# test_current_guide_relative_links_resolve. That test pins this set for the
# repository-relative half; tests/test_check_external_links.py pins the copy
# here so the two cannot drift apart silently.
DOCUMENTS: tuple[str, ...] = (
    "README.md",
    "README.zh-CN.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "docs/README.md",
    "docs/evidence-status.md",
    "docs/operating-guide.md",
    "docs/portfolio-case-study.md",
    "docs/experiment-index.md",
)

# Markdown links and images: "](https://…)", "](<https://…>)". The target may
# not contain a closing bracket or whitespace; a fragment is part of the URL.
LINK = re.compile(r"\]\(\s*<?(https?://[^)\s>]+)>?")

DEFAULT_TIMEOUT = 10.0
DEFAULT_DELAY = 0.5
BOT_BLOCKED = frozenset({403, 429})
USER_AGENT = (
    "academic-commercialization-agent external link check "
    "(+https://github.com/shuxiachai/academic-commercialization-agent)"
)

Fetcher = Callable[[str, float], "tuple[int | None, str | None]"]


@dataclass(frozen=True)
class Link:
    """One external URL and the guides that link to it."""

    url: str
    documents: tuple[str, ...]


@dataclass(frozen=True)
class Result:
    """What requesting one link produced."""

    url: str
    documents: tuple[str, ...]
    status: int | None
    error: str | None

    @property
    def severity(self) -> str:
        if self.status is None or (self.status >= 400 and self.status not in BOT_BLOCKED):
            return "failure"
        if self.status in BOT_BLOCKED:
            return "warning"
        return "ok"


def collect_links(root: Path, documents: Iterable[str]) -> list[Link]:
    """Return every distinct external URL, with the documents that carry it.

    Order is deterministic (by URL) so two runs compare line by line.
    """
    found: dict[str, list[str]] = {}
    for relative in documents:
        text = (root / relative).read_text(encoding="utf-8")
        for url in LINK.findall(text):
            carriers = found.setdefault(url, [])
            if relative not in carriers:
                carriers.append(relative)
    return [
        Link(url=url, documents=tuple(sorted(carriers)))
        for url, carriers in sorted(found.items())
    ]


def fetch_status(url: str, timeout: float) -> tuple[int | None, str | None]:
    """Request one URL and return ``(status, error)``; exactly one is set.

    The body is not read: only the status line matters, and a badge or a long
    page would otherwise cost the whole transfer.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), None
    except urllib.error.HTTPError as exc:  # a status was returned; it is just an error one
        return int(exc.code), None
    except urllib.error.URLError as exc:
        return None, str(exc.reason)
    except TimeoutError:
        return None, f"no response within {timeout:g}s"
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    except http.client.HTTPException as exc:
        return None, f"{type(exc).__name__}: {exc}"


def check_links(
    links: Sequence[Link],
    *,
    fetcher: Fetcher = fetch_status,
    timeout: float = DEFAULT_TIMEOUT,
    delay: float = DEFAULT_DELAY,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Result]:
    """Request every link, pausing between two requests to the same host."""
    last_request: dict[str, float] = {}
    results: list[Result] = []
    for link in links:
        host = urlsplit(link.url).netloc.lower()
        previous = last_request.get(host)
        if previous is not None:
            remaining = delay - (clock() - previous)
            if remaining > 0:
                sleep(remaining)
        status, error = fetcher(link.url, timeout)
        last_request[host] = clock()
        results.append(Result(url=link.url, documents=link.documents, status=status, error=error))
    return results


def _describe(result: Result) -> str:
    return f"{result.status}" if result.status is not None else f"no response ({result.error})"


def report(results: Sequence[Result], *, stream: TextIO = sys.stdout) -> int:
    """Print the broken links and return the process exit code."""
    failures = [result for result in results if result.severity == "failure"]
    warnings = [result for result in results if result.severity == "warning"]
    for result in failures:
        print(f"FAIL {_describe(result)} {result.url}", file=stream)
        print(f"     linked from: {', '.join(result.documents)}", file=stream)
    for result in warnings:
        print(f"WARN {_describe(result)} {result.url} (bot-blocked host, not a failure)", file=stream)
        print(f"     linked from: {', '.join(result.documents)}", file=stream)
    print(
        f"checked {len(results)} unique links: {len(failures)} failed, {len(warnings)} warned",
        file=stream,
    )
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds per request")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="seconds between requests to one host")
    args = parser.parse_args(argv)

    links = collect_links(ROOT, DOCUMENTS)
    started = time.monotonic()
    results = check_links(links, timeout=args.timeout, delay=args.delay)
    exit_code = report(results)
    print(f"finished in {time.monotonic() - started:.1f}s", file=sys.stdout)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
