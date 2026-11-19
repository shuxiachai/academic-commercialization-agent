# Report headings in the report's language, and the English a Chinese report carries

**Date:** 2026-11-19 (UTC).
**Status:** offline measurement on the reports saved on the maintainer's
machine, and a reading of the code path behind one production observation.
The two production runs were read back from the deployment with the
maintainer's consent (GET requests only: each run's status, and the resumed
run's saved report); excerpts are kept in `tests/fixtures/report_headings/`
with the same consent. No search or model request was made.
**Production:** the heading table, its use by a run and by the display layer,
the "GO / NO-GO" spelling in a displayed report, the one-line note and the
resume retry are in the change that carries this file. No prompt, score,
applicability rule or saved report changed.

## Why

A Chinese run on production (2026-11-18, topic 钠离子电池用于电网储能) failed
after its reviewer and was resumed. The resumed run finished, and its report
read as Chinese text under English headings: "Academic Commercialization
Assessment: 钠离子电池用于电网储能", "Executive Summary", "1. Technology
Overview & Maturity", and so on to "Evidence Limitations". Only the reference
list's heading was Chinese, because the display layer already translated that
one. Nothing on the page said why. The same report carried English from the
writer's contract inside Chinese sentences ("actor-specific GO/NO_GO is not
assessed"), and its scope line wrote "GO/NO_GO" where the rest of the page
writes "GO / NO-GO".

## Why the headings stayed English

Read from the code as it stood at `cd368d3` and from the two runs' status as
the deployment serves it; no call was made.

1. **Where.** `language.translate_headings`, called once by
   `source_pipeline.collect_source_collection` when the topic is not English
   (and by the worker when an English topic is given another output language).
   Its input is the nine required headings (`evidence._REQUIRED_REPORT_HEADINGS`)
   and the language's name; it is one auxiliary request of at most 400 output
   tokens, recorded in the run's `auxiliary_usage` as `heading_translation`.
2. **What a failure returned.** The nine English originals, as a non-empty
   list. Nothing told that apart from a translation: the writer was given the
   English headings as "the required section headings (use these exactly)",
   the report guardrail checked for them, and the report was saved with them.
3. **Why the resume did not ask again.** The headings are stored in the
   source collection, which is the retrieval checkpoint. A resume that reuses
   retrieval skips the whole language step (`if not retrieval_reused and …`),
   and the worker's own second chance asked only `not localized_headings`,
   which a list of English headings never satisfies. So the resumed run made no
   auxiliary call at all: its record shows `call_count` 0. It reused
   retrieval, the three evidence agents, the writer and the reviewer, and ran
   only the scorer. The report it delivered is the failed run's own, written
   under the English headings before the resume began, so asking again at the
   resume could not have changed it.
4. **Why the call itself failed twice.** The failed run's record shows two
   `heading_translation` attempts on `qwen3.8-2.4t-a95b`, both `call_failed`
   with no tokens: an exception before a reply was parsed. The model refuses
   `enable_thinking=false` (measured 2026-11-16), and every worker is a new
   process that has learned nothing about its model, so a helper request that
   reaches the provider with thinking off is refused with HTTP 400 and resent
   with thinking on (`llm_parameter_fallback`). The likeliest reading is
   therefore: the first attempt is that refusal, the second is the resent
   request failing by itself. The other reading the code allows is a
   connection that failed before the first request was sent, then a second
   request failing while it waited. Either way the last attempt was a failure
   the helper does not try again, and it was not a connection failing before
   the request was sent, which is tried three times (`_UNSENT_ATTEMPTS`). It
   was also not the full 120-second wait a thinking model is given: the whole
   source-collection stage, searches included, took 77 seconds. What it was
   (an HTTP error, a dropped connection, the 60-second wait) is not recorded
   anywhere the API serves: the auxiliary ledger keeps outcomes only, by
   design, and the helper's warning goes to the worker's standard error. No
   cause is claimed for it. `tests/test_report_headings.py` reproduces the
   recorded pair with a refusal followed by a timeout and holds the result to
   the record field by field.

The translation was a model call for a task that needs none: the headings are
a fixed set, and the saved reports show what they are translated into.

## What was measured

`scripts/audits/report_heading_audit.py` reads every
`commercialization_report.md` under a directory of runs:

```
uv run python -m scripts.audits.report_heading_audit outputs
```

On the maintainer's machine, 2026-11-19: **1,797 reports**. By language, as
the display layer reads it: 1,736 English, 58 Simplified Chinese (50 by their
applicability paragraph or reference legend, 8 by their characters), 2
Japanese, 1 Korean.

### Headings

Of the 58 Chinese reports, **none** was saved under any required English
heading: the failure is not in the local data, and the production run is the
only instance seen. 57 have exactly eight headings before their reference
list; what the model wrote at each position:

