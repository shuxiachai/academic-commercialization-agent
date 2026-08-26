# Results: decision-readiness baseline over the frozen 30-report corpus

**Completed:** 2026-08-26
**Provider cost:** USD 0; existing benchmark reports only
**Corpus:** 30 delivered reports across ten topics and three repetitions
**Method status:** post-hoc internal AI coding, not human or expert review

## Question and boundary

After the two-person target-user pilot described the product as an
evidence-linked orientation brief rather than a decision-ready memorandum, the
existing 30-report benchmark corpus was screened for the same product-level
properties. The screen asked whether each report contained enough explicit
decision framing to support a named actor at a concrete commercialization gate.

This was not pre-registered before the reports existed, and the coding was
performed by an AI assistant. No external paper, patent, market source, or
customer record was opened. The result is therefore an internal product
diagnostic. It is not an expert label set, a source-truth evaluation, a report
accuracy rate, or evidence that any recommendation was correct.

## Frozen rubric

Each report received `0`, `1`, or `2` on seven dimensions:

1. specific asset and product/application scope;
2. named decision, owner, jurisdiction, horizon, and constraints;
3. reproducible benchmark or validation plan;
4. separation of observed evidence, estimates, and analyst inference;
5. one prioritized commercialization route with alternatives;
6. gated action plan with owner, threshold, cost/time state, and stop criteria;
7. restraint around market extrapolation and patent/FTO claims.

A score of `2` required the complete decision-useful property, not merely a
related sentence or a generic list of recommendations. The same rubric was
applied to all 30 reports after the report paths had been enumerated from the
frozen benchmark summary.

## Observed result

The mean score was `8.7 / 14`, the median was `9 / 14`, and the range was
`6-10 / 14`.

| Dimension | Full (`2`) | Partial (`1`) | Absent (`0`) |
|---|---:|---:|---:|
| Specific asset scope | 0 / 30 | 30 / 30 | 0 / 30 |
| Decision frame | 0 / 30 | 30 / 30 | 0 / 30 |
| Reproducible benchmark plan | 0 / 30 | 29 / 30 | 1 / 30 |
| Evidence-semantics separation | 16 / 30 | 14 / 30 | 0 / 30 |
| Prioritized route | 11 / 30 | 18 / 30 | 1 / 30 |
| Complete gated plan | 0 / 30 | 26 / 30 | 4 / 30 |
| Market/patent restraint | 30 / 30 | 0 / 30 | 0 / 30 |

A separate exact-phrase census found zero reports with an explicit kill
criterion or stop condition, zero with customer-discovery or willingness-to-pay
work, zero with a complete same-workload/head-to-head baseline phrase, and zero
with an explicit budget, capital requirement, unit-economics target, or cost
target. All 30 contained evidence-status language and patent/FTO restraint.

The lexical census is narrower and more reproducible than the rubric, but it
can miss semantically equivalent wording. The rubric is broader, but its AI
coding is not independent. Both point in the same direction: the system is
stronger at evidence restraint than at defining whose decision is being made,
what would change that decision, and when work should stop.

## Product implication

The two target-user observations were not an isolated formatting complaint.
Across the frozen corpus, reports consistently lacked a complete decision
context and a complete gated action plan while consistently preserving market
and patent caveats. The next implementation should therefore add optional,
structured decision context and make absence of that context an explicit
orientation state. It should not change the calibrated scoring formula, make a
heuristic screen blocking, or imply that adding a report template proves user
value.

A later provider-backed canary must be separately authorized and pre-registered.
Even a structurally compliant canary would establish only that the new contract
can be produced, not that target users make better decisions or save time.
