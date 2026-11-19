# What a run says while it runs, after it stops, and after a resume

**Date:** 2026-11-19 (UTC).
**Status:** a reading of the code on `main` at `57d82e9` behind seven
observations made on production on 2026-11-18, and a count of what run records
exist on the maintainer's machine. No search or model request was made, and no
production record was read for this document: the production figures below are
the ones the maintainer reported from the run pages on 2026-11-18.
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
behind every figure so that a reader can weigh it.

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
