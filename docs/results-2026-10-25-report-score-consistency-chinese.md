# Results: the report-versus-scorecard check reads Chinese conclusions

Date: 2026-10-25. Module: `src/academic_agent/consistency.py`. Offline, zero
model calls; everything below was computed from runs already on disk.

## What was wrong

The check finds the report's two conclusion sections ("Executive Summary",
"Commercialization Opportunities & Recommendations") by their English headings
and reads the report's own advice there against the overall score. A Chinese
report carries translated headings, so the sections were never found, the
check returned unchecked, and the result page's reliability panel showed
"Not run — this check reads English conclusions only" on every Chinese run.

Measured on the Chinese runs on disk before any change: **checked 0 of 39**.

## Corpus

39 runs under `outputs/` whose report carries `## 执行摘要`, produced between
2026-07-07 and 2026-08-21 by the normal six-agent pipeline. Overall scores
38.3–84.0 (median 58). Each run recorded `output_language: "Simplified Chinese"`
and a complete nine-line `localized_headings` list in `validated_sources.json`.
Conclusion text per run: 1,156–2,971 characters (median 1,825).

For regression, the 40 non-Chinese runs with scores under `outputs/` and the
30-run baseline corpus under `outputs/benchmark/`.

## Headings

The heading translator is a model, and the corpus shows it: section 5 is
`商业化机遇与建议` in 33 runs and `商业化机会与建议` in 6; `执行摘要` is stable
(39/39). The check now matches heading stems (`执行摘要`, `商业化机遇`,
`商业化机会`) rather than whole headings, and the worker also hands over the
run's own translated headings (positions 1 and 6 of the required list, the
order the translator keeps), so a third rendering on a future run is still
read. An incomplete list is ignored: the translator returns the English
originals when its line count is off, and a partial list would put another
section at the conclusions' positions.

## Phrases: what the corpus said about the obvious candidates

Every candidate word was read in context with the run's score before any
phrase was admitted. Counts are over the 39 runs' conclusion text.

| Candidate | Runs (scores) | What it meant in the corpus | Admitted form |
|---|---|---|---|
| 立即 | 6 (57–79) | a patent filing ×4, a research start ×1, a competitor's integration ×1 | only bound to 商业化 / 产业化 / 市场化 / 量产 / 进入市场 / 推向市场 |
| 已具备 | 2 (50, 74) | "basic scientific validation, but…"; a competitor's competitiveness | only 已(经)具备/做好/达到 + 商业化/产业化/量产 + 条件/准备/要求/水平 |
| 低风险 | 2 (59, 60) | a low-risk use case or application | only 低风险(的)投资 |
| 进入市场 | 1 (51) | "a feasible path to enter the market may be…" | only after 应 / 应当 / 可以 / 可 / 建议 (+ 尽快 / 立即 / 直接) |
| 值得投资 | 1 (51) | an adjacent technology (RAG architectures) | not admitted |
| 强烈 | 1 (60) | 强烈的竞争态势 (intense competition) | only 强烈建议 / 强烈推荐 / 高度推荐 |
| 吸引力 | 3 (58–70) | a market segment; heat recovery economics; licensing appeal | only 极具投资价值 / 极具吸引力的投资 / 非常有吸引力的投资 / 绝佳的投资 |
| 推荐 | 2 (64, 67) | 推荐商业化路径 (a sub-heading); 推荐战略 | not admitted |
| 建议 … 投资 | 15 hits (44–84) | invest in a research or manufacturing direction | not admitted; the English table has no equivalent either |
| 成熟 | 40 hits (38–84) | maturity descriptions, mostly 技术成熟度 | only 商业化(条件)已/已经成熟/就绪 |

Eight patterns were admitted, with the English thresholds (60; 55 for the
"strongly recommend" family). None of the eight occurs anywhere in the 39
conclusion texts, negated or not.

Chinese negations and conditions (`尚未 并未 未 不宜 不应 不能 不建议 不推荐 不足
不可 不具备 无法 并非 缺乏 难以 仍需 还需 需要 须 之前 直到 一旦 除非 才 没有 尚不
还不 远未 有待 若 如果 假如 只有`) use the English 60-character window before a
match; there are no word boundaries in the script, so none are used.

## After

| Corpus | Before | After |
|---|---|---|
| 39 Chinese runs, with the run's language and headings | checked 0, flagged 0 | checked 39, flagged 0 |
| 39 Chinese runs, built-in headings only | checked 0 | checked 39, flagged 0 |
| 40 non-Chinese runs on disk | — | every verdict identical to before (dict equality), 35 checked, 0 flagged |
| 30-run baseline corpus | 0 flagged | 0 flagged, 0 verdicts changed |

Synthetic positives (tests): each of the eight phrase families, placed in the
recommendations of a Chinese report, is flagged exactly once at score 40 and
not at 72; five denials or conditionals and six sentences taken from the
corpus (patent filing "立即", "低风险场景", "成功进入市场的可行路径",
"值得投资", "已具备基础科学验证") are not flagged at 40. A report whose
language has no phrase table (Japanese, Traditional Chinese, German) is
unchecked, never consistent.

## Not measured

- No Chinese report in the corpus contains a strong recommendation, so recall
  on real Chinese text is untested; the positives are synthetic sentences.
- The negation window was carried over from English. In Chinese, 60 characters
  is about two sentences, so a denial anywhere in the previous sentence also
  silences a claim. This is the precision-over-recall choice the English axis
  made, kept deliberately.
- Traditional Chinese is excluded: the stems and phrases are simplified, and a
  traditional report would be found through its own headings and then read as
  clean. Adding it means a second phrase table and a corpus to check it on.
