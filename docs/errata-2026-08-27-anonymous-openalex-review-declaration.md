# Erratum: anonymous OpenAlex reviewer declaration copy error

**Date:** 2026-08-27

**Affected result:**
[`results-2026-08-27-evidence-gap-anonymous-openalex-review.md`](results-2026-08-27-evidence-gap-anonymous-openalex-review.md)

## What happened

The first returned `reviewer_declaration.csv` was copied from an unrelated
AI-assisted review. Its labels and row-level notes belonged to this study, but
the declaration row did not. The study owner subsequently relayed the human
reviewer's corrected declaration: all nine rows were reviewed, every source URL
was attempted, no generative AI was used, elapsed time was 20 minutes, and the
reviewer's stated expertise was academic evidence synthesis.

The corrected anonymous alias is `AI01`. It is the reviewer-provided identifier,
not an AI-use declaration; method eligibility is represented separately by
`generative_ai_use=NONE`. The declared limitation is that novelty was assessed
only against the frozen baseline and one CAPTCHA-blocked publisher page was
checked through accessible abstracts and an author manuscript.

## Preserved audit chain

Nothing from the first intake was deleted or silently rewritten. The exact
artifacts are retained locally with these SHA-256 identities:

| Artifact | SHA-256 |
|---|---|
| unchanged nine-row labels | `aaff469be0e10698a5464611343823e91b4f7256b8a881ed6361f3b27d56b296` |
| superseded copied declaration | `eef2fd542819be3709fb322ae8dd0f9828a857b072e64496a7051e809f87e939` |
| superseded strict result | `d6e1b372a2d8bd2e0039068678a25acde7f6072543653a14c93d197ad20d9d62` |
| corrected declaration | `531cdd7b568855208d7fe60f697c2f9791850b962b9c996beec7a9aff1ad9de0` |
| owner-relayed correction record | `449eb9b9da9d916abec6db28ee5e01635a0c8dcfdb0c8610cdac6f29dee3ecdf` |
| corrected strict result | `637a0a5bd1cce17287f56a9822d24582d22efaeb42f3a4c2d859d186c7dc74be` |

The original intake therefore remains inspectable as
`excluded_substantive_ai / not_evaluated`, while the superseding result is
`complete / fail`.

## Corrected effect

The corrected declaration makes the frozen source-value gates evaluable:

| Gate | Observed | Frozen rule | Result |
|---|---:|---:|---|
| Cases with accepted candidates | 4/4 | at least 3/4 | pass |
| Directly irrelevant accepted candidates | 4/9 (44.4%) | at most 5% | fail |
| Cases with relevant, baseline-absent evidence | 4/4 | at least 3/4 | pass |

Because every gate had to pass, the overall decision is `fail`.
`planner_trigger_study_eligible=false` and
`production_connection_authorized=false` remain unchanged.

## Scope

This correction establishes one eligible human review over one frozen
nine-candidate set. It does not establish independent source truth,
inter-reviewer agreement, OpenAlex-wide precision, report improvement or
production Tool Calling readiness.
