# Market-source follow-up: completing inspection is not completing comparability

Date: 2026-09-12. Base: `fed29bb80b6b02a4f930be634b814176c4045f5a`.
Status: agent_source_inspection / no_independent_human_review / production_unchanged.

## Scope and method

Continue the [six-source inspection](results-2026-09-11-market-source-spot-check.md)
with the remaining saved candidates S07-S20, in saved order without substitution.
This completes source-page inspection of the existing 20-candidate convenience
sample across two dates, **not** an independently labelled positive dataset.
The original 20 rows remain unreviewed: new observations are separate from the
original annotations, saved text, fixture/live labels and historical results.

The [compact record](artifacts/2026-09-12-market-source-followup/observations.json)
contains source URLs, original text hashes, selected amounts, passage locators,
qualified agent interpretations and unresolved dimensions. It contains neither
full publisher articles nor raw reviewer documents or private run links.
The original candidate JSON SHA-256 remains
`bae3d1c310a274285fddf32088da426398fe921f8f9a1082e40d7655190e8c47`.
Its 20 rows still have null annotations and expected judgments. The prior
six-source record is also unchanged and hash-linked by the new record.

Fourteen publisher candidates returned readable text through the assistant web
reader; this may be crawler-cached, not captured original HTML or a production
retrieval experiment. S08 initially returned a reader error, then its canonical
trailing-slash URL returned text; it was not replaced by another source. A link
labelled methodology on S10 returned an error. Bounded public searches for
method/pricing disclosures did not establish a comparable price basis. Reading
a contents heading or report-sales price is not reading its valuation method.
No forms, sample requests, purchases or project model/search APIs were used.

## What was established

Selected base/estimate-period amounts reappear for all 14 candidates; this does
not validate their entire summaries or underlying market truth. S11 concerns
2024, not 2025. S09's 2025 value belongs to a forecast period. S18's prose/card
year conflict is retained rather than silently choosing a corrected year.
Public-page interpretations below are by the agent, not independent experts.

