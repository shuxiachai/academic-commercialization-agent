# Pre-registration — academic title gate, live check v1

Registered **2026-10-21**, before any run below. It follows the
[title-gate result](results-2026-10-20-academic-title-gate-v1.md) and the
[deployment erratum](errata-2026-10-20-academic-title-gate-v1-deployment.md).
The gate under test shipped in #245 (`c35fa1a`).

## Questions

**A. Delivered evidence.** Production fills a capped number of academic
slots. When it does so live, does the new gate deliver fewer off-topic papers
than the old one, without leaving topics short of academic sources?

The offline replay could not model slot filling. A rejected paper may be
replaced by another, and a stricter gate may leave slots empty.

**B. End to end.** Under the current production configuration, do the two
topics that fell below their floor in held-out v2 now land in range? The
topics are hyperloop and space-based solar power.

## Why

In held-out v2 (old gate, `qwen3.8-max`), the lowest score on each of these
topics came from the run with the most off-topic academic papers:

| Run | TRL (range) | Academic sources | Off-topic |
|---|---|---|---|
| space-based solar power, rep 1 | 3 (3–5) | 8 | 3 |
| space-based solar power, rep 2 | 3 (3–5) | 8 | 3 |
| space-based solar power, rep 3 | **2** (3–5) | 6 | **4** |
| hyperloop, rep 1 | 4 (4–6) | 8 | 2 |
| hyperloop, rep 2 | **3** (4–6) | 8 | 1 |
| hyperloop, rep 3 | **2** (4–6) | 8 | **6** |

In total, 19 of the 46 academic sources (41%) were off-topic, by the title
gate v1 labels. Three runs are not evidence of cause; the pattern is why
these topics are the ones checked end to end.

## Part A — live academic retrieval under both gates (no model, no web search)

### Plans

The 20 consumed held-out topics, with one frozen plan per topic: rep 1 of
`heldout-trl-v1-c` (H01–H10) and of `heldout-trl-v2` (V01–V10). Each plan
records the planned phrase, the aliases and the weight profile, and is stored
in `evals/academic_gate_live_v1/plans.json`. No planner or model call is made.

### Procedure

`collect.py` runs `source_pipeline._collect_academic_primary` twice per
topic, once with each gate:

- **New gate:** `_academic_title_matches` with the anchor production
  derives.
- **Old gate:** `_title_matches_topic` on the planned phrase, as before #245.

Both arms use the production settings: at most 8 academic sources, and a
minimum of 3 before the fallback.

- **Shared responses:** responses from OpenAlex, Semantic Scholar, PubMed and
  arXiv are cached on first use, so both arms fill from the same responses.
- **One-arm requests:** a request only one arm makes, such as a citation
  snowball from its own papers, is fetched live for that arm.
- **Order:** which arm runs first alternates by topic.
- **Fallback:** the Crossref/web fallback is not run. An arm that delivers
  fewer than 3 sources is recorded as triggering it.

### Labels

- **Who and how:** an AI assistant labels every delivered (topic, title)
  pair from the topic and the full title. The list is shuffled and blind to
  the arm.
- **Reuse:** pairs already labelled in title gate v1 keep that label, with
  its five errata applied.
- **Rubric:** the title gate v1 rubric.

### Measures and readings

1. **A1 (primary for Part A): off-topic papers delivered, summed over the 20
   topics.**
   - **Cleaner delivered evidence:** new ≤ 0.75 × old.
   - **Otherwise:** slot refill absorbs the gain.
2. **A2: topics delivering fewer than 3 academic sources.**
   - **Shortage risk confirmed:** new minus old ≥ 2.
   - **Otherwise:** no shortage increase detected.
3. **A3: relevant papers delivered, summed.**
   - **Flagged as a relevance loss:** new < 0.9 × old.
4. **Descriptive:** a per-topic table, the lane of each delivered source,
   and the number of live calls per arm.

## Part B — eight live runs under the production configuration

| Setting | Value |
|---|---|
| Code | the `main` commit that contains this file; the batch identity records the commit and source hashes |
| Cohort | `evals/heldout_trl_v2/cohort.json`, cases **V06** (space-based solar power, 3–5) and **V07** (hyperloop, 4–6), ranges unchanged |
| Provider / model | `LLM_PROVIDER=qwen`, `QWEN_MODEL=qwen3.8-27b`, `QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1`. This is the production model; it is set on the command line because the local `.env` points elsewhere. |
| Web search | Tavily, as in production |
| Evidence | live retrieval |
| Repetitions | 4 per topic, interleaved (8 runs) |
| Concurrency | 1 |
| Batch | `--experiment-id academic-gate-live-v1` |

