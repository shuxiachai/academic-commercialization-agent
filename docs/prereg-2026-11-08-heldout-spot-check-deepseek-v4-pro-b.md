# Pre-registration — held-out spot check on deepseek-v4-pro, part B

Registered **2026-11-08**, after part A's result was read and before any run
of the five topics below. Same design, same model, same code; the other half
of the v2 cohort, so that every one of its ten topics has one run on this
model.

## Question

[Part A](prereg-2026-11-08-heldout-spot-check-deepseek-v4-pro.md) ran V01,
V03, V06, V07 and V09 and read 5/5 complete and 5/5 in range
([result](results-2026-11-08-heldout-spot-check-deepseek-v4-pro.md)). The
question for part B is the same two, on the five topics part A did not run,
plus one that only the pair can answer: with all ten v2 topics run once on
`deepseek-v4-pro`, is there a reason not to make it the model of the next
registered thirty-run batch? Ten single runs still do not measure
calibration; they are the reading that decision needs.

## Design

| | |
|---|---|
| Cohort | [`evals/heldout_trl_v2/cohort.json`](../evals/heldout_trl_v2/cohort.json), unchanged |
| Cases | V02 continuous glucose monitoring for diabetes (8–9), V04 pig kidney xenotransplantation (5–7), V05 battery-electric aircraft for regional passenger flights (5–6), V08 量子密钥分发网络 (7–9, Chinese), V10 vertical farming for fresh produce (8–9) |
| Why these five | the five v2 topics part A left out; between them two more high floors, the cohort's second low ceiling, the second Chinese input, and V10, the scale-and-economics topic |
| Model, transport, retrieval, repeats, concurrency | as part A: `deepseek-v4-pro` through the `qwen` transport, live retrieval, anonymous OpenAlex, one run each, serial |
| Batch | `--experiment-id heldout-spot-2026-11-08-deepseek-v4-pro-b` |
| Code | `main` at `9bd948c` (part A ran at `14a2097`; the commits between are the part A documents) |

```bash
QWEN_MODEL=deepseek-v4-pro uv run python benchmark.py \
    --cohort evals/heldout_trl_v2/cohort.json --only V02,V04,V05,V08,V10 \
    -c 1 --allow-anonymous-openalex --experiment-id heldout-spot-2026-11-08-deepseek-v4-pro-b
```

## Budget and stop rule

Part A used 423,040 tokens; about 577,000 of the free allowance remain. The
batch stops before the next topic if its own tokens so far exceed
**500,000**, leaving the allowance a margin for one retry batch of one
topic. No failed unit is retried inside the batch.

## Readings, fixed now

The same four as part A, per case: completion, TRL against the frozen range
as named counts, tokens and wall time, retrieval shape. Then, over the ten
runs of both parts together:

- the count in range out of ten, with the misses named and their direction;
- the mean and range of tokens a run, against v2's 91,745;
- every retry or refusal, by node.

The decision this feeds, stated now: part B recommends `deepseek-v4-pro`
for the next thirty-run batch unless any run fails to complete for a reason
in the model's output, or two or more of the ten runs land outside their
range in the same direction. Either way the recommendation is a sentence in
the result, not an adoption; the thirty-run batch would have its own
protocol.

## What this cannot say

As part A: nothing about calibration, nothing about production, nothing
attributed.

## Recording

Raw outputs in `outputs/benchmark-runs/heldout-spot-2026-11-08-deepseek-v4-pro-b/`
(private). The result goes in
`docs/results-2026-11-08-heldout-spot-check-deepseek-v4-pro-b.md`, which
also carries the ten-run table.
