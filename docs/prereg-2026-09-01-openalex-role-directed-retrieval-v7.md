# Pre-registration: OpenAlex role-directed retrieval portfolio v7

Date: 2026-09-01 (Australia/Sydney)

Status: pre-registered before implementation, provider requests, model calls,
or human labels for AA01-AA08 or AB01-AB08

## Decision being tested

The failed role-slot consensus v6 study cannot be repaired by buying more
semantic-judge calls. Its eligible human diagnostic found 13 directly relevant
candidates among 64 provider rows, but only AA-independent predecessor cases
Y04-Y06 (3/8) contained a human-coverable evidence set. Y01, Y02, and Y08 had
core-technology evidence without the required application or decision-evidence
roles; Y03 and Y07 had no directly relevant candidate. Candidate-pool quality
and missing role coverage therefore precede semantic-judge quality.

V7 tests one narrower hypothesis:

> Two separately budgeted, role-directed OpenAlex searches can produce a
> candidate portfolio that is sufficiently relevant, baseline-novel, and
> human-coverable to justify a later semantic judge.

This is a retrieval qualification study. It does not test Qwen, report quality,
planner-trigger precision, source truth, production reliability, or user value.

## Frozen cohorts

- `AA01`-`AA08` are the development cohort.
- `AB01`-`AB08` are the unopened unseen cohort.
- Both cohorts, their role definitions, query text, lane targets, order, and
  baseline identities live in
  `tests/fixtures/openalex_role_directed_v7_challenge.json`.
- Y01-Y08 remain consumed diagnostic evidence. Z01-Z08 remain unopened under
  the v6 protocol and must not be repurposed for v7.
- AA becomes consumed after any provider request. AB must remain unopened until
  AA passes every frozen mechanical and human gate without tuning on AB.

## Retrieval contract

Every case contains the same two ordered read-only lanes:

1. `technology_scope` binds every required technology role to at least one
   application/scope role.
2. `technology_evidence` binds every required technology role to at least one
   supporting performance, validation, durability, or outcome role.

The exact query is code-owned and frozen in the fixture. A model does not write,
rewrite, expand, or choose either query. Each lane may make exactly one
anonymous OpenAlex Works request and return at most six rows with reconstructable
abstracts. Therefore one case authorizes at most two requests and twelve raw
provider rows; AA01-AA08 authorize at most sixteen requests. Redirects, retries,
fallback search, supplementary search, result-page fetching, and model calls are
forbidden.

The future runner must preserve lane identity and provider rank, then deduplicate
by normalized DOI before canonical OpenAlex URL while retaining all lane
memberships. No source may be filtered by a semantic model before the retrieval
qualification review. Every provider row, row-level rejection, lane membership,
deduplication decision, request identity, latency, and provider-reported cost
must reach the serialized audit boundary.

## Role-coverability definition

A case is human-coverable only when at most three directly relevant,
baseline-novel candidates jointly support:

- every required role;
- at least one scope role; and
- at least one supporting role.

The reviewer must derive role support from the frozen title and abstract. This
is not external source verification. `not_checked`, incomplete review, or an
ineligible reviewer is distinct from a failed value gate.

## Frozen gates

All gates are conjunctive. Silence or an unavailable denominator is not a pass.

### Mechanical gates

1. AA expands exactly eight ordered case identities and sixteen ordered lane
   identities before any client can be constructed.
2. A live AA run, if separately authorized later, completes exactly sixteen
   one-attempt OpenAlex requests with inspectable per-request accounting.
3. Every provider row and rejection reaches the aggregate boundary; all
   deduplication decisions retain their originating lane identities.
4. No Qwen or other model request occurs. Production, reports, recovery, and
   planner-trigger connections remain false.

### Human candidate-value gates

1. At least 6/8 cases contain one directly relevant, baseline-novel candidate.
2. At least 6/8 cases are human-coverable under the maximum-three-source rule.
3. Directly relevant candidates are at least 25% of all reviewable unique
   candidates. This is a candidate-pool floor, not the <=5% wrong-source gate
   required of a final production-selected set.
4. `technology_evidence` contributes at least one unique directly relevant
   candidate not returned by `technology_scope` in at least 4/8 cases.
5. The two-lane union makes at least two more cases human-coverable than the
   `technology_scope` lane alone. If one lane is already sufficient, the second
   paid request has not justified its place in the production budget.

## Stop and falsification rules

- The zero-network preflight alone cannot pass any provider or human gate.
- A provider run requires a new explicit authorization naming the merged
  revision, AA fixture hash, maximum sixteen requests, and a cost soft stop.
- Any fixture, implementation, query, lane-target, request-budget, or ordering
  drift after authorization stops before client construction.
- A mechanical failure still requires all safely persisted provider rows to
  remain inspectable, but it cannot be called a value pass.
- AA failure seals v7. Do not tune on AA, rerun it, lower a gate, or open AB and
  call the result validation.
- AA success permits only a separately pre-registered AB evaluation. It does
  not authorize production Tool Calling.

## Production boundary

The preflight and any later runner must remain outside `pipeline_worker.py`.
No production source collection, report, Planner decision, checkpoint, retry,
or recovery path imports v7. A production connection would require a separate
decision after an eligible AB result and a report-level value study.
