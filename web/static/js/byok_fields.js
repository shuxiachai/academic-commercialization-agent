/* Labels and placeholders for the BYOK model and search-service fields.
 *
 * These strings were kept out of i18n.js while a frozen experiment hash-locked
 * it; since 2026-10-22 that experiment reads a snapshot (evals/
 * source_locator_observer_v1), so i18n.js may take new keys. The language
 * still comes from i18n.js. Loaded after app.js as its own module,
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
  anthropic: "claude-sonnet-5-5",
};

// Offered in the field's suggestion list; none is pre-filled. The Qwen pair
// is what this project's runs and evaluations used; the others are the
// providers' current general models, not measured here.
export const MODEL_SUGGESTIONS = {
  deepseek: ["deepseek-chat"],
  qwen: ["qwen3.8-27b", "qwen3.8-max"],
  openai: ["gpt-4o"],
  anthropic: ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"],
};

/* What this project has measured, model by model: runs on held-out topics
 * whose expected readiness range was fixed before any run, and how many
 * landed in it. Until 2026-11-12 the form asked a new account for a model
 * name and offered an example and two typed suggestions, with nothing saying
 * which had been through this pipeline or how it did; the figures existed
 * only in docs/.
 *
 * Each row is the headline of a result document and nothing else:
 * tests/test_byok_fields_web.py reads the figure, the model and the date back
 * out of the document, so a row cannot be added from memory. Listed by share
 * of runs in range, then by more runs. Every measured model so far was run
 * through Model Studio, which is the `qwen` provider here whatever the
 * model's maker. A figure is what one cohort did, not a ranking: the cohorts
 * differ in topics, date and retrieval. */
export const MODEL_MEASURED = {
  qwen: [
    { model: "qwen3.8-max", inRange: 25, runs: 30, date: "2026-10-19" },
    { model: "deepseek-v4-pro", inRange: 8, runs: 10, date: "2026-11-08" },
    { model: "deepseek-v4.1-flash-1017", inRange: 4, runs: 5, date: "2026-11-11" },
    { model: "qwen3.7-plus", inRange: 21, runs: 30, date: "2026-10-18" },
  ],
};

// How the note names a provider. The select's own labels are longer.
const PROVIDER_NAMES = { deepseek: "DeepSeek", qwen: "Model Studio", openai: "OpenAI", anthropic: "Anthropic" };

const STRINGS = {
  English: {
    byok_hint: "Keys: platform.deepseek.com/api-keys · bailian.console.aliyun.com (China Qwen) · platform.openai.com/api-keys · console.anthropic.com — plus app.tavily.com (recommended) or serper.dev for search. The model you name must support JSON output.",
    model_placeholder: "Model (required), e.g. {example}",
    model_measured: "Tested here on held-out topics: runs that landed in the expected readiness range, out of those made. Choose one to fill it in. Any other model is untested here, not unsupported.",
    model_unmeasured: "No held-out run here has gone through {provider}. These are starting points; any model that returns JSON can be tried.",
    model_chip_measured: "Use {model}: {in} of {runs} held-out runs in range, {date}",
    model_chip_plain: "Use {model}",
    search_key_tavily: "Tavily API key",
    search_key_serper: "Serper API key",
  },
  "Simplified Chinese": {
    byok_hint: "获取密钥：platform.deepseek.com/api-keys · bailian.console.aliyun.com（中国区 Qwen）· platform.openai.com/api-keys · console.anthropic.com；检索推荐使用 app.tavily.com，也可使用 serper.dev。所填模型需支持 JSON 输出。",
    model_placeholder: "模型（必填），例如 {example}",
    model_measured: "本项目在留出主题上实测过的模型：落在预期成熟度区间的次数／运行次数。点一个即可填入。其他模型只是没有在这里测过，并非不支持。",
    model_unmeasured: "本项目的留出运行没有经过 {provider}。以下只是起点；任何能返回 JSON 的模型都可以试。",
    model_chip_measured: "填入 {model}：{runs} 次留出运行中 {in} 次落在区间内，{date}",
    model_chip_plain: "填入 {model}",
    search_key_tavily: "Tavily API Key",
    search_key_serper: "Serper API Key",
  },
};

