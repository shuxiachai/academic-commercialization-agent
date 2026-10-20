/* Labels and placeholders for the BYOK model and search-service fields.
 *
 * Kept out of i18n.js on purpose: that file's bytes are hash-locked by a frozen
 * experiment, so new strings live here, as the sample-report strings do. The
 * language still comes from i18n.js. Loaded after app.js as its own module,
 * because app.js's browser contracts strip and inject its imports.
 *
 * The model field is required: there is no default model, so a visitor's key
 * is only billed for a model they named. The placeholder shows an example
 * name for the selected provider; it is a hint, never submitted. */

import { language } from "./i18n.js";

export const MODEL_EXAMPLES = {
  deepseek: "deepseek-chat",
  qwen: "qwen3.8-27b",
  openai: "gpt-4o",
  anthropic: "claude-sonnet-5",
};

const STRINGS = {
  English: {
    byok_hint: "Keys: platform.deepseek.com/api-keys · bailian.console.aliyun.com (China Qwen) · platform.openai.com/api-keys · console.anthropic.com — plus app.tavily.com (recommended) or serper.dev for search. The model you name must support JSON output.",
    model_placeholder: "Model (required), e.g. {example}",
    search_key_tavily: "Tavily API key",
    search_key_serper: "Serper API key",
  },
  "Simplified Chinese": {
    byok_hint: "获取密钥：platform.deepseek.com/api-keys · bailian.console.aliyun.com（中国区 Qwen）· platform.openai.com/api-keys · console.anthropic.com；检索推荐使用 app.tavily.com，也可使用 serper.dev。所填模型需支持 JSON 输出。",
    model_placeholder: "模型（必填），例如 {example}",
    search_key_tavily: "Tavily API Key",
    search_key_serper: "Serper API Key",
  },
};

const t = (key) => STRINGS[language()]?.[key] ?? STRINGS.English[key] ?? key;
const $ = (sel) => document.querySelector(sel);

export function applyByokFields(root = document) {
  for (const node of root.querySelectorAll("[data-byok-i18n]")) {
    node.textContent = t(node.dataset.byokI18n);
  }
  const provider = $("#byok-provider")?.value;
  const model = $("#byok-model");
  if (model) model.placeholder = t("model_placeholder").replace("{example}", MODEL_EXAMPLES[provider] ?? "");
  const search = $("#byok-search")?.value;
  const key = $("#byok-search-key");
  if (key) key.placeholder = t(search === "serper" ? "search_key_serper" : "search_key_tavily");
}

applyByokFields();
for (const id of ["#byok-provider", "#byok-search", "#ui-lang"]) {
  $(id)?.addEventListener("change", () => applyByokFields());
}
// The gate resets the form each time it opens, and reset fires no change
// event; repaint after the reset has restored the default selections.
$("#byok-form")?.addEventListener("reset", () => setTimeout(applyByokFields));
