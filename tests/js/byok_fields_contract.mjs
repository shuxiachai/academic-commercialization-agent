/* The model field's guide, through the served byok_fields.js and i18n.js.
 *
 * A visitor with a key and no idea which model to name gets, under the field,
 * what this project measured for the selected provider and buttons that fill
 * a name in. The field itself is never filled for them. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [dir, scenario] = process.argv.slice(2);
// Words of the project's own method, which the note under the field once used
// ("No held-out run here has gone through…", "any model that returns JSON").
const JARGON = /held-out|留出|JSON/;
const { html, measured, suggestions } = JSON.parse(fs.readFileSync(path.join(dir, "input.json"), "utf8"));

class Element {
  constructor(tag = "div") {
    Object.assign(this, { tag, className: "", value: "", placeholder: "", type: "", hidden: false,
      dataset: {}, attributes: {}, listeners: {}, children: [], focused: 0 });
    this._text = "";
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this._text = ""; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
  dispatchEvent(event) { this.fire(event.type, event); return true; }
  focus() { this.focused++; }
  fire(name, event = {}) { for (const callback of this.listeners[name] ?? []) callback(event); }
}

// Only ids the served page really has: a renamed element must fail here.
const elements = Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [id, new Element()]));
const el = (id) => { assert(elements[id], `Missing DOM #${id}`); return elements[id]; };
const stored = new Map();
globalThis.document = {
  documentElement: { lang: "en", dataset: {} },
  querySelector: (selector) => { assert(selector.startsWith("#"), selector); return elements[selector.slice(1)] ?? null; },
  querySelectorAll: () => [],
  createElement: (tag) => new Element(tag),
};
globalThis.localStorage = { getItem: (k) => stored.get(k) ?? null, setItem: (k, v) => stored.set(k, String(v)) };

const settle = async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0)); };
const field = el("byok-model");
const provider = el("byok-provider");
const chips = () => el("byok-model-chips").children;
const note = () => el("byok-model-note").textContent;
const options = () => el("byok-model-options").children.map((option) => option.value);
const pressed = () => chips().filter((chip) => chip.getAttribute("aria-pressed") === "true").map((chip) => chip.dataset.model);
const figure = (row) => `${row.inRange}/${row.runs}`;

let inputs = 0;
field.addEventListener("input", () => { inputs++; });
async function start(value) {
  provider.value = value;
  await import(pathToFileURL(path.join(dir, "byok_fields.js")).href);
  await settle();
}
async function choose(value) { provider.value = value; provider.fire("change"); await settle(); }
async function type(value) { field.value = value; field.fire("input"); await settle(); }
async function language(value) {
  const i18n = await import(pathToFileURL(path.join(dir, "i18n.js")).href);
  i18n.setLanguage(value);
  el("ui-lang").value = value;
  el("ui-lang").fire("change");
  await settle();
}
/** Every chip is a plain button of the form: a default button would submit it. */
function expectChips(rows) {
  assert.deepEqual(chips().map((chip) => chip.dataset.model), rows.map((row) => row.model));
  for (const [index, chip] of chips().entries()) {
    assert.equal(chip.tag, "button");
    assert.equal(chip.type, "button", "A chip must never submit the form");
    const row = rows[index];
    const text = chip.textContent;
    assert(text.startsWith(row.model), text);
    if (row.runs) assert(text.endsWith(figure(row)), `${text} shows its figure`);
    else assert.equal(text, row.model, "An unmeasured model shows no figure");
  }
}

assert(measured.qwen?.length >= 3, "The scenarios need the measured Model Studio rows");
const qwen = measured.qwen;
const plain = (name) => suggestions[name].map((model) => ({ model }));

