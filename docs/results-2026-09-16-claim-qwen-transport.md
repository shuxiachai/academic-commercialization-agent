# Claim-relative Qwen transport: intercepted wire verification

Date: 2026-09-16. Engineering-only result for the separate
[wire preregistration](prereg-2026-09-16-claim-qwen-transport.md), committed as
`eaea307` before implementation. No provider requests, real-key reads, semantic
accuracy claim, historical relabeling or production activation occurred.

## Implemented seam

The new `ClaimQwenLedger` and `ClaimQwenFollowupTransport` bind a detached,
revalidated snapshot and verbatim caller proposition before the first request.
They have their own offline manifest and session implementation. Only pinned
HTTP, credential, accounting and validation primitives are reused; the old
catalog adapter and frozen claim wrapper are unchanged.

The actual request must preserve the ordered catalog, visible-ID schema,
original native assistant tool call and complete paired local read result.
Expected-result construction is comparison, not a second tool read. Matching
source/snapshot hashes alone cannot legitimize substituted text, offsets,
receipt IDs or a false claim of missing evidence.

Nonempty initial requests use native auto tools. Empty or read-completed
stages omit tools and use JSON Object, with the original four-field claim
declaration returned unchanged. The wrapper, not this transport, validates
relations and derives delivery. A structurally admitted HTTP reply can still
fail the wrapper; a future batch runner must handle that as failure.

The exact final encoded body must fit 12,288 bytes before reservation, and the
journal hash must equal dispatched bytes. Callback entry is not HTTP dispatch.
Two requests/one read, pinned `qwen3.5-plus`, non-thinking output, no redirects,
retry or fallback, secret scanning, unknown-usage reservation and durable
intent/finish rules remain in force. None grants another paid allowance.

## Offline controls and mutation evidence

- Before-change complete suite: 4,637 passed / 1,401 subtests, 269.19 seconds.
- 88 new fictional controls exercise the real wrapper, local executor, actual
  adapter and intercepted HTTP. Coverage includes all four relations,
  positive/negative propositions, late visible IDs, Unicode/blank/missing
  reads, strict native declarations, forged histories/results, exact and
  over-limit wire bodies, credential echoes, response/model/usage errors,
  deadline handling and reserve/finish persistence failures.
- Restored new/old focused regression: 784 passed, 9.31 seconds. Latest Ruff
  0.16.7 passed; repository-wide Ruff and narrow Pylint also passed.
- Four separate defect reinjections each produced the intended first failing
  assertion under `-x`: lost first-claim admission dispatched one HTTP instead
  of zero; lost final-wire bound dispatched a second over-limit HTTP;
  post-reservation byte mutation broke journal/wire SHA equality; lost full
  result comparison sent forged text downstream. These are four targeted
  failures, not exhaustive mutation coverage. Each mutation was restored to
  the identical source hash before the green focused regression.
- An independent read-only LLM reviewer inspected the frozen implementation,
  tests, relevant reused dependencies and guides and found no actionable
  finding. It did not execute tests or verify semantic correctness; supplied
  execution evidence was distinguished from its static inspection.
- All 67 pre-existing tracked files in the frozen inspection inventory retained
  their before-change hashes. The inventory covers existing follow-up modules,
  tests, fixtures/protocol records, selected canaries and dependency files;
  this is not a claim that every repository file is cryptographically frozen.

The default pytest temporary-directory permission error was resolved by using
a fresh workspace temporary directory. A parent probe's initial hash comparison
mistook uppercase/lowercase hexadecimal for differences; normalized comparison
confirmed no changes. Neither event was hidden as an application test pass.
Full-suite and CI outcomes for the final documented tree are recorded separately
against the resulting commit, not inferred from the focused controls above.

## Existing-snapshot capacity replay

The parent projected 30 existing benchmark snapshots with 632 source rows,
used one fixed invented proposition, selected the first visible source
positionally and read up to 1,500 code points. Scripted model replies declared
insufficiency/unavailability. All 60 requests reached `httpx.MockTransport`
through the new adapter, and every reserved and finished request hash matched
the actual wire. First bodies measured 5,769--6,685 bytes; final bodies measured
6,838--8,731 bytes. None exceeded 12,288 bytes. All conversations abstained,
and semantic-support/answer-verification flags remained unverified.

No saved text left the machine. Probe journals remain local and are not
published. These observations demonstrate capacity and byte/accounting seams
for this scripted selection, not model selection quality, source truth,
historical benchmark CSV identity or arbitrary maximum-size inputs. The latter
limits have separate synthetic exact/over-boundary controls.

## Limits and next gate

This is network-capable library code, not a live runner, authentication gate or
production endpoint. Its manifest declares `live_authorization=False`; calling
it outside intercepted tests still requires applicable separate authority.
It remains single-owner and is not a thread-safe shared client. Valid receipt
and JSON relationships do not establish entailment; wrong but structurally
legal judgments retain the explicit unverified semantic status.

The next gate is a newly frozen bounded native experiment and explicitly
identified independent LLM semantic review, not a human-review prerequisite.
Closed CQ/RS budgets, runners and result identities cannot be reused. Private
real-run results remain outside this publication; no scoring formula,
production Planner or historical human declaration changed.
