"""Which market sources are one story, and how many slots one site or one issuer may hold.

Measured on the 95 saved runs since 2026-10-01 that list market sources
(``scripts/audits/market_evidence_audit.py``): a story was listed twice in
27 runs, usually as two addresses of one Yahoo Finance page or as the copies
two aggregators carry, and one site held three or more of a run's market
slots in 41 runs. The report then counted one announcement as two pieces of
evidence, and "market evidence" meant what one aggregator carried.

This module decides three things for the market stage of ``source_pipeline``
and for the offline audit, which replays the same code on saved registries:

- ``same_story``: whether two results are copies of one item;
- ``site_of``: which site a result belongs to, for the per-site share;
- ``same_issuer`` and ``issuer_mates``: whether results on different sites
  have one issuer, for the per-issuer share (the second half of this file).

All are precision-first, as every heuristic here must be: a source wrongly
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


# ── Who issued a release ────────────────────────────────────────────────────
#
# The site share above cannot see that one company wrote three releases when
# three different hosts carry them: three Helio releases held three of eight
# market slots in a run of 2026-11-15, on businessinsider.com, otcmarkets.com
# and stocktitan.net. An issuer therefore has a share of its own, counted
# wherever its releases are carried. Measured on the 132 saved runs since
# 2026-10-01: one issuer held three slots in 8 runs and two in 33
# (docs/results-2026-11-17-market-issuer-share.md).
#
# Who issued a page is read only from what a release states about itself:
# the stock symbol a carrier files it under and the name printed beside that
# symbol, the symbol or the name that opens the release after the wire's
# mark, the name it gives itself beside "the Company", and the research firm
# a market-report release credits. A company merely mentioned is not an issuer:
# market-report releases list a dozen "key players" with their symbols, and
# every joint announcement names a partner. Each sign is exact. A firm's name
# found somewhere inside a longer run of words is not one: matched that way,
# spacesolar.co.uk became the issuer of a release about "BiLight Space Solar
# Technology".
#
# The number is the maintainer's choice, the same as a site's (2026-11-17).
# At 2 the share holds back 8 of 967 saved sources; at 1 it holds back 53.
MARKET_SOURCES_PER_ISSUER = 2

_EXCHANGES = (
    r"NYSE(?:\s+American|\s+Arca)?|NASDAQ|Nasdaq(?:GS|GM|CM)?|OTCID|OTCQB|OTCQX|OTC(?:\s+Markets|\s+Pink)?"
    r"|TSX|TSXV|TSX-V|CSE|NEO|LSE|AIM|ASX|HKEX|SEHK|SGX|FRA|FSE|XETRA|Euronext(?:\s+[A-Z][a-z]+)?"
    r"|KRX|KOSDAQ|TASE|NZX|JSE"
)
# "(NYSE: ORA)", "(Nasdaq: ARQQ, ARQQW)", and the same inside a markdown link.
_SYMBOL = re.compile(rf"\(\s*(?:{_EXCHANGES})\s*:\s*\[?([A-Z0-9][A-Z0-9.]{{0,5}})\b")
# The mark a wire prints between a release's dateline and its first sentence.
_WIRE_MARK = re.compile(
    r"\(GLOBE NEWSWIRE\)\s*--|/PRNewswire(?:-[A-Za-z]+)?/\s*--|\(BUSINESS WIRE\)\s*--|/CNW/\s*--?"
    r"|\(ACCESSWIRE\)\s*--|\(Newsfile Corp\.\s*-\s*[^)]{4,30}\)\s*-|/EINPresswire\.com/\s*--"
)
# How much of the text after the mark is the release's opening: its issuer is
# named there, and the companies it goes on to discuss are not.
_OPENING_CHARS = 240
# Search excerpts join the passages they quote with this; what follows it is
# from somewhere else in the page.
_EXCERPT_GAP = "[...]"
# A release defines its issuer: (NYSE: X) ("Name" or the "Company").
_SELF_NAMED = re.compile(
    rf"\(\s*(?:{_EXCHANGES})\s*:\s*\[?([A-Z0-9][A-Z0-9.]{{0,5}})\b[^()]{{0,40}}\)[^()]{{0,6}}"
    r"(?:\([^()]{0,40}\)[^()]{0,6}){0,3}\([^()]{0,60}the\s+[\u201c\"]Company[\u201d\"][^()]{0,40}\)"
)
# The name it gives itself there, in quotation marks beside "the Company".
_QUOTED = re.compile(r"[“\"]([^“”\"]{2,40})[”\"]")
# Carriers that file a release under its issuer's symbol:
# stocktitan.net/news/HLEO/..., otcmarkets.com/stock/HLEO/news/...
_SYMBOL_IN_ADDRESS = {
    "stocktitan.net": re.compile(r"^/news/([A-Za-z0-9.]{1,6})/"),
    "otcmarkets.com": re.compile(r"^/stock/([A-Za-z0-9.]{1,6})/news/"),
}
# ...and print the issuer's name beside that symbol in the page's title:
# "Helio Corporation (HLEO) enters space-based solar power | HLEO Stock News",
# "Helio Sees ... | HLEO - Helio Corporation | News". The name is taken only
# next to the symbol the address is filed under. In the run of 2026-11-15
# nothing else named Helio: search had excerpted the middle of two releases,
# and the third opened "On January 6, 2026, the Board of Directors of".
_NAME_BESIDE_SYMBOL = (
    r"^([A-Z][^()|]{1,60}?)\s*\(\s*{symbol}\s*\)",
    r"\|\s*{symbol}\s+-\s+([^|]{2,60}?)\s*\|[^|]*$",
)
_COMPANY_FORM = r"(?:Inc|Corp|Corporation|Ltd|Limited|plc|PLC|LLC|Co|AG|SA|NV|ASA|AB|GmbH)\b\.?"
# The name that opens a release: one to five capitalised words, then a comma,
# a bracket or the verb. Anything looser reads "Leading geothermal company X"
# or "New results published in" as a name.
_OPENING_NAME = re.compile(
    r"^((?:[A-Z][\w&.'\u2019-]*)(?:\s+[A-Z][\w&.'\u2019-]*){0,4}?)"
    rf"(?:,?\s+{_COMPANY_FORM})*"
    r"\s*(?:,|\(|today\b|announced\b|announces\b)"
)
_NOT_A_NAME = frozenset({
    "today", "the", "a", "an", "new", "according", "leading", "in", "on", "as", "with", "global",
})
_TRAILING_FORM = re.compile(rf"(?:,?\s+{_COMPANY_FORM})+\s*$")
# The firm a market-report release credits in its opening: "According to the
# SNS Insider,", "As per the SNS Insider report", "a new report published by
# Verified Market Research". The phrase is matched in any case; the name must
# be capitalised words.
_CREDIT_PHRASE = re.compile(
    r"(?i:according\s+to|as\s+per|published\s+by|(?:report|study|research|analysis)\s+(?:from|by))\s+"
    r"(?i:(?:the|a|an)\s+)?(?i:(?:latest|new|recent|comprehensive)\s+){0,2}"
    r"(?i:(?:study|report|research|analysis)\s+(?:published\s+by|from|by)\s+)?"
    r"((?:[A-Z][\w&.]*)(?:\s+[A-Z][\w&.]*){0,4})"
)
# ResearchAndMarkets.com announces each report it adds in one sentence.
_RESELLER_PHRASE = re.compile(r"added\s+to\s+ResearchAndMarkets\.com'?s\s+offering", re.IGNORECASE)
_RESELLER = "researchandmarkets"
# The firm set off at the end of a headline: "| SNS Insider", "| Research by
# SNS Insider", "- Transparency Market Research Inc.", ": Verified Market
# Research". A hyphen counts only before a space: "Space-Based" is one word.
_CREDIT_TAIL = re.compile(r"(?:\s*[|\u2013\u2014]\s*|:\s+|-\s+)([^|:\u2013\u2014]{3,60})$")
_CREDIT_TAIL_LEAD = re.compile(r"^(?:(?:report|research|study|analysis)\s+)?by\s+", re.IGNORECASE)
_CREDIT_TAIL_MAX_WORDS = 5
# A firm's name, letters and digits only, is taken as one once it is this
# long. Shorter, it is a word: market.us has the label "market", and a release
# that credited "Market ..." was tied to it.
_FIRM_NAME_MIN_CHARS = 8
_SQUASH = re.compile(r"[^a-z0-9]+")


def _squash(text: str) -> str:
    return _SQUASH.sub("", text.lower())


@dataclass(frozen=True)
class Issuer:
    """What one market result states about who issued it."""

    # Stock symbols the release is filed under or opens with.
    symbols: frozenset[str] = frozenset()
    # Company names the release opens with, defines itself by, or is filed
    # under, as words without the legal form.
    names: frozenset[tuple[str, ...]] = frozenset()
    # Research firms credited in the opening, letters and digits only.
    credits: frozenset[str] = frozenset()
    # The firm set off at the end of the headline, letters and digits only.
    tail: str = ""
    # The site's first label when the page is on a site that does not carry
    # other parties' releases: there the publisher is the issuer.
    own_label: str = ""
    # Whether the page is on a wire or a host that syndicates releases.
    carried: bool = False


def _opening(summary: str) -> str:
    """The release's first words after the wire's mark; "" if no mark is in the excerpt."""
    mark = _WIRE_MARK.search(summary)
    if mark is None:
        return ""
    return summary[mark.end():].split(_EXCERPT_GAP, 1)[0][:_OPENING_CHARS].strip()


def _name_words(name: str) -> tuple[str, ...]:
    """A company's name as lower-case words, without its legal form."""
    return tuple(_WORD.findall(_TRAILING_FORM.sub("", name.strip()).lower()))


