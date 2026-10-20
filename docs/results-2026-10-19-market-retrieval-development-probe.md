# Market retrieval development probe: does retrieval find the known operators?

Date: 2026-10-19 (Australia/Sydney). A **development measurement** on the
consumed held-out v1 topics. It is not held-out validation and reports no TRL.
It follows the [market query slot-sharing change](results-2026-10-19-market-query-slot-sharing.md)
(#213).

## Question

Two questions:

1. With #213 in place, does market retrieval surface the operators, products and deployments named in each topic's anchor evidence?
2. Would different query wording or Tavily's news search surface more of them?

## Method

```bash
uv run python market_retrieval_probe.py --cache <outside-repo>.json --out <file> --variants A,B,C,D --cases H10,H01
uv run python market_retrieval_probe.py --cache <same> --out <same> --variants A
uv run python market_retrieval_probe.py --saved-coverage   # the v1 runs, no search
```

- **Scope.** Market domain only. Each topic reuses its saved v1 plan (search topic and components), so no LLM was called. Tavily searches ran on 2026-10-19, and every response is cached, so reruns are free. The probe used 77 searches.
- **Label.** An entity named in the topic's [cohort anchor](../evals/heldout_trl_v1/cohort.json), such as Zipline for drone delivery or HTR-PM and NuScale for SMRs. A test checks that every label is anchor text or a declared alias of it, so no label was added after seeing results.
- **Metric.** How many of the 8 market sources name at least one anchor entity in their title or summary. This counts mentions, not support.
- **Variants.**
  - A: production queries after #213.
  - B: operator wording in place of the topic-level templates ("operator deployments in service", "announces first commercial operation", and so on), with market size last.
  - C and D: A and B with Tavily news search for the topic-level queries.
- **Design.** A pilot ran all four variants on drone delivery (H10) and SMRs (H01), the two topics where operator evidence was most clearly missing. A then ran on the other eight topics.
- **Comparison.** The same metric on the saved v1 runs, which used the old code and were retrieved on 2026-10-18.

## Results

**Wording pilot.** Market sources naming an anchor entity, out of 8:

| Topic | A | B | C | D |
|---|---:|---:|---:|---:|
| H10 drone delivery of medical supplies | **3** | 2 | 0 | 1 |
| H01 small modular reactors | **4** | 3 | 3 | 3 |

Neither the operator wording nor news search beat the production queries on
either topic.

**Production queries (A) against the saved v1 runs:**

| Topic | v1, three runs (old code) | A, one run |
|---|---|---|
| H01 small modular reactors | 3/5, 4/5, 4/5 | 4/8 |
| H02 fusion power | 3/7, 1/8, 3/8 | 2/8 |
| H03 implantable BCI | 4/8, 6/8, 5/7 | 5/8 |
| H04 psilocybin therapy | 1/8, 1/8, 1/8 | **6/8** |
| H05 direct air capture | 3/8, 2/8, 2/8 | 3/8 |
| H06 floating offshore wind | 1/8, 0/8, 1/7 | 0/8 |
| H07 artificial photosynthesis | 0/7, 0/7, 0/8 | 0/8 |
| H08 precision fermentation | 3/8, 2/8, 2/8 | 4/8 |
| H09 DNA data storage | 5/8, 0/8, 5/8 | 3/8 |
| H10 drone medical delivery | 0/7, 0/5, 0/5 | **3/8** |

- **Entity-naming sources.** On average across the three v1 sets, 20.7 per ten topics; A has 30.
- **Coverage.** 22 of 30 v1 runs had at least one entity-naming source; A covered 8 of 10 topics.
- **Where it changed.** The largest changes are on the two topics where the topic-level queries had never run: drone delivery, where Zipline went from absent in all three v1 runs to 3 sources, and psilocybin.

H07's anchor names only laboratory groups, and no run on either side found
them.

## Where entities are still lost

This comes from a cache-only reading of the pilot topics' raw results that
named an entity but were not admitted. Each reason is a pattern from that
reading, not a count.

- **Host not on the allowlist.**
  - Wikipedia is deliberately blocked in the market domain, alongside social media. For floating offshore wind, it was the only result naming Hywind, Kincardine and WindFloat.
  - Other unapproved hosts: World Nuclear Association, IEEFA, a NuScale page, healthcare trade press (Becker's, MD+DI) and health-system newsrooms.
- **Per-query limit.** Entity-naming results ranked fourth to eighth in a query were not read once three sources had been admitted from it.
- **Market-report pages.** Many name operators in their snippets ("key players include Zipline"), so a market-size title does not mean the page has no operator evidence.

## Decisions

- **Query wording and news search: not adopted.** They lost or tied on both pilot topics, so the production wording stays.
- **The allowlist is unchanged.** Unblocking Wikipedia would reverse a deliberate precision policy, so the decision is the maintainer's. Adding sector sources (nuclear, energy-finance, healthcare trade press) needs a curated list and its own precision check, because each addition is sector-specific.
- **The per-query limit stays.** It is what lets the topic-level queries run at all.

## Limits

- One run per topic and variant. Live search differs by day.
- The v1 comparison crosses both a day and a code change.
- These topics are consumed, so nothing here is held-out.
- A mention is not support.
- The anchors were AI-assisted and maintainer-reviewed.

For a new cohort, the anchor entities should be fixed in the cohort file
before any run, so the same coverage metric can serve as a registered
retrieval-level measure.
