# Pre-registration — academic title gate v1 (offline replay)

Registered **2026-10-20**, before any rule was run on the test split below.
The dataset, both label files, the frozen rule and the decision thresholds are
committed with this file. A later doubt about a label is recorded as an
erratum beside the unchanged primary result.

## Question

Does an academic title gate anchored on the user's own words admit fewer
off-topic papers, without rejecting more relevant ones, than the production
gate `source_pipeline._title_matches_topic`?

This is an offline replay over saved candidates. It makes no model or search
request. It says nothing yet about TRL.

## Why

All three TRL misses in [held-out v2](results-2026-10-19-heldout-trl-v2.md)
fell below the floor: hyperloop at 3 and 2 (range 4–6), and space-based solar
power at 2 (range 3–5). The saved hyperloop runs show the academic evidence
behind those scores.

- **Off-topic papers accepted.** Rep 3, which scored 2, accepted eight papers,
  all from arXiv. Six of them share only generic words with the planned search
  phrase `Hyperloop high-speed vacuum tube transportation`: a laser
  microparticle launcher, n-hexane imaging in a shock tube, dislocations under
  high-speed deformation, antennas for high-speed railway. The TRL rationale
  then described "unreviewed arXiv preprints … with no peer-reviewed
  experimental validation". Rep 1 scored 4; six of its eight accepted papers
  were about hyperloop or evacuated-tube transport.
- **Relevant papers rejected.** Across the three runs the gate rejected nine
  relevant titles naming hyperloop, among them `Hyperloop System Optimization`
  and `Hyperloop: A Cybersecurity Perspective`.

The gate counts shared words. Two shared words of four or more letters are
enough, and the adjacency guard runs only for phrases of four or more content
words. The planner expands the user's input into a longer phrase, adding
category words (high, speed, power, transmission) that unrelated titles also
use. A title with one distinctive word, the user's own, has only one shared
word and fails. The word "based", split out of "space-based", matches every
title with a "-based" compound.

## Data

- **Rows:** 494 title-gate decisions from 70 saved held-out runs:
  - `heldout-trl-v1*`: 40 runs, 10 topics;
  - `heldout-trl-v2`: 30 runs, 10 topics.
- **What a row is:** every accepted academic source, and every candidate
  rejected because its title was judged off-topic (arXiv, PubMed, OpenAlex,
  Crossref). Other rejection reasons belong to other gates and are excluded.
  Rows are deduplicated by (topic, title).
- **Gate inputs:** database paths gate on the planned research topic.
  Web/Crossref results gate on the topic and its aliases, as in
  `source_pipeline`.
- **Fidelity:** replaying the production gate reproduces 255 of the 257
  recorded development decisions.

### Split, fixed before any rule was designed

| Split | Topics | Rows | Accepted | Rejected for title |
|---|---|---|---|---|
| Development | the 10 v2 topics, where the hypothesis came from | 257 | 104 | 153 |
| Test | the 10 v1 topics | 237 | 117 | 120 |

Fusion power contributes 66 of the 237 test rows. The per-topic table will
show whether one topic drives the result.

### Labels

- **Who and how:** an AI assistant labelled both splits before any rule was
  designed. It saw topic and title only, with titles cut at 120 characters.
  It did not see the gate decisions. The assistant that then designed the
  rules had therefore read the test titles, but not the gate's decisions on
  them, and no rule has been run on them.
- **Rubric:** 1 when the paper is about the topic technology, a variant, a
  component or subsystem, or its application, deployment or assessment; 0 for
  a different subject that shares only words. The label is topic relevance,
  not quality.
- **Status:** these are development labels, not human gold. Titles cut short
  and recognised from the literature are noted in the label files.
- **Dev counts:** 112 of 257 rows relevant.

## Development results (all variants tried, dev split only)

| Rule | Precision | Recall | Off-topic accepted | Relevant rejected |
|---|---|---|---|---|
| production `_title_matches_topic` | 83.0% (88/106) | 78.6% (88/112) | 18 | 24 |
| R2: the user's own words (two, or one for a one-word input), else one plus the production match | 84.5% | 87.5% | 18 | 14 |
| R3: R2 with the user's phrase matched by the production logic on stemmed words | 85.2% | 87.5% | 17 | 14 |
| R4: R3 with the adjacency guard from three words | 87.5% | 87.5% | 14 | 14 |
| **R5: R4's matcher everywhere, including the expanded topic and Chinese inputs** | **91.3%** (95/104) | 84.8% (95/112) | **9** | 17 |

R5 was declared the last variant before it ran. R5 and the production gate
disagree on 32 development rows. R4 has F1 0.875 and R5 0.880.