const t = (key) => STRINGS[language()]?.[key] ?? STRINGS.English[key] ?? key;
const $ = (sel) => document.querySelector(sel);

const fill = (text, values) => text.replace(/\{(\w+)\}/g, (whole, key) => values[key] ?? whole);

/** The models to offer for a provider: the measured ones as measured, then
 * the plain suggestions not already among them. */
function modelsFor(provider) {
  const measured = MODEL_MEASURED[provider] ?? [];
  const seen = new Set(measured.map((row) => row.model));
  return [...measured, ...(MODEL_SUGGESTIONS[provider] ?? []).filter((name) => !seen.has(name)).map((model) => ({ model }))];
}

/** Mark the chip whose model is in the field, typed or chosen. */
function markChosen() {
  const chosen = $("#byok-model")?.value.trim();
  for (const chip of $("#byok-model-chips")?.children ?? []) {
    chip.setAttribute("aria-pressed", String(chip.dataset.model === chosen));
  }
}

/** One button per model worth showing as a button: every measured model of
 * the provider, or its plain suggestions where nothing was measured. A press
 * puts the name in the field, as typing it would; the field is never filled
 * without one, because there is no default model. The typed-suggestion list
 * stays, but a phone shows it poorly or not at all, and it cannot carry a
 * figure. */
function paintModelGuide(provider) {
  const note = $("#byok-model-note");
  const chips = $("#byok-model-chips");
  if (!note || !chips) return;
  const measured = MODEL_MEASURED[provider] ?? [];
  note.textContent = measured.length
    ? t("model_measured")
    : fill(t("model_unmeasured"), { provider: PROVIDER_NAMES[provider] ?? provider });
  const rows = measured.length ? measured : modelsFor(provider);
  chips.replaceChildren(...rows.map((row) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip-btn model-chip";
    chip.dataset.model = row.model;
    const name = document.createElement("span");
    name.className = "model-chip__name";
    name.textContent = row.model;
    chip.append(name);
    if (row.runs) {
      const figure = document.createElement("span");
      figure.className = "model-chip__figure";
      figure.textContent = `${row.inRange}/${row.runs}`;
      chip.append(figure);
    }
    chip.setAttribute("aria-label", fill(t(row.runs ? "model_chip_measured" : "model_chip_plain"),
      { model: row.model, in: row.inRange, runs: row.runs, date: row.date }));
    chip.addEventListener("click", () => {
      const field = $("#byok-model");
      if (!field) return;
      field.value = row.model;
      // Whatever listens for typing hears a choice the same way.
      field.dispatchEvent(new Event("input", { bubbles: true }));
      field.focus();
    });
    return chip;
  }));
  markChosen();
}

export function applyByokFields(root = document) {
  for (const node of root.querySelectorAll("[data-byok-i18n]")) {
    node.textContent = t(node.dataset.byokI18n);
  }
  const provider = $("#byok-provider")?.value;
  const model = $("#byok-model");
  if (model) model.placeholder = t("model_placeholder").replace("{example}", MODEL_EXAMPLES[provider] ?? "");
  const options = $("#byok-model-options");
  if (options) {
    options.replaceChildren(...modelsFor(provider).map((row) => {
      const option = document.createElement("option");
      option.value = row.model;
      return option;
    }));
  }
  paintModelGuide(provider);
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
$("#byok-model")?.addEventListener("input", markChosen);
// A model this page offers for another provider is wrong for the one just
// selected: the buttons make it one press to enter, so a change of provider
// takes it back out rather than let it ride into a key check or a paid run.
// A name the page does not know is the visitor's own and is left alone.
// Registered after the repaint above, so the chips are marked once more here.
$("#byok-provider")?.addEventListener("change", () => {
  const field = $("#byok-model");
  const chosen = field?.value.trim();
  if (!chosen) return;
  const offers = (provider) => modelsFor(provider).some((row) => row.model === chosen);
  const known = Object.keys(MODEL_SUGGESTIONS).some(offers);
  if (!known || offers($("#byok-provider").value)) return;
  field.value = "";
  markChosen();
});
