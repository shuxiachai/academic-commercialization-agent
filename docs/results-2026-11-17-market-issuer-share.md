# Market evidence after selection v1: what the saved runs show, and the one rule that stood

**Date:** 2026-11-17 (UTC).
**Status:** offline measurement on saved runs, plus one production run read
back from the deployment. No search or model request was made. Twenty-five
public pages were read once, at no cost, to see which date fields they carry.
**Production:** the issuer share is in the change that carries this file. A
live before-and-after comparison is
[registered separately](prereg-2026-11-17-market-issuer-share-v1.md) and has
not run.

## Why

[Market selection v1](results-2026-11-14-market-selection-v1.md) left three
things it could not see, listed under "Copies the rule missed": one issuer's
releases spread over several sites, a report's page beside the release that
announces it, and a news item beside the release it reports. A production run
of 2026-11-15 on space-based solar power showed the first: no story twice, no
encyclopedia entry, no site over two slots, and three of eight market slots
held by releases of one company, Helio, on businessinsider.com, otcmarkets.com
and stocktitan.net. Five of the eight sources were undated.

This is the count of each of the three on the saved runs, the rule written
for the first, and why no rule was written for the other two or for dates.

## What was measured

`scripts/audits/market_evidence_audit.py` reads every `validated_sources.json`
under `outputs/` and applies `market_selection.py`, the module the market
stage uses, to each run's saved market sources in their saved order.

```
uv run python -m scripts.audits.market_evidence_audit outputs --since 2026-10-01 --since 2026-11-01
uv run python -m scripts.audits.market_evidence_audit outputs --since 2026-10-01 --pairs --issuers --reports
```

`outputs/` is private and not in the repository, so the command reproduces
these figures only on the maintainer's machine.

**Runs.** Since 2026-10-01: **132 runs with 967 market sources** (16 copies of
a registry and 4 registries with no market source set aside). Since
2026-11-01: 56 runs with 406 market sources. The figures of 2026-11-13 were
taken on 95 runs; the registries of the selection comparison and of later
benchmark batches have been saved since, which is why the scorecard counts
below are larger than the 75 of 88 quoted then.

## One issuer on several sites

Counted on each run's sources after copies and encyclopedia entries are
removed, so that a story listed twice is not also "one issuer, twice".

| | Since 2026-10-01 (132 runs) | Since 2026-11-01 (56 runs) |
|---|---:|---:|
| Runs where one issuer holds two market slots | 35 (27%) | 16 (29%) |
| Runs where one issuer holds three or more | 8 (6%) | 5 (9%) |
| Issuers with more than one slot, spread over several sites | 37 | 20 |
| Sources past an issuer share of 2 | 8, in 8 runs | 5, in 5 runs |
| Sources past an issuer share of 1 | 55, in 43 runs | 30, in 21 runs |

### How an issuer is read

Only from what a release states about itself, and only on a press wire or a
host that syndicates releases:

- **the symbol it is filed under**, on the two carriers that file by symbol (`stocktitan.net/news/HLEO/...`, `otcmarkets.com/stock/HLEO/news/...`), and the name those carriers print beside that symbol in the title;
- **the opening after the wire's mark**: the symbols in its first 240 characters, before any gap in the excerpt, and the name it begins with when that name runs straight into a comma, a bracket or the verb;
- **the name it gives itself beside "the Company"**: `(OTCID: HLEO) ("Helio" or the "Company")`;
- **a headline that begins with that name**, for a carried item that states no issuer of its own;
- **the research firm it credits**, in its opening ("According to the SNS Insider,"), at the end of its headline ("| SNS Insider"), or in ResearchAndMarkets.com's fixed sentence. A carried release is tied to the firm whose own site another listed page is on, and two carried releases to each other when both credit one firm in their openings.

A pair's tie does not always carry: a release known only by its symbol and
one known only by its headline are both tied to the release that states both,
and not to each other. The share therefore counts the whole group reached
through the listed sources (`issuer_mates`).

