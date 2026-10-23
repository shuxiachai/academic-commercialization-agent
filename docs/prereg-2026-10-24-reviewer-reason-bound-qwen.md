# Pre-registration — stating the reviewer's reason bound, six-node rerun on qwen3.8-flash

Written on 2026-10-24, before any paid call of this study.

## Question

Does stating the 300-character `reason` bound in the reviewer prompt reduce
the reviewer's correction-plan failures on `qwen3.8-flash`?

## Why

In the [2026-10-23 topology ablation](results-2026-10-24-agent-topology-ablation-qwen.md),
the six-node arm completed 23 of 30 runs. All seven failures were the reviewer
guardrail giving up after its single retry. The schema in `evidence.py`
limits each correction's `reason` to 300 characters. The reviewer prompt
states the 20-correction limit and the 2,000-character `find`/`replace` limit,
but never this one. The model is told the limit only in the retry's error
message, after it has already broken it.

The [Reviewer v2 closeout](results-2026-10-01-reviewer-comparison-v2.md) met
the same bound on another model.

## Intervention

One change to `config/tasks.yaml`, `report_review_task`:
- The description now says: keep each `reason` to at most 300 characters, one
  sentence naming what changed and why; a single longer reason makes the whole
  plan invalid.
- The output template's `reason` placeholder now ends "at most 300
  characters".

Nothing else changes:
- the schema, `evidence.py` and the guardrail and its single retry;
- every other prompt;
- the model, the fixtures and the runner.

`tests/test_reviewer_prompt_bounds.py` reads every plan bound from the schema.
It checks that the prompt states each one with the same number, both in the
YAML and in the review task that the production crew builds. Re-injecting
the old prompt failed two of its three tests; stating 250 against the
schema's 300 failed the same two.

## Baseline

The six-node arm of experiment `outputs/ablation/20261023T111632Z-737ef33c`:
- 30 cells on the same ten fixtures, three repetitions each;
- the same model and endpoint;
- commit `737ef33`, which differs from this study's runtime code only in the
  two prompt lines above.

`scripts/reviewer_contract_audit.py` reads it as:

| Measure | Baseline |
|---|---|
| Runs | 30 |
| First reviewer attempt failed | 27 of 30 |
| — `reason` over 300 characters | 21 |
| — more than 20 corrections | 5 |
| — a `find` that is not unique | 1 |
| Both attempts failed (terminal) | 7 of 30: 5 `reason` over 300, 2 `find` not unique |
| Completed runs | 23 of 30 |
| Accepted corrections per plan, median / max | 9 / 20 |
| Accepted `reason` length, median / p90 / max | 147 / 206 / 292 characters |
| Median tokens / cost / elapsed per run | 83,929 / $0.013457 / 197.798 s |

## Design

- **Arm.** Only `full`, the production six-node crew, with the same 30
  topic/repetition blocks as the baseline, run serially in order. The runs
  use the runner's targeted `--only` scope; the commands are below. Their
  plan-only listings show exactly one cell for the pilot and 30 for the
  rerun.
- **Code.** The runtime code is `main` plus this intervention. The study runs
  at this branch's pushed commit and is merged only after the result. This
  document and the code are pushed before any paid call.
- **Model and runner settings.** The model configuration and runner settings
  equal the baseline's:
  - `LLM_PROVIDER=qwen`, `QWEN_MODEL=qwen3.8-flash`, Beijing endpoint;
  - `MAX_RPM` unset, so 6;
  - no execution deadline;
  - orientation inputs, with no decision context.

## Outcomes

| | Outcome | Baseline |
|---|---|---|
| **Primary** | First reviewer attempts that fail on a `reason` over 300 characters | 21 of 30 |
| Secondary | Terminal reviewer failures and their causes | 7 of 30 |
| Secondary | First-attempt failures by every other cause | 6 of 30 |
| Secondary | Completed runs | 23 of 30 |
| Secondary | Accepted corrections per plan, and runs with at least one | median 9; 23 of 23 |
| Secondary | Accepted `reason` lengths | median 147 characters |
| Secondary | Median tokens, cost and elapsed time | see the baseline table |

