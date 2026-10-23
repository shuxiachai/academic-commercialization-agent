# Pre-registration — agent-topology ablation on current main with qwen3.8-flash

Written on 2026-10-23, before any paid call of this study. It repeats the
[August topology ablation](prereg-2026-08-21-agent-topology-ablation.md) on
today's code and a different model, with the same frozen evidence, arms,
outcomes, predictions and decision rules.

This is a new experiment, not an amendment. The August document, its results
and its output directory `outputs/ablation/20260821T234300Z-7dd894ef` are not
changed.

## Question

Does the August conclusion still hold on current `main` with Qwen
`qwen3.8-flash`? The question each arm answers is August's, unchanged:

> Holding the retrieved evidence, model settings, report contract, and blocking
> report validation fixed, what is gained by decomposing report generation into
> one, four, or six LLM nodes?

As in August, this tests workflow topology, not whether CrewAI is necessary.
It also does not test whether a technology-transfer officer would act on the
report.

## What changed since August

| | August Stage 2 | This study |
|---|---|---|
| Code | `7dd894ef` | `main` at `faccb61` plus this branch's kickoff fix. That is 669 commits later, 256 of them first-parent merges. |
| Provider and model | DeepSeek `deepseek-chat` | Qwen `qwen3.8-flash`, DashScope Beijing compatible-mode endpoint |
| Model settings | DeepSeek chat | Non-thinking: `enable_thinking=false` is accepted. JSON Object output for the five production JSON nodes |
| Price basis | Built-in `deepseek-chat` row, $0.27 input / $0.07 cached / $1.10 output per Mtok | Built-in `qwen3.8-flash` upper bound: Alibaba Beijing list price, $0.12 input / $0.12 cached / $0.38 output. Cached input is charged at the full rate |
| Evidence | Ten committed `benchmark_fixtures` | The same ten, with identical digests (listed below) |
| Runner | `ablation.py` at `7dd894ef` | Adds an opt-in execution deadline, off here as it was in August, and the reviewer-audit artifact. Plus the kickoff fix below |

### Why `qwen3.8-flash`

- **What the brief named.** It named `qwen3.8-27b`, production's model from
  2026-10-19.
- **What production ran.** On 2026-10-23 production `/health` reported
  `qwen3.7-max-preview`. That model runs only in thinking mode, and a
  production run took about ten minutes.
- **Why the operator chose flash.** Before any paid call, the operator chose
  `qwen3.8-flash` because its one-million-token free quota was unused. The
  study needs about 4.2 million tokens, judged from August's 3.06M input and
  1.05M output.
- **What this measures.** Topology on `qwen3.8-flash`. It is not a
  measurement of the production model on any date. A smaller model may change
  guardrail-retry behaviour; that is part of what is measured, not a defect.
- **Preflight.** On 2026-10-23, `scripts/check_llm_model.py` passed on this
  model. The search planner, translation, agent JSON mode and agent free text
  all passed, with no parameter adaptation.

### Code under the arms

- **Prompts.** The four- and six-node arms reuse production task objects, so
  they run today's production prompts. Since August, `config/agents.yaml` and
  `config/tasks.yaml` gained the Decision Context templates and the
  Writer/Reviewer comparison instructions, among other edits. The monolith keeps
  its frozen prompt inside `ablation.py`.
- **Validation and the outcome screens.** The report contract, the numeric
  grounding screen and the audit code have changed (`evidence.py`,
  `claim_grounding.py`, `report_audit.py`). Both the blocking guardrails and the
  offline outcome screen use this code. Outcome counts are therefore comparable
  across arms within this study, not one-to-one with August's numbers.
- **LLM transport.** `llm_config.py` now has transport retries, the per-call
  runtime budget, and, since 2026-10-23, the parameter fallback. The preflight
  showed that `qwen3.8-flash` triggers no fallback.

### The kickoff fix

`ablation.py` kicked off every arm with `collection.crew_inputs()` alone.
Decision Context later added `{decision_context_json}`, `{assessment_mode}` and
`{decision_mode_guidance}` to the Writer and Reviewer templates, so the four-
and six-node arms would have failed at kickoff. `benchmark.py` had the same
defect: see the [2026-10-18 erratum](errata-2026-10-18-heldout-trl-v1-harness.md).

The defect was confirmed offline before any paid call. Each arm's real crew was
built with a placeholder key and no request was sent. The crew's placeholders
were compared with the kickoff inputs:

| Arm | Nodes | Missing at kickoff |
|---|---:|---|
| `monolith` | 1 | none |
| `specialists_writer` | 4 | `assessment_mode`, `decision_context_json`, `decision_mode_guidance` |
| `full` | 6 | the same three |

With the operator's approval, the fix changes three lines of `ablation.py`:
- It imports `_crew_inputs` from `benchmark`.
- It passes `_crew_inputs(collection)` at both kickoff calls.

`_crew_inputs` is the function `benchmark.py` already uses. It returns the
inputs production builds for a run with no decision context, and a test pins
that equality. Every arm therefore runs as an orientation run, as it had to in
August, when no arm had a decision context to give.

