# Results: regulator source title recovery candidate

Date: 2026-08-25

## Outcome

The deterministic candidate passed every pre-registered development control and
was integrated at the final web-search-result to `EvidenceSource` seam. It is
accepted for that narrow production integration, not as evidence of semantic
title accuracy or real-world precision and recall.

The legacy seam matched 25/29 expected actions. The candidate matched 29/29,
while preserving all 23 genuinely clean official API titles byte for byte.

## Historical denominator measured first

The original benchmark result remained non-assessable: its 30 stored source
collections and ten tracked snapshots contain no official regulator or clinical
registry title. A wider zero-network census then inspected 95 top-level
historical runs:

| Collections | In-scope rows | Unique official URLs | Scope | Structural flags |
|---:|---:|---:|---|---:|
| 95 | 3 | 2 | ClinicalTrials.gov only | 0 |

The three rows are two repeated trial-registry records. This is still too small
to estimate prevalence or semantic correctness. It did, however, replace a zero
denominator with an explicit small denominator before any production rule was
written.

Running the audit directly on the mixed `outputs/` root initially failed because
the discovery function added `.paid-operation-ledger.json` to the run artifacts
and tried to parse it as `SourceCollection`. The fixed discovery contract treats
run-directory and flat-fixture layouts as alternatives. The real mixed root now
loads exactly 95 run artifacts while a flat-only fixture directory remains
strict.

## Frozen development challenge

The challenge contains 29 cases:

| Provenance | Count |
|---|---:|
| Official API clean controls | 23 |
| Official API observed encoding anomaly | 1 |
| Observed production failure | 1 |
| Disclosed synthetic positive controls | 3 |
| Synthetic attacker-suffix scope control | 1 |

Twelve records came from the ClinicalTrials.gov v2 API and twelve from the
openFDA device 510(k) API under the selection rules registered before retrieval.
The openFDA response returned K243224 with literal `U+0099` C1 controls in two
device names. The row was retained and reclassified as an observed upstream
anomaly before candidate implementation; it was not removed to make the clean
preservation result easier.

Frozen challenge SHA-256:

`417f6429cbbc251b2c8923761b1cf1362f5e3d744bbf1170b3d1dc5a98c0cb13`

## Baseline comparison

| Check | Legacy seam | Candidate |
|---|---:|---:|
| All expected actions | 25/29 | 29/29 |
| Official clean titles preserved | 23/23 | 23/23 |
| Observed defects safely recovered | 0/2 | 2/2 |
| Synthetic positive controls matched | 1/3 | 3/3 |
| Attacker-suffix scope control | 1/1 | 1/1 |
| Idempotent output | Not measured | 29/29 |

The four legacy mismatches were the production K222658 fragmented title, the
openFDA K243224 control-character title, a replacement-character trial title,
and an FDA host-only title. The unsupported one-character FDA page was already
rejected by the old five-character floor; the candidate preserves that fail-
closed outcome rather than claiming it as a new recovery.

## Production behavior

The candidate acts only after the existing canonical URL and authority allowlist
checks:

- A structurally clean title is unchanged.
- A broken `accessdata.fda.gov/CDRH510K/Kxxxxxx.pdf` title becomes
  `FDA 510(k) record Kxxxxxx`.
- A broken `clinicaltrials.gov/study/NCTxxxxxxxx` title becomes
  `ClinicalTrials.gov study NCTxxxxxxxx`.
- A broken official title without one of those supported URL identifiers is
  rejected instead of receiving an inferred document name.
- An attacker-suffix host cannot receive an official fallback even if a caller
  supplies the wrong category.
- A recovered source records in `credibility_reason` that the display label came
  only from the validated official URL identifier.

No second page fetch, LLM call, guessed device name, or guessed Unicode repair is
performed.

## Defect re-injection

The authority-category handoff at `_web_source` was temporarily replaced with
`None`, reproducing the pre-candidate path. The final seam test failed because
the exact fragmented production title reached `EvidenceSource.title`. The
temporary change was reversed, and the targeted suite returned to green:

`16 passed, 33 subtests passed`

This demonstrates that the new test guards transport to the final source model,
not merely a helper return value.

## Reproducibility

```bash
uv run python regulator_title_audit.py outputs \
  outputs/regulator-title-audit-20260825-all-history-direct-v2 \
  --expected-count 95 \
  --challenge evals/regulator_title_quality/challenge-v1.json

uv run python regulator_title_recovery_candidate.py \
  evals/regulator_title_quality/recovery-challenge-v1.json \
  outputs/regulator-title-recovery-candidate-20260825-v1
```

Persisted local artifact hashes:

- `result.json`:
  `df3d6cececd431f22593098e9267d1c814564502a32a2431fc204988b0cb7f53`
- `cases.csv`:
  `ca2686fa6c7da3fa75961d5ad5bf84825568774ff0d7e31367cf347363ce1180`

The candidate evaluation reported zero network calls, zero LLM calls, and zero
production mutations. The two official API requests used to create the frozen
development controls are disclosed separately in the challenge metadata.

Post-integration repository validation:

- `uv run --with ruff ruff check .`: pass
- CI-equivalent narrow pylint control-flow check: pass
- `uv run pytest -q`: `1391 passed, 627 subtests passed`
- CI-equivalent coverage run: `87.00%` total, above the `85%` floor

All test runs were zero-network; no provider token was consumed.

## Remaining boundary

This result does not establish title truth, real-world prevalence, report
quality, production success rate, latency, cost reduction, or regulatory
coverage. A provider-backed canary remains unrun and requires separate paid
authorization. Until then, the strongest accurate statement is that the
candidate passed one frozen development challenge and one defect-reinjection
test.
