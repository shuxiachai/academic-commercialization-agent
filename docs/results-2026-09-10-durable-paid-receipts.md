# Durable paid-request receipts: offline boundary verification

Date: 2026-09-10. Starting public main: `207676fa3290ba1409821434877640b84664e99d`.
This is implementation and offline fault evidence, not a paid canary, observed
incident-rate estimate, provider billing reconciliation or automatic recovery.

## Measured premise and scope

The unmodified baseline passed 2,826 tests plus 1,230 subtests. Existing composer
locks/warnings prevented accidental tab-local overlap but could not retrieve a
lost acceptance. A real HTTP-to-`runs.start_run` regression reproduced two
distinct accepted run IDs for the same key before implementation. Its worker
launch was an offline substitute; no provider was contacted.

The committed 30-run benchmark cannot measure browser transport-loss frequency
or quantify duplicate billing. It was not re-run, modified or used to justify a
cost-savings percentage. Formula, confidence floor, frozen experimental sources
and zero-call production Tool Calling are unchanged.

## Contract and rejected alternatives

- A fresh cryptographic `Idempotency-Key` binds operation, normalized input,
  parent/PDF identity, owner and BYOK credentials. SQLite commits a reservation
  before admission and binds the intended resource before dispatch. Same intent
  replays acceptance; changed intent conflicts; unresolved work never relaunches.
- The random key is not stored server-side. Its SHA-256 locates the row; HMAC
  keyed by that capability binds payload/credentials without storing them.
  Code-owned lookup still requires the corresponding valid code; ownerless BYOK
  is explicitly capability-based. Raw keys never belong in URLs or logs.
- GET lookup is `no-store`, bounded in the client, and cannot POST/recover/cancel.
  It distinguishes accepted, failed, pending, unknown, expired and unavailable.
  A pending target is not proof of launch. A failed extraction may still cost money.
- Initial key timestamps are bounded to five minutes. Lookup/replay expire after
  24 hours, and expiry remains a rejection after pruning. This avoids an evicted
  old key being reinterpreted as fresh paid work. Active rows cap at 5,000.
  Cleanup is independently supervised, outside the ASGI loop.
- Existing empty/wrong-schema databases fail closed rather than auto-recreating
  an apparently empty ledger. Claims are transactional; unreadable storage fails
  before admission and is exposed by readiness.
- PDF completion belongs to the actual extraction thread. It commits a minimal
  receipt after derived metadata is saved, retains completed metadata after waiter
  cancellation, and deletes raw PDF bytes. A queued abandoned job performs no
  extraction. Legacy unkeyed abandonment retains its original cleanup behavior.
- The browser persists only key/operation before fetch. Refresh can recover the
  key, read the receipt and hand the result to the real UI. Logout/identity changes
  invalidate prior receipt views. Denied storage remains visibly memory-only.

We rejected automatic resend, replacing unknown with failed/free, caching PDF
excerpts in a second store, and using the browser warning as proof of backend
idempotency. A new explicit key is a new paid intent, not recovery of an old one.
Legacy clients without the opt-in header remain non-idempotent.

## Verification

After implementation: **2,884 tests plus 1,230 subtests**, **89.16% Python coverage**
on Windows/Python 3.12.9; the floor remains 85%. Provider calls: zero. Node
assertions are exercised but are not represented by the Python line percentage.

Behavioral tests cover API/Popen/admission for root runs and recovery children;
PDF replay, changed bytes, expiry and queued/running cancellation; concurrent
duplicates; changed input/credentials; code-owner lookup; missing, corrupt, full
and wrong-schema journals; readiness and independent cleanup; new-process reads
and surviving committed acceptance; OpenAPI headers; actual JavaScript fetch
headers, fresh contexts, unknown/mismatched responses, identity changes and GET timeout.

Real Chromium adds three refresh-to-lookup-to-view journeys: analysis, PDF and
recovery child. Composer counts are 12 original POSTs, five identity POSTs, six
warning-refresh POSTs and three receipt POSTs: **26 intercepted POSTs total,
zero API POSTs reaching the static server, zero provider calls, zero unexpected
requests and zero page errors**. The separate read-only Chromium result journey
also passes with zero mutation attempts.

Eleven temporary defect variants required the named target assertion to fail,
then were restored with matching source SHA-256:

1. Bypass reservation, creating a second worker.
2. Omit pre-launch target binding, losing the durable crash pointer.
3. Bypass code-owner isolation.
4. Ignore changed payload/credential fingerprints.
5. Discard a completed receipted PDF after waiter abandonment.
6. Accept expired keys as replayable work.
7. Omit the actual outgoing client header.
8. Omit the pre-fetch tab journal.
9. Fail to publish pending receipt controls.
10. Omit receipt-view invalidation on identity change.
11. Recreate the schema for a pre-existing empty journal.

Reinjection exposed a weak test: an assertion inside fake fetch was swallowed
by the intentionally expected network-error wrapper. The corrected test observes
the invocation and asserts outside that wrapper; it now fails when the header is
removed. Chromium also caught a genuine rendering seam: the key was saved after
the old warning notification, leaving lookup hidden during a stalled request.
The UI now republishes before fetch. No assertions were relaxed, no warning
filters were weakened and no skips were added.

## Limits that remain

This is a single-process acceptance journal, not provider exactly-once,
cross-replica ownership, automatic checkpoint resume or end-to-end accounting.
Crash between dispatch and completion leaves an unresolved reservation; its
target may or may not have started. We do not assert zero paid duplicates across
distinct keys, deleted/restored journals, lost volumes, old backups or compromised
storage. Disk loss is not repaired by this protocol.

Tab close, storage deletion/denial, logout, changed origin or lost capabilities can
remove lookup ability. Receipts expire after 24 hours; paper retention/deletion
can expire an accepted result earlier. SQLite expiry is not backup/media erasure.
Keep the journal on the existing persistent volume and do not remove it while
serving requests. Historical reports, experiments and manual-review provenance
remain unchanged. No live paid request or manual Railway restart was performed.
