/* The tab title follows the open sample, through the served reader modules. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [dir, scenario] = process.argv.slice(2);
const { html, samples } = JSON.parse(fs.readFileSync(path.join(dir, "input.json"), "utf8"));
const defaultTitle = html.match(/<title>([^<]*)<\/title>/)[1];
assert(samples.length >= 2, "The scenarios need at least two committed samples");

class Element {
  constructor(tag = "div") {
    Object.assign(this, { tag, className: "", href: "", value: "", html: "", dataset: {},
      attributes: {}, listeners: {}, children: [] });
    this._text = "";
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  set innerHTML(value) { this.html = String(value); this.children = []; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this._text = ""; this.html = ""; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
  // The stub renderer emits no headings, so the contents list (#285) stays empty here.
  querySelectorAll() { return []; }
  fire(name, event = {}) {
    for (const callback of this.listeners[name] ?? []) callback({ preventDefault() {}, button: 0, ...event });
  }
}

// Only ids the served page really has: a renamed element must fail here.
const elements = Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [id, new Element()]));
const el = (id) => { assert(elements[id], `Missing DOM #${id}`); return elements[id]; };
const windowListeners = {};
const stored = new Map();
globalThis.document = {
  title: defaultTitle,
  documentElement: { lang: "en", dataset: {} },
  querySelector: (selector) => { assert(selector.startsWith("#"), selector); return el(selector.slice(1)); },
  querySelectorAll: () => [],
  createElement: (tag) => new Element(tag),
};
// A reload, as the list failure's retry asks for: recorded, not performed.
const reloads = [];
globalThis.location = { pathname: "/samples", reload: () => reloads.push(true) };
globalThis.history = { pushState(_state, _unused, url) { location.pathname = new URL(url, "https://samples.test").pathname; } };
globalThis.window = { addEventListener: (name, callback) => (windowListeners[name] ??= []).push(callback) };
globalThis.localStorage = { getItem: (k) => stored.get(k) ?? null, setItem: (k, v) => stored.set(k, String(v)) };

let list = samples, listStatus = 200, deferReads = false;
const pendingReads = [];
globalThis.fetch = async (url) => {
  // The reader asks the deployment's public facts for its link onward; a title follows the sample either way.
  if (url === "/api/site") return new Response('{"accounts":true,"signup_open":true}', { status: 200 });
  if (url === "/api/samples") {
    return new Response(JSON.stringify(list), { status: listStatus, headers: { "Content-Type": "application/json" } });
  }
  // The scorecard and the conclusion read beside a report: none here, so the titles are all this file sees.
  if (url.endsWith("/scores") || url.endsWith("/decision")) return new Response("{}", { status: 404 });
  const slug = decodeURIComponent(url.replace(/^\/api\/samples\//, ""));
  const reply = () => new Response(`# ${slug}`, { status: 200, headers: { "Content-Type": "text/markdown" } });
  if (!deferReads) return reply();
  return new Promise((resolve) => pendingReads.push({ slug, release: () => resolve(reply()) }));
};

const settle = async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0)); };
const start = async (pathname) => {
  location.pathname = pathname;
  await import(pathToFileURL(path.join(dir, "samples.js")).href);
  await settle();
};
const pathOf = (sample) => `/samples/${encodeURIComponent(sample.slug)}`;
// In the Chinese interface a sample goes by its Chinese name, where the
// catalogue gives one; the report itself is in whatever language it is in.
const titleOf = (sample, lang = "English") => (lang === "English"
  ? `${sample.title} · Sample reports`
  : `${sample.title_zh || sample.title} · 示例报告`);
// The page's own name follows the interface too. Until 2026-11-15 it was the
// served <title>, English whatever the reader had chosen.
const defaultTitleZh = "示例报告 · 学术成果商业化评估";
// The stub renderer returns its input, so the article names the sample on screen.
const shown = () => el("sample-reader").children.find((c) => c.tag === "article")?.html ?? null;
// The article itself, for its lang: the reader's language is the interface's,
// the report's is the catalog's.
const articleOf = () => el("sample-reader").children.find((c) => c.tag === "article") ?? null;
async function click(sample) {
  const card = el("sample-list").children.find((c) => c.href === pathOf(sample));
  assert(card, `No card for ${sample.slug}`);
  card.fire("click");
  await settle();
}
async function go(pathname) {  // Back/Forward: the browser has already changed the URL.
  location.pathname = pathname;
  for (const callback of windowListeners.popstate ?? []) callback({});
  await settle();
}
async function switchLanguage(value) {
  el("ui-lang").value = value;
  el("ui-lang").fire("change");
  await settle();
}
let checks = 0;
const expectTitle = (expected, why) => { assert.equal(document.title, expected, why); checks++; };
const [first, second] = samples;

if (scenario === "index") {
  await start("/samples");
  expectTitle(titleOf(first), "/samples opens the first sample, and names it");
  assert.equal(shown(), `# ${first.slug}`);
} else if (scenario === "each_sample") {
  await start("/samples");
  for (const sample of samples) {
    await click(sample);
    assert.equal(location.pathname, pathOf(sample));
    expectTitle(titleOf(sample), `Opening ${sample.slug}`);
    assert.equal(shown(), `# ${sample.slug}`);
  }
} else if (scenario === "history") {
  await start(pathOf(first));
  expectTitle(titleOf(first), "Deep link");
  await click(second);
  expectTitle(titleOf(second), "Card click");
  await go(pathOf(first));
  expectTitle(titleOf(first), "Back");
  await go(pathOf(second));
  expectTitle(titleOf(second), "Forward");
  await go("/samples");
  expectTitle(titleOf(first), "Back to the bare list URL, which shows the first sample");
} else if (scenario === "language") {
  await start(pathOf(second));
  await switchLanguage("Simplified Chinese");
  assert.equal(document.documentElement.lang, "zh-CN", "The real i18n module switched");
  assert(second.title_zh && second.title_zh !== second.title, "The second sample has a Chinese name");
  expectTitle(titleOf(second, "Simplified Chinese"), "A language switch gives the Chinese name and suffix");
  await switchLanguage("English");
  expectTitle(titleOf(second), "And back");
} else if (scenario === "article_lang") {
  // The catalog's one Chinese report and an English one: each keeps its own
  // language whatever the interface says, and a switch of the interface
  // moves the page root but not the open report.
  const chinese = samples.find((s) => s.language === "Simplified Chinese");
  const english = samples.find((s) => s.language === "English");
  assert(chinese, "The catalog has a Chinese report");
  assert(english, "The catalog has an English report");
  const expectArticleLang = (expected, why) => {
    const article = articleOf();
    assert(article, "An article is on screen");
    assert.equal(article.lang, expected, why);
    checks++;
  };
  await start(pathOf(chinese));
  assert.equal(document.documentElement.lang, "en", "The page root starts in the interface language");
  expectArticleLang("zh-CN", "A Chinese report has lang=\"zh-CN\" in the English interface");
  await click(english);
  expectArticleLang("en", "An English report has lang=\"en\" in the English interface");
  await switchLanguage("Simplified Chinese");
  assert.equal(document.documentElement.lang, "zh-CN", "The switch moves the page root");
  expectArticleLang("en", "The switch keeps the open English report's language");
  expectTitle(titleOf(english, "Simplified Chinese"), "And the tab still follows the switch");
  await click(chinese);
  expectArticleLang("zh-CN", "A Chinese report has lang=\"zh-CN\" in the Chinese interface");
  await switchLanguage("English");
  assert.equal(document.documentElement.lang, "en", "Switching back moves the page root");
  expectArticleLang("zh-CN", "Switching back keeps the open Chinese report's language");
} else if (scenario === "article_lang_unknown") {
  // A catalog entry with no recognized language: the article carries none
  // of its own and inherits the page's, which follows the interface.
  list = samples.map((s) => ({ ...s, language: "Klingon" }));
  await start("/samples");
  const article = articleOf();
  assert(article, "An article is on screen");
  assert(!article.lang, "No recognized language leaves the article without a lang of its own");
  assert.equal(document.documentElement.lang, "en", "The page root still follows the interface");
} else if (scenario === "unknown_slug") {
  await start("/samples/no-such-sample");
  expectTitle(defaultTitle, "An unknown slug shows the page's own title");
  assert.equal(el("sample-reader").textContent, "No sample with that name.");
  await switchLanguage("Simplified Chinese");
  expectTitle(defaultTitleZh, "A language switch names the page in Chinese and invents no sample title");
  await switchLanguage("English");
  expectTitle(defaultTitle, "And back: the page's name as it is served");
  await go(pathOf(first));
  expectTitle(titleOf(first), "A known slug after an unknown one");
  await go("/samples/no-such-sample");
  expectTitle(defaultTitle, "Leaving a sample for an unknown slug drops its name");
} else if (scenario === "stale_response") {
  deferReads = true;
  await start(pathOf(first));
  await click(second);
  expectTitle(titleOf(second), "Named on selection, before its report arrives");
  pendingReads.find((r) => r.slug === second.slug).release();
  await settle();
  pendingReads.find((r) => r.slug === first.slug).release();
  await settle();
  assert.equal(shown(), `# ${second.slug}`, "The late response for the abandoned sample is dropped");
  expectTitle(titleOf(second), "and does not rename the tab either");
} else if (scenario === "list_failed") {
  listStatus = 500;
  await start(pathOf(first));
  expectTitle(defaultTitle, "No list, no sample to name");
  const failed = () => el("sample-reader").children;
  assert.deepEqual(failed().map((c) => [c.tag, c.className, c.textContent]),
    [["p", "empty-note", "The sample list could not be loaded."], ["button", "samples__retry", "Try again"]]);
  assert.equal(failed()[1].type, "button", "A button, so it never submits a form");
  // The list's way on is a reload, as the main page's boot failure does (#427).
  failed()[1].fire("click");
  assert.deepEqual(reloads, [true], "The retry reloads the page");
  // A language switch redraws the note in the new language: there is no
  // sample to reopen, so the list failure is the note that follows.
  await switchLanguage("Simplified Chinese");
  assert.deepEqual(failed().map((c) => c.textContent), ["示例列表加载失败。", "重试"]);
  await switchLanguage("English");
  assert.deepEqual(failed().map((c) => c.textContent), ["The sample list could not be loaded.", "Try again"]);
} else if (scenario === "empty_list") {
  list = [];
  await start("/samples");
  expectTitle(defaultTitle, "Nothing to open");
  assert.equal(el("sample-reader").textContent, "Choose a report above.");
} else throw Error(`Unknown scenario ${scenario}`);
console.log(`PASS ${scenario} (${checks} checks)`);
