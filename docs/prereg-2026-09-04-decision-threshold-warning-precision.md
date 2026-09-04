# Pre-registration: decision-threshold warning precision

Date: 2026-09-04

## Question

Can the advisory report audit stop treating source facts and explicitly scoped
analyst proposals as unqualified decision thresholds without weakening the
known unqualified-threshold detection?

This is a zero-network precision study over artifacts already on disk. It does
not authorize a provider request, a search request, a production run, or a
change to report scoring or blocking behavior.

## Frozen pre-change measurement

The exact narrow vocabulary currently shipped was applied before any code
change to 110 report files:

- 30 frozen benchmark reports;
- 79 timestamped historical reports at the local output root; and
- the separately preserved RTI02 production report.

The 30-report benchmark contained zero candidate lines, so it supplies no
precision denominator. Across all 110 reports, eight candidate lines appeared
in two reports. One candidate was already qualified and seven produced
warnings.

Manual report-context inspection classified all seven warnings as false
positives:

1. One historical comparison table described the USMLE pass threshold as a
   source fact. The phrase was not a decision-gate label and was followed by a
   semicolon rather than a label colon.
2. RTI02 contained six labelled pass/stop criteria. The same Markdown section
   explicitly stated before the list that all thresholds below were analyst
   proposals requiring confirmation by the eventual decision owner. Each gate
   also repeated analyst provenance after its criteria.

This coding was performed internally by an AI assistant and was not an
independent human or expert review. The corpus was not held out: RTI02 motivated
the measurement. The observed 0/7 warning precision is therefore a diagnostic,
not a production-rate estimate.

## Narrow implementation hypothesis

Two restrictions should remove the observed false positives while preserving
the known defect:

1. A bare `pass threshold`, `evidence threshold`, `decision threshold`, `kill
   criteria`, or `stop criteria` phrase is a candidate only when it is rendered
   as a Markdown/plain-text label followed by a colon. The already explicit
   sentence form `threshold(s) must be met` remains a candidate without a
   colon.
2. A forward-scoped declaration may qualify later candidates only when one line
   explicitly says that all thresholds below or in the section are proposals,
   require confirmation, or carry another existing authority qualifier. The
   declaration expires at the next Markdown heading. A generic disclaimer or a
   qualifier in an earlier section cannot qualify later text.

The second rule deliberately does not use a fixed line window. A list may be
long, while Markdown section boundaries provide a stricter semantic boundary
than arbitrary distance. It also does not treat the machine-readable decision
gate alone as proof that model prose is safe.

## Falsification and acceptance criteria

The change is rejected or narrowed further if any of the following occurs:

- any frozen benchmark report gains a warning;
- any of the seven observed false-positive warnings remains;
- the known unqualified Qwen `Pass Threshold:` line stops producing a warning;
- a scoped declaration qualifies a candidate after a new Markdown heading;
- an ordinary source-fact phrase without a label colon remains a candidate;
- unavailable/non-English states become clean passes;
- the audit becomes blocking or changes report text, scoring, evidence, Tool
  Calling, or provider behavior.

The post-change result must report the zero candidate denominator in the
30-report baseline separately from the broader 110-report diagnostic. Zero
warnings must not be described as measured perfect precision.

## Verification plan

- Add focused tests for source-fact exclusion, scoped qualification, heading
  expiry, and preservation of the known unqualified warning.
- Re-inject both defects: remove label-shape filtering and allow scoped state to
  cross a heading. The new tests must fail before the correct implementation is
  restored.
- Replay the 110 on-disk reports with zero network access.
- Run the complete zero-network suite, latest Ruff, and narrow Pylint `E0701`.
