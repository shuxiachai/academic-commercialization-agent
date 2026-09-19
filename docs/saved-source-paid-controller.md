# Prepared saved-source admission and receipts

This is a default-disabled backend controller for the isolated saved-source
locator. It is not connected to `api.main` or any native provider. A separate
[receipt entry](saved-source-receipt-entry.md) wraps it in its own isolated HTTP
app/browser. It accepts no BYOK key and does not discover a provider credential.
The original lab remains an injected-callback demonstration without billing.

## Why a separate receipt

The existing paid receipt journal has explicit run, resume and paper resource
and response contracts. Relabeling a source-location request as one of those
operations would make recovery lie about what was accepted. This controller uses
a separate versioned locator journal while sharing the existing `api.runs`
capacity and operator-funded daily operation ledger in the same process.

Before changes, the complete suite passed 6,252 tests and 1,570 subtests.
Read-only prescribed-ID replay of 30 current local source registries delivered
632 saved texts; the largest canonical locator result was 7,770 UTF-8 bytes.
This measured a storage/delivery premise, not model selection quality, original
benchmark identity or an all-input response-size bound. No private input was
published and no provider was contacted.

## Identity, execution and observation

A report ID is a read capability, not permission to spend operator funds. Every
controller execution and receipt lookup requires a currently valid access code,
including when the legacy global gate is unconfigured. The payer is derived from
the verified code, never from a client-supplied owner. This deliberately narrow
preparation also requires the report's readable owner marker to match that
identity before execution. Shared read links, ownerless BYOK reports and another
owner's report cannot select operator funding. An admin can inspect another
owner's receipt but cannot use that read privilege to execute as that owner.
BYOK remains a separate future credential contract.

`SavedSourceController(load_snapshot, journal_root, selector=None,
selector_identity=None)` has asynchronous `execute(key, run_id, question,
access_code)`, `lookup(key, access_code)` and `close()` methods. A trusted injected
selector needs an explicit configuration identity; this string is not an
independent attestation of the callback or its model. Disabling execution keeps
lookup available for already-recorded outcomes. The controller itself has no
HTTP mapping; the separate receipt entry preserves its full observation contract.

A receipt reserves the intent before work can reach shared admission. Its
keyed fingerprint binds the exact question, report ID, payer and selector
identity without storing the question, code or random receipt key. Execution
then binds the detached source snapshot before selector entry. The first actual
selector entry uses the shared capacity and daily ledger. Loading failure,
thread-start failure, abandonment before admission starts and a no-callback
result do not consume daily allowance;
failure after admission does not justify an automatic refund.

Dedicated-thread ownership survives a cancelled async waiter, result validation
and receipt publication. A slot is not free merely because the callback or HTTP
waiter returned. Shutdown rejects new work and drains actual threads outside the
event loop; a stuck trusted callback cannot be safely killed and has no promised
bounded shutdown. Callbacks remain trusted Python, not a sandbox.

Committed completion and failure are immutable. Duplicate intent observes or
replays the existing record without another selector call or daily charge.
Unresolved work whose owner has disappeared is unknown, not free, failed or
permission to start again. Shared admission and journal writes are not one
cross-store transaction: a crash can leave consumed admission with unknown
provider spending.

Only one new dedicated operation thread per controller may be active, including
pre-admission loading and post-target exit. Existing-intent observation remains
possible while occupied. Cancellation before the admission-start decision
abandons queued work; after that decision it cannot retract accounting or
dispatch. This boundary is explicit rather than equating cancellation with a
provider refund.

## Saved-text retention and replay

The locator journal stores a bounded projection of source IDs, hashes, original
outcome and execution counters, not another copy of titles, URLs or excerpts.
Delivery reconstructs the original result from the unchanged saved snapshot and
checks the original canonical result digest. It does not invoke a fake selector
to manufacture historical callback facts. Replay reads are delivery, not a new
model execution.

Receipt completion means that a validated locator outcome was recorded, not
that an excerpt exists or semantic support passed. The original result's
`state` and `reason` remain visible, including declined, unavailable and failed
locator outcomes. Provider usage and cost are explicitly `not_observed`;
admission quota is not a token or dollar estimate.

Deleted, changed and unreadable source data must remain distinguishable. A
completed receipt can survive while its deliverable is no longer available;
that cannot trigger selection again. Receipt expiry and pruning never turn an
expired key into a new intent. Corrupt or wrong-version storage fails closed,
rather than silently recreating an empty journal.

The new `.saved-source-receipts-v1.sqlite3` has its own schema, a 5,000-record
ceiling and a 4 KiB reconstruction-projection limit. New keys have a five-minute
admission window and expire after 24 hours. Claim-time pruning and an explicit
prune method exist; production maintenance/readiness do not inspect this
unconnected journal. Time expiry is not backup or filesystem erasure.

## Verification and remaining boundary

Acceptance requires zero-provider tests through the actual shared admission
and durable journal: competing operations, duplicate requests, source and intent
changes, identity revocation, abandoned waiters, thread-exit windows, restart
observation, expiry and storage faults. Re-injected defects must make the named
regressions fail before the exact fix is restored. Complete regression, latest
Ruff, narrow Pylint and independent review remain release gates.

These tests do not enable production Tool Calling. The separate HTTP/browser
receipt entry has its own delivery tests; a native adapter with fresh credential
and cost bounds, plus explicit activation/data-transfer authority, remain separate.
Capacity is shared only inside one process; this is not distributed scheduling,
provider exactly-once execution or a statement of user benefit. Rollback must
disable new work, drain threads and preserve the journal, not delete it to retry.

## Observed review and regression

The initial new backend tests passed 70 cases; the combined new and existing
boundary selection passed 406 cases plus 30 subtests. Four deliberate defects
each made a named regression fail: bypassing daily admission, bypassing duplicate
intent observation, ignoring the original result digest and freeing a thread
lease before physical exit. Each original file hash was restored afterward.

Independent static review then found two faults not caught by those green tests:
a replay that attempted a read and failed later could report zero delivery
reads, and invalid UTF-8 in an owner marker escaped the safe denial boundary.
The corrected tests compare actual reader calls on failing paths and require a
safe denial with no journal, loader, thread, selector or quota activity for the
damaged owner marker. These are engineering observations, not a provider canary.

Both fixes passed targeted independent re-review. Reintroducing lost failure-path
read counts made four parameter cases fail; removing the decode-error boundary
made its safe-denial case fail. Both mutations were restored to the reviewed
source digest, and the final new backend selection passed 73 cases. Together
with the original four mutations, this is six defect variants producing nine
expected assertion failures, not nine observed production incidents.

The unchanged production result and composer Chromium journeys passed, as did
the isolated lab's one disabled request and fifteen scripted POSTs. Their
external/provider call counts remained zero. This does not make the prepared
controller reachable from any of those pages.

After restoring all reviewed fixes, the complete zero-provider suite passed
6,325 tests and 1,574 subtests. Latest Ruff and the project's narrow Pylint
checks also passed. Cross-platform CI and deployment verification remain
separate release observations rather than claims established by that local run.
