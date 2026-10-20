# TRL compression on the held-out cohort: diagnosis

Date: 2026-10-18 (Australia/Sydney). Source: the 30 completed runs of batch
`heldout-trl-v1-c` ([result](results-2026-10-18-heldout-trl-v1.md)). These
topics are consumed, so this is a **diagnosis, not validation**. Nothing here
shows that a fix works. A fix needs its own protocol and a new cohort.

## Question

Why did no run score above 7, with mature technologies under-scored and
fusion power over-scored?

## Method

Two passes over all 30 runs:

1. **Manual reading** of the scorer's `trl_rationale` and `trl_source_ids`
   for the 9 misses and the 9 on-floor runs.
2. **Keyword tagging** of all 30 rationales and their saved sources. Each
   pattern is listed below, and every count is a lower bound: phrasing
   outside a pattern is missed, as manual reading confirmed for H04 r2/r3
   and H06 r3.

A code-level cap was ruled out first. The only TRL clamp in production code
is the 1–9 label bound.

## Findings

### 1. The TRL 7 label anchors the score

15 of the 20 runs that scored 7 quote the TRL 7 label, "system prototype
demonstrated in operational environment", as their justification. The 9 label,
"actual system proven in operational environment", also contains
"operational environment". Evidence of any real-world deployment is matched
to 7 and not argued past it.

### 2. Scale, cost and adoption are used to withhold 8–9

At least 8 of the 15 runs below or on their floor give scale-type reasons for
staying at 7:

- "not yet multi-manufacturer large-scale production" (floating wind);
- "cost parity has not been achieved" (precision fermentation, 3/3 runs, each
  of which first states that multiple companies have approved commercial
  products);
- "limited to specific jurisdictions rather than global mass adoption"
  (psilocybin);
- "widespread grid-connected commercial revenue … not confirmed" (SMR).

The rubric already forbids this. It says TRL must not require widespread
deployment, that a product approved and being sold is proven in operation at
any volume, and that scale belongs to MRL. The instruction is present but not
followed.

### 3. Market retrieval returns market-size reports, which the rubric discounts

116 of 219 market sources (53%) are market-size or industry-report pages by
title (pattern below). The rubric calls these "NOT a commercial signal" and
also makes market evidence the primary TRL signal. The share is highest where
under-scoring occurred:

- drone medical delivery: 17/17;
- DNA storage: 21/24;
- floating offshore wind: 16/23.

For drone medical delivery, the market queries rewrote "drone" to
"unmanned aerial vehicle" and truncated the topic to "delivery of medical".
Every market source was a general UAV market report. No retrieved or
rejected candidate in any of the three runs mentioned Zipline, the operator
with more than 2 million deliveries. For SMR, no run's evidence named an
operating SMR (HTR-PM, Akademik Lomonosov); one rationale referred only to
"Russian floating reactors" as historical precedent.

### 4. Construction and plans are counted as demonstration

All three over-scored runs (fusion power, 6 against 3–5) cite machines under
construction, expected first-plasma dates (some stale) or planned pilot
plants as "system prototype demonstrated in relevant environment". The
rubric's signal row "pilot programmes or pre-commercial demonstrators → TRL
6–7" does not require that the demonstrator has operated.

## Anchor note

Two psilocybin rationales cite prescribing under Australia's Authorised
Prescriber scheme and a product launched in 2025. That evidence was not
considered when the H04 range (7–8) was anchored, and it would support 8. The
frozen range and the primary result are unchanged. This is recorded so the
anchor's limits are visible.

## Implications for a fix (to be pre-registered separately)

| Mechanism | Direction |
|---|---|
| 1, 2 | Define 7, 8 and 9 by **observable operation**, not by label wording: 7 = a pilot or limited demonstration in the real environment; 8 = qualified or approved and in routine operation for paying users, at any scale; 9 = sustained operation over years or by several independent operators. List scale, cost parity, market share and geographic breadth as MRL or market factors that must not lower TRL. |
| 3 | Make market retrieval seek **deployment and operator evidence**, e.g. operator, customer and deployment-count queries and the topic's own wording, rather than market-size pages. Investigate the query rewriting that dropped "medical supplies". |
| 4 | A demonstrator counts only **once it has operated**. Construction, funding, announcements and target dates are not demonstrations. |

A fix must also be checked against the failure the August protocol called
F1: raising every score. Low-maturity topics must not rise.

## Patterns used for tagging

- Scale/adoption/cost: `widespread`, `mass production|adoption`,
  `large-scale (mature|commercial|production)`, `at scale`, `cost parity`,
  `multi-manufacturer`, `limited to specific`, `early commercialization`,
  `initial commercial`, `rather than widespread|global|commodity`, and the
  Chinese equivalents.
- TRL-7 label: `prototype demonstrated in (an) operational` and its Chinese
  form.
- Future-as-demonstration: `under construction`, `constructing`,
  `is building`, `expected by|in 20xx`, `first plasma expected`, `planned`.
- Market-size titles: `market size|report|share|trends|forecast|analysis|outlook|research`,
  `research report`, `CAGR`, `billion`, and the Chinese equivalents.
