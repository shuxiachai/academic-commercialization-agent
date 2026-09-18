/* Observe the shipped renderer; never infer a "pass" fact from the fixture.
 * This minimal DOM records text/HTML sinks; real layout/keyboard/HTML parsing
 * is covered by the loopback Chromium smoke, not simulated here. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const input = JSON.parse(fs.readFileSync(0, "utf8"));
let focused = null;
class Element {
  constructor(tag) {
    Object.assign(this, { tag, children: [], dataset: {}, style: {}, attributes: {},
      className: "", hidden: false, value: "", disabled: false, listeners: new Map(),
      _text: "", _html: "" });
    this.classList = {
      add: (...names) => { this.className = [this.className, ...names].filter(Boolean).join(" "); },
      remove: (...names) => { this.className = this.className.split(/\s+/).filter(n => !names.includes(n)).join(" "); },
    };
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this._text = this._html = ""; this.children = nodes; }
  set textContent(value) { this.replaceChildren(); this._text = String(value); }
  get textContent() { return this._text + this.children.map(n => n.textContent).join(""); }
  set innerHTML(value) { this.replaceChildren(); this._html = value; }
  get innerHTML() { return this._html; }
  focus() { focused = this; }
  addEventListener(type, callback) { this.listeners.set(type, callback); }
  dispatch(type) {
    if (type === "click" && this.disabled) return;
    assert(this.listeners.has(type), `Missing ${type} listener on ${this.className}`);
    this.listeners.get(type)({ target: this, preventDefault() {} });
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  querySelector(selector) {
    const view = selector.match(/data-view="([^"]+)"/)?.[1];
    assert(view, `Unsupported harness selector: ${selector}`);
    return walk(this).find(node => node.dataset.view === view) ?? null;
  }
}
const walk = node => [node, ...node.children.flatMap(walk)];
const byClass = (root, name) => walk(root).filter(n => n.className.split(/\s+/).includes(name));
const find = (root, name) => byClass(root, name)[0];
const texts = (root, name) => byClass(root, name).map(n => n.textContent);
const calls = [];
const storageWrites = [];
const logs = [];
let resolveOld;
const context = vm.createContext({
  URL, // Positive HTTPS control must exercise the same URL API as the browser.
  localStorage: {
    getItem: () => input.language ?? "English",
    setItem: (...args) => storageWrites.push(args),
    removeItem: (...args) => storageWrites.push(args),
  },
  console: { log: (...args) => logs.push(args), warn: (...args) => logs.push(args), error: (...args) => logs.push(args) },
  document: { createElement: tag => new Element(tag), createTextNode: text => {
    const node = new Element("#text"); node.textContent = text; return node;
  } },
  container: new Element("main"),
  api: {
    getArtifact: async (runId, artifact) => {
      calls.push({ runId, artifact });
      assert.equal(artifact, "sources");
      if (input.stale && runId === "old") return new Promise(resolve => { resolveOld = resolve; });
      if (input.failure) throw Object.assign(new Error(input.failure.message), { status: input.failure.status });
      return input.payload;
    },
    getReport: async runId => {
      calls.push({ runId, artifact: "report" });
      return input.report ?? "HEALTHY_REPORT_SENTINEL";
    },
  },
});

// Mutate only the copy loaded into this VM. Each replacement must hit exactly
// once so a drifted mutation cannot quietly turn into an unmutated green run.
const mutations = {
  omit_excerpt: ['excerpt.append(el("div", "source__text", saved.text));', ""],
  truncate_text: ['excerpt.append(el("div", "source__text", saved.text));',
    'excerpt.append(el("div", "source__text", saved.text.slice(0, 24)));'],
  id_prefix: ["row.searchId === id", "row.searchId?.startsWith(id)"],
};
for (const name of ["i18n.js", "result.js"]) {
  let source = fs.readFileSync(`${input.root}/web/static/js/${name}`, "utf8")
    .replace(/^import .*;\r?\n/gm, "").replace(/export /g, "");
  if (name === "result.js" && input.mutation) {
    const [before, after] = mutations[input.mutation] ?? [];
    assert(before, "Unknown mutation");
    assert.equal(source.split(before).length - 1, 1, "Mutation anchor drifted");
    source = source.replace(before, after);
  }
  vm.runInContext(source, context, { filename: name });
}
async function flush() {
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
}
async function render(runId) {
  context.runId = runId;
  context.progress = { artifacts: input.artifacts ?? ["report", "sources"] };
  vm.runInContext("render(container, runId, progress)", context);
  await flush();
}
async function tab(name) {
  const node = byClass(context.container, "tab").find(n => n.dataset.view === name);
  assert(node, `Missing tab: ${name}`);
  node.dispatch("click");
  await flush();
}
function snapshot() {
  const root = context.container;
  const sourcePanel = byClass(root, "panel").find(n => n.dataset.view === "sources") ?? root;
  const control = name => {
    const node = find(root, name);
    return node ? { disabled: node.disabled, text: node.textContent, value: node.value,
      focused: focused === node, attributes: node.attributes } : null;
  };
  return {
    rows: byClass(sourcePanel, "source").map(row => {
      const details = find(row, "source__excerpt");
      const link = find(row, "source__link");
      return {
        id: find(row, "source__id")?.textContent ?? null,
        title: link?.textContent ?? null,
        link: link ? { tag: link.tag, href: link.href ?? null, rel: link.rel ?? null, target: link.target ?? null } : null,
        excerpt_tag: details?.tag ?? null,
        summary_tag: details?.children[0]?.tag ?? null,
        excerpts: texts(row, "source__text"),
        excerpt_children: byClass(row, "source__text").map(n => n.children.length),
        excerpt_state: texts(row, "source__excerpt-state"),
        summary_source: texts(row, "source__summary-source"),
        faults: texts(row, "source__fault"),
        meta: texts(row, "source__meta"),
      };
    }),
    status: texts(root, "sources__status"),
    warnings: texts(root, "sources__warning"),
    errors: texts(root, "sources__error"),
    notes: texts(sourcePanel, "empty-note"),
    missing: texts(root, "sources__missing"),
    disclosure: texts(root, "sources__disclosure"),
    source_html_writes: walk(sourcePanel).filter(n => n._html).map(n => n._html),
    forbidden_tags: walk(sourcePanel).filter(n => ["img", "script", "iframe", "svg"].includes(n.tag)).map(n => n.tag),
    report_html: byClass(root, "panel").find(n => n.dataset.view === "report")?.innerHTML ?? null,
    active_tab: byClass(root, "tab").find(n => n.dataset.active === "true")?.dataset.view ?? null,
    search: control("sources__search"), clear: control("sources__clear"),
    prev: control("sources__prev"), next: control("sources__next"),
    requests: calls.slice(),
  };
}

const states = [];
await render(input.stale ? "old" : "fixture");
if ((input.artifacts ?? ["report", "sources"]).includes("sources")) await tab("sources");
states.push(snapshot());
if (input.stale) {
  assert.equal(typeof resolveOld, "function", "Old read was not held");
  await render("new");
  await tab("sources");
  states.push(snapshot());
  resolveOld(input.stale.payload);
  await flush();
  states.push(snapshot());
}
for (const action of input.actions ?? []) {
  if (Object.hasOwn(action, "search")) {
    const search = find(context.container, "sources__search");
    assert(search, "Missing search input");
    search.value = action.search;
    search.dispatch("input");
  } else if (action.tab) {
    await tab(action.tab);
  } else {
    assert(["clear", "next", "prev"].includes(action.click), "Unknown action");
    const button = find(context.container, `sources__${action.click}`);
    assert(button, "Missing control");
    button.dispatch("click");
  }
  await flush();
  states.push(snapshot());
}
console.log(JSON.stringify({ states, requests: calls, storage_writes: storageWrites, logs }));
