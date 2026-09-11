# Market estimate sample preparation and comparison contract

Date: 2026-09-11
Base: `44cab3feb7c48428397764e5485838f4e58e0f74`.
Status: offline_engineering / source_candidates_unreviewed / production_disconnected.

## Decision

Prepare attributable inputs before reconsidering the market variance cap. This
step **does not establish a verified same-definition market-estimate dataset**.
It creates executable synthetic controls and a separate local draft containing
saved source text. No scoring formula, confidence floor, 3.5 market cap,
Crew prompt, provider, frozen experiment or production Tool Calling changes.

The preceding [snapshot-qualified audit](results-2026-09-11-market-metric-comparability.md)
found one eligible occurrence but no comparable pair. A read-only inventory now
counts 103 findings containing `billion`/`million`/`bn`/`mn`: 72 cite exactly one
M identifier, 31 do not. One cited source still does not prove number attribution,
equal definitions, literal support or source truth. Do not fill absent currency,
period or geographic scope from the report topic merely to improve coverage.

## Two separate outputs

### Synthetic controls, not empirical market estimates

The versioned [16-case fixture](../tests/fixtures/market_estimate_controls_v1.json)
is explicitly agent-authored engineering data, not human labels, independent
review, a held-out cohort or real market values. It has literal labelled clauses
for metric, currency, calendar year, geography, market scope, time basis, price
basis and measurement basis. The literal grammar is not a natural-language
extraction model. Source IDs and source families are declared synthetic inputs,
not a verified publisher-independence detector.

The offline comparison contract distinguishes:

- fully declared matching dimensions, with either a greater-than-five spread
  or no spread among the tested values;
- explicit incompatible dimensions or repeated source families;
- missing information, even if both sides have the same missing value;
- malformed/unavailable cases, which remain in the denominator.

Same year does not mean forecast and estimate are interchangeable; same currency
does not equate nominal and constant-price estimates. Equal source family cannot
be turned into two independent votes by changing a source ID. Ratios are only
produced for matching complete controls; this is not a new production cap.

All 16 declared contracts matched: three comparable/no-spread, one comparable
spread, nine incomparable, three insufficient-information. This is **16/16
engineering assertions**, not 100% market accuracy. Tests assert complete verdicts,
ratio absence/presence and reason lists at the actual CLI-to-JSON seam.

### Local source candidates, not completed annotations

The snapshot preparation command scans the current 30 directories (29 live,
one fixture). It selects at most two explicit ISO-currency amount-bearing source
summaries per exact topic, using sorted unit/source order and exact topic/URL
deduplication. The result is 20 candidates across ten topics. These are
convenience samples, not representative or independently selected evaluation.
Amounts may still be financing or otherwise non-market quantities; the draft
does not pre-label them as market size. Bare currency symbols, other amount
grammars and later sources may be omitted. Different URLs may repeat a publisher.

Each row includes the market JSON and metadata hashes, literal source-summary
text, source ID/URL, JSON pointer, text hash and exact amount character spans.
It preserves the unit's live/fixture label; matching metadata does not establish
identity with the original archived calibration CSV. All 183 local JSON/CSV
input hashes were unchanged after preparation.

The 90 input hashes in the preceding audit's public manifest still match the
local market/meta/score files. This is continuity with that qualified snapshot,
not new proof of the original all-live calibration identity. Control fixture
SHA-256 is `2be522d029dd04686a349d9530dfb486665433312f547f2257f0697891ef3626`;
sample-tool SHA-256 is
`5760595fe6534d7361e760c2e22b22d03e98e438f67d572b9d1fc2ffbe56fe1d`.

All eight annotation slots remain null, expected judgment remains null,
`judgment=unreviewed`, `external_verification=not_performed`, and URL verification
is false. There are **zero reviewed/externally verified candidates and zero scored
real comparisons**. A saved source summary is not a fetched primary page; the
command makes no network request and cannot infer that missing review happened.
Snapshot output is rejected by the synthetic-control evaluation entry point.

Raw candidate text stays in ignored local outputs. Only aggregate counts and
hashes accompany this public result. No private run URLs, reviewer documents or
raw source-summary packet is published automatically.

## Reproduce without provider calls

Both output directories must be new and outside their input directory:

```bash
uv run --offline --no-sync python -m academic_agent.market_estimate_samples --controls tests/fixtures/market_estimate_controls_v1.json --output outputs/market-controls-new
uv run --offline --no-sync python -m academic_agent.market_estimate_samples --snapshot outputs/benchmark --output outputs/market-candidates-new
uv run --offline --no-sync pytest -q tests/test_market_estimate_samples.py
```

The second command requires the local ignored snapshot. It writes `samples.json`
and prints the same summary as the JSON artifact. Existing output paths are
refused; a failed/incomplete run is not repaired or overwritten. Reads are bounded,
resolved paths stay within the selected corpus, duplicate source IDs invalidate
the whole unit, and unreadable units remain explicitly unavailable. Empty inputs,
no candidates, bad units or failed control expectations return a nonzero exit.

## Verification and limits

The unchanged starting suite passed 2995 tests and 1249 subtests. Fifty new tests
cover the literal contract, real subprocess export, separate denominators,
span/hash binding, repeated inputs, bad shapes, unknown modes, path escape and
non-overwrite behavior. No test ignores or skips were added. Final complete-suite,
static, CI and release observations are recorded on the release PR.

Six deliberate defects were individually injected: ignoring time basis,
equating unknown scopes, ignoring source families, promoting unreviewed drafts,
substituting a source hash, and shifting amount offsets. Each must fail its
targeted behavioral assertion; implementation bytes are SHA-256 restored before
complete validation. This proves those test seams, not model factual accuracy.

Next, a same-definition real comparison needs explicitly supported annotations
and original publisher context, including time/price/measurement basis. The draft
can aid that work but cannot supply human judgments by inference. Such evaluation
and any decision to change the scoring cap require their own method and baseline
impact decision. No paid run, external review or production integration is
authorized or claimed by this preparation step.
