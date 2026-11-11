# Pre-registration — held-out spot check on deepseek-v4.1-flash-1017

Registered **2026-11-11**, before any run. Five topics from the frozen v2
cohort, one run each, on the model the deployment has been serving since
2026-11-09 and that this project has never read against a frozen range.

## Question

The deployment pays for an administrator's runs on its own model variable
(#359). That variable was `deepseek-v4-pro-0813` when the streamed-call batch
was read on 2026-11-09 (5/5 in range on these five topics) and was moved the
same day to `deepseek-v4.1-flash-1017`, where the free allowance was. Since
then every operator-funded production run has been on a model with no
reading at all. The one production run that finished on it scored the topic
at 69.3 where two runs on the model before it gave 72.7 and 76.7, which is one run
and says nothing by itself.

Two questions, in order:

1. Does a live run complete end to end on `deepseek-v4.1-flash-1017` on the
   current `main`, on every one of five topics, without a failure in the
   model's own output?
2. Where does the delivered TRL land against the ranges frozen for these
   topics on 2026-10-19?

This is a spot check. Five single runs cannot measure calibration; the v2
batch needed thirty. Its use is narrower and stated below: whether there is
a reason, visible in five runs, not to keep serving this model.

## Design

| | |
|---|---|
| Cohort | [`evals/heldout_trl_v2/cohort.json`](../evals/heldout_trl_v2/cohort.json), unchanged |
| Cases | V01 robotic-assisted surgery (8–9), V03 enhanced geothermal (7–8), V06 space-based solar power (3–5), V07 hyperloop (4–6, one word), V09 特高压直流输电 (8–9, Chinese) |
| Why these five | the same five as the 2026-11-08 part A batch on `deepseek-v4-pro` and the 2026-11-09 streamed batch on `deepseek-v4-pro-0813`, so each topic has two earlier single runs on a neighbouring model to stand beside |
| Model | `deepseek-v4.1-flash-1017` through the `qwen` transport (`QWEN_MODEL=deepseek-v4.1-flash-1017`, DashScope compatible mode); non-thinking, JSON object output, streamed, as every crew node now is |
| Retrieval | live, current `main`; OpenAlex anonymous (`--allow-anonymous-openalex`), Tavily and Serper on the maintainer's keys |
| Repeats | 1 |
| Concurrency | 1 |
| Batch | `--experiment-id heldout-spot-2026-11-11-deepseek-v4.1-flash-1017` |
| Code | `main` at `47a3840` |
| Where it runs | the maintainer's machine, not the deployment's host |

```bash
QWEN_MODEL=deepseek-v4.1-flash-1017 uv run python benchmark.py \
    --cohort evals/heldout_trl_v2/cohort.json --only V01,V03,V06,V07,V09 \
    -c 1 --allow-anonymous-openalex --experiment-id heldout-spot-2026-11-11-deepseek-v4.1-flash-1017
```

## Budget and stop rule

The one finished production run on this model recorded 105,466 crew tokens.
Five runs are expected near 530,000, inside the model's free allowance on
the maintainer's account. The batch stops before the next topic if the
tokens recorded by the finished units exceed **600,000**; a watcher beside
the runner ends the process when that happens, and a unit it ends is
recorded as stopped by the rule, not as a failure. No failed unit is retried
inside this batch.

One streamed request of a few tokens is sent first to confirm the model
name and the allowance answer; it is not a unit and its usage is reported.

## Readings, fixed now

- **Completion**: units that reach a scored report, out of five. Any failure
  is read through its error record and its attempt rows, and named as the
  model's output, the transport, retrieval or the pipeline.
- **TRL against the frozen range**, per case: in range, above ceiling, or
  below floor, with the topics named. Beside each, the two earlier readings
  on the same topic (2026-11-08 and 2026-11-09), as context and not as a
  paired comparison: model, date of the live evidence and the anonymous
  OpenAlex pool all differ.
- **Tokens and wall time per run**, against 423,040 tokens and 53.7 minutes
  (2026-11-08, plain requests) and 607,840 tokens and 31.4 minutes
  (2026-11-09, streamed) for the same five topics.
- **Attempt rows**: every provider attempt that did not return, by node, and
  every guardrail second call, by node and by what it rejected.
- **Retrieval shape**: sources delivered per domain, and whether V07's plan
  keeps the word "hyperloop".

## The decision this feeds, stated now

The result recommends that the deployment keep serving
`deepseek-v4.1-flash-1017` unless either of these holds:

- a unit fails to complete for a reason in the model's output (a contract it
  cannot meet after the pipeline's own retries); or
- two or more of the five land outside their frozen range in the same
  direction.

If the rule fires, the recommendation is to move the deployment's model
variable to a model with a better reading on these topics, which is the
operator's decision and is not made here, and the other five topics are not
run on this model. If it does not fire, the other five (V02, V04, V05, V08,
V10) are the next reading, under their own protocol, before anything
stronger is said. Either way it is a sentence in the result, not an
adoption.

## What this cannot say

- Nothing about calibration: five runs, one each.
- Nothing about the deployment's path to the provider. These runs leave from
  the maintainer's machine; the stalls measured from the host on 2026-11-09
  and 2026-11-10 are a property of that host's route and are not exercised
  here.
- Nothing about a model a visitor names with their own key.
- Nothing attributable to the model alone, for the reasons given under the
  second reading.

## Recording

Raw outputs stay in
`outputs/benchmark-runs/heldout-spot-2026-11-11-deepseek-v4.1-flash-1017/`
(private, not committed). The result goes in
`docs/results-2026-11-11-heldout-spot-check-deepseek-v4.1-flash.md` with the
readings above and nothing re-scored.