R5 is the primary rule for two reasons. The failure under study is off-topic
evidence pulling TRL down, and R5 uses one matcher throughout. Against R4 it
drops five off-topic acceptances and rejects three more relevant titles:

- "Porcine Xenotransplantation in End-Stage Kidney Disease": the user's words
  appear in another order;
- two "robot-assisted … surgery" titles: "robot" does not match "robotic", and
  other words separate "assisted" from "surgery".

R4 is reported descriptively on the test split.

## Frozen primary rule: R5 (`r5_one_matcher`)

- **Core words:** the display topic's words of three or more letters, minus
  function words, the production topic stopwords and "based", lightly stemmed
  (`-ing`, `-es`, `-s`).
- **One core word** (e.g. "hyperloop"): the title must contain it.
- **Several core words:** the title must match the user's phrase, or match the
  expanded topic AND contain at least one core word.
- **No Latin core words** (Chinese input): the title must match the expanded
  English topic.
- **How a phrase match works:** the production logic, applied to stemmed
  content words of three or more letters with "based" excluded:
  - at least two shared words;
  - the adjacency guard from three content words, not four.

## Primary outcome (test split, one evaluation)

Precision and recall of R5 against the production gate on the 237 test rows,
under the same replay. Thresholds compare unrounded proportions.

- **Supported:** precision(R5) ≥ precision(production) **+ 3.0 points** AND
  recall(R5) ≥ recall(production) **− 3.0 points**.
- **Partial:** exactly one of the two holds.
- **Not supported:** neither holds.

Reported alongside, without changing the reading:

- off-topic and relevant-rejected counts;
- test-split replay fidelity;
- a per-topic table;
- the two Chinese-input test topics;
- R4's numbers.

## Maintainer check (secondary)

The maintainer agreed to check part of the AI labels after the test
evaluation.

- **Sample:** every test row on which R5 and the production gate disagree.
  Only these rows can make the two rules' counts differ. If there are more
  than 30, 30 are drawn with `random.Random(20261020)`. Ten agreeing test
  rows are drawn with the same generator. The rows are shuffled and grouped
  by topic.
- **Blind:** the maintainer sees topic and title only, not the AI label or
  either gate's decision, and names the rows that are not about the topic.
- **Reported in a separate dated note:**
  - agreement with the AI labels;
  - the primary comparison recomputed with the maintainer's labels on the
    checked rows.
- **Reading:** the registered reading stays the one on the frozen AI labels.

## What follows

- **Supported:** R5 goes into production only if the recomputed comparison
  also meets both thresholds. It replaces the academic title gate, with
  development rows as unit tests. A small live check comes after that, under
  its own registration: at most eight runs, within the maintainer's free
  model quota, dispatched only on the maintainer's go-ahead.
- **Partial or not supported:** production is unchanged and the result is
  recorded.

## What this cannot establish

- **No TRL effect.** A supported result means the gate keeps cleaner academic
  evidence on saved candidates. It does not show better scores.
- **Selection effects are not modelled.** The replay judges candidates the old
  gate saw. A live run also fills a capped number of academic slots, so the
  papers that end up in the report can change in other ways.
- **AI labels.** The labeller had read the test titles before the rules were
  designed; see Labels.
- **Development only.** Both splits come from consumed benchmark topics, so
  this is development evidence, not a held-out validation.

## Files

| File | sha256 (LF-normalised) |
|---|---|
| `evals/academic_title_gate_v1/build_dataset.py` | `2e19973e53ab0a96eca9b33b82e000c471fe053fa04ce9c82ec57c1f9dc31331` |
| `evals/academic_title_gate_v1/dataset.jsonl` | `d901d651b96d31466f679b745a8d7e65f4a680e32cdf4d1d0abecfa92d62eacc` |
| `evals/academic_title_gate_v1/labels_dev.json` | `433bfc4f46785580c122476ecdca2ece41ed97d5ff5f18451eccab3528e4fd3d` |
| `evals/academic_title_gate_v1/labels_test.json` | `14b981d63f3c12bbb2f46fe66abf497e5dc9e95d272480c304f6c9cb250a873f` |
| `evals/academic_title_gate_v1/rules.py` | `5432ba0ee3c8a140973113adcd24b30a247f8e1c224c2635a1fd3adcc9eac3c9` |
| `evals/academic_title_gate_v1/evaluate.py` | `c22504222d7c0d309d1dfdd79e5130d4a7eaf8c1ef6e98f0067f8dc157b85e36` |

The production gate is replayed from `src/academic_agent/source_pipeline.py`
at `778f27d`.

Reproduce:

```bash
uv run python evals/academic_title_gate_v1/evaluate.py . \
  evals/academic_title_gate_v1/dataset.jsonl \
  evals/academic_title_gate_v1/labels_test.json --split test --rule r5_one_matcher
```
