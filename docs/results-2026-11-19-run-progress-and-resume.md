# What a run says while it runs, after it stops, and after a resume

**Date:** 2026-11-19 (UTC).
**Status:** a reading of the code on `main` at `57d82e9` behind seven
observations made on production on 2026-11-18, and a count of what run records
exist on the maintainer's machine. No search or model request was made, and no
production record was read for the change itself: the production figures in
the first sections are the ones the maintainer reported from the run pages on
2026-11-18. The deployment's run records were read afterwards, on 2026-11-19,
and are in the last section.
**Production:** the changes named under "What changed" are in the change that
carries this file. How a failure is classified, what a run is charged, and
when a resume is admitted are unchanged.

## The observations

Three runs on production, on one account, on 2026-11-18:

| Run | Outcome | Time | Tokens |
|---|---|---|---|
| English, decision-support | completed | 24 min 40 s | not noted |
| Chinese | failed, `error_code` `unknown`, after the reviewer | 25 min 31 s | 141,193 |
| resume of the Chinese run | completed | 3 min 48 s | about 35,000 |

1. The first run's page said "about 7 min" at its start. The landing said a
   run takes "6 to 15 minutes".
2. A second topic, started while the first ran, went through its plan preview
   and was refused only when Start was pressed.
3. The failed run's page said "this run produced no report", and to "contact
   the operator with the run ID", showing neither the ID nor a contact.
4. The resume's stage stayed "Phase 1 — Evidence Collection" until it was
   done; its header ended in "6 checkpoint stages reused"; its estimate was
   "about 9 min"; its page gave 3:48 and about 35,000 tokens; and the history
   listed the two runs as two rows with one name.

## What the code did

Each of these was confirmed by reading `main` at `57d82e9`.

**The estimate** (`api/eta.py`). One figure: the median of each stage over
the newest thirty completed runs, whatever model each ran on, minus the time
already spent in the current stage. Three things follow. A deployment that
changes model keeps answering from the faster model's runs until thirty runs
of the new one exist. A resumed run counted as a completed run: its total was
its own few minutes and, because of the next point, those minutes were filed
under the evidence stage. And one median says nothing about spread, on a
deployment whose link to its model provider stalls for minutes at a time
(`api/link_probe.py`).

**The stage of a resume** (`pipeline_worker.py`). The public stage is moved by
a callback CrewAI fires when a task completes. Tasks restored from
checkpoints complete without it, and after restoring them the worker wrote
the evidence-phase label once more. A resume with only scoring left therefore
read "Phase 1" from its first second to its last; `stage_timings` filed the
scorer's time under that stage; and the estimate, asked at "Phase 1", was for
evidence, writing, review and scoring: hence "about 9 min".

**The draft** (`pipeline_worker.py`, `api/runs.py`). The report file is
written once, after the crew has returned, so a run that fails in scoring has
none. The writer's answer is on disk in that case, as
`checkpoints/writer/output-<sha256>.md` with its manifest: it is what the
resume reused. No read served it.

**The run ID and the contact.** The sentence for an unrecognised failure names
both; the page had the ID only in its address and the contact only on the
privacy page and the sign-up form.

**The refusal.** The one-at-a-time rule is applied where a paid operation is
admitted (`runs._admit_paid_operation_locked`). `POST /api/plan` does not go
through it, and no read told the page that the account had a run going.

**The totals.** A resumed run's record covers what it ran. Its parent is
named in `recovery.source_run_id`, which both run reads already carry.

## What run records exist locally

`outputs/` on the maintainer's machine holds 332 entries. One has an API
run id (from August 2026); none has a `terminal.json`, and none of the 68
`status.json` files carries `stage_timings`. So the stage-by-stage history
the estimate is drawn from **cannot be measured locally**; it exists only on
the deployment.

What is local is whole-run time for runs made from the command line on the
maintainer's machine, by batch. These are not the production host's network
path and are not used by the estimate; they show how much the model alone
moves the time of a run:

