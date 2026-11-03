# Academic title gate v1: R5 cuts off-topic acceptances from 19 to 12 with recall unchanged

Date: 2026-10-20 (Australia/Sydney).

- **Protocol:** [pre-registration](prereg-2026-10-20-academic-title-gate-v1.md),
  with its frozen files pushed as commit `694a13e` (#243) before the test split
  was run.
- **Run:** the test split was evaluated once.
- **Scope:** an offline replay. No model or search request; no TRL.

## Primary measure

The test split is 237 title-gate decisions over the ten v1 topics, 123 of them
relevant by the AI labels.

| Rule | Accepted | Precision | Recall | Off-topic accepted | Relevant rejected |
|---|---|---|---|---|---|
| production `_title_matches_topic` | 115 | 83.5% (96/115) | 78.0% (96/123) | 19 | 27 |
| **R5** (registered) | 108 | **88.9%** (96/108) | 78.0% (96/123) | **12** | 27 |

Precision rose 5.4 points (threshold: +3.0). Recall did not change (threshold:
at most 3.0 points lost). By the registered rule, the result is **supported**.

## Secondary measures

1. **The deciding rows.** The rules disagree on 11 of 237 rows. By the labels,
   R5 is right on 9:
   - **Off-topic papers R5 rejects** (7, all accepted by production):
     - direct air capture: carbon capture and storage, "the way forward";
     - drone delivery: three general UAV surveys;
     - fusion power: "Back to the future - from nuclear energy to AI", and an
       NMR study of membrane fusion proteins;
     - precision fermentation: plant-based meat and dairy fermentation.
   - **Relevant papers R5 accepts** (2, rejected by production):
     - "Fusion power.";
     - a cross-cultural study of the stigma of fusion power.

     Against the planned phrase `nuclear fusion energy generation`, the first
     shares only "fusion". The second fails the adjacency guard. Both match the
     user's words.
   - **Relevant papers R5 loses** (2, accepted by production):
     - "Unmanned aerial vehicle (drones) in public health: A SWOT analysis",
       lost to a stemming flaw (see Exploratory);
     - "Nuclear phenomena in low-energy nuclear reaction research", which
       names neither "fusion" nor "power".
   - **Sign test (not registered):** an exact test on the 11 rows gives
     p = 0.065, two-sided. The direction matches development, but the
     evidence is 11 rows.

2. **Per topic.**

   | Topic | Rows | Relevant | Production accepted (off-topic) | R5 accepted (off-topic) | Relevant kept, production → R5 |
   |---|---|---|---|---|---|
   | fusion power | 66 | 27 | 25 (9) | 24 (7) | 16 → 17 |
   | small modular reactors for grid electricity | 34 | 10 | 10 (0) | 10 (0) | 10 → 10 |
   | 人工光合作用制备太阳能燃料 | 23 | 6 | 6 (1) | 6 (1) | 5 → 5 |
   | 漂浮式海上风电 | 23 | 19 | 17 (2) | 17 (2) | 15 → 15 |
   | DNA data storage | 19 | 15 | 13 (0) | 13 (0) | 13 → 13 |
   | precision fermentation for dairy proteins | 17 | 8 | 9 (1) | 8 (0) | 8 → 8 |
   | direct air capture of carbon dioxide | 15 | 8 | 9 (1) | 8 (0) | 8 → 8 |
   | implantable brain-computer interfaces for paralysis | 15 | 13 | 4 (0) | 4 (0) | 4 → 4 |
   | psilocybin therapy for treatment-resistant depression | 13 | 10 | 12 (2) | 12 (2) | 10 → 10 |
   | drone delivery of medical supplies | 12 | 7 | 10 (3) | 6 (0) | 7 → 6 |

   Six topics are unchanged. With any one topic left out, R5's precision gain
   is +3.5 to +6.4 points and its recall change −1.0 to +0.9. No single topic
   carries the result. Drone delivery contributes the most: 3 of the 7
   off-topic papers removed.

3. **Chinese-input topics.** On both, R5 decided every row as production did;
   for these topics it matches against the planned English phrase.

4. **R4 (descriptive).** 111 accepted, precision 86.5% (96/111), recall 78.0%,
   15 off-topic. R5 removes three off-topic papers that R4 keeps and loses no
   relevant one.

5. **Replay fidelity.** 235 of 237 recorded decisions are reproduced (dev: 255
   of 257). One row was accepted in two runs and rejected in one; it replays as
   rejected. One row recorded as accepted replays as rejected.

## Label errata

The labeller saw titles cut at 120 characters. Of the 92 rows with longer
titles, five were labelled 0 although the hidden part names the topic:

| Row | Hidden part | Label | Under the rubric |
|---|---|---|---|
| test-0361 | "… A case study of nuclear fusion energy" | 0 | 1 |
| test-0454 | "… All-Organic Photocatalyst for Artificial Photosynthesis of H2O2" | 0 | 1 |
| test-0303 | a Zenodo record whose title field is a pasted chatbot reply (4,523 characters) describing a "Constraint-Grid Fusion Platform" | 0 | 1 by topic, though not a paper |
| dev-0106 | "… Compared with Robot-Assisted Thoracic Surgery" | 0 | 1 |
| dev-0145 | "Space-Based Solar Power Supply", one of eight parts of a speculative scheme | 0 | 1 under the fringe-preprint convention |

Both rules accept all three test rows. With the errata applied:

| Split | Production precision | Production recall | R5 precision | R5 recall |
|---|---|---|---|---|
| Test | 86.1% | 78.6% | 91.7% | 78.6% |
| Dev | 84.9% | 78.9% | 92.3% | 84.2% |

The registered reading is unchanged.

## What both rules still miss (descriptive)

Both rules reject the same 25 relevant test titles.

- **19 share at most one word with the user's phrase and the planned phrase.**
  They name the technology in other words:
  - brain-computer interfaces (9 of 13 relevant titles): neuroprosthesis,
    tetraplegia, brain-spine interface;
  - fusion power (8): plasma regime, fusion devices, cold fusion.
- **6 share two or more words but fail the adjacency guard.** No matched pair
  appears in the topic's order. Examples: "Offshore Floating Wind Turbine"
  against `floating offshore wind`, and "DNA-Based Information Storage" against
  "DNA data storage".

R5 is strict about single words on purpose. Five of its seven off-topic
fusion acceptances use "fusion" and "power" in other senses, such as data
fusion for power systems. Accepting "fusion" alone would let more of them in.

The remaining fusion acceptance is the Zenodo record above. Its title field
holds a 4,523-character chatbot reply, which no title-word rule can screen; a
title-length check could.

## Exploratory, found after the evaluation (not a result)

R5's test errors show a stemming flaw. The stemmer cuts "-es" after any letter,
so "drones" becomes "dron" and "interfaces" becomes "interfac". Neither then
matches "drone" or "interface".

The variant tried was a plural-only stemmer: "-ies" becomes "-y", "-es" is cut
only after s, x, z, ch or sh, and otherwise "-s" is cut.

- **Development:** no decision changes.
- **Test:** five decisions change; precision 88.5%, recall 81.3%.
  - Four relevant titles are accepted: the drone SWOT analysis, and three
    brain-spine or brain-machine interface papers.
  - One general UAV survey is accepted.

It was found by reading test-split errors, so it is a lead, not a validated
result.

## Maintainer check

Pending.

- **Sample:** all 11 deciding rows plus 10 agreeing rows, 21 in all, in
  `evals/academic_title_gate_v1/maintainer_check_sample.json`.
- **Method:** the maintainer labels the sample blind.
- **Report:** a separate dated note.

## Reading

**What R5 gives.** R5 gives cleaner academic evidence on the test topics. It
removes 7 of the production gate's 19 off-topic papers and keeps the same
number of relevant ones.

**Recall.** On development, R5 kept 7 more relevant titles than production,
6 of them for the one-word input `hyperloop`. It also dropped three
evacuated-tube papers that never say "hyperloop", because a one-word input now
requires that word. The test split has no one-word input, and recall did not
move there.

**Size.** The gain is modest in absolute terms and rests on 11 deciding rows.

**Production.** Production stays unchanged until the maintainer check is in.
Under the protocol, R5 ships only if the comparison recomputed with the
maintainer's labels also meets both thresholds. The stemming fix is not part
of the registered rule; if it ships with R5, it is a separate, declared change.

## What this cannot establish

- **No TRL effect.** Cleaner candidates on saved runs do not show better
  scores. That needs the live check described in the protocol.
- **Selection effects are not modelled.** A live run fills capped academic
  slots, so the papers in a report can change in other ways.
- **AI labels.** The labeller had read the test titles before the rules were
  designed, and five labels are corrected above.
- **Development only.** Both splits are consumed benchmark topics.

## Files and reproduction

- `evals/academic_title_gate_v1/report.py` prints:
  - the deciding rows;
  - the per-topic and leave-one-topic-out tables;
  - the sign test;
  - the maintainer sample;
  - the exploratory stemmer check;
  - the errata sensitivity.

  It was written after the evaluation. The primary numbers come from the
  frozen `evaluate.py`.
- `evals/academic_title_gate_v1/maintainer_check_sample.json` holds the
  registered maintainer-check sample.

```bash
uv run python evals/academic_title_gate_v1/evaluate.py . \
  evals/academic_title_gate_v1/dataset.jsonl \
  evals/academic_title_gate_v1/labels_test.json --split test --rule r5_one_matcher
uv run python evals/academic_title_gate_v1/report.py .
```
