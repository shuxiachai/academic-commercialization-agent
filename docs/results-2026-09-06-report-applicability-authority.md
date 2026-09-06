# Report applicability authority at delivery

Date: 2026-09-06. Implementation base:
`dc79efb5e91d81ce7a58bc7c867e8c9819e9a1f7`.
This is an offline maintenance result, not a paid canary or a new quality study.

## Inspect stored evidence before changing the rule

The bounded local inventory contains 30 benchmark reports, 79 reports in
direct timestamped run directories, and the retained RTI02 report: 110 total.
No reserved evaluation cohort, raw reviewer file or provider endpoint was read.

| Local group | Reports | Threshold candidates / warnings | Material candidates / lexically checkable / unverifiable |
|---|---:|---:|---:|
| Frozen benchmark | 30 | 0 / 0 | 38 / 22 / 16 |
| Direct historical runs | 79 | 0 / 0 | 76 / 25 / 51 |
| Retained RTI02 delivery | 1 | 6 / 0 | Not run: this local snapshot has no sibling validated_sources.json |

For the material check, source rows were loaded from the existing sibling
`validated_sources.json` and validated through the source schema. All 30
benchmark files and all 79 historical source files were readable. The latter
group contains 35 English, 39 Simplified Chinese, two Japanese, two Korean and
one Italian report. The current material heuristic does not cover those 44
non-English reports; it must not describe them as passed.

Across the covered records, 47 segments were lexically checkable and 67 were
unverifiable; there were no material-mismatch warnings. These are lexical
coverage counters, **not 47 independently verified factual claims**. No external
source was opened. Missing sources beside the local RTI02 copy do not establish
that its original run lacked evidence. The threshold-only check does not need
those sources and still sees its six qualified candidates.

Only RTI02 contains the reserved applicability marker, with the correct
orientation caveat. No naturally occurring forged declaration was found in
these 110 files. The defect below was reproduced with synthetic model output,
not inferred to be an observed production incident. These current diagnostics
do not replace the denominators in earlier dated replay results.

## Reproduced delivery defect

`add_applicability_block` treated the presence of
`<!-- decision-applicability:v1 -->` anywhere in generated text as evidence that
Python had already written the authoritative paragraph. A copied bare marker,
an inline example, or a fabricated code-labelled `decision_support` /
`owner_approved` paragraph therefore prevented the actual orientation gate from
being delivered. The raw report could disagree with the correct status payload.

An independent placement defect searched for the first H1 anywhere in the
report. An H1 inside a fenced example could receive the notice inside that
example rather than at the report preamble.

Both are deterministic delivery defects. Neither requires broadening a
heuristic screen or asking a model to correct itself.

## Changed contract

- With a current gate, the saved report reasserts its exact mode, permission and
  threshold-provenance status. The gate computation and translated copy are
  unchanged; a genuinely complete context remains eligible.
- A marker is a locator, not an authorship credential. Only the reserved
  marker plus one of the six known code-owned labels identifies a replaceable
  metadata paragraph, including contiguous blockquote continuation lines.
  Stale, copied and duplicated reserved paragraphs are replaced.
- Full current content at the report preamble is idempotent, including its
  existing LF/CRLF spacing. Matching content buried later in the report is not
  an adequate preamble.
- The notice follows an opening H1, if present, or precedes other model prose.
  A later example heading cannot move it into a fence.
- No gate means no retrospective relabelling. Ordinary unmarked prose, bare
  markers and inline examples are preserved; this is not a semantic scrubber.

Changing every report to orientation would hide legitimate decision contexts.
Simply prepending a new notice would leave stale code-labelled approval below
it. Neither alternative preserves the authority contract.

## Boundary verification

The initial suite passed 2,240 tests and 1,144 subtests before editing.
The implementation adds 25 tests covering disk persistence, the real report
download endpoint, matching status/progress gates, six-language replacement,
approved-context positive controls, legacy identity, LF/CRLF identity, duplicate
paragraphs, buried valid notices and fenced headings.

The real Chromium fixture now passes fabricated approval through `save_report`
instead of pre-writing a correct final string. The browser asserts one visible
canonical paragraph, orientation, no assessed actor-specific GO/NO_GO,
`not_established`, and absence of the fabricated approval. The small existing
renderer uses paragraph elements for this Markdown; the test targets its actual
DOM, not an assumed general-purpose blockquote renderer.

Defect re-injection, followed by restoration:

1. Restore the old marker-presence early return: 19 of the 25 tests fail, and
   Chromium sees `decision_support` instead of the required `orientation`.
2. Restore the first-H1-anywhere placement: the fenced-heading case fails;
   the plain-introduction positive control still passes.

The post-fix in-memory preservation replay leaves all 110 input byte strings
unchanged: 30 benchmark and 79 historical reports through the no-gate legacy
path, and the existing RTI02 report through its current English orientation
gate. No stored report was rewritten.

After restoration, the full suite passed 2,265 tests and 1,144 subtests.
After documentation synchronization it passed again with 2,265 tests and
1,149 subtests; the five additional subtests check documentation links.
Latest Ruff, the narrow CONTRIBUTING Pylint command, and standalone Chromium
passed. Chromium recorded zero paid-provider requests, external requests,
mutation attempts, console errors and page errors.

One concurrent local validation attempt reported a Windows connection reset
and failure to stop the loopback ASGI server cleanly. The unchanged standalone
rerun passed; no timeout, warning policy or assertion was relaxed. This is a
local harness observation, not evidence of a production transport failure.

## Limits and next step

This protects the reserved code-owned delivery paragraph, not every possible
way model prose can assert approval. Unmarked claims, qualitative citation
entailment, source truth and user decision value remain unestablished.
The original Decision Context canary failure remains a failure.

No scoring formula, confidence floor, source screen, CrewAI task, provider
adapter or Tool Calling policy changed. Supplementary retrieval remains
zero-call shadow mode; the failed v8 unseen evaluation is not reopened.

After separately authorized merge, existing delivery code can be checked
without purchasing another assessment. A new semantic or user-value claim
needs its own bounded evidence and protocol, not more permissive guardrails.
