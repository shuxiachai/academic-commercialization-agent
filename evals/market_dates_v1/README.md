# Market page dates v1

Protocol: [pre-registration](../../docs/prereg-2026-10-22-market-page-dates-v1.md).

| File | Role |
|---|---|
| `probe.py` | Reads saved market sources, fetches each page once (cached), records the date `page_dates` finds |
| `verify.py` | Renders each dated page in Chromium and looks for the date (one day either side) in its visible text |
| `dev_probe.json`, `dev_verify.json` | Development split: the held-out v2 market sources |

The extractor and the rule under test are `src/academic_agent/page_dates.py`
(`date_from_html`, `should_date`). No model or search request is made.
