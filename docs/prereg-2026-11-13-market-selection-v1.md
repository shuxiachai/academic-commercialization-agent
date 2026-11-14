# Pre-registration: market selection v1, before and after on live results

Registered **2026-11-13** (UTC), before any request for it. Nothing below has
run. It needs the maintainer's approval of the budget in this file first.

## Question

The market stage now keeps one copy of a story, holds a site's third result
back, lists no encyclopedia entry, and reads the page date of report releases
on press wires and syndicating hosts
([what the saved runs show](results-2026-11-13-market-selection-offline.md)).
The saved runs say exactly what leaves a registry. They cannot say what
arrives, because the candidates a run rejected were not kept. Two questions
follow, in order:

1. **Part R, retrieval.** On live search results, do the rules do what they
   were written to do, without merging different sources and without thinning
   the registry?
2. **Part S, scores.** With the registry changed that way and nothing else,
   where do TRL, market accessibility, evidence confidence and the overall
   score land?

## Change under test (frozen)

This branch at the commit that carries this file: `market_selection.py`, the
market stage of `source_pipeline.py`, and `should_date` in `page_dates.py`.
The comparison is against `main` at `5256c14`.

## Cases

[`evals/market_selection_v1/cases.json`](../evals/market_selection_v1/cases.json), twelve cases:

| Cases | Topics | Used in |
|---|---|---|
| V01, V03, V06, V07, V09 | five of the frozen v2 cohort, unchanged: robotic-assisted surgery, enhanced geothermal, space-based solar power, hyperloop, 特高压直流输电 | Part R and Part S |
| N01 to N07 | green ammonia as a marine fuel; direct lithium extraction from geothermal brines; autonomous trucks for long-haul freight; satellite direct-to-cell mobile service; 3D-printed concrete houses; 氢燃料电池重型卡车; wave energy converters for grid electricity | Part R only |

- **The V cases are development topics for these rules.** Their saved runs were read while the rules were written: the Helio and SLB copies are in the tests. They are here because they have frozen TRL ranges and three earlier single runs each.
- **The N cases are unseen.** None had a saved run on 2026-11-13, and they were named before any search for them. They have no TRL range and are not scored.

## Part R: the two arms see the same answers

[`collect.py`](../evals/market_selection_v1/collect.py) runs
`collect_source_collection` for each case under one arm's code. The `old` arm
is a checkout of `main` at `5256c14`; the `new` arm is this branch.

Every request the pipeline makes goes through one recorder kept in a file
outside the repository: web search, the topic planner and heading translator,
the academic and patent clients, the URL check, the page-date reader and the
patent-page reader. The old arm runs first and makes each request once. The new arm
is answered from the record, so the two registries differ only where the code
differs. A request only the new arm makes is sent live and counted.

```bash
git worktree add --detach ../market-evidence-base 5256c14
uv run python evals/market_selection_v1/collect.py --arm old --src ../market-evidence-base/src \
    --cache <outside-repo>/market-selection-v1.cache --out <runs>/market-selection-v1 \
    --accessed <date of the run> --env <main checkout>/.env
uv run python evals/market_selection_v1/collect.py --arm new --src src   # same --cache, --out, --accessed, --env
uv run python evals/market_selection_v1/compare.py --out <runs>/market-selection-v1 --json <runs>/market-selection-v1/compare.json
```

`compare.py` prints the table and the reading list: every pair the new arm
called one story, and every source only one arm lists.

### Readings and bars, fixed now

| | Reading | Bar |
|---|---|---|
| R1 | Each "duplicate story" note of the new arm: both pages are read and the pair is labelled one story or different | **No pair is different** |
| R2 | Market sources per case in each arm | **No case loses its market domain in the new arm; no case with 3 or more market sources in the old arm has fewer than 3 in the new** |
| R3 | Encyclopedia entries, and stories the rule itself still finds twice, in the new arm | **0 and 0** (anything else is a defect in the wiring) |
| R4 | Each date only the new arm gives a report release, against the publication date the page prints or the release's dateline | **None contradicted by more than one day**; if more than 20 are checked, at most 5% |
| R5 | Requests only the new arm made: web searches, URL checks, page reads | **At most 25% more web searches than the old arm made, over all cases** |

Reported without a bar:
- cases where one site holds more than two market slots, in each arm;
- sources on a press wire or syndicating host, and undated sources, in each arm;
- which sources left and which arrived, by case, with the kind and site of each;
- sources still held for a site's share that returned to a slot, and how often a nearer copy replaced a listed one;
- copies the rule missed: for each new-arm registry the market titles and addresses are read for a pair that is one story and was not merged;
- whether the academic and patent sources are identical between the arms. They should be. A case where they are not is named, and its Part S comparison is read as confounded.

**Predictions, not bars.** Fewer cases have a site over its share in the new
arm. The count of market sources per case changes by at most one. The share of
undated sources falls by the report releases on wires and syndicating hosts
and no further.