def _credit_tail(title: str) -> str:
    text = _ELLIPSIS.sub("", title.strip())
    found = _CREDIT_TAIL.search(text)
    if found is None:
        return ""
    tail = _TRAILING_FORM.sub("", _CREDIT_TAIL_LEAD.sub("", found.group(1).strip()))
    if not 1 <= len(_WORD.findall(tail.lower())) <= _CREDIT_TAIL_MAX_WORDS:
        return ""
    return _squash(tail)


def issuer_of(item: MarketItem) -> Issuer:
    """The issuer signs one result carries; an empty ``Issuer`` when it carries none."""
    site = site_of(item.url)
    if not site:
        return Issuer()
    carried = site in _SYNDICATION_SITES or site in _WIRE_SITES
    if not carried:
        label = site.split(".")[0]
        return Issuer(own_label=label if len(label) >= _FIRM_NAME_MIN_CHARS else "")
    symbols: set[str] = set()
    names: set[tuple[str, ...]] = set()
    credits: set[str] = set()
    filed = _SYMBOL_IN_ADDRESS.get(site)
    if filed is not None:
        found = filed.search(urlsplit(item.url).path)
        if found:
            symbol = found.group(1).upper()
            symbols.add(symbol)
            for pattern in _NAME_BESIDE_SYMBOL:
                beside = re.search(pattern.replace("{symbol}", re.escape(symbol)), item.title)
                if beside:
                    names.add(_name_words(beside.group(1)))
    opening = _opening(item.summary)
    if opening:
        symbols.update(_SYMBOL.findall(opening))
        named = _OPENING_NAME.match(opening)
        if named:
            words = _name_words(named.group(1))
            if words and words[0] not in _NOT_A_NAME:
                names.add(words)
        credits.update(
            _squash(_TRAILING_FORM.sub("", found.group(1))) for found in _CREDIT_PHRASE.finditer(opening)
        )
    for found in _SELF_NAMED.finditer(item.summary):
        symbols.update(_SYMBOL.findall(found.group(0)))
        defined = found.group(0)[found.group(0).rindex("("):]
        names.update(_name_words(name) for name in _QUOTED.findall(defined) if name.lower() != "company")
    names.discard(())
    if _RESELLER_PHRASE.search(item.summary):
        credits.add(_RESELLER)
    credits = {name for name in credits if len(name) >= _FIRM_NAME_MIN_CHARS}
    return Issuer(
        symbols=frozenset(symbols),
        names=frozenset(names),
        credits=frozenset(credits),
        tail=_credit_tail(item.title),
        carried=True,
    )


