# Evidence, PDF input and terminal-consumer boundaries

Date: 2026-09-10
Status: offline_verified / no_paid_canary
Preceding release: provider/logging repair, public PR #129.

## Adopted repairs

- Numeric grounding compares decimal values and explicit quotation precision,
  not digit prefixes. Both truncation and half-up rounding at the quoted decimal
  places remain tolerated. `26.15 -> 26.1` is not accused; `100% -> 10%` and
  `1000 MW -> 100 MW` no longer pass. Existing unit checks and the advisory,
  non-blocking role of this screen are unchanged. This is not unit conversion
  or a general claim-entailment model.
- Production scoring requires P citations for patent scores and M citations
  for market scores. TRL/MRL lists need an A/M anchor, with patents permitted as
  supplements. Phantom/malformed bracket citations in all rationale, risk and
  opportunity fields are rejected when the source registry is available.
  Scores, weights, normalization, confidence floor and market cap are unchanged.
- PDF text budgeting reserves space across selected pages before distributing
  remaining characters. A long introduction cannot consume the complete budget
  of a selected result/conclusion page. The actual model input is bounded to
  7000 characters and records scanned, selected, included, truncated and omitted
  pages. Code-owned coverage survives the paid HTTP response and saved extraction;
  model-provided coverage cannot override it. Blank text fails before the LLM.
- A model-only DOI/URL cannot override document-text candidates. Conflicting or
  absent candidates are explicit. Reachability is separate from document identity:
  an uploaded contribution remains medium credibility even with a reachable
  locator. Bibliography DOIs can still be candidates; this does not establish
  manuscript identity or semantic support. Historical extraction fields default
  to `legacy_unverified` / `not_recorded`, not a successful verification.
- `ops_report` follows valid immutable `terminal.json` before legacy status and
  markers. An unreadable terminal yields unknown instead of a fallback success.
  This aligns outcome counts with the core API; it does not migrate every
  legacy operational usage/check-summary reader.

## Measure before changing

The existing 90 evidence artifacts from 30 benchmark runs were read without
provider calls. Numeric screening remained **50 checked, 1 ungrounded, 161
unverifiable**, with identical findings before/after the repair. That is a
regression observation, not an independent accuracy estimate.

A candidate rule banning all patent references from TRL/MRL rejected 2/30
historical scorecards. Both cited process patents alongside academic and market
manufacturing evidence. The final anchor rule avoids those false accusations.
All **30/30** archived scorecards pass the final wrapper; after restoring their
input integer scale, its output is byte-identical to the unchanged legacy
guardrail under the same source pool, market evidence and weight profile.

The full suite also correctly rejected direct edits to `evidence.py`, a frozen
dependency of previous paid experiments. Those bytes and all experiment locks
were restored unchanged. The new `scoring_contract.py` wraps the old factory at
the production Crew import. Local checkpoint revision hashes include this new
module so local resumes cannot reuse scores across an admission-rule change.
Historical runners remain bound to their original implementation, not silently
upgraded experiments.

## Verification

Behavior tests cover findings-to-audit, actual Crew scoring admission, local
recovery identity, real PDF-to-model prompt, HTTP response versus persisted
extraction, and ops outcome versus the core API. No model output is obtained
from a real provider. Eight deliberate defect injections fail at the intended
assertions: numeric prefix, old Crew import, unchecked prose citations, legacy
terminal precedence, PDF prefix truncation, model DOI override, high credibility
from reachability, and omitted scoring code in the local revision hash. All
mutations were restored before the final test run.

Final local suite: **2784 passed + 1218 subtests**, **89.07% coverage**.
Latest Ruff, narrow Pylint and whitespace checks pass.

Both Chromium journeys pass with no provider/external requests. The composer
intercepts 23 paid POST fixtures and three held history reads. Full-suite,
coverage, lint, CI and exact deployment verification are recorded on the release
PR. No paid canary, manual restart, new search call, experimental cohort access
or production Tool Calling activation is authorized by these offline results.

## Remaining audit scope

The external 20-item review mixes reproducible bugs with architectural and
research gaps. This release does not label the entire list resolved:

| Review items | Disposition |
|---|---|
| 1 | Shared provider resolution shipped in PR #129; fake-key reproduction is not proof of historical disclosure. |
| 2 | Named access/PDF/helper diagnostics repaired in #129; third-party and other log paths still need broader auditing. |
| 3, 5, 6, 18 | Narrow numeric, production citation, PDF budgeting and terminal-reader contracts repaired here. |
| 7 | Model override/high-confidence promotion repaired; full document identity and claim support remain unverified. |
| 4 | Mixed market metrics confirmed: the existing extractor produces a spread above 5 in all 30 baseline market artifacts. This does not prove all 30 penalties wrong. Classify metric/time/currency/geography in an offline, versioned comparison before changing the calibrated cap; do not silently alter the protected formula. |
| 8, 9, 10 | Durable paid receipts, parser subprocess isolation and explicit public-startup policy remain separate runtime designs. Existing tab warnings, PDFium mutex and readiness do not imply these capabilities. No current Railway misconfiguration was established. |
| 11 | Crew-node usage still excludes helper/inline PDF calls. Price completeness for recorded nodes is not end-to-end bill completeness. |
| 12, 13, 14, 15, 16 | General entailment, autonomous tool-use, isolated role benefit, cross-source selection quality and independent calibration require new evaluation; historical failures remain sealed, production remains zero-call shadow. |
| 17 | Legacy `benchmark.py` skip/force behavior still lacks full run identity and immutable rerun batches. Preserve archived results; do not use it to claim a fresh-model evaluation by resuming old output directories. |
| 19 | One replica remains the supported operating boundary. |
| 20 | New regressions execute consumer boundaries and deliberate mutations; this is not a claim that every older test is end-to-end. |

For uploaded PDFs, page budgeting is not section understanding, OCR, complete
paper ingestion or a native-process memory/time fault boundary. The coverage
fields are delivered by API and stored; they are not yet a dedicated browser
coverage inspector. No reduction in production incident rate, spending or
report error rate is inferred from these deterministic regressions.
