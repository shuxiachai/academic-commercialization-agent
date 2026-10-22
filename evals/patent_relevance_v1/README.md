# Patent relevance v1

Outcome: [development comparison](../../docs/results-2026-10-22-patent-relevance-v1-dev.md). No word rule
advanced, so no protocol was registered and the test split was neither labelled nor read.

| File | Role |
|---|---|
| `build_pairs.py` | Unique topic and patent pairs from saved registries, with the Google Patents abstract from the patent family page cache |
| `dev_labels.json` | The held-out v2 pairs, their AI labels and the rubric |
| `report.py` | How many labelled on- and off-topic patents each candidate rule removes |
