# Pre-registration: market issuer share v1, before and after on live results

Registered **2026-11-17** (UTC), before any request for it. Nothing below has
run. It needs the maintainer's approval of the budget in this file, and the
maintainer's choice of model, first.

## Question

The market stage now holds back a third result by one issuer, wherever its
releases are carried
([what the saved runs show](results-2026-11-17-market-issuer-share.md)). The
saved runs say what would wait: 8 of 967 sources, in 8 of 132 runs. They
cannot say what takes the freed slot, because the candidates a run rejected
were not kept. Two questions follow, in order:

1. **Part R, retrieval.** On live search results, does the rule hold back
   only sources that share an issuer with two listed ones, without thinning
   the registry, and what arrives in the slot?
2. **Part S, scores.** Where the registry changed, and nothing else did,
   where do TRL, market accessibility, evidence confidence and the overall
   score land?

The rule fires rarely. A comparison in which it never fires on an unseen
topic is a possible result and is reported as that.

## Change under test (frozen)

This branch at the commit that carries this file: `issuer_of`, `same_issuer`
and `issuer_mates` in `market_selection.py`, and the issuer share in the
market stage of `source_pipeline.py`. The comparison is against `main` at
`926eb7b`.

## Cases

[`evals/market_issuer_share_v1/cases.json`](../evals/market_issuer_share_v1/cases.json), ten cases:

| Cases | Topics | Used in |
|---|---|---|
| V01, V06 | two of the frozen v2 cohort, unchanged: robotic-assisted surgery, space-based solar power | Part R, and Part S if their registries differ |
| U01 to U08 | lithium-sulfur batteries; ocean thermal energy conversion; electric vertical take-off and landing air taxis; humanoid robots for warehouse logistics; focused ultrasound for essential tremor; 氢基直接还原铁炼钢; insect protein for animal feed; iron-air batteries for long-duration grid storage | Part R only |

- **The V cases are development topics for this rule.** Their saved runs are where one issuer was seen to hold three slots (Medtronic, Helio), and the Helio releases are in the tests. They are here because they have frozen TRL ranges and because the rule is expected to fire on them.
- **The U cases are unseen.** None had a saved run under `outputs/` on 2026-11-17, and they were named before any search for them. They have no TRL range and are not scored.

## Part R: the two arms see the same answers

The collector is the one registered for
[market selection v1](prereg-2026-11-13-market-selection-v1.md), unchanged:
every request the pipeline makes goes through one recorder kept outside the
repository. The old arm runs first and makes each request once; the new arm
is answered from the record, so the two registries differ only where the code
differs. A request only the new arm makes is sent live and counted.

```bash
git worktree add --detach ../market-issuer-base 926eb7b
uv run python -m evals.market_issuer_share_v1.collect --arm old --src ../market-issuer-base/src \
    --cache <outside-repo>/market-issuer-share-v1.cache --out <runs>/market-issuer-share-v1 \
    --accessed <date of the run> --env <main checkout>/.env
uv run python -m evals.market_issuer_share_v1.collect --arm new --src src   # same --cache, --out, --accessed, --env
uv run python -m evals.market_issuer_share_v1.compare --out <runs>/market-issuer-share-v1 --json <runs>/market-issuer-share-v1/compare.json
```

`compare` prints the table and the reading list: every source the new arm
held for its issuer's share, the listed sources of each issuer, and every
source only one arm lists.

### Readings and bars, fixed now

| | Reading | Bar |
|---|---|---|
| R1 | Each "deferred (issuer share" note of the new arm: the held page and the listed pages it was tied to are read, and the held source is labelled the same issuer's or not | **No held source is another issuer's** |
| R2 | Market sources per case in each arm | **No case loses its market domain in the new arm; no case with 3 or more market sources in the old arm has fewer than 3 in the new** |
| R3 | Issuers holding more than two market slots in the new arm with no held release that returned to an otherwise empty slot | **0** (anything else is a defect in the wiring) |
| R4 | Requests only the new arm made | **At most 25% more web searches than the old arm made, over all cases** |

Reported without a bar:
- cases where one issuer holds more than two market slots, in each arm, and on the eight unseen cases alone;
- every pair of new-arm sources the rule ties to one issuer, read and labelled, whether or not anything was held;
- which sources left and which arrived, by case, with the kind, the site and the date of each;
- held sources that returned to a slot;
- undated sources and sources on a wire or syndicating host, in each arm;
- issuers the rule missed: for each new-arm registry the market titles and addresses are read for three or more sources by one issuer that the rule did not tie;
- whether the academic and patent sources are identical between the arms. They should be. A case where they are not is named, and its Part S comparison is read as confounded.

**Predictions, not bars.** The rule holds a source in V06 and in V01. It
holds a source in at most two of the eight unseen cases. The count of market
sources per case does not change. The share of undated sources does not fall.

**Labels.** An AI assistant reads the pages and labels R1, following the
[AI-only review policy](llm-review-policy.md). It is not blind to the arm.

## Part S: the crew on each arm's registry

Only the scored cases whose market sources differ between the arms: at most
V01 and V06. Each arm's Part R registry is frozen as the benchmark's evidence
and the crew is run by `benchmark.py --fixtures`. Retrieval does not run
again, so the two arms differ in the market sources and in nothing else that
is under the pipeline's control. The model's own variation remains.

