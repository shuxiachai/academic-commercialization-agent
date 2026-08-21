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
    retention_note: "Runs on this deployment are deleted automatically after {days} days.",
    retention_forever: "Runs on this deployment are kept until deleted manually.",
    tokens_suffix: "tokens",
    price_basis: "Price basis",
    cost_partial: "Partial estimate — no price known for: {models}",

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
    delete_run: "Delete",
    confirm_delete_run: "Delete this run permanently? The report and every other artifact will be gone for good.",
    confirm_broad_topic: "This topic may be too broad for reliable academic, patent, and market retrieval. Add a specific technology and use case for a stronger report.\n\nRun it anyway?",
    msg_deleted: "Run deleted.",
    download_report: "Report",
    sources_suffix: "sources",
    academic: "academic",
    patent: "patent",
    market: "market",

    // Result
    tab_score: "Scorecard",
    tab_report: "Report",
    tab_sources: "Sources",
    tab_grounding: "Citation check",
    tab_retrieval: "Retrieval diagnostics",
    retrieval_lede: "Source collection stopped before the six-agent assessment. The details below show how the topic was interpreted and, when retrieval began, what each query returned.",
    retrieval_input: "Submitted topic",
    retrieval_search: "Academic search topic",
    retrieval_aliases: "Equivalent search phrases",
    retrieval_count: "Validated academic sources: {accepted} of {required} required",
    retrieval_audit: "Query audit",
    retrieval_query_summary: "{domain} · {results} candidates · {accepted} accepted",
    retrieval_rejections: "Rejected candidates",
    retrieval_no_audit: "No query audit was available; topic planning stopped before retrieval.",
    // Says what was actually checked. The old wording claimed "the numbers in
    // this report", which named the wrong document: the screen reads the three
    // evidence agents' structured findings, and the report is written from
    // those afterwards. A reader who took the old sentence at face value would
    // have credited the final text with a check it never received.
    grounding_lede: "Which figures in the evidence agents' findings were checked against the text of the sources they cite. This screens the findings the report is written from, not the finished report.",
    grounding_checked: "checked",
    grounding_ungrounded: "figure not in the cited source",
    grounding_unverifiable: "could not be checked",
    grounding_checkable: "checkable",
    grounding_no_figures: "no numeric claims",
    grounding_missing: "not found in the cited sources: {figures}",
    grounding_detail: "Claims needing a look",
    grounding_duplicates: "{count} repeated claim occurrences were collapsed; the counts above represent distinct claim/source pairs.",

    // Report-versus-scorecard
    tab_consistency: "Report vs score",
    consistency_lede: "Whether the report's own advice agrees with the scorecard beside it. Nothing else in the pipeline compares the two: the reviewer never sees the scorecard, and the scorer never sees the reviewed report.",
    consistency_clear: "The recommendation matches the score.",
    consistency_excerpt: "In the report",

    // Reliability panel — what the automated checks found, above the score
    // rather than inside a JSON file. A reader meets the flags before the
    // number they qualify.
    rel_title: "Automated checks",
    rel_verdict_risk: "A check disagrees with this report",
    rel_verdict_review: "Worth reading with the notes below in mind",
    rel_verdict_clear: "Nothing was flagged",
    rel_verdict_unknown: "Too little could be checked to say",
    // The distinction the panel exists to preserve. "Nothing flagged" is not
    // "verified" — the checks are heuristics over what could be retrieved, and
    // presenting silence as a pass is the failure mode this whole panel is
    // meant to avoid rather than commit.
    rel_verdict_clear_sub: "These are automated checks over the sources that were retrieved, not verification. They can only report what they can see.",
    rel_consistency: "Report vs score",
    rel_consistency_conflict: "The report's advice is stronger than its own score supports ({count})",
    rel_consistency_ok: "The recommendation matches the score",
    rel_consistency_unchecked: "Not run — this check reads English conclusions only",
    rel_grounding: "Citation check",
    rel_grounding_flagged: "{count} figures were not found in the source cited for them",
    rel_grounding_ok: "{count} figures matched the sources cited for them",
    rel_grounding_none: "No figure could be checked — the retrieved source text is too short",
    rel_sources: "Source coverage",
    rel_sources_failed: "Assessed without {domains} — retrieval for it failed",
    rel_sources_ok: "All three evidence domains returned sources",
    rel_authority: "Clinical authority coverage",
    rel_authority_missing: "No accepted {categories} source; this does not prove that no record exists",
    rel_authority_complete: "All authority source categories required for this topic were accepted",
    rel_authority_unchecked: "Not recorded for this run - this is not a pass",
    authority_regulatory: "regulator",
    authority_clinical_registry: "clinical-trial registry",
    rel_trail: "Audit trail",
    rel_trail_incomplete: "The per-agent evidence files could not be written; the report is unaffected",

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
    // Says "your keys", not "nothing". The old sentence was written about the
    // credentials and was true of them, but a visitor about to upload an
    // unpublished paper reads it as a statement about everything they are
    // handing over — and the assessment, along with the uploaded PDF, stays on
    // this server for the retention window. The second line below carries that
    // half, with the actual number.
    byok_sub: "Your keys go to this run's worker process and nowhere else, and are gone from this browser once you close the tab.",
    byok_retention: "The assessment itself is stored on this server for {days} days, then deleted automatically.",
    byok_retention_forever: "The assessment itself is stored on this server until it is deleted.",
    byok_llm_placeholder: "LLM API key",
    byok_serper_placeholder: "Serper API key",
    byok_hint: "Keys: platform.deepseek.com/api-keys · platform.openai.com/api-keys · console.anthropic.com — and serper.dev/api-key for search (free tier available).",
    byok_submit: "Start",
    byok_have_code: "I have an access code",
    byok_badge: "Using your own API keys",
    byok_exit: "Exit",
    byok_no_history: "No runs yet this session. Runs you start will stay listed here until you close this tab.",
    byok_no_attach: "Paper upload needs an access code",
    code_badge: "Signed in with an access code",
    code_exit: "Log out",
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
    retention_note: "本部署的运行记录会在 {days} 天后自动删除。",
    retention_forever: "本部署的运行记录会一直保留，直到手动删除。",
    tokens_suffix: "tokens",
    price_basis: "计价依据",
    cost_partial: "部分估算 —— 以下模型无已知价格：{models}",

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
    delete_run: "删除",
    confirm_delete_run: "确定要永久删除这条记录吗？报告和其他所有产出文件都会一并清除，无法恢复。",
    confirm_broad_topic: "这个主题可能过于宽泛，难以稳定检索学术、专利和市场证据。建议补充具体技术与应用场景，以获得更可靠的报告。\n\n仍要继续运行吗？",
    msg_deleted: "记录已删除。",
    download_report: "报告",
    sources_suffix: "条来源",
    academic: "学术",
    patent: "专利",
    market: "市场",

    tab_score: "评分卡",
    tab_report: "报告",
    tab_sources: "来源",
    tab_grounding: "引用核查",
    tab_retrieval: "检索诊断",
    retrieval_lede: "本次运行在六智能体评估开始前停止。以下信息展示系统如何理解主题，以及检索已经开始时每条查询返回了什么。",
    retrieval_input: "用户提交的主题",
    retrieval_search: "学术检索主题",
    retrieval_aliases: "等价检索短语",
    retrieval_count: "已验证学术来源：{accepted} 条，最低需要 {required} 条",
    retrieval_audit: "查询审计",
    retrieval_query_summary: "{domain} · {results} 个候选 · {accepted} 个通过",
    retrieval_rejections: "候选未通过的原因",
    retrieval_no_audit: "没有可用的查询审计；本次运行在主题规划阶段停止。",
    grounding_lede: "三个证据智能体的结论中，有哪些数字已对照其引用来源的正文核对过。核的是报告所依据的结论，不是成文的报告本身。",
    grounding_checked: "已核对",
    grounding_ungrounded: "来源正文中没有该数字",
    grounding_unverifiable: "无法核对",
    grounding_checkable: "可核对",
    grounding_no_figures: "无量化结论",
    grounding_missing: "在被引来源中未找到：{figures}",
    grounding_detail: "需要留意的结论",
    grounding_duplicates: "已合并 {count} 个完全重复的结论；以上数量按不同的“结论＋来源”组合计算。",

    tab_consistency: "报告与评分",
    consistency_lede: "报告自己给出的建议，与旁边的评分卡是否一致。流水线里没有别的环节比较过这两者：审查员看不到评分卡，评分器看不到审查后的报告。",
    consistency_clear: "建议强度与评分一致。",
    consistency_excerpt: "报告原文",

    rel_title: "自动检查",
    rel_verdict_risk: "有一项检查与本报告不一致",
    rel_verdict_review: "阅读时请一并参考下列说明",
    rel_verdict_clear: "未发现问题",
    rel_verdict_unknown: "可核对的内容太少，无法判断",
    rel_verdict_clear_sub: "这些是针对已检索到的来源做的自动检查，不等于核实。它们只能报告自己看得见的部分。",
    rel_consistency: "报告与评分",
    rel_consistency_conflict: "报告的建议强度超出了自身评分所能支持的范围（{count} 处）",
    rel_consistency_ok: "建议强度与评分一致",
    rel_consistency_unchecked: "未运行——此项检查只识别英文结论",
    rel_grounding: "引用核查",
    rel_grounding_flagged: "有 {count} 个数字未能在其引用的来源中找到",
    rel_grounding_ok: "{count} 个数字与其引用的来源一致",
    rel_grounding_none: "没有数字可核对——检索到的来源正文过短",
    rel_sources: "来源覆盖",
    rel_sources_failed: "本次评估未包含 {domains}——该域检索失败",
    rel_sources_ok: "三个证据域均返回了来源",
    rel_authority: "\u4e34\u5e8a\u6743\u5a01\u6765\u6e90\u8986\u76d6",
    rel_authority_missing: "\u7f3a\u5c11\u5df2\u63a5\u53d7\u7684 {categories} \u6765\u6e90\uff1b\u8fd9\u4e0d\u4ee3\u8868\u76f8\u5173\u8bb0\u5f55\u4e0d\u5b58\u5728",
    rel_authority_complete: "\u5df2\u63a5\u53d7\u672c\u4e3b\u9898\u8981\u6c42\u7684\u5168\u90e8\u4e34\u5e8a\u6743\u5a01\u6765\u6e90\u7c7b\u522b",
    rel_authority_unchecked: "\u672c\u6b21\u8fd0\u884c\u672a\u8bb0\u5f55\u6b64\u68c0\u67e5\uff0c\u4e0d\u80fd\u89c6\u4e3a\u5df2\u901a\u8fc7",
    authority_regulatory: "\u76d1\u7ba1\u673a\u6784",
    authority_clinical_registry: "\u4e34\u5e8a\u8bd5\u9a8c\u6ce8\u518c",
    rel_trail: "审计记录",
    rel_trail_incomplete: "各智能体的证据文件未能写入；报告本身不受影响",
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
    byok_sub: "密钥只会传给这次运行的工作进程，关闭标签页后就从浏览器中消失。",
    byok_retention: "评估结果本身会保存在本服务器上 {days} 天，之后自动删除。",
    byok_retention_forever: "评估结果本身会保存在本服务器上，直到被删除。",
    byok_llm_placeholder: "LLM API Key",
    byok_serper_placeholder: "Serper API Key",
    byok_hint: "获取密钥：platform.deepseek.com/api-keys · platform.openai.com/api-keys · console.anthropic.com；检索用的 serper.dev/api-key 有免费额度。",
    byok_submit: "开始",
    byok_have_code: "我有访问口令",
    byok_badge: "正在使用自己的 API Key",
    byok_exit: "退出",
    byok_no_history: "本次会话还没有运行记录。你提交的运行会一直显示在这里，直到关闭这个标签页。",
    byok_no_attach: "上传论文需要访问口令",
    code_badge: "已通过访问口令登录",
    code_exit: "退出登录",
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
