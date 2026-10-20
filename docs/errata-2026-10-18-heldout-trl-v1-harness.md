# Erratum — held-out TRL v1: first batch stopped on a runner defect

**Protocol:** [prereg-2026-10-18-heldout-trl-v1.md](prereg-2026-10-18-heldout-trl-v1.md)
(unchanged). **Batch:** `heldout-trl-v1`, closed and kept as recorded.

## What happened

The registered command was run on 2026-10-18 at `60f6b43`, with Qwen and
`qwen3.5-plus` recorded in the batch identity. The registered stop-rule
monitor halted it after three consecutive failures:

| Unit | Status | Elapsed | Recorded Crew-node usage |
|---|---|---|---|
| H01 rep 1 | `error_crew` | 111 s | none |
| H02 rep 1 | `error_crew` | 90 s | none |
| H03 rep 1 | `error_crew` | 120 s | none |
| H04 rep 1 | killed during retrieval (`running`) | — | none |

All three failures raised the same error at kickoff, before any agent ran:
`Missing required template variable 'decision_context_json'`.

## Cause

`benchmark.py` called `crew.kickoff(inputs=source_collection.crew_inputs())`.
When Decision Context added `{decision_context_json}`, `{assessment_mode}`
and `{decision_mode_guidance}` to the Writer and Reviewer templates,
`pipeline_worker` began merging those inputs and `benchmark.py` did not.
Every live run of `benchmark.py` has failed at kickoff since then. No test
runs a real crew, so nothing caught it. The advertised 30-run baseline
predates the change.

`ablation.py` builds its kickoff inputs the same way and has the same defect.
It is a frozen experiment runner with an open contributor PR, so it is not
changed here.

## What was and was not observed

- **No TRL, score or report was produced**, and none was looked at. The
  primary measure has no observations from this batch.
- Retrieval ran for H01–H03 and partly for H04, and wrote
  `validated_sources.json`. Those sources were not inspected. The next batch
  retrieves live again and does not reuse them.
- No Crew-node cost was recorded. Web searches and any helper calls made
  during retrieval are not counted by this runner.

## Held-out status

The protocol says the topics become consumed once a batch starts, and that a
later method change cannot be validated on them. That rule exists so no one
tunes the system after seeing its outcomes. This batch produced no outcome,
and the fix changes the runner, not the system under test: prompts, rubric,
retrieval and scoring are untouched. The topics are therefore treated as
still held out. This reading is stated here rather than assumed, and a
reader who disagrees can discount the next batch accordingly.

## Correction and next batch

- `benchmark.py` now builds kickoff inputs as production does for a run with
  no decision context (`_crew_inputs`). A test compares them with every
  template placeholder and with the production assembly, so a future
  template variable the runner lacks fails offline.
- As the protocol requires for a defect found mid-batch, the measurement is
  repeated in a **new batch, `heldout-trl-v1-b`**. It uses the same cohort,
  ranges, thresholds, configuration, preflight and stop rules, at the `main`
  commit containing this fix.
- Batch `heldout-trl-v1` is not resumed, retried or overwritten.
