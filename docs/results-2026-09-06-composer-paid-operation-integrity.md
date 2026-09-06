# Composer paid-operation and configuration integrity

Date: 2026-09-06. Base: `495431d0ae164d0575ae95b63a5b75ea36e4299d`.
This is deterministic maintenance, not a paid canary or a source-quality study.

## Measured defects

The unmodified full suite passed 2,291 tests and 1,156 subtests using a fresh
Windows temporary directory. Read-only production checks found healthy endpoints
and matching deployed assets. No production run or upload was submitted.

Execution of the shipped client with delayed synthetic responses reproduced:

- A pending run POST could be followed by another after an input event re-enabled
  the button. Two outgoing requests were observed, not two observed paid bills.
- PDF success with a pre-existing topic left Run disabled. Empty-topic auto-fill
  was a working positive control, so this was not a general PDF pipeline failure.
- Two overlapping extractions could resolve out of order and attach the older
  paper. Finishing one also cleared the single extraction flag too early.
- Explicit `LLM_PROVIDER=qwen` with no LLM key, or an unknown selector, returned
  `200 / ready=true` in an isolated readiness HTTP replay. Auto-selection with no
  key correctly returned 503. This is not evidence of missing production keys.

Code/UI inspection also found that every submit-time 429 was displayed as two
busy slots, although daily quota and rate limiting share that status and deployed
capacity was five. The homepage promised a citation for every claim and described
the six roles as the collectors, exceeding the established workflow contract.

## Changes and limits

1. A tab-local submission lock survives input events and guards the event handler
   as well as disabled controls. Submitted controls are frozen while waiting.
   Rejection releases the lock; acceptance clears the composer and opens the
   accepted run. There is no automatic POST retry, cross-tab deduplication or
   persistent idempotency key. A lost acknowledgement still has unknown outcome.
2. PDF extraction is serialized, including drop/change events. A second request
   is refused locally, rather than aborting fetch and pretending the paid call
   stopped. A selection generation rejects stale responses; invalidation alone
   does not release physical in-flight work. All settlement paths synchronize
   controls, preserving existing topics and empty-topic suggestions.
3. Readiness and operator SDK construction share credential alias resolution.
   Unsupported providers and absent/whitespace-only selected credentials fail
   before SDK construction. Qwen/DeepSeek retain legacy OPENAI_API_KEY fallback.
   The public projection contains no key, and no health probe contacts a provider.
   Explicit BYOK routing, empty sentinels, models and endpoints are unchanged.
4. Additive X-Error-Code headers distinguish concurrency, daily quota and rate
   limits while retaining string detail and HTTP status. All three paid endpoints
   preserve admission reasons; the browser translates recognized reasons and
   leaves unknown/legacy details intact. Quota accounting itself is unchanged.
5. English/Chinese homepage copy describes retrieval before the six-stage workflow
   and visible references, gaps and limits, not universal citation correctness.

Server-level idempotency was not added as an incidental extension: it requires
actor scope, durable reservations and uncertain-outcome handling, especially for
ownerless BYOK. A button lock must not be marketed as exactly-once billing.

## Regression evidence

Node tests execute shipped app handlers and the actual fetch client, asserting
request counts and paper IDs in the POST body. A static-only loopback server plus
real Chromium covers existing-topic attachment, overlapping input, pending submit,
accepted-run navigation, auto-fill, extraction rejection and bilingual UI reasons.
It fulfills seven synthetic POSTs inside the browser: zero API requests reach the
server, zero external/unexpected requests, zero provider calls and zero page errors.
The original read-only production-ASGI browser journey remains separate and passes.

Seven defect re-injections trigger their intended assertions: duplicate submission,
missing PDF unlock, overlapping uploads, stale attachment response, detection-only
readiness, dropped HTTP error classification and the old homepage overclaim.
An early Node test waited for a duplicate response before counting requests; its
mutation exposed that weak test and the assertion was moved before the await.
The first restoration pass also exposed an ambiguous patch target between liveness
and readiness; final re-injections use identifying context and verify every restored
file's SHA-256 equals its pre-injection bytes. No weakened assertion or skip was used.

After all fixes and documentation links were restored, the complete suite passed
**2,323 tests and 1,161 subtests**. The local Windows/Python 3.12 coverage run
measured **88.48%**, exceeding the unchanged 85% floor; this is not a CI figure.
Latest Ruff and the CONTRIBUTING narrow Pylint command passed. CI
retains its existing four OS/Python cells, coverage floor, lint, Docker and both
browser journeys in the single Chromium job. Counts are revision-specific, not
report accuracy or evidence of a live paid operation.

This work changes no scoring formula, evidence screen, retrieval source, frozen
experiment bytes, CrewAI version, provider model, reviewer data or production
Tool Calling gate. It does not establish monetary savings, deployment SLOs or
semantic report correctness.
