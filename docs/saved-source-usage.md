# Isolated saved-source usage delivery

This successor connects operation-scoped native accounting to an isolated
receipt response and browser. It does not mount a production route, discover a
credential, add a paid runner or reopen a consumed canary. The existing locator,
native transport and RQ runner remain unchanged; their historical observations
retain their original meaning.

## Why this seam needs its own observation

Before edits, the full local suite passed 6,583 tests and 1,588 subtests. Read-only
inspection of the closed [RQ batch](results-2026-09-20-saved-source-receipt-qwen-canary.md)
found complete native usage for both requests: 1,191 input / 34 output tokens,
USD 0.000799403 estimated use and USD 0.022298624 reservation consumption.
Both historical receipt replies still used `not_observed` for usage and cost.
Those records are evidence of the gap, not outputs of this new implementation.

Do not copy the old batch into a new receipt, infer that an old request was free,
or relabel the historical client result. Native response usage, budget reservation,
price estimate and provider invoice are separate facts.

## Compatibility and authority

The old controller and receipt factory keep their default behavior and exact
legacy fields. An explicitly configured accounted selector uses the same
authorization, durable intent and shared paid admission. It cannot be combined
with a legacy selector. Providing only a store allows observation, not execution.

Accounting belongs to the actual claimed receipt and bound snapshot. The owner,
intent fingerprint, report identity and source binding come from the controller,
never a browser-supplied payer or a global last-result variable. Same questions
under different receipt keys are distinct operations and must not share accounting.

The dedicated Qwen wrapper receives its key, question, snapshot and fresh native
ledger explicitly. It has no environment or BYOK fallback, cannot be reused for
another receipt, and does not make a new ledger to retry an uncertain attempt.
Construction and offline tests do not grant live transmission authority.

## Delivery without rewriting the legacy receipt

The new isolated envelope is versioned as `saved_source_receipt_usage_v1`:
it contains the original strict receipt and a separate accounting projection.
The original receipt's unobserved fields remain unchanged. Only the new projection
describes observations made by the accounting collector.

The separate factory serves its page at `/`, new assets at `/usage-static/`,
`POST /api/runs/{run_id}/saved-source-usage` and
`GET /api/saved-source-usage-receipts`. It reuses the legacy state machine and
strict saved-result validator rather than copying their authorization and
recovery behavior. These paths are not registered by `api.main`.

The accounting projection carries schema/method/scope identity, the receipt-key
hash, run ID and expiry, then independent publication, dispatch, native-journal,
model-match, usage and cost facts. It does not expose owner IDs, fingerprints,
questions, titles, receipt keys, provider bodies or filesystem paths. The complete
response stays within 128 KiB; the accounting component has its own 4 KiB bound.

| Observation | What it can establish | What it cannot establish |
|---|---|---|
| Durable dispatch fence | This operation may have entered the native transport | Provider receipt, a charge or exactly-once delivery |
| Coherent reported token counts | Counts observed for this bound operation | Source relevance, answer correctness or an invoice |
| Complete native reserve/finish pair | The operation's journal was checked | Successful locator content or public feature readiness |
| USD reservation | Conservative admission provision | Actual spend, a refund or the whole batch's bill |
| USD estimate with rate-policy identity | Arithmetic on the admitted model's reported counts | Current retail pricing or provider invoice amount |

Money is a canonical nonnegative string with nine fractional digits; counts are
strict integers. The frozen engineering policy computes nanodollars as
`prompt_tokens * 573 + completion_tokens * 3440`, with explicit policy identity,
not floating-point approximations. A model mismatch may retain coherent token
counts but cannot use that model-specific price basis. Invoice status is always
`not_observed` in this version.

The page distinguishes reported complete use, reported partial use, unknown
outcome, positively observed no-dispatch and unavailable observation. Missing or
corrupt storage is not no-dispatch evidence. Unknown values are null, not zero.
Provider-reported counts are not independent provider attestations; USD estimates
must retain their rate basis and never be presented as invoices. Reservation
consumption is not the reported-use estimate or a refund calculation.

Receipt identity and saved-result validation remain blocking delivery checks.
Accounting-only damage shows an explicit unavailable state without hiding an
otherwise valid saved excerpt. Values are rendered as inert text, and small
nonzero estimates must not silently round to a displayed zero.

## Persistence and failure ownership

