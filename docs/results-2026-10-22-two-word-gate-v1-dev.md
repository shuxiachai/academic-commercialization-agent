# Two-word title gate v1: development comparison, no rule advanced

**Date:** 2026-10-22.
**Status:** development only. No pre-registration was written and the test
split was not read, because no candidate rule met the bar on dev.
**Production:** unchanged (R5 with the plural stemmer).

## Question

For a two-word input such as "fusion power", R5 accepts any title that
contains both words, wherever they stand. Fusion power accepted data-fusion
papers about power systems this way. Would requiring the two words to stand
together, or nearly so, remove mostly off-topic papers?

## Method

- **Topics:** twelve two-content-word inputs (`evals/two_word_gate_v1/topics.json`).
  - Fusion power was fixed to dev. The other eleven were shuffled with seed 20261021.
  - Dev: fusion power, carbon capture, quantum computing, wave energy, tidal power, green hydrogen.
  - Test: edge computing, smart grid, smart glass, digital twin, gene therapy, swarm robotics.
- **Plans:** one frozen `qwen3.8-27b` plan per topic (`plans.json`).
- **Pool:** live responses from the primary academic lanes, collected with
  `collect_pool.py` and the production clients and row counts.
  - The lanes are OpenAlex recent, cited and per alias, plus Semantic Scholar, PubMed and arXiv.
  - OpenAlex was fetched on 2026-10-22 after the anonymous budget reset, with no refusals.
  - Semantic Scholar refused anonymous requests for 9 of 12 topics, as it does in production.
  - Total: 1,841 rows.
- **Selection** (`label_set.py`): the 240 rows (dev 152, test 88) that R5
  accepts on some lane while the anchor's two words are not adjacent in order
  in the stemmed title. Every candidate rule only removes rows, so it agrees
  with R5 on every other row.
- **Labels** (`labels.json`): by an AI assistant, on the title gate v1 rubric.
  - Inputs: the topic, the full title and the first 220 characters of the abstract.
  - Order: shuffled, blind to every rule decision.
  - Both splits were labelled. Only dev was read.
- **Rules** (`rules.py`):
  - W0: the two words adjacent in the title.
  - W1: at most one word between them.
  - W0+A and W1+A: either of the above, or the adjacent pair anywhere in the abstract.
- **Bar, set before the dev comparison:** at least 5 rows removed, with off-topic and on-topic removals at a ratio of at least 2:1.

## Result on dev

| Rule | Removed | Off-topic | On-topic | Off:on |
|---|---:|---:|---:|---:|
| W0 | 152 | 71 | 81 | 0.9:1 |
| W1 | 125 | 67 | 58 | 1.2:1 |
| W0+A | 138 | 69 | 69 | 1.0:1 |
| W1+A | 115 | 67 | 48 | 1.4:1 |

Off-topic and on-topic papers removed by W1+A, by topic:

| Topic | Off-topic | On-topic |
|---|---:|---:|
| fusion power | 29 | 9 |
| wave energy | 23 | 0 |
| green hydrogen | 6 | 12 |
| carbon capture | 4 | 11 |
| quantum computing | 3 | 5 |
| tidal power | 2 | 11 |

No rule meets the bar.

## Reading

**What separates the off-topic papers.** The removals that help come from
topics whose first word has several senses:
- "fusion": data fusion, image fusion, laser powder bed fusion;
- "wave": electromagnetic, plasma and acoustic waves.

Where the first word is specific, the same rules mostly remove relevant work
that phrases the topic differently:
- "power generation from tidal energy";
- "tidal current turbine power generation";
- "CO2 capture by porous carbon".

Word position does not carry the sense distinction.

**A narrower variant that this data set cannot test.** One rule would apply W1+A
only when the second anchor word is "power" or "energy". On dev it removes 54
off-topic papers and 20 relevant ones (2.7:1). However:
- it was found by reading these dev results;
- no test topic has that shape, so this data set cannot test it;
- tidal power, the third topic of that shape, still loses 11 relevant papers against 2 off-topic.

**What is kept.**
- The test labels are committed unread. `report.py` prints dev only unless
  `--test` is given, so a later rule can be pre-registered against them once.
- A more promising direction is a sense check, for example the work's
  OpenAlex topic or field, or terms in its abstract, rather than word order.

## Limitations

- **AI labels**, made from an abstract excerpt; not human gold.
- **Title gate only.** The selection covers title-gate decisions alone. Later
  filters (OpenAlex topic checks, duplicates), slot limits and the shortfall
  top-up are not modelled, so effects on delivered evidence are not measured.
- **Small sample.** Six dev topics with 13–39 selected rows each; per-topic
  counts are small.

## Files

`evals/two_word_gate_v1/`:
- `topics.json`, `plans.json`, `build_plans.py`;
- `collect_pool.py`, `label_set.py`, `labels.json`;
- `rules.py`, `report.py`.

To reproduce the dev table:

```
python evals/two_word_gate_v1/report.py evals/two_word_gate_v1/labels.json
```
