# Erratum: v7 AB05 evidence-lane query

Date: 2026-09-01 (Australia/Sydney)

This correction was made after pre-registration commit `e0d9155` and before
the v7 preflight implementation, any OpenAlex request, any model call, or any
human label.

## What the zero-network audit found

The original AB05 `technology_evidence` query was:

```text
phage loaded hydrogel pathogen reduction in vivo survival
```

The existing evidence-gap scope tokenizer counted only `loaded` and `in` as
exact overlaps with the frozen topic. That technically met the two-token
authorization rule while failing to bind the query robustly to the
`bacteriophage_delivery` and `hydrogel_carrier` roles. Treating that formal
pass as a meaningful scope pass would reproduce the precise retrieval-noise
problem that v7 is intended to test.

## Bounded correction

The query is replaced with:

```text
bacteriophage loaded hydrogels bacterial fish pathogen reduction survival
```

No case identity, topic, role, lane target, request limit, qualification gate,
cohort order, or production boundary changed. AB01-AB08 remain unopened. The
corrected fixture receives a new raw-byte hash and becomes the only fixture
identity accepted by the implementation.
