"""What a search engine is told about this deployment's pages.

Until 2026-11-17 it was told nothing: /robots.txt and /sitemap.xml answered
404, every /samples/<slug> was served with the list's title and the list's
address, and a run page carried no instruction at all. Two things follow from
that, in opposite directions. The pages meant to be found (the home page, the
sample reports, the privacy page) gave a crawler little to find them by. And
a run page, whose address is the permission to read the run (AGENTS.md: "A
run URL is a read capability"), could be listed by a search engine as soon as
somebody pasted a share link on a public page.

What may be indexed is a list, `public_paths()`. The sitemap is that list
and nothing else, and every response for an address that is not on it carries
`X-Robots-Tag: noindex, nofollow` (the middleware in api/main.py asks
`indexable()`). A route added later is therefore closed until someone puts it
on the list, rather than open until someone remembers to close it.

robots.txt does NOT disallow /run/ or /compare/, and that is deliberate. A
crawler that is told not to fetch an address never reads the noindex on it,
and a search engine may then list the bare address, without a snippet, once
another page links to it ("indexed, though blocked by robots.txt"). For most
pages that is a nuisance; for a run it is the leak, because the address is
all anyone needs. So the two share addresses stay fetchable and say noindex,
which is the combination search engines document as the way to keep a page
out. Nothing is exposed by letting them be fetched: /run/<id> is the same
script-drawn shell as the home page, with no report in it.

/api/runs/ goes the other way and is disallowed with the rest of /api/. An
address under it returns the run itself, so a crawler that keeps what it
fetches (an archive, a training set) would hold a copy of a report its owner
can still delete; a Disallow is what such a crawler obeys. The price is the
one just described, a pasted API address listed bare, and it is the smaller
one here: the address the page gives out to share is /run/, and the header
is sent on every API response regardless, for a crawler that fetches anyway.

robots.txt also leaves open the few API reads the public pages are drawn
from. The sample reader, the privacy page and the landing page are built by
script. Loaded in Chromium on 2026-11-17 with every request under /api/
refused, as a renderer that honours such a robots.txt would refuse them, the
sample page read "The sample list could not be loaded." and the home page
showed an empty workbench instead of its landing.

The address written into the sitemap, into robots.txt and into a sample's
og:url is the one the shipped pages already name in their own og:url, read
from the page rather than stated here a second time. PUBLIC_URL was the other
candidate; it is set only where mail is configured, and it would let the
sitemap name one host while the cards on the same pages name another. A
self-hosted copy points its cards at its own address by editing that tag
(the comment in web/index.html), and these follow.

Each page on the list also says which address is the one to keep, in a
`<link rel="canonical">`. The deployment answers at two hosts: the public
one, and the one Railway issued, which the deploy checks read on purpose
(AGENTS.md). Without the link a search engine that finds the second host has
a second copy of every public page and picks one itself. Measured on
2026-11-17: none of the four kinds of public page carried one. The link is
written in the page beside og:url and says the same address; a sample's is
derived from the list's exactly as its og:url is. The privacy page has no
card and so no og:url, and names its address in that link alone. Where a
document is served at an address that is not on the list, the link is taken
out with og:url (`unlisted_page`): a run page that named the home page as
its canonical address would be telling a search engine something false.
"""

from __future__ import annotations

import html
import re
from urllib.parse import quote, urlsplit
from xml.sax.saxutils import escape as _xml

from api import samples

NOINDEX = "noindex, nofollow"

# Reads the public pages make from script, which a crawler that renders them
# has to be allowed to make too: the sample reader and the landing's sample
# list (/api/samples...), the retention and contact lines of the reader and
# the privacy page (/api/site), and the landing's access check, whose 401 is
# what keeps the landing on screen (app.js decideAccess).
_PAGE_READS = ("/api/samples", "/api/site", "/api/access/check")
# Not a page for a visitor who is not signed in, or, under /api/runs/, the
# content of a run, which a crawler should not copy; see the module docstring.
# /run/ and /compare/ are absent on purpose and must stay absent.
_CLOSED = ("/api/", "/admin", "/source-locator")

