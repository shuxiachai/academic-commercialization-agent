"""Who holds a patent, from its Google Patents page, for patent rows web search returns without one.

Web search gives a patent row no applicant. In 66 of 69 saved runs the patent
list named none, and each row's publisher was the site: "Google", "Wipo" or
"Justia". Who holds a patent is often what a commercialization reader needs
most: the competitor, or the party to license from.

Every Google Patents page names its current and original assignees in the
header block. In the 276 pages checked, that block always ended within the
first 256 KB, so only that much is read.

The current assignee is used, or the original when none is listed, because
it is the party to approach now. "Individual" means the patent is owned by
its inventor: it is never listed as a company, and the inventors are named
instead. Google warns that its assignee list may be inaccurate, so a source
records where the name came from.

The same header states the patent's dates. Web search gave a patent row no
date either: 44% of the 4,091 patent rows in the saved registries had none,
and the rest carried the year read out of the publication number as
1 January. On 60 of those pages sampled on 2026-10-29, every one stated a
publication date inside the bytes already read, none of the 30 existing dates
matched it exactly, and 10 of the 30 had the wrong year. The page's
publication date therefore replaces whatever the row had.
"""

from __future__ import annotations

import html as html_lib
import re
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, build_opener

from academic_agent.evidence import _NoRedirectHandler, _validate_public_url
from academic_agent.patent_family import publication_number

MAX_BYTES = 256 * 1024
TIMEOUT_SECONDS = 8
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AcademicAgentEvidenceVerifier/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}
_INDIVIDUAL = "individual"
# The header lists each assignee as its own <dd> straight after the <dt> label.
# Citation and similar-document tables also carry assigneeOriginal, but in
# <td> cells, so anchoring on the label keeps them out.
_BLOCKS = {
    kind: re.compile(rf'<dt>{label}[^<]*</dt>((?:\s*<dd itemprop="{prop}"[^>]*>[^<]*</dd>)+)')
    for kind, label, prop in (("current", "Current Assignee", "assigneeCurrent"),
                              ("original", "Original Assignee", "assigneeOriginal"),
                              ("inventors", "Inventor", "inventor"))
}
_DD_TEXT = re.compile(r">([^<]*)</dd>")
# <time itemprop="publicationDate" datetime="2024-03-26">, in the header's date list.
_DATES = re.compile(r'itemprop="(publicationDate|priorityDate|filingDate)"[^>]*\bdatetime="(\d{4}-\d{2}-\d{2})"')


def google_patents_url(url: str | None) -> str | None:
    """The Google Patents page for a Google Patents, Patentscope WO or Justia patent URL."""
    number = publication_number(url)
    return f"https://patents.google.com/patent/{number}/en" if number else None


def assignees_from_html(html: str) -> dict[str, list[str]]:
    """{"current", "original", "inventors": [...]} from the page's header block, in page order."""
    found: dict[str, list[str]] = {}
    for kind, pattern in _BLOCKS.items():
        match = pattern.search(html)
        names = [" ".join(html_lib.unescape(text).split()) for text in _DD_TEXT.findall(match[1])] if match else []
        found[kind] = list(dict.fromkeys(name for name in names if name))
    return found


def applicants(html: str) -> tuple[list[str], str]:
    """(names, status): companies or institutions ("named"), the inventors of an
    inventor-owned patent ("individual"), or nothing ("none")."""
    found = assignees_from_html(html)
    listed = found["current"] or found["original"]
    names = [name for name in listed if name.lower() != _INDIVIDUAL]
    if names:
        return names, "named"
    if listed:
        return found["inventors"], "individual"
    return [], "none"


def patent_dates(html: str) -> dict[str, date]:
    """{"publication" | "priority" | "filing": date} from the header's dated <time> tags.

    The first statement of each kind wins; a malformed date is left out rather
    than guessed, so a row keeps whatever it had.
    """
    found: dict[str, date] = {}
    for kind, text in _DATES.findall(html):
        key = kind.removesuffix("Date")
        if key in found:
            continue
        try:
            found[key] = date.fromisoformat(text)
        except ValueError:
            continue
    return found


def fetch_head(url: str) -> str | None:
    """The page's first MAX_BYTES as text, following only public redirects."""
    opener = build_opener(_NoRedirectHandler)
    current = url
    for _ in range(5):
        safe, _reason = _validate_public_url(current)
        if not safe:
            return None
        try:
            with opener.open(Request(current, headers=_HEADERS), timeout=TIMEOUT_SECONDS) as response:
                if "html" not in (response.headers.get("Content-Type") or "").lower():
                    return None
                raw = response.read(MAX_BYTES)
                return raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        except HTTPError as exc:
            location = exc.headers.get("Location") if exc.code in {301, 302, 303, 307, 308} else None
            if not location:
                return None
            current = urljoin(current, location)
        except (URLError, TimeoutError, OSError, ValueError, LookupError):
            return None
    return None


def patent_page_facts(url: str) -> tuple[list[str], str, dict[str, date]]:
    """(names, status, dates) for a patent URL, from one read of its Google Patents page.

    status adds "unreadable" and "no_number"; dates is empty in both cases.
    """
    page_url = google_patents_url(url)
    if page_url is None:
        return [], "no_number", {}
    html = fetch_head(page_url)
    if html is None:
        return [], "unreadable", {}
    names, status = applicants(html)
    return names, status, patent_dates(html)


def patent_applicants(url: str) -> tuple[list[str], str]:
    """(names, status) for a patent URL; status adds "unreadable" and "no_number"."""
    names, status, _dates = patent_page_facts(url)
    return names, status