**Labels.** An AI assistant reads the pages and labels R1 and R4, following
the [AI-only review policy](llm-review-policy.md). It is not blind to the arm.

## Part S: the crew on each arm's registry

The five V cases, each arm's Part R registry frozen as the benchmark's
evidence, the crew run by `benchmark.py --fixtures`. Retrieval does not run
again, so the two arms differ in the market sources and in nothing else that
is under the pipeline's control. The model's own variation remains.

```bash
# from the root of ../market-evidence-base (old arm), then from the root of this branch (new arm);
# freeze.py is this branch's file in both cases
uv run python <this branch>/evals/market_selection_v1/freeze.py --arm-dir <runs>/market-selection-v1/<arm>
QWEN_MODEL=deepseek-v4.1-flash-1017 uv run --env-file <main checkout>/.env python benchmark.py --fixtures \
    --cohort evals/heldout_trl_v2/cohort.json --only V01,V03,V06,V07,V09 -c 1 -r 2 \
    --experiment-id market-selection-v1-<arm>
```

| | |
|---|---|
| Model | `deepseek-v4.1-flash-1017` through the `qwen` transport, the model the deployment serves and the one read on these five topics on 2026-11-11 (4 of 5 in range). The maintainer may name another model when approving; it is then written here before the first run |
| Repeats | 2 per arm, so that a difference between arms can be set against the difference between two runs of one arm |
| Units | 5 cases × 2 arms × 2 repeats = 20 |
| Order | old arm first, then new; one unit at a time |
| Where | the maintainer's machine |

The fixture files and manifest entries written by `freeze.py` stay local to
the two checkouts and are not committed.

### Readings, fixed now

- **Completion** per arm, out of 10. A unit that fails is read through its error record and named as the model's output, the transport, or the registry.
- **TRL against the frozen range**, per unit.
- **Market accessibility, evidence confidence and the overall score**, per unit. For each case, the difference between the arms' means is set beside the larger of the two within-arm differences. A between-arm difference no larger than that is reported as not distinguishable from run-to-run variation, whatever its sign.
- **The market cap**, per unit: triggered, applied, and the spread it recorded.
- **Tokens and wall time** per unit.

### Bars

| | Bar |
|---|---|
| S1 | **The new arm has at most two fewer units inside their frozen TRL range than the old arm** (of 10) |
| S2 | **No new-arm unit fails for a reason in its registry** (a guardrail or contract tripped by the sources) where the old arm's unit completes |

**No prediction is made about the market cap or the market score.** One copy
of a story and more sites can put more different market figures in front of
the scorer. The spread between them can widen and the cap can trigger more
often. Either direction is reported as found.

## What counts as failure, and what follows

- **R1 fails:** the sign that produced the wrong pair is named. It is removed or tightened in a new commit, the saved-run replay is rerun, and the change is not merged before that.
- **R2 fails:** the rule that thinned the registry is named (the copy rule, the encyclopedia rule or the site share). The change is not merged as it is.
- **R3 fails:** a defect. Fixed and Part R rerun from the record, at no cost.
- **R4 fails:** the page-date extension is taken out of the change. The other three rules stand or fall on their own bars.
- **R5 fails:** reported as a cost the maintainer decides on. It does not by itself block the change.
- **S1 or S2 fails:** the change is not merged as it is. The result says which cases moved and what in their registries changed.
- **All bars hold:** the result recommends merging. It claims no improvement in any score and no calibration.

Part S runs only if R1, R2 and R3 hold.

## Budget and stop rules

| Part | What is paid | Estimate | Stop rule |
|---|---|---|---|
| R, web search | The old arm's searches, and the few only the new arm makes. The fifteen runs of 2026-11-08 and 2026-11-11 audited 5 to 12 searches each, mean 9 | 110 to 150 searches for twelve cases; about 150 Tavily credits, or USD 0.15 at Serper's list price | No new case starts once **300** live searches are recorded |
| R, model | The topic planner once per case and the heading translator for the two Chinese cases | under 40,000 tokens | none beyond the case count |
| S, model | 20 crew runs. The five runs of 2026-11-11 on this model used 523,069 tokens, 104,614 a run | about **2.1 million tokens**; about 3.5 hours serial at 11 minutes a run | No new unit starts once finished units record **2.6 million** tokens. A watcher ends the process then; a unit it ends is recorded as stopped by the rule |

Page reads, URL checks and the academic and patent APIs cost nothing.

**A smaller Part S.** With one repeat per arm (10 runs, about 1.05 million
tokens, stop at 1.3 million) the TRL readings and both bars stand, with S1
read as "at most one fewer of 5". The comparison against run-to-run variation
is then unavailable, and a score difference between the arms could not be
told from noise. The maintainer chooses which when approving; the choice is
written here before the first run.

No failed unit is retried. Nothing here changes the deployment or any
variable on its host.

