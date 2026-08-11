/* Interface language.
 *
 * Distinct from the report language: this translates the chrome, while the
 * report language is passed to the pipeline and decides what the agents
 * write. A user reading Chinese reports may still want an English interface,
 * so the two are chosen separately.
 *
 * English is the source. A missing key falls back to it rather than showing
 * a bare identifier — a partially translated interface is still usable.
 */

const STRINGS = {
  English: {
    // Chrome
    brand: "Assessment",
    new_analysis: "New analysis",
    no_runs: "No runs yet",
    group_today: "Today",
    group_yesterday: "Yesterday",
    group_earlier: "Earlier",
    running_label: "running",
    offline: "offline",

    // Composer
    compose_title: "What should we assess?",
    compose_sub: "Six agents gather academic, patent, and market evidence, then score commercialization readiness. Every claim carries a citation.",
    topic_placeholder: "perovskite solar cells for utility-scale power generation",
    attach: "Paper",
    auto_lang: "Auto language",
    auto_profile: "Auto profile",

    // Stages
    stage_sources: "Collecting and validating sources",
    stage_evidence: "Academic · Patent · Market analysis",
    stage_report: "Writing the report",
    stage_review: "Reviewing citations and claims",
    stage_scoring: "Scoring commercialization readiness",

    // Run pane
    cancel: "Cancel",
    download_report: "Report",
    sources_suffix: "sources",
    academic: "academic",
    patent: "patent",
    market: "market",

    // Result
    tab_score: "Scorecard",
    tab_report: "Report",
    tab_sources: "Sources",
    readiness: "commercialization readiness",
    band_strong: "Strong",
    band_moderate: "Moderate",
    band_early: "Early",
    band_nascent: "Nascent",
    dim_trl: "Technology readiness",
    dim_mrl: "Manufacturing readiness",
    dim_patent: "Patent position",
    dim_market: "Market accessibility",
    dim_evidence: "Evidence confidence",
    risks: "Risks",
    opportunities: "Opportunities",
    group_academic: "Academic",
    group_patents: "Patents",
    group_market: "Market",
    no_artifacts: "This run produced no artifacts.",

    // Messages
    msg_complete: "Analysis complete.",
    msg_cancelled: "Run cancelled.",
    msg_busy: "Both run slots are busy. Try again when one finishes.",
    msg_paper_attached: "Paper attached.",
    msg_not_pdf: "That is not a PDF.",
    msg_too_large: "That PDF is over the 50 MB limit.",
    msg_reading: "Reading",
    msg_wait_extract: "Waiting for the paper to finish extracting",
    run_hint: "Run analysis  (Enter)",

    // Access gate
    gate_title: "Access code required",
    gate_sub: "This is a private demo link. Enter the code you were given.",
    gate_placeholder: "Access code",
    gate_submit: "Continue",
    gate_error: "That code was not accepted.",
    gate_no_code: "No code? Use your own API keys instead",

    // Bring-your-own-key
    byok_title: "Use your own API keys",
    byok_sub: "Nothing is sent anywhere but this run's worker process, and nothing is saved once you close the tab.",
    byok_llm_placeholder: "LLM API key",
    byok_serper_placeholder: "Serper API key",
    byok_hint: "Keys: platform.deepseek.com/api-keys · platform.openai.com/api-keys · console.anthropic.com — and serper.dev/api-key for search (free tier available).",
    byok_submit: "Start",
    byok_have_code: "I have an access code",
    byok_badge: "Using your own API keys",
    byok_exit: "Exit",
    byok_no_history: "Run history is only visible with an access code. Your run stays open in this tab once it starts.",
    byok_no_attach: "Paper upload needs an access code",
  },

  "Simplified Chinese": {
    brand: "商业化评估",
    new_analysis: "新建分析",
    no_runs: "暂无运行记录",
    group_today: "今天",
    group_yesterday: "昨天",
    group_earlier: "更早",
    running_label: "运行中",
    offline: "未连接",

    compose_title: "要评估什么技术？",
    compose_sub: "六个智能体收集学术、专利与市场证据，评估商业化就绪度。每条结论都附带可核查的引用。",
    topic_placeholder: "钙钛矿太阳能电池在公用事业级发电中的应用",
    attach: "论文",
    auto_lang: "自动语言",
    auto_profile: "自动方案",

    stage_sources: "收集并校验来源",
    stage_evidence: "学术 · 专利 · 市场分析",
    stage_report: "撰写报告",
    stage_review: "审查引用与论断",
    stage_scoring: "评估商业化就绪度",

    cancel: "取消",
    download_report: "报告",
    sources_suffix: "条来源",
    academic: "学术",
    patent: "专利",
    market: "市场",

    tab_score: "评分卡",
    tab_report: "报告",
    tab_sources: "来源",
    readiness: "商业化就绪度",
    band_strong: "较强",
    band_moderate: "中等",
    band_early: "早期",
    band_nascent: "萌芽",
    dim_trl: "技术就绪度",
    dim_mrl: "制造就绪度",
    dim_patent: "专利地位",
    dim_market: "市场可及性",
    dim_evidence: "证据置信度",
    risks: "风险",
    opportunities: "机会",
    group_academic: "学术",
    group_patents: "专利",
    group_market: "市场",
    no_artifacts: "该次运行没有产出任何文件。",

    msg_complete: "分析完成。",
    msg_cancelled: "运行已取消。",
    msg_busy: "两个运行槽位都在忙，等一个结束后再试。",
    msg_paper_attached: "论文已附加。",
    msg_not_pdf: "这不是 PDF 文件。",
    msg_too_large: "PDF 超过 50 MB 上限。",
    msg_reading: "正在读取",
    msg_wait_extract: "等待论文提取完成",
    run_hint: "开始分析（回车）",

    gate_title: "需要访问口令",
    gate_sub: "这是一个私密演示链接，请输入你收到的口令。",
    gate_placeholder: "访问口令",
    gate_submit: "继续",
    gate_error: "口令不正确。",
    gate_no_code: "没有口令？改用自己的 API Key",

    byok_title: "使用自己的 API Key",
    byok_sub: "密钥只会传给这次运行的工作进程，关闭标签页后不会被保存。",
    byok_llm_placeholder: "LLM API Key",
    byok_serper_placeholder: "Serper API Key",
    byok_hint: "获取密钥：platform.deepseek.com/api-keys · platform.openai.com/api-keys · console.anthropic.com；检索用的 serper.dev/api-key 有免费额度。",
    byok_submit: "开始",
    byok_have_code: "我有访问口令",
    byok_badge: "正在使用自己的 API Key",
    byok_exit: "退出",
    byok_no_history: "运行历史仅对持有访问口令的访客可见。本次运行会一直显示在当前标签页里。",
    byok_no_attach: "上传论文需要访问口令",
  },
};

const STORAGE_KEY = "ui-language";

let current = localStorage.getItem(STORAGE_KEY) ?? "English";
if (!STRINGS[current]) current = "English";

/** Translate a key, falling back to English and then to the key itself. */
export function t(key) {
  return STRINGS[current]?.[key] ?? STRINGS.English[key] ?? key;
}

export function language() {
  return current;
}

export function setLanguage(next) {
  if (!STRINGS[next]) return;
  current = next;
  localStorage.setItem(STORAGE_KEY, next);
  apply();
}

/** Apply translations to everything declaratively marked in the HTML. */
export function apply(root = document) {
  for (const node of root.querySelectorAll("[data-i18n]")) {
    node.textContent = t(node.dataset.i18n);
  }
  for (const node of root.querySelectorAll("[data-i18n-placeholder]")) {
    node.placeholder = t(node.dataset.i18nPlaceholder);
  }
  document.documentElement.lang = current === "English" ? "en" : "zh-CN";
}
