// Independent behavioral harness: execute only the new shipped script, no HTTP.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const fixtures = JSON.parse(fs.readFileSync(0, "utf8"));
const root = new URL("../../", import.meta.url);
const source = fs.readFileSync(new URL("web/saved-source-lab/app.js", root), "utf8");
const html = fs.readFileSync(new URL("web/saved-source-lab/index.html", root), "utf8");
const clone = value => structuredClone(value);
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

function harness() {
  const forbidden = [];
  const deny = name => () => { forbidden.push(name); throw new Error(`Forbidden ${name}`); };
  class Element {
    constructor(tag = "div") {
      this.tagName = tag.toUpperCase(); this.value = ""; this.disabled = false;
      this.hidden = true; this.dataset = {}; this.children = []; this.listeners = {}; this.attributes = {};
      this._text = "";
    }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
    set innerHTML(_) { deny("innerHTML")(); }
    set outerHTML(_) { deny("outerHTML")(); }
    set href(_) { deny("href")(); }
    insertAdjacentHTML() { deny("insertAdjacentHTML")(); }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this._text = ""; this.children = nodes; }
    setAttribute(name, value) { this.attributes[name] = value; }
    focus() {}
    addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
    async dispatch(name) {
      await Promise.all((this.listeners[name] ?? []).map(fn => fn({ preventDefault() {} })));
    }
  }
  const elements = Object.fromEntries([...html.matchAll(/<([\w-]+)[^>]*\bid="([^"]+)"/g)]
    .map(([, tag, id]) => [id, new Element(tag)]));
  const calls = [];
  const context = {
    document: {
      getElementById(id) { assert(elements[id], `Missing real HTML element ${id}`); return elements[id]; },
      createElement(tag) { assert(["dt", "dd"].includes(tag), `Unexpected element ${tag}`); return new Element(tag); },
    },
    fetch(url, options) {
      const pending = deferred(); calls.push({ url, options, ...pending }); return pending.promise;
    },
    setTimeout: deny("timer"), setInterval: deny("poll"),
    XMLHttpRequest: deny("xhr"), WebSocket: deny("websocket"),
    navigator: { sendBeacon: deny("telemetry") },
  };
  for (const name of ["localStorage", "sessionStorage", "indexedDB"]) {
    Object.defineProperty(context, name, { get: deny(name) });
  }
  context.window = context;
  vm.runInNewContext(source, context, { filename: "saved-source-lab/app.js" });
  const el = id => elements[id];
  assert.equal(calls.length, 0, "No automatic request on boot");
  el("run-id").value = fixtures.run_id;
  el("question").value = " \nLocate 前🙂\t ";
  const submit = () => el("locator-form").dispatch("submit");
  async function deliver(payload, status = 200) {
    const pending = submit();
    calls.at(-1).resolve({ status, json: async () => payload });
    await pending;
    assert.deepEqual(forbidden, []);
  }
  function empty() {
    assert.equal(el("result").hidden, true, "Stale/malformed result must be hidden");
    assert.equal(el("saved-text").textContent, "", "Stale text must be erased, not only hidden");
    assert.equal(el("source-metadata").children.length, 0);
  }
  return { el, calls, submit, deliver, empty, forbidden };
}

