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
    samples_sub: "Finished assessments you can read without an account or API keys.",
    samples_back: "Back to the app",
    samples_skip: "Skip to the report",
    samples_added: "Added {date}",
    samples_historical: "A run of {date} with {model}, kept as it was written. One report shows the format, not a measure of accuracy or an up-to-date market assessment, and its citations have not been re-verified.",
    samples_tech: "Technical details",
    samples_revision: "Pipeline revision: {commit}",
    samples_decision_context: "This run was given a decision context, so its report states a conclusion for the decision below. Asset: “{asset}”. Target application: “{application}”.",
    samples_card_decision: "With a decision conclusion",
    samples_choose: "Choose a report above.",
    samples_list_failed: "The sample list could not be loaded.",
    samples_read_failed: "This report could not be loaded.",
    samples_try_again: "Try again",
    samples_missing: "No sample with that name.",
    samples_contents: "Contents",
    samples_download: "Download Markdown",
    samples_scorecard: "Scorecard",
    samples_brief_note: "A sample keeps only the report and its scorecard, not the run's automatic checks or its source list, so this brief leaves out the lines that depend on them.",
    samples_previous: "Previous: {title}",
    samples_next_sample: "Next: {title}",
    samples_neighbours: "Neighbouring samples",
    samples_next: "Run one on your own topic.",
    samples_next_create: "Create account",
    samples_next_signin: "Sign in",
    samples_next_open: "Open the app",
  },
  "Simplified Chinese": {
    samples_link: "无需 Key，先看示例报告",
    samples_title: "示例报告",
    samples_sub: "无需账号或 API Key 即可阅读的完整评估。",
    samples_back: "返回应用",
    samples_skip: "跳到报告",
    samples_added: "收录于 {date}",
    samples_historical: "{date} 用 {model} 跑出的一次运行，保持原样。单份报告展示的是格式，不代表准确率或最新市场判断，其中引用也未重新核验。",
    samples_tech: "技术细节",
    samples_revision: "流水线版本：{commit}",
    samples_decision_context: "这次运行填写了决策场景，所以报告针对下面的决策给出了结论。资产或科研成果：“{asset}”；目标应用：“{application}”。",
    samples_card_decision: "含决策结论",
    samples_choose: "请在上方选择一份报告。",
    samples_list_failed: "示例列表加载失败。",
    samples_read_failed: "这份报告加载失败。",
    samples_try_again: "重试",
    samples_missing: "没有这个示例。",
    samples_contents: "目录",
    samples_download: "下载 Markdown",
    samples_scorecard: "评分卡",
    samples_brief_note: "示例只保留了报告和评分卡，没有运行时的自动检查和来源清单，所以简报少了依赖它们的几行。",
    samples_previous: "上一份：{title}",
    samples_next_sample: "下一份：{title}",
    samples_neighbours: "相邻示例",
    samples_next: "用你自己的主题跑一份。",
    samples_next_create: "创建账号",
    samples_next_signin: "登录",
    samples_next_open: "打开应用",
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
