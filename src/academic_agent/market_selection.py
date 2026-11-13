"""Which market sources are one story, and how many slots one site may hold.

Measured on the 95 saved runs since 2026-10-01 that list market sources
(``scripts/audits/market_evidence_audit.py``): a story was listed twice in
27 runs, usually as two addresses of one Yahoo Finance page or as the copies
two aggregators carry, and one site held three or more of a run's market
slots in 41 runs. The report then counted one announcement as two pieces of
evidence, and "market evidence" meant what one aggregator carried.

This module decides two things for the market stage of ``source_pipeline``
and for the offline audit, which replays the same code on saved registries:

- ``same_story``: whether two results are copies of one item;
- ``site_of``: which site a result belongs to, for the per-site share.

Both are precision-first, as every heuristic here must be: a source wrongly
called a copy is evidence the run never reads. A similar title alone is
therefore never enough. Market-research firms title their reports alike
("X Market Size, Share & Trends Report, 2034") while stating different
numbers: of the 95 pairs with alike titles in those runs, 62 were different
sources. Two different releases by one company also share their closing
"About the company" paragraph, so shared text alone is not enough either. A
pair is one story only when its address says so, or when one headline comes
with a second, independent sign.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from os.path import commonprefix
from urllib.parse import urlsplit

# One site may hold this many of a run's market slots before further results
# from it wait for a slot nothing else filled. The number is the maintainer's
# choice (2026-11-13), not a measured optimum: of 698 saved market sources
# since 2026-10-01, 65 were a site's third or later.
MARKET_SOURCES_PER_SITE = 2

# Country-code suffixes under which organisations register one level down,
# so the site is the last three labels, not the last two. Deliberately a short
# list of the suffixes market results actually come from, not the Public
# Suffix List. An unlisted suffix groups unrelated ".co.xx" sites as one site:
# the third result among them is then held back, and still listed if nothing
# else fills its slot.
_TWO_LABEL_SUFFIXES = frozenset({
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "org.au", "net.au", "gov.au",
    "edu.au", "co.jp", "or.jp", "ne.jp", "go.jp", "ac.jp", "com.cn", "org.cn",
    "net.cn", "gov.cn", "edu.cn", "co.in", "org.in", "gov.in", "ac.in", "co.kr",
    "or.kr", "go.kr", "com.br", "com.sg", "com.hk", "com.tw", "co.nz", "co.za",
    "com.mx", "com.tr", "co.il", "com.my", "co.id", "com.ar",
    # Each EU body publishes under its own name here (ema., ec., eur-lex.).
    "europa.eu",
    # Hosting platforms: every name under them is a different publisher.
    "github.io", "gitlab.io", "substack.com", "wordpress.com", "blogspot.com",
    "medium.com", "notion.site", "wixsite.com", "webflow.io", "netlify.app",
    "vercel.app", "pages.dev", "readthedocs.io", "sharepoint.com",
})

# Hosts that carry other parties' releases under the original headline. A
# headline found on one of them is expected to exist elsewhere too.
_SYNDICATION_SITES = frozenset({
    "yahoo.com", "businessinsider.com", "stocktitan.net", "otcmarkets.com",
    "marketscreener.com", "morningstar.com", "benzinga.com", "nasdaq.com",
    "marketwatch.com", "investing.com", "streetinsider.com", "seekingalpha.com",
    "barchart.com", "advfn.com", "finanznachrichten.de", "tmcnet.com",
    "openpr.com", "einnews.com",
})
# Press wires: the release as its issuer distributed it.
_WIRE_SITES = frozenset({
    "prnewswire.com", "businesswire.com", "globenewswire.com", "newswire.ca",
    "accesswire.com", "newsfilecorp.com", "einpresswire.com", "prweb.com",
    "prnewswire.co.uk",
})
# Sites that republish another publisher's documents whole, under the same
# title: the copy's site -> the original's.
_MIRROR_OF = {"everycrsreport.com": "congress.gov"}

_WORD = re.compile(r"[a-z0-9]+")
# A site name set off after the headline: " | Markets Insider", " - Wikipedia".
_TITLE_TAIL = re.compile(r"\s+[|\u2013\u2014-]\s+(?!.*\s[|\u2013\u2014-]\s)(.*)$")
_TITLE_TAIL_MAX_WORDS = 4
_ELLIPSIS = re.compile(r"\s*(?:\.{3}|\u2026)\s*$")

# An article address ends in a slug this long; shorter final segments
# ("index.html", "news", "overview") recur across a site's sections.
_SLUG_MIN_CHARS = 20
# Yahoo Finance posts one release under several numeric ids
# (".../slb-ormat-partner-accelerate-integrated-130000995.html" and
# "...-130000034.html"). Only an id this long is set aside when comparing
# slugs: a short "-2" is what a site appends to a second, different article.
_SLUG_ID = re.compile(r"[-_]\d{6,}$")
_SLUG_EXTENSION = re.compile(r"\.[a-z0-9]{2,5}$")
# Aggregators build an article's address from the release's headline
# ("/news/ORA/slb-and-ormat-partner-to-accelerate-integrated-geothermal-asset-...")
# even when they print a rewritten one. This many leading characters of
# headline, letters and digits only, must match for the address to count as
# carrying it: two releases by one company part ways well before that.
_HEADLINE_IN_SLUG_MIN_CHARS = 40
# A headline this short ("Company Overview", "Press Releases") recurs by chance.
_HEADLINE_MIN_WORDS = 5
# A truncated headline must still be this long to count as the same one.
_TRUNCATED_MIN_WORDS = 6
# Shared wording is counted in runs of this many words: long enough that a
# shared run is copied text, not a common phrase.
_SHINGLE_WORDS = 6
# Two copies of one release share much of what search excerpted from each:
# the 23 pairs merged by headline across every saved run shared at least 0.32
# of the shorter excerpt. Two different releases share only boilerplate,
# which one headline already rules out, so this bound has only to exclude
# chance. No saved pair with one headline fell between 0.05 and 0.32, so the
# data does not fix where in that gap the bound belongs.
_SHARED_TEXT_MIN = 0.15
# A release syndicated the next morning, read in another time zone.
_SAME_DAY_TOLERANCE = 2


@dataclass(frozen=True)
class MarketItem:
    """What the rules read of one market result."""

    title: str
    url: str
    summary: str = ""
    published: date | None = None


def item_of(source: object) -> MarketItem:
    """The rule's view of an ``EvidenceSource``."""
    url = getattr(source, "url", None)
    return MarketItem(
        title=str(getattr(source, "title", "") or ""),
        url=str(url) if url else "",
        summary=str(getattr(source, "evidence_summary", "") or ""),
        published=getattr(source, "published_date", None),
    )