The accounting intent is persisted before any possible provider entry. A failed
initial reservation blocks that entry. The dispatch boundary means an operation
may have reached the provider; it does not prove receipt or billing there.

The actual operation thread finalizes accounting, including exception paths,
before its physical lease is released. A cancelled HTTP waiter cannot erase
native observations or authorize another request. Accounting and locator-result
persistence are separate outcomes: an accounting failure cannot erase a valid
saved result, and a receipt publication failure cannot become a claimed durable
success. In-memory usage is not a substitute for the native durable finish record.

GET and browser refresh never construct a native selector or call a provider.
Explicit receipt lookup uses the original authorization and reads persisted
observations only. Missing, pending, damaged or uncertain records cannot unlock
resubmission or manufacture a zero-cost outcome.

The separate `.saved-source-accounting-v1.sqlite3` is bounded to 5,000 records,
with an 8 KiB private-content-free stored record and a 4 KiB public projection.
It checks the parent receipt's expiry but adds no production cleanup/readiness
stage. GET is strictly read-only and does not prune expired rows; reaching the
store ceiling blocks new accounting rather than silently discarding history.
This prepared single-process store is not a distributed ledger, backup strategy
or complete production retention service.

## Verification scope and release boundary

Acceptance requires fake-key interception of the actual native HTTP path,
controller/store/POST/GET delivery and the shipped browser renderer. It includes
lost acknowledgements, same-question different-key isolation, partial or missing
usage, independent store/receipt failures, cancelled waiters and physical drain.
Critical regressions must make unchanged seam assertions fail when reinjected.

This round is offline engineering validation, not another paid canary or a
real-report effectiveness study. No private report is transmitted and no model
credential is needed. A real-data evaluation and public activation remain
separate gates. Rollback disables new execution, drains actual threads and keeps
authorized read-only recovery; it does not delete journals to permit a retry.

## Observed offline verification (2026-09-21)

After restoring all deliberate defect variants, the complete local zero-provider
suite passed **6,677 tests and 1,592 subtests**, against the 6,583/1,588 baseline.
Current Ruff and the project's narrow Pylint command passed over the full checked
source ranges. All six actual Chromium journeys passed, including the unchanged
production result/composer, original saved-source lab, legacy receipt page and
the intercepted RQ rehearsal. RQ's occupied native output was not reopened.

The new usage journey covered 13 scenarios: one disabled POST, one executed
loopback POST and eleven GETs. The executed request traversed the current native
transport with a fake key and an intercepted response, then the accounting
store, controller, HTTP envelope and shipped DOM. It observed one intercepted
native HTTP entry, zero external provider calls and one temporary daily admission.
Lost-ack refresh/recovery did not repeat the model path. Accounting faults kept
the valid excerpt while displaying an explicit unavailable state. The fee panel
precedes the potentially long saved excerpt and preserves tiny nonzero amounts.

Independent review found that the shared legacy JSON parser rejected a numeric
accounting value such as `0.0001261` before component-level fallback could run.
A raw-response regression reproduced the hidden-excerpt defect. A narrow opt-in
path hook now discards the entire accounting component when its numeric syntax
is invalid; the default parser still rejects the same token. Fractional,
exponential and unsafe numbers in the original receipt, duplicate members,
invalid JSON, depth and whole-response byte limits remain fail-closed. Seven
accounting raw-number cases and fifteen strict negative controls passed. The
new browser journey includes raw fractional and `1e0` accounting responses.

Seven separate reinjected defects made unchanged assertions fail and were
restored to their original source hashes: accepting a changed operation context,
skipping the pre-HTTP accounting fence, treating a failed native fsync as complete,
dropping delivered cost, displaying unknown as zero, automatic refresh dispatch,
and reverting the numeric-component reader fix. These are deliberate regression
controls, not seven observed production incidents. Independent final static
review found no remaining actionable issue; it did not execute the tests itself.

The backend boundary selection passed 111 cases including legacy regressions;
the HTTP/browser selection passed 204. These selections overlap the full suite,
not additional independent samples. A default-temp-directory ACL failure and
two separate fixture-isolation mistakes were corrected without skips, warning
ignores or weakened assertions. No real key or paid request was used in this
round. Cross-platform CI and normal deployment remain separate release gates.

The subsequent [RU offline preparation](prereg-2026-09-22-real-source-usage-offline.md)
binds real saved inputs for a future evaluation without activating this provider
path. Its scripted accounting is not another native observation or permission
to send the private packet to a model.
