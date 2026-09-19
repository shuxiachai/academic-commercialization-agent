# SLC: public bibliography search comparison preparation

Registered before implementation and search observation on 2026-09-19 from
`176a0bc679b44ba01588f9f7c10dcc6abdc82fa2`. Method:
`report_evidence_source_locator_comparison_v1`. This is an offline baseline
and comparison preparation, not a native runner, paid allowance or production
feature. The closed [SLQ batch](results-2026-09-19-source-locator-qwen-canary.md)
is neither reopened nor counted as observations on these new questions.

## Input scope and existing-data measurement

Use the already public, tracked
[solid-state battery example](../examples/solid-state-batteries-ev.md), not
private saved reports, ignored benchmark registries or reserved cohorts.
Its References section has 20 ordered entries: 4 academic, 8 patent and 8
market/industry codes. Historical prose and the examples index instead mention
7 market sources; use the actual bibliography inventory and retain the older
artifact unchanged. A count of entries is not validation of twenty sources.

Reconstruct only exact ID/title pairs. Bind the report's UTF-8 bytes normalized
from CRLF to LF, the exact ordered catalog and each reference-line title prefix.
Report SHA-256 under that rule:
`8fac15788439fecf6a6fbdcd32e4aea069ad8cfbb721aa54bd3abd8a8ee984cd`.

There is no public original source-summary registry for this specimen. Record
`unavailable_in_public_input`; never substitute report-generated prose, title
fallback or invented abstracts for original saved text. Do not fetch its URLs
or infer source truth, patent status or paper identity from the bibliography.

The Sources renderer admits these 20 ID/title rows below its single-page,
string and aggregate limits. The reconstructed catalog is also below the
locator's 32-title limit. This is a reused historical public specimen, not an
unseen report or a representative distribution of real user tasks.

## Freeze before seeing baseline outcomes

The fixture is `tests/fixtures/report_evidence_source_locator_comparison.json`.
It binds the report/catalog, current observer assets and six authored questions,
short keyword queries and acceptable reference sets. Keywords are explicitly
author-prepared assistance, not measured user behavior or automatic query
generation. Their spaces and punctuation are significant and remain unchanged.

| Case | Prepared query, exact | Acceptable IDs from visible titles |
|---|---|---|
| SLC01 | `HELENA` | A2 |
| SLC02 | `Machine Learning` | A4 |
| SLC03 | `multilayer` | P7 |
| SLC04 | `all-solid-state battery` | P5 and P8 are both acceptable |
| SLC05 | `[m1]` | M1 |
| SLC06 | `enzymatic` | No fitting title in this catalog |

A fresh `route_reviewer` context saw only the twenty ID/title pairs and the
six questions, not keywords, draft references or search results. It independently
returned A2, A4, P7, {P5,P8}, M1 and the empty set, explicitly rejecting forced
uniqueness and source-truth claims. This is context-limited LLM reference
adaptation, not human gold. Configured Astra/high is not effective backend
attestation; backend metadata was unavailable and no external sources were read.

UTF-8/LF text provenance of that pre-freeze review:

- Input JSON SHA-256: `3cda647fd61b5fb74611a07476ee6db65a8605b11e8f57edb099ca175e4e7d8a`.
- Full prompt SHA-256: `07c64ce89f34b8b29a41758b0cd3966e8f13eca49ecfa57e15ad9418709908c9`.
- Returned review SHA-256: `502c9859e1b8bd062aa9d5c7f20ec243a5ea58a63c3ccd55c729f548a9640758`.

## Observe the shipped filter, not a rewritten baseline

Reuse unchanged `tests/js/source_browser_contract.mjs` to load the actual
`web/static/js/result.js` and `i18n.js`, render source rows and dispatch search
input events. Bind all three normalized asset hashes from the fixture before
and after observation. No production JS or old harness is edited. This minimal
DOM observation exercises actual filter/render code, not browser layout,
keyboard behavior, real HTTP or an observed human search session.

The payload contains only title and ID in the three source groups. Publishers,
URLs, credibility, summaries and other inferred fields are absent. This matches
the locator's title/ID information scope but is NOT the richer original saved-
source UI input. Labels and planned outcomes never become observed hit lists.

Run both conditions for every case, with input strings unchanged:

1. `question_literal_diagnostic`: the complete natural-language question in
   the existing literal search input. This tests input-shape mismatch and is
   not a fair primary quality comparison against a language model.
2. `prepared_keyword_assisted`: the frozen short query above. This is the
   assisted keyword condition, not evidence that users formulate it for free.

Use a fixed Node subprocess argument list and JSON stdin; no shell evaluation,
provider import, credentials, searches or new JS implementation. Require complete
initial delivery of the twenty ordered IDs/titles and all twelve filter states,
matching query values, no partial/unreadable warnings, no unexpected pagination
or endpoint calls. Missing Node/assets, timeout, process/parse errors, drift or
partial observations are `unavailable`, with null hit data, never empty success.
Do not modify an old script or silently skip the observation to obtain a pass.

## Interfaces and metrics

Add `academic_agent.report_evidence_source_locator_comparison` and dedicated
tests. Separate manifest preparation, Node observation and set-based grading.
Default module CLI runs this fixed offline comparison and prints JSON only;
no output directory, provider adapter or model callback is introduced.

For each condition report six planned cases, observed/unavailable cases,
observed IDs and candidate count. For a nonempty acceptable set, report
intersection and its fraction of the reference set. For an empty reference,
that fraction is null and catalog-level no-match behavior is reported separately.
A unique acceptable hit means exactly one total hit that is acceptable.

SLC04's two acceptable hits are NOT a failure; one acceptable hit is also useful
location, with lower reference-set coverage. Do not force a top-one score on an
unranked candidate list or call it model accuracy. There are six dependent cases
and twelve paired condition observations, not twelve independent samples.
Keep unavailable units visible in the planned denominator.

The model lane is explicitly `not_run`, with zero evaluated model cases and
null model quality/benefit. Do not report 0/6 model accuracy, script references
as model outputs, cost savings or user time savings. No runtime semantic flag,
retrieval behavior, score, access control or production entry point changes.

## Offline acceptance and stopping rules

Use real Node observations on the public specimen and focused generated boundary
controls in tests. Keep expected labels separate from the Node input. Tests
must reject malformed/missing/partial states, wrong query or source identity,
duplicate/hidden IDs, false pagination completeness and fabricated nonempty text.

Reinject: (a) observer failure presented as an empty observed result, (b) accepting
partial initial source delivery as complete, and (c) treating multi-hit acceptable
results as incorrect. Corresponding unchanged assertions must fail and then
pass after exact restoration. No warning ignores, weakened assertions or skips.

Run before/after full zero-provider tests, latest Ruff, narrow Pylint and
independent read-only review. Freeze the offline output as a qualified public
baseline result. Keywords/references cannot be retuned after seeing it and
called validation. If the observer cannot execute, report the unavailable
baseline instead of a winner. A later model comparison needs its own frozen
native execution scope and applicable data/budget boundary; SLC preparation and
SLQ success provide neither production admission nor private-data permission.