async function domain() {
  for (const name of ["excerpt", "missing_text", "empty_text", "blank_text", "declined", "refused", "out_of_scope", "no_sources", "budget", "partial"]) {
    const h = harness(), payload = fixtures[name], r = payload.result;
    await h.deliver(payload);
    assert.equal(h.el("result").hidden, false, name);
    assert(h.el("result-state").textContent.endsWith(`· ${r.state}`), name);
    assert.equal(h.el("saved-text").textContent, r.saved_text?.text ?? "", "Whole exact saved text");
    assert.equal(h.el("saved-text").tagName, "PRE");
    assert.equal(h.el("saved-text").hidden, r.saved_text === null);
    assert.equal(h.el("saved-text").children.length, 0, "Text, never interpreted nodes");
    const c = r.catalog;
    assert(h.el("catalog-coverage").textContent.includes(`${c.returned_count} / 共 ${c.total_count}`));
    assert(h.el("catalog-coverage").textContent.includes(`省略 ${c.omitted_count}`));
    assert(h.el("catalog-coverage").textContent.includes(`标题截短 ${c.title_truncation_count}`));
    assert(h.el("catalog-coverage").textContent.includes(c.coverage));
    assert(h.el("semantic-status").textContent.includes("semantic_support: not_assessed"));
    assert(h.el("semantic-status").textContent.includes("selection_relevance: not_assessed"));
    if (r.source) {
      const values = h.el("source-metadata").children.filter(el => el.tagName === "DD").map(el => el.textContent);
      for (const key of ["source_id", "group", "title", "publisher", "source_type", "url", "published_date", "accessed_date", "origin", "stored_length"]) {
        assert(values.includes(String(r.source[key])), key);
      }
      assert(values.includes("未保存（null）"));
    }
    const call = h.calls[0];
    assert.equal(call.url, `/api/runs/${fixtures.run_id}/saved-source-location`);
    assert.equal(call.options.method, "POST");
    assert.deepEqual(JSON.parse(call.options.body), { question: " \nLocate 前🙂\t " });
    assert.deepEqual(Object.keys(call.options.headers), ["Content-Type"]);
    assert.equal(call.options.credentials, "omit");
    assert.equal(call.options.cache, "no-store");
    assert.equal(call.options.redirect, "error");
    assert.equal(h.calls.length, 1);
  }
  const nullable = clone(fixtures.excerpt);
  for (const key of ["url", "doi", "published_date"]) nullable.result.source[key] = null;
  const h = harness(); await h.deliver(nullable);
  assert.equal(h.el("result").hidden, false, "Nullable metadata is valid, not missing structure");
}

async function malformed() {
  const variants = [null, [], {}, "{}", 1];
  const groups = [[], ["result"], ["result", "catalog"], ["result", "source"], ["result", "saved_text"]];
  const at = (value, path) => path.reduce((node, key) => node[key], value);
  for (const path of groups) {
    for (const key of Object.keys(at(fixtures.excerpt, path))) {
      const missing = clone(fixtures.excerpt);
      delete at(missing, path)[key]; variants.push(missing);
      const nullableMetadata = path.join(".") === "result.source" && ["url", "doi", "published_date"].includes(key);
      if (at(fixtures.excerpt, path)[key] !== null && !nullableMetadata) {
        const nulled = clone(fixtures.excerpt); at(nulled, path)[key] = null; variants.push(nulled);
      }
    }
    const extra = clone(fixtures.excerpt); at(extra, path).extra = "untrusted"; variants.push(extra);
  }
  const edits = [
    [["schema_version"], true], [["selector_mode"], "native"], [["billing_integration"], "free"],
    [["result", "state"], "missing_text"], [["result", "reason"], "__proto__"], [["result", "reason"], ["saved_text"]],
    [["result", "semantic_support"], "supported"], [["result", "selection_relevance"], true],
    [["result", "callback_entries"], true], [["result", "read_completed"], "1"],
    [["result", "callback_bytes"], 2 ** 53], [["result", "callback_bytes"], 0],
    [["result", "catalog", "total_count"], -1], [["result", "catalog", "returned_count"], 1.1],
    [["result", "catalog", "coverage"], "partial"], [["result", "catalog", "omitted_count"], 1],
    [["result", "catalog", "catalog_hash"], "not-a-hash"], [["result", "catalog", "title_truncation_count"], 2],
    [["result", "source", "stored_length"], "1500"], [["result", "source", "group"], "patent"], [["result", "source", "group"], ["academic"]],
    [["result", "source", "url"], {}], [["result", "source", "published_date"], 2026],
    [["result", "source", "title"], ""], [["result", "source", "source_id"], "A0"],
    [["result", "source", "summary_hash"], "z".repeat(64)],
    [["result", "saved_text", "window_truncated"], 0], [["result", "saved_text", "window_truncated"], "false"],
    [["result", "saved_text", "window_truncated"], true], [["result", "saved_text", "start"], false],
    [["result", "saved_text", "end"], 1499], [["result", "saved_text", "end"], true],
    [["result", "saved_text", "text"], "x".repeat(1501)], [["result", "saved_text", "text"], "clipped"],
    [["result", "saved_text", "text_scope"], "full_paper"],
  ];
  for (const [path, value] of edits) {
    const malformed = clone(fixtures.excerpt); at(malformed, path.slice(0, -1))[path.at(-1)] = value; variants.push(malformed);
  }
  for (const payload of variants) {
    const h = harness();
    await h.deliver(fixtures.excerpt); // A bad response must replace, not retain, a good one.
    await h.deliver(payload);
    h.empty();
    assert.equal(h.el("request-status").dataset.kind, "error", JSON.stringify(payload));
    assert.equal(h.calls.length, 2, "No retry on malformed data");
  }
}

