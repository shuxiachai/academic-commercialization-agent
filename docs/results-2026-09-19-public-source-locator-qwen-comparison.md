# SLCQ: six native public-title selections against assisted keyword search

The [frozen protocol](prereg-2026-09-19-public-source-locator-qwen-comparison.md),
with its [pre-live encoding erratum](erratum-2026-09-19-slc-baseline-encoding.md),
completed once on 2026-09-19. **Six native requests passed six mechanical and
six frozen-reference checks.** The five positive questions selected acceptable
IDs and the no-fit question explicitly declined. The batch is closed.

This is title-based location on six dependent development cases, not evidence
that Qwen is better than keyword search. The assisted keyword baseline also
covered all five positives and returned nothing for the no-fit control.
No saved source text was available or delivered, and no production route was
activated. SLQ and the original SLC records remain separate and unchanged.

## Paired outcomes

All twenty public bibliography titles entered each request without omission or
clipping. Only frozen instructions, the current question and title/ID catalog
were sent; keywords, references, report prose and private material were not.

| Case | Prepared keyword candidates | Native selection | Local outcome |
|---|---|---|---|
| SLC01 | A2 | A2 | missing_text; one completed local read |
| SLC02 | A4 | A4 | missing_text; one completed local read |
| SLC03 | P7 | P7 | missing_text; one completed local read |
| SLC04 | P5, P8 | P5 | missing_text; one completed local read |
| SLC05 | M1 | M1 | missing_text; one completed local read |
| SLC06 | none | explicit decline | declined; zero reads |

SLC04 passes both methods: the keyword candidate set covers 2/2 acceptable IDs,
while the valid native choice covers 1/2. Returning one rather than two does not
establish reduced human effort or greater quality. The model handled two Chinese
questions here, but two authored cases do not establish multilingual accuracy.

There were six callback entries, six durable reservations, six HTTP-primitive
entries and six responses; five local reads completed and **zero evidence texts
were delivered**. All observed count fields were available. No retries, repair,
fallback, external search, second model turn or resumed batch occurred.
A successful missing-text lookup does not mean the model detected missing text:
text availability was hidden from the selector.

The same-input keyword observation was rerun before credentials/output creation.
Whole-question literal misses remain diagnostic only. Prepared keywords were
author-supplied, so query formulation/translation effort, human time, real user
benefit and adoption remain unmeasured. This is not a fair cost-saving claim
against a measured human workflow, unseen accuracy or scientific entailment.

## Accounting, identity and execution limits

- Executed and reviewed commit: `11bd4bf75cf15f1184fe427535f56f71f8647bf7`.
- Public specimen/base commit: `6ac8f426ff54bfcef8b9a420a47827332985dd30`.
- Fixture SHA-256: `74bc2a26041a9365802d635e7e348387a47ce48404718793a2e5ce2f78c0e867`.
- Admitted unmodified baseline JSON SHA-256: `ef2ba8075ebbcb7eac467071cd673ecd4ac6cca3b111e20d945d7feb9e7d66ce`.
- Summary file byte SHA-256, including its final LF: `01ea5ebcaa110f89314a89d049dd7662ffb9a7b7c916bbae61a18e97a8b83899`.
- Identity file byte SHA-256, including its final LF: `dd3f07501c790eb314a12c37130a568009facea30ad1e3bec1f71719fcae2079`.

Each reply matched exact `qwen3.5-plus` and supplied coherent usage. Aggregate
reported usage was **7,250 prompt + 141 completion = 7,391 tokens**. The frozen
rate estimate was **USD 0.004639290**; conservative reservation consumption was
**USD 0.066895872** against the USD 0.10 soft ceiling. Neither is a provider
invoice. Unknown-usage requests and pending cases were both zero.

Per-case monotonic times through publication attempts ranged from 6.000 to
6.672 seconds, median 6.242, sum 37.734. These include local setup, identity,
callback, read, audit and publication work; they exclude batch setup and final
summary publication. They are not isolated provider latency, an SLO or a
timed comparison with a person.

Parent post-run inspection reconciled all six two-event reserve/finish journals,
request hashes, exact response-model checks, complete usage and persisted case
states. Raw batch artifacts remain ignored under the fixed
`outputs/report_evidence_source_locator_comparison_qwen_v1` directory. Do not
delete, reuse or reinterpret it as a new allowance. Local observations and
hashes do not independently attest network delivery or provider exactly-once.

## Engineering and independent LLM inspection

Before edits, 6,000 tests / 1,555 subtests passed. The reviewed implementation
passed **6,097 tests / 1,562 subtests**, 97 focused tests, the 457-test restored
regression, latest Ruff and narrow Pylint. All eight CI checks passed on the
exact execution commit before any native request.

The first focused validation failed at the incorrectly described historical
baseline encoding. Its correction was committed separately before native use;
outcomes/labels were not changed. Independent review also caught rejected
projection content being persisted. The fix withholds rejected result/choice
data and marks untrusted read counts unavailable without discarding usage.
Final independent read-only review found no remaining actionable issues.

Six real source reinjections made unchanged tests fail: stop bypass,
mechanical/reference conflation, refusal treated as empty success, pre-dispatch
identity bypass, baseline bypass and rejected-result publication. Source hashes
were restored before full regression and CI; these intended failures are not
native experiments.

A fresh label-blinded LLM context received only the public title catalog,
questions, native choices and local delivery states. It marked all six choices
`supported` **within title-location scope**, explicitly noting that P8 was
also valid for SLC04 and that no text or scientific support was established.
It saw no frozen labels, prepared queries, baseline hits or desired outcomes,
used no tools/external sources and made no additional paid Qwen judge call.

Configured role was `route_reviewer` (Astra/high); effective backend metadata
was unavailable. This is fallible context-limited LLM inspection, not human
gold or independent factual validation. Assistant/review effort was not costed.
UTF-8/LF text provenance, without an added trailing newline:

- Review input SHA-256: `769a3d12166bd427640016e06a9ee8381c01a54c53b6b2e0f2ebbf6de5daf712`.
- Full prompt SHA-256: `bd5b92dfe62fb1928028705d4fd0eb15c59f31f1f96324cfb3427980cfa070f3`.
- Returned review SHA-256: `22eee554f2fddfc3b5392f878022ae9987687ba2c2a308bb9b45d956362a9d2b`.

## Decision

Retain ordinary Sources browsing as the baseline. This batch supports a narrow
natural-language title-location candidate, not a superior search method or an
answering agent. Any next step should test whether an acceptable selection can
deliver actually available, authorized saved text in an isolated user-facing
flow, preserving missing/declined/unavailable states and original access/payment
boundaries. Do not add more search tools or silently enable production on the
strength of these six cases.
