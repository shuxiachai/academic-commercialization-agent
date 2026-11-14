# Market selection: what the saved runs show, and what the rules change on them

**Date:** 2026-11-13 (UTC).
**Status:** offline measurement on saved runs. No search, page or model
request was made for the figures in the first three sections; the last
section's dates were already on disk.
**Production:** the rules are in the change that carries this file. The live
before-and-after comparison was
[registered separately](prereg-2026-11-13-market-selection-v1.md) and had not
run when this was written; its [result](results-2026-11-14-market-selection-v1.md)
is dated a day later.

## Why

A signed-out review of the site found the market evidence the weakest part of
a report: one release listed twice, one aggregator holding most of the market
slots, an encyclopedia entry cited as market evidence, and most sources
undated. A first count with a rough title match put numbers on it. This is the
exact count, by the code the pipeline now runs.

## What was measured

`scripts/audits/market_evidence_audit.py` reads every `validated_sources.json`
under `outputs/` and applies `market_selection.py`, the module the market
stage uses, to each run's saved market sources in their saved order.

```
uv run python -m scripts.audits.market_evidence_audit outputs --since 2026-10-01 --since 2026-11-01
uv run python -m scripts.audits.market_evidence_audit outputs --since 2026-10-01 --pairs
uv run python -m scripts.audits.market_evidence_audit outputs --since 2026-01-01 \
    --page-date-probes evals/market_dates_v1/dev_probe.json evals/market_dates_v1/test_probe.json
```

`outputs/` is private and not in the repository, so the command reproduces
these figures only on the maintainer's machine.

**Runs.** Since 2026-10-01 there are 101 registry files. Two are copies of
another (identical bytes) and four list no market source (test artefacts),
which leaves **95 runs with 698 market sources**. The first count's "99 runs"
included those four.

## As saved

| Measure | Since 2026-10-01 (95 runs, 698 sources) | Since 2026-11-01 (19 runs, 137 sources) | First count |
|---|---:|---:|---:|
| Runs listing one story twice | 27 (28%) | 6 (32%) | 32% and 42% |
| Slots holding a second copy | 38 | 8 | 38 |
| Runs where one site holds more than 2 market slots | 41 (43%) | 11 (58%) | 41% and 58% |
| Sources on yahoo.com, all regional hosts | 222 (32%) | 50 (36%) | 32% |
| Sources on a press wire or a syndicating host | 276 (40%) | 63 (46%) | 35% |
| Runs with an encyclopedia entry | 13 (14%) | 2 (11%) | 13% |
| Undated sources | 644 (92%) | 83 (61%) | 92% and 61% |

**Copies.** The 38 second copies were recognised by:
- the same article address on one site, 23 (a regional Yahoo host, or a tracking parameter the locator check did not strip);
- one headline on a host that carries other parties' releases, confirmed by shared text, 12;
- a document mirror, 3 (everycrsreport.com republishing a congress.gov report).

**Titles alone would not do.** In those 95 runs, 95 pairs of sources have
alike titles (similarity of at least 0.75). Only 33 of them are one story. The
other 62 are different sources, nearly all of them two firms' reports on one
market with different figures.

**Why sources are undated.** For the 19 runs since 2026-11-01, when page dating
was already in place:

| Why undated | Sources |
|---|---:|
| Market report on its publisher's page: not read, by the registered rule | 47 |
| Page read, states no publication date | 16 |
| Market report on a press wire or syndicating host: not read | 15 |
| Home page: not read | 3 |
| Encyclopedia entry: not read | 2 |

Of the 70 sources the rule then admitted, 54 were dated. The remaining gap is
mostly report publishers' landing pages, which are left undated on purpose: a
landing page keeps its first date while its forecast years move on
([registered rule](prereg-2026-10-22-market-page-dates-v1.md)).

**Scorecards.** 88 of the 95 runs have a scorecard, and all 88 record the
market cap. It triggered in 75 and lowered the score in 23; market
accessibility is exactly 3.5 in 47.

## The rules

