/* The contents list follows the open sample, through the served reader modules. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [dir, scenario] = process.argv.slice(2);
const { html, samples, markdown } = JSON.parse(fs.readFileSync(path.join(dir, "input.json"), "utf8"));
assert(samples.length >= 2, "The scenarios need at least two committed samples");

class Element {
  constructor(tag = "div") {
    Object.assign(this, { tag, className: "", href: "", value: "", html: "", id: "", open: false,
      dataset: {}, attributes: {}, listeners: {}, children: [], scrolledTo: 0 });
    this._text = "";
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  // The stub renderer emits only <h2> elements; parse them back, as a browser would.
  set innerHTML(value) {
    this.html = String(value);
    this.children = [...this.html.matchAll(/<h2>([^<]*)<\/h2>/g)].map(([, text]) => {
      const heading = new Element("h2");
      heading.textContent = text;
      return heading;
    });
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this._text = ""; this.html = ""; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
  querySelectorAll(selector) {
    assert.equal(selector, "h2", "The contents read the article's h2 headings");
    const found = [];
    const walk = (node) => { for (const child of node.children) { if (child.tag === "h2") found.push(child); walk(child); } };
    walk(this);
    return found;
  }
  scrollIntoView() { this.scrolledTo++; }
  fire(name, event = {}) {
    for (const callback of this.listeners[name] ?? []) callback({ preventDefault() {}, button: 0, ...event });
  }
}

// Only ids the served page really has: a renamed element must fail here.
const elements = Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [id, new Element()]));
const el = (id) => { assert(elements[id], `Missing DOM #${id}`); return elements[id]; };
const windowListeners = {};
const stored = new Map();
const media = { matches: scenario !== "narrow", listeners: [] };
globalThis.document = {
  title: "",
  documentElement: { lang: "en", dataset: {} },
  querySelector: (selector) => { assert(selector.startsWith("#"), selector); return el(selector.slice(1)); },
  querySelectorAll: () => [],
  createElement: (tag) => new Element(tag),
};
globalThis.location = { pathname: "/samples", hash: "" };
globalThis.history = {
  pushState(_state, _unused, url) {
    const next = new URL(url, "https://samples.test");
    Object.assign(location, { pathname: next.pathname, hash: next.hash });
  },
};
globalThis.window = {
  addEventListener: (name, callback) => (windowListeners[name] ??= []).push(callback),
  matchMedia: (query) => {
    assert.equal(query, "(min-width: 1280px)", "samples.css places the contents beside the report from 1280px");
    return { get matches() { return media.matches; }, addEventListener: (name, cb) => media.listeners.push([name, cb]) };
  },
};
globalThis.localStorage = { getItem: (k) => stored.get(k) ?? null, setItem: (k, v) => stored.set(k, String(v)) };

let list = samples, failReads = false;
const reads = [];
// A sample's scorecard, read beside its report. By slug: an object is served
// as JSON, a string as that body, "refused" fails the request itself, and a
// slug with no entry has no scorecard (404), which is what every scenario
// written before scorecards existed sees.
const scorecards = {};
const scoreReads = [];
globalThis.cited = [];
globalThis.fetch = async (url) => {
  if (url === "/api/samples") {
    return new Response(JSON.stringify(list), { status: 200, headers: { "Content-Type": "application/json" } });
  }
  const scores = url.match(/^\/api\/samples\/([^/]+)\/scores$/);
  if (scores) {
    const slug = decodeURIComponent(scores[1]);
    scoreReads.push(slug);
    const card = scorecards[slug];
    if (card === "refused") throw new TypeError("network");
    // An answer that is not OK is not a scorecard, whatever its body says.
    if (card === undefined) return new Response('{"detail":"none","overall_score":99}', { status: 404, headers: { "Content-Type": "application/json" } });
    return new Response(typeof card === "string" ? card : JSON.stringify(card),
      { status: 200, headers: { "Content-Type": "application/json" } });
  }
  const slug = decodeURIComponent(url.replace(/^\/api\/samples\//, ""));
  reads.push(slug);
  if (failReads) return new Response("", { status: 503 });
  return new Response(markdown[slug] ?? "", { status: 200, headers: { "Content-Type": "text/markdown" } });
};

const settle = async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0)); };
const start = async (pathname, hash = "") => {
  Object.assign(location, { pathname, hash });
  await import(pathToFileURL(path.join(dir, "samples.js")).href);
  await settle();
};
const pathOf = (sample) => `/samples/${encodeURIComponent(sample.slug)}`;
const reader = () => el("sample-reader");
const article = () => reader().children.find((c) => c.tag === "article");
const tocs = () => reader().children.filter((c) => c.className === "samples__toc");
const headingsOf = (sample) => [...markdown[sample.slug].matchAll(/^## (.*)$/gm)].map(([, text]) => text);
async function click(sample) {
  const card = el("sample-list").children.find((c) => c.href === pathOf(sample));
  assert(card, `No card for ${sample.slug}`);
  card.fire("click");
  await settle();
}
async function go(pathname, hash = "") {  // Back/Forward or a fragment link: the URL has already changed.
  Object.assign(location, { pathname, hash });
  for (const callback of windowListeners.popstate ?? []) callback({});
  await settle();
}
async function switchLanguage(value) {
  el("ui-lang").value = value;
  el("ui-lang").fire("change");
  await settle();
}
let checks = 0;
const shape = () => reader().children.map((c) => c.className || c.tag);
const WITHOUT_SCORES = ["samples__notice", "samples__download", "samples__toc", "prose"];
const WITH_SCORES = ["samples__notice", "samples__download", "brief", "samples__scorecard", "samples__toc", "prose"];
/** The brief and the scorecard of the open sample, between the download link and the contents. */
function expectScores(sample, { title = "Scorecard", note = /^A sample keeps only the report and its scorecard, not the run's automatic checks or its source list,/, open = true } = {}) {
  assert.deepEqual(shape(), WITH_SCORES);
  const overall = String(scorecards[sample.slug].overall_score);
  const [, , brief, block] = reader().children;
  assert.equal(brief.dataset.overall, overall, "The brief is this sample's");
  // The run page's brief says it was built from the run's checks too, and that
  // every line can be opened below. A sample keeps no checks; it says so.
  assert.match(brief.dataset.note, note);
  assert.equal(brief.dataset.markdown, markdown[sample.slug], "...and reads this sample's report");
  assert.equal(block.tag, "details");
  assert.equal(block.open, open, "Open where the contents sit beside the report, folded above it on a narrow screen");
  const [summary, card] = block.children;
  assert.equal(summary.tag, "summary");
  assert.equal(summary.textContent, title);
  assert.equal(card.className, "scorecard");
  assert.equal(card.dataset.overall, overall);
  assert.equal(card.dataset.sources, "null", "A sample has no source registry to draw market figures from");
  checks++;
}
/** One contents block, between the notice and the article, linking exactly the open sample's headings. */
function expectContents(sample, label = "Contents", order = WITHOUT_SCORES) {
  const [toc, ...extra] = tocs();
  assert(toc, `No contents for ${sample.slug}`);
  assert.equal(extra.length, 0, "One contents block");
  assert.deepEqual(shape(), order);
  assert.equal(toc.tag, "nav");
  assert.equal(toc.attributes["aria-label"], label);
  const [details] = toc.children;
  assert.equal(details.tag, "details");
  const [summary, list] = details.children;
  assert.equal(summary.tag, "summary");
  assert.equal(summary.textContent, label);
  const expected = headingsOf(sample);
  assert(expected.length > 0, `${sample.slug} has no sections`);
  const headings = article().querySelectorAll("h2");
  // A counter, not a slug of the text: the Chinese sample's headings have no Latin letters.
  assert.deepEqual(headings.map((h) => h.id), expected.map((_, i) => `section-${i + 1}`));
  const links = list.children.map((item) => item.children[0]);
  assert.deepEqual(links.map((a) => [a.tag, a.href, a.textContent]),
    expected.map((text, i) => ["a", `#section-${i + 1}`, text]));
  checks++;
  return details;
}

const [first, second] = samples;
const chinese = samples.find((sample) => /[一-鿿]/.test(headingsOf(sample).join("")));

if (scenario === "each_sample") {
  assert(chinese, "One committed sample has Chinese headings");
  await start("/samples");
  expectContents(first);
  for (const sample of samples) {
    await click(sample);
    expectContents(sample);
  }
} else if (scenario === "rebuilt") {
  await start(pathOf(first));
  expectContents(first);
  await click(second);
  expectContents(second);
  await switchLanguage("Simplified Chinese");
  expectContents(second, "目录");
  await switchLanguage("English");
  expectContents(second);
  await go(pathOf(first));
  expectContents(first);
} else if (scenario === "fragment") {
  // A contents link changes only the hash, and Chromium fires popstate for it.
  await start(pathOf(second));
  const shown = article();
  await go(pathOf(second), "#section-3");
  assert.deepEqual(reads, [second.slug], "Following a contents link does not read the sample again");
  assert.equal(article(), shown, "and does not re-render it");
  await go(pathOf(second));
  assert.deepEqual(reads, [second.slug], "Back to the top of the same sample neither");
  await go(pathOf(first));
  assert.deepEqual(reads, [second.slug, first.slug], "Back to another sample still opens it");
  expectContents(first);
  // The bare list URL shows the first sample, so its fragments are the first sample's too.
  await go("/samples", "#section-2");
  assert.deepEqual(reads, [second.slug, first.slug], "A fragment of /samples while it shows the first sample");
  checks++;
} else if (scenario === "failed_read") {
  failReads = true;
  await start(pathOf(first));
  assert.equal(reader().textContent, "This report could not be loaded.");
  assert.equal(tocs().length, 0);
  failReads = false;
  await go(pathOf(first));
  assert.deepEqual(reads, [first.slug, first.slug], "A sample that never rendered is read again");
  expectContents(first);
} else if (scenario === "deep_link") {
  await start(pathOf(second), "#section-4");
  expectContents(second);
  const scrolled = article().querySelectorAll("h2").map((h) => h.scrolledTo);
  assert.deepEqual(scrolled, scrolled.map((_, i) => (i === 3 ? 1 : 0)), "The linked section, once");
  // Back from another sample to a section of this one.
  await click(first);
  await go(pathOf(second), "#section-2");
  assert.deepEqual(article().querySelectorAll("h2").map((h) => h.scrolledTo).slice(0, 3), [0, 1, 0]);
  checks++;
} else if (scenario === "wide" || scenario === "narrow") {
  await start(pathOf(first));
  const wide = scenario === "wide";
  assert.equal(expectContents(first).open, wide, "Open beside the report, closed above it");
  // Resizing across the width moves the block, so it opens or closes with it.
  media.matches = !wide;
  for (const [name, callback] of media.listeners) if (name === "change") callback({ matches: media.matches });
  assert.equal(expectContents(first).open, !wide);
  await click(second);
  assert.equal(expectContents(second).open, !wide, "A new sample's contents start in the current layout");
} else if (scenario === "scorecard") {
  // A report without its score is half of what a run delivers: the verdict,
  // the five dimensions and the reasons were what the sample page left out.
  samples.forEach((sample, i) => { scorecards[sample.slug] = { overall_score: 40 + i }; });
  await start(pathOf(first));
  expectScores(first);
  expectContents(first, "Contents", WITH_SCORES);
  assert.deepEqual(scoreReads, [first.slug], "One read of the scorecard, beside the report's");
  assert.deepEqual(cited.splice(0).sort(), ["brief", "prose", "scorecard"],
    "Citations in the brief and the scorecard open the same cards as the report's");
  await click(second);
  expectScores(second);
  expectContents(second, "Contents", WITH_SCORES);
  await switchLanguage("Simplified Chinese");
  expectScores(second, { title: "评分卡", note: /^示例只保留了报告和评分卡，没有运行时的自动检查和来源清单，/ });
  expectContents(second, "目录", WITH_SCORES);
  await switchLanguage("English");
  const before = scoreReads.length;
  await go(pathOf(second), "#section-2");
  assert.equal(scoreReads.length, before, "Following a contents link reads no scorecard again");
  await go(pathOf(first));
  expectScores(first);
  // On a phone the scorecard is two screens of its own before the report:
  // it folds when the window narrows, and a sample opened there starts folded.
  media.matches = false;
  for (const [name, callback] of media.listeners) if (name === "change") callback({ matches: false });
  expectScores(first, { open: false });
  await click(second);
  expectScores(second, { open: false });
  media.matches = true;
  for (const [name, callback] of media.listeners) if (name === "change") callback({ matches: true });
  expectScores(second);
  // A sample with no scorecard, opened after one that had it: resizing then moves only what is on the page.
  delete scorecards[first.slug];
  await click(first);
  media.matches = false;
  for (const [name, callback] of media.listeners) if (name === "change") callback({ matches: false });
  expectContents(first);
} else if (scenario === "scorecard_missing") {
  // The report is the sample. Whatever happens to the scorecard's read, the
  // report is shown as it was before scorecards existed.
  const [third, fourth, fifth] = samples.slice(2);
  assert(fifth, "This scenario needs five committed samples");
  scorecards[second.slug] = { overall_score: 61 };
  scorecards[third.slug] = "refused";
  scorecards[fourth.slug] = "<html>not a scorecard</html>";
  scorecards[fifth.slug] = { overall_score: "high" };
  await start(pathOf(first));
  expectContents(first);                         // 404
  await click(third);
  expectContents(third);                         // the request itself failed
  await click(fourth);
  expectContents(fourth);                        // answered, but not JSON
  await click(fifth);
  expectContents(fifth);                         // JSON with no readable overall: no brief, so no card either
  await click(second);
  expectScores(second);
  await click(first);
  expectContents(first);                         // ...and the one before it leaves nothing behind
} else if (scenario === "no_headings") {
  list = [...samples, { ...first, slug: "plain", title: "Plain" }];
  markdown.plain = "# Plain\n\nNo sections.";
  await start("/samples/plain");
  assert.equal(tocs().length, 0, "No contents without sections");
  assert.deepEqual(reader().children.map((c) => c.className), ["samples__notice", "samples__download", "prose"]);
  checks++;
} else throw Error(`Unknown scenario ${scenario}`);
console.log(`PASS ${scenario} (${checks} contents checks)`);
