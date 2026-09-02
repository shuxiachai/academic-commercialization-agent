# Pre-registration amendment: adaptive role-gap closure v8 live runner

**Frozen:** 2026-09-02, on top of merged zero-network v8 revision
`aa9bd79920f6b5cf7d718374d0286bd22fd87913`, before implementing a
network-capable AC01-AC08 runner, constructing an OpenAlex adapter for those
cases, or making any provider request for AC01-AC08 or AD01-AD08.

**Parent protocol:**
[`prereg-2026-09-02-openalex-adaptive-role-gap-closure-v8.md`](prereg-2026-09-02-openalex-adaptive-role-gap-closure-v8.md)

**Challenge fixture:**
`tests/fixtures/openalex_role_gap_v8_challenge.json`

**Raw fixture SHA-256:**
`0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`

**Production connection authorized:** no

**Live provider execution authorized:** no. This amendment authorizes only
implementation and zero-network verification of the disconnected AC runner.
A real AC execution requires separate owner authorization naming the merged
revision, the exact fixture hash, no more than sixteen sequential anonymous
OpenAlex requests, and a provider-reported cost soft stop no greater than USD
0.02. AD01-AD08 remain unopened unless AC passes every frozen mechanical and
human gate without tuning.

## Question

Can the frozen v8 adaptive sequence be executed through a durable boundary
that first observes one anchor result set, persists the resulting role-gap
decision, and then spends at most one role-specific closure request without
allowing an unrecorded route, missing provider row, or interrupted run to look
complete?

This implementation phase does not ask whether a source is relevant, novel,
or sufficient for a commercial decision. Those remain independent human-review
questions and must stay `not_evaluated` after implementation or a provider run.

## Frozen execution scope

Only development cases AC01-AC08 may enter this runner. The existing preflight
may continue to validate AD01-AD08 offline, but the live runner must not accept
the unseen cohort.

For each ordered AC case:

1. issue exactly one frozen `anchor_search`, capped at six provider rows;
2. derive all five role observations from candidate-local title and abstract
   text using the frozen router;
3. persist either `abstain_no_mechanical_role_gap` or the highest-priority
   missing role and its already-frozen closure identity;
4. issue exactly one `role_closure` request only when that persisted decision
   selects it, capped at six provider rows; and
5. join the completed anchor and optional closure into one case portfolio.

The complete study may make between eight and sixteen requests and observe at
most 96 provider rows. Redirects, retries, fallback queries, supplementary
search, result-page fetches, model calls, repair, recovery, parallel requests,
and a second closure are forbidden. A failed request, invalid response,
identity mismatch, uninspectable cost, or reached soft stop prevents a later
provider request.

## Identity and authorization boundary

Before output reservation or construction of any network-capable object, the
runner must verify:

- the raw challenge fixture bytes;
- all eight ordered AC case identities, eight anchor identities, and forty
  pre-authorized but mutually exclusive closure identities;
- the committed bytes of `openalex_role_gap_unseen.py`;
- the committed bytes of `evidence.py`, `evidence_gap.py`, and
  `evidence_search.py`;
- the committed bytes of `domain_evidence_search.py` and
  `anonymous_openalex_search.py`; and
- the exact provider, routing, portfolio, and qualification contracts expanded
  by the preflight.

The runner records its observed self SHA-256 rather than embedding a recursive
expected hash of itself. A later execution authorization must therefore name
the exact merged revision that owns that observed runner.

The live path must require an explicit `--execute-live` flag, a fresh
write-once output directory, acknowledgement of the anonymous OpenAlex daily
budget, and a positive soft stop no greater than USD 0.02. It must refuse to
start when `OPENALEX_API_KEY` is configured. Supplying an output path alone
cannot convert the default zero-network CLI mode into live authority.

## Write-once ordering

After identities and arguments pass, ordering is fixed:

1. reserve the fresh output directory;
2. persist `manifest.json` with every expanded collection, role profile,
   anchor identity, closure option, idempotency key, budget, contract, and
   implementation identity;
3. only then construct the adapter;
4. issue one anchor request and persist its complete request journal before
   routing or any later request;
5. derive and persist the complete route decision before a selected closure
   request may begin;
6. if selected and still within budget, issue one closure request and persist
   its journal before portfolio construction;
