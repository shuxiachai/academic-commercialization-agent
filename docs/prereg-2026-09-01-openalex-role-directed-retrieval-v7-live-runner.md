# Pre-registration amendment: role-directed retrieval v7 live runner

**Frozen:** 2026-09-01, on top of the merged zero-network v7 preflight
revision `f28160305247df1235c5bd2b1bac63bcb04e2f46`, before implementing a
network-capable runner, constructing an OpenAlex adapter for AA01-AA08, or
making any provider request for AA01-AA08 or AB01-AB08.

**Parent protocol:**
[`prereg-2026-09-01-openalex-role-directed-retrieval-v7.md`](prereg-2026-09-01-openalex-role-directed-retrieval-v7.md)

**Challenge fixture:**
`tests/fixtures/openalex_role_directed_v7_challenge.json`

**Raw fixture SHA-256:**
`9a91746d0a77fee6d57bfc91ae4329ab78a89109fca6f35171d56c0f3ee95761`

**Production connection authorized:** no

**Live provider execution authorized:** no. This amendment authorizes only
implementation and zero-network verification of the disconnected AA runner.
A real AA run requires separate owner authorization naming the merged revision,
the exact fixture hash, no more than sixteen requests, and a provider-reported
cost soft stop no greater than USD 0.02. AB01-AB08 remain unavailable until AA
passes every frozen mechanical and human gate without tuning.

## Question

Can the frozen AA01-AA08 two-lane retrieval method be executed through a
durable, bounded boundary that preserves every spent request, provider row,
rejection, lane membership, and deduplication decision without allowing an
interrupted or uninspectable run to look complete?

This phase does not ask whether the retrieved sources are relevant, novel, or
jointly role-covering. Those are human-review questions and remain
`not_evaluated` after runner implementation or provider execution.

## Frozen execution scope

Only the `development` cohort AA01-AA08 may enter this runner. The existing
preflight may continue to byte-check and expand AB01-AB08 offline, but live
execution must reject the unseen cohort before adapter construction.

Each AA case owns exactly two sequential anonymous OpenAlex Works requests in
the fixture order:

1. `technology_scope`;
2. `technology_evidence`.

Each lane may return at most six provider rows with reconstructable abstracts.
The complete AA run may therefore make at most sixteen one-attempt requests and
observe at most 96 provider rows. Redirects, retries, fallback queries,
supplementary search, result-page fetches, model calls, repair, recovery, and
parallel requests are forbidden. A failed request, invalid response, identity
mismatch, uninspectable cost, or reached soft stop ends the run before a later
request begins.

## Identity and authorization boundary

Before output reservation or construction of any network-capable object, the
runner must verify:

- the raw challenge fixture bytes;
- all eight ordered AA case identities and sixteen ordered lane identities;
- the committed bytes of `openalex_role_directed_unseen.py`;
- the committed bytes of `evidence.py`, `evidence_gap.py`, and
  `evidence_search.py`;
- the committed bytes of `domain_evidence_search.py` and
  `anonymous_openalex_search.py`; and
- the exact provider, portfolio, and qualification contracts expanded by the
  preflight.

The runner records its observed self SHA-256 in the manifest and final
execution artifact. It cannot embed an expected hash of its own complete bytes
without recursion, so a later live authorization must name the exact merged
revision that owns that observed runner.

The live path must also require an explicit `--execute-live` flag, a fresh
write-once output directory, acknowledgement of the anonymous OpenAlex daily
budget, and a positive soft stop no greater than USD 0.02. It must refuse to
start when `OPENALEX_API_KEY` is configured. The CLI defaults to zero-network
dry-run and may not infer live authority from the presence of an output path.

## Write-once ordering

After all identities and arguments pass, ordering is fixed:

1. reserve the fresh output directory;
2. persist `manifest.json` with every expanded source collection, validated
   plan, role profile, lane contract, idempotency key, request ceiling, value
   gate, and implementation identity;
3. only then construct the adapter;
4. issue at most one request for the next ordered AA lane;
5. persist its complete `lane-executions/AAxx--lane.json` journal before a later
   lane may start;
6. after both lanes complete, deterministically create and persist the case
   portfolio before the next case may start; and
7. finish with write-once execution, provider-row, unique-candidate,
   blank-review, and artifact-index files.