### The pairs, read

The signs tie **29 distinct pairs** of addresses in the 132 runs: 10 by a
credited firm, 8 by a headline, 8 by a symbol and 3 by a name. Each was read
by the AI assistant that wrote the rule; none is two issuers.

| Issuer | Pairs | Signs |
|---|---:|---|
| Helio | 10 | symbol (5), headline (5) |
| Medtronic | 4 | name (2), headline (2) |
| ResearchAndMarkets.com (its pages, and releases announcing reports it resells) | 5 | credited firm |
| SNS Insider | 2 | credited firm |
| Precedence Research, Future Market Insights, DelveInsight | 3 | credited firm, one each |
| Aikido Technologies, Envision Energy, Psyence Biomedical, T-Mobile, Eco Wave Power | 5 | name, headline, symbol, symbol, symbol |

One pair is looser than the rest and is left tied: a Yahoo page headed
"Envision Energy completes green marine ammonia bunkering operation" beside
Envision's own release. It is a trade paper's report of that release, carried
by Yahoo. It is about the issuer, not by it. The share is soft, and two such
pages still take two slots.

### Wrong ties found while the rule was written

Each was found by reading every tied pair on the saved runs, and each changed
the rule before it was wired in.

| Wrong tie | Why it happened | What changed |
|---|---|---|
| spacesolar.co.uk, a company's home page, tied to a Yahoo release about "BiLight Space Solar Technology" | The first version looked for the site's label anywhere in the release's title and opening with the spaces taken out | A firm is tied only where it is credited in so many words: the whole end of the headline, a credit phrase in the opening, or the reseller's sentence |
| market.us tied to a release that credited "Market ..." | Six letters were taken as a firm's name | A firm's name must be eight letters or more |
| The third Helio release of the 2026-11-15 run not tied to the other two | No saved excerpt of that run opened with the company's name: two were cut from the middle of a release, and the third opened "On January 6, 2026, the Board of Directors of" | The name printed beside the symbol in a carrier's title, and the name defined beside "the Company", are read |

The last one is the run the work started from. The first version of the rule
passed every test written from the local runs and did nothing on it.

### What the share changes, replayed

The pipeline's rules applied to each run's saved sources, in saved order. The
site share is applied first, as in the pipeline.

| Measure | As saved | Rules replayed |
|---|---:|---:|
| Runs where one issuer holds more than 2 slots (132 runs) | 8 (6%) | 0 to 8 (6%) |
| Sources waiting for their issuer's share | | 5 (1%) in 5 runs |
| The same, since 2026-11-01 (56 runs) | 5 (9%) | 0 to 5 (9%); 5 sources (1%) in 5 runs |
| Runs the rules change, all rules together | | 86 (65%), from 84 before the share |

Three of the eight sources past an issuer's share were already held by the
site share. **All five that the issuer share adds are Helio releases, in five
runs on space-based solar power.** On the saved runs the rule is that one
case. The range is the same as
for the site share: every held release replaced by another issuer's result,
or none. Which it is depends on results that were not saved. In the selection
comparison of 2026-11-14 every slot freed by the site share was refilled.

**The production run of 2026-11-15**, read back from the deployment and
replayed: the third Helio release (stocktitan.net) waits; the other seven
sources are untouched. Its researchandmarkets.com page and its Yahoo release
of a report ResearchAndMarkets resells are tied to one firm and are within
the share.

**The number.** A share of 2 is the maintainer's choice for a site, and is
used here for an issuer without a measurement behind it. At 2 the share holds
back 8 sources in 132 runs. At 1 it would hold back 55 in 43 runs, among them
every second release of a company and every release beside its firm's page.
The table above is there for that decision.

## A report beside the release that announces it: no rule

Three signs were tried on the saved runs. None is in the pipeline.

