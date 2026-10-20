/* Strings for the sample-report reader and the links to it.
 *
 * Kept out of i18n.js on purpose: that file's bytes are hash-locked by a frozen
 * experiment (report_evidence_source_locator_comparison.py), so adding keys
 * there would invalidate it. The language choice itself still comes from
 * i18n.js, so both tables follow one selector. Elements opt in with
 * data-samples-i18n rather than data-i18n, which i18n.apply() owns. */

import { language } from "./i18n.js";

const STRINGS = {
  English: {
    samples_link: "Browse sample reports — no key needed",
    samples_title: "Sample reports",
    samples_sub: "Finished assessments you can read without an access code or API keys. Opening one makes no model or search request.",
    samples_back: "Back to the app",
    samples_historical: "Historical output from an earlier pipeline version, committed {date} ({commit}). It shows the report format; it is not current model accuracy or an up-to-date market assessment, and its citations have not been re-verified.",
    samples_choose: "Choose a report above.",
    samples_list_failed: "The sample list could not be loaded.",
    samples_read_failed: "This report could not be loaded.",
    samples_missing: "No sample with that name.",
  },
  "Simplified Chinese": {
    samples_link: "无需 Key，先看示例报告",
    samples_title: "示例报告",
    samples_sub: "无需访问口令或 API Key 即可阅读的完整评估。打开示例不会发起任何模型或检索请求。",
    samples_back: "返回应用",
    samples_historical: "这是早期流水线版本的历史输出，提交于 {date}（{commit}）。它展示报告格式，不代表当前模型准确率或最新市场判断，其中引用也未重新核验。",
    samples_choose: "请在上方选择一份报告。",
    samples_list_failed: "示例列表加载失败。",
    samples_read_failed: "这份报告加载失败。",
    samples_missing: "没有这个示例。",
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
