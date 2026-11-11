# Result — held-out spot check on deepseek-v4.1-flash-1017

Run **2026-11-11** under the
[pre-registered protocol](prereg-2026-11-11-heldout-spot-check-deepseek-v4.1-flash.md),
after it and its one amendment (the batch name) were committed and before
any of these five runs. Five v2 topics, one live run each, serial,
`deepseek-v4.1-flash-1017` through the `qwen` transport, from the
maintainer's machine, code as `main` at `47a3840`. Batch
`heldout-spot-2026-11-11-deepseek-v4-1-flash-1017`; raw outputs private.
Nothing re-scored.

## Headline

- **Completion 5/5.** No unit failed.
- **TRL in range 4/5.** One below floor: V07 hyperloop at 3.0 against 4–6.
  None above ceiling. Two of the four sit on a boundary (V03 and V06 on
  their floors).
- **The decision rule stated in advance does not fire.** No unit failed on
  the model's output and one, not two, landed outside its range. By the rule
  the result recommends that the deployment keep serving this model, and the
  other five topics are the next reading.
- **28 of 61 provider attempts did not return**, from a machine that had 0
  of 35 two days earlier. Two calls returned only on their fifth attempt and
  one on its fourth; under the three-attempt cap that was in force until
  2026-11-09, three of the five runs would have failed. This is the reading
  the rule did not anticipate, and it is not about the model: see below.
- **523,069 crew tokens**, 91,661–117,845 a run, mean 104,614. Serial wall
  time **57.7 minutes**, 46% of it inside attempts that did not return.

## Per unit

| Case | Topic | Expected | TRL | Score | Sources A/P/M | Tokens | Time | Attempts (not returned) | Second calls |
|---|---|---|---|---|---|---|---|---|---|
| V01 | robotic-assisted surgery | 8–9 | 9.0 | 73.8 | 8/8/7 | 91,661 | 643 s | 14 (8) | none |
| V03 | enhanced geothermal systems | 7–8 | 7.0 | 63.8 | 6/8/7 | 107,745 | 833 s | 14 (7) | scorer |
| V06 | space-based solar power | 3–5 | 3.0 | 43.2 | 8/8/7 | 117,845 | 712 s | 10 (3) | writer |
| V07 | hyperloop | 4–6 | **3.0** | 41.7 | 8/5/6 | 100,514 | 667 s | 12 (5) | scorer |
| V09 | 特高压直流输电 (Chinese) | 8–9 | 9.0 | 75.5 | 7/8/8 | 105,304 | 608 s | 11 (5) | none |

V07's plan kept the word "hyperloop" in its queries. The runner counted 2
rate-limit hits per run, as in every batch since 2026-11-08. The grounding
check found no ungrounded figure in any report (1, 1, 0, 0 and 1 checkable).

## Beside the two earlier single runs on the same topics

Context, not a paired comparison: the model, the date of the live evidence
and the anonymous OpenAlex pool all differ.

| Case | Expected | 2026-11-08 `deepseek-v4-pro` | 2026-11-09 `deepseek-v4-pro-0813` | 2026-11-11 `deepseek-v4.1-flash-1017` |
|---|---|---|---|---|
| V01 | 8–9 | 8.0 | 8.0 | 9.0 |
| V03 | 7–8 | 7.3 | 7.3 | 7.0 |
| V06 | 3–5 | 5.0 | 5.0 | 3.0 |
| V07 | 4–6 | 5.0 | 5.0 | **3.0** |
| V09 | 8–9 | 9.0 | 9.0 | 9.0 |

On the two low-maturity topics this model read two levels lower than both
earlier runs, on its floor for one and below it for the other; on the
highest it read one higher. Three single runs a topic do not say whether
that is the model or the day's evidence. It is the pattern to look for in
the other five topics.

V07's scorer gave its reason in the report: the academic registry states
that hyperloop "has not reached a higher technology-readiness level", with
component-level validation for levitation coils only and the rest modelling
or concept work. That is a defensible reading of that evidence at 3; the
range frozen on 2026-10-19 is 4–6.

## Tokens and time

| Batch | Model | Requests | Tokens | Serial wall time |
|---|---|---|---|---|
| 2026-11-08 | `deepseek-v4-pro` | plain | 423,040 | 53.7 min |
| 2026-11-09 | `deepseek-v4-pro-0813` | streamed | 607,840 | 31.4 min |
| 2026-11-11 | `deepseek-v4.1-flash-1017` | streamed | 523,069 | 57.7 min |

