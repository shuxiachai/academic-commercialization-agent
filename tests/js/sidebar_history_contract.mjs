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

function harness(history, words = null) {
  const requests = [];
  const box = new Element();
  box.hidden = true;
  const api = { listRuns: async (limit = 50, offset = 0) => {
    requests.push({ limit, offset });
    return { runs: history.slice(offset, offset + limit), total: history.length };
  } };
  const document = { createElement: () => new Element(), querySelector: (selector) => (selector === "#run-search" ? box : null) };
  const t = (key) => (words && Object.hasOwn(words, key) ? words[key] : key);
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
  // Every row's delete button was named "Delete": a screen reader's list of
  // controls held one per run and nothing to tell them apart (2026-11-20).
  async delete_names() {
    const words = { delete_run: "Delete", delete_run_named: "Delete: {topic}", run_state_failed: "Failed",
                    run_earlier_row: "{state} after {duration}" };
    const long = "solid-state lithium-metal batteries for electric aircraft with a very long topic indeed";
    const parent = { ...run(1, "sodium-ion storage"), state: "failed", duration: "25m 31s" };
    const child = { ...run(3, "sodium-ion storage"), resumed_from: parent.run_id };
    const h = harness([child, { ...run(2, long), state: "failed" }, { ...run(4, ""), state: "completed" }, parent], words);
    await h.refresh({ onDelete() {} });
    const flat = (node) => [node, ...(node.children ?? []).flatMap(flat)];
    const buttons = flat(h.list).filter((node) => node.className === "runitem__delete icon-btn");
    const names = buttons.map((node) => node.attributes["aria-label"]);
    assert.deepEqual(names, [
      "Delete: sodium-ion storage",
      "Delete: sodium-ion storage — Failed after 25m 31s",
      `Delete: ${long.slice(0, 59).trimEnd()}…`,
      "Delete: run-0004",
    ], "the topic says which run; an earlier attempt also says how it ended; a long topic is cut");
    assert.equal(new Set(names).size, names.length, "no two buttons share a name");
    assert.deepEqual(buttons.map((node) => node.title), names);
  },

  // ── Before the history has answered ────────────────────────────────
  // A signed-in reader with seven runs was shown "No runs yet" for about a
  // second on every visit (production, 2026-11-27): the page's own markup
  // said so until the list arrived. Nothing may say "no runs" before the
  // server has.
  async loading_until_answered() {
    let answer;
    const requests = [];
    const m = build({ listRuns: (limit = 50, offset = 0) => {
      requests.push({ limit, offset });
      return new Promise((resolve) => { answer = resolve; });
    } });
    assert.equal(typeof m.loading, "function", "sidebar.js paints a state for a history not read yet");
    const list = new Element();
    m.loading(list);
    assert.equal(list.dataset.state, "loading");
    const busy = list.children[0];
    assert.equal(busy.className, "runlist__loading");
    assert.equal(busy.attributes?.role, "status");
    assert.equal(busy.attributes?.["aria-busy"], "true");
    assert.equal(flat(busy).find((node) => node.className === "visually-hidden")?.textContent, "runs_loading",
      "Said to a screen reader, in the interface's words");
    const reading = m.refresh(list, { onSelect() {} });
    await tick();
    assert.deepEqual(requests, [{ limit: 50, offset: 0 }]);
    assert.equal(list.dataset.state, "loading", "Still asking: still loading");
    assert.ok(!flat(list).some((node) => node.textContent === "no_runs"), "Never an empty history before the answer");
    answer({ runs: [], total: 0 });
    await reading;
    assert.equal(list.dataset.state, "shown");
    assert.equal(list.children[0].textContent, "no_runs", "A history that is empty says so once the server has");
  },
  // A list that cannot be read says so, with a way to ask again. Until now a
  // failed read kept whatever was there, which before the first answer would
  // be the loading rows: a list loading for ever.
  async first_read_fails() {
    let fail = true;
    const m = build({ listRuns: async () => {
      if (fail) throw Object.assign(new Error("Service Unavailable"), { status: 503 });
      return { runs: [run(1)], total: 1 };
    } });
    const list = new Element();
    m.loading?.(list);
    let asked = 0;
    const options = { onSelect() {}, onChange: () => { asked++; } };
    assert.equal(await m.refresh(list, options), null);
    assert.equal(list.dataset.state, "failed", "An unread history is said to be unread, not left loading");
    assert.equal(list.children.length, 1);
    const note = list.children[0];
    assert.equal(note.className, "runlist__empty runlist__failed");
    assert.equal(note.attributes?.role, "status");
    assert.equal(note.children[0].textContent, "runs_read_failed");
    assert.ok(!flat(list).some((node) => node.textContent === "no_runs"), "Not read is not empty");
    const retry = note.children[1];
    assert.equal(retry.className, "runlist__retry");
    assert.equal(retry.textContent, "runs_retry");
    retry.listeners.click();
    assert.equal(asked, 1, "The button asks the page for the list again");
    fail = false;
    await m.refresh(list, options);
    assert.equal(list.dataset.state, "shown");
    assert.equal(list.children.filter((node) => node.className === "runitem-row").length, 1);
    // A list already drawn keeps its rows when a later read fails: an empty
    // rail would read as "your runs are gone".
    fail = true;
    await m.refresh(list, options);
    assert.equal(list.dataset.state, "shown");
    assert.equal(list.children.filter((node) => node.className === "runitem-row").length, 1);
    // A late failure that belongs to an older view paints nothing.
    const fresh = new Element();
    m.loading(fresh);
    await m.refresh(fresh, { ...options, isCurrent: () => false });
    assert.equal(fresh.dataset.state, "loading");
  },
  // Asked while the boot's access check is still out (app.js startBootReads),
  // and used by the first refresh only for the identity it was asked with.
  async prefetched_first_page() {
    const requests = [];
    const who = { session: "token-A", code: null };
    let failing = false;
    const m = build({
      listRuns: async (limit = 50, offset = 0) => {
        requests.push({ limit, offset, session: who.session });
        if (failing) throw Object.assign(new Error("Bad Gateway"), { status: 502 });
        return { runs: [run(1, who.session)], total: 1 };
      },
      getSessionToken: () => who.session,
      getAccessCode: () => who.code,
    });
    assert.equal(typeof m.prefetch, "function", "sidebar.js can ask for the first page before it is drawn");
    m.prefetch();
    assert.deepEqual(requests, [{ limit: 50, offset: 0, session: "token-A" }], "Asked at once, for the page the rail shows first");
    const list = new Element();
    await m.refresh(list, { onSelect() {} });
    assert.equal(requests.length, 1, "The first refresh draws that reply instead of asking again");
    assert.deepEqual(list.children.filter((node) => node.className === "runitem-row")
      .map((row) => row.children[0].dataset.runId), ["run-0001"]);
    await m.refresh(list, { onSelect() {} });
    assert.equal(requests.length, 2, "Used once; the next refresh asks as before");
    // Another identity by the time the rail is drawn: the early reply is not theirs.
    m.prefetch();
    who.session = "token-B";
    await m.refresh(list, { onSelect() {} });
    assert.deepEqual(requests.slice(-2).map((r) => r.session), ["token-A", "token-B"]);
    // Nor is it when a code is stored or removed in between.
    m.prefetch();
    who.code = "code";
    await m.refresh(list, { onSelect() {} });
    assert.equal(requests.length, 6);
    who.code = null;
    // Forgotten (the boot stopped at the sign-in card): asked again afterwards.
    m.prefetch();
    m.forgetPrefetch();
    await m.refresh(list, { onSelect() {} });
    assert.equal(requests.length, 8);
    // A search wants more than the first page; the early reply is not used for it.
    m.prefetch();
    m.setQuery("token");
    await m.refresh(list, { onSelect() {} });
    assert.equal(requests.length, 10);
    m.setQuery("");
    // An early read that failed is a failed first read, said as one.
    failing = true;
    m.prefetch();
    const fresh = new Element();
    m.loading(fresh);
    await m.refresh(fresh, { onSelect() {} });
    assert.equal(requests.length, 11, "Not asked twice for one refresh");
    assert.equal(fresh.dataset.state, "failed");
  },
};

// The new scenarios build the module themselves, naming only what exists, so
// that one missing export fails its scenario by assertion, not the file.
function build(api) {
  const box = new Element();
  box.hidden = true;
  const document = { createElement: () => new Element(), querySelector: (selector) => (selector === "#run-search" ? box : null) };
  const names = ["render", "refresh", "setQuery", "resetView", "loading", "prefetch", "forgetPrefetch"];
  return new Function("api", "t", "document",
    `${source}; return { ${names.map((name) => `${name}: typeof ${name} === "function" ? ${name} : undefined`).join(", ")} };`,
  )({ getSessionToken: () => null, getAccessCode: () => null, ...api }, (key) => key, document);
}
function flat(node) { return [node, ...(node.children ?? []).flatMap(flat)]; }
const tick = () => new Promise((resolve) => setImmediate(resolve));
assert.ok(scenarios[process.argv[2]], "Unknown scenario");
await scenarios[process.argv[2]]();
console.log(`PASS ${process.argv[2]}`);
