# Result: role-directed retrieval v7 AA development live run

Date: 2026-09-02 (Australia/Sydney)

Status: provider and mechanical execution completed; source value not evaluated;
AA01-AA08 consumed; AB01-AB08 unopened; production disconnected

## Authorized identity and scope

The owner separately authorized this run on merged revision
`2a61c32d4693f4f9a44965312c378dc8f14fb308` and frozen fixture SHA-256
`9a91746d0a77fee6d57bfc91ae4329ab78a89109fca6f35171d56c0f3ee95761`.
The authorization permitted only the sixteen ordered AA01-AA08 anonymous
OpenAlex Works requests, with a USD 0.02 provider-reported soft stop. It forbade
retry, redirect, model calls, repair, recovery, supplementary search, access to
AB01-AB08, and production connection.

The default zero-network preflight first reproduced 8/8 cases, 16/16 lane
identities, the exact fixture hash, and all six frozen implementation hashes.
The combined v7 suite passed 27/27 immediately before the provider run. The
environment contained no `OPENALEX_API_KEY`, and the write-once output directory
was fresh.

## Provider execution

The live runner completed the frozen sequence without retry or recovery:

| Measure | Observed |
|---|---:|
| Ordered OpenAlex requests | 16/16 |
| Successful lane journals | 16/16 |
| Completed case portfolios | 8/8 |
| Provider rows | 96 |
| Provider candidates | 84 |
| Provider rejections | 12 |
| DOI/URL-deduplicated candidates | 79 |
| Blank human-review rows | 79 |
| Provider-reported cost | USD 0.016 |
| Total request latency | 23,540.564 ms |
| Per-request latency, min / median / max | 708.016 / 1,523.273 / 2,503.959 ms |
| Model calls | 0 |

The candidate boundary by case was:

| Case | Provider candidates | Provider rejections | Unique candidates |
|---|---:|---:|---:|
| AA01 | 11 | 1 | 11 |
| AA02 | 11 | 1 | 10 |
| AA03 | 9 | 3 | 7 |
| AA04 | 10 | 2 | 9 |
| AA05 | 10 | 2 | 10 |
| AA06 | 12 | 0 | 12 |
| AA07 | 11 | 1 | 10 |
| AA08 | 10 | 2 | 10 |

These are transport and portfolio counts, not relevance labels. In particular,
the 79-row review boundary contains no populated relevance, novelty, role, or
reviewer-note fields.

## Artifact audit

The artifact index covers 29 files: the manifest, final execution, three CSV
boundaries, sixteen lane journals, and eight case portfolios. Independent local
recomputation found zero SHA-256 mismatches. All sixteen provider request IDs
and all sixteen idempotency keys were unique; every lane had inspectable
provider cost. The execution reports `serialized_boundary_complete=true`,
`source_lock_state=not_created`, `human_review_state=not_prepared`, and
`source_value_state=not_evaluated`.

Selected top-level hashes are:

| Artifact | SHA-256 |
|---|---|
| `manifest.json` | `221e874252ea010fb60fe253a7aaa06a115f0dc2e38eb2dffac48ccfc6863d7d` |
| `execution.json` | `50aeddf9ec2604b12cdc62eb8ae2949c056ce9feeb0a06a60cc3a68ccdcd2506` |
| `provider-rows.csv` | `5f01e459e612d10778925da5f3a2b478eb1a492635212dc80e82b1712513ec0b` |
| `unique-candidates.csv` | `1a11206970c8d751de01a896f8f36ef4f904d8ef146f9fbcdd87545b25bd21af` |
| `review.csv` | `2a62f9b3367413c61f87553b184356eb4c3dfcbef2d25beac14fb859d0210719` |
| `artifact-index.json` | `7ff4d2a86d19caac5e2a73177870f77540ec19a431bc42e3f321324830bf56bc` |

The authoritative write-once directory remains local at
`outputs/openalex-role-directed-v7-aa-live-2026-09-02/`. A later source-lock
stage must bind these exact bytes rather than reconstructing or rerunning AA.

## Post-artifact Windows stdout defect

After `execute_live_study()` had written every aggregate and indexed artifact,
the CLI attempted to print the returned object through a strict Windows GBK
text stream. One provider title contained U+2022 BULLET, so the final
`print()` raised `UnicodeEncodeError` and the process exited with code 1. The
exception happened after the complete result was durably committed; the
execution artifact itself is `completed` and no provider retry was attempted.
AA must not be rerun to obtain a cosmetic zero exit code.

A zero-network regression test now sends the same character through the CLI
JSON projection under strict GBK. Re-injecting the original non-ASCII stdout
projection made that test fail with the observed exception. The repair escapes
non-ASCII code points only in stdout while preserving original UTF-8 text in the
write-once artifacts. This operational repair does not alter the frozen query,
provider result, portfolio, cost, or any artifact hash above.

## Decision

The frozen provider and mechanical gates passed: OpenAlex compatibility,
bounded one-attempt accounting, durable request ordering, complete row and
lineage serialization, zero model calls, and production isolation were all
observed for this one AA run. This does not pass a human candidate-value gate.

AA01-AA08 are now consumed development evidence and may not be tuned on or
rerun as validation. AB01-AB08 remain unopened. The next permitted step is a
separately implemented source lock and eligible label-blind human review of the
79 frozen candidates. Only if all five pre-registered human gates pass may a
separate AB evaluation be considered. This result does not authorize a semantic
judge, Planner trigger study, report connection, or production Tool Calling.

## Explicit non-claims

This run does not establish source relevance, novelty, role coverability,
candidate precision, evidence-lane incremental value, report improvement,
planner-trigger precision, user value, recall, an SLO, or production readiness.
The latency distribution contains sixteen observations and is not a p95 claim.
