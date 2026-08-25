# Regulator-source title quality audit — result

**Run date:** 2026-08-25
**Protocol:** [frozen implementation protocol](protocol-2026-08-25-regulator-title-quality-audit.md)
**Network, LLM, supplementary search, and production mutations:** 0

## Outcome

The audit completed, but the benchmark result is **not assessable**. All 30
stored benchmark collections loaded and were content-hashed; none contained a
source from the frozen regulator or clinical-registry host set. The correct
state is therefore `not_assessable_zero_denominator`, not pass and not
`checked_no_structural_flags`.

| Dataset | Collections | In-scope titles | Affected collections | State |
|---|---:|---:|---:|---|
| Stored 30-run benchmark | 30/30 | 0 | 0/30 | `not_assessable_zero_denominator` |
| Tracked ten-topic fixtures | 10/10 | 0 | 0/10 | `not_assessable_zero_denominator` |

The ten tracked fixtures are a reproducibility cross-check, not an independent
sample: they are snapshots of the same benchmark topics. Their agreement only
shows that a clean clone can reproduce the zero denominator.

## Frozen challenge

The five-case disclosed challenge matched 5/5 expectations. Its SHA-256 is
`0be6054820be180b749a1925ce66a9ec6a716d4176f5c8fe7308888a7bc4c811`.

| Case | Provenance | Observed state | Reason |
|---|---|---|---|
| Production `M7` FDA title | Exact post-fix canary artifact | `review_required` | `fragmented_single_letter_tokens` |
| Plausible FDA 510(k) title | Synthetic negative control | `clean` | — |
| Plausible ClinicalTrials.gov title | Synthetic negative control | `clean` | — |
| `fda.gov.attacker.example` | Synthetic scope control | `out_of_scope` | — |
| Title containing `�` | Synthetic positive control | `review_required` | `encoding_replacement_character` |

The known production title was:

```text
'b, , 4 , I 'b, I - accessdata.fda.gov
```

It came from source `M7` at
`https://www.accessdata.fda.gov/CDRH510K/K222658.pdf` in run
`20260825T024919Z-d8c43b0ba3479dc46227b4bfaa82f0a4`. The classifier flags it
only because it combines at least four isolated alphabetic fragments, a
majority fragment ratio, and the official host printed in the title. It does
not use general punctuation density, capitalization, title length, PDF
suffixes, or product codes as failure signals.

This is a post-hoc regression case plus synthetic controls. A 5/5 result does
not establish prevalence, recall, or held-out precision.

## Determinism and verification

The 30-collection audit was executed twice into separate output directories.
Both persisted files were byte-identical:

- `result.json`: `4d40f8d1f3d419757058f12d4977bde897f95bf9f8c67f78f34a696a4a0ee778`
- `cases.csv`: `ffb8ec0843555652701b8fa2b92015b17a36a0a15c64ad75a912ef9293d1e084`

The implementation also records every collection hash and per-collection
official-source count, retains challenge provenance and expected/observed
labels at the CSV seam, refuses to overwrite prior output, and fails closed on
invalid collections or expected-count drift.

The original defect was re-injected by changing the minimum isolated-fragment
count from four to five. The exact production subtest changed from
`review_required` to `clean` and failed; restoring four returned the targeted
suite to green.

Local gates after restoration:

- 1,381 zero-network tests and 602 subtests passed;
- CI-equivalent coverage remained 86.91%, above the frozen 85% floor;
- the newest Ruff passed; and
- the audit itself executed no network or provider path.

Commands:

```bash
uv run python regulator_title_audit.py outputs/benchmark \
  outputs/regulator-title-audit-20260825-benchmark \
  --expected-count 30 \
  --challenge evals/regulator_title_quality/challenge-v1.json

uv run python regulator_title_audit.py benchmark_fixtures \
  outputs/regulator-title-audit-20260825-tracked-fixtures \
  --expected-count 10 \
  --challenge evals/regulator_title_quality/challenge-v1.json
```

## Decision

No production title normalizer is added by this change. One observed failure is
enough for a regression challenge, but zero benchmark denominator is not enough
to estimate false-positive cost or choose a normalization policy. A broad PDF
cleaner would violate the project's precision-first rule.

The next defensible step is to retain future official regulator titles in a
separately versioned challenge set, with manual labels and source identity. A
future FDA-specific normalizer should be proposed only against that set and
must preserve the raw title, expose that normalization occurred, and abstain
when a stable identifier such as a 510(k) number cannot be verified. This audit
does not authorize that implementation.

## Claim limits

The result establishes that the audit contract represents a zero denominator
honestly and catches one exact known failure without firing on the disclosed
controls. It does not establish regulator-title quality, source truth, report
correctness, production error rate, semantic title correspondence, general
precision/recall, or business value.
