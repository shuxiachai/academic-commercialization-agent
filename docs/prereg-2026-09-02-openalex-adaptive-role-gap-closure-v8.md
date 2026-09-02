# Pre-registration: adaptive role-gap closure v8

**Date:** 2026-09-02 (Australia/Sydney)

**Status:** frozen before implementation, provider requests, model calls, or
human labels for AC01-AC08 or AD01-AD08

**Production connection authorized:** no

## Decision being tested

Role-directed retrieval v7 established that broad relevance was not enough.
Its eligible AA human review found directly relevant, baseline-novel material
in 8/8 cases and 37/79 relevant candidates, but only 5/8 cases were jointly
role-coverable. The second fixed query lane contributed unique relevant rows in
7/8 cases while making zero additional cases coverable. The three failed cases
each lacked one narrow role: a magnesium-air cell, cold-chain packaging use, or
a monovalent-selective membrane. A second broad query therefore spent a request
without targeting the role that actually blocked the evidence set.

V8 tests one narrower hypothesis:

> After one anchor search, a deterministic candidate-local role screen can
> select at most one pre-frozen closure query for the highest-priority missing
> role, improving human role coverability without allowing a model to invent or
> expand a query.

This is a disconnected retrieval-and-routing qualification study. It does not
test report quality, planner-trigger precision on production reports, source
truth, recall, user value, latency SLOs, or autonomous model-written tools.

## Frozen cohorts

- The raw fixture SHA-256 is
  `ebdaf5da97a941abf7499b87bfcd3602db117a1be054ed3d13ef4ca3906f88f2`.
- `AC01`-`AC08` are a new development cohort.
- `AD01`-`AD08` are a new unopened unseen cohort.
- The exact topics, role descriptions, candidate-local signal groups, anchor
  queries, closure priorities, and every possible closure query live in
  `tests/fixtures/openalex_role_gap_v8_challenge.json`.
- AA01-AA08 remain consumed v7 evidence. AB01-AB08 remain sealed under the
  failed v7 protocol. Neither cohort may be reused by v8.
- AC becomes consumed after any provider request. AD must remain unopened until
  AC passes every frozen mechanical and human gate without tuning on AD.

## Bounded routing contract

Each case starts with exactly one code-owned `anchor_search` query and at most
six abstract-bearing OpenAlex rows. No second request is preselected.

After the anchor response, each frozen role is screened independently. A role
is mechanically observed only when all phrases in one of that role's frozen
signal groups occur within the title-and-abstract text of the same candidate.
Phrases may not be pooled across candidates, and OpenAlex topics, keywords,
citation counts, or other provider metadata may not establish role coverage.
These signals route a bounded request; they are not source-truth labels.

If every role is mechanically observed, the router returns
`abstain_no_mechanical_role_gap` and spends no second request. Otherwise it
chooses the first missing role in the case's frozen closure-priority order and
may issue exactly that role's pre-frozen `role_closure` query. It may not build,
rewrite, broaden, or substitute a query at runtime. The complete case therefore
uses one or two requests, never more than two, and returns at most twelve raw
provider rows.

The future runner must preserve the anchor observations, every matched signal
group and candidate index, all missing roles, the selected role and frozen query
identity, the explicit abstention reason, provider rank, request accounting,
and all raw rows at the serialized boundary. Human review receives source text
and role definitions but not the mechanical routing decision until its labels
are locked.

## Portfolio contract

Provider rows are deduplicated within a case by normalized DOI before canonical
OpenAlex URL. Every occurrence retains its request identity, route identity,
provider rank, and deduplication owner. No semantic model may filter candidates
before human qualification. At most three directly relevant, baseline-novel
sources may form a human role-covering set.

## Frozen gates

All gates are conjunctive. An unavailable denominator is `not_evaluated`, not a
pass.

### Mechanical gates

1. The zero-network preflight expands exactly eight ordered cases per cohort,
   one anchor identity and five mutually exclusive closure-option identities
   per case, while authorizing at most two executed requests per case.
2. Every possible closure option is query- and role-bound before any provider
   client can exist; unselected options are never sent.
3. A later AC live run, if separately authorized, durably records every spent
   request and provider row before a later request.
4. No retry, redirect, fallback, supplementary search, result-page fetch,
   recovery, or model call occurs.
5. Production, reports, checkpoints, and the current shadow Planner remain
   disconnected.

### Human routing-and-value gates

1. At least 6/8 cases contain a directly relevant, baseline-novel candidate.
2. Directly relevant candidates are at least 25% of all reviewable unique
   candidates.
3. At least 6/8 routing decisions are human-correct: a closure call must target
   a role absent from the human-labeled anchor portfolio, while an abstention is
   correct only when the anchor portfolio is already human-coverable.
4. In at least four executed closure cases, the closure request contributes a
   directly relevant, baseline-novel candidate supporting the selected role.
5. At least 6/8 union portfolios are human-coverable with no more than three
   sources.
6. The union makes at least two more cases human-coverable than the anchor
   portfolio alone.

The 25% candidate-pool floor is not the final production-selected-set
wrong-source gate. Passing AC would only justify a separately pre-registered AD
evaluation.

## Required zero-network implementation evidence

Before any live authorization, implementation tests must prove that:

1. raw fixture bytes are checked before JSON parsing or case expansion;
2. AC and AD topics, role profiles, priorities, anchor calls, and every closure
   option have distinct content-addressed identities;
3. a role signal cannot be completed by phrases split across two candidates;
4. the first missing role in frozen priority order is selected even when a
   different missing role appears first in serialized role order;
5. no-gap input produces an explicit abstention and no closure call;
6. the selected query is byte-for-byte one frozen closure option;
7. every route observation and closure option reaches the dry-run client
   boundary;
8. the preflight imports no provider, execution, model, or private-review code;
9. all live-authority, model, production, report, and recovery flags remain
   false; and
10. the full zero-network suite, latest Ruff, and narrow Pylint pass.

Two defects must be re-injected and observed red before restoration: pooling
signal phrases across candidates, and dropping one valid closure option before
the serialized dry-run boundary. Assertions may not be weakened or skipped.

## Stop and falsification rules

- This pre-registration authorizes implementation and zero-network verification
  only. It authorizes no OpenAlex or model request.
- A live AC run requires new explicit owner authorization naming the merged
  revision, exact fixture hash, no more than sixteen sequential OpenAlex
  requests, and a provider-reported cost soft stop no greater than USD 0.02.
- Fixture, signal, priority, query, implementation, order, or budget drift stops
  before client construction.
- AC failure seals v8. Do not tune on AC and call a rerun validation, lower a
  gate, or open AD.
- AC success permits only a separately pre-registered AD evaluation. AD success
  would still require a report-level value and disabled-path study before any
  production connection.

## Explicit non-claims

Passing the zero-network stage would establish only a deterministic, bounded,
inspectable routing contract. It would not establish provider compatibility,
source relevance, routing accuracy, closure value, role coverability, report
improvement, user utility, production reliability, or completed Tool Calling.
