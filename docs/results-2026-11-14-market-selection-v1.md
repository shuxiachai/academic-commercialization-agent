# Market selection v1: every bar holds; no score is shown to improve

**Date:** 2026-11-14 (UTC).
**Status:** run once under the
[protocol](prereg-2026-11-13-market-selection-v1.md), including its two dated
amendments. Part S did not run as first registered: its model changed and its
second repeat covers one case. Both are described under Deviations.
**Reading:** the registered rule recommends merging the change. It claims no
improvement in any score and no calibration.

## Result

| | Bar | Read |
|---|---|---|
| R1 | No pair the new arm merged is two stories | **Holds.** 9 pairs, each read: 9 are one story |
| R2 | No case loses its market domain; none with 3 or more market sources drops below 3 | **Holds.** 88 market sources in each arm, the same count in every case |
| R3 | No encyclopedia entry and no story twice in the new arm | **Holds.** 0 and 0 |
| R4 | No date the new arm gives a report release is contradicted by more than a day | **Holds.** 6 dates, 6 agree |
| R5 | At most 25% more web searches in the new arm | **Holds.** 13 more on 81, 16% |
| S1 | With each case paired once: at most one fewer new-arm unit inside its TRL range, of 5 | **Holds.** 5 of 5 in each arm, the same TRL in every pair |
| S2 | No new-arm unit fails for a reason in its registry | **Holds.** No new-arm unit failed |

## Part R: twelve cases, both arms answered from one record

The old arm is `main` at `5256c14`; the new arm is this branch (`src`
unchanged since `25e198a`). Access date 2026-11-14. The old arm ran first and
made 81 web searches. The new arm was answered from the record and made 13
more, for queries the old arm never reached.

| Case | Topic | Market sources | Story-twice pairs | Largest site | Encyclopedia | Undated |
|---|---|---:|---:|---:|---:|---:|
| V01 | robotic-assisted surgery | 6 → 6 | 0 → 0 | 1 → 1 | 0 → 0 | 3 → 3 |
| V03 | enhanced geothermal | 8 → 8 | 4 → 0 | 2 → 2 | 0 → 0 | 3 → 5 |
| V06 | space-based solar power | 8 → 8 | 1 → 0 | 3 → 2 | 0 → 0 | 3 → 4 |
| V07 | hyperloop | 7 → 7 | 0 → 0 | 1 → 1 | 1 → 0 | 5 → 5 |
| V09 | 特高压直流输电 | 8 → 8 | 1 → 0 | 3 → 2 | 1 → 0 | 5 → 2 |
| N01 | green ammonia as a marine fuel | 8 → 8 | 1 → 0 | 3 → 2 | 0 → 0 | 4 → 4 |
| N02 | direct lithium extraction | 8 → 8 | 1 → 0 | 3 → 2 | 0 → 0 | 3 → 4 |
| N03 | autonomous trucks | 8 → 8 | 0 → 0 | 3 → 2 | 1 → 0 | 3 → 3 |
| N04 | satellite direct-to-cell | 8 → 8 | 2 → 0 | 3 → 2 | 0 → 0 | 4 → 4 |
| N05 | 3D-printed concrete houses | 3 → 3 | 0 → 0 | 1 → 1 | 1 → 0 | 3 → 3 |
| N06 | 氢燃料电池重型卡车 | 8 → 8 | 1 → 0 | 4 → 2 | 0 → 0 | 4 → 5 |
| N07 | wave energy converters | 8 → 8 | 0 → 0 | 2 → 2 | 0 → 0 | 5 → 3 |

Over the twelve cases, old arm to new arm:

| Measure | Old | New |
|---|---:|---:|
| Market sources | 88 | 88 |
| Cases listing a story twice | 7 | 0 |
| Cases where one site holds more than 2 slots | 7 | 0 |
| The same, on the seven unseen N cases | 5 | 0 |
| Encyclopedia entries | 4 | 0 |
| Sources on yahoo.com | 27 | 18 |
| Sources on a press wire or syndicating host | 42 | 31 |
| Distinct sites, summed over cases | 69 | 78 |
| Sources typed as market reports | 34 | 37 |
| Undated sources | 45 | 45 |