The fix changes the runner, not the system under test. Prompts, scoring,
validation and the arms are untouched.

`tests/test_ablation_crew_inputs.py` takes the inputs at the kickoff call
itself, for each arm's real tasks and agents, on both kickoff paths. It also
checks that the production arms receive orientation inputs. Re-injecting the
defect turned the suite red:
- reverting both calls: 6 tests;
- reverting only the deadline-path call: 2 tests.

## Arms

Unchanged from August:

| arm | nodes | work performed |
|---|---:|---|
| `monolith` | 1 | One generalist reads the three immutable source registries and writes the report |
| `specialists_writer` | 4 | The existing academic, patent, and market tasks feed the existing report writer |
| `full` | 6 | The production workflow: three specialists, writer, reviewer, and scorer |

The four- and six-node arms reuse production task objects without edited
prompts. The monolith has a purpose-built prompt because telling it that three
specialist outputs exist when they do not would contaminate the treatment. Its
delivered report nevertheless passes the same normalisation and blocking
validation implementation as Tasks 4 and 5.

The scorer is intentionally absent from the one- and four-node arms. Therefore
TRL and overall score are not common outcomes and will not be used to rank the
topologies. Adding a scorer to every arm would turn this into a two/five/six
node experiment and answer a different question.

## Fixed inputs and controls

Unchanged from August:

- The ten committed `benchmark_fixtures` are the only evidence inputs. A
  missing or digest-mismatched fixture aborts; there is no fallback to live
  retrieval.
- Model/provider and each production role's LLM construction, output language,
  required headings, source registry, `MAX_RPM`, and final-report validation
  are held fixed. The monolith matches the production writer's free-text setup.
- Runs are serial. Within each topic/repetition block, arm order rotates by a
  deterministic Latin-square schedule. Across ten topics and three
  repetitions, every arm occupies every position ten times.
- Every result records the fixture digest and age, commit SHA, arm position,
  provider/model usage, request count, token count, cost basis/completeness,
  elapsed time, and guardrail calls/failures.
- The harness is plan-only by default. Paid calls require `--execute`; a pilot
  and the full study are separate decisions.

Specific to this study:

- **Fixture digests.** They equal August's recorded digests, checked on
  2026-10-23:

  | Case | Digest | Case | Digest |
  |---|---|---|---|
  | 01 | `6159a446a2f36859` | 06 | `4dcd24217fea4e80` |
  | 02 | `96935f19b7cfc29b` | 07 | `6732ba8c9d0f5d2f` |
  | 03 | `8643e7369b337b9b` | 08 | `2cb26be92fc7e04b` |
  | 04 | `231bc9bd2210f9ac` | 09 | `1082e67c2bedad41` |
  | 05 | `abb0d051a5071093` | 10 | `397e7080d907f4f8` |

- **Runner settings.** `MAX_RPM` is unset, so the runner's default of 6
  applies. The execution deadline stays off: `ABLATION_MAX_EXECUTION_TIME` is
  unset and no `--max-execution-time` is passed, as in August.
- **Model configuration.** `LLM_PROVIDER=qwen`, `QWEN_MODEL=qwen3.8-flash`, and
  `QWEN_API_BASE` set to the Beijing compatible-mode endpoint. No key is printed
  in any output.
- **Where it runs.** On the operator's local machine, against DashScope's
  Beijing endpoint.

## Outcomes

Unchanged from August.

### Primary quality and reliability outcomes, common to all arms

1. Completed-run rate.
2. Final-report contract errors, including missing headings, unknown or
   mismatched citations, and blocking citation-policy failures.
3. High-precision numeric grounding against the cited source summaries:
   checked claim lines, unsupported claim lines, and unverifiable claim lines.
4. First-attempt report-guardrail failures and total guardrail retries.

`0 unsupported / 0 checked` is recorded as `not_checked`, never as a pass.
Qualitative claim correctness is outside the deterministic screen's reach and
will not be described as verified.

### Secondary operational outcomes

- Prompt, completion, and total tokens.
- Provider requests.
- Estimated USD cost, always accompanied by price basis and whether every
  model was priced.
- Wall-clock latency and report word count.
- Unique citations and represented evidence domains.

### Six-node diagnostics, not common outcomes

- Accepted reviewer correction count and stated reasons.
- Draft-to-delivered-report text retention after removing deterministic
  reviewer notes.

A reviewer edit is activity, not proof of improvement. Correction counts are
descriptive until the edits are manually judged.

## Predictions

Unchanged from August:

| # | Prediction |
|---|---|
| P1 | The four-node arm has fewer first-attempt report-guardrail failures than the monolith |
| P2 | The six-node arm has no more unsupported checked numeric claims than the four-node arm |
| P3 | Removing two nodes reduces median cost and total tokens by at least 20% from six to four nodes |
| P4 | The monolith is cheapest, but loses at least one common quality or reliability outcome to the four-node arm |

## Decision and falsification rules

Unchanged from August:

The default decision is the simpler topology. Extra nodes are justified only
by a measured benefit on a common outcome.

