# Two-word title gate v1

Result: [development comparison, no rule advanced](../../docs/results-2026-10-22-two-word-gate-v1-dev.md).

| File | Role |
|---|---|
| `topics.json` | Twelve two-word inputs, split by seed into dev and test |
| `build_plans.py`, `plans.json` | One frozen `qwen3.8-27b` plan per topic |
| `collect_pool.py` | Fetches the primary academic lanes with the production clients, caching every response |
| `label_set.py` | Selects the rows R5 accepts although the two anchor words are not adjacent |
| `labels.json` | The 240 selected rows with title, abstract and AI label; test labels are unread |
| `rules.py`, `report.py` | Candidate rules and the removed-row comparison (dev only unless `--test`) |

The pool itself is not committed. `collect_pool.py` refetches it, and live
responses change over time. `labels.json` holds every field the rules read.