- **Every freed slot was refilled.** Eighteen sources left and eighteen arrived. No source held for its site's share returned to a slot: another site's result filled it each time.
- **What left:** 9 second copies, 4 encyclopedia entries, and 5 results held for their site's share (8 were held in all; 3 of those the old arm had never read).
- **What arrived:** 8 market reports, 6 company pages, 2 news items and 2 government documents.
- **The predictions held, except the third.** Fewer cases have a site over its share (7 to 0). The count per case did not change at all. Undated sources did not fall: six report releases gained a date, and the sources that arrived are mostly report publishers' pages and PDFs, which carry none.
- **The academic and patent sources are identical in all twelve cases**, so nothing but the market list differs between the arms. No audit records an academic refusal, and no domain failed.

**Requests only the new arm made:** 13 web searches, 32 URL checks (the old arm made 113) and 16 page-date reads (the old arm made 48).

### R1: the nine merged pairs

Each pair was read on 2026-11-14 by the AI assistant that wrote the rules. It
was not blind to the arm.

| # | Case | Sign | Left | Kept | What the pages show |
|---|---|---|---|---|---|
| 1 | V03 | same address | Yahoo, id 130000034 | Yahoo, id 130000995 | One headline, one day. Each partner issued the joint announcement on its own wire: SLB on Business Wire, Ormat on GlobeNewswire. The opening names the two companies in the other order; the second sentence is word for word the same |
| 2 | V03 | mirror | everycrsreport.com IF13278 | congress.gov IF13278, which took the slot | Same title and report number; the mirror names Congress.gov as its source. congress.gov answered the reader with a bot check, so the original was not read |
| 3 | V03 | same headline | Stock Titan | Yahoo, id 130000995 | Stock Titan rewrote the headline; the body is the GlobeNewswire release, same dateline and opening |
| 4 | V06 | same address | ca.finance.yahoo.com | finance.yahoo.com | One Newsfile release of February 4, 2026 |
| 5 | V09 | same address | uk.finance.yahoo.com, id 113300728 | finance.yahoo.com, id 113300390 | One Research and Markets release, "Dublin, Jan. 27, 2026 (GLOBE NEWSWIRE)" |
| 6 | N01 | same headline | Yahoo | prnewswire.com, which took the slot | One PR Newswire release, "DALIAN, China, July 25, 2025" |
| 7 | N02 | same headline | Markets Insider | ca.finance.yahoo.com | One GlobeNewswire release, "HOUSTON, April 30, 2026" |
| 8 | N04 | same headline | Yahoo | Markets Insider | One VEON release, "Dubai and Kyiv, November 24, 2025" |
| 9 | N04 | same address | Yahoo page | the same page with a tracking parameter | One page |

All nine are one story. Four of them (6 to 9) are on cases the rules had never
seen.

Pair 1 is the one a stricter reader could label otherwise. It is two
releases, one from each partner, of one announcement. They are not byte
copies. It is labelled one story because a report that lists both counts one
agreement twice, which is what the rule exists to prevent.

### R4: the six dates only the new arm gives a report release

| Case | Source | Date given | Page prints | Release dateline |
|---|---|---|---|---|
| V03 | Yahoo, "Geothermal Power Market to Reach $14.5 billion" | 2025-11-20 | not read | Nov. 20, 2025, in the saved excerpt |
| V09 | Yahoo, HVDC market report 2026 | 2026-01-27 | January 27, 2026 | Jan. 27, 2026 |
| V09 | Yahoo, HVDC industry report 2025 | 2025-06-05 | June 5, 2025 | June 05, 2025 |
| N04 | Yahoo, satellite-to-cell report 2026 | 2026-01-22 | January 23, 2026 | Jan. 22, 2026 |
| N07 | Yahoo, wave energy converter market | 2024-02-12 | February 13, 2024 | Feb. 12, 2024 |
| N07 | prnewswire.com, wave energy converter market | 2026-10-15 | Oct 15, 2026 | Oct. 15, 2026 |

All six agree with the release's own dateline. Two Yahoo pages print the next
day: the page shows the date in the reader's time zone.

### Copies the rule missed (reported, no bar)

All twelve new-arm market lists were read for a pair that is one story and
was not merged. No release at two addresses was found unmerged. Three things
the rule does not cover were found:

