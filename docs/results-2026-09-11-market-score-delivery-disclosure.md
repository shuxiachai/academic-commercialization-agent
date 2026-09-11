# Market-score comparison disclosure at delivery

Date: 2026-09-11. Inspection base: `37fd50118ee824edc2c2435aa043f229b1bd2b75`.
Status: offline behavioral repair; **not a scoring-policy or accuracy improvement**.

## Observed defect and decision

All 30 current local benchmark score artifacts contain a legacy
`market_uncertainty` flag; none contains a comparison qualification. The
browser previously omitted the flag entirely. The legacy amount parser mixes
metrics, years and scopes and labels its result `bn USD` without verifying
currency. A capped score therefore reached the user without its key limitation.
The [metric replay](results-2026-09-11-market-metric-comparability.md) and
[six-source inspection](results-2026-09-11-market-source-spot-check.md) do not
establish a validated replacement: zero fully attributable real positive pairs
is not agreement. Same-year USD headlines alone do not establish the inclusion,
price or measurement basis. No source labels were invented or retrospectively
upgraded to independent human review.

Change the delivery contract, not the frozen scoring computation. Keep the
formula, confidence floor, 3.5 market cap and byte-locked evidence/scoring
modules unchanged. A mixed market/funding regression deliberately still
produces 3.5, and asserts that the user receives an explicit limitation.
This preserves evidence lineage but leaves the numeric policy limitation open.

## Contract

`save_scores` now rebuilds `market_comparison` for market-bearing JSON from
both fresh and restored scorer outputs. Version `market-comparison-disclosure-v1`
always declares `comparability_status=not_assessed` and
`deduction_status=not_reconstructable`. Generated `verified` metadata is replaced.
It does not call an offline audit, fetch sources or adjudicate their contents.

| Stored legacy signal | Disclosure | What it does not prove |
|---|---|---|
| Recognized old `high (... spread: ... bn USD)` format | `triggered` | Comparable USD estimates, source truth or an actual deduction |
| Explicit null | `not_triggered` | Source agreement, sufficient coverage or a comparison pass |
| Missing, wrong type or unrecognized text | `unavailable` | That the cap did not run |

The raw `market_uncertainty` field remains an unchanged legacy diagnostic for
compatibility; its amounts are not verified monetary estimates. A downstream
consumer must read the qualification, not treat that string as normalized facts.
The actual pre-cap score is not available in these artifacts: 13 local scores
equal 3.5 and 17 are lower, which is not 13 proven deductions.

The shipped English/Chinese scorecard derives the conservative display state
from the raw legacy field. It never grants semantic verification based on
generated/stale `market_comparison` metadata. Old records get a visible caveat
without filesystem migration. New JSON reaches the normal `/scores` artifact
route unchanged; unrelated scores, formula, rationale and risk/opportunity
fields survive. Non-object or sparse non-market diagnostics keep their old
save behavior. Markdown/PDF report prose and historical files are not rewritten.

## Verification and limitations

- Pre-change full suite: **3045 passed + 1259 subtests**.
- Post-change full suite: **3104 passed + 1266 subtests** on local Windows /
  Python 3.12.9; latest Ruff and the project's narrow Pylint check passed.
- New suite: 59 zero-provider tests covering writer/HTTP/actual JS DOM,
  missing/null/malformed signals, two interface languages, legacy files,
  forged verification, restored outputs and numeric preservation.
- Targeted suite: **241 passed** before fault injection.
- Replayed all 30 local scores into a fresh output directory: every field from
  the previous saver is preserved, and 30/30 receive `not_assessed` with the
  recorded legacy trigger. **183 historical JSON/CSV hashes remain unchanged**.
  The current local units remain 29 live-labelled + 1 fixture-labelled; this
  is not a new validation of the archived all-live calibration CSV's identity.
- Bypassing the saver disclosure causes **13 assertion failures**. Omitting
  the DOM append causes **13 assertion failures**. Both files were restored
  to their exact pre-injection hashes; syntax/collection failures were not
  counted as successful defect detection.
- Real Chromium exercises saver -> artifact GET -> visible scorecard and
  report navigation, with no external or mutating requests. Initial attempts
  exposed two test-setup mistakes: adding a score tab changed the default tab,
  and its actual ID is `score`, not `scores`. Explicit navigation fixed the
  tests; the report assertions were retained. Both browser journeys then passed.

Full-suite/static/CI results and the public merge identity are recorded on the
delivery PR. Detailed production health observations stay in private operations
notes. Configuration readiness is not a paid report-quality canary or an SLO.
No project-provider request, paid report purchase, manual Railway restart,
Tool Calling activation or new independent reviewer judgment is part of this
maintenance. A future numeric-policy change still needs explicit comparable
source definitions, fresh evaluation and its own evidence-backed decision.
