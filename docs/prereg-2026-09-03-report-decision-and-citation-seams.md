# Pre-registration: report decision and citation seams

Date: 2026-09-03

## Question

Can the delivered report make its decision applicability and threshold
provenance unambiguous, and can a deterministic, precision-first audit catch a
narrow class of citation-scope mismatch without turning a heuristic into a
blocking guardrail?

This work follows two observed production failures. A paid Decision Context
canary did not preserve the exact machine-readable assessment-mode token in the
delivered prose and introduced an unqualified threshold. A later Qwen canary
introduced mandatory pass/kill thresholds in orientation mode and used an
oxide-electrolyte source to support a sulfide-electrolyte action criterion.

## Frozen baseline measurements

The measurements below were completed before implementation and use only
artifacts already on disk, except for a read-only fetch of the already public
Qwen canary artifacts. No model or search-provider call was made.

- All 30 benchmark reports were scanned.
- A broad threshold vocabulary (`threshold`, `minimum`, `at least`) matched 18
  lines in 9 reports. Manual inspection found source facts such as cycle counts,
  patent language, and stated physical requirements rather than invented
  decision gates. That vocabulary is therefore rejected.
- The narrow decision-gate vocabulary (`pass threshold`, `evidence threshold`,
  `decision threshold`, `thresholds must be met`, `kill criteria`, and `stop
  criteria`) matched 0 lines in the 30 benchmark reports and does match the
  known Qwen canary.
- A material-family citation rule over sulfide, oxide, chloride/halide and
  polymer electrolyte terminology produced 23 checkable report segments, zero
  mismatches and 40 segments that could not be decided from the available
  summaries. The known Qwen canary produced four checkable segments, one
  mismatch and eleven unverifiable segments; the mismatch is the already
  observed sulfide/oxide case.

The unverifiable denominator is part of the result. It must never be presented
as if the audit checked and cleared those segments.

## Implementation hypothesis

The following bounded changes should make the observed defects visible without
changing the calibrated score or rejecting a completed paid run:

1. Extend Decision Context with optional success criteria and an explicit
   owner-approval declaration. The public gate exposes only provenance state,
   not the user text.
2. Inject a code-owned, localized applicability block into the report at the
   persistence seam. It must contain the exact assessment-mode token, whether
   actor-specific GO/NO_GO is permitted, and the success-criteria provenance.
3. Run a post-generation, non-blocking report audit against the original model
   report and the validated source registry. The audit may flag only the frozen
   narrow threshold vocabulary and the frozen material-family contradiction.
4. Persist the full audit as JSON and carry its summary through both run-status
   endpoints and the browser. `not checked`, `not applicable`, `partial`, and
   `completed` remain different states.

## Precision rules

### Threshold provenance

A narrow threshold line is qualified only when its local text explicitly marks
the criterion as one of the following:

- owner-approved or user-supplied;
- an analyst proposal, illustrative value, or value requiring confirmation;
- an external/source benchmark rather than a decision-owner gate.

A citation by itself does not establish owner approval. General factual uses of
`minimum`, `at least`, and `threshold` are outside this audit.

### Material citation scope

A report line is eligible only when it names exactly one frozen electrolyte
material family and contains at least one valid A/P/M citation. A mismatch may
be reported only when every cited source is checkable, no cited source names the
claimed family, and every cited source explicitly names a different frozen
family. Search snippets, short summaries, missing citations, mixed-family
sources, and sources without material-family language are unverifiable rather
than mismatches.

## Falsification and acceptance criteria

The implementation is rejected or narrowed further if any of the following is
true:

- any of the 30 baseline reports gains a threshold-provenance finding;
- any of the 23 previously checkable baseline material segments gains a
  mismatch finding;
- the known Qwen sulfide/oxide line is not reported;
- an unavailable or zero-denominator audit is shown as passing;
- the applicability block is absent from the persisted Markdown, or either API
  endpoint silently drops the audit summary;
- the audit blocks, retries, or discards a completed report;
- the implementation changes the scoring formula, evidence-confidence floor,
  existing uncited-claim blocking policy, or production Tool Calling state.

## Verification plan

- Add unit tests for Decision Context normalization, provenance validation,
  legacy RunSpec compatibility and checkpoint identity.
- Add persistence-seam tests for exact mode/provenance labels and localization.
- Add positive, negative, mixed and unverifiable report-audit fixtures.
- Add status/progress/artifact/client seam tests.
- Re-inject one persistence defect and one source-scope defect and confirm the
  new tests fail before restoring the implementation.
- Run the complete zero-network suite, latest Ruff, the existing narrow Pylint
  check, and the loopback browser smoke test before publishing the branch.