_OG_URL = re.compile(r'(<meta property="og:url" content=")([^"]*)(">)')
_OG_URL_LINE = re.compile(r'[ \t]*<meta property="og:url" content="[^"]*">\r?\n?')
# Same three groups as _OG_URL, so one function rewrites either address.
_CANONICAL = re.compile(r'(<link rel="canonical" href=")([^"]*)(">)')
_CANONICAL_LINE = re.compile(r'[ \t]*<link rel="canonical" href="[^"]*">\r?\n?')
_CHARSET_LINE = re.compile(r'(<meta charset="utf-8">\r?\n)')
_TITLE = re.compile(r"(<title>)[^<]*(</title>)")


def origin_of(page: str) -> str | None:
    """The http(s) origin a shipped page names in its og:url, or None."""
    match = _OG_URL.search(page)
    if match is None:
        return None
    parts = urlsplit(html.unescape(match[2]))
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def public_paths() -> list[tuple[str, str | None]]:
    """Every address a search engine may index, with the date it last changed
    where one is known.

    The samples come from the allowlist in api/samples.py, so a sample added
    there is listed here and one removed is gone. A sample's date is the day
    it was committed: the report is kept as the run wrote it, so that is the
    last day the page's content changed. The other three state no date
    rather than an invented one.
    """
    return [
        ("/", None),
        ("/samples", None),
        *((f"/samples/{quote(sample.slug, safe='')}", sample.committed) for sample in samples.SAMPLES),
        ("/privacy", None),
    ]


def indexable(path: str) -> bool:
    """Whether a response for `path` may be left without a noindex.

    The public pages, the files they are made of, and the two documents a
    crawler reads to find them. Exact matches: "/samples/" and
    "/samples/<a name that is not listed>" are not the pages above.
    """
    if path.startswith("/static/") or path in ("/robots.txt", "/sitemap.xml"):
        return True
    return any(path == listed for listed, _ in public_paths())


def robots_txt(origin: str | None) -> str:
    """The rules, and where the sitemap is when the pages name an address.

    Allow lines come first and are longer than the Disallow they carve out
    of. A crawler that takes the longest match (RFC 9309, Google, Bing) and
    one that takes the first match in file order (Python's urllib, and older
    parsers like it) then reach the same answer for every address.
    """
    lines = [
        "# A shared assessment (/run/, /compare/) is deliberately not disallowed:",
        "# every such response says \"X-Robots-Tag: noindex, nofollow\", and a",
        "# crawler that is told not to fetch a page never reads that.",
        "User-agent: *",
        *(f"Allow: {path}" for path in _PAGE_READS),
        *(f"Disallow: {path}" for path in _CLOSED),
    ]
    if origin:
        lines += ["", f"Sitemap: {origin}/sitemap.xml"]
    return "\n".join(lines) + "\n"


def sitemap_xml(origin: str) -> str:
    """`public_paths()` as a sitemap on `origin`."""
    entries = []
    for path, changed in public_paths():
        lastmod = f"<lastmod>{_xml(changed)}</lastmod>" if changed else ""
        entries.append(f"  <url><loc>{_xml(origin + path)}</loc>{lastmod}</url>")
    return "\n".join((
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        *entries,
        "</urlset>",
    )) + "\n"


def unlisted_page(page: str) -> str:
    """A shipped page as it is served at an address that must not be indexed.

    Three changes to the head. A robots tag, for a crawler that reads the
    page and not the header. And og:url removed: it names the page the file
    was written for (the home page, or the sample list), and a site that
    builds a link card treats og:url as the address the card is about, so a
    shared run could open the home page instead. Without the tag the card is
    about the address that was shared. The run's own address is not written
    in its place: nothing needs it there, and a page that echoes part of its
    request is one more thing to get wrong.

    The canonical link goes for the same reason, said to a search engine
    instead of a card: it would name the home page as the address of a run.
    Beside a noindex it is also a contradiction, one tag saying "keep that
    page for this one" and the other "keep nothing".

    The rest of the card (title, description, picture) stays the site's
    general one. Whether a shared run's card should name its topic and score
    is the deployment owner's decision, not made here.
    """
    page = _OG_URL_LINE.sub("", page, count=1)
    page = _CANONICAL_LINE.sub("", page, count=1)
    return _CHARSET_LINE.sub(lambda match: f'{match[1]}<meta name="robots" content="{NOINDEX}">\n', page, count=1)


