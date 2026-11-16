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
// The rule that reads a model's kind from its name. In a module of its own
// since the run page reads it too (a run that failed on such a model).
import { MODEL_KINDS, modelKind } from "./model_kind.js";

export { MODEL_KINDS, modelKind };

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
    // The words between the links to where keys come from (index.html, #byok-links).
    byok_keys_model: "Model keys:",
    byok_keys_qwen: "(China Qwen)",
    byok_keys_search: "Search keys:",
    byok_keys_recommended: "(recommended)",
    // The stop after each of the two lists: in the markup it was an ASCII one in every language.
    byok_keys_stop: ".",
    byok_keys_json: "The model you name must support JSON output.",
    model_placeholder: "Model (required), e.g. {example}",
    model_measured: "Checked by this project on topics set aside for testing: runs that landed in the expected readiness range, out of those made. Choose one to fill it in. Any other model is untested here, not unsupported.",
    model_unmeasured: "No quality check by this project has gone through {provider} yet. The models below are places to start; any other model name can be entered too.",
    model_chip_measured: "Use {model}: {in} of {runs} test runs in range, {date}",
    model_chip_plain: "Use {model}",
    // Under a model field whose name says it is another kind of model.
    model_kind_note: "“{model}” looks like {kind}. An assessment needs a general chat model that can write long text; this one will most likely fail after using tokens. It can still be saved.",
    model_kind_ocr: "an OCR (text recognition) model",
    model_kind_embedding: "an embedding model",
    model_kind_rerank: "a reranking model",
    model_kind_speech: "a speech or audio model",
    model_kind_image: "an image model",
    model_kind_video: "a video model",
    model_kind_translation: "a translation model",
    model_kind_moderation: "a moderation model",
    search_key_tavily: "Tavily API key",
    search_key_serper: "Serper API key",
  },
  "Simplified Chinese": {
    byok_keys_model: "模型密钥：",
    byok_keys_qwen: "（中国区 Qwen）",
    byok_keys_search: "检索密钥：",
    byok_keys_recommended: "（推荐）",
    byok_keys_stop: "。",
    byok_keys_json: "所填模型需支持 JSON 输出。",
    model_placeholder: "模型（必填），例如 {example}",
    model_measured: "本项目用专门留作测试的主题抽检过的模型：落在预期成熟度区间的次数／运行次数。点一个即可填入。其他模型只是没有在这里测过，并非不支持。",
    model_unmeasured: "本项目还没有经 {provider} 做过质量抽检。下面是可以先试的型号，也可以填写其他型号。",
    model_chip_measured: "填入 {model}：{runs} 次测试运行中 {in} 次落在区间内，{date}",
    model_chip_plain: "填入 {model}",
    model_kind_note: "“{model}”看起来是{kind}。评估需要能写长文本的通用对话模型，这个模型很可能在消耗 token 之后失败。仍然可以保存。",
    model_kind_ocr: "文字识别（OCR）模型",
    model_kind_embedding: "向量（embedding）模型",
    model_kind_rerank: "重排序模型",
    model_kind_speech: "语音模型",
    model_kind_image: "图像模型",
    model_kind_video: "视频模型",
    model_kind_translation: "翻译专用模型",
    model_kind_moderation: "内容审核模型",
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

/** Say under a model field what kind of model its name says it is, or nothing. */
function paintKind(field, note) {
  if (!field || !note) return;
  const name = field.value.trim();
  const kind = modelKind(name);
  note.hidden = !kind;
  note.textContent = kind ? fill(t("model_kind_note"), { model: name, kind: t(`model_kind_${kind}`) }) : "";
}

const paintKinds = () => {
  paintKind($("#byok-model"), $("#byok-model-kind"));
  paintKind($("#byok-saved-model"), $("#byok-saved-model-kind"));
};

/** The typed suggestions for the saved keys' model: the saved provider's, which app.js notes on the field. */
function paintSavedModelOptions() {
  const options = $("#byok-saved-model-options");
  const provider = $("#byok-saved-model")?.dataset?.provider;
  if (!options) return;
  options.replaceChildren(...modelsFor(provider).map((row) => {
    const option = document.createElement("option");
    option.value = row.model;
    return option;
  }));
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
  paintKinds();
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
$("#byok-model")?.addEventListener("input", paintKinds);
// The model of the saved keys: app.js fills the field with what is saved and
// announces it as typing, so the same listener speaks about a saved name.
$("#byok-saved-model")?.addEventListener("input", () => { paintKinds(); paintSavedModelOptions(); });
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
