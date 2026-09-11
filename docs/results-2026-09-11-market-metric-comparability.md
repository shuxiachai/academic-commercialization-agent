# Offline market-metric comparability audit v1

Date: 2026-09-11
Status: offline_diagnostic / production_disconnected / no_paid_calls
Inspection base: `d3beb2c19cce5ad9fbd4ef4c4eeb3bbcda1d3cd6` (PR #133).

## Decision

The mixed-metric defect is real, but a replacement cap is **not validated**.
Keep the production formula, confidence floor, 3.5 market cap, frozen evidence
module and old calibration CSVs unchanged. The new `market_metric_audit` module
is an operator-invoked offline diagnostic, not a production guardrail, a score
repair, a Tool Calling activation or a new market-accuracy benchmark.

The minimal reproduction puts a USD 20 billion market and USD 10 million
company financing into the legacy extractor. Its untyped ratio is 2000; the
typed diagnostic excludes financing from market-size comparisons. Other observed
confounds include acquisitions, revenue, tonnes of CO2, molecule counts, future
versus current estimates and parent versus application-specific markets.

## Snapshot identity matters

This replay reads the **current 30 local unit directories**, not a newly frozen
copy of the original 30 live runs. Their metadata says **29 live + 1 fixture**.
`03-solid-state-batteries-for-electric-vehicles/meta.json` is the fixture unit;
the separately archived `benchmark_summary.csv` describes all 30 as live.
Matching names or the other 29 mode labels do not establish byte identity with
the historical run that generated that CSV.

This qualifies the earlier September 10/11 descriptions of local artifact
replays as "baseline" replays. It does not rewrite their observations or the
historical CSV, nor show that the original live experiment itself used a fixture.
Do not claim these local diagnostic results as a new independent confirmation of
26/30 TRL calibration or as a clean, current-model live evaluation.

The export binds each market, metadata and saved-score file by SHA-256, plus
the implementation and archived CSV. A separate read-only check compared 183
local JSON/CSV files before/after the audit: all were unchanged. Its manifest
digest was `5a8c3650511019e404c4f28b49184afe55645723bb246f8cfd70bfd0acf7f0d4`.
The [public aggregate and input hashes](artifacts/2026-09-11-market-metric-audit/summary.json)
contain no raw reports, reviewer labels, credentials or private run URLs.

## Measurements, not an accuracy claim

| Observation | Result |
|---|---|
| Readable market artifacts | 30/30 |
| Exact historical extraction and float-ratio parity | 30/30 |
| Positive amount occurrences, including duplicates/context | 858 |
| Legacy ratio above five | 30/30 |
| Lexical funding occurrences / containing units | 19 / 9 |
| Lexical acquisition occurrences / containing units | 3 / 3 |
| Explicit non-monetary occurrences / containing units | 17 / 6 |
| Revenue occurrences / containing units | 21 / 3 |
| Market-labelled / unknown-or-mixed occurrences | 336 / 462 |
| Units with a complete comparable pair under v1 | 0/30 |
| Typed comparison outcome | 30 `not_assessed`, not 30 passes |
| Saved market scores below / at the 3.5 ceiling | 17 / 13 |

These are lexical occurrence counts, **not distinct sources, independent
judgments or confirmed factual errors**. Limitations and summaries contribute
636 context occurrences to the old extractor. Exclusion reasons overlap: for
example, a multi-year paragraph may also lack explicit geography and currency.
The archived normalized score does not retain its pre-cap input. Thirteen
scores equal to 3.5 do not establish thirteen deductions; this audit deliberately
does not publish reconstructed penalty amounts or a counterfactual total score.

## Narrow implementation contract

- Preserve the legacy `bn`/`billion`/`mn`/`million` grammar and historical float
  division for its replay. The real corpus exposed `78.6 / 1000` becoming
  `0.07859999999999999`; Decimal normalization is kept separate rather than
  incorrectly described as bit-exact old behavior.
- Store field paths, character offsets, raw numeric tokens and source IDs.
  Do not classify every number from a finding's model-authored category label.
- Typed comparisons require one point amount, one registered M source, a clear
  market metric, explicit currency, a single calendar year, explicit geography
  and an exact lexical market scope. Bare `$`, bounds, multiple amounts/years,
  mixed metrics and missing dimensions abstain. A shared topic is not scope.
- Compare only matching dimensions across distinct registered source IDs.
  Deduplicate equivalent numeric quotations from one source. Source summaries
  and limitations explain legacy extrema but are not independent estimates.
- `not_assessed`, `spread_candidate` and `no_spread_in_checked_pairs` are
  distinct. The latter is limited to the checked pairs, never all evidence.
- Broken or missing market artifacts remain in the denominator as unavailable;
  absent metadata/scores have separate states. Empty audits return nonzero.
  The CLI refuses existing output directories and output inside its input tree.

Exact lexical scope is intentionally low-recall. Distinct source IDs do not
prove independent publishers; matching scopes do not prove equal market
definitions, time bases or methodologies. This is not Chinese amount parsing,
currency conversion, general semantic entailment, independent annotation or
an acceptance test for changing scores. **Zero comparable pairs is a failure
to establish coverage**, not evidence that all market estimates agree.

## Reproduce without provider calls

Use the local snapshot if it is available; the public repo does not distribute
these complete ignored run directories. Do not substitute another snapshot and
reuse these measured counts. For example, with a new output directory:

```bash
uv run --offline --no-sync python -m academic_agent.market_metric_audit --input outputs/benchmark --output outputs/market-metric-audit-new
uv run --offline --no-sync pytest -q tests/test_market_metric_audit.py
```

The CLI writes `audit.json` and prints the same summary delivered in that JSON.
It uses only standard-library file/text operations, not providers, model repair
or retrieval. Regression fixtures cover the actual subprocess-to-JSON seam,
corrupt/missing/oversized inputs, manifest identity, unchanged input bytes and
non-overwrite behavior. A production scoring call is also exercised while the
offline diagnostic is made unusable; the returned score matches the legacy
guardrail exactly.

Nine deliberate defect variants fail their assertions: accepting funding as
market size; losing currency, year, geography or scope comparisons; accepting
the same source twice; calling no comparison agreement; accepting a bound as a
point; and double-counting equivalent numeric representations. The funding
mutation was also tested alone at the comparison verdict, not merely its label.
Each mutated implementation was restored and SHA-256 checked before the final
suite. Baseline was 2922 tests + 1242 subtests; final local verification was
2995 tests + 1242 subtests with 88.98% coverage. Latest Ruff, narrow Pylint and
both Chromium journeys passed with zero provider requests. Composer's 26 paid
POST fixtures were intercepted, not sent to the API. Exact CI/deployment
observations belong to the release PR.

## Next gate

Before changing the cap, construct a small versioned set of **explicitly
attributed, same-definition market estimates** with the original source span,
metric, time basis, currency, geography and covered segment. Evaluate extraction
and comparison separately, retaining unknowns and rejected pairs. Existing
snapshot text can support initial engineering cases; it cannot supply expert
truth by inference or retroactively become a held-out test. Any scoring-policy
change needs a separate baseline-impact decision. No paid experiment is implied.