1. **One story, one slot.** Two results are one story when they have the same
   article address on one site; or when one is a document mirror of the other;
   or when they carry one headline, at least one of them on a host that carries
   other parties' releases, and either both dates fall within two days or the
   two excerpts share text. Of two copies the one nearer the issuer is kept:
   the issuer's own page or an original publisher, then a press wire, then a
   syndicating host; on one site, the main host before a regional one.
2. **At most two market slots per site**, counting a publisher's regional
   hosts as one site. A third result from a site is held. It is listed only if
   no other site's result fills the slot.
3. **No encyclopedia entry in the market slots.**
4. **Page dates for report releases.** A source typed as a market report is
   read for its page date when it is on a press wire or a syndicating host.
   A report publisher's own page stays undated.

Rule 3 reverses a decision of 2026-10-19, when one Wikipedia entry per run
was admitted because it was the only result naming the floating offshore wind
farms that topic's anchor rests on
([record](results-2026-10-19-market-allowlist-sector-sources.md)). That
benefit is given up: the entry's primary sources have to be found by the
other queries, or they are not in the report.

Rule 2's number is the maintainer's choice, not a measured optimum.

## Replayed on the saved runs

| Measure | Since 2026-10-01 | Since 2026-11-01 |
|---|---:|---:|
| Runs the rules change | 70 of 95 (74%) | 16 of 19 (84%) |
| Sources no longer listed: 38 second copies and 13 encyclopedia entries | 51 (7%) | 10 (7%) |
| Sources held for their site's share | 65 (9%) in 38 runs | 13 (9%) in 9 runs |
| Runs listing one story twice | 0 | 0 |
| Runs where one site holds more than 2 slots | 0 to 38 | 0 to 9 |
| Runs left with fewer than two market sources before refill | 0 | 0 |
| A copy nearer the issuer replaces the one listed first | 4 times | 2 times |

**What the replay cannot show.** A run's audit keeps the title of a rejected
candidate and nothing else, and results past a query's source limit were never
read. The sources that would take the 51 freed slots, or stand in for the 65
held ones, are not on disk. That is why site concentration after the change
is a range: 0 runs if every held source is replaced by another site's result,
38 if none is and each returns to its slot. Where in that range it lands, and
which sources arrive, is what the live comparison measures.

**Every merged pair was read.** Over all 240 saved runs with market sources
since July, the rules merge 44 slots, 26 distinct pairs. Each pair was read
by the AI assistant that wrote the rules, and each is one release or one
document at two addresses. The pairs the rules leave alone were read as well. They
include two releases by one company that share their closing paragraph, two
pages of one company profile, and one site's two articles whose addresses
differ by "-2". None of these is shown to be one item, so each is kept.

## The page-date extension, checked on saved probes

The registered page-date test left market reports out. The saved probes of
that test had recorded what each page stated all the same. For pages on a
press wire or a syndicating host:

| Source type | Probed | Stated a date |
|---|---:|---:|
| reputable_news | 75 | 75 |
| company_disclosure | 21 | 18 |
| market_report | 13 | 13 |

A release prints its own dateline ("Dublin, Oct. 20, 2026 (GLOBE NEWSWIRE)
--"), and 45 saved excerpts of these pages carry one. The date in the page's
metadata is within a day of that dateline in **45 of 45**: 34 news items, 7
company disclosures and 4 market reports. The dateline is used only for this
check. The pipeline still takes dates from page metadata alone.

## Limits

- **One reader, not blind.** The AI assistant that wrote the rules read the pairs, on the same runs the rules were written on. These runs are development data for the rules, not a test.
- **Thresholds are not fitted.** The shared-text bound is 0.15. Every pair merged by headline shares at least 0.32 and no saved pair with one headline falls between 0.05 and 0.32, so the data does not fix where the bound belongs.
- **The site list is short by design.** Hosts that syndicate releases are named in `market_selection.py`. A host missing from the list is treated as an original publisher, which errs toward keeping a copy.
- **Four market reports carry the dateline check.** The other 41 agreeing pages are news and company items on the same hosts.
- **No effect on scores is claimed.** Removing copies and spreading sites changes which market figures a report sees. The spread between them may widen, and the cap may then trigger more often, not less.
