# Market page dates v1: protocol

**Date:** 2026-10-22.
**Status:** registered before any test-split page was fetched.

## Why

Web search returns market sources without a date. None of the 229 market
sources in the held-out v2 runs had one, so every report lists them as
"Published: n.d.". A reader cannot tell a 2021 hiring announcement from this
week's news. The production hyperloop report presented Virgin Hyperloop as an
active company on the strength of an undated item about a CFO hire.

Many pages state their own publication date in machine-readable metadata.

## Change under test (frozen)

`src/academic_agent/page_dates.py` reads a page's publication date from
explicit metadata only, in this order:
1. JSON-LD `datePublished`, including inside `@graph`;
2. a publication-time `<meta>` tag;
3. `itemprop="datePublished"`;
4. a full `/YYYY/MM/DD/` date in the URL path.

It never reads prose, modification dates or partial dates. A date after the
access date, or before 1990, is rejected. Fetching follows only public
HTTP(S) redirect hops.

`should_date(source_type, url)` decides which sources may be dated. It
excludes:
- market reports: a landing page keeps its first date while its forecast years move on;
- Wikipedia: the date is the entry's creation;
- site home pages: the date is the site's.

If adopted, production applies this to each accepted market source that has
no date, once per run, before the registry is built. That integration is not
part of this test, which measures the extractor and the rule on saved sources.

## Development (held-out v2 market sources)

There are 117 unique URLs; 105 pages could be read. `should_date` admits 63 of
them. Of those, 41 were dated (65%), almost all from JSON-LD.

Each dated page was loaded in headless Chromium, and its rendered visible
text was searched for the date in common written forms:
- **Found within one day: 37 of 41 (90%).** Three were found only one day off. Metadata carries its own time zone, and the page renders in the reader's (Sydney).
- **Contradicted: 1.** The indiatimes byline reads 30 Aug 2025; the metadata says 2024-08-09.
- **Not checkable: 3.** Two pages print no date, and one returned "Forbidden".

These rule details were set on this split, after reading its results:
- the market-report, Wikipedia and home-page exclusions;
- the one-day tolerance.

## Test split

The test split is the market sources of the batches `heldout-trl-v1`,
`heldout-trl-v1-b`, `heldout-trl-v1-c`, `academic-gate-live-v1` and
`hyperloop-confirm-v1`, minus every development URL. That is 167 URLs, of
which `should_date` admits 109. Both counts were taken from the saved
registries, before any of these pages was fetched.

## Procedure

1. Run `probe.py` over the test batches, excluding the development probe. It makes one GET per page and caches the result.
2. Run `verify.py` on the result. It renders each dated page and searches for the date with the one-day tolerance.
3. For each dated row not found, an AI assistant reads the rendered excerpt and labels it, blind to which bar is close:
   - **contradicted:** the page prints this article's own publication date, more than one day from the extracted date;
   - **not printed:** no article date is shown (a header showing today's date, or another article's date, does not count);
   - **unreadable:** rendering failed or was blocked.

## Measures and bars

| Measure | Definition | Bar |
|---|---|---|
| P1 precision | found within one day / dated | ≥ 0.80 |
| P2 contradictions | contradicted / dated | ≤ 0.05 |
| C coverage | dated / admitted by `should_date` | ≥ 0.50 |

**Reading.** If all three bars hold, production adopts the change for market
sources. If any fails, it does not, and the result names the failing bar.
No TRL or report-quality effect is claimed either way.

## Limits

- **The check cannot catch a page that prints the same wrong date.** A syndicated copy can show the syndication date rather than the original release date, and both the metadata and the page would agree on it.
- **Pages are read on 2026-10-22**, not on the day their runs collected them. A page may have changed or disappeared since.
- **Coverage depends on which sites refuse automated requests.**
- **The labels are by an AI assistant**, not a human.
