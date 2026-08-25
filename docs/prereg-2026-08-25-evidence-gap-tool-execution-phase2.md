# Evidence-gap bounded tool execution — phase 2 pre-registration

**Frozen:** 2026-08-25, before the phase-2 executor and challenge fixtures were
written
**Production evidence changes authorized:** no
**Network, search-provider, or planner-model calls authorized by this document:**
no

## Question

Can a validated evidence-gap plan drive a strictly bounded set of read-only
search adapters while keeping every returned row quarantined until it passes
the existing evidence rules, and while making request, rejection, latency,
cost, and trace accounting inspectable?

Phase 2 is an execution-contract experiment.  It does not authorize the
production worker to inject a planner, execute supplementary search, or change
the `SourceCollection` supplied to the six-stage workflow.  A later provider-
backed experiment needs separate authorization because it can spend search and
LLM quota.

## Measurement already available

The phase-1 replay was rerun from the 30 collections already on disk before any
phase-2 code was written:

- 30/30 collections loaded and remained byte-identical;
- 9 were eligible and 21 had no explicit gap;
- all 18 signals were `authority_category_missing`; and
- zero component or failed-domain signals occurred.

Those nine cases are a development set and current retrieval already searches
the relevant authority endpoints.  Repeating their queries would be duplicate
retrieval, not novel evidence gain, so they cannot establish phase-2 efficacy.

## Frozen execution boundary

1. Input is a phase-1 `GapContext` plus `ValidatedGapPlan`.  The executor never
   accepts an unvalidated model dictionary.
2. Only the four named read-only capabilities are addressable:
   `academic_search`, `patent_search`, `market_search`, and `authority_search`.
   There is no arbitrary URL, shell, file, mutation, or user-selected tool.
   Every query must overlap the original research topic; component and
   authority gaps must additionally name the missing component or authority
   category. Tool authorization alone cannot widen the user's research scope.
3. One adapter invocation equals one actual outbound search attempt.  A single
   run receives a global budget of two attempts.  A retry consumes the same
   budget; therefore two planned calls leave no retry capacity.
4. Every adapter response is strict Pydantic data.  Unknown fields, mismatched
   tool identities, mismatched idempotency keys, and claims of anything other
   than exactly one outbound attempt are rejected.
5. Returned candidates remain in a separate evidence delta.  They never enter
   the original `SourceCollection` in this phase.
6. Before a candidate can enter that delta it must pass schema validation,
   public HTTP(S) URL policy, domain/source-type consistency, topical
   relevance, and URL/DOI/title deduplication against both the original
   collection and earlier accepted candidates.
7. Policy rejection, adapter failure, exhaustion, and a clean empty result are
   different observable states.  No accepted source is reported as a pass when
   validation did not run.
8. Audit output records the trigger ids, normalized query hash rather than the
   full potentially sensitive query, idempotency key, attempt count, raw and
   accepted counts, rejection reason codes, latency, incremental cost, and
   trace id.
9. The executor is deterministic for the same validated inputs and frozen
   adapter responses.  It does not mutate either input object.

## Frozen zero-network challenge

The executable challenge will contain at least twelve cases spanning all four
capabilities and the following seams:

- a novel valid source is accepted;
- an existing URL, DOI, and normalized title are each rejected as duplicates;
- private, credential-bearing, unsupported-scheme, and non-allowlisted URLs
  are rejected before registration;
- a source with the wrong evidence domain is rejected;
- an off-topic candidate is rejected;
- one retryable adapter failure consumes a second and final request;
- two planned calls execute once each and cannot retry;
- a missing adapter and malformed adapter response are explicit failures;
- zero validated candidates is `evidence_incomplete`, never a successful
  evidence gain; and
- attempted mutation of the original collection is detected at the output
  seam.

The challenge is a deliberately adversarial contract set, not a random sample
of production topics and not a held-out estimate of real-world tool value.

## Phase-2 implementation acceptance

The implementation may merge as an experimental, production-disconnected
kernel only if:

1. the existing zero-network suite, latest Ruff, CI Pylint exception-order
   check, and 85% coverage floor remain green;
2. every frozen challenge case produces its exact registered disposition;
3. no case exceeds two adapter invocations;
4. zero invalid, duplicate, wrong-domain, or policy-rejected candidates enter
   the evidence delta;
5. every triggered success case with a provided valid novel candidate retains
   at least one candidate, while empty/failed validation remains explicitly
   incomplete;
6. all attempt, latency, cost, rejection, and trace fields are present and
   arithmetically consistent;
7. the production worker still injects no planner and executes zero
   supplementary calls; and
8. reintroducing one request-budget defect and one evidence-quarantine defect
   makes their targeted tests fail before each defect is removed.

## Criteria before any production connection

This PR cannot satisfy the phase-1 production thresholds with synthetic
responses alone.  A separately frozen, independently inspected planner and
live-search run must still report:

- trigger precision of at least 90%;
- no more than two actual outbound attempts per run;
- zero invalid, unregistered, or policy-rejected sources entering evidence;
- wrong-source rate no greater than 5%;
- novel validated evidence in at least 50% of triggered cases;
- complete incremental latency, token, search-cost, rejection, and trace
  accounting; and
- no output regression when the feature flag is disabled.

Until those criteria pass, the accurate description is **bounded Tool Calling
execution kernel validated offline**, not production Tool Calling and not an
improvement in report quality.
