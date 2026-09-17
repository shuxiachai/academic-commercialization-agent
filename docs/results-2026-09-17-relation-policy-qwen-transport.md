# Relation-policy native wire: separate delivery and accounting

Date: 2026-09-17. Offline engineering successor to the
[RP callback layer](results-2026-09-17-claim-relation-policy.md).
Protocol commit `0390617` registered the
[wire acceptance rules](prereg-2026-09-17-relation-policy-qwen-transport.md)
before implementation. PCQ/CLQ failures and all frozen predecessors stay unchanged.

## What changed, and why

The new positional-request adapter binds a detached trusted snapshot, the
verbatim caller claim and the frozen explicit relation policy at construction.
It compares both stages' complete system/catalog/claim, the accepted native
assistant call and the complete deterministic tool result. A matching receipt
hash alone cannot admit substituted text, scope or a fabricated missing result.

A new exact-type ledger has an independent manifest with policy hash and
offline scope. Only frozen key/HTTP/accounting and pure validation helpers are
reused. The old claim/catalog native adapters are not wrapped or patched.
Limited duplication preserves their frozen experiment identities.

The initial nonempty catalog allows one visible-ID read. After that, or for an
empty catalog, the native body omits tools and uses final-only JSON Object.
The native final content is returned unchanged; the frozen claim wrapper owns
strict final parsing and relation/receipt consistency. A valid but wrong
semantic relation is not repaired in Python.

## Three delivery observations

1. The frozen inner result describes delivery to the policy bridge.
2. RP audit entries describe entry into the positional native callback.
3. The native journal describes reserved wire intent and observed HTTP outcome.

These are not interchangeable. RP can admit a read to the callback, while
the complete HTTP body is over budget and never dispatched. No callback fact
is backfilled into the inner result or promoted to provider delivery.

After all stage transformations the canonical HTTP JSON body must fit 12,288
bytes. Reserve that body durably, then send the same immutable encoding.
Headers are outside this JSON-body bound. The journal's request hash must match
actual intercepted content, not merely another object constructed in a test.

Unknown usage retains the reservation and stops. Known usage survives invalid
responses; failed finalization leaves unresolved intent. Raw/escaped secret
echoes are refused before transcript persistence. The code exposes safe failure
categories rather than exception content.

The fixed endpoint/model, TLS/no-proxy/no-redirect/no-retry HTTP behavior,
token/response/time limits and inherited accounting ceilings are unchanged.
They are not new paid authority, current price promises or a network sandbox.
No CLI, live batch, production route, merge or deployment is added.

## Verification record

Baseline: 5,195 tests / 1,448 subtests passed in 291.45s before edits.
The free pre-edit replay projected 30 snapshots / 632 sources and reached
60 RP callbacks. Initial callback bodies were 6,944-7,860 bytes; final callback
bodies were 7,983-9,876. No HTTP was involved in that first measurement.

The new focused suite passed 154 tests after restoration. It uses actual RP,
the frozen local read executor, the new adapter, inherited HTTP posting and
MockTransport. Eight frozen RP controls each receive a fresh ledger; labels
and reference rationales are not sent as instructions. A valid but semantically
wrong relation remains unchanged.

Five actual mutations were applied only to the new source and independently
restored to the same SHA-256. Valid downstream scripted responses ensured
these failures were not missing-mock accidents:

| Removed or injected defect | Targeted failures | Observed failed seam |
|---|---:|---|
| Omit complete system/policy admission | 10 | One/two HTTP requests instead of zero/one |
| Omit initial claim admission | 1 | Changed first claim dispatched |
| Omit final wire ceiling | 1 | Precheck passes; 12,289-byte final body reserved and sent |
| Append a space after reservation | 8 | Journal hash differs from actual HTTP bytes |
| Omit complete read-result comparison | 8 | Forged result reaches a second HTTP request |

Each restored full focused run passed 154 tests (3.08-3.31s). These intentional
red controls establish the particular regression assertions, not exhaustive
mutation coverage or semantic accuracy. Restored source SHA-256:
`9b1a79953efacc1c4d5516d98430e25be545a8be87fd8c4cc5bbb1fe26463d53`.
Test file SHA-256:
`acdf3984374fbe297b7438a6600cb3fdea59007a9f543234bb407ba01750b50f`.

Development also corrected test-harness issues rather than ignoring warnings
or widening product limits: a temporary-directory ACL, Windows asyncio's
stdlib self-pipe, an already-over-limit unpadded probe and an incorrect
assumption that native content plus a tool call must be invalid. Each had one
failed attempt. A separate parent diagnostic reproduced the self-pipe cause:
unconditionally blocking socket.connect prevents Windows loop construction.
The guard now permits only the synchronous stdlib socketpair loopback operation,
not arbitrary local/external connections. Provider HTTP remains intercepted.

The post-implementation replay used the same 30 local snapshots / 632 sources
and short invented claim, with 60 intercepted native requests and 60 matching
journal hashes. Initial full bodies were 7,067-7,983 bytes; final full bodies
were 8,136-10,029. All fit 12,288. Replies and usage were scripted; no project
provider was contacted. Raw saved material and probe journals stayed ignored
locally. This does not establish capacity for arbitrary maximal inputs.

All 134 files in the pre-edit frozen inventory retained their hashes. This
covers selected old protocols/results, fixtures, follow-up source/tests and
dependency files, not the whole computer.

The seven files in the closed PCQ native output directory also retained
their hashes. No old experiment was retried or rewritten.

The final full zero-provider suite passed 5,349 tests / 1,456 subtests in
276.87s. Repository-wide Ruff 0.16.8 and the prescribed narrow Pylint passed;
no assertion weakening, warning suppression or skip was added.

A different requested route_reviewer / gpt-6-astra / high context found no
actionable issue in the stable source/tests and boundaries. It checked file
identities and test mechanisms statically; it did not run tests or provider
requests. Mutation numbers came from the implementation expert and the full
suite/capacity observations from the parent. Effective backend model metadata
is unavailable. Exact-commit CI outcomes belong in the pull request, not an
inferred pass from these local checks.

## Limits and next gate

The eight RP controls are dependent synthetic development cases with
context-limited LLM reference review, not new unseen data. Scripted HTTP
responses exercise real request/receipt/accounting paths, not model inference.
All runtime semantic flags remain unverified.

This phase makes no project-provider calls or real-key reads. Locally replayed
saved text is not disclosed, and raw private journals are not published.
A later native experiment requires a new frozen runner, identity and output
under applicable bounded authority. No occupied batch is reopened. Native
compatibility, relation correctness, unseen validation and production admission
remain separate; this stage establishes none of the latter three.
