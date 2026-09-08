# Paid-request refresh warning boundary

Date: 2026-09-08. Baseline: public main
`4b61c294b31762d17576e23e2c6642eb0cf26626` (PR #126).

## Observed defect and scope

The existing composer prevented duplicate clicks and waited for paid replies
before logout. Those locks existed only in the current JavaScript document.
An offline execution of the shipped app/API with held fetch responses sent
one POST in the first document and another POST in a fresh document. No real
socket, model or search provider was involved. This is a reproducible boundary
failure, not a measured production duplicate-billing rate. Stored benchmark
reports cannot measure this browser lifecycle failure.

The fix covers the first-party analysis, PDF extraction and resume handlers.
It does not change server admission, provider configuration, scoring, recovery,
or production-disconnected supplementary Tool Calling.

## Contract

- Before paid dispatch, write one constant marker to tab `sessionStorage`.
  No credentials, payloads, topic/file names, run IDs or capability links are
  stored in this marker. Presence, including malformed values, means an
  unconfirmed prior outcome on a fresh document.
- A persistent bilingual warning blocks all three new paid dispatches until
  explicit risk acknowledgement. Read-only history/status remains available.
  Acknowledgement itself sends no request and does not cancel, retry, recover
  or verify any prior operation. Dismissing confirmation leaves the block.
- JSON parsing alone is not delivery. Successful run/resume responses require
  a nonempty run identity and a completed view handoff; PDF responses require
  a paper identity and attachment handoff (or an explicitly discarded selection).
  Optional history failures cannot prevent following an accepted run.
- Transport loss, malformed success, 408, 5xx and handoff failures retain the
  warning. Definite non-408 4xx rejections release the intent, but do **not**
  establish zero cost: PDF validation can follow extraction.
- Overlapping requests settle individually. One success or an old duplicate
  callback cannot erase a peer uncertainty or a newer request. In-flight
  requests cannot be released with the acknowledgement button.
- `beforeunload` requests a native warning only while awaiting delivery. It is
  best effort and never sends a cancellation, retry, or beacon.
- Denied storage retains memory-only operation and displays explicit unavailable
  observation/persistence. A removal failure cannot undo successful delivery;
  a leftover marker may conservatively warn again on reload.

## Verification

The clean baseline passed 2,636 tests and 1,201 subtests on local Windows /
Python 3.12. New Node tests execute the actual app/API with held responses,
fresh document contexts and shared session bytes. They cover each paid route
against refresh, transport failure, malformed success, handoff failure, 408,
500, 401, 422 and 429; additional contracts cover delivery ordering, storage
denial, URL-history failure, overlapping settlement and stale callbacks.
The old exact-await spelling test is backed by the actual resume/rerender
request-and-child-delivery regression, not replaced with a weaker assertion.

Real Chromium adds three forced-reload cases to the existing composer journey:
six new intercepted POSTs, with twelve existing composer and five identity
POSTs retained. The static-only server has no paid API; all API requests are
intercepted, unexpected traffic fails the audit. Final clean execution observed
zero API requests reaching the server, zero provider requests and zero page
errors. Orphaned interception cleanup is explicit, not a warning suppression.

Eight defect re-injections each produced the intended `AssertionError`:

1. Discard the saved marker at boot.
2. Dispatch without first persisting intent.
3. Erase transport uncertainty.
4. Release the marker before view handoff.
5. Bypass the new-dispatch guard.
6. Let one success erase a peer uncertainty.
7. Acknowledge an in-flight request.
8. Accept a success response without its paid identity.

Each final mutation restored the exact source SHA-256; the targeted 55-test
suite passed afterwards. The final local full suite passed 2,667 tests and
1,206 subtests; fresh Python coverage was 88.89% (85% floor retained). Latest
Ruff, narrow Pylint and both Chromium commands passed. Python coverage does
not measure JavaScript line coverage. CI/deployment evidence belongs to the
resulting PR and commit, not an inferred success from this text.

## Limits and non-goals

This is a tab-session **warning marker**, not durable receipt recovery, server
idempotency, global logout, or exactly-once provider billing. A new tab/session,
cleared storage, denied storage, direct API calls or a modified client can bypass
it. A cloned tab may inherit a conservative warning. BYOK history may never
have received the lost run ID; PDF extraction has no recovery history. A lost
response is not reconstructed. Confirming risk may still lead to another charge.
No new paid canary or manual Railway restart was used for this change.
