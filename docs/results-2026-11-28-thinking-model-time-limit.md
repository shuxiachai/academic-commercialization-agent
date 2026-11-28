# A longer run limit for a model that cannot turn thinking off

**Date:** 2026-11-28 (UTC).
**Status:** a read-only measurement of production run records, then a change
chosen by the maintainer from the options it compared. No search or model
request was made for the measurement. Run records were read signed out
through `GET /api/runs/{run_id}/progress`, using the maintainer's own run IDs;
the admin console was not used.
**Production:** the change that carries this file gives a run 40 minutes
instead of 30 when its model is known to run only in thinking mode. The
reviewer reserve, the per-call windows, the closeout reserve, the daily
allowance and the charging rules are unchanged.

## What was read

| Source | Runs | Note |
|---|---:|---|
| Production run records, read signed out | 23 | 2026-09-29 to 2026-11-27, all the maintainer's own; 31 other IDs returned 404 (past retention, or test IDs) |
| The paid run of 2026-11-28 01:07 | 1 | its record was not read; its figures come from the notes of the session that watched it |
| Local `outputs/` | 1 API run, 41 command-line runs | command-line runs have no 30-minute limit and another network; reference only |
| Production runs not read | at least 3 | the estimate on 2026-11-28 said "from 19 runs"; the records read account for 16 |

Of the 24 runs, 21 were new runs and 3 were resumes. Ten were on
`qwen3.8-2.4t-a95b`, the production model, which refuses non-thinking mode
(7 new runs, 3 resumes). The other 14 new runs were on eight other models.

## Stage times of the production model

Completed stages only, in seconds:

| Stage | n | Median | Max | Values |
|---|---:|---:|---:|---|
| Sources | 6 | 51 | 77 | 27, 34, 48, 54, 57, 77 |
| Evidence | 6 | 226 | 335 | 162, 200, 217, 235, 309, 335 |
| Writer | 6 | 668 | 888 | 396, 493, 647, 689, 745, 888 |
| Review | 4 | 498 | 544 | 459, 459, 537, 544; one more ran past 853 and was killed at 30 minutes |
| Scoring | 5 | 218 | 305 | 189, 213, 218, 229, 305 (three of them from resumes) |

The medians add up to 1,661 seconds (27.7 minutes); the maxima to 35.8
minutes. Under the rules on `main` at `6982865`, scoring may start only with
at least 360 seconds left before the hard limit (its 300-second window plus the
60-second closeout reserve), so a typical run of this model no longer fits in
30 minutes. With six or fewer values a 90th percentile is the maximum and is
not reported.

The other models each have one or two values per stage, too few for a
distribution. None of their 13 new runs since stage times were recorded came
near the limit: scoring started with at least 916 seconds left. One earlier run
on `glm-5.3` (2026-11-08) ended in `run_time_limit` in its writer, after 1,226
seconds there, before attempts were recorded one by one and before calls
streamed; its cause cannot be read and it is left out of what follows.

## What happened to the six runs that reached the writer

| Date | Outcome | Where it stopped | Left before 30 minutes |
|---|---|---|---|
| 2026-11-18 | completed, reviewed and scored | — | — |
| 2026-11-18 | `run_time_limit` | scoring never started | 267.7 s (207.7 before the closeout reserve) |
| 2026-11-20 | recorded as `provider_unreachable` | scoring: three attempts of about 125 s each with no output, the fourth refused by its window | 341.8 s |
| 2026-11-25 | hard timeout | review: started with 846 s left, still streaming after 853 s | — |
| 2026-11-27 | `run_time_limit` | scoring never started | 260.8 s (200.8 before the closeout reserve) |
| 2026-11-28 | completed without its review | review skipped: about 510 s left, less than the reviewer reserve plus its window | — |

One run in six delivered a reviewed and scored report. The seventh new run
stopped at sources for a reason unrelated to time.

Three things in these records:

1. **The review's planning window and its real length disagree.** The review
   took 459 to 544 seconds in one call (four values), against a 300-second
   window. The budget decides only whether an attempt may start; a streamed
   attempt that has started is never cut at its stage deadline, only after 120
   seconds without a chunk. So when the review ends, the scorer's window has
   often gone. The three runs whose review started with 727, 798 and 846
   seconds left never scored; the two that started it with 1,052 and 1,180
   seconds left did.