- Any increase in high-confidence unsupported numeric claims is a material
  regression even when averages elsewhere improve.
- A cost or latency change below 20% is not treated as practically meaningful
  for this small study.
- If monolith matches both staged arms on all common quality/reliability
  outcomes while using at least 20% fewer tokens or dollars, the claim that
  specialist decomposition is necessary is falsified.
- If four nodes improve first-attempt validation or grounding over monolith
  without a material cost regression, domain decomposition is supported.
- If six nodes match four nodes on common outcomes while costing at least 20%
  more, the reviewer/scorer remain product features but do not establish that
  six nodes are necessary for report generation.
- Six nodes are not declared better merely because the reviewer produced
  corrections.

With only ten topics and three repetitions, the report will emphasize paired
effect sizes and uncertainty rather than binary statistical significance. No
metric or threshold will be changed after seeing the paid results.

## Execution stages and stop rules

### Stage 0 — offline verification

Stage 0 costs nothing:
- the model preflight above;
- the kickoff regression test and its re-injection;
- the full zero-network suite and Ruff;
- the plan-only listings. `uv run python ablation.py --pilot` must list
  exactly three cells, and `--full` exactly 90.
- a check that `qwen3.8-flash` is priced in the project's price table, so cost
  is never recorded as complete for an unpriced model.

This document is pushed before any paid call.

### Stage 1 — paid pilot

Fixture case 03 runs once through all three arms. The run needs separate
approval, and its soft ceiling is checked after each serial cell:

```bash
uv run python ablation.py --pilot --execute --stop-after-usd 0.50
uv run python ablation_check.py outputs/ablation/<experiment-id>
```

Summaries are rebuilt from persisted metadata, not read from terminal output.
Stop before the full study if any arm, unchanged from August:

- uses live retrieval;
- loses its final report at the persistence boundary;
- reports cost as complete when an agent is unpriced;
- records `0 checked` as a grounding pass; or
- cannot identify its fixture digest, model usage, or guardrail attempts.

The pilot report gives, per arm:
- cost, tokens and elapsed time;
- guardrail retries;
- whether any stop rule fired.

It also estimates the full study's total cost and duration as 30 times the
pilot.

### Stage 2 — full paid study

The full study needs a separate approval after the pilot review, with an
approved budget. It runs ten topics, three repetitions and three arms: ninety
serial cells.

```bash
uv run python ablation.py --full --execute --confirm-full-study \
  --stop-after-usd <approved-budget>
```

**Budget.** The soft ceilings are in recorded, list-price USD:
- the pilot, $0.50;
- the full study, at most $2.00 (August's ceiling), unless the pilot gives a
  reason to approve a different figure before Stage 2 starts.

At the `qwen3.8-flash` row, the full study is expected to record about $0.80.
The free quota is not reflected in recorded cost, so the actual charge is
lower.

**Account precondition.** The provider account must be able to bill past the
free quota. Its "stop when the free quota runs out" option must be off, or
cells after about one million tokens would be refused.

**Failures and interruptions.**
- A failed cell is retained as an outcome, whatever its cause, and is reported
  with its error. It is never rerun to fill the table.
- If the process is interrupted, the study resumes under the same experiment
  ID. Existing successful cells are reused only when the arm identity and
  fixture digest match. The interruption is recorded in the result.
- No file under `outputs/ablation/20260821T234300Z-7dd894ef` is overwritten.

## What a difference from August can and cannot mean

The model, the provider and 669 commits of code changed together. A result
that differs from August cannot be attributed to any single one of them. The
findings of this study are its within-study arm comparisons. Comparisons with
August are descriptive.

Absolute dollar figures are not comparable either: the price bases differ,
August's rows charged DeepSeek cache hits, and the free quota is not
reflected. The registered cost prediction, P3, is a ratio within this study.

## Reporting

The result will be written to `docs/results-2026-10-XX-agent-topology-ablation-qwen.md`
in the format of August's "Stage 2 full-study outcome". It will give:
- spend, duration and completion;
- the same outcome table;
- paired comparisons and a verdict on each of P1–P4;
- the reviewer diagnostics;
- a side-by-side comparison with August, and the limits.

The experiment directory will also hold `article_figures.json`, computed from
successful cells only. Per arm it gives:
- `cells`, `completed`;
- `uncited_findings`: validation errors containing "no inline citation";
- `contract_findings`, `checked_lines`, `unsupported_lines`;
- `median_tokens`, `median_cost`, `median_elapsed`, `max_elapsed`,
  `total_cost`;
- `first_attempt_report_guardrail_failures`.

For four nodes against six it gives the paired median reductions in tokens,
cost and elapsed time. For the reviewer it gives the median and minimum
retention and the number of accepted corrections.

README figures and published article figures are not changed by this study.

## Relationship to prior rejected work

Unchanged from August: this experiment does not change the scoring formula,
evidence-confidence floor, TRL rubric, maturity-language screen, uncited-claim
blocking policy, prompt caching, source-summary retrieval, or CrewAI version.
The production six-node arm is the unmodified control.