| Batch (`outputs/benchmark-runs/`) | Model | Runs | Seconds, fastest to slowest |
|---|---|---|---|
| `heldout-spot-2026-11-08-deepseek-v4-pro` | deepseek-v4-pro | 5 | 327, 369, 430, 972, 1061 |
| `heldout-spot-2026-11-08-deepseek-v4-pro-b` | deepseek-v4-pro | 5 | 388, 438, 446, 473, 478 |
| `stream-2026-11-09-deepseek-v4-pro-0813` | deepseek-v4-pro-0813 | 5 | 232, 262, 398, 423, 509 |
| `heldout-spot-2026-11-11-deepseek-v4-1-flash-1017` | deepseek-v4.1-flash-1017 | 5 | 608, 643, 667, 712, 833 |
| the two Anthropic runs of 2026-11-12 | claude-sonnet-5-5 | 2 | 209, 211 |
| the two DeepSeek-direct runs of 2026-11-12 | deepseek-chat | 2 | 120, 146 |

Twenty-four runs, from 2 minutes to 17 minutes 41 seconds. Within one model
the slowest run of five took between 1.2 and 3.2 times the fastest; between
models the medians differ by a factor of five. The production run of
2026-11-18, on a model none of these batches used, took 24 min 40 s. Two
conclusions are drawn from this and no more: an estimate has to be asked of
runs on the same model, and it has to be a range.

**Not measured.** How wide the range is on production for the model in use
there, and how often a run falls outside it. That needs the deployment's own
run records, which this change did not read. The page shows the count of runs
behind every figure so that a reader can weigh it. (Those records were read
on 2026-11-19 after the change shipped: see the last section.)

## What changed

- **The estimate is a range from the same model's runs.** For each of the
  newest ten completed runs on the run's own model: what that run took from
  the current point to its end. The range is the fastest and slowest of
  those, asked only of runs that had not left the current stage by now. With
  fewer than three runs on the model, the newest ten of any model stand in
  and the page says so. A resumed run is not a sample, and is given no
  estimate until its real stage is known. The worker records its model at
  its start (`llm_model`), since the usage record names it only after the
  first agent answers.
- **The pages state no time of their own.** The landing and the sign-in card
  show the fastest and slowest whole run of the deployment's newest ten, with
  the count, from `/health`; nothing with fewer than three.
- **A resume records the stage of the first task that really runs**, and a
  reused stage has no clock in the resume. This is a change to what the
  worker writes into `status.json`, not to what is resumed.
- **A stopped run with a writer's checkpoint shows it as a draft**, named
  "not reviewed or scored" on its tab and above its text, through the
  existing artifact route under the existing read rule. A checkpoint that
  does not match its manifest is not shown.
- **A failure only the operator can look into shows the run ID, a copy
  button and `OPERATOR_CONTACT`**; where none is set, it says so.
- **A resumed run says what it reused and what both runs took**, under its
  header. The sum of tokens is "at least" unless every run's count is
  complete, which a failed run's is not: an interrupted request is not free.
  For the pair above the page reads 29:19 and at least 176,205 tokens.
- **The history folds the run a resume continues under it.**
- **An account with a run going is told so above the workbench**, and the
  run button, the plan's Start and the upload are off with the reason beside
  them, from the same count the admission makes. This is the first of two
  designs put to the maintainer, who chose it on 2026-11-19; the second, a
  server-side queue that starts the next run when the first ends, was not
  built: it changes when a run is admitted and charged.

## Limits

- The draft is the writer's text. Where the reviewer had also answered, its
  corrections are not shown: the steps that turn a reviewer's answer into
  the report did not run, and the label would no longer be true of it.
- The totals are read from the earlier run's own record. If that run is
  deleted, the resume says so and gives its own figures as a floor.
- The estimate's range is the fastest and slowest of at most ten runs. A run
  can still fall outside it, and the page then says it is slower than all of
  them instead of counting down.
- Seen in a real browser on synthetic runs only (the browser smoke and a
  local preview); not yet seen on production.

## Seen on production after the deploy, and three follow-ups

With the maintainer's consent the failed run and its resume were opened by
their links on 2026-11-19, signed out, with GET requests only. The resume
read "In all: 29:19 (3:48 here + 25:31 before) · at least 176.5k tokens
(35.3k here + at least 141.2k before)", and its link opened the failed run;
the failed run opened on its draft, under the notice, with its run ID and the
operator's contact; at a phone's width it opened at the top. Not seen: the
history fold and the line about a run in progress, which need an account.

Three things seen there were changed afterwards:

- The resume's timing fold still read "Evidence 3:33": its record predates
  the stage fix and is not rewritten. A stage the run took whole from the
  earlier run ran nothing in it, so the page now shows such seconds under
  the first step the run's own record says it ran ("Scoring 3:33").
