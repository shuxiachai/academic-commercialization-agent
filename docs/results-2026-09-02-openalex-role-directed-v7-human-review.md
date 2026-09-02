# Result: role-directed retrieval v7 AA human review

**Date:** 2026-09-02 (Australia/Sydney)

**Status:** eligible human review completed; three of five frozen gates passed;
overall candidate-value decision failed; AA sealed; AB unopened; production
disconnected

## Bound evidence

The zero-network summarizer validated the exact AA01-AA08 provider run, source
lock, packet manifest, all 79 candidate identities, every immutable reviewer
field, all role IDs and all row-level notes before joining hidden retrieval-lane
provenance. No provider request or model call occurred during intake.

| Artifact | SHA-256 |
|---|---|
| source lock | `4ef109812aa81f0b72dbf635a625f4a71d17e6cb26d76933a0902576ec150757` |
| packet manifest | `f9d0ccd8efaaba69ad7617a75d2aabadd68615c6968784d95b6e0b37fe80392b` |
| returned 79-row labels | `6d779f5b0648aced92be0c43b278aafe1f2bda4ac45ae4d50ae18bdb1a2805d4` |
| strict corrected result | `72d1f28a701c8322302c66596f08355829cc9ed054f0cb7513818dac66c50efc` |

## Declaration correction

The first returned declaration recorded `generative_ai_use=MOST_OR_ALL`. The
strict first intake therefore correctly produced
`excluded_substantive_ai / not_evaluated` and ran none of the five gates. The
study owner subsequently relayed that the substantive judgments were completed
by a human reviewer and that this field was a filling error. The original
declaration, excluded result, owner-relayed correction and corrected declaration
are all retained in the private audit archive; no row label, role assignment or
note was changed.

The superseding declaration records `reviewed_all=YES`,
`generative_ai_use=NONE`, `external_sources_checked=NONE`, 45 elapsed minutes,
and expertise in academic literature screening and evidence synthesis. The
review is eligible under the frozen protocol, but the correction remains an
owner-relayed attestation rather than an independently signed second reviewer
statement.

## Frozen gate result

All 79 rows were complete and inspectable. The reviewer marked 37 candidates
directly relevant and baseline-novel and 42 not directly relevant; no row was
unverifiable.

| Frozen gate | Observed | Required | Result |
|---|---:|---:|---|
| cases with relevant, baseline-novel evidence | 8/8 | at least 6/8 | pass |
| union role-coverable cases, at most three sources | 5/8 | at least 6/8 | **fail** |
| directly relevant candidate share | 37/79 (46.84%) | at least 25% | pass |
| cases with unique evidence-lane relevant value | 7/8 | at least 4/8 | pass |
| union coverability gain over scope-only | 0 (5 versus 5 cases) | at least +2 | **fail** |

The union-coverable cases were AA02, AA03, AA04, AA07 and AA08. The
evidence-only lane contributed at least one relevant candidate in AA01, AA02,
AA03, AA05, AA06, AA07 and AA08, but those additions did not make any case
coverable that was not already coverable from the scope lane. Because all five
gates were conjunctive, the strict decision is `complete / fail` and
`ab_evaluation_eligible=false`.

## Interpretation

The retrieval-first method found baseline-novel relevant material in every
case and produced a 46.84% title-and-abstract relevance rate. Those observations
are useful, but they do not satisfy the method's actual purpose: assembling
complete required, scope and supporting role sets while demonstrating that the
second query lane adds case-level coverage. The missing role coverage in AA01,
AA05 and AA06 and the zero incremental coverability are blocking failures.

The v6 and v7 cohorts, candidate pools and review contracts differ, so their raw
counts are not a causal head-to-head comparison. The v7 result cannot be used to
rewrite the earlier v6 failure as an improvement claim.

## Limits and decision

This is one reviewer judging frozen titles and abstracts. No external source
was opened, there is no inter-rater agreement, and the result does not establish
full-text source truth, recall, report improvement, Planner-trigger precision,
user value, latency or an SLO.

AA01-AA08 are consumed and must not be rerun or tuned. The failed conjunctive
gate seals role-directed retrieval v7: AB01-AB08 must remain unopened and no v7
adapter, semantic judge, Planner trigger or report connection is authorized.
Production Tool Calling remains in zero-call shadow mode. A future successor
would require a new pre-registered method and fresh development/unseen cohorts;
it may not tune on AA and call the result validation.

## Verification

The returned packet passed the existing strict source, identity, label, role,
note and declaration seams. The complete zero-network suite passes 1,894 tests
plus 657 subtests when pytest's temporary directory is placed in the writable
project tree. The first attempt used the inaccessible Windows user temp root
and produced setup `PermissionError` failures rather than code failures; no
warning was ignored and no assertion or test was relaxed.