def site_of(url: str) -> str:
    """The site a URL belongs to: its registrable domain, lower case.

    Regional and section hosts of one publisher (``uk.finance.yahoo.com``,
    ``ca.finance.yahoo.com``, ``www.``) are that publisher's site. Returns
    "" for a URL with no host.
    """
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if not host:
        return ""
    labels = host.split(".")
    if len(labels) <= 2 or labels[-1].isdigit():
        return host
    if ".".join(labels[-2:]) in _TWO_LABEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def provenance_rank(url: str) -> int:
    """How close a copy is to the release's issuer: lower is closer.

    0 is any site not known to carry other parties' releases (the issuer's own
    page, an original publisher), 1 a press wire, 2 a host that syndicates.
    A rank says which of two copies of one story to keep; it is not a
    credibility tier and nothing else reads it.
    """
    site = site_of(url)
    if site in _SYNDICATION_SITES or site in _MIRROR_OF:
        return 2
    if site in _WIRE_SITES:
        return 1
    return 0


def prefer(candidate: MarketItem, kept: MarketItem) -> bool:
    """Whether ``candidate`` should replace ``kept`` as the copy of their story.

    Only a strictly better copy replaces the one already listed: one closer
    to the issuer, or, on the same site, the publisher's main host rather than
    a regional one (``finance.yahoo.com`` over ``uk.finance.yahoo.com``).
    """
    new_rank, old_rank = provenance_rank(candidate.url), provenance_rank(kept.url)
    if new_rank != old_rank:
        return new_rank < old_rank
    if site_of(candidate.url) != site_of(kept.url):
        return False
    new_host = (urlsplit(candidate.url).hostname or "").lower().removeprefix("www.")
    old_host = (urlsplit(kept.url).hostname or "").lower().removeprefix("www.")
    return new_host.count(".") < old_host.count(".")


def _path(url: str) -> str:
    return urlsplit(url).path.rstrip("/").lower()


def _slug(url: str) -> str:
    """The final path segment, lower case, without a file extension."""
    path = urlsplit(url).path.rstrip("/")
    return _SLUG_EXTENSION.sub("", path.rsplit("/", 1)[-1].lower())


