# Result: scope-link v4 abstention diagnostic human review

**Completed:** 2026-08-29

**Status:** `complete / evaluated` as a post-outcome diagnostic only.

**Authority:** descriptive human interpretation of the 64 frozen W01-W08
titles and abstracts. This result cannot repair the failed v4 gate, establish
source truth, validate a successor, authorize another provider run, or connect
Tool Calling to production.

## Why this is a separate result

The live v4 study accepted zero candidates and therefore stopped before its
planned source-value review. That mechanical failure did not distinguish
irrelevant retrievals from useful sources rejected by an overly literal rule.
The project consequently pre-registered a label-blind, post-outcome diagnostic
over every abstained candidate. W01-W08 were already consumed before this
review began and remain unavailable as unseen validation data.

The diagnostic locked the exact live revision
`678254d66c599402811d04f9b2b91ff6977ac089`, source lock
`8a9747f4240fc7c529d8d8f2a737fb21b502579ad2f69c19587bf093cabba7af`,
and packet manifest
`68e15abdca46f4a65d33a75aedaa9a0eac2112a90a8b1e6eb1d00e71e59b8616`.
The reviewer saw the frozen topic, gap, baseline context, title and abstract,
but not the v4 action, rejection reasons, concept profile, match provenance or
link evidence.

## Eligible return

One anonymous human reviewer completed all 64 rows in 30 minutes and declared:

- all rows reviewed: `YES`;
- substantive generative-AI use: `NONE`;
- external sources checked: `NONE`;
- expertise: academic literature relevance assessment;
- limitation: judgments used only the frozen titles and abstracts.

The returned declaration encoded the external-source answer as `0`, while its
plain-language limitation independently stated that no external sources were
checked. With the project owner's explicit confirmation, only that field was
normalized to the schema value `NONE`. The byte-exact returned files were
preserved in the private audit archive before normalization; no substantive
label, note, identity, duration or limitation was changed.

The strict zero-network summarizer revalidated the source lock, packet
manifest and every row identity before producing `complete / evaluated` with
no method issue and no incomplete row.

## Aggregate result

| Measure | Result |
|---|---:|
| Completed rows | 64 / 64 |
| Directly relevant from frozen text | 28 / 64 (43.75%) |
| Directly irrelevant / retrieval noise | 36 / 64 (56.25%) |
| Unverifiable from frozen text | 0 / 64 |
| Cases with at least one relevant source | 8 / 8 |
| Cases with at least one relevant, baseline-novel source | 8 / 8 |
| Rows where the reviewer inferred the required semantic link | 5 |
| Human semantic links missed by v4 | 4 / 5 (80.0%) |

The hidden-trace attribution joined after review was:

| Attribution | Rows |
|---|---:|
| Retrieval noise | 36 |
| Semantic relation missed by v4 | 4 |
| Relevant source rejected by another v4 gate | 24 |

The 24 rows in the final category are relevant-source rejections, not
additional semantic-link misses. Only five rows received a positive human
semantic-link label, and four of those five were missed by the exact
same-segment rule.

## Case-level census

| Case | Relevant | Retrieval noise | Semantic-link miss | Other relevant-source rejection |
|---|---:|---:|---:|---:|
| W01 | 7 | 1 | 2 | 5 |
| W02 | 1 | 7 | 0 | 1 |
| W03 | 1 | 7 | 0 | 1 |
| W04 | 1 | 7 | 0 | 1 |
| W05 | 8 | 0 | 1 | 7 |
| W06 | 3 | 5 | 0 | 3 |
| W07 | 5 | 3 | 0 | 5 |
| W08 | 2 | 6 | 1 | 1 |

## Interpretation

The zero-acceptance outcome had two observable contributors:

1. the generic OpenAlex candidate query returned substantial retrieval noise;
2. among the small set of rows where a human inferred the target relationship,
   the exact same-segment lexical rule missed most links.

All eight cases nevertheless contained at least one source the reviewer judged
both directly relevant and novel relative to the displayed frozen baseline.
The live failure therefore cannot be explained solely as an absence of useful
candidate evidence.

These observations explain the failure shape; they do not estimate provider
recall, source truth, report improvement, user value or production reliability.
Because no external page was checked, every judgment is limited to the supplied
title and abstract. One reviewer also provides no inter-rater agreement.

## Decision

Scope-link v4 remains failed and disconnected. The diagnostic does not reopen
its frozen gate and does not authorize v5 validation or production Tool
Calling. A successor may be designed only as a new hypothesis with newly
frozen, unseen cases. It should address retrieval precision and relation recall
as separate failure surfaces rather than tuning against W01-W08.

## Verification

The completed return passed the strict zero-network summarizer and all 16
focused diagnostic seam tests. The implementation continues to expose
`production_connected=false`, `report_workflow_connected=false`, and
`v5_validation_authorized=false`.

See the
[pre-registration](prereg-2026-08-29-openalex-scope-link-v4-abstention-diagnostic.md),
[blank-packet implementation result](results-2026-08-29-openalex-scope-link-v4-abstention-diagnostic-implementation.md),
and [original live result](results-2026-08-29-openalex-scope-link-v4-live.md).