| Required heading | Written as (count of 57) |
|---|---|
| `# Academic Commercialization Assessment:` | 学术商业化评估 42 · 学术成果商业化评估 15 |
| `## Executive Summary` | 执行摘要 57 |
| `## 1. Technology Overview & Maturity` | 技术概述与成熟度 53 · 技术概览与成熟度 4 |
| `## 2. Patent Landscape & White Spaces` | 专利布局与空白领域 25 · 专利格局与空白领域 24 · 专利格局与技术空白 8 |
| `## 3. Target Industries & Use Cases` | 目标行业与应用场景 55 · 目标行业与应用案例 2 |
| `## 4. Competitive Landscape` | 竞争格局 57 |
| `## 5. Commercialization Opportunities & Recommendations` | 商业化机遇与建议 39 · 商业化机会与建议 18 |
| `## Evidence Limitations` | 证据局限性 57 |

The table (`report_display.HEADING_TRANSLATIONS`) takes the most frequent
wording at each position, with one exception: the title is the product's name
as the page's own header writes it, 学术成果商业化评估, which the model wrote 15
times against 42 for the shorter form. The three Japanese and Korean reports
gave the wording for those two languages. The other nine languages (Traditional
Chinese, German, French, Spanish, Italian, Portuguese, Russian, Arabic, Hindi)
were written for the table and **no native reader has reviewed them**. Before
the table, each run's own model translation was reviewed by nobody either, and
differed from run to run, as the Chinese counts show.

### "GO/NO_GO"

In all 1,797 reports the compound occurs 429 times: `GO/NO_GO` 409,
`GO/NO-GO` 10, lower-case `go/no-go` 7, and three in code marks inside
applicability paragraphs. By place: the report's prose 410, the proofreading
record 16, the applicability paragraph 3, the reference list 0. The display
rule respells the upper-case forms in the prose, the proofreading record and
the scope paragraph, and leaves alone the lower-case English phrase ("a
go/no-go decision"), the reference list (a source's title is the source's) and
the verdict word `NO_GO` standing alone (8 occurrences in 8 reports; a
conclusion is quoted as written).

Old display against new, over the same 1,797 reports: 1,599 are shown
byte for byte as before; 198 differ only in this spelling, on 404 lines.
Nothing else changed in any of them.

### English inside Chinese reports

In the prose of the 58 Chinese reports (applicability paragraph and reference
list excluded):

| What | Reports | Occurrences |
|---|---|---|
| `freedom-to-operate` (kept in Latin on purpose, `evidence.py`) | 51 | 86 |
| `GO/NO_GO` | 18 | 47 |
| the code word `orientation`, usually as a gloss: "定向（orientation）模式" | 9 | 18 |
| "analyst proposal…" | 3 | 3 |
| "actor-specific" | 1 | 1 |
| "…not assessed" | 1 | 1 |
| "success criteria" | 1 | 1 |

Nine reports have a run of five or more English words inside a Chinese line,
twelve runs in all. Three of the twelve are the contract's wording ("analyst
proposal requiring owner confirmation" twice, "actor-specific GO/NO_GO is not
assessed" once). The other nine are a journal's name, a company's name, a
source's title or its registry rationale.

## What was decided

- **Headings: a table, used twice.** A run in a language the table has takes
  its headings from it and makes no call. A report already saved under the
  English headings is shown under the table's, on the page, in the PDF and in
  the words of the decision card; the saved file and its Markdown download
  keep every byte. A language the table lacks still gets one model call.
- **"GO/NO_GO": respelt when shown.** It is one token with one meaning, it
  occurs in a tenth of all reports, and the page already writes it the other
  way everywhere else.
- **Other English in Chinese prose: left alone.** The sentence from the
  production report occurs once in 58 reports. The phrases are the model's
  own prose, worded differently each time, and most English inside a Chinese
  line is a name. A display rule that rewrote them would change what a report
  says on the strength of a pattern, for at most three reports in 58. If it
  is to be fixed, the place is the writer's contract, which a paid comparison
  would have to justify; that is not proposed here.
- **Resume.** The headings are part of every agent's checkpoint identity (the
  crew inputs and the collection are both hashed). A resumed run therefore
  asks for them again only when the earlier run committed no agent output;
  otherwise it keeps the paid work, and the report is shown under the table's
  headings. In a language the table lacks, the report tab says in one line
  that the headings are English.

## Limits

- The failure itself is one production run. Its last failed attempt has no
  recorded cause, and none is claimed.
- Nine of the twelve translations have not been read by a native reader.
- A report whose headings the writer changed (a suffix, another level) is not
  touched: only a line that is exactly a required heading is shown translated.
- The reference list's heading and labels are still translated for Chinese
  only; in other languages the list is shown as saved.
- A PDF exported before this change is rebuilt once, on its next download.
