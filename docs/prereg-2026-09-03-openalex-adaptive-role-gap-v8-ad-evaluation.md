# Pre-registration: adaptive role-gap v8 AD unseen evaluation

**Date:** 2026-09-03 (Australia/Sydney)

**Status:** frozen after the eligible AC01-AC08 development review and before
an AD-capable live runner, any AD01-AD08 provider response, source lock, human
label, or aggregate result

**Production connection authorized:** no

**Live provider execution authorized:** no

## Decision being tested

The consumed AC development cohort passed all six frozen v8 gates. That result
supports further evaluation; it does not establish that adaptive role-gap
retrieval generalizes. This unseen study asks one question:

> Without changing the frozen query, role, routing, portfolio, or scoring
> rules, does adaptive role-gap retrieval preserve useful source coverage and
> closure value on AD01-AD08?

AD is an outcome-unseen cohort, not a secret-input cohort. Its code-owned
topics, roles, signals, priorities, anchor queries, and closure options were
already byte-frozen with AC and are exercised by zero-network identity tests.
No AD OpenAlex response, provider-derived route outcome, candidate set, or
human label has been observed before this registration.

This study remains a production-disconnected retrieval qualification. It does
not test planner-trigger precision, report improvement, autonomous model-written
queries, full-text source truth, recall, user utility, latency SLOs, or a
production Tool Calling path.

## Frozen lineage

- parent protocol:
  `docs/prereg-2026-09-02-openalex-adaptive-role-gap-closure-v8.md`
- AD pre-registration base revision:
  `9121bcc155751de6c774a36526587fcdc9641a9e`
- challenge fixture:
  `tests/fixtures/openalex_role_gap_v8_challenge.json`
- authoritative fixture SHA-256:
  `0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`
- consumed AC strict-result SHA-256:
  `7651aa1f7d6de14b05b3ee33fc0e2b8828e7bc168f44cdc0f1750b568998b187`
- AD case order: exactly `AD01` through `AD08`

The fixture, case order, topics, baseline summaries, role groups, candidate-
local signal phrases, closure priorities, anchor queries, and every possible
closure query are immutable. No AD observation may be used to edit them. The
six thresholds below are inherited unchanged from the parent v8 protocol.

AC artifacts, labels, and route outcomes may be used only as the disclosed
reason for advancing to AD. They may not be used as fallback rows, query terms,
or repair examples during AD execution.

## Required implementation boundary

Implementation begins only after this pre-registration is committed. The AD
entrypoint must be separately named and accept only the unseen cohort. It may
reuse the already-tested deterministic kernel, but it may not silently widen
the AC runner or make production import an experimental v8 component.

Before output reservation or construction of a network-capable adapter, the
future runner must verify:

1. the raw fixture bytes and exact AD order;
2. all eight case identities, eight anchor identities, and forty mutually
   exclusive closure-option identities;
3. the provider, routing, portfolio, qualification, request, and cost
   contracts;
4. every committed implementation dependency named by its manifest; and
5. an explicit live flag, a fresh output directory, anonymous-budget
   acknowledgement, and a positive soft stop no greater than USD 0.02.

The runner must refuse to start when `OPENALEX_API_KEY` is configured. Its own
hash is observed rather than recursively predeclared; a later live
authorization must name the exact merged implementation revision and the
fixture hash above.

## Frozen execution contract

Cases execute sequentially in AD01-AD08 order. Each case may spend:

1. exactly one code-owned `anchor_search`, capped at six abstract-bearing
   OpenAlex rows; and
2. at most one already-frozen `role_closure` request for the first missing role
   in frozen priority order, also capped at six rows.

If every role is mechanically observed in candidate-local title-and-abstract
text, the route must record `abstain_no_mechanical_role_gap` and spend no second
request. Provider topics, keywords, citation counts, or other metadata may not
establish role coverage.

The complete cohort therefore permits eight to sixteen sequential anonymous
OpenAlex requests and at most ninety-six provider rows. Redirects, retries,
fallback, repair, supplementary search, result-page fetches, model calls,
recovery, parallel requests, query rewriting, and a second closure are
forbidden. The provider-reported soft stop may not exceed USD 0.02. One request
already in flight may create a small disclosed overrun; no later request may
start after the stop is reached.

## Write-once evidence order

The future runner must preserve this order:

1. validate immutable identities and authorization;
2. reserve a fresh output directory;
3. write the complete manifest before adapter construction;
4. persist each anchor request and every returned or rejected row before
   routing;