# The sample reader's name for itself, as web/static/js/samples_i18n.js has it
# (samples_title). The served <title> is the one samples.js sets once it runs,
# `<sample> · <this>`, in the language of the report;
# tests/test_search_indexing.py reads the script's strings and compares. So
# for a reader whose interface is in the report's language the page has one
# name with or without script. The script names the tab in the interface
# language, though: in an English interface the Chinese sample becomes
# "特高压直流输电 · Sample reports" once it runs, and a crawler that renders
# the page may keep that one. Seen in a browser on 2026-11-17 and left as it
# is; the script's naming has its own tests (tests/test_samples_title_web.py).
_READER_NAME = {"English": "Sample reports", "Simplified Chinese": "示例报告"}


def _facts(entry: dict) -> tuple[str | None, str | None]:
    """The score and the readiness level as the sample's card words them
    (i18n.js sample_verdict, sample_trl), or None where the scorecard gave none."""
    overall, trl = entry.get("overall_score"), entry.get("trl_score")
    return (f"{overall:.1f} / 100" if overall is not None else None,
            f"TRL {trl:g}" if trl is not None else None)


def _sample_words(entry: dict) -> tuple[str, str, str]:
    """(title, card title, description) for one sample, in its report's language.

    The description says what the reader's own notice says about a sample: an
    old run with its date and model, kept as written, not a current market
    view. A search result that left that out would present a kept output as
    a live assessment. The topic and the numbers come first and the rest is
    kept short, because a search result shows roughly 160 characters of a
    description and a card roughly 70 of a title. The six descriptions run
    from 99 to 192 characters: the date and the model fall inside the cut
    for every sample, the last clause does not for the longest topic.
    """
    name = entry["title"]
    overall, trl = _facts(entry)
    if entry.get("language") == "Simplified Chinese":
        numbers = "，".join(part for part in (f"总分 {overall}" if overall else None, trl) if part)
        card = f"{name}：{numbers} · 商业化评估示例" if numbers else f"{name} · 商业化评估示例"
        lead = f"{name}的商业化评估示例报告：{numbers}。" if numbers else f"{name}的商业化评估示例报告。"
        description = (f"{lead}{entry['committed']} 用 {entry['model']} 跑出的一次运行，保持原样；"
                       "展示的是报告格式，不代表最新市场判断。")
        return f"{name} · {_READER_NAME['Simplified Chinese']}", card, description
    numbers = ", ".join(part for part in (f"{overall} overall" if overall else None, trl) if part)
    short = ", ".join(part for part in (overall, trl) if part)
    card = f"{name}: {short} · Sample assessment" if short else f"{name} · Sample assessment"
    lead = f"Sample commercialization assessment of {entry['topic']}"
    lead += f": {numbers}. " if numbers else ". "
    description = (f"{lead}A {entry['committed']} run with {entry['model']}, kept as written; "
                   "not a current market view.")
    return f"{name} · {_READER_NAME['English']}", card, description


def _set_meta(page: str, attribute: str, key: str, value: str) -> str:
    pattern = re.compile(rf'(<meta {attribute}="{re.escape(key)}" content=")[^"]*(">)')
    # A function, not a template: a name with a backslash in it is text.
    return pattern.sub(lambda match: match[1] + html.escape(value, quote=True) + match[2], page, count=1)


def sample_page(page: str, entry: dict) -> str:
    """The sample reader as it is served for one listed sample.

    `entry` is the sample's line of `samples.list_samples()`: the allowlist
    entry and the two numbers its card shows, so the head states what the
    list states. The title, the description, og:title and og:description
    become the sample's own, and og:url and the canonical link each gain the
    sample's name after the list's address, by one function, so the two say
    the same address for a sample whenever they do for the list. Everything
    below the head is the reader as committed.

    A crawler that runs no script (every link-preview crawler, and several
    search engines) read six pages with one title and one address before
    this, and so had one page.
    """
    title, card, description = _sample_words(entry)
    page = _TITLE.sub(lambda match: match[1] + html.escape(title, quote=False) + match[2], page, count=1)
    page = _set_meta(page, "name", "description", description)
    page = _set_meta(page, "property", "og:title", card)
    page = _set_meta(page, "property", "og:description", description)
    slug = html.escape(quote(entry["slug"], safe=""), quote=True)

    def under_the_list(match: re.Match[str]) -> str:
        return f"{match[1]}{match[2].rstrip('/')}/{slug}{match[3]}"

    page = _OG_URL.sub(under_the_list, page, count=1)
    return _CANONICAL.sub(under_the_list, page, count=1)
