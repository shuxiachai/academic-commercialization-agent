# Market retrieval: the topic's own queries never ran

Date: 2026-10-19 (Australia/Sydney). Source: the saved source collections of
the 30 runs in batch `heldout-trl-v1-c`. This document diagnoses retrieval
composition and describes a retrieval change. It reports **no TRL result**.
Those topics are consumed for held-out purposes, so the change's effect on TRL
needs a new cohort under its own protocol.

## Question

The [TRL compression diagnosis](results-2026-10-18-trl-compression-diagnosis.md)
found that about half of all market sources were market-size pages, which the
rubric does not count as commercial signals. It also found that drone medical
delivery never retrieved its leading operator. Which query admitted each
market source?

## Method

```bash
uv run python -m scripts.audits.market_query_origin outputs/benchmark-runs/heldout-trl-v1-c
```

Each market source is attributed to the first audited market query that
accepted it. Queries are classed by template wording, not by the topic
phrase, because the short and full topic forms are identical for topics of
six words or fewer. The title pattern is a lower bound. With this script's
pattern, 102 of 219 titles match; the diagnosis's broader pattern matched
116.

## Findings

| Query class | Queries run | Market sources | Market-size titled |
|---|---:|---:|---:|
| Component (`<component> company product commercial deployment`) | 53 | **166 (76%)** | 73 |
| Market size / market report | 13 | 37 (17%) | 26 |
| Authority (`site:fda.gov`, EMA, ClinicalTrials.gov) | 15 | 9 | 0 |
| Topic + `industry company deployment commercial scale` | 4 | 7 | 3 |
| Topic + `company commercial deployment industry news` | **0** | 0 | 0 |
| Topic + `product manufacturer revenue commercial sales` | **0** | 0 | 0 |
| Other full-topic templates | **0** | 0 | 0 |

**Mechanism.**
- Market slots fill in query order.
- The planner listed components for 27 of 30 runs, including single technologies such as fusion power, and component queries ran first.
- The per-query processing cap is 8, the same as the market slot count, so it could not stop one query from filling the domain.

In the three runs without components, the market-size query ran first and
supplied 6, 8 and 5 sources.

Example, drone delivery of medical supplies, run 1:
- The component query "unmanned aerial vehicles company product commercial deployment" admitted six general UAV market reports.
- The second component query admitted nothing.
- The market-size query admitted the remaining two slots.
- Collection stopped there, before the full-topic deployment or revenue query ran.

The rubric's SCOPE MATCH RULE then treats component-level evidence as evidence
about a narrower thing, and the market evidence it reads is mostly about
components or market size.

### Market-size releases were classed as news

Market-size releases were also classed as news. Of the 75 market sources
classed as `reputable_news`, 40 have market-estimate titles. Most are
syndicated releases on finance.yahoo.com, for example "Direct Air Capture
Market Poised for Explosive 43.3% CAGR Growth". Classed as news, they bypassed
the four-source cap on market reports and satisfied the company-news guard,
which exists to secure at least one real company or news source. In 6 of the
30 runs, every news-classed source was such a release, so the guard did not
run. These include all three drone-delivery runs. Elsewhere, real company
news was in the same registries: NuScale's design
approval, Optimi's psilocybin launch in Australia, GE Vernova's air-capture
deployment and Biomemory's first commercial product.

A title pattern now requires market-estimate wording, such as market
size/share/report/forecast, industry or research report, CAGR, or "market
worth/poised/projected/to reach". A bare amount, as in "raises $1 billion",
does not match: that is a commercial event. Over the 83 distinct news and
company titles in those runs, the 34 matches are all estimates and the 49
non-matches are all company or news items.

## Change

- **Component queries.** In the primary market pass, a component query admits at most **one** source. It still reserves coverage for its building block, which is what component queries were added for.
- **Other queries.** Every other primary market query admits at most **three** sources.
- **Order.** The topic's deployment and revenue queries now come first. The two market-size queries come after them and fill only the slots still empty.
- **Reclassification.** A news or press-wire source whose title matches the market-estimate pattern is classed as `market_report`, and its credibility reason says so. It then counts toward the market-report cap, and the company-news guard runs when no real company news remains.
- **Tests.**
  - An offline seam test feeds every market query eight valid results and checks the limits through `collect_source_collection`. With the limits removed, it fails.
  - Classification tests cover syndicated releases and news items that mention amounts.

**Unchanged:**
- the rubric and scoring formula;
- the authority queries;
- the host allowlist;
- the native-language supplement;
- the six-word `_mkt_short` truncation that cut "supplies" from the drone topic.

## Retrieval probe (descriptive, one run per topic)

Collection only, with no assessment, for two consumed topics on 2026-10-19
(`qwen3.8-max` topic planning, Tavily). The mechanics held: each component
query admitted one source, and the topic's deployment query ran and admitted
three.

| Topic | v1 runs: market-size titled | Probe |
|---|---|---|
| Small modular reactors for grid electricity | 2/5, 3/5, 3/5 | 2/8 |
| Drone delivery of medical supplies | 6/7, 3/5, 3/5 | 2/7 |

The deployment queries still return mostly market-report pages, and Zipline
still does not appear. Two causes stay open:

- **Query wording.** Search engines rank SEO market pages highly for generic commercial queries.
- **Host allowlist.** It rejects some authoritative sector sources: `world-nuclear.org` was rejected as "not approved" in the SMR probe.

Either change needs its own measurement. One run per topic says nothing about
the distribution.

## What this does not show

- **Any effect on TRL.** The expected direction is more topic-level operator and deployment evidence. Whether this changes scores, and whether low-maturity topics stay low, must be registered and measured on a new cohort.
- **Retrieval stability.** Live retrieval varies by day. In August, the floor-sitting count moved by 7 in 30 between live batches with no code change.
- **The market-evidence score.** Fewer market-size pages may lower it. This is a secondary measure for the next batch.

Re-running the audit on that batch checks the retrieval-level prediction.
The topic deployment query should run in nearly every run, and component
queries should supply at most one market source each.