| Sign | Pairs in 132 runs | What they are |
|---|---:|---|
| The release quotes, in the reseller's sentence, the exact title another listed source carries | 0 | The sign is exact and never occurs in what the selection stage sees. The pair on record (satellite direct-to-cell, 2026-11-14) is a ResearchAndMarkets page and a Yahoo release, and the saved excerpt of the release does not contain the sentence |
| Both titles are "<subject> ... Report <year>" with one subject and one year | 1 | That pair. One true case cannot show the sign is safe: two firms title a report "X Market Report 2026" alike, and nothing in a title says which firm wrote it |
| Both titles open with one subject before "Market" | 123 | Different firms' reports of one market, which the run needs both of. Five of the 123 are from one firm, and those are that firm's different reports |

"One firm" does not mean "one report" either. Of the ten pairs tied by a
credited firm, seven are two different reports or documents
(ResearchAndMarkets resells many analysts' reports; SNS Insider's page on
direct air capture sat beside its release on carbon dioxide utilization), one
is the same market in two editions with different horizons, one is probably
a page and its own release, and one cannot be told either way from the titles
and excerpts. Merging on the firm would have dropped a different estimate at
least seven times in ten.

What the issuer share does for this case: a firm's page and a release
crediting it count toward one share, so a third source from that firm waits.
The pair itself stays.

## A news item beside the release it reports: no rule

News pages that share at least 5% of an excerpt with a carried release listed
in the same run: **0** in 132 runs. Search excerpts a different part of each
page, so the wording a reporter copied from a release is rarely in both
excerpts. The pair on record (green ammonia, 2026-11-14) is the Envision pair
above, and there the report is itself carried by Yahoo, so the headline sign
ties it for the share.

## Dates: no rule

| Why undated, since 2026-11-01 | Sources |
|---|---:|
| Market report on its publisher's own page: not read, by decision | 136 |
| Page read, no publication date in its metadata | 40 |
| Market report on a wire or syndicating host, in runs before 2026-11-13 | 28 |
| Home page: not read | 9 |
| Encyclopedia entry (no longer listed) | 8 |
| **Undated** | **221 of 406 (54%)** |

The largest group is deliberate. A report's landing page keeps its first date
while its forecast years move on, so its metadata dates the page and not the
estimate (`page_dates.should_date`).

The 40 pages that were read and gave no date are 25 distinct addresses. Each
was read again on 2026-11-17 with the pipeline's own reader, to see whether a
structured date field is there and unread:

| What the page carries | Pages |
|---|---:|
| Not readable (a bot check or a refusal): congress.gov, weforum.org, bts.gov, irena.org and others | 11 |
| Readable, no date-like field of any kind | 6 |
| A "date" key in the page's own application data, not a publication field (cbinsights.com) | 7 |
| A `<time>` element showing the day of the visit | 1 |

No reliable field is being missed. The cbinsights value is not marked as a
publication date and on one page read 2018 for a profile that is current; the
`<time>` element is the reason that tag is not read. Dating from prose stays
out, as before.

## What did not change

| | Since 2026-10-01 |
|---|---|
| Scorecards | 98, all with a cap record |
| Market cap triggered | 84 |
| Cap lowered the score | 27 |
| Market accessibility exactly 3.5 | 52 |

Nothing here is expected to change these. A slot that passes from one
issuer's third release to another source can bring another market figure, the
spread between figures can widen, and the cap can trigger more often. The
registered comparison makes no prediction about it.

## Limits

- **The rule is rare.** It changes 5 sources in 132 saved runs beyond what the site share already held, all of one company. It answers the case it was written for; on the saved runs it does nothing else.
- **The pairs were read by the AI assistant that wrote the rule**, not blind and not by a person.
- **What takes a freed slot is not on disk.** The replay says what waits, not what arrives.
- **Every saved run is a development run for this rule.** The unseen topics are in the registered comparison, which has not run.
- **Issuers that state nothing about themselves are not seen.** A private company whose releases are excerpted from the middle, on a carrier that does not file by symbol, is three unrelated sources to the rule.
