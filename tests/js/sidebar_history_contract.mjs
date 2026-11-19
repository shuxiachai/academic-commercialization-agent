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
  setAttribute(name, value) { (this.attributes ??= {})[name] = String(value); }
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
    `${source}; return { render, refresh, setQuery, showMore, resetView, matches, grouped };`)(api, t, document);
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
  // A run's state was a coloured dot and nothing else: no word for a screen
  // reader, none for a reader who cannot tell red from green.
  async states() {
    const states = ["running", "completed", "failed", "cancelled", "timeout"];
    const history = states.map((state, index) => ({ ...run(index, `topic ${state}`), state }));
    history.push({ ...run(9, "topic unknown"), state: "unknown" });
    history.push({ ...run(10, "topic owned"), state: "failed", owner_label: "team" });
    const h = harness(history);
    await h.refresh();
    const items = h.list.children.filter((node) => node.className === "runitem-row").map((row) => row.children[0]);
    assert.equal(items.length, history.length);
    const flat = (node) => [node, ...(node.children ?? []).flatMap(flat)];
    const part = (item, name) => flat(item).find((node) => node.className === name);
    for (const [index, state] of states.entries()) {
      const item = items[index];
      const dot = part(item, "runitem__state"), spoken = part(item, "visually-hidden");
      assert.equal(dot.dataset.state, state);
      assert.equal(dot.title, `run_state_${state}`, "The word, on the dot, for a pointer");
      assert.ok(spoken, `${state} has a word for a screen reader`);
      assert.equal(spoken.textContent, ` \u2014 run_state_${state}`, "After the topic, as the unknown state reads");
      assert.equal(item.children.at(-1), spoken, "Read after the topic");
      assert.equal(item.attributes?.["aria-label"], undefined, "The topic stays the button's own text");
      assert.equal(item.title, `topic ${state}`, "The tooltip stays the topic, which the rail cuts short");
    }
    // The state nobody could read keeps the sentence it already had, and gets no second word.
    const unknown = items[5];
    assert.equal(unknown.attributes["aria-label"], "topic unknown \u2014 run_state_unknown");
    assert.equal(part(unknown, "visually-hidden"), undefined);
    // An administrator's row carries the owner too; the word still comes last.
    const owned = items[6];
    assert.equal(part(owned, "runitem__owner").textContent, "team");
    assert.equal(owned.children.at(-1).textContent, " \u2014 run_state_failed");
  },
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
  // A resumed run and the run it continues were two rows with one name, one
  // failed and one completed, and nothing to say which led to which.
  async resumed() {
    const parent = { ...run(1, "sodium-ion storage"), state: "failed", duration: "25m 31s" };
    const child = { ...run(3, "sodium-ion storage"), resumed_from: parent.run_id, duration: "3m 48s" };
    const other = run(2, "something else");
    const h = harness([child, other, parent]);
    const opened = [];
    await h.refresh({ onSelect: (id) => opened.push(id), onDelete() {} });
    assert.deepEqual(h.shown(), [child.run_id, other.run_id], "The run that was continued has no row of its own");
    const [first, fold, second] = h.list.children.filter((node) => node.className !== "runlist__group");
    assert.equal(first.children[0].dataset.runId, child.run_id);
    assert.equal(fold.className, "runitem-earlier", "Directly under the run that continued it");
    assert.equal(second.children[0].dataset.runId, other.run_id);
    assert.equal(fold.open, false, "Folded: the newest run is the one to open");
    const [summary, row] = fold.children;
    assert.equal(summary.textContent, "runs_earlier_one");
    assert.equal(row.className, "runitem-row runitem-row--earlier");
    const item = row.children[0];
    assert.equal(item.dataset.runId, parent.run_id, "Still a row that opens the earlier run");
    const flat = (node) => [node, ...(node.children ?? []).flatMap(flat)];
    const label = flat(item).find((node) => node.className === "runitem__label");
    // Named by how it ended and how long it ran: its topic is the row above's.
    assert.equal(label.textContent, "run_earlier_row");
    assert.equal(flat(item).find((node) => node.className === "runitem__state").dataset.state, "failed");
    assert.equal(item.title, "sodium-ion storage", "The tooltip stays the topic");
    assert.ok(row.children[1], "It can still be deleted on its own");
    item.listeners.click();
    assert.deepEqual(opened, [parent.run_id]);
    // Opened from a link or the fold: the row on screen is never out of sight.
    const again = harness([child, other, parent]);
    await again.refresh({ activeId: parent.run_id });
    assert.equal(again.list.children.find((node) => node.className === "runitem-earlier").open, true);
    assert.equal(again.list.children.find((node) => node.className === "runitem-earlier")
      .children[1].children[0].attributes["aria-current"], "true");
  },
  async chains() {
    const h = harness([]);
    const ids = (entries) => entries.map(({ run: top, earlier }) => [top.run_id, earlier.map((older) => older.run_id)]);
    const r = (id, from) => ({ run_id: id, resumed_from: from ?? null });
    // A resume of a resume: one row, the two it continues under it, nearest first.
    assert.deepEqual(ids(h.grouped([r("c", "b"), r("b", "a"), r("a")])), [["c", ["b", "a"]]]);
    // The run it continues is on a page not loaded yet: nothing to fold, nothing lost.
    assert.deepEqual(ids(h.grouped([r("c", "gone"), r("x")])), [["c", []], ["x", []]]);
    // Resumed twice: the earlier run goes under the newest resume, and the older resume keeps its row.
    assert.deepEqual(ids(h.grouped([r("c2", "a"), r("c1", "a"), r("a")])), [["c2", ["a"]], ["c1", []]]);
    // Runs that are no resume are untouched, in the order given.
    assert.deepEqual(ids(h.grouped([r("z"), r("y"), r("x")])), [["z", []], ["y", []], ["x", []]]);
    // A record naming itself, or two naming each other, folds nothing twice and never loops.
    assert.deepEqual(ids(h.grouped([r("s", "s")])), [["s", []]]);
    assert.deepEqual(ids(h.grouped([r("p", "q"), r("q", "p")])), [["p", ["q"]]]);
    // More than one earlier run is counted in the fold's line.
    const three = [{ ...run(3), resumed_from: "run-0002" }, { ...run(2), resumed_from: "run-0001", state: "failed" },
                   { ...run(1), state: "failed" }];
    const drawn = harness(three);
    await drawn.refresh();
    const fold = drawn.list.children.find((node) => node.className === "runitem-earlier");
    assert.equal(fold.children[0].textContent, "runs_earlier_many");
    assert.equal(fold.children.length, 3);
    // A search still finds both: they share the topic, and the fold holds the earlier one.
    const searched = harness([{ ...run(3, "sodium"), resumed_from: "run-0001" }, run(2, "other"), { ...run(1, "sodium"), state: "failed" }]);
    searched.setQuery("sodium");
    await searched.refresh();
    assert.deepEqual(searched.shown(), ["run-0003"]);
    assert.ok(searched.list.children.find((node) => node.className === "runitem-earlier"));
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