An interrupted prefix is durable history, not resumable authority. This runner
does not add checkpoint or retry semantics. If only one lane of a case was
spent, its journal remains visible and no portfolio is fabricated for that
case.

## Frozen portfolio and deduplication contract

Every valid candidate remains reviewable; there is no semantic source filter.
Within one case, candidates are visited in frozen lane order and provider-rank
order. The first candidate owns the unique-candidate record. A later candidate
is merged only when it shares:

1. the same non-empty normalized DOI, compared case-insensitively; otherwise
2. the same canonical OpenAlex record URL.

DOI identity has precedence over URL identity. A duplicate occurrence must
retain its own lane ID, provider rank, request identity, candidate hash, and the
deduplication key and owner that caused the merge. The unique record must retain
all originating lane memberships and occurrences. Two candidates with
different non-empty DOIs do not merge merely because a malformed provider
response points them at one URL; that ambiguity is retained for human review.

Every provider rejection remains attached to its request and provider row. It
does not enter the unique candidate denominator, but it must reach the raw-row
CSV and final accounting.

## Final states and mechanical gates

`completed` means all sixteen ordered requests reached durable completed
journals and all eight case portfolios were persisted. It does not mean source
value passed. The final artifact must distinguish:

- provider state: `not_observed`, `known`, or `uninspectable` cost;
- execution state: `completed` or `partial`;
- review-packet state: `eligible_for_source_lock` only after all mechanical
  gates, otherwise `incomplete` or `mechanical_gate_failed`;
- human review: always `not_prepared` in this phase; and
- source value: always `not_evaluated` in this phase.

Mechanical eligibility requires exactly eight ordered portfolios, sixteen
one-attempt completed requests with inspectable accounting, complete serialized
coverage of every provider row and rejection, complete occurrence-to-unique
candidate lineage, and zero model calls. Production, reports, Planner,
checkpoint recovery, and supplementary-search connections remain false.

The human gates from the parent protocol are unchanged. In particular, a
complete provider run does not calculate relevance, novelty, role support,
candidate precision, evidence-lane incremental value, or union coverability.
All blank review rows must expose both frozen baseline context and complete
source title/abstract content without exposing a hidden answer or model label.

## Required zero-network verification

Before a real AA authorization, tests must prove that:

1. dry-run locks eight AA cases, sixteen lanes, dependency hashes, and all
   request ceilings while constructing no adapter and opening no socket;
2. fixture, implementation, order, or authorization drift fails before output
   reservation and adapter construction;
3. `manifest.json` exists before an injected adapter factory can run;
4. each prior lane journal exists before a later injected request can run;
5. both lane journals and the portfolio exist before the next case request;
6. every provider candidate and rejection reaches the raw-row CSV;
7. every duplicate occurrence and all lane memberships reach the unique-source
   and blank-review boundaries;
8. provider failure, invalid accounting, identity mismatch, unknown cost, and
   soft stop remain distinct partial states with no retry;
9. no environment secret reaches any artifact;
10. the production worker imports no v7 preflight, runner, or experimental
    adapter; and
11. the full zero-network suite, latest Ruff, and narrow Pylint pass.

Two defects must be re-injected and observed red before restoration: moving
manifest persistence after adapter construction, and dropping one duplicate
occurrence or lane membership from the final serialized boundary. Existing
assertions may not be weakened or skipped.

## Stop and falsification rules

Runner implementation fails if a network-capable object can exist before the
manifest, if a later request can begin before the previous spent-request
journal, if a later case can begin before its predecessor portfolio, if any
provider row or deduplication lineage disappears before the client artifact,
or if production imports a v7 component.

A later AA run fails mechanically if it does not complete all sixteen requests
and eight portfolios with inspectable accounting. A mechanically complete run
still requires a separate source lock and eligible human review. AA failure
seals v7; it does not authorize tuning on AA, rerunning it as validation,
opening AB, lowering a gate, or connecting the method to production.

## Explicit non-claims

Passing this implementation stage would establish only a durable, bounded,
inspectable and production-disconnected execution contract. It would not
establish OpenAlex compatibility on AA, source relevance, novelty, precision,
recall, role coverability, incremental value of the second lane, report
improvement, planner-trigger precision, user utility, an SLO, autonomous tool
choice, or completed production Tool Calling.
