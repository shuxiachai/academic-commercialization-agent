# Result: returned review for the anonymous OpenAlex study

**Date:** 2026-08-27

**Live execution:**
[`results-2026-08-27-evidence-gap-anonymous-openalex-live.md`](results-2026-08-27-evidence-gap-anonymous-openalex-live.md)

**Review boundary:**
[`results-2026-08-27-evidence-gap-anonymous-openalex-review-implementation.md`](results-2026-08-27-evidence-gap-anonymous-openalex-review-implementation.md)

**Declaration erratum:**
[`errata-2026-08-27-anonymous-openalex-review-declaration.md`](errata-2026-08-27-anonymous-openalex-review-declaration.md)

**Protocol status:** `complete`

**Decision:** `fail`

**Production connection authorized:** no

## Outcome

The returned Schema v2 packet preserved the exact source lock, packet manifest,
four baseline contexts and all nine candidate identities. All nine rows were
completed, every URL was declared attempted, and the strict intake found no
incomplete row, uninspectable row, method-coverage issue or identity drift.

The first declaration row was copied from an unrelated AI-assisted review, so
the initial strict intake correctly returned
`excluded_substantive_ai / not_evaluated`. The study owner then relayed the
human reviewer's corrected declaration: `reviewed_all=YES`,
`generative_ai_use=NONE`, `external_sources_checked=ALL_ATTEMPTED`, and 20
minutes elapsed. The original bytes and result remain preserved, while the
superseding strict intake is `complete / fail`.

The returned files remain gitignored. Their audit identities are:

| Artifact | SHA-256 |
|---|---|
| unchanged `labels.csv` | `aaff469be0e10698a5464611343823e91b4f7256b8a881ed6361f3b27d56b296` |
| superseded copied declaration | `eef2fd542819be3709fb322ae8dd0f9828a857b072e64496a7051e809f87e939` |
| superseded strict result | `d6e1b372a2d8bd2e0039068678a25acde7f6072543653a14c93d197ad20d9d62` |
| corrected declaration | `531cdd7b568855208d7fe60f697c2f9791850b962b9c996beec7a9aff1ad9de0` |
| correction record | `449eb9b9da9d916abec6db28ee5e01635a0c8dcfdb0c8610cdac6f29dee3ecdf` |
| corrected strict result | `637a0a5bd1cce17287f56a9822d24582d22efaeb42f3a4c2d859d186c7dc74be` |

## Source-value gates

The corrected declaration makes all frozen gates evaluable:

| Gate | Observed | Frozen rule | Result |
|---|---:|---:|---|
| Cases with accepted candidates | 4/4 | at least 3/4 | pass |
| Directly irrelevant accepted candidates | 4/9 (44.4%) | at most 5% | fail |
| Cases with relevant, baseline-absent evidence | 4/4 | at least 3/4 | pass |

All gates had to pass, so the provider decision is `fail`.
`planner_trigger_study_eligible=false` and production authorization remains
false.

## Declared limitation

One publisher page required a CAPTCHA. The return says that row was instead
checked through the full OpenAlex abstract and an accessible author manuscript.
It also states that no independent source-truth validation was performed. This
does not change the AI-use exclusion and must not be promoted into a source-truth
or provider-precision claim.

## Decision

Retain the declaration correction, returned packet and both strict results as
transparent evidence. Do not rerun the four provider requests: the exact
candidate set is already locked. The anonymous OpenAlex path missed its source-
value gate and must not advance to planner-trigger measurement or production.

Any future retrieval or quarantine method must treat these nine labels as
development evidence, freeze a different unseen challenge before evaluation,
and preserve the existing production disconnection. Tuning on these rows and
reporting the same rows as validation would not be an independent result.

## Explicit non-claims

This single human review does not establish independent source truth,
inter-reviewer agreement, OpenAlex-wide precision, report improvement, user
utility, adoption, cost savings, an SLO or production Tool Calling readiness.
