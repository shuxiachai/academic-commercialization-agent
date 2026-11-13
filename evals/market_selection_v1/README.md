# Market selection v1

Protocol: [pre-registration](../../docs/prereg-2026-11-13-market-selection-v1.md).
Registered 2026-11-13; not run. It needs the maintainer's approval of its budget.
Offline measurement behind the rules: [result](../../docs/results-2026-11-13-market-selection-offline.md).

| File | Role |
|---|---|
| `cases.json` | The twelve cases: five from the frozen v2 cohort (scored) and seven with no saved run (retrieval only) |
| `collect.py` | Part R. Collects each case's sources under one arm's code. Every outside request goes through one record, so the second arm is answered with what the first arm received |
| `compare.py` | Part R. Reads the two arms' registries side by side and prints the pairs and sources the protocol asks to be read |
| `freeze.py` | Part S. Hands one arm's registries to `benchmark.py --fixtures` as that checkout's frozen evidence |

The rules under test are `src/academic_agent/market_selection.py`, the market
stage of `source_pipeline.py` and `should_date` in `page_dates.py`.

`collect.py` sends web searches and a few model requests, which are paid.
`tests/test_market_selection_eval.py` runs both arms against replaced clients
and makes no request. The request record holds third-party text; keep it
outside the repository. The fixtures `freeze.py` writes are local to the
experiment and are not committed.