5. persist the route decision before any selected closure request;
6. persist the closure request before portfolio construction;
7. persist the case portfolio before the next case; and
8. emit execution, provider-row, route, deduplication, unique-candidate,
   blank-review, and artifact-index outputs without overwriting earlier files.

An interrupted prefix is durable evidence but carries no recovery authority.
A selected closure that was not spent is `partial`, not an abstention or a
completed portfolio. Unknown or malformed accounting is `uninspectable`, not
zero cost.

Every provider row and rejection, route observation, selected identity,
candidate occurrence, deduplication owner, lane membership, latency, cost
state, and trace identity must reach the serialized audit boundary. Only a
mechanically complete eight-case run can become eligible for a source lock.

## Frozen human review

After a mechanically complete run, a separate source lock must reconstruct all
indexed bytes and create a route- and lane-blind Schema v2 packet. The reviewer
may see the frozen baseline, source title and abstract, and role definitions,
but not provider lane, rank, route action, missing role, selected closure,
mechanical matches, coverability, or aggregate answers.

At least one eligible independent reviewer must complete every row and the
method declaration. Only `NONE` or `LANGUAGE_ONLY` substantive generative-AI
use is eligible. External pages are optional because this remains a title-and-
abstract study, but their use must be declared. Incomplete, excluded, or
uninspectable review remains `not_evaluated` and cannot run a gate.

Hidden route and lane provenance may be joined only after all labels and the
declaration pass strict validation.

## Frozen conjunctive gates

The six AC gates carry forward unchanged:

1. at least 6/8 cases contain a directly relevant, baseline-novel candidate;
2. directly relevant candidates are at least 25% of all reviewable unique
   candidates;
3. at least 6/8 routing decisions are human-correct;
4. at least four executed closure cases contain selected-role closure value;
5. at least 6/8 union portfolios are human-coverable with no more than three
   sources; and
6. union coverability exceeds anchor-only coverability by at least two cases.

All six are conjunctive. If fewer than four closure requests execute, gate 4
fails rather than changing denominator or threshold. Missing denominators,
failed source locking, or ineligible review are `not_evaluated`, never pass.

## Required zero-network evidence before live authorization

Tests must prove that:

1. the AD entrypoint accepts exactly AD01-AD08 and rejects development cases;
2. fixture or implementation drift fails before output reservation and adapter
   construction;
3. the manifest exists before an injected adapter factory can run;
4. one anchor and at most one selected closure can execute per case;
5. abstention spends no closure while remaining explicitly observable;
6. journals, routes, portfolios, rejections, costs, and candidate lineage reach
   every final boundary;
7. a partial request sequence cannot fabricate a complete case or cohort;
8. no secret reaches an artifact and no provider or model call occurs in dry
   run;
9. production imports no AD or v8 experimental entrypoint;
10. the existing AC behavior and all prior frozen tests remain unchanged; and
11. the complete zero-network suite, latest Ruff, narrow Pylint, browser smoke,
    and Docker checks pass.

Two defects must be re-injected after implementation: allowing the AD
entrypoint to load `development`, and dropping a persisted route from the final
client artifact. Each must make its seam test fail before restoration. Tests
may not be weakened or skipped.

## Stop and decision rules

- This document authorizes implementation and zero-network verification only.
- Any AD provider request requires a new explicit owner authorization naming
  the merged implementation revision, exact fixture hash, at most sixteen
  sequential anonymous OpenAlex requests, and a total soft stop no greater
  than USD 0.02.
- AD becomes consumed after its first provider request, including a partial or
  failed request. It may not be tuned and rerun as unseen validation.
- Identity drift, wrong cohort, unexpected credential, output reuse, adapter
  construction before manifest persistence, retry, redirect, model use,
  uninspectable accounting, or production import stops the study.
- Mechanical failure prevents source-value claims. Human-gate failure seals
  v8. Neither may be repaired by lowering thresholds or borrowing AC rows.
- Passing all six AD gates still does not authorize production. It permits only
  separately pre-registered disabled-path, planner-trigger, and report-value
  studies before any connection decision.

## Explicit non-claims

This pre-registration does not establish provider compatibility, source
quality, routing accuracy, closure value, unseen generalization, report
improvement, user utility, cost stability, latency, an SLO, autonomous Tool
Calling, or production readiness. At registration time AD provider calls,
candidate rows, human labels, and model calls all remain zero.
