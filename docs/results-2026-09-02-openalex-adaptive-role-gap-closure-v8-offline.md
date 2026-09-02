# Adaptive role-gap closure v8: zero-network implementation result

**Date:** 2026-09-02 (Australia/Sydney)

**Protocol:**
`prereg-2026-09-02-openalex-adaptive-role-gap-closure-v8.md`

**Live provider requests:** 0

**Model calls:** 0

**Production connection:** false

## Why this method exists

The eligible v7 human review found relevant, baseline-novel candidates in 8/8
cases and 37/79 relevant candidates, but only 5/8 cases were jointly
role-coverable. Its second fixed query lane added uniquely relevant material in
7/8 cases while closing zero additional role sets. V8 therefore tests a more
specific mechanism: spend the optional second request only on the highest-
priority role that a candidate-local screen did not observe after the anchor.

## Implemented boundary

The new zero-network preflight:

- raw-byte checks the AC01-AC08 development and AD01-AD08 unseen fixture before
  JSON parsing or case expansion;
- expands one anchor identity and five mutually exclusive closure identities
  per case, while capping future execution at one anchor plus one closure;
- matches all phrases in one frozen signal group within one candidate's title
  and abstract, never across candidates and never from provider metadata;
- selects the first missing role in the frozen per-case priority, rather than
  serialized role order;
- returns `abstain_no_mechanical_role_gap` with no selected call when all roles
  are observed;
- binds every option to a validated academic-search call, idempotency key,
  plan hash, role kind, query and route-contract hash; and
- serializes all observations and all closure options while importing no
  provider, executor, model, CrewAI or private-review code.

The empty-anchor route embedded in dry-run output is explicitly marked as a
synthetic seam probe, not a provider observation. It proves that checked
negative observations and the selected route identity reach the client-facing
serialization boundary.

## Preflight correction

The first focused run stopped before any network-capable object existed. Six of
80 closure queries failed the existing evidence-gap topic-scope rule because
lexical variants shared only one exact topic token. The scope rule was retained.
One existing topic token was appended to each affected query, with both raw
fixture identities and every correction preserved in
`errata-2026-09-02-openalex-role-gap-v8-query-scope.md`.

The authoritative corrected fixture SHA-256 is
`0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`.
No cohort, role, signal group, priority, intended query meaning, experimental
gate or budget changed.

## Mechanical result

Both cohort dry-runs report:

| Measure | Development AC | Unseen AD |
|---|---:|---:|
| Cases | 8 | 8 |
| Potential call identities | 48 | 48 |
| Maximum executable requests | 16 | 16 |
| Maximum provider rows | 96 | 96 |
| Maximum model calls | 0 | 0 |

Shared contract hashes are:

- provider: `26ebc0e138d7b40e26556ea61232c078a8e145649d9cb6168aa3bc4347b5bff3`;
- routing: `c00c93afb38662d2b4eae66f55f1aaa591e43c2d0c8f46f52d5a0cb2d8d783b5`;
- portfolio: `c857fce7c183544bd3971f348ca2de141ffcfa63b60b97a812bbbe18e4a5389a`;
  and
- qualification: `19a17bfe778d7b503cc8a2093687832be7b3be29848cf41109259da893ac2791`.

The focused suite passes **15/15**. Two protocol-mandated defects were then
injected separately:

1. pooling signal phrases across candidates changed the engineered-PET-
   hydrolase observation from false to true and made the candidate-local seam
   test fail; and
2. dropping the final valid closure option only during serialization made the
   exact fixture-to-boundary comparison fail.

Both defects were removed and the 15/15 focused suite passed again. No assertion
was relaxed and no test was skipped.

## Strict interpretation

This stage passes the frozen zero-network mechanical gates only. AC and AD are
still unopened, provider compatibility and cost are unobserved, and source
relevance, routing correctness, selected-role closure value, role coverability,
report improvement and user utility are all `not_evaluated`.

V8 remains disconnected from the production worker, reports, checkpoints,
recovery and the phase-1 shadow Planner. A separately implemented, identity-
locked write-once AC runner plus new explicit authorization would be required
before any OpenAlex request. Even an AC pass would justify only a separately
pre-registered AD evaluation, not production Tool Calling.
