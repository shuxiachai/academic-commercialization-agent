# Pre-registration — held-out spot check on deepseek-v4-pro

Registered **2026-11-08**, before any run. Five topics from the frozen v2
cohort, one run each, on a model this project has never run, after four weeks
in which the serving layer changed and the pipeline did not.

## Question

Since the v2 held-out batch of 2026-10-19 the repository gained accounts,
email, a landing page, per-account caps and an admin console (#311–#355),
and the maintainer's free quota moved to `deepseek-v4-pro` on DashScope. The
crew, the retrieval and the scoring did not change. Two questions, in order:

1. Does a live run still complete end to end from the CLI on the current
   `main`, with the current retrieval, on a model the code has never seen?
2. Where the delivered TRL lands against the ranges frozen for these topics
   on 2026-10-19, so that a later, larger batch on this model has a first
   reading to compare against.

This is a spot check. Five runs cannot measure calibration; the v2 batch
needed thirty, and its 25/30 was read against thresholds this check does not
reuse. Nothing here adopts or retires anything.

## Design

| | |
|---|---|
| Cohort | [`evals/heldout_trl_v2/cohort.json`](../evals/heldout_trl_v2/cohort.json), unchanged |
| Cases | V01 robotic-assisted surgery (8–9), V03 enhanced geothermal (7–8), V06 space-based solar power (3–5), V07 hyperloop (4–6, one word), V09 特高压直流输电 (8–9, Chinese) |
| Why these five | one high-maturity topic that v2 scored in range, one mid, one low-ceiling topic that v2 missed below floor, the short input, and the Chinese input |
| Model | `deepseek-v4-pro` through the `qwen` transport (`QWEN_MODEL=deepseek-v4-pro`, DashScope compatible mode); non-thinking, JSON object output, as for every model on this transport |
| Why this model | the maintainer's unused free quota (1,000,000 tokens to 2026-11-29). It is not the production model: production is bring-your-own-key, and this run says nothing about any key a visitor brings |
| Retrieval | live, current `main`; OpenAlex anonymous (`--allow-anonymous-openalex`; no key held), Tavily and Serper on the maintainer's keys |
| Repeats | 1 |
| Concurrency | 1 |
| Batch | `--experiment-id heldout-spot-2026-11-08-deepseek-v4-pro` |
| Code | `main` at `14a2097` |

```bash
QWEN_MODEL=deepseek-v4-pro uv run python benchmark.py \
    --cohort evals/heldout_trl_v2/cohort.json --only V01,V03,V06,V07,V09 \
    -c 1 --allow-anonymous-openalex --experiment-id heldout-spot-2026-11-08-deepseek-v4-pro
```

## Budget and stop rule

The v2 batch used 2,752,364 crew tokens over 30 runs, about 92,000 a run.
Five runs are expected near 460,000. The batch stops before the next topic if
the tokens recorded so far exceed **600,000**, and no failed unit is retried
inside this batch; a retry, if any, is a new batch with its own id. The
anonymous OpenAlex budget is shared; a refusal stops the run before the crew,
as `benchmark.py` already does, and is recorded as such.

## Readings, fixed now

- **Completion**: units that reach a scored report, out of five. Five is the
  expectation; any failure is read through its error record, and a failure on
  a model-contract field (as v2's reviewer bound) is named as such.
- **TRL against the frozen range**, per case: in range, above ceiling, or
  below floor. Reported as counts with the topics named; no threshold is set,
  and no claim of "supported" or "falsified" is made on five runs.
- **Tokens and wall time per run**, against v2's 92,000 per run on
  `qwen3.8-max`. The recorded cost figure uses the Qwen price basis and is
  not this model's price; tokens are the measure.
- **Retrieval shape**: academic sources delivered against the minimum, and
  whether V07's plan keeps the word "hyperloop" (the v2 failure that #248
  corrected).

## What this cannot say

- Nothing about calibration: five runs, one each.
- Nothing about the production path: the web client, accounts, caps and
  email are not on the CLI path. A production check needs a visitor's own key
  and is a separate decision.
- Nothing attributable: the model, the date of the live evidence and the
  anonymous OpenAlex pool all differ from v2 at once.

## Recording

Raw outputs stay in `outputs/benchmark-runs/heldout-spot-2026-11-08-deepseek-v4-pro/`
(private, not committed). The result goes in
`docs/results-2026-11-08-heldout-spot-check-deepseek-v4-pro.md` with the
numbers above and nothing re-scored.
