# Academic title gate, live check v1

Protocol: [pre-registration](../../docs/prereg-2026-10-21-academic-gate-live-v1.md).

| File | Role |
|---|---|
| `build_plans.py` | Freezes one saved retrieval plan per consumed held-out topic into `plans.json` (from local runs; the output is committed) |
| `plans.json` | The 20 frozen plans: planned phrase, aliases, weight profile |
| `collect.py` | Part A: live academic retrieval with both gates filling slots from the same cached responses |
| `part_a_results.json`, `labels_part_a.json`, `report_part_a.py` | Part A's delivered sources, blind labels and measures ([result](../../docs/results-2026-10-21-academic-gate-live-v1.md)) |
| `labels_part_b.json` | Labels for Part B sources not labelled before |

Part A makes no model or web-search request. Part B is a `benchmark.py`
batch; see the protocol.
