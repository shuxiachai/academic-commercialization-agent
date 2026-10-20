# Pre-registration — held-out TRL calibration v1

Registered **2026-10-18**, before any run of the ten topics below. The
expected ranges and the decision thresholds are committed together with this
file and must not change once a run has started. A later doubt about a range
is recorded as an erratum next to the unchanged primary result, never as a
re-scored pass.

## Question

On topics the system has never been run on, with expected TRL ranges fixed
from external evidence before any run, how often does the delivered TRL fall
inside its range?

## Why this is needed

The advertised baseline (`benchmark.TOPICS`, 26/30 in range) is not
held-out validation: several of its ranges were adjusted after early
observations, as the README and the comments above `TOPICS` state. It was
also measured on an earlier revision. Since then, three changes have reached
the evidence the scorer reads: the uploaded paper's summary (#202), abstract
truncation (#203) and the grading of repository deposits and preprints (#204).

## Cohort

Frozen in [`evals/heldout_trl_v1/cohort.json`](../evals/heldout_trl_v1/cohort.json),
with each range's evidence and sources. Case IDs `H01`–`H10` do not reuse a
`TOPICS` number.

| ID | Topic | Expected TRL | Input shape |
|---|---|---|---|
| H01 | small modular reactors for grid electricity | 7–9 | English |
| H02 | fusion power | 3–5 | **short** (2 words) |
| H03 | implantable brain-computer interfaces for paralysis | 5–7 | English |
| H04 | psilocybin therapy for treatment-resistant depression | 7–8 | English |
| H05 | direct air capture of carbon dioxide | 6–8 | English |
| H06 | 漂浮式海上风电 | 8–9 | **Chinese** |
| H07 | 人工光合作用制备太阳能燃料 | 3–5 | **Chinese** |
| H08 | precision fermentation for dairy proteins | 7–9 | English |
| H09 | DNA data storage | 4–6 | English |
| H10 | drone delivery of medical supplies | 8–9 | English |

**Selection.**
- None of these topics appears among the 42 distinct topics in the local run history.
- Topics near earlier local runs were avoided: PEM electrolysis, hydrogen storage, perovskites, solid-state and sodium-ion batteries, CCS, cultivated meat, CRISPR, CAR-T and superconductors.
- A first candidate, solid-state automotive lidar, was replaced before anchoring by floating offshore wind. Chinese usage of the term includes semi-solid-state units, which are in mass production, while no reliable production evidence was found for fully solid-state units, so the topic's scope was ambiguous.
- Three cases cover input shapes absent from the baseline: one very short topic and two Chinese topics.

**Anchoring and its limits.** Each range spans the defensible field-level
and leading-application readings under the standard 1–9 TRL definitions,
following the CRISPR precedent in `TOPICS`. The ranges were set by an AI
assistant (Claude) using web search on 2026-10-18 and reviewed by the
maintainer. This is not an independent human-expert panel. Several anchors
rely on company statements or secondary reporting, which the cohort file
notes. Ranges were set from external evidence, not from the system's
scoring rubric.

## Fixed configuration

| Setting | Value |
|---|---|
| Code | the `main` commit that contains this file; batch identity records the exact commit and source hashes |
| Provider / model | `LLM_PROVIDER=qwen`, `QWEN_MODEL=qwen3.5-plus`, `QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1`: the production configuration, set explicitly because an unset `QWEN_MODEL`/`QWEN_API_BASE` falls back to `OPENAI_MODEL_NAME`/`OPENAI_API_BASE`, which a local `.env` may point at another vendor |
| Web search | Tavily, as in production (the default when `TAVILY_API_KEY` is set) |
| Evidence | live retrieval (no `--fixtures`) |
| Repetitions | 3 per topic, interleaved (30 runs) |
| Concurrency | 1 |
| Batch | `--experiment-id heldout-trl-v1` |

```bash
# Scheduling preview, no provider calls:
uv run python benchmark.py --cohort evals/heldout_trl_v1/cohort.json --repeat 3 --dry-run
# The measurement, only after explicit authorization:
LLM_PROVIDER=qwen QWEN_MODEL=qwen3.5-plus \
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1 \
uv run python benchmark.py --cohort evals/heldout_trl_v1/cohort.json \
    --repeat 3 -c 1 --experiment-id heldout-trl-v1
uv run python benchmark_check.py --batch heldout-trl-v1
```

## Primary measure and decision (registered before running)

The primary measure is the number of the 30 attempted runs whose delivered
TRL lies inside its expected range, boundaries inclusive. A run that delivers
no TRL counts as **not in range**, and completion is reported separately.

| Result | Reading |
|---|---|
| ≥ 21 / 30 in range | Held-out calibration **supported** at this revision |
| 16–20 / 30 | **Inconclusive** |
| ≤ 15 / 30 | Held-out calibration **not supported**; the 26/30 baseline should not be read as general accuracy |

Expectation, registered so it can be wrong: about **19–24 / 30**, lower than
the tuned baseline.

## Secondary measures (descriptive, no thresholds)

1. **Topics in range in all three repetitions.** The baseline had 7 of 10.
2. **Direction of misses.** The baseline's main defect was scores sitting on the floor of their range, so this reports how many misses fall below the floor and how many above the ceiling. If at least two thirds of misses fall on one side, that is reported as a directional bias. Also reported: mean distance outside the range, and runs exactly on their floor.
3. **Input-shape subgroup.** H02, H06 and H07 (9 runs) are reported separately. With n = 9 this is descriptive only and supports no claim about Chinese or short inputs in general.
4. **Existing proxies.** Completion, weighted-formula correctness, report structure and uncited numeric lines, as computed by `benchmark_check.py`.
5. **Source mix.** The share of academic sources graded as preprints or repository deposits under #204's rule.
6. **Cost.** Recorded Crew-node cost, which is not a full invoice.

## Rules

- No prompt, rubric, retrieval or scoring change between the first and last run of the batch. A defect found mid-batch is recorded and fixed afterwards, in a new batch with a new ID.
- The ranges in `cohort.json` are frozen at this commit. The batch identity binds each case's topic and range, so the batch cannot be resumed under different ranges.
- Failed runs are not retried in this batch. Units never started may run under `--resume-batch heldout-trl-v1` with an unchanged identity.
- These topics become consumed for held-out purposes once the batch starts. A later method change cannot be validated on them again and needs a new cohort.

## Preflight

Before the first run, one minimal model request and one web search check
that the configured Qwen and Tavily credentials are accepted. The preflight
uses no cohort topic and is not part of the 30 runs. If it fails, nothing is
dispatched.

## Stop rules

Stop dispatching new runs and record the reason if any of these happens:

- an authentication, quota or account error from the model or search provider;
- three consecutive run failures;
- recorded Crew-node cost for the batch exceeds **USD 5**.

## Budget

The six-node arm of the topology ablation recorded a median Crew-node cost of
about USD 0.03 per run (33 cells, an earlier provider). Thirty runs are
therefore expected to cost on the order of USD 1 in model tokens, plus web
search and helper calls, which are recorded separately. The USD 5 stop rule
bounds the model part. The historical median run time was about 3 minutes.

## Authorization

This file prepares the measurement; it does not authorize it. Running the
batch requires the maintainer's explicit approval, after confirming that the
production web-search key used for comparison is the active one.

## What this cannot establish

- Source truth, claim support or user value. TRL calibration is one proxy.
- Behaviour on other providers. Only `qwen3.5-plus` is measured.
- Stability over time. Live retrieval reflects what the web returned on the run date.
- Expert-level ground truth. The anchors are AI-assisted and maintainer-reviewed.
