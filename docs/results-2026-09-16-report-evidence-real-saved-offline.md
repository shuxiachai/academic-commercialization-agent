# Real saved-report follow-up: offline preparation result

Date: 2026-09-16. Protocol: `report_evidence_real_saved_offline_v1`.
The [preregistration](prereg-2026-09-16-report-evidence-real-saved-offline.md)
was committed at `84bd76b` before the new implementation. This result covers
local preparation, not a Qwen experiment, production change or accuracy study.

## Data and reference boundary

Inspection of 30 current local benchmark directories found 29 live and one
fixture. The selected second repetition is marked successful/live and its topic
matches the saved collection. Preserve all 20 sources in original order,
including 4 academic, 8 patent and 8 market entries. Do not treat this inventory
as reconstruction of the archived calibration CSV or independent source truth.

Two newly authored Chinese questions share one snapshot but have independent
conversations. RS01 asks for a material-level explanation; RS02 asks whether
that research supports a production-vehicle/deployment conclusion. Both require
a full read of the same 1,408-code-point NONEMPTY saved abstract. The negative
case is insufficient evidence, not CQ's missing-text control. These are
purposive development tasks on consumed evidence, not fresh held-out examples.

References were AI-authored and checked by a separate read-only AI reviewer
against the saved report/source bytes. No external paper was opened. The review
found no actionable reference mismatch; it is not a human gold label, full-paper
verification or a test of model answers, which do not yet exist.

Original report/source/metadata bytes, ordered questions, projection,
configuration, snapshot/catalog and separate reference-label bytes are bound.
Raw reports, questions, labels and probe transcripts remain local/private.
Hashes identify current files; they do not grant transmission authority or
attest the original historical execution.

## Intercepted wire rehearsal

The existing catalog-native adapter was exercised with a fake key and
`httpx.MockTransport`. All four requests stayed local. Scripted replies selected
the target and supplied the final states; this is not native model selection,
inference, token usage or spending.

The full 20-entry catalog occupied 2,891 ASCII bytes, with no omission or title
truncation. The callback and complete HTTP bodies stayed below 12,288 bytes:

| Case | Callback bytes, turns 1 / 2 | HTTP body bytes, turns 1 / 2 | Scripted mechanical observation |
|---|---|---|---|
| RS01 | 5,471 / 7,413 | 5,594 / 7,566 | Answer with one actually delivered receipt |
| RS02 | 5,429 / 7,371 | 5,552 / 7,524 | Abstain with no final IDs; retain the nonempty served receipt |

The paired tool message contained the exact complete saved window, and each
actual HTTP body hash matched its local reservation record. Both mechanical
reviews passed while retaining `semantic_support=not_assessed` and
`answer_verification=not_verified`. Original input hashes remained unchanged.

An earlier private probe stopped because a pre-consumed mock HTTP response
could not support the frozen adapter's raw streaming reader. The harness was
corrected to use `ByteStream`; the unsuccessful artifacts were retained.
No production transport change, paid retry or hidden replacement run occurred.

Independent implementation review found that the private probe originally
derived its scripted source choice from reference labels. This indirect
dependency was removed: the fixed script now accepts only prepared inputs,
and references enter review after execution. A separate local counterfactual
changes both reference targets without changing any of the four HTTP body
hashes, invalidates the old binding and fails the receipt review as expected.
Execution is forbidden from reading the label file. Reinjecting that read
tripped the new regression; exact restoration returned it to green. These
additional intercepted controls are not extra model cases.

## Verification

The clean baseline was 4,261 tests and 1,381 subtests. Default Windows temporary
directory access failed at setup; a fresh workspace basetemp resolved that
environment failure without ACL changes, warning suppression or weaker tests.

The new module has 81 synthetic regression cases. They exercise original-byte
drift, full source projection, separate label binding/payload isolation, actual
read receipts, nonempty read-then-abstain, capacity and explicit transport.
Reinjecting an ignored-label-hash defect made its regression fail; exact restore
returned all 81 tests to green. Real-packet rehearsal is a separate denominator.

The full suite passed **4,342 tests / 1,385 subtests in 177.68 seconds**.
Latest Ruff and the narrow Pylint command passed. After the documentation
increment, its separate contract passed 6 tests / 694 subtests. These are
revision-specific local counts, not independent answer-quality observations.
The independent read-only implementation reviewer closed the private probe
finding after the correction and found no remaining actionable finding in the
reviewed scope. This was an AI code/artifact review, not an independent rerun or
semantic validation. Final packet publication is still a local verification.

## Remaining gate

There is no live runner or production route in this change. A future two-case
real-model pilot needs a distinct committed execution protocol, source/data
locks, at most four sequential requests, first-failure stop, explicit cost
accounting and data authorization. That scope must cover both questions, all
visible titles and any selectable saved window, not just the reference target.
Report prose, raw metadata, local paths and labels must remain outside the
model payload. The old synthetic allowance is not real-data permission.

Mechanical closure, semantic support, user utility and production admission
remain different gates. This small developmental packet establishes none of
the latter three.