The stop rule did not bind: 417,765 tokens were recorded when the last unit
began, against 600,000. Wall time is the slowest of the three although
every call streams: 1,579 of the 3,463 seconds were spent in attempts that
did not return, and the backoff between them is on top of that.

## The attempt rows

| Node | Attempts | Did not return |
|---|---|---|
| Three evidence agents | 18 | 3 |
| Writer | 13 | 7 |
| Reviewer | 13 | 8 |
| Scorer | 17 | 10 |
| **All** | **61** | **28** |

Eighteen were connection errors, eight a request or stream silent for 60
seconds, two a read timeout after a stream had run for one to two minutes. The three nodes
that send the long prompt (about 25,000 tokens) lost 25 of 43 attempts; the
evidence agents, with prompts a fifth of that size, lost 3 of 18. That is
the shape the host's link probe showed on 2026-11-09 and 2026-11-10: the
larger the request, the more often it does not get through.

Deepest retries: V03's scorer and V09's reviewer returned on the fifth
attempt, V01's writer on the fourth. Five attempts on a streamed node is the
cap since #364; one more failure on either of the first two would have
failed the run. Under the earlier cap of three, V01, V03 and V09 would have
failed.

## Second calls

Three guardrail second calls, all absorbed:

- Scorer, V03 and V07: the score object lacked the required
  `evidence_rationale` field; the second object had it.
- Writer, V06: the draft cited a source id, `M9`, that the registry does not
  contain; the second draft did not.

Both kinds have appeared on the two earlier models. Two of three on the
scorer's schema is worth watching over the other five topics; it is not a
contract the model could not meet.

## Decision, by the rule written before the batch

Keep serving `deepseek-v4.1-flash-1017`: no unit failed for a reason in the
model's output, and one of five, not two, landed outside its range. The
other five topics (V02, V04, V05, V08, V10) are the next reading, under
their own protocol, and the direction to watch is stated above: low on the
low-maturity topics. This is a recommendation in a result, not an adoption,
and the model variable is the operator's.

## After the batch, not registered

The attempt rows asked a question the protocol had not: this machine sent 35
attempts on 2026-11-09 and every one returned. Model, or day? Two checks
were made after the batch was read. They were not registered, they decide
nothing above, and they are reported because they change what the attempt
rows mean.

**The same small request on two models, alternating, no retry.** A long
streamed answer (about 2,500 completion tokens) from a short prompt, five
times each on `deepseek-v4.1-flash-1017` and `deepseek-v4-pro-0813`: four
returned and one failed with a connection error before its first chunk, on
each model. Ten requests cannot measure a rate; they do not show a
difference between the models, and one in five is what the evidence agents'
small requests lost in the batch. About 21,000 tokens.

**The link probe from this machine**, three times between 03:24 and 03:28
UTC, minutes after the batch. It posts requests with no key, so nothing is
billed:

| Endpoint | 1 KB | 10 KB | 30 KB | 100 KB |
|---|---|---|---|---|
| `dashscope.aliyuncs.com` | 3 of 3 answered | 2 of 3 (one in 21 s) | 1 of 3 | 1 of 6 |
| `dashscope-intl.aliyuncs.com` | 3 of 3 | 3 of 3 | 3 of 3 | 6 of 6, all under 0.8 s |

On 2026-11-09 the same probe from this machine carried 100 KB to the
mainland host in about four seconds, twice out of twice.

What these two say together: the attempts that did not return in this batch
were the path to the mainland endpoint on this day, not this model. And the
stall the deployment's host showed on 2026-11-09 and 2026-11-10 is not a
property of that host's route alone: a second network, on another day,
shows the same size-dependent failure into the same endpoint while the
international endpoint answers every size from both.

## What this does and does not say

- Nothing about calibration: five single runs.
- The TRL readings stand apart from the transport: every delivered score
  came from a call that returned in full, and a retried call is a fresh
  request.
- Nothing about how often the mainland endpoint is in this state. Three
  days of readings from two networks show it clean (2026-11-09 from this
  machine), partly failing (the host, both days) and mostly failing for
  large requests (this machine, 2026-11-11).
- The completion figure depends on the five-attempt cap. It would have been
  2/5 under the cap of three that was in force until 2026-11-09.
- The free allowance used: 523,069 tokens by the batch, 13 by the first
  check, about 21,000 by the control (half of it on `deepseek-v4-pro-0813`).