- **A report's page and the release announcing it** (N04). researchandmarkets.com lists "Satellite-to-Cell Phone Service Market Report 2026", and a Yahoo release says that report "has been added to ResearchAndMarkets.com's offering". One estimate holds two slots. The titles differ, so the rule leaves them.
- **A news report and the release it reports** (N01). A Ship Technology article and Envision's own release describe one bunkering operation. They are different items about one event.
- **One issuer on three sites** (V06). Three different Helio releases, on Stock Titan, Yahoo and Markets Insider, hold three of eight slots. They are not copies, and the site share cannot see that one small company wrote all three. This is the pattern `examples/README.md` records for the same topic, and the change does not remove it.

## Part S: the crew on each arm's registry

Run on `glm-5`, one unit a batch, old arm then new arm for each case, from
the registries of Part R frozen as fixtures. Retrieval did not run again.

### Repeat 1: five complete pairs

| Case | Frozen TRL | TRL old → new | Market accessibility | Evidence confidence | Overall |
|---|---|---|---|---|---|
| V01 | 8–9 | 9.0 → 9.0 | 3.5 → 3.5 | 4.0 → 4.0 | 74.0 → 74.0 |
| V03 | 7–8 | 7.0 → 7.0 | 3.0 → 3.5 | 4.0 → 4.0 | 66.3 → 68.8 |
| V06 | 3–5 | 3.0 → 3.0 | 2.5 → 2.5 | 2.5 → 3.0 | 46.2 → 49.2 |
| V07 | 4–6 | 5.0 → 5.0 | 3.0 → 3.0 | 3.0 → 3.0 | 54.1 → 57.6 |
| V09 | 8–9 | 9.0 → 9.0 | 3.5 → 3.5 | 4.0 → 4.0 | 74.0 → 74.0 |

- **Completion:** 5 of 5 in each arm.
- **TRL:** all ten units are inside their frozen range, and the TRL is the same in every pair. S1 holds.
- **Market accessibility** moved in one pair (V03, by half a point). **Evidence confidence** moved in one (V06, by half a point).
- **The overall score** is equal in two pairs and higher in the new arm in three, by 2.5, 3.0 and 3.5 points.

**Those three differences are not shown to come from the market sources.**
- In V07 the whole difference is manufacturing readiness (4.0 to 5.0) and patent strength (2.5 to 3.0). Market accessibility and evidence confidence are equal.
- In V06 two of the three points are patent strength (3.5 to 4.0).
- The patent sources are identical in both arms. A patent score that moves half a point on identical patents is the model's variation between two runs.
- Only V03's difference is in the market score itself.

### The market cap

| Case | Triggered old / new | Lowered the score old / new | Spread the scorecard records, old → new |
|---|---|---|---|
| V01 | yes / yes | yes / yes | 24000× → 24000× |
| V03 | yes / yes | no / no | 2632× → 2632× |
| V06 | yes / yes | no / no | 10× → 384× |
| V07 | yes / yes | no / no | 8382× → 24× |
| V09 | yes / yes | yes / yes | 6× → 177× |

The cap triggered in all ten units and lowered the score in two of five in
each arm. The spread widened in two cases and narrowed in one. **The change
did not reduce how often the cap triggers**, as the protocol declined to
predict. The spread is the scorecard's legacy untyped figure, not a verified
comparison of like estimates.

### Repeat 2: one pair, then the allowance ended

| Case | TRL old → new | Market accessibility | Evidence confidence | Overall |
|---|---|---|---|---|
| V01 | 9.0 → 9.0 | 3.5 → 3.5 | 4.2 → 4.0 | 74.4 → 74.0 |

The next unit (V03, old arm) was refused for the allowance and everything
stopped. By the amendment this repeat is reported and not counted in S1.

V01 is the one case with two units in each arm, and its market list is the
same in both arms. Its two old-arm units differ by 0.4 points overall, and
its two new-arm units by none. **The comparison against run-to-run variation
that two full repeats would have given is not available.** One pair on a case
whose registries do not differ cannot stand in for it.

### Usage

| | Units that finished | Tokens recorded | Time per unit |
|---|---:|---:|---|
| `glm-5` | 12 | 991,572 | 92 to 142 s |
| `deepseek-v4.1-flash-1017` (not compared) | 3 | 291,769 | 96 to 128 s |

