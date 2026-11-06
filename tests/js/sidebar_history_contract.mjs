// The run list beyond its first page, and its search box.
//
// Runs the shipped sidebar.js against a fake history and records every
// request it makes. What matters most here is what is NOT in those requests:
// the words typed into the search box.
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../web/static/js/sidebar.js", import.meta.url), "utf8")
  .replace(/^import .*;\r?\n/gm, "").replace(/export /g, "");

class Element {
  constructor() { Object.assign(this, { children: [], dataset: {}, hidden: false, textContent: "", listeners: {} }); }
  set innerHTML(_value) { this.children = []; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute() {}
  addEventListener(name, handler) { this.listeners[name] = handler; }
}

function harness(history) {
  const requests = [];
  const box = new Element();
  box.hidden = true;
  const api = { listRuns: async (limit = 50, offset = 0) => {
    requests.push({ limit, offset });
    return { runs: history.slice(offset, offset + limit), total: history.length };
  } };
  const document = { createElement: () => new Element(), querySelector: (selector) => (selector === "#run-search" ? box : null) };
  const t = (key) => key;
  const module = new Function("api", "t", "document",
    `${source}; return { render, refresh, setQuery, showMore, resetView, matches };`)(api, t, document);
  const list = new Element();
  const shown = () => list.children.filter((node) => node.className === "runitem-row")
    .map((row) => row.children[0].dataset.runId);
  const refresh = (options = {}) => module.refresh(list, { onSelect() {}, ...options });
  return { ...module, requests, box, list, shown, refresh };
}

const run = (index, topic = `topic ${index}`) => ({
  run_id: `run-${String(index).padStart(4, "0")}`, topic, state: "completed", started_at: "2026-01-01T00:00:00Z" });
const many = (count) => Array.from({ length: count }, (_, index) => run(index));

const scenarios = {
  async first_page() {
    const h = harness(many(130));
    await h.refresh();
    assert.deepEqual(h.requests, [{ limit: 50, offset: 0 }], "The first page is the request it always was");
    assert.equal(h.shown().length, 50);
    const more = h.list.children.at(-1);
    assert.equal(more.className, "runlist__more");
    assert.equal(more.textContent, "runs_show_more");
    assert.equal(h.box.hidden, false);
    // Each click adds a page, in one request while one request can hold it.
    let changed = 0;
    await h.refresh({ onChange: () => { changed++; } });
    h.list.children.at(-1).listeners.click();
    assert.equal(changed, 1);
    h.requests.length = 0;
    await h.refresh();
    assert.deepEqual(h.requests, [{ limit: 100, offset: 0 }]);
    assert.equal(h.shown().length, 100);
    h.showMore();
    h.requests.length = 0;
    await h.refresh();
    assert.equal(h.shown().length, 130);
    assert.notEqual(h.list.children.at(-1).className, "runlist__more", "Nothing more to show at the end");
  },
  async beyond_one_request() {
    const h = harness(many(450));
    for (let i = 0; i < 6; i++) h.showMore();   // 350 wanted
    await h.refresh();
    assert.deepEqual(h.requests, [{ limit: 200, offset: 0 }, { limit: 150, offset: 200 }]);
    assert.equal(h.shown().length, 350);
  },
  async search() {
    const history = many(450);
    history[7] = run(7, "Hyperloop for freight");
    history[430] = run(430, "a much older HYPERLOOP study");
    const h = harness(history);
    h.setQuery("  hyperloop ");
    await h.refresh();
    // The whole history is loaded and filtered here; the words are never sent.
    assert.deepEqual(h.requests, [{ limit: 200, offset: 0 }, { limit: 200, offset: 200 }, { limit: 200, offset: 400 }]);
    assert.ok(!JSON.stringify(h.requests).toLowerCase().includes("hyperloop"));
    assert.deepEqual(h.shown(), ["run-0007", "run-0430"], "An old run is found, case ignored");
    assert.equal(h.list.children.some((node) => node.className === "runlist__more"), false);
    h.setQuery("nothing like this");
    await h.refresh();
    assert.equal(h.list.children.length, 1);
    assert.equal(h.list.children[0].textContent, "runs_no_match");
    assert.equal(h.box.hidden, false, "The box stays while a search has no result, or it could not be cleared");
    // Clearing the box goes back to where the rail was.
    h.setQuery("");
    h.requests.length = 0;
    await h.refresh();
    assert.deepEqual(h.requests, [{ limit: 50, offset: 0 }]);
    assert.equal(h.shown().length, 50);
  },
  async capped() {
    const h = harness(many(1300));
    h.setQuery("topic 12");
    await h.refresh();
    assert.equal(h.requests.length, 5, "A search loads at most a thousand runs");
    assert.equal(h.requests.at(-1).offset, 800);
    const note = h.list.children.at(-1);
    assert.equal(note.className, "runlist__note");
    assert.equal(note.textContent, "runs_search_capped", "A search that did not reach the whole history says so");
  },
  async short_history() {
    const h = harness(many(5));
    await h.refresh();
    assert.equal(h.box.hidden, true, "A handful of runs needs no search box");
    assert.equal(h.shown().length, 5);
    assert.equal(h.list.children.some((node) => node.className === "runlist__more"), false);
    const empty = harness([]);
    await empty.refresh();
    assert.equal(empty.list.children[0].textContent, "no_runs");
  },
  async shifting() {
    // A run starts between two requests and moves every later one down a place.
    const history = many(260);
    const h = harness(history);
    const original = h.requests;
    let calls = 0;
    const real = h.refresh;
    for (let i = 0; i < 5; i++) h.showMore();   // 300 wanted
    const api = { listRuns: async (limit, offset = 0) => {
      original.push({ limit, offset });
      if (calls++ === 1) history.unshift(run(9999, "started just now"));
      return { runs: history.slice(offset, offset + limit), total: history.length };
    } };
    const document = { createElement: () => new Element(), querySelector: () => null };
    const module = new Function("api", "t", "document", `${source}; return { refresh, showMore };`)(api, (key) => key, document);
    for (let i = 0; i < 5; i++) module.showMore();
    await module.refresh(h.list, { onSelect() {} });
    const ids = h.shown();
    assert.equal(new Set(ids).size, ids.length, "No run is listed twice");
    void real;
  },
  async reset() {
    const h = harness(many(130));
    h.showMore(); h.setQuery("topic 1");
    h.resetView();
    await h.refresh();
    assert.deepEqual(h.requests, [{ limit: 50, offset: 0 }], "A new identity starts from the first page, unfiltered");
    assert.equal(h.matches({ topic: "Hyperloop", owner_label: "for-alice", run_id: "r1" }, "alice"), true);
    assert.equal(h.matches({ topic: null, run_id: "r1" }, "zzz"), false);
  },
};
assert.ok(scenarios[process.argv[2]], "Unknown scenario");
await scenarios[process.argv[2]]();
console.log(`PASS ${process.argv[2]}`);
