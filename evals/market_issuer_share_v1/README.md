# Market issuer share v1

Before-and-after comparison for the issuer share in the market stage.

- Protocol: [`docs/prereg-2026-11-17-market-issuer-share-v1.md`](../../docs/prereg-2026-11-17-market-issuer-share-v1.md), registered 2026-11-17. **Not run.** It needs the maintainer's approval of its budget and a model.
- What the saved runs show: [`docs/results-2026-11-17-market-issuer-share.md`](../../docs/results-2026-11-17-market-issuer-share.md).

The rule under test is `issuer_of`, `same_issuer` and `issuer_mates` in
`src/academic_agent/market_selection.py`, and the issuer share in the market
stage of `source_pipeline.py`.

| File | What it does |
|---|---|
| `cases.json` | Ten cases: two scored development topics, eight unseen topics named before any search |
| `collect.py` | Part R. The collector of `evals/market_selection_v1`, unchanged, run over these cases. Both arms are answered from one request record |
| `compare.py` | Part R. Reads the two arms' registries: issuers per arm, what the new arm held, what left and what arrived. No request |
| `freeze.py` | Part S. Stores an arm's registries as the benchmark's fixtures, for the scored cases whose registries differ |

`collect.py` makes paid requests (web search, the topic planner). `compare.py`
and the tests make none. `tests/test_market_issuer_share_eval.py` covers the
wiring with every client replaced.
