# Academic title gate v1

Offline replay of academic title-gate rules over 494 saved decisions from the
held-out benchmark runs. Protocol and frozen thresholds:
[pre-registration](../../docs/prereg-2026-10-20-academic-title-gate-v1.md).

| File | Role |
|---|---|
| `build_dataset.py` | Builds `dataset.jsonl` from `outputs/benchmark-runs/heldout-trl-v*` (local runs; the output is committed) |
| `dataset.jsonl` | One row per (topic, title) title-gate decision, split dev (v2 topics) / test (v1 topics) |
| `labels_dev.json`, `labels_test.json` | Topic-relevance labels (AI assistant, blind to the decisions; not human gold) |
| `rules.py` | Every candidate rule tried on the dev split; `r5_one_matcher` is the frozen primary |
| `evaluate.py` | Replays the production gate or a candidate and reports precision and recall |
| `report.py` | Descriptive tables for the [result](../../docs/results-2026-10-20-academic-title-gate-v1.md), written after the registered evaluation |
| `maintainer_check_sample.json` | The registered maintainer-check sample (topic and title only) |

No model or search request is made.
