# SLQ: one native synthetic source-location batch

The [pre-registered SLQ batch](prereg-2026-09-19-source-locator-qwen-canary.md)
completed four sequential requests to exact `qwen3.5-plus`. All four mechanical
gates and all four frozen development-reference checks passed. This is a narrow
native compatibility observation, not independent selection accuracy, semantic
claim verification, user benefit or a production Tool Calling release.

## Identity and release gates

- Executed commit: `a6b87c1afa57b49b98e8f5caf3092c62bf40caf7`.
- Fixture SHA-256: `c4301fe9d6d57427de3f0252492b88886964ed6b0a15bbf6f6a5c9e9fbaff36e`.
- Execution date: 2026-09-19, Australia/Sydney.
- All eight [CI checks on that commit](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/35368484327) passed before native execution.
- Baseline: 5,780 tests / 1,539 subtests; post-implementation: 5,859 / 1,543, all passing. Latest Ruff and narrow Pylint passed.
- Independent code review found no remaining actionable findings. The three
  restored defects (continuing after failure, bypassing pre-dispatch identity,
  and conflating reference mismatch with mechanical failure) each made the
  unchanged boundary tests fail.
- Actual committed-tree identity-only execution passed without creating output.
  Native execution then used the new protocol acknowledgement and bounded
  standing low-cost permission, not an old batch's allowance.

The fixed local output is `outputs/report_evidence_source_locator_qwen_canary_v1`.
It is now occupied and closed: do not resume, rerun or relabel this batch.
Raw journals and operator records are not included in this public result.

## Observed delivery and reference agreement

| Case | Native choice | Code-owned delivery | Local read attempts / completions | Mechanical gate | Reference check | End-to-end seconds |
|---|---|---|---|---|---|---|
| SLQ01 | A12 | Exact saved text (`excerpt`) | 1 / 1 | pass | match | 5.454 |
| SLQ02 | P21 | Exact saved text (`excerpt`) | 1 / 1 | pass | match | 4.687 |
| SLQ03 | Explicit decline | No source or text (`declined`) | 0 / 0 | pass | match | 4.375 |
| SLQ04 | P41 | No saved text (`missing_text`) | 1 / 1 | pass | match | 5.250 |

There were four callback entries, four accounted native attempts, three local
read attempts/completions and two nonempty saved-text deliveries. A completed
missing-text read is not a delivered excerpt. Each case journal contains one
reserve and one finish event; all four reported coherent usage and passed the
configured response-model identity check. No case remained pending or unrun.

The provider saw only synthetic questions and title/ID catalogs. Saved text,
reference labels and credentials were not prompt content. There was no second
model turn: code performed the selected local read and returned its saved-text
projection. No retries, redirects, repair, fallback, external search or additional
paid judging requests were used.

Durations include case setup, local identity checks, callback, local read, gates
and the case-publication attempt. They exclude batch setup and summary
publication; they are neither isolated provider latency nor a production SLO.

## Usage, reservation and uncertainty

| Case | Prompt tokens | Completion tokens | Known-use estimate, USD |
|---|---|---|---|
| SLQ01 | 593 | 28 | 0.000436109 |
| SLQ02 | 594 | 28 | 0.000436682 |
| SLQ03 | 580 | 6 | 0.000352980 |
| SLQ04 | 584 | 28 | 0.000430952 |
| Total | 2,351 | 90 | 0.001656723 |

Aggregate conservative reservation consumption was **USD 0.044597248**, below
the **USD 0.05** soft stop. Reported-use coverage was complete for these four
requests, with zero unknown-usage requests. These values use the frozen
engineering price rates; they are not provider invoices or a promise that
future requests cost the same. Reservations and reported-use estimates are
different quantities and must not be interchanged.

Local raw-file identities, recorded without publishing their contents:

- `summary.json`: `b452d1d02f8c2468f6e112ceb9217dc030fcf7d2a3cb761bce40c1dd700e83df`.
- `identity.json`: `07704955e880c54c7942d064803610012b6e98f4fe59de688dd6e4ab398c076f`.

These are file identities, not cryptographic provider-execution attestation.

## Separate label-blinded LLM inspection

A new `route_reviewer` context, separate from the reference reviewer and runner
author, received only questions, visible title/ID catalogs, actual choices and
delivered state/text. Reference labels, prior reviews, gate outcomes and costs
were hidden. It returned `supported` for all four **narrow location/delivery**
observations, noting that it could not independently verify underlying saved
bytes, scientific truth, patent validity, entailment or system accuracy.

This was a context-limited LLM inspection, not human expert gold or a second
independent accuracy study. The configured role was Astra/high; effective
backend metadata was unavailable. No external sources or project-provider
judging calls were used. The inspection did not change any runtime semantic
flag or frozen reference.

UTF-8/LF text provenance:

- Supplied observation JSON SHA-256: `18aef1c7809fdd8f15f25b4af7d633d768735590ab43056d6e27aeac2ae1caae`.
- Full prompt SHA-256: `9f69937896f88e0f68d698deb93d7bae9bac620e305643d9f77d51874b4397c9`.
- Returned inspection text SHA-256: `36d3798bcdbbcc20def52cc6a46e176eeb8215bf1cfe9cfeeb70ebbfa341b53c`.

## What this does not establish

These are four easy author-generated development controls, not held-out tasks.
The Chinese case covers one question; it is not broad Chinese-input validation.
The decline applies only to the supplied small catalog, not absence of relevant
literature. SLQ04 proves the program preserves missing text, not that the model
recognized text availability from hidden data. Matching a title cannot establish
source truth, useful scientific evidence or a correct investment conclusion.

The next evidence gate is a fresh, more realistic source-selection evaluation
against the existing no-model Sources browser/literal lookup baseline. Any real
saved-report data needs an applicable transmission boundary. A public feature
also needs ownership, shared paid admission, durable client receipts, cost
visibility and safe UI failure states. None was added or enabled by this batch.
