# Academic title gate live check v1: the gate cleans what it is given, but the live planner decides what that is

Date: 2026-10-21 (Australia/Sydney). Protocol:
[pre-registration](prereg-2026-10-21-academic-gate-live-v1.md).

- **Part A** ran at the protocol commit (`0c99896`, pushed before it ran).
- **Part B** ran at `c2033ee`, the `main` merge of the protocol. That commit
  also carries #200, a change to `ablation.py` only. The batch was
  `academic-gate-live-v1`, with `LLM_PROVIDER=qwen` and `QWEN_MODEL=qwen3.8-27b`.

## Part A — live academic retrieval under both gates (registered)

The 20 frozen plans were fetched live once, and both gates filled the
production slots from the same responses.

| Measure | New gate | Old gate | Reading |
|---|---|---|---|
| A1 off-topic papers delivered | **13** | 20 | **cleaner delivered evidence** (threshold: ≤ 15) |
| A2 topics below 3 sources | 0 | 0 | no shortage increase detected |
| A3 relevant papers delivered | 146 | 140 | no relevance loss flagged |
| Papers delivered | 159 | 160 | — |

- **Where it helped:** hyperloop went from 2 off-topic papers to 0; only 1
  of its 8 titles is shared between the arms. Drone delivery went from 4 to
  1, and space-based solar power from 2 to 1 (7 delivered).
- **Where it hurt:** enhanced geothermal went from 0 to 1, and
  battery-electric aircraft from 1 to 2.
- **Labels:** 143 of the 186 delivered pairs reuse title gate v1 labels.
  The other 43 were labelled blind to the arm.

## Part B — eight live runs, production configuration (registered)

| Run | Status | Academic sources | Off-topic | TRL (range) |
|---|---|---|---|---|
| space-based solar power, rep 1 | success | 8 (6 from the academic web fallback) | 2 | 5 (3–5) ✓ |
| space-based solar power, rep 2 | success | 3 | 2 | 4 (3–5) ✓ |
| space-based solar power, rep 3 | success | 3 | 2 | 4 (3–5) ✓ |
| space-based solar power, rep 4 | success | 3 | 2 | 4 (3–5) ✓ |
| hyperloop, reps 1–4 | `error_sources` | 1, 2, 2, 2 (minimum is 3) | — | none |

1. **B1 (primary for Part B): 4 / 8 in range.**
   - **Registered reading:** for ≤ 4 / 8 it is "the misses persist; academic
     retrieval is not the lever that fixes them". That is recorded as
     registered.
   - **What happened instead:** the reading's premise does not hold. Every
     run that produced a score landed in range: space-based solar power went
     4 / 4, against 2 / 3 in v2. The four hyperloop runs produced no score;
     each stopped at the academic minimum before the crew ran.
2. **B2: off-topic share, 8 / 17 (47%).** The prediction of ≤ 20% was not
   met.
   - **Reps 2–4 delivered the same three sources:** a speculative
     multi-topic document that names "Space-Based Solar Power Supply"
     (counted relevant under the title gate v1 erratum), a
     planetary-settlement treatise, and a solar-electric UAV paper.
   - **Rep 1 had more good evidence, not less:** its primary lanes found
     only two papers, so the academic web fallback ran and supplied six
     on-topic sources.
3. **B3: shortage.** Four runs, all hyperloop, failed below 3 academic
   sources. One run, space-based solar power rep 1, used the academic web
   fallback.
4. **B4: other measures.**
   - **Completion:** 4 / 8.
   - **Reports:** every completed run had the required sections and 0
     uncited numeric lines.
   - **Cost:** 285,072 Crew-node tokens in all (80,812, 67,923, 71,058 and
     65,279). The failed runs used no crew.

## Why hyperloop failed (exploratory, after the batch)

`benchmark.py` does not keep the diagnostics of a failed source collection,
so the plan was reproduced: two planner calls under `qwen3.8-27b`.

- **The plan:** both calls returned "Low-pressure tube transportation
  systems", with aliases "Vacuum-tube transit technology" and "Hypersonic
  ground transport infrastructure". The word the user typed was never
  searched.
- **The candidates:** OpenAlex returned well-cited papers on other subjects,
  arXiv 32 off-topic titles, and Semantic Scholar nothing.
- **Both gates failed:** from these candidates the new gate kept 0 papers
  and the old gate 1, a multi-UAV transport paper. In held-out v2 the
  `qwen3.8-max` planner kept "Hyperloop" in the phrase three times out of
  three.

The same check across all 20 consumed topics, with one live `qwen3.8-27b`
plan each, gave papers delivered by the new gate against the old gate:

| Topics | Plan | New gate | Old gate |
|---|---|---|---|
| 18 | — | 8 | 8 |
| hyperloop | "Low-pressure tube transportation systems" | 0 | 1 |
| vertical farming for fresh produce | "Controlled environment agriculture for leafy greens" | **1** | 8 |

The vertical farming plan drifted away from the user's words. The papers it
retrieved name controlled-environment agriculture, which R5 rejects without
the user's terms, while the old gate admitted them. Production as deployed
would stop that topic at the academic minimum: a regression caused by the
gate, triggered by planner drift.

## Deviations

- **One score seen early.** Space-based solar power rep 2's TRL (4) appeared
  in the run log before the B2 labels were written. The other runs' scores
  were read after labelling.
- **Errata applied in B2.** B2 uses the title gate v1 errata as registered,
  which counts the multi-topic document as relevant. Without that erratum
  the share is 11 / 17.

## Reading

- **The gate works on its input.** It removes off-topic papers from the
  candidates it receives: the offline replay, and Part A with the v2 plans.
- **Live, the planner sets the candidates.** The `qwen3.8-27b` planner can
  paraphrase the user's term away (hyperloop) or drift from it (vertical
  farming). A gate anchored on the user's words then has little or nothing
  to accept.
- **Production consequence:** the deployed combination can fail a run that
  the old gate would have completed. Two corrections follow in a separate
  change:
  - the planner keeps the user's own technology term in the search phrase;
  - a shortfall below the academic minimum is topped up with the old gate
    rather than failing the run.
- **Space-based solar power:** it scored in range four times under
  `qwen3.8-27b`, but on thin academic evidence except when the web fallback
  ran.

## What this cannot establish

- **Attribution.** Part B cannot separate gate, model and planner; all three
  changed since v2.
- **Size.** Eight runs on two consumed topics; development evidence only.
- **Exploratory diagnosis.** It was done after the batch, with one or two
  planner calls per topic.
- **AI labels.** The labels are from an AI assistant.

## Files

- `evals/academic_gate_live_v1/part_a_results.json`,
  `labels_part_a.json` and `report_part_a.py` hold Part A's delivered
  sources, labels and measures.
- `evals/academic_gate_live_v1/labels_part_b.json` holds labels for the
  Part B sources not labelled before.