7. persist the completed case portfolio before the next case may begin; and
8. finish with write-once execution, provider-row, route-decision,
   unique-candidate, blank-review, and artifact-index files.

An interrupted prefix is durable history, not resumable authority. A persisted
route without its selected closure is explicitly partial. No portfolio may be
fabricated from a failed anchor or an unspent selected closure.

## Frozen portfolio and provenance contract

Every provider-valid candidate remains reviewable; v8 adds no semantic source
filter. Within a case, candidates are visited in anchor-then-closure order and
provider-rank order. A later occurrence merges with the first owner only by:

1. the same non-empty normalized DOI, compared case-insensitively; otherwise
2. the same canonical OpenAlex work URL.

Different non-empty DOIs do not merge merely because they share a malformed
URL. Every occurrence retains its lane, provider rank, request identity,
candidate hash, deduplication basis, and owner. Unique rows retain all
occurrences and lane memberships. Every provider rejection remains attached to
its request and reaches raw-row accounting.

Route provenance is a separate first-class boundary. It must retain all five
checked observations, candidate counts, local signal matches, missing-role
order, action, reason, and the selected closure contract when present. A route
that was not checked cannot be represented as abstention.

## Final states and later qualification

`completed` means every AC case has a persisted anchor journal, route decision,
and valid portfolio, plus a closure journal exactly when its route selected
one. It does not mean source value passed. Final output must distinguish:

- provider cost as `not_observed`, `known`, or `uninspectable`;
- execution as `completed` or `partial`;
- source-lock eligibility as `eligible_for_source_lock` only after every
  mechanical boundary, otherwise `incomplete`;
- human review as `not_prepared`; and
- source value as `not_evaluated`.

The parent protocol's six conjunctive human gates remain unchanged. Blank
review material must expose frozen baseline context, route context, and source
title/abstract text without hidden answers or model labels. This runner must
not calculate or claim relevance, novelty, routing correctness, closure value,
candidate precision, role coverability, or gain over anchor-only retrieval.

## Required zero-network verification

Before a real AC authorization, tests must prove that:

1. dry-run locks eight AC cases, eight anchors, forty possible closures,
   dependency hashes, and request ceilings while opening no socket;
2. fixture, implementation, order, budget, or authorization drift fails before
   output reservation and adapter construction;
3. `manifest.json` exists before an injected adapter factory can run;
4. an anchor journal exists before its router runs and the persisted route
   exists before a selected closure request;
5. the complete case portfolio exists before the next case request;
6. a no-gap route spends no closure request while still producing a complete
   case;
7. every provider candidate and rejection reaches the raw-row boundary;
8. every route observation, selected identity, duplicate occurrence, and lane
   membership reaches its aggregate and blank-review boundary;
9. provider failure, invalid accounting, identity mismatch, unknown cost, and
   soft stop remain distinct partial states with no retry;
10. no environment secret reaches any artifact;
11. production code imports no v8 preflight, runner, or experimental adapter;
    and
12. the full zero-network suite, latest Ruff, and narrow Pylint pass.

Two defects must be re-injected and observed red before restoration: moving
manifest persistence after adapter construction, and dropping one correctly
computed route decision from the final serialized boundary. Existing
assertions may not be weakened or skipped.

## Stop and falsification rules

Runner implementation fails if a network-capable object can exist before the
manifest, if a closure can begin before its anchor journal and route decision,
if a later case can begin before its predecessor portfolio, if any provider
row or route/deduplication lineage disappears before the client artifact, or if
production imports a v8 component.

A later AC run fails mechanically if any ordered case lacks its required
durable boundaries or inspectable accounting. A mechanically complete run
still requires a separately pre-registered source lock and eligible human
review. Failure seals v8; it does not authorize tuning on AC, rerunning AC as
validation, opening AD, lowering a gate, or connecting v8 to production.

## Explicit non-claims

Passing this stage would establish only a bounded, adaptive, inspectable, and
production-disconnected execution contract. It would not establish live
OpenAlex compatibility on AC, source relevance, novelty, precision, recall,
routing correctness, closure value, role coverability, report improvement,
planner-trigger precision, user utility, autonomous tool choice, an SLO, or
completed production Tool Calling.
