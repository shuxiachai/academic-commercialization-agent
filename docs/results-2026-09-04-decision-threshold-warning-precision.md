# Result: decision-threshold warning precision

Date: 2026-09-04

## Outcome

The precision-first narrowing is implemented and passes its pre-registered
zero-network acceptance criteria. It removes the seven observed false-positive
warnings while preserving the known unqualified Qwen threshold finding and the
explicit `threshold(s) must be met` sentence form.

This is an advisory detector improvement. It does not change report prose,
guardrail blocking, scoring, evidence, provider calls, Tool Calling, or run
admission.

## Pre-change measurement

The exact shipped rule was replayed against 110 report files already on disk:

| Corpus | Reports | Candidate lines | Warnings |
|---|---:|---:|---:|
| Frozen benchmark | 30 | 0 | 0 |
| Timestamped historical output root | 79 | 1 | 1 |
| RTI02 preserved production report | 1 | 7 | 6 |
| **Total** | **110** | **8** | **7** |

The benchmark has no candidate and therefore no precision denominator. Manual
context inspection classified all seven warnings as false positives. The one
historical warning described an external USMLE pass threshold in a comparison
table, not a commercialization gate. RTI02's six warnings were pass/stop labels
inside a section that had already declared all following thresholds to be
analyst proposals requiring owner confirmation.

The eighth candidate was RTI02's code-derived narrative statement that any
additional decision threshold is an analyst proposal. The old rule already
treated that line as qualified, so it did not warn.

The coding was performed internally by an AI assistant. It was not an
independent human/expert review, and RTI02 was not held out because it motivated
the study. The pre-change `0/7` is a diagnostic on this corpus, not a production
precision estimate.

## Implemented boundary

The detector now separates two actionable shapes from source-fact noun phrases:

- `pass threshold`, `evidence threshold`, `decision threshold`, `kill criteria`,
  and `stop criteria` require label punctuation, accepting both common Markdown
  emphasis placements around the colon;
- `threshold(s) must be met` remains actionable without a colon and is checked
  before the shorter regex alternatives can consume it.

A forward declaration qualifies later candidates only when it explicitly
scopes all thresholds below or in the section and contains an existing authority
qualifier. The state resets at every Markdown heading. A generic disclaimer,
machine-readable gate state, or declaration in another section cannot suppress
a warning.

## Post-change replay

The same 110 files produced:

| Corpus | Reports | Candidate lines | Warnings |
|---|---:|---:|---:|
| Frozen benchmark | 30 | 0 | 0 |
| Timestamped historical output root | 79 | 0 | 0 |
| RTI02 preserved production report | 1 | 6 | 0 |
| **Total** | **110** | **6** | **0** |

The USMLE source fact and RTI02's code-derived narrative line are no longer
candidates. RTI02's six labelled criteria remain candidates but are correctly
qualified by their same-section declaration. Zero warnings is not reported as
perfect precision because the post-change corpus contains no positive warning
denominator.

## Defect reinjection

Both protocol-required defects were reintroduced independently:

1. Replacing label-shape detection with the old broad noun-phrase search made
   `test_source_fact_pass_threshold_without_label_colon_is_not_a_candidate`
   fail: the USMLE source fact changed from `not_applicable` to `completed`.
2. Removing the Markdown-heading reset made
   `test_section_scope_expires_before_a_later_markdown_heading` fail: an
   unqualified investment threshold in a later section was incorrectly cleared.

The correct implementation was restored, and all 11 focused report-audit tests
passed. The complete zero-network suite then passed 2,066 tests plus 678
subtests in 62.94 seconds. Latest Ruff reported `All checks passed!`, and the
CI-matching narrow Pylint gate for exception ordering, unreachable code,
used-before-assignment and undefined variables completed cleanly. No browser,
provider, search or model call was required because no API or DOM seam changed.

## Interpretation limits

This result establishes that two observed false-positive classes no longer
warn on the measured files and that the known synthetic/production-derived
defect fixture remains detectable. It does not establish precision, recall,
source truth, report accuracy, user value, or behavior on unseen model prose.

A future natural positive warning should be reviewed rather than assumed
correct. A new held-out corpus with eligible independent labels is required
before publishing a precision rate or making this advisory check blocking.
