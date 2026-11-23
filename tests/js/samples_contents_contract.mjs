/* The contents list follows the open sample, through the served reader modules. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [dir, scenario] = process.argv.slice(2);
const { html, samples, markdown, decisions } = JSON.parse(fs.readFileSync(path.join(dir, "input.json"), "utf8"));
assert(samples.length >= 2, "The scenarios need at least two committed samples");

class Element {
  constructor(tag = "div") {
    Object.assign(this, { tag, className: "", href: "", value: "", html: "", id: "", open: false,
      dataset: {}, attributes: {}, listeners: {}, children: [], scrolledTo: 0, focused: 0, tabIndex: 0 });
    this._text = "";
    const classes = new Set();
    this.classList = { add: (name) => classes.add(name), remove: (name) => classes.delete(name), contains: (name) => classes.has(name) };
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
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
  querySelectorAll(selector) {
    // The contents read the article's h2 headings; the conclusion card's link
    // looks through its text blocks, of which the stub renderer draws only h2.
    assert(selector === "h2" || selector === "p, li, td, h2, h3, h4", selector);
    const found = [];
    const walk = (node) => { for (const child of node.children) { if (child.tag === "h2") found.push(child); walk(child); } };
    walk(this);
    return found;
  }
  scrollIntoView() { this.scrolledTo++; }
  focus() { this.focused++; }
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
// A promise the list waits for before it is answered: the page before the
// list arrives (scenario "skeleton").
let listHold = null;
// The deployment's public facts (/api/site), of which the reader wants
// whether it has accounts and takes new ones. "refused" fails the request
// itself, a string is served as that body.
let access = { status: 200, body: { retention_days: 90, accounts: true, signup_open: true } };
const accessReads = [];
const reads = [];
// A sample's scorecard, read beside its report. By slug: an object is served
// as JSON, a string as that body, "refused" fails the request itself, and a
// slug with no entry has no scorecard (404), which is what every scenario
// written before scorecards existed sees.
const scorecards = {};
const scoreReads = [];
// What a sample's report concludes (/api/samples/<slug>/decision): the served
// answer, unless a scenario puts "refused" (the request fails) or
// { status, body } here for a slug.
const decisionAnswers = {};
const decisionReads = [];
globalThis.cited = [];
globalThis.fetch = async (url, options) => {
  assert.equal(options, undefined, "The reader sends no header, credential or body with any request");
  assert.notEqual(url, "/api/access/check", "The access check refuses a page that sends no credential; it is not asked");
  if (url === "/api/site") {
    accessReads.push(url);
    if (access === "refused") throw new TypeError("network");
    return new Response(typeof access.body === "string" ? access.body : JSON.stringify(access.body),
      { status: access.status, headers: { "Content-Type": "application/json" } });
  }
  if (url === "/api/samples") {
    if (listHold) await listHold;
    if (list === "refused") throw new TypeError("network");
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
  const decided = url.match(/^\/api\/samples\/([^/]+)\/decision$/);
  if (decided) {
    const slug = decodeURIComponent(decided[1]);
    decisionReads.push(slug);
    const answer = decisionAnswers[slug] ?? { status: 200, body: decisions[slug] };
    if (answer === "refused") throw new TypeError("network");
    return new Response(typeof answer.body === "string" ? answer.body : JSON.stringify(answer.body),
      { status: answer.status, headers: { "Content-Type": "application/json" } });
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
const WITHOUT_SCORES = ["samples__notice", "samples__download", "samples__toc", "prose", "samples__neighbours", "samples__next"];
const WITH_SCORES = ["samples__notice", "samples__download", "brief", "samples__scorecard", "samples__toc", "prose", "samples__neighbours", "samples__next"];
// A sample whose run was given a decision context has what was asked and the
// conclusion card under the download link.
const DECIDED = ["samples__context", "verdict-card"];
const decidedOf = (sample) => Boolean(sample.decision);
const orderFor = (sample, scored = false) => {
  const order = [...(scored ? WITH_SCORES : WITHOUT_SCORES)];
  if (decidedOf(sample)) order.splice(2, 0, ...DECIDED);
  return order;
};
const cards = () => el("sample-list").children;
const cardOf = (sample) => cards().find((c) => c.href === pathOf(sample));
const partsOf = (card) => Object.fromEntries(card.children.map((c) => [c.className, c]));
/** The block after the report: one sentence and one link. */
function expectNext(text, label, href) {
  const block = reader().children.at(-1);
  assert.equal(block.className, "samples__next");
  assert.equal(block.tag, "aside");
  assert.deepEqual(block.children.map((c) => [c.tag, c.className, c.textContent]),
    [["p", "samples__next-text", text], ["a", "samples__next-link", label]]);
  assert.equal(block.children[1].href, href);
  checks++;
}
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
function expectContents(sample, label = "Contents", order = orderFor(sample)) {
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

// The page opens the first sample listed, which since 2026-11-21 is the one run
// with a decision context; the scenarios about every sample's reader use the
// first two without one, and say so where they rely on the order.
const opened = samples[0];
const [first, second] = samples.filter((sample) => !decidedOf(sample));
const chinese = samples.find((sample) => /[一-鿿]/.test(headingsOf(sample).join("")));

if (scenario === "each_sample") {
  assert(chinese, "One committed sample has Chinese headings");
  await start("/samples");
  expectContents(opened);
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
  await go(pathOf(opened));
  assert.deepEqual(reads, [second.slug, opened.slug], "Back to another sample still opens it");
  expectContents(opened);
  // The bare list URL shows the first sample, so its fragments are the first sample's too.
  await go("/samples", "#section-2");
  assert.deepEqual(reads, [second.slug, opened.slug], "A fragment of /samples while it shows the first sample");
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
  const [third, fourth, fifth] = samples.filter((sample) => !decidedOf(sample)).slice(2);
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
  assert.deepEqual(reader().children.map((c) => c.className), ["samples__notice", "samples__download", "prose", "samples__neighbours", "samples__next"]);
  checks++;
} else if (scenario === "cards") {
  // The list as served carries each sample's score, readiness level and
  // language; a card says them under the title, and still says when it was added.
  assert(samples.every((sample) => typeof sample.overall_score === "number" && typeof sample.trl_score === "number"),
    "Every committed sample is listed with its scorecard's numbers");
  await start("/samples");
  assert.equal(cards().length, samples.length);
  for (const sample of samples) {
    const parts = partsOf(cardOf(sample));
    // The sample run with a decision context says so on its card.
    assert.deepEqual(cardOf(sample).children.map((c) => c.className),
      ["sample-card__title", "sample-card__verdict", ...(decidedOf(sample) ? ["sample-card__decision"] : []), "sample-card__meta"]);
    if (decidedOf(sample)) assert.equal(parts["sample-card__decision"].textContent, "With a decision conclusion");
    assert.equal(parts["sample-card__title"].textContent, sample.title);
    assert.equal(parts["sample-card__verdict"].textContent, `verdict ${sample.overall_score}`);
    assert.equal(parts["sample-card__verdict"].dataset.tone, sample.overall_score >= 70 ? "success" : "warning");
    assert.equal(parts["sample-card__meta"].textContent,
      `TRL ${sample.trl_score} · in ${sample.language} · Added ${sample.committed}`);
    checks++;
  }
  assert(chinese && chinese.language === "Simplified Chinese", "The Chinese sample is listed as Chinese");
  assert.equal(samples.filter(decidedOf).length, 1, "One committed sample was run with a decision context");
  assert.equal(samples.filter((sample) => sample.language === "English").length, samples.length - 1);
  assert.deepEqual(scoreReads, [opened.slug], "The cards cost no request of their own: only the open sample's scorecard is read");
  await switchLanguage("Simplified Chinese");
  assert.match(partsOf(cardOf(first))["sample-card__meta"].textContent, / · 收录于 /, "The cards follow the language");
} else if (scenario === "cards_without_scores") {
  // A deployment without a sample's scorecard lists it with nulls; a list
  // from before these fields has no such keys at all. Either way the card
  // is the title and the date, and the report opens.
  list = [
    { ...first, overall_score: null, trl_score: null },
    Object.fromEntries(Object.entries(second).filter(([key]) => !["overall_score", "trl_score", "language"].includes(key))),
    { ...samples[2], trl_score: null },
  ];
  await start(pathOf(first));
  const [none, older, half] = cards();
  assert.deepEqual(none.children.map((c) => c.className), ["sample-card__title", "sample-card__meta"]);
  assert.equal(partsOf(none)["sample-card__meta"].textContent, `in ${first.language} · Added ${first.committed}`);
  assert.deepEqual(older.children.map((c) => [c.className, c.textContent]),
    [["sample-card__title", second.title], ["sample-card__meta", `Added ${second.committed}`]]);
  assert.deepEqual(half.children.map((c) => c.className), ["sample-card__title", "sample-card__verdict", "sample-card__meta"]);
  assert.equal(partsOf(half)["sample-card__meta"].textContent, `in ${samples[2].language} · Added ${samples[2].committed}`);
  expectContents(first);
  await click(second);
  expectContents(second);
} else if (scenario === "evidence") {
  // The brief is handed the reference list the page parsed for its citation
  // cards, so it can name the best-rated source; and nothing but that.
  samples.forEach((sample, i) => { scorecards[sample.slug] = { overall_score: 40 + i }; });
  await start(pathOf(first));
  const brief = () => reader().children.find((c) => c.className === "brief");
  assert.equal(brief().dataset.references, "the report's own");
  assert.equal(brief().dataset.extra, "", "No registry, no checks: a sample has neither and is not given them");
  await click(second);
  assert.equal(brief().dataset.references, "the report's own", "Each sample's brief gets its own report's list");
  assert.equal(brief().dataset.markdown, markdown[second.slug]);
  expectScores(second);
  checks++;
} else if (scenario === "next_create" || scenario === "next_sign_in" || scenario === "next_without_accounts"
    || scenario === "next_when_sign_up_is_not_said" || scenario === "next_when_the_question_fails") {
  // After the report, where a reader goes for one of their own. The link
  // names what this deployment offers; the page asks once, as a stranger.
  const cases = {
    next_create: [{ status: 200, body: { accounts: true, signup_open: true } }, "Create account", "创建账号", "/#create-account"],
    next_sign_in: [{ status: 200, body: { accounts: true, signup_open: false } }, "Sign in", "登录", "/#sign-in"],
    next_without_accounts: [{ status: 200, body: { accounts: false, signup_open: false } }, "Open the app", "打开应用", "/"],
    // A server from before this fact existed says it has accounts and nothing
    // of sign-up: an account is then not offered, only the sign-in.
    next_when_sign_up_is_not_said: [{ status: 200, body: { accounts: true } }, "Sign in", "登录", "/#sign-in"],
  };
  // Every way the question can go unanswered ends the same: the plain link.
  // One per process, chosen by the fifth argument, since the page asks once.
  const failures = ["refused", { status: 503, body: "<html>down</html>" }, { status: 401, body: { accounts: true, signup_open: true } },
    { status: 200, body: { accounts: "yes", signup_open: true } }, { status: 200, body: "null" },
    { status: 200, body: { signup_open: true } }];
  const failure = failures[Number(process.argv[4] ?? 0)];
  assert(scenario !== "next_when_the_question_fails" || failure !== undefined, "No such failure");
  const [answer, label, labelZh, href] = cases[scenario] ?? [failure, "Open the app", "打开应用", "/"];
  access = answer;
  await start(pathOf(first));
  expectContents(first);
  expectNext("Run one on your own topic.", label, href);
  await click(second);
  expectNext("Run one on your own topic.", label, href);
  await switchLanguage("Simplified Chinese");
  expectNext("用你自己的主题跑一份。", labelZh, href);
  await go("/samples/not-a-sample");
  assert.deepEqual(shape(), ["empty-note"], "No report, no next step after it");
  assert.equal(accessReads.length, 1, "Asked once for the page, not once for each report");
} else if (scenario === "skeleton") {
  // Until 2026-11-21 the reader said "Choose a report above." while the list
  // above it was still on its way and nothing was there to choose. Now the
  // list holds placeholders, marked busy, and the reader a placeholder too.
  let release;
  listHold = new Promise((resolve) => { release = resolve; });
  // The module's own top-level await is the held request: it is not waited for here.
  Object.assign(location, { pathname: "/samples", hash: "" });
  const loading = import(pathToFileURL(path.join(dir, "samples.js")).href);
  await settle();
  const holders = el("sample-list").children;
  assert(holders.length >= 3, "Placeholders where the cards will be");
  assert(holders.every((c) => c.className === "sample-card sample-card--placeholder" && c.attributes["aria-hidden"] === "true"));
  assert.equal(el("sample-list").attributes["aria-busy"], "true");
  assert.deepEqual(shape(), ["skeleton"], "The reader waits too");
  assert(!reader().textContent.includes("Choose a report above."));
  release();
  await loading;
  await settle();
  assert.equal(el("sample-list").attributes["aria-busy"], undefined, "No longer busy");
  assert.equal(cards().length, samples.length);
  assert(cards().every((c) => c.className === "sample-card"));
  assert.notDeepEqual(shape(), ["skeleton"]);
  checks++;
} else if (scenario === "skeleton_empty") {
  // An empty list is the one time there is nothing to choose: then it says so.
  list = [];
  await start("/samples");
  assert.equal(el("sample-list").attributes["aria-busy"], undefined);
  assert.equal(cards().length, 0);
  assert.deepEqual(reader().children.map((c) => c.textContent), ["Choose a report above."]);
  checks++;
} else if (scenario === "skeleton_failed") {
  list = "refused";
  await start("/samples");
  assert.equal(el("sample-list").attributes["aria-busy"], undefined);
  assert.equal(cards().length, 0, "No placeholder is left standing for a list that will not come");
  assert.deepEqual(reader().children.map((c) => c.textContent), ["The sample list could not be loaded."]);
  checks++;
} else if (scenario === "notice") {
  // The dated notice names the day and the model in words a reader has; the
  // pipeline's commit, which is a term, is one press away under "Technical details".
  await start(pathOf(second));
  const notice = reader().children.find((c) => c.className === "samples__notice");
  assert.equal(notice.tag, "div");
  const [text, tech] = notice.children;
  assert.equal(text.textContent, `A run of ${second.committed} with ${second.model}, kept as it was written. `
    + "One report shows the format, not a measure of accuracy or an up-to-date market assessment, and its citations have not been re-verified.");
  assert(!text.textContent.includes(second.commit) && !/pipeline/i.test(text.textContent));
  assert.equal(tech.tag, "details");
  assert.deepEqual(tech.children.map((c) => [c.tag, c.textContent]),
    [["summary", "Technical details"], ["p", `Pipeline revision: ${second.commit}`]]);
  await switchLanguage("Simplified Chinese");
  const zh = reader().children.find((c) => c.className === "samples__notice");
  assert.equal(zh.children[0].textContent, `${second.committed} 用 ${second.model} 跑出的一次运行，保持原样。`
    + "单份报告展示的是格式，不代表准确率或最新市场判断，其中引用也未重新核验。");
  assert.deepEqual(zh.children[1].children.map((c) => c.textContent), ["技术细节", `流水线版本：${second.commit}`]);
  checks++;
} else if (scenario === "neighbours") {
  // At the end of a report, the samples either side of it, named: the only
  // way on was back up past the whole report to the list.
  assert(samples.length >= 3, "The scenario needs a first, a middle and a last sample");
  const blocks = () => reader().children.filter((c) => c.className === "samples__neighbours");
  const linksOf = () => blocks()[0].children.map((a) => [a.tag, a.className, a.href, a.textContent]);
  const middle = samples[Math.floor(samples.length / 2)];
  const last = samples[samples.length - 1];
  // The stub's sampleTitle, as test_samples_contents_web.py writes it: the
  // Chinese name in the Chinese interface, the listed title otherwise.
  const zhNameOf = (sample) => (typeof sample.title_zh === "string" && sample.title_zh.trim()
    ? sample.title_zh.trim() : sample.title);
  // The first sample: only a next link, naming the second, after the report.
  await start(pathOf(opened));
  assert.equal(blocks().length, 1, "One neighbours block");
  assert.equal(blocks()[0].tag, "nav");
  assert.equal(blocks()[0].attributes["aria-label"], "Neighbouring samples");
  assert.deepEqual(reader().children.map((c) => c.className).slice(-2), ["samples__neighbours", "samples__next"],
    "Between the report and the sign-up block");
  assert.deepEqual(linksOf(), [["a", "samples__neighbour", pathOf(samples[1]), `Next: ${samples[1].title}`]]);
  // A plain click follows it as a card is followed: no reload, the list's
  // mark moves with it, and the reader is brought back into view.
  const scrolledBefore = reader().scrolledTo;
  blocks()[0].children[0].fire("click");
  await settle();
  assert.deepEqual(reads, [opened.slug, samples[1].slug], "The next sample is read, the page is not");
  assert.equal(reader().scrolledTo, scrolledBefore + 1, "The top of the reader, where the new report starts");
  assert.equal(cardOf(samples[1]).attributes["aria-current"], "page");
  assert.equal(cardOf(opened).attributes["aria-current"], undefined);
  assert.deepEqual(linksOf(), [
    ["a", "samples__neighbour", pathOf(opened), `Previous: ${opened.title}`],
    ["a", "samples__neighbour", pathOf(samples[2]), `Next: ${samples[2].title}`],
  ], "The second sample has both, each naming its neighbour");
  // A modified click is the browser's: it opens nothing here.
  blocks()[0].children[0].fire("click", { ctrlKey: true });
  await settle();
  assert.deepEqual(reads, [opened.slug, samples[1].slug], "A Ctrl-click is left to the browser");
  // Back returns to the sample before.
  await go(pathOf(opened));
  assert.deepEqual(linksOf(), [["a", "samples__neighbour", pathOf(samples[1]), `Next: ${samples[1].title}`]]);
  // A middle sample: both links, naming the samples either side of it.
  const beforeMiddle = samples[samples.indexOf(middle) - 1];
  const afterMiddle = samples[samples.indexOf(middle) + 1];
  await click(middle);
  assert.deepEqual(linksOf(), [
    ["a", "samples__neighbour", pathOf(beforeMiddle), `Previous: ${beforeMiddle.title}`],
    ["a", "samples__neighbour", pathOf(afterMiddle), `Next: ${afterMiddle.title}`],
  ]);
  // The last sample: only a previous link, and the names follow a language switch.
  await click(last);
  assert.deepEqual(linksOf(), [
    ["a", "samples__neighbour", pathOf(samples[samples.length - 2]), `Previous: ${samples[samples.length - 2].title}`],
  ]);
  await switchLanguage("Simplified Chinese");
  assert.equal(blocks()[0].attributes["aria-label"], "相邻示例");
  assert.deepEqual(linksOf(), [
    ["a", "samples__neighbour", pathOf(samples[samples.length - 2]), `上一份：${zhNameOf(samples[samples.length - 2])}`],
  ], "The neighbour is named in the current language");
  await switchLanguage("English");
  assert.deepEqual(linksOf(), [
    ["a", "samples__neighbour", pathOf(samples[samples.length - 2]), `Previous: ${samples[samples.length - 2].title}`],
  ]);
  checks++;
} else if (scenario === "first_card_is_the_decision") {
  // The one sample with a decision conclusion stood seventh, out of sight on a
  // screen 717 px wide. It is the first card and the report the page opens.
  await start("/samples");
  assert(decidedOf(cards().length ? samples[0] : {}), "The served list puts it first");
  assert.equal(cards()[0].href, pathOf(samples.find(decidedOf)));
  assert.equal(cards()[0].attributes["aria-current"], "page", "...and it is the one opened");
  assert.deepEqual(decisionReads, [samples.find(decidedOf).slug]);
  checks++;
} else if (scenario.startsWith("decision")) {
  const decided = samples.find(decidedOf);
  assert(decided, "One committed sample was run with a decision context");
  const plain = samples.find((sample) => !decidedOf(sample));
  const card = () => reader().children.find((c) => c.className === "verdict-card");
  const context = () => reader().children.find((c) => c.className === "samples__context");
  if (scenario === "decision") {
    // What was asked, then the conclusion card, under the notice and the
    // download link; the report is not asked for one where its run was not.
    await start(pathOf(plain));
    expectContents(plain);
    assert.deepEqual(decisionReads, [], "A sample run without a decision context is not asked what it concluded");
    await click(decided);
    expectContents(decided);
    assert.deepEqual(decisionReads, [decided.slug], "One read of the conclusion, beside the report's");
    const { asset_description, target_application, decision_owner, decision_type } = decided.decision;
    assert.equal(context().tag, "p");
    // The asset and the application only: the conclusion card under it names
    // the owner and the decision, and the page said both twice until 2026-11-21.
    assert.equal(context().textContent,
      "This run was given a decision context, so its report states a conclusion for the decision below. "
      + `Asset: “${asset_description}”. Target application: “${target_application}”.`);
    assert(!context().textContent.includes(decision_owner) && !context().textContent.includes(decision_type));
    // The served answer, as the server read it from the committed report.
    assert.deepEqual([card().dataset.state, card().dataset.verdict, card().dataset.opens], ["stated", "defer", "function"]);
    assert.deepEqual(cited.filter((name) => name === "verdict-card"), ["verdict-card"],
      "Citations in the card open the same cards as the report's");
    await switchLanguage("Simplified Chinese");
    expectContents(decided, "目录");
    assert.match(context().textContent, /^这次运行填写了决策场景，所以报告针对下面的决策给出了结论。资产或科研成果：“Lab-scale /);
    assert.match(context().textContent, /目标应用：“Utility-scale photovoltaic modules”。$/);
    assert(!context().textContent.includes("决策负责人"));
    await switchLanguage("English");
    // Following a contents link reads nothing again, the conclusion included.
    const before = decisionReads.length;
    await go(pathOf(decided), "#section-2");
    assert.equal(decisionReads.length, before);
    await click(plain);
    expectContents(plain);
    assert.equal(card(), undefined, "...and leaves no card behind on the next sample");
    checks++;
  } else if (scenario === "decision_with_scores") {
    // A run page's order: the conclusion over the brief. The brief is told the
    // run had a decision context, so it does not say one would help.
    scorecards[decided.slug] = { overall_score: 69.3 };
    scorecards[plain.slug] = { overall_score: 60 };
    await start(pathOf(decided));
    assert.deepEqual(shape(), orderFor(decided, true));
    const brief = reader().children.find((c) => c.className === "brief");
    assert.equal(brief.dataset.extra, "progress", "The decided sample's brief knows its run was asked");
    await click(plain);
    assert.deepEqual(shape(), orderFor(plain, true));
    assert.equal(reader().children.find((c) => c.className === "brief").dataset.extra, "", "...and no other sample's does");
    checks++;
  } else if (scenario === "decision_open") {
    // The card's link marks the quoted passage in the report under it and
    // takes the reader there: here by its section's heading, the block the
    // stub renderer draws.
    await start(pathOf(decided));
    const reply = decisions[decided.slug];
    const target = article().children.find((h) => h.textContent === reply.conclusion.section);
    assert(target, "The quoted section is a heading of the report on the page");
    card().open();
    assert(target.classList.contains("prose__found"));
    assert.equal(target.focused, 1, "Focus goes with the reader");
    assert.equal(target.tabIndex, -1);
    assert.equal(target.scrolledTo, 1);
    assert.equal(article().children.filter((h) => h.classList.contains("prose__found")).length, 1);
    checks++;
  } else if (scenario === "decision_not_asked") {
    // A list from before the field, an entry with a field left empty, or one
    // that carries something else: a sample without a decision context.
    const { decision, ...older } = decided;
    list = [older, { ...decided, slug: "half", decision: { ...decision, decision_type: " " } },
      { ...decided, slug: "odd", decision: "License it" }];
    markdown.half = markdown.odd = markdown[decided.slug];
    for (const slug of [decided.slug, "half", "odd"]) {
      await (slug === decided.slug ? start(`/samples/${slug}`) : go(`/samples/${slug}`));
      assert.deepEqual(shape(), WITHOUT_SCORES, slug);
      assert.equal(cardOf(list.find((s) => s.slug === slug)).children.some((c) => c.className === "sample-card__decision"), false);
    }
    assert.deepEqual(decisionReads, [], "None of them is asked what it concluded");
    checks++;
  } else {
    // A conclusion that cannot be read is said to be unread, never dropped:
    // an empty space would read as "the report concluded nothing".
    const failures = ["refused", { status: 404, body: { detail: "none" } }, { status: 200, body: "<html>no</html>" }];
    const failure = failures[Number(process.argv[4] ?? 0)];
    assert(failure !== undefined, "No such failure");
    decisionAnswers[decided.slug] = failure;
    await start(pathOf(decided));
    expectContents(decided);
    assert.equal(card().dataset.state, "unread");
    assert(context(), "What was asked is still said");
    checks++;
  }
} else throw Error(`Unknown scenario ${scenario}`);
console.log(`PASS ${scenario} (${checks} contents checks)`);
