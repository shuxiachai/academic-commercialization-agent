# Result — streaming crew calls

Run **2026-11-09** under the
[pre-registered protocol](prereg-2026-11-09-streaming-crew-calls.md), after it
was committed and before any of these five runs. Five v2 topics, one live run
each, serial, `deepseek-v4-pro-0813` through the `qwen` transport, branch
`perf/stream-crew-calls` at `836c0f0`. Batch
`stream-2026-11-09-deepseek-v4-pro-0813`; raw outputs private. Nothing
re-scored.

## Headline

- **Completion 5/5.** Six usage rows in every run, each with a successful
  request and a non-zero completion count.
- **Stalled attempts 0 of 35.** Every provider attempt returned; the longest
  was a healthy 175-second reviewer answer (V09), which the previous
  150-second request window would have killed and retried.
- **TRL in range 5/5**, as on 2026-11-08.
- **Serial wall time 31.4 minutes** against 53.7 for the same five topics on
  2026-11-08 (the undated model, plain requests).
- **607,840 crew tokens**, against 423,040 on 2026-11-08. The difference is
  the model variant and five guardrail second calls, not streaming; see below.
  The 600,000 stop rule binds before a unit starts and stood at 456,762 when
  the last unit began.
- **Every decision criterion stated in advance is met.** Streaming goes to
  production.

## Per unit

| Case | Topic | Expected | TRL | Score | Sources A/P/M | Tokens | Time | 2026-11-08 time | Attempts |
|---|---|---|---|---|---|---|---|---|---|
| V01 | robotic-assisted surgery | 8–9 | 8.0 | 74.3 | 8/8/8 | 95,919 | 232 s | 972 s¹ | 6, all returned, longest 88 s (writer) |
| V03 | enhanced geothermal systems | 7–8 | 7.3 | 70.9 | 8/8/8 | 133,838 | 423 s | 430 s | 8, all returned; writer second call, reviewer second call |
| V06 | space-based solar power | 3–5 | 5.0 | 51.1 | 8/8/7 | 98,573 | 262 s | 327 s | 6, all returned, longest 116 s (writer) |
| V07 | hyperloop | 4–6 | 5.0 | 51.1 | 6/8/8 | 128,432 | 398 s | 369 s | 8, all returned; writer second call, reviewer second call |
| V09 | 特高压直流输电 (Chinese) | 8–9 | 9.0 | 82.2 | 8/8/8 | 151,078 | 509 s | 1,061 s¹ | 7, all returned; reviewer second call; longest 175 s (reviewer) |

¹ Included a planner timeout before send on 2026-11-08.

Per-attempt durations, all returned (seconds): evidence agents 29–113, with
the market analyst the slowest in four of five runs (43, 86, 51, 57, 113);
writer first calls 88, 101, 116, 99, 113; reviewer first calls 8, 70, 9, 65,
175; scorer 27–40.

## What the attempt rows say

The 2026-11-09 production run had three attempts that stopped delivering
(302, 312 and 160 seconds) out of nine; this batch had none out of 35. Two
runs are two runs, and five are five: this does not measure how often a plain
request stalls. It does say that a streamed answer of 175 seconds is carried
to the end, and that no healthy answer was cut by the 60-second per-chunk
bound, which was the risk stated in advance.

## Second calls

Five guardrail second calls, all absorbed, none reaching a report:

- Writer, V03 and V07: the draft failed the report validator (V07's errors
  were on proposed stop criteria in the decision section); the second draft
  passed.
- Reviewer, V03, V07 and V09: the correction plan failed the plan's field
  contract (a pydantic validation error, not malformed JSON; the batch log
  kept only the first line, so the field is not named here); the second plan
  passed, and V09's second plan returned in 5 seconds.

The 2026-11-08 part A batch had two guardrail retries across the same five
topics; part B had three across its five. Five here is within the range the
model has shown, and the retry mechanism is the same code.

## Tokens

607,840 against 423,040 on 2026-11-08 for the same topics. Two things
account for it, neither of them streaming:

- **The model variant writes more.** On every topic the three evidence agents'
  answers were 40–100% longer than on the undated model with prompts of the
  same size (academic 1,318 → 2,859 on V01; market 1,604 → 8,034 on V09). The
  two production runs of 2026-11-08 and 2026-11-09 on `deepseek-v4-pro-0813`,
  both plain requests, had evidence answers of 2,060–3,402 tokens, the same
  size as here. A tiny streamed request made before this batch returned 11
  completion tokens for an 11-token answer, so the count holds no hidden
  reasoning.
- **Five second calls** (two writer, three reviewer) against one on
  2026-11-08, each repeating a 15,000–25,000-token prompt.

Streaming asks for usage in the final chunk; the per-agent rows carry the
same fields as before and the smoke request's count was exact.

## Decision

By the rule written before the batch: all five complete, six usage rows with a
successful request in every run, no non-returned attempt at all, 5/5 TRL in
range. Streaming goes to production. The per-chunk bound stays at 60 seconds;
the planning windows stay at 150 and 300.

## What this does and does not say

- Nothing about calibration: five single runs, all in range, as the day before.
- Nothing about the stall's cause upstream. The rows show that plain requests
  stopped delivering and streamed ones did not, in two production runs and
  one batch; they do not show why.
- Nothing about frequency. A production run on the merged code is the next
  reading, and its rows will be the same shape as these.
- Free allowance on `deepseek-v4-pro-0813` after this batch: about 156,000 of
  the 764,250 it showed before it.