Recorded in all: 1,283,341 tokens, against a stop rule of 2.6 million. Not
recorded: the requests of four units that ended after some of their calls had
returned (one ended by the watcher, one cut, two refused part-way) and the
planner's twelve calls in Part R. Web searches: 94, against a stop rule of 300. Of 75 provider attempts
in the twelve `glm-5` units, all returned.

### The three units on the first model

For the record, and outside the comparison. Old arm only.

| Case | Frozen TRL | TRL | Market accessibility | Overall |
|---|---|---|---|---|
| V01 | 8–9 | 9.0 | 3.5 | 76.5 |
| V03 | 7–8 | 7.0 | 3.0 | 61.3 |
| V07 | 4–6 | 3.0, below the range | 2.5 | 43.2 |

V07 at 3.0 is where the same model put it on 2026-11-11.

## Deviations from the protocol

1. **The model changed.** The old arm began on `deepseek-v4.1-flash-1017`. Its free allowance ended after four units and the account uses the free tier only, so the new arm could not run there. The protocol had no way to see the remaining allowance beforehand. The maintainer chose `glm-5` for both arms. No new-arm score had been seen. This project has no earlier reading of `glm-5` on these topics.
2. **One repeat, not two.** `glm-5`'s allowance covered twelve units. The amended order kept whole pairs: five in repeat 1 and one in repeat 2. S1 was therefore read in the smaller form the protocol had registered.
3. **The watcher ended a unit it should not have.** Its first version took the benchmark's "running" status for a failure and ended the old arm's first unit within a minute. The old arm was restarted as a new batch. Nothing had been scored.
4. **The watcher let five units start after the allowance ended.** Its second version stopped only if the first unit failed that way. Each of the five was refused at its first request. They are not readings and are not counted as failed units.
5. **One unit was cut at the model's output limit** (V06, old arm, first model): the writer's answer stopped at the limit and was not used. It was not retried.
6. **The reading list was incomplete.** `compare.py` listed a case only if a source changed or the audit carried a note, so N07's two new dates were missing from the list the protocol says to read. The "Undated" column gave it away, and the figures were in `compare.json`. The list is fixed and has a test.
7. **Two readers.** Markets Insider pages were read in a browser because the page reader could not fetch them. congress.gov answered both with a bot check and was not read.

## What follows

- **All bars hold**, so by the registered rule the result recommends merging the change.
- **No score is shown to improve.** TRL is unchanged in every pair. The overall score is higher in three of five pairs, mostly in dimensions whose inputs did not change.
- **The market cap is not relieved.** It triggered in every unit of both arms.
- **What the change does do** is what Part R measured: one copy of a story, no site over two slots, no encyclopedia entry, at the price of 16% more searches and with every slot refilled.
- **What it leaves** is under "Copies the rule missed": a report beside its own release, and one issuer's releases across several sites.

## Limits

- **Five topics, one model, one run a unit.** Nothing here is a calibration, and nothing separates a difference between arms from the model's own variation.
- **The V cases are development topics for the rules.** The N cases are unseen but were not scored.
- **Both arms saw one day's recorded answers.** That makes them comparable and says nothing about day-to-day variation in search.
- **The labels are an AI assistant's**, not blind and not a human's. The same assistant wrote the rules.
- **`glm-5` has no other reading here.** Its five TRLs landed inside the frozen ranges in both arms; that is ten units, not a recommendation of the model.

## Files

- `evals/market_selection_v1/`: the cases and the three scripts.
- Private, not committed, under `outputs/benchmark-runs/` on the maintainer's machine:
  - `market-selection-v1/`: both arms' registries, `compare.json` and the request record;
  - `ms-v1-glm5-<arm>-<case>-r<n>/`: the thirteen `glm-5` batches;
  - `market-selection-v1-old/` and `market-selection-v1-old-b/`: the first model's two old-arm batches.

To rerun Part R's comparison from the saved registries, at no cost:

```
uv run python evals/market_selection_v1/compare.py --out outputs/benchmark-runs/market-selection-v1
```

These registries are now under `outputs/`, so
`scripts/audits/market_evidence_audit.py` counts them from 2026-11-14 on. The
figures in the [offline result](results-2026-11-13-market-selection-offline.md)
were taken before they existed.
