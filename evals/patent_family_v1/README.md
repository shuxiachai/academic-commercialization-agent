# Patent family v1

Protocol: [pre-registration](../../docs/prereg-2026-10-22-patent-family-v1.md).

| File | Role |
|---|---|
| `families.py` | Reads saved patent registries, derives each row's publication number from its URL, fetches its Google Patents page once (cached, paced) and records the page's own number, DOCDB family ("Also Published As") and "Other versions" |
| `evaluate.py` | Replays each registry under the current whole-title check and the candidate rule, and scores each rejection against the recorded families |
| `dev_families.json` | Development split: the held-out v2 registries |

The rule under test is `src/academic_agent/patent_family.py`
(`same_invention`). The ground truth is parsed by `families.py`, independently
of the rule. No model or search request is made.