def _headline(title: str) -> tuple[tuple[str, ...], bool]:
    """A title's words without a trailing site name, and whether it was cut."""
    text = title.strip()
    cut = bool(_ELLIPSIS.search(text))
    text = _ELLIPSIS.sub("", text)
    tail = _TITLE_TAIL.search(text)
    if tail and len(_WORD.findall(tail.group(1).lower())) <= _TITLE_TAIL_MAX_WORDS:
        head = text[:tail.start()]
        if _WORD.search(head.lower()):
            text = head
            cut = cut or bool(_ELLIPSIS.search(text))
            text = _ELLIPSIS.sub("", text)
    return tuple(_WORD.findall(text.lower())), cut


def _same_headline(first: str, second: str) -> bool:
    """One headline, allowing a site name after it and a cut-off ending."""
    a, a_cut = _headline(first)
    b, b_cut = _headline(second)
    if len(a) < _HEADLINE_MIN_WORDS or len(b) < _HEADLINE_MIN_WORDS:
        return False
    if a == b:
        return True
    short, long_, short_cut = (a, b, a_cut) if len(a) <= len(b) else (b, a, b_cut)
    return short_cut and len(short) >= _TRUNCATED_MIN_WORDS and long_[:len(short)] == short


def _headline_in_address(title: str, url: str) -> bool:
    """Whether a URL's slug opens with the same characters as a headline."""
    words, _cut = _headline(title)
    headline = "".join(words)
    slug = "".join(_WORD.findall(_slug(url)))
    return len(commonprefix([headline, slug])) >= _HEADLINE_IN_SLUG_MIN_CHARS


def _one_headline(first: MarketItem, second: MarketItem) -> bool:
    return (
        _same_headline(first.title, second.title)
        or _headline_in_address(first.title, second.url)
        or _headline_in_address(second.title, first.url)
    )


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = _WORD.findall(text.lower())
    return {tuple(words[i:i + _SHINGLE_WORDS]) for i in range(len(words) - _SHINGLE_WORDS + 1)}


def shared_text(first: str, second: str) -> float:
    """Share of the shorter excerpt's six-word runs that the other also has."""
    a, b = _shingles(first), _shingles(second)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def same_story(first: MarketItem, second: MarketItem) -> str:
    """Why two market results are copies of one item, or "" if not shown to be.

    One of three signs, each sufficient:

    - ``same address``: one site and the same article path, whatever the
      regional host or the query string; or one site and the same slug ending
      in a long numeric id, whatever the directory; or one site, the same
      headline, and slugs that differ only in that id;
    - ``mirror``: a site that republishes another's documents whole, carrying
      the same headline as the original's site;
    - ``same headline``: one headline on two pages of which at least one is a
      host that carries other parties' releases, confirmed either by both
      pages' dates falling together or, when a date is missing, by shared
      wording in the two excerpts. The headline is one when the titles are
      identical or when one page's address is built from the other's title.

    Two dated pages more than two days apart are never one story by headline:
    recurring releases reuse theirs. An identical headline with neither sign
    is left alone, as is every pair of similar but not identical titles.
    """
    site_a, site_b = site_of(first.url), site_of(second.url)
    if not site_a or not site_b:
        return ""
    same_title = _same_headline(first.title, second.title)
    if site_a == site_b:
        slug_a, slug_b = _slug(first.url), _slug(second.url)
        # The slug alone is not the article: a site files each year's release
        # under the same one (".../2025/third-quarter-financial-results" and
        # ".../2026/..."). The whole path must match, unless the slug carries
        # an id of its own, which names one article wherever it is filed.
        if slug_a == slug_b and len(slug_a) >= _SLUG_MIN_CHARS and (
            _path(first.url) == _path(second.url) or _SLUG_ID.search(slug_a)
        ):
            return "same address"
        stem_a, stem_b = _SLUG_ID.sub("", slug_a), _SLUG_ID.sub("", slug_b)
        if (
            same_title
            and stem_a == stem_b
            and len(stem_a) >= _SLUG_MIN_CHARS
            and stem_a != slug_a
            and stem_b != slug_b
        ):
            return "same address"
    if same_title and (_MIRROR_OF.get(site_a) == site_b or _MIRROR_OF.get(site_b) == site_a):
        return "mirror"
    carriers = _SYNDICATION_SITES | _WIRE_SITES
    if site_a not in carriers and site_b not in carriers:
        return ""
    if not _one_headline(first, second):
        return ""
    if first.published is not None and second.published is not None:
        apart = abs((first.published - second.published).days)
        return "same headline" if apart <= _SAME_DAY_TOLERANCE else ""
    if shared_text(first.summary, second.summary) >= _SHARED_TEXT_MIN:
        return "same headline"
    return ""
