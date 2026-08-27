# Result: returned review for the anonymous OpenAlex study

**Date:** 2026-08-27

**Live execution:**
[`results-2026-08-27-evidence-gap-anonymous-openalex-live.md`](results-2026-08-27-evidence-gap-anonymous-openalex-live.md)

**Review boundary:**
[`results-2026-08-27-evidence-gap-anonymous-openalex-review-implementation.md`](results-2026-08-27-evidence-gap-anonymous-openalex-review-implementation.md)

**Protocol status:** `excluded_substantive_ai`

**Decision:** `not_evaluated`

**Production connection authorized:** no

## Outcome

The returned Schema v2 packet preserved the exact source lock, packet manifest,
four baseline contexts and all nine candidate identities. All nine rows were
completed, every URL was declared attempted, and the strict intake found no
incomplete row, uninspectable row, method-coverage issue or identity drift.

The declaration also identified the reviewer as an AI system and recorded
`generative_ai_use=MOST_OR_ALL`. The protocol was frozen before the packet was
returned and allows no substantive generated judgment in an eligible human
value review. The strict result is therefore
`excluded_substantive_ai / not_evaluated`; completion and source attempts do not
override that exclusion.

The returned files remain gitignored. Their audit identities are:

| Artifact | SHA-256 |
|---|---|
| `labels.csv` | `aaff469be0e10698a5464611343823e91b4f7256b8a881ed6361f3b27d56b296` |
| `reviewer_declaration.csv` | `eef2fd542819be3709fb322ae8dd0f9828a857b072e64496a7051e809f87e939` |
| strict result JSON | `d6e1b372a2d8bd2e0039068678a25acde7f6072543653a14c93d197ad20d9d62` |

## Descriptive labels only

The ineligible form labelled five of nine candidates directly relevant and
four directly irrelevant. All five relevant rows were also labelled materially
absent from the frozen baseline, spanning D01-D04. These counts are retained as
diagnostic observations, not as a human-value result.

If the labels were counterfactually treated as eligible, the implied
wrong-source rate would be `4/9 = 44.4%`, far above the frozen 5% maximum, even
though all four cases would contain at least one `YES/YES` row. The real strict
summary intentionally does not compute those gates: all three threshold results
remain `not_evaluated`, `planner_trigger_study_eligible=false`, and production
authorization remains false.

## Declared limitation

One publisher page required a CAPTCHA. The return says that row was instead
checked through the full OpenAlex abstract and an accessible author manuscript.
It also states that no independent source-truth validation was performed. This
does not change the AI-use exclusion and must not be promoted into a source-truth
or provider-precision claim.

## Decision

Retain the returned packet and strict result as transparent negative evidence.
Do not rerun the four provider requests: the exact candidate set is already
locked. The next valid gate remains one independently completed, source-grounded
review whose declaration satisfies the frozen human-review eligibility rules.
Only then may the wrong-source and novel-evidence gates be evaluated. Even a
pass would authorize only a separately pre-registered planner-trigger precision
study, not production Tool Calling.

## Explicit non-claims

This return does not establish human source review, source truth, OpenAlex-wide
precision, novel-evidence yield, planner precision, report improvement, user
utility, adoption, cost savings, an SLO or production Tool Calling readiness.
