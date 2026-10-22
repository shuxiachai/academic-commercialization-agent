"""Whether two patent search results are one invention, from their titles and URLs alone.

Web search returns one row per publication, so one invention can take several
patent slots when it was filed in several offices, or published as an
application and then granted. In one held-out run, five of eight slots held
the same psilocybin treatment, filed in AU, EP, US, CA and WO.

The existing duplicate check compared whole titles. Google Patents titles
carry the publication number ("US9422922B2 - ... - Google Patents"), so no
two family members ever matched.

Two rows are one invention when either holds:
- they are the same publication: the same number without its kind code, from
  any host;
- their titles match once publication numbers and the site name are removed,
  and their numbers come from different offices, or are an application and a
  grant (A vs B kind). A truncated title ("...") of at least four words may
  match the start of the other.

Two same-kind publications from one office with one title, such as two
Chinese grants or two US applications, are kept apart. In development these
were different inventions, from different applicants or years.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

_NUMBER_PARTS = re.compile(r"^([A-Z]{2})(\d+)([A-Z]\d?)?$")
_NUMBER_IN_TITLE = re.compile(r"\b[A-Z]{2}\d{4,}[A-Z]?\d?\b")
# " - Google Patents", including the cut-off forms search titles end with.
_SITE_SUFFIX = re.compile(
    r"\s+-\s+G(?:o(?:o(?:g(?:l(?:e(?:\s+P(?:a(?:t(?:e(?:n(?:t(?:s)?)?)?)?)?)?)?)?)?)?)?)?\s*$")
_GOOGLE_PATH = re.compile(r"^/patent/([A-Z]{2}\d+[A-Z]?\d?)(?:/|$)")
_JUSTIA_PATH = re.compile(r"^/patent/(\d{7,11})(?:/|$)")
_WO_NUMBER = re.compile(r"WO\d{10}")
_WORD = re.compile(r"[a-z0-9]+")
_MIN_TRUNCATED_WORDS = 4


def publication_number(url: str | None) -> str | None:
    """The publication number a patent URL points at, with its kind code when the URL has one."""
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if host == "patents.google.com":
        match = _GOOGLE_PATH.match(parts.path)
        return match[1] if match else None
    if host == "patentscope.wipo.int":
        # Only WO numbers: other docIds there are internal record ids.
        match = _WO_NUMBER.search(parse_qs(parts.query).get("docId", [""])[0] or parts.path)
        return match[0] if match else None
    if host == "patents.justia.com":
        match = _JUSTIA_PATH.match(parts.path)
        return f"US{match[1]}" if match else None
    return None


def _parts(number: str | None) -> tuple[str, str, str] | None:
    match = _NUMBER_PARTS.match(number or "")
    return (match[1], match[2], match[3] or "") if match else None


def title_key(title: str) -> tuple[str, bool]:
    """(the title's words without numbers or site name, whether the title was cut off)."""
    text = _NUMBER_IN_TITLE.sub(" ", _SITE_SUFFIX.sub("", title))
    return " ".join(_WORD.findall(text.lower())), text.rstrip().endswith(("...", "…"))


def titles_match(a: str, b: str) -> bool:
    (key_a, cut_a), (key_b, cut_b) = title_key(a), title_key(b)
    if not key_a or not key_b:
        return False
    if key_a == key_b:
        return True
    (short, cut), long_ = ((key_a, cut_a), key_b) if len(key_a) <= len(key_b) else ((key_b, cut_b), key_a)
    return cut and len(short.split()) >= _MIN_TRUNCATED_WORDS and (long_ + " ").startswith(short + " ")


def _offices_differ(a: tuple[str, str, str], b: tuple[str, str, str]) -> bool:
    if a[0] != b[0]:
        return True
    return bool(a[2] and b[2] and a[2][0] != b[2][0])


def same_invention(title_a: str, url_a: str | None, title_b: str, url_b: str | None) -> bool:
    """Whether two patent rows are one invention under the rule above."""
    a, b = _parts(publication_number(url_a)), _parts(publication_number(url_b))
    if a is None or b is None:
        return False
    if a[:2] == b[:2]:
        return True
    return titles_match(title_a, title_b) and _offices_differ(a, b)
