# Result: Phase 4 domain live value-study harness — implementation only

**Date:** 2026-08-26

**Pre-registration revision:** `3c1126c`

**Protocol:**
[`prereg-2026-08-26-evidence-gap-domain-live-phase4.md`](prereg-2026-08-26-evidence-gap-domain-live-phase4.md)

## Outcome

The production-disconnected live runner and Schema v2 human-review path now
implement the pre-registered Phase 4 measurement boundary. The default command
is still a zero-network dry-run. No OpenAlex or Lens request was made, no live
provider credential was consumed, and neither the runner nor the review module
is imported by the production worker.

The implementation is ready for a separately authorized frozen provider run;
it does **not** establish provider compatibility, source relevance, novelty,
planner precision, report improvement, production utility, or production Tool
Calling readiness.

## Live execution boundary

The runner now:

- verifies the byte-frozen eight-case fixture and three frozen implementation
  files before constructing a provider adapter;
- requires both provider credentials, a positive OpenAlex soft stop no greater
  than USD 0.05, explicit acknowledgement that Lens cost is uninspectable, and
  a new output directory before the live path can begin;
- persists the complete expanded collection, validated plan, collection hash,
  plan hash and implementation hashes before the first request;
- permits exactly one outbound request for each attempted case and no more than
  eight requests across the study;
- commits one write-once case journal before a later request may begin;
- isolates provider failure and the OpenAlex soft stop so one provider cannot
  erase the other provider's audit trail;
- keeps OpenAlex provider-reported USD separate from Lens `uninspectable` cost;
  and
- projects every provider candidate and rejection into an indexed CSV before
  generating the blank human-review rows.

Partial execution, failed provider accounting and uninspectable cost are
observable states. They are not rewritten as success or zero cost.

## Source lock and human review

The review module does not mutate the write-once live directory. It first
requires a study-owner source lock over every aggregate artifact, then creates
a separate Schema v2 packet. The packet exposes, for every case:

- the frozen topic, gap state and baseline source summaries;
- the accepted candidate identity, title and URL;
- the exact allowed label pairs and provider-specific thresholds; and
- the study's measurement limit.

A completed source can be locked only when all eight cases and both four-case
provider boundaries are complete, the aggregate files match their artifact
index, the case journals match the aggregate execution, provider lineage and
cost accounting remain valid, and candidate/review CSV rows can be regenerated
exactly from the executor audits.

The result path distinguishes incomplete review, substantive-AI exclusion and
an eligible human result. External URLs must all be attempted for an eligible
result. Zero accepted candidates explicitly fail the value gate instead of
producing a misleading zero-error pass. Even a pass authorizes only a later
planner-trigger experiment; `production_connection_authorized` remains false.

## Defects found while testing

Testing found and fixed four boundary issues before merge:

1. a Pydantic `HttpUrl` reached a standard `json.dumps` boundary as an object;
   source URLs are now converted to strings at the model-to-artifact seam;
2. the expanded manifest originally rechecked the collection hash but not the
   validated-plan hash; both identities are now recomputed from typed values;
3. provider summaries accepted more requests than attempted cases; the frozen
   one-request contract now requires equality; and
4. the measurement-limit sentence was emitted but not independently frozen;
   packet intake now rejects any drift instead of reflecting changed prose into
   the result.

One test fixture also exposed a Windows newline mistake in its own tamper hash.
The test now hashes actual persisted bytes, matching the artifact-index
contract, rather than assuming in-memory `\n` bytes equal on-disk bytes.

## Defect re-injection

Two defects were deliberately reintroduced after the targeted suite was green:

1. the implementation-hash mismatch branch was disabled. The dedicated test
   failed before it could assert the pre-adapter, pre-output rejection; and
2. provider-rejected rows were omitted from CSV projection. The boundary test
   failed with 8 rows instead of the required 16.

Both mutations were removed immediately. Each targeted test passed after
restoration. This shows the tests observe executable admission and artifact
delivery seams, not only values on directly constructed models.

## Verification

- frozen protocol dry-run: 8/8 identities, implementation hashes present,
  `live_provider_requests_authorized=false`, zero network;
- Phase 4 runner/review/adapter subset: **50/50 passed**;
- complete zero-network suite: **1,515 tests plus 627 subtests passed**;
- latest Ruff: passed;
- CI Pylint exception-order/unreachable checks: passed; and
- coverage: **87.07%**, above the unchanged 85% floor.

The coverage run emitted nine inherited `ResourceWarning` messages from CrewAI
SQLite lifecycle paths. It emitted no `UserWarning`, did not enter a paid
fallback and passed the existing warning policy. No warning filter was added.

## Decision and next gate

The disconnected measurement harness is eligible to merge. Production Tool
Calling remains ineligible.

The next step is not another implementation change. It is a separately
authorized run over the exact frozen eight cases, with at most eight provider
requests, the existing OpenAlex soft stop, explicit Lens uninspectable-cost
acknowledgement and a new output directory. After the source is locked, an
independent eligible reviewer must inspect every returned URL against the
visible baseline context.

Both providers must independently satisfy all three frozen value gates before
a planner-trigger precision study is justified. Passing that later study would
still require a separate production-connection decision.

## Supported claim

> A production-disconnected Phase 4 harness can execute a byte-frozen,
> eight-case OpenAlex/Lens value study with exact one-request accounting,
> write-once case journals, source-locked artifacts and a provenance-checked
> Schema v2 human-review packet. Its zero-network implementation suite passes;
> live provider compatibility and evidence value have not yet been measured.
