# Academic title gate, live check v1

Protocol: [pre-registration](../../docs/prereg-2026-10-21-academic-gate-live-v1.md).

| File | Role |
|---|---|
| `build_plans.py` | Freezes one saved retrieval plan per consumed held-out topic into `plans.json` (from local runs; the output is committed) |
| `plans.json` | The 20 frozen plans: planned phrase, aliases, weight profile |
| `collect.py` | Part A: live academic retrieval with both gates filling slots from the same cached responses |

Part A makes no model or web-search request. Part B is a `benchmark.py`
batch; see the protocol.
