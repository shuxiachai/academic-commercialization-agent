# Result: role-directed retrieval v7 live runner implementation

Date: 2026-09-02 (Australia/Sydney)

Status: implemented and mechanically qualified offline; no OpenAlex request,
model call, human review, unseen-cohort access, or production connection

## Scope

This stage implements the write-once runner pre-registered in
`prereg-2026-09-01-openalex-role-directed-retrieval-v7-live-runner.md`. It does
not execute AA01-AA08. The exact fixture remains:

```text
9a91746d0a77fee6d57bfc91ae4329ab78a89109fca6f35171d56c0f3ee95761
```

AA therefore remains unconsumed, and AB01-AB08 remains unopened.

## Implemented execution boundary

`openalex_role_directed_live.py` now provides a production-disconnected CLI
that defaults to the existing zero-network dry-run. Its live path accepts only
the AA development cohort and requires a fresh output directory, an explicit
live flag, anonymous-budget acknowledgement, no configured OpenAlex key, and a
positive provider-reported soft stop no greater than USD 0.02.

Before a network-capable adapter can exist, the runner checks the raw fixture
and six behavior-bearing dependency hashes, expands all eight ordered cases and
sixteen ordered lane identities, records its own observed hash, reserves the
output directory, and writes the complete manifest. Each attempted lane then
owns one request and one durable journal. A second lane cannot start before the
first journal exists, and a later case cannot start before the preceding
two-lane portfolio exists.

A provider failure, invalid OpenAlex accounting shape, idempotency mismatch,
uninspectable cost, or reached soft stop creates an explicit partial result and
starts no later request. A structurally parseable but provider-unidentified
response remains visible in its failed lane journal without being promoted to
the provider-row table. This distinction was found by the new test suite rather
than being hidden as a zero-row provider pass.

## Portfolio and review boundary

Completed lane candidates are visited in frozen lane and provider-rank order.
The deterministic portfolio merges the same normalized DOI first, then an
unambiguous canonical OpenAlex work URL. Conflicting non-empty DOIs do not merge
solely because their URLs collide. Every candidate occurrence retains:

- case and lane identity;
- provider rank and request identity;
- candidate, occurrence, owner, and unique-source hashes;
- the exact deduplication basis and value; and
- all originating lane memberships.

Every valid provider candidate and indexed rejection reaches
`provider-rows.csv`. First-seen sources and complete occurrence membership reach
`unique-candidates.csv`. The blank `review.csv` exposes the topic, frozen
baseline, full role profile, title, abstract, DOI, URL, provider ranks, and lane
memberships, while relevance, novelty, supported roles, and notes remain blank.
No model predicts or filters those labels.

The artifact index hashes the manifest, execution, all lane journals, all case
portfolios, and all three CSV boundaries. Final models recompute request,
candidate, rejection, occurrence, unique-source, portfolio, cost, and latency
totals from their child artifacts. `completed` means sixteen durable completed
requests and eight portfolios only; source value remains `not_evaluated`.

## Verification

- new live-runner focused suite: 17/17 passed;
- combined v7 preflight and runner suite: 27/27 passed;
- full zero-network suite: 1,878 tests plus 657 subtests passed;
- latest Ruff across the repository and the CI-equivalent narrow Pylint gate:
  passed; and
- default CLI dry-run: 8/8 cases, 16/16 lanes, zero live authority, zero model
  calls, and no provider client construction.

Two pre-registered boundary defects were re-injected and observed red:

1. manifest persistence was moved after adapter construction; the injected
   factory failed immediately because durable authority did not yet exist;
2. the serialized unique-source boundary was changed to retain only the first
   lane; the CSV seam test failed for all shared two-lane candidates.

Both defects were restored, after which the combined v7 suite returned to
27/27. The broader suite also caught one implementation issue during normal
development: a generic response without provider usage was durable as a failed
journal but could not be serialized as an identified OpenAlex row. The runner
now preserves that failure without inventing provider lineage.

## What this establishes

This result establishes a bounded, write-once, identity-locked execution
contract for a future separately authorized AA run. It preserves the exact
relationship between spent requests, raw provider rows, duplicate occurrences,
unique candidates, and blank human-review rows. It also keeps model calls,
production reports, Planner triggers, supplementary search, retries, and
recovery structurally disconnected.

It does not establish live OpenAlex compatibility for AA, candidate relevance,
novelty, precision, role coverability, incremental value of the evidence lane,
report improvement, user value, autonomous tool choice, or production Tool
Calling. A real run still requires separate authorization naming the merged
revision, this fixture hash, no more than sixteen sequential anonymous OpenAlex
requests, and a cost soft stop no greater than USD 0.02. Even a mechanically
complete run requires a separately source-locked, eligible human review.
