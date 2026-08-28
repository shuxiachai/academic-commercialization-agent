# Pre-registration: OpenAlex scope-link v4 live harness

**Frozen:** 2026-08-28, after the zero-network v4 implementation merged as
`e9a9616e07bce1a7967888d0b8ba290237754f99`, but before implementing a v4
live runner, constructing a provider adapter for W01-W08, or making any
provider request for those cases.

**Parent protocol:**
`docs/prereg-2026-08-27-openalex-scope-link-v4.md`

**Challenge fixture:**
`tests/fixtures/openalex_scope_link_v4_challenge.json`

**Raw fixture SHA-256:**
`f4267c6a79c0bb8a685664de5086e4cfff59ebac1b352cbb56c2277957a55cc3`

**Production connection authorized:** no

**Live provider execution authorized:** no. This document authorizes only the
implementation and zero-network verification of a disconnected runner. A real
run requires separate owner authorization naming the merged revision, a cap of
no more than eight requests and a provider-reported soft stop no greater than
USD 0.01.

## Question

Can the frozen W01-W08 v4 method be executed through a durable, auditable
one-request-per-case boundary without allowing code drift, retries, unknown
cost or incomplete relation provenance to look like a successful source-value
study?

This stage does not ask whether v4 retrieves useful sources. Provider
compatibility, accepted-case coverage, wrong-source rate, novelty and source
value remain `not_evaluated` until a separately authorized live run and an
eligible human review occur.

## Frozen execution contract

The runner must default to a zero-network dry-run. Its live path must require
all of the following:

1. an explicit `--execute-live` flag;
2. a fresh write-once output directory;
3. a positive provider-reported soft stop no greater than USD 0.01;
4. acknowledgement of the anonymous OpenAlex daily budget;
5. no configured `OPENALEX_API_KEY`; and
6. a separately authorized merged revision.

The runner may attempt W01-W08 in frozen order. Each attempted case owns
exactly one anonymous OpenAlex Works request with `has_abstract:true`,
`per-page=8`, topics and keywords selected, no redirect, no internal retry, no
enrichment fetch and no model call. A provider failure, invalid response,
identity mismatch, uninspectable cost or reached soft stop ends the run without
starting another request.

## Identity and persistence order

Before reserving output or constructing a network-capable adapter, the runner
must verify the raw fixture bytes and the committed bytes of every reused
method and adapter dependency. The frozen dependency set is:

- `domain_evidence_search.py`;
- `evidence.py`;
- `evidence_gap.py`;
- `evidence_search.py`;
- `openalex_claim_scope.py`, which defines the adapter candidate contract;
- `openalex_claim_scope_search.py`, which defines the anonymous adapter;
- `openalex_precision.py`, which supplies exact phrase normalization;
- `openalex_scope_link.py`; and
- `openalex_scope_link_unseen.py`.

The runner's own observed SHA-256 must also reach the manifest and final
execution artifact before provider work. It cannot embed an expected hash of
its own complete bytes without a recursive identity. The separate execution
authorization must therefore name the merged revision, while the artifact
records the observed runner bytes for later comparison.

After identity checks, ordering is fixed:

1. reserve the fresh output directory;
2. persist `manifest.json` with every expanded collection, validated plan,
   profile, idempotency key, value gate and implementation identity;
3. only then construct the adapter;
4. issue at most one request for the next frozen case;
5. persist its complete `case-executions/Wxx.json` journal before another case
   can begin; and
6. finish with write-once execution, candidate, blank-review and artifact-index
   files.

An interrupted prefix is inspectable history, not resumable authority. This
experimental runner does not add retry or recovery semantics.

## Frozen artifact contract

Every valid provider candidate must reach the v4 decision boundary. Every
malformed provider row must reach an indexed rejection. Candidate rows must
preserve at least:

- provider request, row, cost and trace identities;
- `ACCEPT`, `ABSTAIN` or explicit `NOT_EVALUATED` disposition;
- missing, exact and provider-only required groups;
- exact and linked scope groups;
- title anchors;
- required, scope and supporting match provenance; and
- every same-title or same-abstract-sentence scope link, including field,
  sentence index, both group IDs and exact phrases.

Only `ACCEPT` candidates may appear in `review.csv`, and all human label cells
must remain blank. A completed provider run with accepted candidates in fewer
than 6/8 cases is `mechanical_gate_failed`; six or more is only
`eligible_for_source_lock`. Both states retain
`human_review_state=not_prepared` and `source_value_state=not_evaluated`.

## Frozen source-value gates

The parent v4 gates remain unchanged:

1. at least one accepted candidate in at least 6/8 cases;
2. at least one relevant and baseline-novel candidate in at least 6/8 cases;
3. no more than 5% directly irrelevant accepted candidates;
4. every attempted source reviewed; and
5. no substantive generative AI producing the human judgments.

No implementation test may manufacture a source-value pass. Synthetic rows
exercise persistence and accounting only.

## Required zero-network verification

Before any live authorization, tests must prove that:

- the dry-run locks all eight W identities and opens zero sockets;
- fixture or implementation drift fails before output and adapter construction;
- `manifest.json` exists before an injected adapter factory can run;
- each prior case journal exists before a later injected request can run;
- exactly one request, latency and cost record reaches every attempted case;
- provider failures, invalid accounting, unknown cost and soft stop remain
  distinct partial states;
- all provider rows and v4 decisions reach CSV, including complete scope-link
  provenance;
- only accepted rows reach the blank review boundary;
- fewer than six accepted cases cannot be described as source value;
- no environment secret reaches any artifact; and
- `pipeline_worker.py` imports none of the v4 runner, preflight, method or
  adapter modules.

After the focused suite passes, remove scope-link provenance from the CSV seam
temporarily and confirm the boundary test fails. Restore it, run the full
zero-network suite, latest Ruff and the project's narrow Pylint checks, and
record the result without performing a provider request.

## Stop and falsification rules

Implementation fails if any required identity can drift without detection, if
an adapter can exist before the complete manifest, if a later request can begin
before the previous journal, if a spent request lacks inspectable accounting,
if an accepted row loses relation provenance, or if production imports any v4
component.

A later live study fails mechanically if fewer than six cases retain an
accepted candidate. It must then stop before human review because labels cannot
rescue the frozen all-gates rule. A mechanically eligible run still has no
source-value result until a separate source lock and eligible human review
apply every remaining gate.

## Explicit non-claims

Passing this implementation stage would not establish provider compatibility,
source relevance, novelty, precision, recall, report improvement,
planner-trigger precision, decision quality, adoption, ROI, an SLO, autonomous
tool choice or production Tool Calling. `pipeline_worker.py` must remain
disconnected.
