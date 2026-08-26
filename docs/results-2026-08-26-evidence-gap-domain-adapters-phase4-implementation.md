# Result: Phase 4 domain evidence adapters — implementation only

**Date:** 2026-08-26

**Pre-registration revision:** `cd9cfe9`

**Protocol:**
[`prereg-2026-08-26-evidence-gap-domain-adapters-phase4.md`](prereg-2026-08-26-evidence-gap-domain-adapters-phase4.md)

## Outcome

The source-native OpenAlex and Lens adapters satisfy the frozen offline
implementation contract. They remain disconnected from both the production
worker and report evidence registry. No OpenAlex or Lens request was made for
this result, so provider compatibility, candidate relevance and novel-evidence
yield remain **not observed**.

The byte-frozen eight-case challenge expands deterministically in dry-run mode:

- 8/8 case recipes validated;
- four `academic_search` calls remained bound to OpenAlex;
- four `patent_search` calls remained bound to Lens;
- all collection, plan and idempotency identities were emitted;
- `production_connected=false`;
- `report_workflow_connected=false`; and
- `real_network_calls_performed=false`.

## Measurement before implementation

The preceding generic Tavily pilot had 25/25 completed returned labels but only
5/25 candidates marked directly relevant. Its academic and patent cases were
both 0/5. The review was formally ineligible because it declared substantive
generated judgment, but the descriptive 80% wrong-source rate was sufficient
to reject production connection and motivate a narrower provider experiment.

The existing production collector already contains OpenAlex and optional Lens
retrieval. Phase 4 therefore does not claim two new production data sources. It
implements separate one-request boundaries because the production clients own
retry loops, which would make the bounded executor's request accounting false.

## Implemented contracts

### OpenAlex

- one injected transport invocation equals one `GET /works` request;
- a live adapter requires `OPENALEX_API_KEY` and keeps it out of returned
  objects and request fingerprints;
- search, result limit and root-level selected fields are code-owned;
- `meta.cost_usd` is required and reaches the executor as provider-reported
  cost;
- the inverted abstract is reconstructed under token and position safety
  limits; no second-page abstract retrieval exists;
- malformed, non-object, missing-abstract and invalid-record rows are preserved
  as indexed provider rejections; and
- a provider that returns no request id is represented by a deterministic,
  secret-independent client identity explicitly labelled `client_generated`.

OpenAlex requires its key in a query parameter. Defect-injection output exposed
that chaining a low-level `URLError` could retain the complete credentialed URL
in a traceback even though the high-level error text was sanitized. The adapter
now suppresses that lower-level exception chain, and a regression assertion
formats the complete public traceback and verifies the key is absent.

### Lens

- one injected transport invocation equals one `POST /patent/search` request;
- the query searches title, abstract and the documented singular `claim` field;
- `LENS_API_KEY` exists only in the Authorization header;
- provider rows require a Lens id, localized invention title and usable
  abstract; claim text affects retrieval but is not mislabeled as an abstract;
- malformed and missing-summary rows remain indexed rejections; and
- because the response has no trustworthy per-request monetary value, accepted
  responses carry `cost_basis=uninspectable` and `search_cost_usd=null`, never
  a fabricated zero.

### Shared accounting and isolation

`ToolProviderUsage` now distinguishes:

- provider-owned versus client-generated request identity;
- credit accounting, provider-reported USD and uninspectable cost; and
- Tavily, OpenAlex and Lens provider contracts.

Every provider row must reach exactly one candidate or rejection index. The
existing executor then applies URL, host, evidence-domain, relevance and
deduplication quarantine without mutating the input collection. A seam test
confirms provider identity, cost state and accepted evidence reach the final
executor audit for both adapters.

The full suite initially failed because `OPENALEX_API_KEY` was not classified
at the BYOK environment boundary. It is now treated as an operator-billed
credential and scrubbed from visitor-funded subprocesses. The test was not
weakened: the newly read credential was added to the same deny-by-default table
that protects all other paid provider keys.

## Defect re-injection

Two pre-registered defects were reintroduced after the green targeted run:

1. an internal OpenAlex transport retry was added after a retryable failure;
   the no-hidden-retry test failed for OpenAlex while the Lens control remained
   green; and
2. both provider result-count and result-index coverage checks were disabled;
   the row-accounting test failed because the malformed response no longer
   raised.

Both mutations were then removed. Their targeted tests returned to green. This
demonstrates that the tests observe the request and artifact seams rather than
merely restating fields on a constructed object.

## Verification

- frozen dry-run: 8/8 identities, zero network;
- adapter/executor regression subset: 71/71 passed;
- BYOK plus new adapter subset: 42 tests and 2 subtests passed;
- complete zero-network suite: **1,488 tests plus 627 subtests passed**;
- latest Ruff: passed;
- CI Pylint exception-order/unreachable checks: passed; and
- coverage: **87.07%**, above the unchanged 85% floor.

The coverage run emitted inherited `ResourceWarning` messages from CrewAI
SQLite lifecycle paths. It emitted no `UserWarning`, did not reach a network or
paid fallback, and passed the existing warning policy. This result does not
reinterpret those warnings as adapter failures or hide them with a filter.

## Decision and next gate

The implementation is eligible to merge while disconnected. It is not eligible
for production Tool Calling.

A next experiment requires a separate preflight and explicit user
authorization before any request. It must bind to the exact fixture SHA-256
`f9eee1fcf2ff5acb75e9da840b94baa43e3b10f7e3136dec9886c3a572663a24`,
cap the run at eight requests, persist every row once, keep OpenAlex reported
cost separate from Lens uninspectable cost, and produce a schema-v2 human
review packet with visible baseline context. The frozen value gate remains
unchanged.

Only after that source-value gate passes would a planner-trigger study be
worthwhile. Until then, report generation remains phase-1 zero-call shadow mode.

## Supported claim

> A production-disconnected bounded Tool Calling executor now has strict,
> source-native one-request adapters for OpenAlex academic and Lens patent
> retrieval, with explicit request-identity provenance, non-fabricated cost
> states, row-complete quarantine auditing and BYOK credential isolation. The
> adapters pass offline implementation checks but have not yet made a live
> provider request or demonstrated candidate value.
