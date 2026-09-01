# Result: OpenAlex role-directed retrieval portfolio v7 offline preflight

Date: 2026-09-01 (Australia/Sydney)

Status: implemented and mechanically qualified offline; no provider request,
model call, human review, or production connection

## Why this successor exists

The eligible v6 failure diagnostic was re-measured before implementation. Among
the eight consumed Y cases:

- Y04, Y05, and Y06 were human-coverable under the frozen maximum-three-source
  role rule;
- Y01, Y02, and Y08 contained core-technology evidence but lacked scope or
  supporting evidence;
- Y03 and Y07 contained no directly relevant candidate; and
- the complete pool contained 13 relevant and 51 irrelevant rows.

Only 3/8 candidate pools could therefore support the task even if the semantic
judge were perfect. V7 tests retrieval before buying another semantic run.

## Frozen method

Commit `e0d9155` froze new AA01-AA08 development and AB01-AB08 unseen
cohorts, two ordered role-directed queries per case, a maximum of six rows per
query, and conjunctive human-value gates. Commit `605d20f` transparently
corrected one AB05 evidence query before implementation or any provider request
after the existing scope tokenizer exposed a weak formal overlap. The corrected
fixture hash is:

```text
9a91746d0a77fee6d57bfc91ae4329ab78a89109fca6f35171d56c0f3ee95761
```

Each case now expands:

1. one `technology_scope` academic-search call that targets every required
   role and at least one scope role; and
2. one `technology_evidence` call that targets every required role and at
   least one supporting role.

The ordinary evidence-gap validator authorizes and hashes both calls. The v7
module adds case, profile, plan, lane, provider, portfolio, and qualification
contract identities. All 16 development idempotency keys and all 16 lane
contract hashes are distinct.

## Observable dry-run boundary

`openalex_role_directed_unseen.py` emits the exact two lanes for every case,
including query text, target role IDs, result limit, idempotency key, and lane
contract hash. It also states separately that:

- the maximum AA request count is 16;
- the maximum raw provider-row count is 96;
- the maximum model-call count is zero;
- human qualification has not run;
- provider and model calls are not authorized; and
- production, reports, planner triggers, recovery, private labels, network, and
  model clients remain disconnected.

The module imports no provider adapter, execution kernel, HTTP library, CrewAI,
or model client. Its default CLI is therefore structurally zero-network rather
than relying on an operator remembering a dry-run flag.

## Verification

- focused v7 suite: 10/10 passed;
- full zero-network suite: 1,861 tests plus 657 subtests passed;
- latest Ruff: passed;
- narrow Pylint `E0701`: passed; and
- fixture JSON, cohort order, topic uniqueness, query uniqueness, query scope,
  role targets, and raw-byte identity: passed.

The protocol-mandated seam defect was also re-injected. The dry-run serializer
was temporarily changed to emit only the first lane even though both validated
calls still existed internally. The boundary test failed because eight
`technology_evidence` lanes were absent. Restoring the complete zip returned
the focused suite to 10/10.

## What this result does and does not establish

This result establishes a deterministic, auditable, two-call retrieval
preflight that cannot silently open a socket. It does not establish OpenAlex
compatibility for these queries, candidate relevance, role coverability,
incremental value from the second lane, report improvement, or production Tool
Calling.

AA remains unconsumed because no provider request has occurred. AB remains
unopened. A live AA run requires separate authorization naming the merged
revision, exact fixture hash, maximum 16 sequential anonymous OpenAlex requests,
and a cost soft stop. Even a mechanically complete run must then undergo an
eligible, source-locked human review before any semantic model experiment can
be considered.