| Pair | Selected publisher amounts | Outcome and unresolved boundary |
|---|---|---|
| P04 S07/S08 | [Fortune solar cells](https://www.fortunebusinessinsights.com/industry-reports/perovskite-solar-cell-market-101556): 2025 USD 101.02m; [Market.us modules](https://market.us/report/perovskite-solar-cells-module-market/): 2025 USD 0.44bn | Insufficient information. Similar applications do not settle cell versus module value-chain accounting. S07's 2034 forecast differs from the saved text; the historical reason is unknown. |
| P05 S09/S10 | [MarketsandMarkets CRISPR](https://www.marketsandmarkets.com/Market-Reports/crispr-technology-market-134401204.html): 2025 USD 3.21bn; [Towards Healthcare CRISPR](https://www.towardshealthcare.com/insights/crispr-gene-editing-market-sizing): 2025 USD 4.76bn | Incompatible time basis: S09 declares 2024 as base and 2025-2030 as forecast; S10 calls 2025 an estimate. The matching year does not make both retrospective estimates. Both are broader than genetic-disease therapy alone. |
| P06 S11/S12 | [GMI post-combustion CCS](https://www.gminsights.com/industry-analysis/post-combustion-carbon-capture-storage-market): 2024 USD 5.5bn; [Fortune CCS](https://www.fortunebusinessinsights.com/industry-reports/carbon-capture-and-sequestration-market-100819): 2025 USD 4.51bn | Incompatible scope and year. The second includes multiple capture technologies; the first is post-combustion only. Do not annualize using a forecast CAGR to manufacture a matching historical estimate. |
| P07 S13/S14 | [Mordor cultured meat](https://www.mordorintelligence.com/industry-reports/cultured-meat-market): 2025 USD 35.67m; [Research Nester cultured meat](https://www.researchnester.com/reports/cultured-meat-market/8272): 2025 USD 292.6m | Insufficient information. Both include multiple species and hybrid products, but full-product versus cultured-component revenue, pricing and channel valuation remain unresolved. S14 also has a forecast arithmetic inconsistency. |
| P08 S15/S16 | [Roots quantum drug discovery](https://www.rootsanalysis.com/reports/quantum-computing-in-drug-discovery.html): 2025 USD 315m; [SNS quantum drug discovery](https://www.snsinsider.com/reports/quantum-computing-in-drug-discovery-market-10497): 2025 USD 0.45bn | Insufficient information. Overlapping hardware/software/service lists do not reconcile allocation of shared-platform revenue. Roots places detailed methodology in the full report; SNS gives differing 2035 headline/FAQ values. |
| P09 S17/S18 | [SNS graphene electronics](https://www.snsinsider.com/press-release/global-graphene-electronics-market): 2025 USD 943.10m; [Precedence flexible electronics](https://www.precedenceresearch.com/flexible-electronics-market): prose 2025 USD 38.08bn | Incompatible scope: all graphene electronics is not all flexible electronics, nor their intersection. S18's card says 2024 while its prose uses 2025. |
| P10 S19/S20 | [SNS superconductors](https://www.snsinsider.com/reports/superconductors-market-4291): 2025 USD 10.94bn; [Mordor superconductors](https://www.mordorintelligence.com/industry-reports/superconductors-market): 2025 USD 1.34bn | Insufficient information. Material/component/end-system inclusions are not reconciled. Both concern LTS/HTS markets, not an established ambient-pressure room-temperature product market. |

Missing information is preserved even when a separate explicit mismatch is
already sufficient to reject a comparison. All 14 price-basis annotations remain
null: the inspected passages do not establish a common nominal/constant-price
basis. This does not assert that the full reports lack that information.
Different publisher names do not establish independent underlying observations.

### Additional real development negative

S07's headline market value and its July-2025 GCL financing passage provide a
literal market-size-versus-funding example: USD 101.02m and about USD 28m,
respectively. Shared currency, year and publisher do not make these comparable
market estimates. N01 is **one same-page development negative**, outside the seven
candidate-pair denominator; it is not independent confirmation of either amount.
No production score or spread ratio is generated from this example.

### Preserve source inconsistencies instead of guessing corrections

S14 reports USD 303.1m in 2026, USD 416.7m in 2035 and 33.6% CAGR.
Computing `100 * ((416.7 / 303.1) ** (1 / 9) - 1)` gives about **3.60%**.
The 2025-2035 endpoints also imply about 3.60%, so choosing nine versus ten years
does not resolve 33.6%. This is an arithmetic check of displayed endpoints, not
identification of the correct forecast. S16's headline/table uses USD 1.48bn for
2035 while its FAQ uses USD 1.47bn; both readings are retained.
S07's current/saved forecast mismatch is a different state: no original HTML
exists here to distinguish publisher revision from historical extraction error.

## Denominators and decision

- This batch: **14 inspected candidates, seven pairs**; three explicit
  incompatibilities, four insufficient-information pairs, zero fully established
  same-definition pairs. One separate development negative.
- Combined with the earlier batch: **20 candidates / ten pairs** inspected over
  two dates; five explicit incompatibilities and five insufficient-information
  pairs. Zero independent human judgments and zero replacement scores.
- These are coverage and agent-inspection outcomes, not representative error
  rates, human labels, source independence, statistical accuracy or market truth.
- The synthetic 16-case controls remain separate. They cannot fill the missing
  real positive denominator. The local historical snapshot still has 29 live
  labels and one fixture; it is not proof of the original calibration CSV bytes.

The original scoring formula, confidence floor, legacy 3.5 market cap, model
identity and production zero-call shadow policy are unchanged. **This closes the
remaining-source inspection, not the real-positive or replacement-policy gate.**

Use the [collection checklist](market-estimate-collection-guide.md) to pursue one
fully documented positive pair before another scoring experiment. Do not expand
to unrelated easy markets, drop missing-price requirements, invent null values,
or count repeated publisher data merely to produce a passing comparison.

## Verification

The pre-change complete zero-provider suite passed **3180 tests and 1273
subtests**. This changes evidence records and navigation, not executable
production or comparison logic; there is no repaired runtime defect to re-inject.
Local verification binds all 14 row hashes/URLs to the original draft, checks
unchanged null annotations, recomputes pair counters and verifies both prior
records and all 183 benchmark JSON/CSV hashes remain unchanged. It validates
artifact integrity, not the semantic truth of this agent's judgments.
Full-suite/static checks and CI remain required; release outcomes are recorded
on the delivery PR rather than inferred from the historical test count.
