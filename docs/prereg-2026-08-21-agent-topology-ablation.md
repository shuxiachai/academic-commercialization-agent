# Pre-registration — agent-topology ablation

Written before the experiment harness and before any paid treatment run. The
purpose is to test whether this product's six named agents buy measurable
quality or reliability, rather than to defend the architecture already in the
repository.

## Question

Holding the retrieved evidence, model settings, report contract, and blocking
report validation fixed, what is gained by decomposing report generation into
one, four, or six LLM nodes?

This experiment tests **workflow topology**, not whether CrewAI is necessary.
All three arms use CrewAI so provider integration, retry behaviour, and usage
accounting stay comparable. A separate CrewAI-versus-raw-asyncio experiment
would be needed to measure framework overhead.

It also does not test whether a technology-transfer officer would act on the
report. That requires independent users and remains an open product-validity
question whatever this experiment finds.

## Arms

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

## Outcomes

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

| # | Prediction |
|---|---|
| P1 | The four-node arm has fewer first-attempt report-guardrail failures than the monolith |
| P2 | The six-node arm has no more unsupported checked numeric claims than the four-node arm |
| P3 | Removing two nodes reduces median cost and total tokens by at least 20% from six to four nodes |
| P4 | The monolith is cheapest, but loses at least one common quality or reliability outcome to the four-node arm |

## Decision and falsification rules

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

### Stage 0 — offline harness verification

Run unit tests, deliberately re-inject a known defect to prove the new test
fails, run the full zero-network suite, and run Ruff. This stage costs nothing.

### Stage 1 — paid pilot

Run fixture case 03 once through all three arms. The pilot validates output
wiring, accounting completeness, and actual per-arm cost. Pilot results do not
decide the architecture.

Inspect the exact three-cell plan first. This is the safe default and makes no
files or API calls:

```bash
uv run python ablation.py --pilot
```

After separately approving the spend, run the pilot with a soft emergency
ceiling. The ceiling is checked after each serial cell, so one in-flight cell
can take the total above it:

```bash
uv run python ablation.py --pilot --execute --stop-after-usd 0.20
```

Then rebuild and inspect the summaries from persisted metadata rather than
trusting terminal output:

```bash
uv run python ablation_check.py outputs/ablation/<experiment-id>
```

Stop before the full study if any arm:

- uses live retrieval;
- loses its final report at the persistence boundary;
- reports cost as complete when an agent is unpriced;
- records `0 checked` as a grounding pass; or
- cannot identify its fixture digest, model usage, or guardrail attempts.

### Stage 2 — full paid study

Only after reviewing the pilot: ten topics, three repetitions, three arms,
ninety serial cells. Existing successful cells are resumable; arm identity and
fixture digest must match before reuse.

The full-study confirmation flag is intentionally separate from `--execute`:

```bash
uv run python ablation.py --full --execute --confirm-full-study \
  --stop-after-usd <approved-budget>
```

## Relationship to prior rejected work

This experiment does not change the scoring formula, evidence-confidence
floor, TRL rubric, maturity-language screen, uncited-claim blocking policy,
prompt caching, source-summary retrieval, or CrewAI version. The production
six-node arm is the unmodified control.

## Stage 1 pilot outcome - 2026-08-21

The three approved paid cells ran from commit `e532eb80` against frozen case
03 (`solid-state batteries for electric vehicles`). The persisted experiment
is `outputs/ablation/20260821T114329Z-e532eb80`.

| Arm | Status | Requests | Tokens | Observed cost | Elapsed |
|---|---:|---:|---:|---:|---:|
| Monolith | success | 1 | 15,535 | $0.009123 | 43.935 s |
| Specialists + writer | success | 4 | 37,130 | $0.019728 | 61.739 s |
| Full | success | 6 | 79,143 | $0.028989 | 74.257 s |

All three final reports reached disk, used the same fixture digest, represented
all three source domains, and had complete model pricing. Total observed spend
was $0.057840.

The pilot nevertheless hit the pre-registered stop rule. CrewAI 1.14.7 executes
the private `Task._guardrail` callable captured during construction, while the
recorder had replaced only the later public `Task.guardrail` field. Production
guardrails still ran, but all attempt counts were therefore falsely recorded as
zero and P1 could not be evaluated.

A second measurement defect was exposed by the saved reports. A line containing
both a checkable academic or patent citation and a non-checkable search-snippet
market citation was treated as wholly checkable. Market figures that appeared
verbatim in M4 and M5 were then compared only with the unrelated checkable
sources and falsely marked unsupported. The precision-first correction treats
mixed-provenance lines as unverifiable unless every cited source is checkable.

With that correction, offline re-analysis reports zero unsupported numeric lines
for all three arms; checked/unverifiable lines are 6/30, 5/12, and 4/14 for the
monolith, four-node, and full arms respectively. This re-analysis diagnoses the
saved output but does not repair the missing runtime guardrail-attempt history.

The one-run cost differences are descriptive pilot observations, not an
architecture decision. The paid pilot must be rerun from the corrected commit
before the ninety-cell study can be considered.

## Corrected Stage 1 pilot outcome - 2026-08-21

The three approved cells were rerun from merge commit `2d929429` against the
same frozen case 03 and fixture digest `8643e7369b337b9b`. The persisted
experiment is `outputs/ablation/20260821T130155Z-2d929429`.

| Arm | Status | Requests | Tokens | Observed cost | Elapsed |
|---|---:|---:|---:|---:|---:|
| Monolith | success | 1 | 16,484 | $0.008272 | 56.758 s |
| Specialists + writer | success | 4 | 37,558 | $0.017908 | 64.534 s |
| Full | reviewer guardrail failure | 6 | 67,940 | $0.028757 | 89.574 s |

Total observed spend was $0.054937, below the approved $0.20 soft ceiling.
Every provider request was attributed to a priced model, and all three cells
used fixture evidence rather than live retrieval.

The corrected measurement seam worked. The monolith recorded one report
guardrail call; the four-node arm recorded one call for each of its four tasks;
and the full arm recorded one call for each evidence task and the writer plus
two failed reviewer calls, including one retry. This resolves the instrumentation
defect found in the first pilot without changing production guardrail behavior.

The full arm did not reach the scorer or persist a final report. On both
reviewer attempts, the model returned at least one correction whose `find` and
`replace` strings were identical while explaining that no change was needed.
The reviewer guardrail correctly rejected the no-op, but the second identical
failure exhausted its single retry and failed the whole crew. This is a real
workflow-reliability result, not a harness or persistence defect, and triggers
the Stage 1 stop rule. No full ninety-cell study should run until the no-op
review path is made failure-tolerant and another three-cell pilot succeeds.

The two completed reports also failed the offline report contract: the
monolith had 12 findings and the four-node arm had 3. The monolith introduced
an uncited automotive cycle-life threshold, which the numeric grounding screen
correctly identified as unsupported. The four-node screen's `2013 eur` finding
is a false positive caused by reading the phrase "2013 European patent" as a
currency amount. Its patent-framing finding is also a negated disclaimer that
contains the prohibited phrase rather than an affirmative legal claim. These
precision defects must be separated from genuine report defects before the
quality metrics can support an architecture decision.

This corrected pilot still does not decide P1-P4. P1 was not supported in this
single case because both completed arms passed the report guardrail on their
first attempt. P2 and the common full-arm quality outcomes are unavailable
because the reviewer stopped the full arm. The four-node arm used 55.3% of the
failed full arm's tokens and 62.3% of its observed cost, but the full arm never
reached its scorer, so those differences are diagnostic only.