```bash
# from the root of ../market-issuer-base (old arm), then from the root of this branch (new arm)
uv run python <this branch>/evals/market_issuer_share_v1/freeze.py --arm-dir <runs>/market-issuer-share-v1/<arm> --only <cases that differ>
QWEN_MODEL=<the model the maintainer names> uv run --env-file <main checkout>/.env python benchmark.py --fixtures \
    --cohort evals/heldout_trl_v2/cohort.json --only <one case> -c 1 -r 1 \
    --experiment-id mis-v1-<arm>-<case>-r<n>
```

| | |
|---|---|
| Model | **Not chosen.** The free allowances of `deepseek-v4.1-flash-1017` and `glm-5` ended during the last comparison, and the provider does not report what is left of any other. The maintainer names the model when approving; it is written here before the first run |
| Repeats | 2 per arm, so that a difference between arms can be set against the difference between two runs of one arm |
| Units | up to 2 cases × 2 arms × 2 repeats = 8 |
| Order | repeat 1 of each case, old arm then new arm; then repeat 2 in the same order. One unit a batch, so that whole pairs remain whenever an allowance ends |
| Where | the maintainer's machine |

### Readings, fixed now

- **Completion** per arm. A unit that fails is read through its error record and named as the model's output, the transport, or the registry.
- **TRL against the frozen range**, per unit.
- **Market accessibility, evidence confidence and the overall score**, per unit. For each case, the difference between the arms' means is set beside the larger of the two within-arm differences. A between-arm difference no larger than that is reported as not distinguishable from run-to-run variation, whatever its sign.
- **The market cap**, per unit: triggered, applied, and the spread it recorded.
- **Tokens and wall time** per unit.

### Bars

| | Bar |
|---|---|
| S1 | **In every complete pair the new arm's unit is inside its frozen TRL range if the old arm's is** |
| S2 | **No new-arm unit fails for a reason in its registry** (a guardrail or contract tripped by the sources) where the old arm's unit completes |

**No prediction is made about the market cap or the market score.** A source
from another issuer can put another market figure in front of the scorer. The
spread between figures can widen and the cap can trigger more often. Either
direction is reported as found. With at most two cases and two runs each,
nothing here can show that a score improved.

## What counts as failure, and what follows

- **R1 fails:** the sign that tied the wrong pair is named. It is removed or tightened in a new commit, the saved-run replay is rerun, and the rule is taken out of the pipeline until then.
- **R2 fails:** the rule thinned a registry. It is taken out of the pipeline as it is.
- **R3 fails:** a defect. Fixed and Part R rerun from the record, at no cost.
- **R4 fails:** reported as a cost the maintainer decides on.
- **S1 or S2 fails:** the result says which case moved and what in its registry changed. Whether the rule stays is the maintainer's decision, on that reading.
- **All bars hold:** the result says the rule does what it was written to do. It claims no improvement in any score and no calibration.

Part S runs only if R1, R2 and R3 hold and at least one scored case's
registries differ.

## Budget and stop rules

| Part | What is paid | Estimate | Stop rule |
|---|---|---|---|
| R, web search | The old arm's searches, and the few only the new arm makes. Market selection v1 made 81 for twelve cases, and its new arm 13 more | 70 to 110 searches for ten cases, on the maintainer's search key | No new case starts once **200** live searches are recorded |
| R, model | The topic planner once per case and the heading translator for the one Chinese case | under 40,000 tokens, on the model named for Part S | none beyond the case count |
| S, model | up to 8 crew runs. The twelve runs of market selection v1 on `glm-5` recorded 991,572 tokens, about 83,000 a run; `deepseek-v4.1-flash-1017` used about 105,000 | **0.7 to 0.9 million tokens**; about 20 minutes a pair | No new unit starts once finished units record **1.1 million** tokens, and everything stops at the first unit the provider refuses for its allowance |

Page reads, URL checks and the academic and patent APIs cost nothing.

**A smaller Part S.** With one repeat per arm (up to 4 runs, about 0.4
million tokens, stop at 0.55 million) the TRL readings and both bars stand.
The comparison against run-to-run variation is then unavailable, and a score
difference between the arms could not be told from noise. The maintainer
chooses which when approving; the choice is written here before the first
run.

**Part R alone.** Part R answers the first question without any crew run.
The maintainer may approve it alone.

No failed unit is retried. No trial request is sent ahead of the first unit.
A unit still running after 30 minutes is ended and recorded as stopped by the
runner. The watcher reads a unit's status only after its process has exited:
the benchmark writes "running" at a unit's start, and a watcher that read
that as a failure ended a unit in the last comparison. Nothing here changes
the deployment or any variable on its host.

## What this cannot say

- **Nothing about calibration.** At most two topics, two runs each.
- **Nothing about unseen topics' scores.** The U cases are not scored.
- **Nothing about day-to-day variation in search.** Both arms see one day's recorded answers.
- **Nothing about a reader's judgement of the report.**
- **The labels are an AI assistant's**, not blind and not a human's. The same assistant wrote the rule.

## Recording

Raw registries, the request record and the benchmark outputs stay private
(`outputs/benchmark-runs/market-issuer-share-v1*` and `mis-v1-*`, not
committed). The result goes in
`docs/results-<date the runs finish>-market-issuer-share-v1.md`, with every
bar read as registered and nothing re-scored.