async function inputs() {
  for (const invalid of ["", fixtures.run_id.toUpperCase(), `${fixtures.run_id}\n`, ` ${fixtures.run_id}`, "../private", fixtures.run_id + "a"]) {
    const h = harness(); h.el("run-id").value = invalid; await h.submit();
    assert.equal(h.calls.length, 0, invalid); h.empty();
  }
  for (const invalid of ["", " \r\n\t\u0085", "🙂".repeat(4097)]) {
    const h = harness(); h.el("question").value = invalid; await h.submit();
    assert.equal(h.calls.length, 0); h.empty();
  }
  const h = harness(); h.el("question").value = "🙂".repeat(4096);
  await h.deliver(fixtures.budget);
  assert.equal(JSON.parse(h.calls[0].options.body).question, "🙂".repeat(4096));
}

async function lifecycle() {
  for (const change of ["run-id", "question", "reset"]) {
    const h = harness(); await h.deliver(fixtures.excerpt);
    const pending = h.submit(); h.empty();
    assert.equal(h.el("locate").disabled, true);
    await h.submit(); assert.equal(h.calls.length, 2, "Double-click must not dispatch");
    if (change === "reset") await h.el("locator-form").dispatch("reset");
    else {
      const old = h.el(change).value; h.el(change).value = "changed";
      await h.el(change).dispatch("input");
      h.el(change).value = old; await h.el(change).dispatch("input"); // Even A -> B -> A invalidates.
    }
    h.empty();
    h.el("run-id").value = fixtures.run_id; h.el("question").value = "replacement";
    await h.submit(); assert.equal(h.calls.length, 2, "Reset/edit cannot release the request slot");
    h.calls[1].resolve({ status: 200, json: async () => fixtures.excerpt }); await pending;
    h.empty(); assert.equal(h.el("locate").disabled, false);
    assert.equal(h.calls.length, 2, "Settling must not submit the replacement automatically");
    await h.deliver(fixtures.missing_text);
    assert(h.el("result-state").textContent.endsWith("· missing_text"));
    assert.equal(h.calls.length, 3);
    h.el("question").value = "edited after success"; await h.el("question").dispatch("input"); h.empty();
  }
}

async function errors() {
  for (const [status, code] of [[404, "saved_source_missing"], [413, "body_too_large"], [422, "invalid_request"], [429, "locator_busy"], [502, "selector_contract_error"], [503, "selector_disabled"], [503, "locator_closing"], [503, "saved_source_unavailable"], [500, "surprise"]]) {
    const h = harness(); await h.deliver(fixtures.excerpt);
    await h.deliver({ detail: "PRIVATE_PATH_<img>", error_code: code }, status); h.empty();
    const message = h.el("request-status").textContent;
    assert(!message.includes("PRIVATE_PATH"));
    if (["locator_busy", "selector_disabled", "locator_closing"].includes(code)) assert(message.includes(code));
    assert.equal(h.el("request-status").dataset.kind, "error"); assert.equal(h.calls.length, 2);
  }
  for (const failure of ["network", "json", "stale_rejection"]) {
    const h = harness(); await h.deliver(fixtures.excerpt); const pending = h.submit(); h.empty();
    if (failure === "json") h.calls[1].resolve({ status: 200, json: async () => { throw new Error("PRIVATE"); } });
    else {
      if (failure === "stale_rejection") await h.el("locator-form").dispatch("reset");
      h.calls[1].reject(new Error("PRIVATE"));
    }
    await pending; h.empty(); assert(!h.el("request-status").textContent.includes("PRIVATE"));
    assert.equal(h.el("locate").disabled, false); assert.equal(h.calls.length, 2);
  }
}

async function json_wait() {
  const h = harness(), body = deferred(); const pending = h.submit();
  h.calls[0].resolve({ status: 200, json: () => body.promise });
  await Promise.resolve();
  await h.el("locator-form").dispatch("reset");
  h.el("run-id").value = fixtures.run_id; h.el("question").value = "new";
  await h.submit(); assert.equal(h.calls.length, 1);
  body.resolve(fixtures.excerpt); await pending; h.empty();
  assert.equal(h.el("locate").disabled, false);
}

const scenario = process.argv[2];
const scenarios = { domain, malformed, inputs, lifecycle, errors, json_wait };
assert(Object.hasOwn(scenarios, scenario));
await scenarios[scenario]();
process.stdout.write(JSON.stringify({ scenario, passed: true }));