- The failed run did not say it had been resumed. It now does, with the way
  to the run that continued it, for whoever may modify it; a reader holding
  only its link is not handed another run by that.
- The draft's notice told every reader that resuming reuses the text. A
  reader of someone else's run cannot resume it and is no longer told to.

## The deployment's own run records (read 2026-11-19)

Read after both changes had shipped, with the maintainer's consent, signed in
as the administrator, with GET requests only: the run list and each run's
status (state, model, time, stage times, whether it was a resume). No topic
and no report text was taken. The deployment keeps runs for 90 days and held
17: 12 completed (one of them the resume), 4 failed, 1 cancelled.

The eleven completed runs that ran every stage themselves, newest first,
in seconds:

| Started (UTC) | Model | Whole run | Sources | Evidence | Report | Review | Scoring |
|---|---|---|---|---|---|---|---|
| 2026-11-18 | qwen3.8-2.4t-a95b | 1,480 | 27 | 217 | 493 | 544 | 189 |
| 2026-11-09 | deepseek-v4.1-flash-1017 | 343 | 54 | 46 | 127 | 89 | 15 |
| 2026-11-09 | deepseek-v4-pro-0813 | 1,072 | 52 | 46 | 715 | 59 | 189 |
| 2026-11-08 | deepseek-v4-pro-0813 | 781 | 39 | 362 | 282 | 50 | 40 |
| 2026-10-25 | qwen3.7-max-2026-06-08 | 389 | 42 | 44 | 84 | 38 | 168 |
| 2026-10-23 | qwen3.7-max-preview | 641 | 84 | 241 | 223 | 48 | 33 |
| 2026-10-21 | qwen3.8-27b | 988 | stage times not recorded then |||||
| 2026-10-21 | qwen3.8-27b | 333 | |||||
| 2026-10-21 | qwen3.8-27b | 423 | |||||
| 2026-10-21 | qwen3.8-27b | 275 | |||||
| 2026-09-29 | qwen3.5-plus | 250 | |||||

Not among them: the resume (228 s), four failures (after 125, 190, 1,523 and
1,531 s) and a cancellation (at 728 s).

What they show:

- **The two figures the page gave are reproduced exactly.** The old estimate
  was the median of each stage over the completed runs with stage times.
  Before the run of 2026-11-18 those were the five runs under it in the
  table: 52 + 46 + 223 + 50 + 40 = 411 s, shown as "about 7 min". The run took
  1,480. With that run added, a run whose stage read "Phase 1" was told the
  evidence median and everything after it, 131 + 252 + 54 + 104 = 541 s:
  "about 9 min" from its first seconds. That was the resume, which ran
  scoring only and took 228 s.
- **No model has three completed runs with stage times.** Eleven runs carry
  eight model names; the one model with four runs ran them before stage
  times were recorded. So on production every estimate today is drawn from
  other models' runs, and says so. The same-model range, the main change,
  has not yet been in effect there.
- **The new method would not have covered that run either, and says why.** On
  the history as it stood before 2026-11-18, the range at a run's start is
  what the five runs took, 331 to 1,061 s: "about 5–18 min left, going by
  runs on other models". The run took 24 min 40 s. A model new to the
  deployment and slower than every earlier one cannot be foreseen from the
  others' runs. What changes is that the page says whose runs the figure
  comes from, gives the spread instead of a middle, and, once a run outlasts
  them, says it is slower than all of them instead of counting down. Today,
  with that run in the pool: 331 to 1,470 s, "about 5–25 min left".
- **The spread is inside the stages, and it moves.** Across the six runs:
  sources 27 to 84 s, evidence 44 to 362, report 84 to 715, review 38 to 544,
  scoring 15 to 189. The two runs on one model, a day apart, took 781 and
  1,072 s, with evidence at 362 against 46 and the report at 282 against
  715: a different stage was the slow one each time. That fits a link that
  stalls on some requests (`api/link_probe.py`) more than a model being slow,
  and it means a same-model range will be wide too.
- **The pages' sentence.** The newest ten whole runs took 275 to 1,480 s,
  which `/health` gives as 4 to 25 minutes and the landing shows.

**Still not measured:** how often a run falls outside its range. Six runs with
stage times cannot say, and none of them was estimated by the new method.