2. **The two `run_time_limit` runs were stopped by the window, not the clock.**
   Their resumes, with the same model and inputs, scored in 207 and 214
   seconds. Allowed to start, the originals would have ended at 28.9 and 29.2
   minutes.
3. **Closeout takes under 2 seconds.** In the four scoring stages with
   per-attempt rows, the run ended within 2 seconds of the scorer's answer; in
   18 runs the terminal record was written at most 0.9 seconds after the last
   stage.

Writer retries cost 20, 283 and 297 seconds in three of the six runs; two
writers returned on their fourth attempt. A stalled attempt of this model
waits about 125 seconds for a chunk before it is given up.

## The options compared

Each of the six runs was replayed under the rules on `main`, with its own stage
times; a refused scoring stage took the time its resume took. As an order of
magnitude only, every combination of observed stage times was also replayed
(6 × 6 × 6 × 5 × 5 = 5,400; stages assumed independent, the review past 853
seconds counted as 853, so the figures lean optimistic).

| Option | Runs saved of six | Runs made worse | Combinations delivering a reviewed, scored report |
|---|---:|---:|---:|
| Today (30 minutes) | — | — | 37% |
| a. 35 minutes for a thinking-only model | 2 | 1: the 2026-11-28 run would start its review and then have scoring refused | 84% |
| a. 37 minutes | 3, perhaps 4 | 0 | 92% |
| a. 40 minutes | 3, perhaps 4 | 0 | 98.6% |
| b. let scoring start inside its window | 2, ending 47 and 60 seconds before the kill | 0 replayed, but a 305-second scoring would become a hard timeout | 60% |
| c. reserve the doubled window for review and cut a late review | 3, all without their review | 0 | 37% (the rest finish unreviewed) |
| d. cap writer retries, or hold time back for review | 0 | 2 to 3 writers fail | — |

The 2026-11-25 run is saved under a only if its review would have returned
soon after 853 seconds, which is unknown. The 2026-11-20 run, whose scorer
stalled three times running, cannot be replayed.

The four complete reviews alone are covered by 37 minutes (the slowest
combination ends at 36.0). Counting the review past 853 seconds as 853, 37
minutes covers 61% of the combinations that include it, 40 minutes 93%, 45
minutes 100%. The 1.4% of all combinations refused at 40 minutes all include
that review.

## What changed

A run of a model known to run only in thinking mode is launched with 2,400
seconds instead of 1,800 (`api/runs.py`, `THINKING_TIMEOUT_SECONDS`). The
reviewer and closeout reserves, the windows and the per-chunk bound are the
same rules measured from the later deadline. The run page reads the limit from
the run's own budget, so it says 40 minutes for such a run with no page
change.

The limit is fixed when the API launches the worker, and the worker learns
that thinking cannot be turned off only from the provider's refusal of its
first call. So the API decides from two things it can read at launch, with no
list of models:

- what its own process has learned: a topic preview calls the same model
  through the same parameter adaptation, so a model that refused
  `enable_thinking=false` there is known before the run starts;
- the run records: a worker whose model refused non-thinking mode marks its
  `status.json` with `thinking_required: true`, and the API reads the newest
  100 records for a mark on the same model. A failed run carries the mark too.

The first run of a new thinking-only model with no preview before it in the
process keeps 30 minutes; the runs after it get 40. A BYOK run is judged by the
model the visitor named, not the deployment's.

## What this does not settle

- Six runs reached the writer and four reviews completed. The percentages above
  are orders of magnitude, not success rates.
- The 2026-11-25 review is known only to have run past 853 seconds. If it
  would never have returned, 40 minutes only makes it time out later.
- Every figure for the 2026-11-28 run comes from notes; under a its review
  time was assumed to lie in the observed 459 to 544 seconds.
- The scoring times used for the two refused runs come from resumes 30 to 60
  minutes later, on a link that may have differed.
- At least three production runs were not read.
- A run that hangs now holds its concurrency slot up to 40 minutes, ten more
  than before. A cut for a streamed attempt that has run past its stage
  deadline would be the defence against that; it is not part of this change.
- The 60-second closeout reserve and the 150- and 300-second windows are far
  from what was measured (under 2 seconds; reviews of 459 to 544). They are
  unchanged; changing them needs the attempt rows read again, starting from
  the notes at the top of `src/academic_agent/runtime_budget.py`.