`scripts/reviewer_contract_audit.py` and `scripts/ablation_outcomes.py` report
the outcomes from persisted metadata only. Blocks are also compared in pairs:
the same topic and repetition, before and after.

The report-contract and numeric-grounding screens are recorded but are not
outcomes here, because both drifted (see the baseline's result).

## Predictions

| # | Prediction |
|---|---|
| RB1 | At most 5 of 30 first reviewer attempts fail on a `reason` over 300 characters |
| RB2 | At most 3 of 30 runs end in a terminal reviewer failure |
| RB3 | First-attempt failures from other causes stay at or below 9 of 30. The change must not just move failures elsewhere |
| RB4 | The reviewer stays active: at least 18 successful runs accept a correction, and the median accepted corrections per plan is at least 5 |

## Decision rules

- **Adopt** the prompt change, by merging it, if RB1 holds and neither RB3 nor
  RB4 is violated.
- **RB2** decides only whether the result may claim fewer terminal failures.
  Two of the seven baseline terminal failures had another cause, so it does
  not block adoption.
- **If RB1 fails,** stating the bound does not change compliance on this
  model. The change is not adopted, and any code-side handling, such as
  clipping reasons, needs a protocol of its own.
- **Out of scope:** more-than-20-correction failures and non-unique `find`
  failures. They are reported, not addressed.
- No threshold changes after the results are seen.

## Stages, stop rules and budget

**Stage 0, offline.** These cost nothing:
- the new tests and their re-injection;
- the full suite, Ruff and the narrow pylint;
- the plan listings.

**Stage 1, pilot.** One six-node cell on case 03:

```bash
uv run python ablation.py --only 03 --variants full --repeat 1 --execute --stop-after-usd 0.10
```

Stop before Stage 2 if the cell breaks any of the August study's five stop
rules:
- live retrieval;
- a lost final report;
- complete cost for an unpriced agent;
- `0 checked` as a pass;
- missing digest, usage or guardrail records.

A reviewer failure in the pilot is not a stop rule.

**Stage 2, rerun.** 30 cells:

```bash
uv run python ablation.py --only 01 --only 02 --only 03 --only 04 --only 05 \
  --only 06 --only 07 --only 08 --only 09 --only 10 \
  --variants full --repeat 3 --execute --stop-after-usd 1.00
```

**Budget.** At most $1.00 recorded for Stage 2. The baseline arm recorded
$0.384383 for the same 30 cells.

**Failures and interruptions.** Failed cells are retained, whatever their
cause, and never rerun. An interruption resumes under the same experiment ID.
No earlier experiment directory is written.

## Amendment before any call

The first pushed version of this document (`8fcbdf6`) registered two
commands:
- `--pilot --variants full` for the pilot;
- `--full --variants full --confirm-full-study` for the rerun.

The runner refuses both for a paid run. Its `--pilot` and `--full` guards
encode the August protocol, which runs all three arms. The pilot attempt
exited during argument parsing: no request was sent and no experiment
directory was created.

The commands above express the same cells with `--only`. Their plan-only
listings match the earlier ones: 1 and 30 cells, in the same order. No
outcome, threshold, budget or other part of the design changed.

## Limits

- **Variance.** The model and fixtures are the same, but the day is not. The
  provider's sampling and load vary between runs, and 30 cells cannot
  separate a modest effect from that variance. Large effects are what the
  thresholds look for.
- **Model.** The study measures `qwen3.8-flash` only. Once merged, the change
  reaches every model production uses, including `qwen3.7-max-preview`, on
  which it is unmeasured.
- **Scope.** Fewer failures do not show that the reviewer's corrections are
  right; no edit is judged here.
