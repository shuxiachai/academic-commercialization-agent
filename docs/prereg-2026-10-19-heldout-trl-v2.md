# Pre-registration — held-out TRL calibration v2

Registered **2026-10-19**, before any run of the ten topics below. The expected
ranges, the anchor entities and the decision thresholds are committed together
with this file, and they must not change once a run has started. A later doubt
about a range is recorded as an erratum beside the unchanged primary result,
never as a re-scored pass.

## Question

The first held-out batch scored **21 of 30** runs in range, but its scores were
compressed: no run scored above 7
([result](results-2026-10-18-heldout-trl-v1.md),
[diagnosis](results-2026-10-18-trl-compression-diagnosis.md)). Market
retrieval has since changed:

- topic-level deployment queries can now run, and component queries no longer take most market slots (#213);
- syndicated market-size releases are classed as market reports (#213);
- Wikipedia and sector sources are admitted (#215).

The rubric and scoring formula are unchanged. On ten topics never run before,
with the current production configuration, two questions:

1. How often does the delivered TRL fall inside its range?
2. Does any run now reach 8 or 9 where the evidence supports it?

## Why this design

The fix has to be tested on unseen topics, because the v1 topics are consumed.

- **High-maturity topics.** Five topics have ranges reaching 8 or 9 (V01, V02, V08, V09, V10). Four of them have a floor of 8. If compression persists, every run on those four misses, and the batch cannot reach the "supported" threshold. The design therefore puts the compression question directly to the primary measure.
- **Low-maturity topics.** Three topics have ceilings of 5 or 6 (V05, V06, V07). They check for the failure registered in August as F1: raising every score.
- **Scale and economics.** V10 is a deployed technology with poor economics. It tests the diagnosis's scale and cost mechanism directly.

## Cohort

Frozen in [`evals/heldout_trl_v2/cohort.json`](../evals/heldout_trl_v2/cohort.json),
with each range's evidence, sources and anchor entities. Case IDs `V01`–`V10`
reuse neither a `TOPICS` number nor a v1 ID.

| ID | Topic | Expected TRL | Input shape |
|---|---|---|---|
| V01 | robotic-assisted surgery | 8–9 | English |
| V02 | continuous glucose monitoring for diabetes | 8–9 | English |
| V03 | enhanced geothermal systems for electricity generation | 7–8 | English |
| V04 | pig kidney xenotransplantation | 5–7 | English |
| V05 | battery-electric aircraft for regional passenger flights | 5–6 | English |
| V06 | space-based solar power | 3–5 | English |
| V07 | hyperloop | 4–6 | **short** (1 word) |
| V08 | 量子密钥分发网络 | 7–9 | **Chinese** |
| V09 | 特高压直流输电 | 8–9 | **Chinese** |
| V10 | vertical farming for fresh produce | 8–9 | English |

**Selection.**
- None of these topics appears in the v1 cohort, in `TOPICS`, or among the 68 distinct topics in the local run history.
- Topics near earlier runs were avoided: display technologies (a quantum-dot LED topic was run), batteries, perovskites, hydrogen, nuclear (v1 had SMRs), brain-computer interfaces and the rubric's calibration-anchor technologies.
- Two candidates were dropped before anchoring. Foldable OLED displays were too close to the quantum-dot LED topic that was run. For bacteria-based self-healing concrete, the evidence found did not date its commercial use reliably.

**Anchoring and its limits.**
- Each range spans the defensible field-level and leading-application readings under the standard 1–9 definitions. Scale, cost, profitability and adoption breadth were not allowed to lower a range: they are MRL and market questions.
- An AI assistant (Claude) set the ranges using web search on 2026-10-19, and the maintainer reviewed them before dispatch. This is not an independent human-expert panel.
- V03's first commercial unit began operating 19 days before anchoring, so retrieval may lag it. V08's adoption figures rest on company and press claims.

## Fixed configuration

| Setting | Value |
|---|---|
| Code | the `main` commit that contains this file; batch identity records the exact commit and source hashes |
| Provider / model | `LLM_PROVIDER=qwen`, `QWEN_MODEL=qwen3.8-max`, `QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1`. This is the production model since 2026-10-18. It is set explicitly because a local `.env` may point the `OPENAI_*` fallbacks at another vendor. |
| Web search | Tavily, as in production |
| Evidence | live retrieval (no `--fixtures`) |
| Repetitions | 3 per topic, interleaved (30 runs) |
| Concurrency | 1 |
| Batch | `--experiment-id heldout-trl-v2` |

```bash
uv run python benchmark.py --cohort evals/heldout_trl_v2/cohort.json --repeat 3 --dry-run
LLM_PROVIDER=qwen QWEN_MODEL=qwen3.8-max \
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1 \
uv run python benchmark.py --cohort evals/heldout_trl_v2/cohort.json \
    --repeat 3 -c 1 --experiment-id heldout-trl-v2
uv run python benchmark_check.py --batch heldout-trl-v2
uv run python -m scripts.audits.market_query_origin outputs/benchmark-runs/heldout-trl-v2 \
    --cohort evals/heldout_trl_v2/cohort.json
```

## Primary measure and decision (registered before running)

The primary measure is the number of the 30 attempted runs whose delivered TRL
lies inside its expected range, boundaries inclusive. A run that delivers no
TRL counts as **not in range**, and completion is reported separately.

| Result | Reading |
|---|---|
| ≥ 21 / 30 in range | Held-out calibration **supported** at this revision |
| 16–20 / 30 | **Inconclusive** |
| ≤ 15 / 30 | Held-out calibration **not supported** |

The thresholds are v1's. Expectation, registered so it can be wrong: about
**15–21 / 30**. Retrieval changed, but the diagnosis's rubric-reading
mechanisms did not: the TRL 7 label anchor, scale and cost reasons, and
construction counted as demonstration.

## Secondary measures (registered readings)

1. **Compression.**
   - The number of runs scoring 8 or higher; v1 had 0 of 30.
   - Reading: if it is **0** again, compression persists despite the retrieval changes. The next lever is then how the scorer reads the rubric, or independent scores from several models, not retrieval.
   - Also reported: the distribution of scores and how many runs score exactly 7.
2. **Inflation check (F1).**
   - Runs above their ceiling on V05, V06 and V07 (9 runs).
   - Reading: **4 or more** above their ceiling is flagged as over-scoring of low-maturity topics.
3. **Direction of misses.** As in v1: below floor against above ceiling, with two thirds on one side reported as a directional bias, plus mean distance outside the range.
4. **Retrieval level.** This tests the retrieval changes, not TRL.
   - Anchor-entity coverage: market sources naming one of the case's fixed `anchor_entities`, matched case-sensitively as whole tokens.
   - Prediction: at least **7 of 10** topics have at least one such source in at least two of their three runs.
   - Query audit predictions: the topic-level deployment query runs in at least **27 of 30** runs, and no component query supplies more than one market source.
5. **Input-shape subgroup.** V07, V08 and V09 (9 runs), descriptive only.
6. **Existing proxies.** Completion, weighted-formula correctness, report structure and uncited numeric lines, from `benchmark_check.py`.
7. **Cost.** Recorded Crew-node cost, and Tavily searches used.

## Rules

- No prompt, rubric, retrieval or scoring change between the first and last run of the batch. A defect found mid-batch is recorded and fixed afterwards, in a new batch with a new ID.
- The ranges and anchor entities in `cohort.json` are frozen once the batch starts.
- Failed runs are not retried in this batch. Units never started may run under `--resume-batch heldout-trl-v2` with an unchanged identity.
- These topics become consumed for held-out purposes when the batch starts.
- **Comparison with v1 is descriptive only.** The topics and the model differ (v1 used `qwen3.7-plus`).

## Preflight

Before the first run, one minimal model request and one web search check that
the configured Qwen and Tavily credentials are accepted. The preflight uses no
cohort topic. If it fails, nothing is dispatched.

## Stop rules

Stop dispatching new runs and record the reason if any of these happens:

- an authentication, quota or account error from the model or search provider;
- three consecutive run failures;
- recorded Crew-node cost for the batch exceeds **USD 12**;
- Tavily plan usage reaches **900** of the account's 1,000 monthly searches.

## Budget

v1 recorded 2.41 million Crew-node tokens over 30 runs, about 2.09 million
input and 0.32 million output. At the `qwen3.8-max` upper-bound price of 2.00
input and 6.00 output USD per million tokens, the same volume is about
**USD 6**, and the USD 12 stop rule allows for a longer-output model.

v1 used about 6–7 web searches per run, so this batch is expected to need
about 200–250 Tavily searches. Helper calls are recorded separately.

## Authorization

The maintainer approved this batch and its budget on 2026-10-19. Dispatch
waits for the maintainer's review of the cohort ranges, which this file
records.

## What this cannot establish

- Source truth, claim support or user value. TRL calibration is one proxy.
- Behaviour on other providers. Only `qwen3.8-max` is measured.
- Which retrieval change caused any difference from v1: the topics and the model also changed.
- Stability over time. Live retrieval reflects what the web returned on the run date.
- Expert-level ground truth. The anchors are AI-assisted and maintainer-reviewed.
