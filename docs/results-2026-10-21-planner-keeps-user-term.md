# Planner keeps the user's term: academic shortfalls from the live gate check removed

Date: 2026-10-21 (Australia/Sydney). A **development check**, not registered,
of the two corrections that follow the
[academic gate live check](results-2026-10-21-academic-gate-live-v1.md).
No crew run and no web search were used; the planner calls ran on
`qwen3.8-27b`.

## The corrections

1. **Planner prompt.** The prompt asked for "established scholarly vocabulary
   rather than repeating the same words". It now asks the planner to keep the
   input's own name for the technology in the search phrase, coined or
   brand-like terms included. Alternative terms go in the aliases.
2. **Shortfall top-up.** This runs only when academic retrieval would fail
   the minimum of three, and only after the web fallback:
   - candidates the primary lanes already fetched are converted again with
     the earlier title gate, up to the minimum;
   - each source admitted this way says so in its credibility reason;
   - the audit lists them under `[Relaxed-Title-Gate]`.

## Check

**Inputs.** 28 inputs, each planned twice with the new prompt:

- the 20 consumed held-out topics;
- a request ("We are building an LLM for scriptwriting; assess its value");
- an abbreviation ("LLM");
- two Chinese inputs;
- four other English topics.

**Fill.** For each input, the first plan's candidates were then fetched live
from OpenAlex, Semantic Scholar, PubMed and arXiv. Both gates filled the
production slots from those candidates, as in Part A of the live check.

| | Old prompt, live plans (live check) | New prompt |
|---|---|---|
| Consumed topics delivering 8 academic sources under R5 | 18 / 20 | **20 / 20** |
| hyperloop | 0 (plan: "Low-pressure tube transportation systems") | **8** (plan: "Hyperloop transportation system") |
| vertical farming for fresh produce | 1 (plan drifted to controlled-environment agriculture) | **8** |

**Plans.**

- All 20 topic plans kept the user's words, and the anchor was set for every
  English topic.
- The request and the abbreviation were still rewritten ("Large language
  models for scriptwriting", "Large Language Models"). Both left the anchor
  off, as designed, and delivered 8 sources each.
- One input failed under both gates: "help me assess the commercial
  potential of hyperloop". The plan kept "commercial potential" in the
  phrase, and the old gate also delivered 0. The new prompt does not
  remove that kind of request framing.

**Spot check** of delivered titles, by an AI assistant:

| Topic | Relevant | Off-topic |
|---|---|---|
| hyperloop | 7 / 8 | CERN ALICE's "Hyperloop" analysis software |
| fusion power | 6 / 8 | fibre fusion splicing; data fusion for photovoltaic forecasting, the known two-word weakness of R5 |
| vertical farming | 8 / 8 | — |

**Top-up.** Covered by unit tests:

- it runs after the web fallback;
- it stops at the minimum;
- it skips duplicates;
- it marks what it admits;
- a run that already meets the minimum never reaches it.

It did not trigger in the check above.

## Limits

- One live sample per input. Retrieval and planning vary between calls.
- No crew run, so no TRL effect is shown.
- Spot checks and labels are by an AI assistant.
- A request that keeps assessment words in the plan can still come up short.
