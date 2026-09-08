# Document-scoped access identity across tabs and late responses

Date: 2026-09-08. Base: `66cfdbcab71673fd9fb05c89ff2b5ec5096254d3`.
This is offline client-boundary maintenance, not a paid experiment or evidence
that a real visitor incurred a wrong-account charge.

## Measurement before implementation

The unchanged baseline passed **2,619 tests and 1,196 subtests**. Two synthetic
replays executed the shipped HTTP client against shared in-memory storage and
held responses. After tab A selected code A, another tab stored B: A's next
paid request sent B. A later 401 also erased a newer stored C. The new seam
tests failed on the submitted header and persistent selection respectively.
No provider or production mutation was involved. Existing report artifacts
cannot establish browser tab histories or the frequency of this race.

## Changed contract

- A document snapshots the shared access code on its first read. Only an
  explicit local selection changes it. Another tab's login/logout no longer
  silently changes the payer, history identity or mutation header of an open
  document. A fresh document still reads the persisted selection.
- BYOK remains session-scoped with per-request schema validation. It is not
  frozen with the shared code, and malformed BYOK cannot fall back to operator
  billing. No provider identity, admission rule or server authorization changes.
- A 401 clears only the current selection that actually sent that header.
  Candidate checks and late responses cannot erase a newer choice; a generation
  also distinguishes A -> B -> A from the original A request.
- Clearing the code first clears this document's memory. If persistent storage
  contains a different selection, it is preserved and logout returns to the
  gate without reloading into that other identity. A bilingual notice separates
  this conflict from unavailable storage. Attachment/context clearing and the
  existing paid-acknowledgement wait remain intact.

## Verification

Seventeen added zero-network tests cover all three paid entrypoints plus history
and delete, current/candidate/late/ABA 401 responses, another tab's logout,
denied reads/removals, and the actual app logout handler. Assertions inspect
outbound headers, retained storage and DOM/gate/reload effects, not just fields.

Real Chromium runs a separate two-tab journey with five intercepted POSTs:
PDF -> run -> recovery under A while B signs in, a delayed 401, explicit A
reselection and B's subsequent request. This is in addition to the unchanged
12-POST composer journey. No API request reaches the static-only server, no
unexpected/external request is accepted, and no provider is called. The
independent read-only browser journey remains zero-mutation.

Five defects were re-injected individually: repeated shared-storage adoption,
unconditional persistent removal, candidate-response clearing, missing selection
generation, and logout reloading after a conflict. Each failed at its intended
request/storage/reload assertion; each edited source hash was restored before
final checks. Full pytest/coverage, latest Ruff, narrow Pylint and both browser
journeys are required; CI retains the unchanged 85% coverage gate and warning
policy. No assertion was weakened and no skip was added.

Final local Windows / Python 3.12.9 verification: **2,636 passed and 1,201
subtests**, Python coverage **88.89%**. The coverage denominator is `src`,
`api` and `ui`, not JavaScript coverage; the actual JS and browser contracts
above provide separate evidence. CI supplies its own platform-specific counts.

## Limits and next boundary

This is selected-identity protection, **not cross-tab deduplication, global
logout, transactional browser storage, server idempotency or provider
exactly-once delivery**. The compare-before-remove is not a cross-document
transaction; truly simultaneous persistent updates are not serialized. Open
documents keep their prior code until explicit local selection or a relevant
401; revoke a code on the server if all documents must lose authorization.

A refresh, close or crash can still lose a paid acknowledgement. There is no
durable client receipt journal or automatic safe resubmission. The logout guard
protects its own reload, not arbitrary browser navigation. Investigating a
credential-free pending/unknown receipt and its explicit user acknowledgement
is separate follow-up work; this patch neither retries paid POSTs nor claims
that aborting fetch cancels server/provider work. No extra paid canary, Railway
restart, scoring change or production Tool Calling activation was performed.
