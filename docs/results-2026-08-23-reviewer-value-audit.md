# Result: blinded audit of Reviewer value

**Completed:** 2026-08-23

**Registered before labels:**
[`prereg-2026-08-22-reviewer-value-audit.md`](prereg-2026-08-22-reviewer-value-audit.md)

**Incremental model cost:** USD 0; the audit reused frozen ablation artifacts

## Decision

Both evaluator forms completed all nine report pairs and independently passed
the frozen retention criterion. The result therefore **provisionally supports
retaining the production Reviewer** for a larger independent evaluation.

It does not prove that all six production nodes are necessary, that the reports
are useful to target users, or that the cited claims are factually correct.
Those questions require different comparisons and endpoints.

## Unit of analysis

The topology ablation recorded 34 accepted Reviewer plan items across nine
successful full-topology runs. It did not persist a clean before/after pair for
every individual correction. The pre-registered audit therefore used the nine
complete Writer-draft versus reviewed-report pairs as its units. The result
must not be restated as “34 corrections were verified.”

## Frozen criterion

The Reviewer was provisionally supported only if every report pair was judged
and all three thresholds passed:

| Frozen threshold | Evaluator A | Evaluator B | Result |
|---|---:|---:|---|
| Reviewed report preferred in at least 6/9 pairs | 7 | 7 | Both pass |
| Reviewed report labelled harmful in at most 1/9 pairs | 0 | 0 | Both pass |
| Draft has better citation support in at most 1/9 pairs | 1 | 1 | Both pass |

The harmful-version counts above refer specifically to cases where the
**reviewed** report was judged harmful. Evaluator B marked the draft harmful in
two pairs; Evaluator A marked neither version harmful.

## Descriptive outcomes

| Dimension | Evaluator A | Evaluator B |
|---|---|---|
| Overall preference | reviewed 7, draft 1, tie 1 | reviewed 7, draft 1, tie 1 |
| Citation support | reviewed 6, draft 1, tie 2 | reviewed 7, draft 1, tie 1 |
| Decision usefulness | reviewed 2, draft 0, tie 7 | reviewed 7, draft 1, tie 1 |
| Harmful version | reviewed 0, draft 0, neither 9 | reviewed 0, draft 2, neither 7 |

Across the 18 evaluator-pair judgments, the reviewed report was preferred 14
times, the draft twice, and two pairs were ties. These totals are descriptive;
the sample is too small and its recruitment too informal for population-level
inference.

## Inter-rater agreement

| Dimension | Exact agreement | Disagreements |
|---|---:|---|
| Overall preference | 9/9 (100%) | none |
| Citation support | 8/9 (88.9%) | R09 |
| Decision usefulness | 3/9 (33.3%) | R01 and R05–R09 |
| Harmful version | 7/9 (77.8%) | R02 and R09 |
| All recorded categorical judgments | 27/36 (75.0%) | — |

The stable part of the result is overall preference, with relatively strong
agreement on citation support. Decision usefulness is not stable: Evaluator A
used `tie` in seven pairs while Evaluator B preferred the reviewed report in
seven. The project therefore does not promote the stronger claim that Reviewer
reliably improves business decisions.

## Method records and limitations

- Evaluator B confirmed reading all nine pairs, using no generative AI, seeing
  no answer key, A/B identity, or other reviewer results, and spending about
  2 hours 30 minutes.
- Evaluator A's returned material included an AI-use statement. The study owner
  later clarified that the substantive judgments were made and checked by a
  person and that the AI-related statement was pasted in error. The form is
  retained because its labels were owner-confirmed, but the correction happened
  after return and the actual human review time is unavailable. This weakens
  provenance and is disclosed rather than silently normalised.
- Neither evaluator opened the underlying papers, patents, or market sources.
  “Citation support” therefore means internal correspondence and apparent
  support in the report, not independent verification of source truth.
- This is one 9-pair experiment built from a single frozen evidence set and one
  model configuration. Evaluators were not recruited as a representative panel
  of technology-transfer or investment professionals.
- The audit evaluates complete reports, not the accuracy of each of the 34
  accepted Reviewer plan items.

## What this changes

The production topology remains unchanged. The audit supplies evidence for
keeping Reviewer while the project gathers stronger evidence. It does not
override the topology ablation's conclusion that four domain-specialised nodes
captured the measured quality at lower cost than the six-node workflow.

The Reviewer comparison and the separate user-utility audit answer different
questions. This audit compares Writer draft with reviewed report; the utility
audit compares the complete system with a monolithic baseline. A report-level
Reviewer preference can coexist with no demonstrated end-user utility advantage
for the full topology.

## Next evidence required

1. Persist structured correction-level plans in a future paid experiment so
   individual Reviewer edits can be audited rather than inferred from full
   reports.
2. Repeat with a larger, independently recruited evaluator panel and record
   expertise, time, AI use, and source-opening behaviour before unblinding.
3. If decision usefulness remains an objective, tighten its rubric or use
   target-user tasks with observable go/no-go decisions instead of relying only
   on a broad ordinal judgment.