def same_issuer(first: MarketItem, second: MarketItem) -> str:
    """Why two market results have one issuer, or "" if not shown to.

    - ``same symbol``: both are filed under, or open with, one stock symbol;
    - ``same name``: both releases state one company name;
    - ``named in headline``: a carried item that states no issuer of its own
      has a headline that begins with the name the other release states;
    - ``credited firm``: two carried items credit one research firm in their
      openings, or a carried item credits, in its opening or at the end of
      its headline, the firm whose own site the other page is on.

    Two pages on one publisher's site are not compared here: the site share
    counts them.
    """
    a, b = issuer_of(first), issuer_of(second)
    if a.symbols & b.symbols:
        return "same symbol"
    if a.names & b.names:
        return "same name"
    for stated, other, headline in ((a, b, second.title), (b, a, first.title)):
        if stated.names and other.carried and not other.symbols and not other.names:
            words, _cut = _headline(headline)
            if any(len(words) > len(name) and words[:len(name)] == name for name in stated.names):
                return "named in headline"
    if a.credits & b.credits:
        return "credited firm"
    # Only a carried item has a tail or credits: issuer_of reads neither on a
    # publisher's own page, so a newspaper that prints "| SNS Insider" after
    # its headline is not tied here.
    for own, other in ((a, b), (b, a)):
        if own.own_label and (own.own_label == other.tail or own.own_label in other.credits):
            return "credited firm"
    return ""


def issuer_mates(candidate: MarketItem, listed: list[MarketItem]) -> list[int]:
    """Positions in ``listed`` of the results that share the candidate's issuer.

    The signs link pairs, and a pair's link does not always carry: a release
    filed under a symbol and one known only by its headline are both tied to
    the release that states the symbol and the name, and not to each other.
    The issuer's results are therefore the whole group reached from the
    candidate through the listed results, not only its direct matches.
    """
    reached: list[int] = []
    frontier = [candidate]
    remaining = list(range(len(listed)))
    while frontier:
        current = frontier.pop()
        for index in list(remaining):
            if same_issuer(current, listed[index]):
                remaining.remove(index)
                reached.append(index)
                frontier.append(listed[index])
    return sorted(reached)
