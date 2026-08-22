# Human patent-relevance review — 2026-08-22

This directory archives the first completed label set for the pre-registered
accepted-patent relevance audit.

## Result

| Corpus | Directly relevant | Weak | Irrelevant | Usable |
|---|---:|---:|---:|---:|
| Benchmark core | 64/75 (85.3%) | 9/75 (12.0%) | 2/75 (2.7%) | 73/75 (97.3%) |
| Sodium-ion challenge | 5/6 (83.3%) | 1/6 (16.7%) | 0/6 | 6/6 (100%) |
| Combined | 69/81 (85.2%) | 10/81 (12.3%) | 2/81 (2.5%) | 79/81 (97.5%) |

The strongest clustered weakness is `quantum computing for drug discovery`:
all four accepted patents were labelled `WEAK` because drug discovery appeared
only in broad application lists for general quantum hardware or cloud systems.
The two `IRRELEVANT` cases were a plant-disease CRISPR patent and an adhesive
polymer patent matched through “room temperature”.

This is a single-human audit with no inter-rater agreement measurement. See
`attestation.md` for the corrected provenance statement and interpretation
limits. The post-hoc sodium-ion challenge remains diagnostic and is not held
out.

## Reproduce the summary

```bash
uv run python patent_relevance_eval.py summarize \
  evals/patent_relevance/human-review-2026-08-22/labels.csv \
  evals/patent_relevance/human-review-2026-08-22/manifest.json \
  outputs/patent-relevance-audit/reproduced-summary.json
```

The committed test suite also regenerates the summary and verifies that every
frozen case-card hash still matches the reviewed manifest.
