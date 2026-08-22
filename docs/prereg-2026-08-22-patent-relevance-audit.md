# Pre-registration: accepted-patent relevance audit

**Registered:** 2026-08-22, before any human relevance labels were collected.

## Question

When the production retrieval pipeline accepts a patent source, how often is
that source topically useful for assessing the patent landscape or
commercialization position of the submitted research topic?

This audit measures accepted-source relevance. It cannot measure global recall:
the sample contains no patents that retrieval failed to find.

## Frozen sample

The audit uses public evidence already on disk and performs no network or model
calls.

- **Benchmark core:** a complete census of all 75 patent records in the 10
  tracked `benchmark_fixtures/*.json` topic fixtures.
- **Sodium-ion challenge:** all 6 patent records from retained production-style
  run `20260707T012519Z-6e9d3f0d66`, frozen in
  `evals/patent_relevance/sodium-ion-grid-storage-challenge.json`.
- **Total:** 81 accepted patent-topic pairs across 11 topics.

The sodium-ion run was selected after a topical-relevance weakness was observed.
It is therefore a post-hoc challenge set, not an independent held-out set. Its
results must remain separate from the benchmark-core headline result. Duplicate
topic/URL pairs are rejected rather than counted twice.

## Blinding and evidence available to the reviewer

Each case card shows the research topic, retrieved patent title, source ID, URL,
and frozen evidence summary. The card intentionally omits the corpus name so the
reviewer is not told whether a case came from the benchmark core or the observed
challenge. Corpus membership remains in the machine-readable manifest for later
grouping.

The primary judgment uses the frozen title and evidence summary. Reviewers must
record whether they opened none, some, or all external URLs. Opening a URL is
allowed for clarification, but this audit does not ask the reviewer to validate
legal status, claim validity, ownership, freedom to operate, or commercial
quality.

## Labels

Exactly one label is required for every case:

- `RELEVANT`: the claimed invention directly concerns the topic's core
  technology or the named commercialization application.
- `WEAK`: adjacent or contextually useful, but not direct evidence of the core
  patent landscape.
- `IRRELEVANT`: keyword overlap without a material connection to the topic.
- `UNCERTAIN`: the frozen title and summary are insufficient for a reliable
  judgment; the reviewer must not guess.

Every label also requires confidence from 1 to 5 and a concise rationale.
`UNCERTAIN` remains in every denominator. Excluding difficult cases would let a
weak corpus improve its own score by withholding judgment.

The reviewer declaration records personal completion, substantive generative-AI
use, external-link use, collaboration, elapsed time, expertise, and limitations.
An AI-generated label set must not be represented as an independent human audit.

## Locked analysis

The summarizer calculates results only when all 81 expected case IDs have a
complete label, confidence, and rationale. Missing, extra, duplicate, or partial
rows are protocol errors. Before completion, the output must say `incomplete`
and all metric fields must remain null.

Metrics are reported overall and separately by corpus and topic:

1. direct relevance rate: `RELEVANT / all cases`;
2. usable relevance rate: `(RELEVANT + WEAK) / all cases`;
3. weak rate;
4. irrelevant rate;
5. uncertain rate; and
6. mean reviewer confidence.

The benchmark-core result is the main descriptive baseline. The sodium-ion
challenge result is diagnostic only. No pass/fail threshold is registered for
this first audit because no prior human baseline exists; inventing one now would
turn characterization into target-seeking.

## Interpretation and next decision

This audit can support claims about the topical precision of accepted patent
evidence under these frozen topics. It cannot support claims about:

- retrieval recall;
- factual correctness of every evidence-summary sentence;
- patent validity, ownership, enforceability, or freedom to operate;
- usefulness of the final commercialization report; or
- performance on future topic distributions.

No production filter will be changed from these labels alone. A candidate
relevance rule must first be frozen and compared against exactly the same human
labels, with precision prioritized over recall because a false rejection removes
evidence from a paid report.

## Reproduction

```bash
uv run python patent_relevance_eval.py prepare benchmark_fixtures \
  outputs/patent-relevance-audit/packet \
  --challenge evals/patent_relevance/sodium-ion-grid-storage-challenge.json

uv run python patent_relevance_eval.py summarize \
  outputs/patent-relevance-audit/packet/labels.csv \
  outputs/patent-relevance-audit/packet/manifest.json \
  outputs/patent-relevance-audit/summary.json
```

`prepare` refuses to overwrite an existing packet so a started human audit
cannot be silently reset. The manifest stores a SHA-256 hash for every case
card, and `summarize` requires the exact manifest case-ID set.

## Results — added after labeling on 2026-08-22

All 81 rows passed the locked completeness and case-ID checks. The project owner
attested that every label and rationale was checked by a human and corrected
AI-authorship text that had been accidentally pasted into the packet's source
declaration. The public archive preserves that correction and describes the
result as one completed human label set, not an independent expert panel.

| Corpus | Relevant | Weak | Irrelevant | Usable relevance |
|---|---:|---:|---:|---:|
| Benchmark core | 64/75 (85.3%) | 9/75 (12.0%) | 2/75 (2.7%) | 73/75 (97.3%) |
| Sodium-ion challenge | 5/6 (83.3%) | 1/6 (16.7%) | 0/6 | 6/6 (100%) |
| Combined | 69/81 (85.2%) | 10/81 (12.3%) | 2/81 (2.5%) | 79/81 (97.5%) |

No case was labelled `UNCERTAIN`. Mean confidence was 4.85/5 overall, but a
reviewer's confidence is not an external accuracy measure. The clearest
concentrated failure was `quantum computing for drug discovery`: all four
accepted patents were `WEAK`, because drug discovery appeared only in generic
application lists for quantum hardware or cloud systems. The two `IRRELEVANT`
cases were a plant-disease CRISPR patent and an adhesive polymer patent matched
through “room temperature”.

The result characterizes the current accepted set; it does not measure recall
or validate a new filter. Production retrieval remains unchanged. The next
experiment must freeze a candidate relevance rule and compare its decisions
against these same labels, with false rejection reported explicitly.

That next experiment is now complete. The first frozen lexical candidate failed
the zero-false-drop and review-load gates, so production remains unchanged. Its
pre-registration and complete decisions are preserved in
[`evals/patent_relevance/candidate-screen-v1-2026-08-22/`](../evals/patent_relevance/candidate-screen-v1-2026-08-22/).

Artifacts, hashes, corrected provenance, and the reproducible summary are in
[`evals/patent_relevance/human-review-2026-08-22/`](../evals/patent_relevance/human-review-2026-08-22/).
