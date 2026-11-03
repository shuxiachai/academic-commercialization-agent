"""Publication dates from a page's own metadata, for sources search returned undated.

Web search gives market sources no date: none of the 229 market sources in
the held-out v2 runs had one, so every report listed them as "n.d." and a
2021 hiring announcement read like current news. Many pages state their
publication date in machine-readable metadata. This reads only those
explicit statements, never prose:

- JSON-LD ``datePublished`` (any object, including inside ``@graph``);
- publication-time ``<meta>`` tags (``article:published_time`` and the like);
- ``itemprop="datePublished"`` on an element;
- a full ``/YYYY/MM/DD/`` date in the URL path.

Modification dates are not publication dates and are ignored, as are
partial dates (a year, or a year and month), which would have to be
invented into a day. A date after the access date, or before 1990, is
treated as malformed. Fetching follows the same public-address rules as
the URL check: every redirect hop must be a public HTTP(S) host.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener

from academic_agent.evidence import _NoRedirectHandler, _validate_public_url

MAX_BYTES = 768 * 1024
TIMEOUT_SECONDS = 8
_EARLIEST = date(1990, 1, 1)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AcademicAgentEvidenceVerifier/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}
_META_NAMES = frozenset({
    "article:published_time", "og:article:published_time", "article.published", "published_time",
    "datepublished", "date.published", "pubdate", "publishdate", "publish-date", "publish_date",
    "dc.date.issued", "dcterms.issued", "citation_publication_date", "parsely-pub-date", "sailthru.date",
})
_ISO_DATE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:$|[T\s])")
_URL_DATE = re.compile(r"/((?:19|20)\d{2})/(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])(?:/|$)")


# Pages whose stated publication date describes the page, not its content:
# a market-report landing page keeps its first date while its forecast years
# move on, an encyclopedia entry dates its creation, a home page dates the site.
_UNDATABLE_TYPES = frozenset({"market_report"})
_UNDATABLE_HOSTS = ("wikipedia.org",)


def should_date(source_type: str | None, url: str | None) -> bool:
    """Whether a source's page metadata may supply its publication date."""
    if not url or source_type in _UNDATABLE_TYPES:
        return False
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in _UNDATABLE_HOSTS):
        return False
    return bool(parts.path.strip("/"))


def _parse(value: object, accessed: date) -> date | None:
    match = _ISO_DATE.match(str(value or ""))
    if match is None:
        return None
    try:
        parsed = date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        return None
    return parsed if _EARLIEST <= parsed <= accessed else None


class _DateTags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: list[str] = []
        self.itemprop: list[str] = []
        self.json_ld: list[str] = []
        self._in_json_ld = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            name = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if name in _META_NAMES and a.get("content"):
                self.meta.append(a["content"])
        elif a.get("itemprop", "").lower() == "datepublished":
            self.itemprop.append(a.get("datetime") or a.get("content") or "")
        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self.json_ld.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_json_ld = False

    def handle_data(self, data):
        if self._in_json_ld:
            self.json_ld[-1] += data


def _json_ld_dates(blocks: list[str]) -> list[object]:
    found: list[object] = []

    def walk(node):
        if isinstance(node, dict):
            if "datePublished" in node:
                found.append(node["datePublished"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for block in blocks:
        try:
            walk(json.loads(block))
        except (ValueError, RecursionError):
            continue
    return found


def date_from_html(html: str, url: str, accessed: date) -> tuple[date | None, str]:
    """(date, method) from page metadata, or (None, "none")."""
    tags = _DateTags()
    try:
        tags.feed(html)
    except Exception:  # noqa: BLE001 - malformed markup yields no date, never an error
        return None, "none"
    for method, values in (("json_ld", _json_ld_dates(tags.json_ld)), ("meta", tags.meta),
                           ("itemprop", tags.itemprop)):
        for value in values:
            parsed = _parse(value, accessed)
            if parsed is not None:
                return parsed, method
    return date_from_url(url, accessed)


def date_from_url(url: str, accessed: date) -> tuple[date | None, str]:
    match = _URL_DATE.search(urlsplit(url).path)
    if match is None:
        return None, "none"
    parsed = _parse(f"{match[1]}-{match[2]}-{match[3]}", accessed)
    return (parsed, "url_path") if parsed is not None else (None, "none")


def fetch_html(url: str) -> str | None:
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
                charset = response.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        except HTTPError as exc:
            location = exc.headers.get("Location") if exc.code in {301, 302, 303, 307, 308} else None
            if not location:
                return None
            current = urljoin(current, location)
        except (URLError, TimeoutError, OSError, ValueError, LookupError):
            return None
    return None


def page_publication_date(url: str, accessed: date | None = None) -> tuple[date | None, str]:
    """(date, method) for a URL; the URL path alone when the page cannot be read."""
    accessed = accessed or datetime.now().date()
    html = fetch_html(url)
    if html is None:
        return date_from_url(url, accessed)
    return date_from_html(html, url, accessed)