```bash
uv run python benchmark.py --cohort evals/heldout_trl_v2/cohort.json --only V06,V07 --repeat 4 --dry-run
LLM_PROVIDER=qwen QWEN_MODEL=qwen3.8-27b \
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1 \
uv run python benchmark.py --cohort evals/heldout_trl_v2/cohort.json --only V06,V07 \
    --repeat 4 -c 1 --experiment-id academic-gate-live-v1
uv run python benchmark_check.py --batch academic-gate-live-v1
```

### Measures and readings

1. **B1 (primary for Part B): runs in range, out of 8.** A run that delivers
   no TRL counts as not in range.

   | Result | Reading |
   |---|---|
   | ≥ 7 / 8 | The below-floor misses do not recur under the current production configuration |
   | 5–6 / 8 | Inconclusive |
   | ≤ 4 / 8 | The misses persist; academic retrieval is not the lever that fixes them |

   Expectation, registered so it can be wrong: 5–7 / 8. The v2 baseline on
   these topics was 3 / 6, under a different model.
2. **B2: off-topic share of delivered academic sources across the 8 runs.**
   - **Labels:** written before any run's score is read, by the Part A
     procedure.
   - **Prediction:** at most 20%, against 41% in v2.
3. **B3: academic shortage.** Runs with fewer than 3 academic sources, or in
   which the academic web fallback ran (from the audit).
4. **B4: other measures.**
   - Completion.
   - The `benchmark_check.py` proxies.
   - Recorded Crew-node tokens.
   - Tavily searches.
5. **Descriptive:** each run's TRL beside its off-topic count.

## Rules

- **Order:** Part A runs before Part B. Part A's result does not change Part
  B.
- **No changes mid-batch:** no code, prompt or rubric change between Part B's
  first and last run. A defect found mid-batch is recorded and fixed
  afterwards.
- **Failures:** failed runs are not retried. Units never started may run
  under `--resume-batch academic-gate-live-v1` with an unchanged identity.
- **Comparison with v2 is descriptive only.** The model
  (`qwen3.8-max` → `qwen3.8-27b`) and the gate changed together.

## Preflight

Before the first run, one minimal model request and one web search check
that the configured Qwen and Tavily credentials are accepted. The preflight
uses no cohort topic. If it fails, nothing is dispatched.

## Stop rules

Stop dispatching and record the reason if any of these happens:

- an authentication, quota, `Arrearage` or other account error from the
  model or the search provider. The batch must stay inside the free model
  quota;
- three consecutive run failures;
- Tavily plan usage reaches **900** of the account's 1,000 monthly searches.

## Budget

- **Model:** the maintainer's Bailian free quota for `qwen3.8-27b`. In the
  maintainer's experience it covers about ten runs; this batch uses 8 plus
  the preflight. Held-out v1 averaged about 80,000 Crew-node tokens per run,
  so expect about 0.65 million tokens.
- **Web search:** up to about 14 Tavily searches per run, about 110 in all.
- **Part A:** free public APIs only.

## Authorization

The maintainer approved this step on 2026-10-21. Dispatch waits for the
maintainer's review of this file.

## What this cannot establish

- **Attribution.** Part B cannot separate the gate from the model change.
  Part A isolates the gate's effect on delivered evidence, but not on scores.
- **Size.** Eight runs on two topics.
- **Development evidence only.** The topics are consumed, and hyperloop
  motivated the gate. This is not held-out validation.
- **AI labels.** The labels are not human gold.
- **Drift.** Live retrieval drifts, so Part A's responses are those of the
  day it runs.

## Files

| File | sha256 (LF-normalised) |
|---|---|
| `evals/academic_gate_live_v1/build_plans.py` | `47436f316cdaaf73d6fa48799b587087aa44fa5041345da5c7362b0e80269aa1` |
| `evals/academic_gate_live_v1/collect.py` | `7242714983df55926b0a9afb4c25ae12f95bd58cfc0694294aab8c9bae1e9af8` |
| `evals/academic_gate_live_v1/plans.json` | `f08942e05f05451838a62a4b37b1fad5dab3c3227aa2fc7f9cd8110ba4e23390` |