## What this cannot say

- **Nothing about calibration.** Five topics, two runs each.
- **Nothing about unseen topics' scores.** The N cases are not scored.
- **Nothing about day-to-day variation in search.** Both arms see one day's recorded answers; that is what makes them comparable, and what keeps this from being a live-versus-live measurement.
- **Nothing about a reader's judgement of the report.** Whether a report with these sources is more useful is a separate question, and the closed utility studies did not establish it for any change.
- **The labels are an AI assistant's**, not blind and not a human's.

## Recording

Raw registries, the request record and the benchmark outputs stay private
(`outputs/benchmark-runs/market-selection-v1*`, not committed). The result
goes in `docs/results-<date the runs finish>-market-selection-v1.md`, with
every bar read as registered and nothing re-scored.

## Amendment before the first run

Added 2026-11-14 (UTC), after the maintainer's approval and before any
request. Nothing above is changed.

- **Approval.** The maintainer approved the budget on 2026-11-14 with **two repeats per arm**: 20 units, stop at 2.6 million tokens. No other model was named, so Part S runs on `deepseek-v4.1-flash-1017`.
- **Access date.** Both arms collect with `--accessed 2026-11-14`.
- **How the stop rules are applied.** `collect.py` has no stop rule of its own. A driver runs it one case at a time with `--only` and starts no case once the live web searches counted in the finished cases' `calls.json` reach 300. For Part S a watcher sums `usage.total_tokens` over the finished units' `meta.json` in both batches and ends the runner at 2.6 million.
- **No trial request.** Nothing is sent ahead of the first unit to try the model: such a request is not in the approved budget. If the first unit fails on the model's name or allowance before any crew answer, the batch stops there and is reported. The remaining units are then not run, and are not recorded as failures.
- **Where the files are.** Each arm's registries go under this branch's `outputs/benchmark-runs/market-selection-v1/`, and each benchmark batch under its own checkout's `outputs/benchmark-runs/market-selection-v1-<arm>/`. The request record is kept outside the repository while the arms run. All of it is copied to the main checkout's private `outputs/benchmark-runs/` when the runs finish.

## Amendment during Part S

Added 2026-11-14 (UTC), after Part R was read and after the old arm of Part S
stopped. No new-arm unit had run, so no score of the new arm had been seen.
The Part R protocol and its bars are unchanged.

**What happened.** The old arm ran on `deepseek-v4.1-flash-1017` as
registered. Three units finished (V01, V03 and V07, first repeat). The
writer's answer for V06 was cut at the model's output limit. From the fifth
unit on, the provider refused every request: the model's free allowance was
exhausted and the account is set to use the free tier only. The new arm
could not run on that model at all.

**A defect in the watcher, twice.** Its first version read the benchmark's
"running" status as a failure and ended the first unit within a minute of its
start; the old arm was restarted as `market-selection-v1-old-b`, and the
ended unit's unrecorded requests are counted against the stop rule as 60,000
tokens, an upper estimate. Its second version stopped only when the *first*
unit failed on the allowance, so five later units were started and refused at
their first request. Both are faults of the runner, not readings.

**What changes, by the maintainer's decision of 2026-11-14.**

- **Model.** Part S runs on `glm-5` through the same `qwen` transport, both arms from the start. This project has no earlier reading of `glm-5` on these topics. The three finished old-arm units on the first model are reported beside the result and take no part in the comparison.
- **Order.** The maintainer asked for two repeats per arm. The allowance named for `glm-5` is about one million tokens, and twenty units need about 1.9 million at the 97,000 a unit measured above. So the units run in an order that leaves whole pairs whenever the allowance ends: repeat 1 of each case, old arm then new arm (V01, V03, V06, V07, V09), then repeat 2 in the same order. Each unit is its own batch, `ms-v1-glm5-<arm>-<case>-r<n>`.
- **Stop.** Everything stops at the first unit the provider refuses for its allowance, and at the registered 2.6 million tokens, counting about 450,000 for the first model's units, recorded and estimated. A unit refused for the allowance is not a reading and is not counted as a failed unit.
- **S1.** Read on complete pairs only. With every case paired once: the new arm has at most one fewer unit inside its frozen range, of 5, which is the smaller reading registered above. With every case paired twice: at most two fewer, of 10, and the comparison against run-to-run variation is available. A second repeat that covers only some cases is reported and is not counted in S1.
- **S2 and every other reading** are unchanged, as is the rule that no failed unit is retried. A unit that fails in the model's own output (a cut or empty answer, a contract not met) leaves its pair incomplete; the pair is then reported and not counted in S1. When the old-arm unit of a pair fails, the pair's new-arm unit is not run: the allowance is short, and the pair could not be counted.
- **A unit's time.** A unit still running after 30 minutes is ended and recorded as stopped by the runner. The registered protocol set no limit; the deployment's own budget for a run is 25 minutes.
