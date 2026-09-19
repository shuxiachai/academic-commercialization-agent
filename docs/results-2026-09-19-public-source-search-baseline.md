# SLC: observed public-title keyword baseline

The [frozen SLC comparison](prereg-2026-09-19-public-source-search-comparison.md)
completed all twelve paired observations over six authored questions. Prepared
keywords exposed an acceptable title for all five positive-reference cases;
four had one candidate and one had two acceptable candidates. The no-fit control
returned no titles. **No Qwen comparison ran**, so this is not evidence that
either method is better, cheaper for a user, or ready for production.

## What was actually observed

The input is twenty ID/title entries reconstructed from an already public,
historical battery report: four A codes, eight P codes and eight M codes.
Original saved summaries are unavailable and were not invented from report
prose. Source facts, patent status and original registry completeness were not
checked. These are new development questions over reused public metadata, not
unseen reports, expert gold or real user behavior.

The unchanged Sources JavaScript renderer/filter ran through the existing Node
minimal-DOM observer. One complete initial twenty-row display and twelve search
input events were checked. No source warnings, unreadable records, unexpected
pagination, storage writes or logs occurred. The report/source reads were local
mock API observations, not HTTP requests. This is not a Chromium layout or
keyboard test and does not measure human query formulation or decision time.

| Case | Exact author-prepared query | Observed IDs | Acceptable-set coverage | Unique acceptable hit |
|---|---|---|---|---|
| SLC01 | `HELENA` | A2 | 1/1 | yes |
| SLC02 | `Machine Learning` | A4 | 1/1 | yes |
| SLC03 | `multilayer` | P7 | 1/1 | yes |
| SLC04 | `all-solid-state battery` | P5, P8 | 2/2 | no; both candidates are acceptable |
| SLC05 | `[m1]` | M1 | 1/1 | yes |
| SLC06 | `enzymatic` | none | not applicable: no fitting title reference | no; no-fit control matched |

There are **six cases, not twelve independent samples**. Each condition has
five evaluable positive-reference cases and one no-fit control; all six were
observed, with zero unavailable cases. Returning either P5 or P8 alone would
also be acceptable location, with one-half reference-set coverage. A list of
multiple valid candidates must not be scored as an incorrect top-one answer.

All six complete natural-language questions returned no literal matches in the
separate diagnostic condition. That is an input-shape observation: the current
search is a literal substring/whole-ID filter, not a question-answering endpoint.
Do not use those zero hits as the main baseline to manufacture a model win.

The short queries were authored before observation, not produced by a measured
user or free automatic query generator. The Chinese question's English search
phrase was already supplied. The experiment therefore cannot price the effort
of translating a request into a useful query or claim human time savings.

## Identity and regression evidence

- Executed comparator commit: `1b8b75f92ad0da42f6d76329cf95ec3c65043c1e`.
- Public specimen base: `176a0bc679b44ba01588f9f7c10dcc6abdc82fa2`.
- Fixture SHA-256: `74bc2a26041a9365802d635e7e348387a47ce48404718793a2e5ce2f78c0e867`.
- Normalized report SHA-256: `8fac15788439fecf6a6fbdcd32e4aea069ad8cfbb721aa54bd3abd8a8ee984cd`.
- Canonical comparator-output SHA-256: `8e8405087757368672736a43d858094349bea6c295029ffe4ea8a3ef15c385d8` (sorted keys, compact ASCII JSON, no trailing newline).

The report, exact queries/reference sets and three observer assets were frozen
before the first search observation. Their identities were unchanged. A direct
parent harness run and the committed comparator agreed on all observed IDs.
The reference adaptation used the separate label-blinded LLM review documented
in the preregistration; this is not human validation or source-truth assessment.

Baseline tests: 5,859 / 1,547 subtests passed. The reviewed implementation passed
6,000 tests / 1,551 subtests; 141 focused boundary tests, latest Ruff and narrow
Pylint also passed. Independent review caught first-draft gaps in malformed-state
handling, incomplete/fabricated row admission and missing positive assertions.
Those were fixed, then re-reviewed without remaining actionable findings.

Actual source mutations made unchanged tests fail: an observer failure relabeled
as empty success, partial initial delivery accepted as complete, and a false
multi-hit penalty. The implementation was restored exactly after each mutation.
Unavailable cases retain planned denominators and null hit metrics; they cannot
be silently converted to no-match controls. No earlier fixture, renderer,
harness, historical report or SLQ result was modified.

The observer is version-bound: asset drift makes a new invocation unavailable,
not comparable by default. Do not silently rehash the frozen input just to retain
a green baseline. A deliberately changed Sources behavior needs a separately
identified observation and must not overwrite this historical result.

## Decision and next gate

The model lane is `not_run`, with zero evaluated model cases and null quality
and benefit. There were no Qwen requests or private-data transmissions in this
phase; assistant/reference-review effort was not costed. SLQ remains a separate closed synthetic native
observation, not the model arm of SLC.

Keep ordinary keyword browsing as the baseline. If continuing, evaluate optional
natural-language location on the same information scope and acceptable-ID sets,
recording failures, extra cost and candidate burden without treating assisted
queries as free human behavior. That requires a separately frozen native scope.
This preparation does not authorize private saved-text transmission, automatic
paid dispatch or a public follow-up endpoint, and it proves no model benefit yet.
