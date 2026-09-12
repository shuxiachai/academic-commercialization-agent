# Whole numeric tokens and market-cap arithmetic provenance

Date: 2026-09-12. Starting main:
`ec115e91fcd4cece2f0b3d8093337b88d5f08988`. Zero paid provider calls.

## Measured defects and adopted changes

All four submitted cases reproduced before editing. Sources containing
`1e-3%` / `1e+3%` supported a claimed `3%`; `26.1 kg / m2` supported
`26.1 kg`; `− 10.5%` supported positive `10.5%`.

The lexer now consumes complete scientific numbers and spaced signs. Bounded
Decimal expansion supports equivalent scientific/plain forms and leading
decimal points without binary float rounding or exponent suffix matches.
Recognized Wh/kg and Wh/L compounds permit separator whitespace. Unsupported
compound units, malformed exponents, power expressions and quantity ranges
remain explicit **unverifiable**, including on the source side, not support.
The source-absence warning remains non-blocking. This is not general unit
conversion, interval arithmetic, manuscript entailment or universal notation
support. Existing small-count, date and analyst-bound exclusions remain.

The market/funding reproducer still yields the historical **5 -> 3.5** cap.
Changing that numeric rule requires independent comparable samples and a
separately evaluated policy; disclosure is not a scoring-correctness repair.
The production wrapper now captures the validated normalized score before the
frozen factory mutates its output, then records:

- pre/post market scores, cap, actual deduction in market-scale points;
- whether the old rule triggered versus whether it actually reduced the score;
- the specific untyped >5 spread reason, never a verified USD disagreement.

Input audit fields are discarded by the frozen schema dump and overwritten
by code after success. The receipt travels in TaskOutput.raw through the real
checkpoint callback/restoration, score saver, HTTP artifact and bilingual DOM.
The separate implementation participates in local recovery identity. Read
validation checks schema/arithmetic consistency; its version marker is not
authentication. Trust remains the post-guardrail publisher and hash-bound
checkpoint, not arbitrary files claiming to be code-owned.

Historical scores without a receipt stay not reconstructable. Malformed or
inconsistent records do not become zero deductions or hide otherwise valid
scores. Same-definition market comparability remains not assessed in every
case. No historical score or experiment lock was rewritten.

## Frozen-data replay and limits

Baseline: **3104 passed + 1266 subtests**. Read-only replay of 90 evidence
artifacts in 30 current local units (29 live + 1 fixture):

| Numeric-screen outcome | Before | After |
|---|---:|---:|
| Checked findings | 32 | 23 |
| Ungrounded findings (subset of checked) | 0 | 0 |
| Unverifiable findings | 179 | 188 |
| Audit errors | 0 | 0 |

Nine range-bearing findings move from grounded to unverifiable. This is reduced
asserted coverage, not a measured precision improvement. The prior implementation
matched parts of ranges; this repair does not pretend to understand their full
semantics. An initial broader grammar also counted calendar/count ranges and
made publication dates globally uncertain. Those regressions were fixed by
retaining the old date/count exclusions; assertions were not weakened.

All 183 archived JSON/CSV files retain their hashes. No consumed evaluation
labels, market drafts, raw human reviews or paid results were modified. The
previous six-source inspection still establishes no real same-definition
positive pair; that evidence gate is not filled by this arithmetic audit.

## Verification

76 new cases exercise supported and rejected equivalents, unknown grammar,
real evidence JSON publication and HTTP/client display; the scoring cases
compare every pre-existing output field with the frozen factory. They include
triggered-but-not-reduced scores, forged input metadata, malformed delivered
receipts, failed validation and real six-node checkpoint hydration.

Six defect injections must cause test assertions to fail before exact source
hash restoration: fragment lexer (23 failures), lost spaced compound suffix
(7), omitted cap receipt (24), unchecked receipt metadata (15), dropped client
receipt (24), and omitted recovery identity (1). Initial patch-runner/Windows
command-size and fragment-anchor errors are tooling failures, not successful
mutation evidence.

Local full regression after documentation sync: **3180 passed + 1273 subtests**. Latest Ruff, narrow
Pylint and both Chromium journeys pass. The result journey retains the old
unknown-cap case and adds a new measured receipt; the composer intercepts its
paid POSTs. Both report zero provider calls and unexpected/page errors.
Release CI and deployment observations are recorded separately on the PR and
in private operating notes. No paid canary or manual Railway restart is implied.