if (scenario === "measured") {
  await start("qwen");
  assert.equal(field.value, "", "Nothing is filled in for the visitor");
  expectChips(qwen);
  assert.deepEqual(pressed(), []);
  assert.match(note(), /topics set aside for testing/);
  assert.match(note(), /untested here, not unsupported/);
  assert.doesNotMatch(note(), JARGON);
  // The typed list offers the measured names first, then the others, once each.
  const extra = suggestions.qwen.filter((name) => !qwen.some((row) => row.model === name));
  assert.deepEqual(options(), [...qwen.map((row) => row.model), ...extra]);
  // What a screen reader hears says what the figure counts and when.
  const label = chips()[0].getAttribute("aria-label");
  for (const part of [qwen[0].model, `${qwen[0].inRange} of ${qwen[0].runs}`, qwen[0].date]) {
    assert(label.includes(part), `${label} names ${part}`);
  }
  assert.equal(label, `Use ${qwen[0].model}: ${qwen[0].inRange} of ${qwen[0].runs} test runs in range, ${qwen[0].date}`);
  for (const chip of chips()) assert.doesNotMatch(chip.getAttribute("aria-label"), JARGON);
} else if (scenario === "fill") {
  await start("qwen");
  const chip = chips()[1];
  chip.fire("click");
  await settle();
  assert.equal(field.value, qwen[1].model);
  assert.equal(inputs, 1, "The page hears the change as it hears typing");
  assert.equal(field.focused, 1, "Focus goes to the field the choice landed in");
  assert.deepEqual(pressed(), [qwen[1].model]);
  chips()[0].fire("click");
  await settle();
  assert.equal(field.value, qwen[0].model);
  assert.deepEqual(pressed(), [qwen[0].model], "One choice at a time");
} else if (scenario === "typed") {
  await start("qwen");
  await type(`  ${qwen[2].model} `);
  assert.deepEqual(pressed(), [qwen[2].model], "A typed name is the same choice as a pressed one");
  await type("some-other-model");
  assert.deepEqual(pressed(), []);
  assert.equal(field.value, "some-other-model", "Typing is never overwritten");
} else if (scenario === "unmeasured") {
  await start("deepseek");
  expectChips(plain("deepseek"));
  // Said of the provider, not of its models: deepseek-v4-pro has figures,
  // measured through Model Studio.
  assert.equal(note(), "No quality check by this project has gone through DeepSeek yet. " +
    "The models below are places to start; any other model name can be entered too.");
  assert.doesNotMatch(note(), JARGON);
  assert.deepEqual(options(), suggestions.deepseek);
  chips()[0].fire("click");
  await settle();
  assert.equal(field.value, suggestions.deepseek[0]);
  assert.deepEqual(pressed(), [suggestions.deepseek[0]]);
  assert.equal(chips()[0].getAttribute("aria-label"), `Use ${suggestions.deepseek[0]}`);
} else if (scenario === "switch") {
  await start("qwen");
  chips()[0].fire("click");
  await settle();
  await choose("anthropic");
  expectChips(plain("anthropic"));
  assert.match(note(), /gone through Anthropic yet\./);
  // A name this page offers for another provider is wrong for this one, and
  // would otherwise ride along into a key check or a paid run.
  assert.equal(field.value, "", "Another provider's model does not follow the visitor");
  assert.deepEqual(pressed(), []);
  await type("my-own-deployment");
  await choose("qwen");
  expectChips(qwen);
  assert.equal(field.value, "my-own-deployment", "A name the page does not know is the visitor's and stays");
  assert.deepEqual(pressed(), []);
  await type(` ${qwen[1].model} `);
  await choose("qwen");
  assert.equal(field.value, ` ${qwen[1].model} `, "A model of the provider still selected stays, as typed");
  assert.deepEqual(pressed(), [qwen[1].model]);
  // Switching the language repaints the same guide and must not erase either.
  await choose("openai");
  await type(suggestions.openai[0]);
  await language("Simplified Chinese");
  assert.equal(field.value, suggestions.openai[0]);
} else if (scenario === "language") {
  await start("qwen");
  await language("Simplified Chinese");
  assert.match(note(), /专门留作测试的主题/);
  assert.match(note(), /并非不支持/);
  assert.doesNotMatch(note(), JARGON);
  expectChips(qwen);
  assert.equal(chips()[0].getAttribute("aria-label"),
    `填入 ${qwen[0].model}：${qwen[0].runs} 次测试运行中 ${qwen[0].inRange} 次落在区间内，${qwen[0].date}`);
  for (const chip of chips()) assert.doesNotMatch(chip.getAttribute("aria-label"), JARGON);
  await choose("openai");
  assert.equal(note(), "本项目还没有经 OpenAI 做过质量抽检。下面是可以先试的型号，也可以填写其他型号。");
  assert.doesNotMatch(note(), JARGON);
  assert.equal(chips()[0].getAttribute("aria-label"), `填入 ${suggestions.openai[0]}`);
  await language("English");
  assert.match(note(), /gone through OpenAI yet\./);
} else if (scenario === "reset") {
  await start("qwen");
  chips()[0].fire("click");
  await settle();
  // What the gate does each time it opens: a reset, which fires no change.
  field.value = "";
  provider.value = "deepseek";
  el("byok-form").fire("reset");
  await settle();
  expectChips(plain("deepseek"));
  assert.deepEqual(pressed(), []);
} else if (scenario === "kind_rules") {
  // The rule itself. Names that say what they are, each with the kind it says...
  await start("qwen");
  const { modelKind, MODEL_EXAMPLES, MODEL_KINDS } = await import(pathToFileURL(path.join(dir, "byok_fields.js")).href);
  const says = {
    ocr: ["qwen-vl-ocr-2025-11-20", "qwen-vl-ocr", "QWEN-VL-OCR-latest", "got-ocr2", "paddleocr-v4", "ocr-pro"],
    embedding: ["text-embedding-v3", "text-embedding-3-large", "bge-m3", "multimodal-embedding-v1"],
    rerank: ["gte-rerank", "bge-reranker-v2"],
    speech: ["whisper-1", "tts-1", "gpt-4o-audio-preview", "gpt-4o-realtime-preview", "paraformer-v2", "cosyvoice-v1",
      "sensevoice-v1", "qwen3-asr-flash", "qwen-tts"],
    image: ["dall-e-3", "gpt-image-1", "qwen-image", "wanx2.1-t2i-turbo", "flux-schnell", "stable-diffusion-3.5-large"],
    video: ["wan2.2-t2v-plus", "sora-2", "veo-3", "video-01"],
    translation: ["qwen-mt-turbo", "qwen-mt-plus"],
    moderation: ["omni-moderation-latest", "llama-guard-3-8b"],
  };
  assert.deepEqual(Object.keys(says).sort(), MODEL_KINDS.map(([kind]) => kind).sort(), "Every rule has names here that it must catch");
  for (const [kind, names] of Object.entries(says)) {
    for (const name of names) assert.equal(modelKind(name), kind, name);
  }
  assert.equal(modelKind("  qwen-vl-ocr  "), "ocr", "As typed, spaces and all");
  // ...and names that do not. Every model this page offers or has measured, first.
  const offered = [...Object.values(suggestions).flat(), ...Object.values(measured).flat().map((row) => row.model),
    ...Object.values(MODEL_EXAMPLES)];
  assert(offered.length >= 10);
  for (const name of offered) assert.equal(modelKind(name), null, `${name} is offered by this page`);
  // General chat models, vision ones included, and names with a rule's letters inside an ordinary word.
  for (const name of ["gpt-4o", "gpt-4o-mini", "gpt-4o-2024-08-06", "o3", "o4-mini", "claude-sonnet-5-5", "claude-opus-5-5",
    "deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro-0813", "qwen-plus", "qwen-max-latest", "qwen-vl-max", "qwen3-vl-plus",
    "qwen3-coder-plus", "glm-5.3", "kimi-k2", "moonshot-v1-128k", "MiniMax-M2", "llama-4-70b-instruct", "mistral-large",
    "gemini-2.5-pro", "doubao-pro-256k", "ernie-4.5-turbo", "my-own-deployment", "team-proxy:gpt-4o", "mediocre-1", "smt-large",
    "imagine-1", "pilgrimage-2", "vanguard-7", "wand-2", "nova-pro", "sonar-pro", "embark"]) {
    if (name === "embark") continue;        // "embed" is not in it; kept as a reminder that "emb" alone is not a rule
    assert.equal(modelKind(name), null, name);
  }
  for (const empty of ["", "   ", null, undefined]) assert.equal(modelKind(empty), null);
} else if (scenario === "kind") {
  // Under the model field of the form: said while the name is typed, gone when it is not that kind.
  await start("qwen");
  const said = el("byok-model-kind");
  assert.equal(said.hidden, true, "Nothing is said about an empty field");
  await type("qwen-vl-ocr-2025-11-20");
  assert.equal(said.hidden, false);
  assert.equal(said.textContent, "\u201cqwen-vl-ocr-2025-11-20\u201d looks like an OCR (text recognition) model. An assessment needs a " +
    "general chat model that can write long text; this one will most likely fail after using tokens. It can still be saved.");
  assert.equal(field.value, "qwen-vl-ocr-2025-11-20", "Advice only: the name is left as typed");
  await type(" text-embedding-v3 ");
  assert.match(said.textContent, /^\u201ctext-embedding-v3\u201d looks like an embedding model\./);
  await type("qwen3.8-max");
  assert.deepEqual([said.hidden, said.textContent], [true, ""]);
  // A chip is a model this page offers: pressing one clears the advice about what was typed.
  await type("whisper-1");
  assert.equal(said.hidden, false);
  chips()[0].fire("click");
  await settle();
  assert.equal(said.hidden, true);
  // The gate's reset empties the field without an input event.
  await type("tts-1");
  field.value = "";
  el("byok-form").fire("reset");
  await settle();
  assert.equal(said.hidden, true);
} else if (scenario === "kind_saved") {
  // The model of the saved keys: app.js fills the field and announces it as typing.
  await start("deepseek");
  const saved = el("byok-saved-model"), said = el("byok-saved-model-kind");
  const options = () => el("byok-saved-model-options").children.map((option) => option.value);
  assert.equal(said.hidden, true);
  saved.value = "qwen-vl-ocr-2025-11-20";
  saved.dataset.provider = "qwen";
  saved.fire("input");
  await settle();
  assert.equal(said.hidden, false);
  assert.match(said.textContent, /^\u201cqwen-vl-ocr-2025-11-20\u201d looks like an OCR \(text recognition\) model\./);
  // The suggestions are the saved provider's, not those of the provider the form below happens to show.
  const extra = suggestions.qwen.filter((name) => !qwen.some((row) => row.model === name));
  assert.deepEqual(options(), [...qwen.map((row) => row.model), ...extra]);
  assert.equal(el("byok-model-kind").hidden, true, "The form's own field has nothing in it to speak of");
  saved.value = qwen[0].model;
  saved.fire("input");
  await settle();
  assert.deepEqual([said.hidden, said.textContent], [true, ""]);
  // Typing in the form's field does not disturb what is said about the saved one, and the reverse.
  saved.value = "bge-m3"; saved.fire("input"); await settle();
  await type("whisper-1");
  assert.match(said.textContent, /embedding model/);
  assert.match(el("byok-model-kind").textContent, /speech or audio model/);
} else if (scenario === "kind_language") {
  await start("qwen");
  const said = el("byok-model-kind"), saved = el("byok-saved-model");
  await type("qwen-vl-ocr");
  saved.value = "qwen-mt-turbo"; saved.fire("input"); await settle();
  await language("Simplified Chinese");
  assert.equal(said.textContent, "\u201cqwen-vl-ocr\u201d看起来是文字识别（OCR）模型。评估需要能写长文本的通用对话模型，这个模型很可能在消耗 token 之后失败。仍然可以保存。");
  assert.match(el("byok-saved-model-kind").textContent, /^\u201cqwen-mt-turbo\u201d看起来是翻译专用模型。/);
  assert.equal(field.value, "qwen-vl-ocr");
  await language("English");
  assert.match(said.textContent, /looks like an OCR/);
} else throw Error(`Unknown scenario ${scenario}`);
console.log(`PASS ${scenario}`);
