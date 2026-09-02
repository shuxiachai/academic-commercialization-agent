# Result: role-directed retrieval v7 AA human-review boundary

**Implemented:** 2026-09-02 (Australia/Sydney)

**Parent protocol:**
[`prereg-2026-09-02-openalex-role-directed-v7-human-review.md`](prereg-2026-09-02-openalex-role-directed-v7-human-review.md)

**Frozen provider run:**
[`results-2026-09-02-openalex-role-directed-retrieval-v7-development-live.md`](results-2026-09-02-openalex-role-directed-retrieval-v7-development-live.md)

**Provider-run revision:**
`2a61c32d4693f4f9a44965312c378dc8f14fb308`

**Production connection authorized:** no

## Outcome

The zero-network source-lock and human-review boundary is implemented. It
successfully validated the exact completed AA01-AA08 provider directory and
created a separate lane-blind Schema v2 packet containing all 79 frozen unique
candidates across all eight cases.

This is an implementation and blank-packet preflight result. No human label
has been entered, no AB case has been opened, and none of the five candidate-
value gates has been evaluated. The strict blank result is therefore
`incomplete / not_evaluated`, not a zero-error pass.

## Exact source reconstruction

Before packet creation, the implementation binds and checks 30 files: the 29
files named by the provider artifact index plus the index itself. It parses and
independently reconstructs:

- all 16 completed one-attempt lane journals and USD 0.016 aggregate cost;
- all eight portfolios and every occurrence-to-unique-candidate relation;
- all 96 provider rows, including 84 candidates and 12 rejections;
- all 79 DOI/OpenAlex-deduplicated candidates and blank review rows; and
- every fixture, implementation, runner, request, ordering, accounting and
  production-disconnection identity.

The reconstruction matched the authoritative bytes. During implementation,
this real-data check also found a one-character transcription error in the new
AA03 scope-journal hash constant. The artifact, artifact index and execution
were mutually consistent; only the new constant was corrected. No provider
artifact was changed or rerun.

## Reviewer boundary

Every reviewer row contains immutable case and candidate identity, topic,
title, OpenAlex URL, DOI, bibliographic metadata, frozen abstract, baseline
sources, and the complete role catalogue. It excludes lane membership,
provider rank, duplicate-occurrence count, lane incremental status, computed
coverability, model output and answer keys.

The return contract requires a valid relevance/novelty pair, a JSON array of
known supported role IDs, and a source-grounded note for every row. Relevant
rows require at least one supported role; non-relevant and unverifiable rows
require an empty array. External page access is optional and declarative
because this protocol intentionally measures support from frozen titles and
abstracts. Missing, partial, unverifiable, unconfirmed or substantively AI-
generated reviews cannot produce a value pass.

Only after every label and declaration passes validation does the summarizer
join hidden lane provenance and calculate deterministic covers of at most
three baseline-novel relevant sources. It reports each numerator, denominator,
case ID and selected row ID for all five frozen gates. A pass can authorize
only a separately pre-registered AB evaluation; production authorization is
always false.

## Verification

The focused suite passes 15/15 zero-network tests. The full suite passes 1,894
tests plus 657 subtests. Latest Ruff and the narrow CI Pylint gate also pass.

Two protocol-mandated defects were re-injected before restoration:

1. adding `lane_memberships` to a reviewer-visible packet row made the
   serialized boundary test fail; and
2. allowing scope-only coverability to use the full two-lane union made the
   successful five-gate scenario fail.

The tests also cover source and packet byte drift, portfolio-lineage drift,
unknown roles, relevance/role contradictions, blank and ineligible reviews,
all five gate outcomes, and production-import isolation.

## Decision and next permitted step

The source-lock, blinding, role-label and deterministic summary mechanisms are
ready for the frozen AA human review. Candidate value remains
`not_evaluated`; AB01-AB08 remain unopened, and production Tool Calling remains
disconnected.

The next permitted step is one eligible human completion of the exact 79-row
packet, followed by this zero-network summarizer. AA must not be rerun or tuned.
AB may be considered only if all five frozen gates pass; that would still not
authorize a semantic judge, Planner-trigger study, report connection or
production Tool Calling.

## Explicit non-claims

This result does not establish source relevance, novelty, source truth, recall,
role coverability, second-lane value, report improvement, planner-trigger
precision, user utility, an SLO or production readiness.
