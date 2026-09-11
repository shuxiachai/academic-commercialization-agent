# Six-source market-estimate spot check

Date: 2026-09-11
Inspection base: `fa48312cb3545410cdf8f0200bb01047442c8151`.
Status: agent_source_inspection / no_independent_human_review / production_unchanged.

## Selection and limits

Inspect the first six existing candidates, S01-S06, in the saved order of the
[sample-preparation result](results-2026-09-11-market-estimate-sample-contract.md).
This selection was stated before opening the publisher pages. It is convenience
sampling, not a publicly pre-registered accuracy experiment or fresh held-out set.
No difficult page was replaced. Four candidates came from live-labelled local
units, two from the already disclosed fixture-labelled battery unit. Their mode
does not become live because a publisher page can now be read.

The original local `samples.json` SHA-256 is
`bae3d1c310a274285fddf32088da426398fe921f8f9a1082e40d7655190e8c47`.
It remains unchanged and unreviewed; this separate inspection does not rewrite
its annotations, original source summaries, synthetic controls or benchmark CSVs.
The [compact observation record](artifacts/2026-09-11-market-source-spot-check/observations.json)
binds each candidate to that snapshot and its saved text hash. It contains no raw
report, full publisher article, reviewer packet or private run capability URL.

The observer is Codex, not an independent human or market expert. Six unique
publisher URLs were opened through the assistant's web reader; returned text may
be crawler-cached. These are readable-page observations, not measurements of the
production retriever, six billable API requests or archived original HTML bytes.
Only public landing-page material was inspected, not purchased reports, private
datasets or the publishers' underlying research. Follow-up text searches on those
same six pages located the relevant headings; no alternative sources were added.

## Findings

| Candidate | What the inspected publisher text establishes | What remains unestablished |
|---|---|---|
| S01: [Precedence, CAR-T](https://www.precedenceresearch.com/car-t-cell-therapy-market) | The selected 2025 value is 5,206.15 million USD. The 2026 paragraph contains `6,0836.15`, while its scope table contains `6,0836.47`, both in millions. The unusual grouping and differing values also occur in the saved summary. | Do not silently repair either token or call faithful copying model hallucination. Broad CAR-T includes indications beyond the user's blood-cancer topic. Neither grouping nor internal agreement establishes market truth. |
| S02: [Fortune, CAR-T](https://www.fortunebusinessinsights.com/car-t-cell-therapy-market-108455) | The current headline says 8.62 billion USD for 2025, unlike the saved 8.95 billion. The page labels its update August 24, 2026. | Without original page bytes, this is a snapshot/current-page mismatch, not proof of either historical extraction error or a publisher revision. Do not overwrite the old value with today's number and call it revalidation. |
| S03: [Mordor, mRNA](https://www.mordorintelligence.com/industry-reports/mrna-vaccines-and-therapeutics-market) | The selected 2025 figure remains 6.84 billion USD. The described scope includes infectious diseases and other therapeutic areas, not just cancer. | A parent-market total is not an oncology-specific estimate merely because the report discusses oncology. No independently verified price basis was obtained. |
| S04: [Vantage, cancer mRNA](https://www.vantagemarketresearch.com/mrna-cancer-vaccines-and-therapeutics-market) | The 2025 figure remains 6.4 billion USD. The 2035 summary/card says 21.34 billion, whereas the introduction says 22.8 billion. Both are visible on the same returned page and in the saved summary. | Do not choose whichever forecast makes a comparison pass. This is publisher-text inconsistency, not evidence of which forecast is correct. Its described oncology/value-chain scope differs from S03. |
| S05: [MarketsandMarkets, batteries](https://www.marketsandmarkets.com/Market-Reports/solid-state-battery-market-164577856.html) | The selected 2025 value remains 0.26 billion USD. Applications include electronics, vehicles, medical devices and sensors; the page separately describes value and MWh units. | This is not the EV-only segment. A vehicle share labelled 2024 cannot silently turn its 2025 total into a same-year EV estimate. The saved candidate remains fixture-labelled. |
| S06: [Fortune, EV batteries](https://www.fortunebusinessinsights.com/ev-solid-state-battery-market-115751) | The selected 2025 figure remains 24.8 million USD and the described scope is specifically vehicle batteries. | It is not a second estimate of S05's entire battery market. Its saved candidate also remains fixture-labelled; page access is not evidence of a historical live pipeline execution. |

These observations cover selected headline amounts and scope/forecast passages,
not every statement in six long pages. Five selected 2025 amounts reappear; that
is not five wholly verified summaries. Two pages exhibit the specified within-page
numeric problems. Neither result is an independent source-accuracy estimate.

## Pair decisions

| Pair | Agent inspection outcome | Reason |
|---|---|---|
| S01/S02 | Insufficient information | Similar headline names do not establish identical inclusions, pricing or measurement assumptions. S02's stored/current values differ; S01 also has unresolved forward-year numeric problems. |
| S03/S04 | Incompatible scope | General mRNA and oncology-specific/value-chain scope are not interchangeable totals. |
| S05/S06 | Incompatible scope | All battery applications and EV-only batteries are different markets. |

There are **zero fully established same-definition pairs out of three inspected
pairs**, not three agreements and not three confirmed incorrect scores. Ratios
and replacement scores are not emitted. Price basis remains null for all six:
the inspected passages do not establish a common nominal/constant-price basis.
This does not assert that the full paid reports contain no such disclosure.
Different publisher names also do not prove independent underlying observations.

## Decision and next useful work

Do not change the calibrated formula, confidence floor or 3.5 market cap based
on this spot check. Production Tool Calling stays zero-call shadow. All existing
source and scoring modules, frozen experiments and synthetic fixtures are unchanged.
No project-provider model/search call, paid canary, report purchase, form submission
or manual Railway restart was performed. Ordinary assistant web retrieval is not
represented as a new project cost measurement.

The next evidence step is narrower than collecting more market pages: use the
two explicit scope-mismatch pairs as development negatives, and obtain a real
positive pair with documented inclusions, time basis, price basis and measurement
method before evaluating a replacement policy. Preserve the separate version-
mismatch and internally inconsistent states. Do not require a user to pretend
this agent inspection was independent human review, or infer missing annotations.

The pre-change offline suite passed 3045 tests and 1256 subtests. This release
adds observations and navigation, not executable extraction/comparison logic;
there is no new runtime defect to re-inject. Existing full-suite/static CI checks
remain required. Automated document/link checks cannot validate these semantic
judgments. Final test, merge and bounded deployment facts are recorded on the PR.
