/* Strings for the sample-report reader and the links to it.
 *
 * Written while i18n.js was hash-locked by a frozen experiment
 * (report_evidence_source_locator_comparison.py); since 2026-10-22 that
 * experiment reads a snapshot instead. The language choice itself still comes
 * from i18n.js, so both tables follow one selector. Elements opt in with
 * data-samples-i18n rather than data-i18n, which i18n.apply() owns. */

import { language } from "./i18n.js";

const STRINGS = {
  English: {
    samples_link: "Browse sample reports — no key needed",
    samples_title: "Sample reports",
    samples_sub: "Finished assessments you can read without an account or API keys. Opening one makes no model or search request.",
    samples_back: "Back to the app",
    samples_added: "Added {date}",
    samples_historical: "A run of {date} on pipeline {commit} with {model}, kept as the pipeline wrote it. One report shows the format, not a measure of accuracy or an up-to-date market assessment, and its citations have not been re-verified.",
    samples_choose: "Choose a report above.",
    samples_list_failed: "The sample list could not be loaded.",
    samples_read_failed: "This report could not be loaded.",
    samples_missing: "No sample with that name.",
    samples_contents: "Contents",
    samples_download: "Download Markdown",
    samples_scorecard: "Scorecard",
    samples_brief_note: "Built from this run's own scorecard and report, by the same code as a run's page; no new model call. A sample keeps neither the run's checks nor its source list, so the lines those would add are not shown here.",
  },
  "Simplified Chinese": {
    samples_link: "无需 Key，先看示例报告",
    samples_title: "示例报告",
    samples_sub: "无需账号或 API Key 即可阅读的完整评估。打开示例不会发起任何模型或检索请求。",
    samples_back: "返回应用",
    samples_added: "收录于 {date}",
    samples_historical: "{date} 在流水线 {commit} 上用 {model} 跑出的一次运行，保持原样。单份报告展示的是格式，不代表准确率或最新市场判断，其中引用也未重新核验。",
    samples_choose: "请在上方选择一份报告。",
    samples_list_failed: "示例列表加载失败。",
    samples_read_failed: "这份报告加载失败。",
    samples_missing: "没有这个示例。",
    samples_contents: "目录",
    samples_download: "下载 Markdown",
    samples_scorecard: "评分卡",
    samples_brief_note: "由这次运行自己的评分卡和报告生成，与运行页面用的是同一段代码，没有新的模型调用。示例不保留这次运行的各项检查和来源清单，所以由它们得出的几行这里不显示。",
  },
};

/** Translate a sample key, falling back to English and then the key. */
export function st(key) {
  return STRINGS[language()]?.[key] ?? STRINGS.English[key] ?? key;
}

/** Translate every element marked with data-samples-i18n. */
export function applySamples(root = document) {
  for (const node of root.querySelectorAll("[data-samples-i18n]")) {
    node.textContent = st(node.dataset.samplesI18n);
  }
}
