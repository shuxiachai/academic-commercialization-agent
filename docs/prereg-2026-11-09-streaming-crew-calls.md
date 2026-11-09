# Pre-registration — streaming crew calls

Registered **2026-11-09**, before any paid run of the five topics below, after
the first production run with per-attempt records and before the change it
tests is merged.

## Question

The 2026-11-09 production run (`deepseek-v4-pro-0813`, 1,072 s) was the first
with a record of every provider attempt. It spent 774 of its 1,072 seconds in
requests that had stopped delivering: the writer's first two attempts hung for
302 and 312 seconds and the third returned in 95; the scorer hung 160 seconds
and then returned in 27. The three evidence agents returned in 36–45 s. The
2026-11-08 run (782 s) and the 2026-10-23 and 2026-10-25 runs have the same
signature: one stage twice as long as its answer, usage showing one request.

The change: every crew node streams its answer, so the SDK timeout bounds the
wait for one chunk (60 s) instead of the whole answer; the project wrapper
stays the only retry owner on every path; CrewAI 1.14.7 asks for usage in the
final chunk; each attempt row also carries the call sequence on its node.

Two questions. Does a streamed run keep the output contract intact (every node
answers, usage recorded for every node, guardrails and scores unchanged in
kind)? And does it remove the stalls, read from the attempt rows rather than
from wall time alone?

## Design

| | |
|---|---|
| Cohort | [`evals/heldout_trl_v2/cohort.json`](../evals/heldout_trl_v2/cohort.json), unchanged |
| Cases | V01 robotic-assisted surgery (8–9), V03 enhanced geothermal systems (7–8), V06 space-based solar power (3–5), V07 hyperloop (4–6), V09 特高压直流输电 (8–9, Chinese) |
| Why these five | the part A set of 2026-11-08: all five were in range that day on `deepseek-v4-pro`, so a miss here would be new; the one-word topic (V07, whose scorer retried) and the Chinese topic (V09, whose writer retried and cost the most tokens) are included |
| Model, transport | `deepseek-v4-pro-0813` through the `qwen` transport, the production model since 2026-11-08; non-thinking JSON output as in production |
| Retrieval, repeats, concurrency | live retrieval, anonymous OpenAlex, one run each, serial |
| Code | the commit of this document, on branch `perf/stream-crew-calls` |
| Batch | `--experiment-id stream-2026-11-09-deepseek-v4-pro-0813` |

```bash
LLM_PROVIDER=qwen QWEN_MODEL=deepseek-v4-pro-0813 uv run python benchmark.py \
    --cohort evals/heldout_trl_v2/cohort.json --only V01,V03,V06,V07,V09 \
    -c 1 --allow-anonymous-openalex --experiment-id stream-2026-11-09-deepseek-v4-pro-0813
```

## Budget and stop rule

The model's free allowance showed 764,250 of 1,000,000 tokens when this was
written, and the maintainer has set the whole of it aside for this batch
(production can move to another model's allowance). The same five topics cost
423,040 tokens on 2026-11-08 on the undated model. The batch stops before the
next topic if its own tokens so far exceed **600,000**, or after two
consecutive units fail to complete. No failed unit is retried inside the batch.

## Readings, fixed now

Per case, from `meta.json`:

- completion;
- usage: six agent rows, each with at least one successful request and a
  non-zero completion count (a streamed answer whose usage went missing would
  show here first);
- attempt rows (`llm_attempts`): the count of attempts that did not return,
  their durations, and the longest; whether any non-returned attempt lasted
  more than twice the per-chunk bound (120 s), which would mean the bound
  does not do what it says;
- wall time, against the same topic on 2026-11-08 (V01 972 s and V09 1,061 s
  include planner timeouts before send; V03 430 s, V06 327 s, V07 369 s);
- TRL against the frozen range, as a guard: all five were in range on
  2026-11-08.

## Decision, stated now

Streaming goes to production if, over the five runs: all five complete; every
run has six usage rows with a successful request each; no non-returned attempt
lasts more than 120 seconds; and at least four of five TRL scores are inside
their frozen ranges, with any miss named. Wall time is reported, not gated: a
run with no stalls to remove will not get faster, and that is a finding, not a
failure.

If a run fails to complete for a reason in the streaming path (a parse of a
partial answer, usage missing, a chunk-bound timeout on a healthy answer),
the change does not merge in this form, whatever the other readings say.

## What this cannot say

Nothing about calibration (five single runs); nothing about the stall's cause
upstream (the rows show when a connection stopped delivering, not why); and
nothing about how often production stalls, since two runs are two runs.

## Recording

Raw outputs in `outputs/benchmark-runs/stream-2026-11-09-deepseek-v4-pro-0813/`
(private). The result goes in `docs/results-2026-11-09-streaming-crew-calls.md`.
