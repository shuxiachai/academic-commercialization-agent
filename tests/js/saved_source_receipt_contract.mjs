/* Exercise the shipped two-file client. All HTTP is a local controlled stream. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createHash, webcrypto } from "node:crypto";

const fixtures = JSON.parse(fs.readFileSync(0, "utf8"));
const root = new URL("../../", import.meta.url);
const resultSource = fs.readFileSync(new URL("web/saved-source-receipts/result.js", root), "utf8");
const appSource = fs.readFileSync(new URL("web/saved-source-receipts/app.js", root), "utf8");
const html = fs.readFileSync(new URL("web/saved-source-receipts/index.html", root), "utf8");
const name = "saved-source-receipts:v1";
const sha = text => createHash("sha256").update(text).digest("hex");
const clone = structuredClone;
let cases = 0;
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const storedKey = () => `v1.${Math.floor(Date.now() / 1000)}.${"9".repeat(64)}`;
const record = key => JSON.stringify({ version: 1, receipt_key: key });
const error = error_code => ({ detail: "Saved-source receipt request could not be completed.", error_code });
const response = (payload, status = 200, headers = {}) => new Response(JSON.stringify(payload), {
  status, headers: { "content-type": "application/json", ...headers },
});
const tick = () => new Promise(resolve => setImmediate(resolve));

function harness({ data = new Map(), fault = null } = {}) {
  const forbidden = [], calls = [], timers = new Map();
  let activeFault = fault, nextTimer = 0;
  const deny = label => () => { forbidden.push(label); throw Error(`Forbidden ${label}`); };
  class Element {
    constructor(tag) {
      this.tagName = tag.toUpperCase(); this.value = ""; this.hidden = true;
      this.disabled = false; this.checked = false; this.dataset = {}; this.children = [];
      this.listeners = {}; this.attributes = {}; this._text = "";
    }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
    set innerHTML(_) { deny("innerHTML")(); }
    set outerHTML(_) { deny("outerHTML")(); }
    set href(_) { deny("active URL")(); }
    insertAdjacentHTML() { deny("HTML")(); }
    replaceChildren(...nodes) { this._text = ""; this.children = nodes; }
    append(...nodes) { this.children.push(...nodes); }
    setAttribute(key, value) { this.attributes[key] = value; }
    focus() {}
    addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); }
    async dispatch(type) { await Promise.all((this.listeners[type] ?? []).map(fn => fn({ preventDefault() {} }))); }
  }
  const elements = Object.fromEntries([...html.matchAll(/<([\w-]+)[^>]*\bid="([^"]+)"/g)]
    .map(([, tag, id]) => [id, new Element(tag)]));
  const storage = {
    getItem(key) { if (activeFault === "get") throw Error("denied"); return data.get(key) ?? null; },
    setItem(key, value) {
      if (activeFault === "set") throw Error("denied");
      if (activeFault !== "lost_write") data.set(key, value);
      if (activeFault === "wrong_write") data.set(key, record(storedKey()));
    },
    removeItem(key) {
      if (activeFault === "remove") throw Error("denied");
      if (activeFault !== "lost_remove") data.delete(key);
    },
  };
  const context = vm.createContext({
    crypto: webcrypto, TextEncoder, TextDecoder, Uint8Array, AbortController,
    document: {
      getElementById(id) { assert(elements[id], `Missing real element ${id}`); return elements[id]; },
      createElement(tag) { assert(["dt", "dd"].includes(tag)); return new Element(tag); },
    },
    fetch(url, options) {
      const pending = deferred();
      // Capture observations outside the app's catch boundary; assert later.
      calls.push({ url, options, persisted: data.get(name), ...pending });
      return pending.promise;
    },
    addEventListener() {},
    setTimeout(fn, ms) { timers.set(++nextTimer, { fn, ms }); return nextTimer; },
    clearTimeout(id) { timers.delete(id); },
    setInterval: deny("polling"), XMLHttpRequest: deny("xhr"), WebSocket: deny("websocket"),
    navigator: { sendBeacon: deny("telemetry") },
  });
  for (const key of ["localStorage", "indexedDB"]) Object.defineProperty(context, key, { get: deny(key) });
  Object.defineProperty(context, "sessionStorage", { get() {
    if (activeFault === "access") throw Error("denied");
    return storage;
  } });
  // Strip module syntax only; execute the shipped functions unchanged together.
  vm.runInContext(resultSource.replace(/^export /gm, "") + "\n" + appSource.replace(/^import \{[\s\S]*?from "\.\/result\.js";\n/m, ""), context);
  const el = id => elements[id];
  assert.equal(calls.length, 0, "Reload never automatically fetches");
  el("access-code").value = "fixture-code"; el("run-id").value = fixtures.run_id;
  el("question").value = " \nLocate 前🙂\t ";
  const submit = () => el("locator-form").dispatch("submit");
  const recover = () => el("recover").dispatch("click");
  const key = () => calls.at(-1)?.options.headers["Idempotency-Key"] ?? JSON.parse(data.get(name)).receipt_key;
  function payload(result = fixtures.results.excerpt) {
    const receipt = key();
    return {
      schema_version: 1, operation: "saved_source_location_v1", receipt_key_sha256: sha(receipt),
      state: "completed", run_id: fixtures.run_id, expires_at: Number(receipt.split(".")[1]) + 86400,
      admission_state: result.callback_entries ? "admitted" : "not_admitted",
      provider_usage: "not_observed", provider_cost: "not_observed", error_code: null,
      delivery: "available", delivery_snapshot_reads: 0, delivery_source_reads: 0, result: clone(result),
    };
  }
  async function deliver(result = fixtures.results.excerpt) {
    const pending = submit(); assert.equal(calls.length, 1);
    calls[0].resolve(response(payload(result))); await pending;
    assert.deepEqual(forbidden, []);
  }
  function empty() {
    assert.equal(el("result").hidden, true); assert.equal(el("receipt").hidden, true);
    assert.equal(el("saved-text").textContent, ""); assert.equal(el("source-metadata").children.length, 0);
  }
  async function cannotPost() {
    const count = calls.length, pending = submit();
    assert.equal(calls.length, count, "Unresolved or unacknowledged intent must never POST");
    await pending;
    assert.equal(el("locate").disabled, true);
  }
  async function risk() { el("risk").checked = true; await el("risk").dispatch("change"); }
  return { el, calls, data, timers, forbidden, submit, recover, deliver, payload, empty, key, risk, cannotPost,
    fault: value => { activeFault = value; }, ack: () => el("acknowledge").dispatch("click") };
}
function verifyPost(h) {
  const c = h.calls[0];
  assert.equal(c.persisted, record(c.options.headers["Idempotency-Key"]), "Receipt must persist BEFORE fetch");
  assert.match(c.options.headers["Idempotency-Key"], /^v1\.[0-9]{10}\.[0-9a-f]{64}$/);
  assert.equal(c.url, `/api/runs/${fixtures.run_id}/saved-source-location`);
  assert.equal(c.options.method, "POST"); assert.equal(c.options.credentials, "omit");
  assert.equal(c.options.cache, "no-store"); assert.equal(c.options.redirect, "error");
  assert.equal(Object.hasOwn(c.options, "signal"), false, "No POST timeout");
  assert.equal(JSON.parse(c.options.body).question, " \nLocate 前🙂\t ");
  assert.deepEqual(Object.keys(c.options.headers).sort(), ["Content-Type", "Idempotency-Key", "X-Access-Code"]);
  assert.equal(h.data.size, 1, "No credentials, question, result or run in storage");
}
async function domain() {
  for (const result of Object.values(fixtures.results)) {
    const h = harness(); await h.deliver(result); verifyPost(h);
    assert.equal(h.el("result").hidden, false, result.reason);
    assert.equal(h.el("saved-text").textContent, result.saved_text?.text ?? "");
    assert.equal(h.el("saved-text").tagName, "PRE"); assert.equal(h.el("saved-text").children.length, 0);
    assert(h.el("result-state").textContent.endsWith(`· ${result.state}`));
    assert(h.el("receipt-facts").textContent.includes('"state": "completed"'));
    assert(h.el("semantic-status").textContent.includes("semantic_support: not_assessed"));
    await h.cannotPost(); cases++;
  }
  for (const state of ["pending", "unknown", "failed"]) {
    const h = harness(), pending = h.submit(), p = h.payload();
    Object.assign(p, { state, result: null, delivery: "not_ready", error_code: state === "failed" ? "execution_unavailable" : null });
    h.calls[0].resolve(response(p)); await pending;
    assert.equal(h.el("receipt").hidden, false); assert.equal(h.el("result").hidden, true);
    await h.risk(); assert.equal(h.el("acknowledge").disabled, state !== "failed"); await h.cannotPost(); cases++;
  }
  for (const delivery of ["expired", "changed", "unavailable"]) {
    const h = harness(), pending = h.submit(), p = h.payload();
    Object.assign(p, { result: null, delivery, delivery_snapshot_reads: 1 });
    h.calls[0].resolve(response(p)); await pending;
    assert.equal(h.el("receipt").hidden, false); assert.equal(h.el("result").hidden, true); cases++;
  }
}
async function malformed() {
  const seed = harness(); const work = seed.submit(); const good = seed.payload();
  seed.calls[0].resolve(response(good)); await work;
  const variants = [];
  for (const path of [[], ["result"], ["result", "catalog"], ["result", "source"], ["result", "saved_text"]]) {
    const at = (p, route) => route.reduce((v, field) => v[field], p);
    for (const field of Object.keys(at(good, path))) {
      variants.push(p => { delete at(p, path)[field]; });
    }
    variants.push(p => { at(p, path).unexpected = "PRIVATE"; });
  }
  for (const [field, value] of Object.entries({ schema_version: true, operation: "run", receipt_key_sha256: "0".repeat(64),
    state: "accepted", run_id: fixtures.run_id + "\n", expires_at: true, admission_state: "paid", provider_cost: 0,
    provider_usage: "complete", error_code: "access_denied", delivery: "not_ready", delivery_source_reads: true,
    delivery_snapshot_reads: 2, result: null })) variants.push(p => { p[field] = value; });
  const edits = [
    [["result", "state"], "failed"], [["result", "reason"], "toString"], [["result", "callback_entries"], false],
    [["result", "callback_bytes"], 12289], [["result", "read_completed"], 0], [["result", "semantic_support"], "verified"],
    [["result", "catalog", "total_count"], 0], [["result", "catalog", "coverage"], "partial"],
    [["result", "catalog", "title_truncation_count"], 5], [["result", "source", "group"], "patent"],
    [["result", "source", "stored_length"], 1499], [["result", "source", "url"], {}],
    [["result", "source", "summary_hash"], "0".repeat(64)], [["result", "source", "title"], "\ud800"],
    [["result", "saved_text", "text_sha256"], "0".repeat(64)], [["result", "saved_text", "window_truncated"], 0],
    [["result", "saved_text", "start"], false], [["result", "saved_text", "end"], "1500"],
    [["result", "saved_text", "text"], "x".repeat(1500)], [["result", "saved_text", "text_scope"], "full_paper"],
  ];
  for (const [path, value] of edits) variants.push(p => { path.slice(0, -1).reduce((v, field) => v[field], p)[path.at(-1)] = value; });
  for (const code of ["saved_source_missing", "saved_source_unavailable", "concurrency_limit", "daily_quota_exceeded", "access_denied", "request_abandoned"]) {
    for (const admission of ["admitted", "unknown"]) variants.push(p => {
      Object.assign(p, { state: "failed", error_code: code, result: null, delivery: "not_ready", admission_state: admission });
    });
  }
  for (const mutate of variants) {
    const h = harness(); await h.deliver();
    const pending = h.recover(), p = h.payload(); mutate(p);
    h.calls.at(-1).resolve(response(p)); await pending;
    h.empty(); await h.risk(); assert.equal(h.el("acknowledge").disabled, true);
    await h.cannotPost(); assert(h.data.has(name)); cases++;
  }
  const h = harness(), pending = h.submit(), wrongRun = h.payload();
  wrongRun.run_id = fixtures.run_id.replace(/a/g, "b");
  h.calls[0].resolve(response(wrongRun)); await pending; h.empty(); await h.cannotPost(); cases++;
}
async function inputs() {
  const invalid = {
    "run-id": ["", "a".repeat(32), fixtures.run_id + "\n", fixtures.run_id.toUpperCase(), "../private"],
    question: ["", " \u0085\u001c\t", "🙂".repeat(4097), "\ud800"],
    "access-code": ["", " ", "\n", "code\r\nX-Foo: bar", "密码", "x".repeat(4097)],
  };
  for (const [field, values] of Object.entries(invalid)) for (const value of values) {
    const h = harness(); h.el(field).value = value; await h.submit();
    assert.equal(h.calls.length, 0); assert.equal(h.data.size, 0); cases++;
  }
  const h = harness(); h.el("question").value = "🙂".repeat(4096); h.el("access-code").value = "x".repeat(4096);
  await h.deliver(fixtures.results.budget); assert.equal(h.el("result").hidden, false); cases++;
}
async function lifecycle() {
  for (const change of ["run-id", "question", "access-code", "reset"]) for (const status of [200, 401]) {
    const h = harness(), pending = h.submit(), oldKey = h.key();
    if (change === "reset") await h.el("locator-form").dispatch("reset");
    else {
      const old = h.el(change).value;
      h.el(change).value = "changed"; await h.el(change).dispatch("input");
      h.el(change).value = old; await h.el(change).dispatch("input");
    }
    h.el("access-code").value = "newer-code";
    await h.cannotPost(); assert.equal(h.calls.length, 1);
    h.calls[0].resolve(response(status === 200 ? h.payload() : error("access_denied"), status)); await pending;
    h.empty(); assert.equal(h.el("access-code").value, "newer-code");
    assert.equal(h.data.get(name), record(oldKey)); await h.risk(); await h.ack(); await h.cannotPost(); cases++;
  }
  const h = harness(), body = deferred(), pending = h.submit();
  h.calls[0].resolve({ status: 200, headers: new Headers({ "content-type": "application/json" }),
    body: { getReader: () => ({ read: () => body.promise, releaseLock() {}, cancel: async () => {} }) } });
  await tick(); await h.el("locator-form").dispatch("reset");
  await h.cannotPost(); body.resolve({ done: true }); await pending;
  h.empty(); assert(h.data.has(name)); cases++;
}
async function storage() {
  for (const fault of ["access", "get", "set", "lost_write", "wrong_write"]) {
    const h = harness({ fault }); await h.submit(); assert.equal(h.calls.length, 0);
    h.fault(null); await h.submit(); assert.equal(h.calls.length, 0, "Known storage failure stays latched"); cases++;
  }
  for (const raw of ["", "{", "null", "{}", '[]', '{"version":1,"receipt_key":"bad"}',
    JSON.stringify({ version: 1, receipt_key: storedKey(), question: "private" }),
    `{"version":1,"version":1,"receipt_key":"${storedKey()}"}`]) {
    const h = harness({ data: new Map([[name, raw]]) }); await h.submit(); assert.equal(h.calls.length, 0);
    h.data.delete(name); await h.submit(); assert.equal(h.calls.length, 0); cases++;
  }
  for (const loss of ["missing", "changed", "get"]) {
    const h = harness(); await h.deliver();
    if (loss === "missing") h.data.delete(name);
    else if (loss === "changed") h.data.set(name, record(storedKey()));
    else h.fault("get");
    await h.risk(); await h.ack(); await h.cannotPost();
    const pending = h.recover(); h.calls.at(-1).resolve(response(h.payload())); await pending;
    assert.equal(h.el("result").hidden, false, "Memory key GET survives storage degradation");
    h.fault(null); await h.risk(); await h.ack(); await h.cannotPost(); cases++;
  }
}
async function recovery() {
  for (const outcome of ["network", "malformed", "pending", "unknown", "not_found"]) {
    const data = new Map(), before = harness({ data }), pending = before.submit(); verifyPost(before);
    const key = before.key();
    if (outcome === "network") before.calls[0].reject(Error("lost acknowledgement"));
    else if (outcome === "malformed") before.calls[0].resolve(response({}));
    else if (outcome === "not_found") before.calls[0].resolve(response(error("receipt_not_found"), 404));
    else before.calls[0].resolve(response({ ...before.payload(), state: outcome, result: null, delivery: "not_ready" }));
    await pending; await before.risk(); await before.ack(); await before.cannotPost();
    const after = harness({ data }); after.el("access-code").value = "";
    await after.recover(); assert.equal(after.calls.length, 0, "Fresh code is required after reload");
    await after.cannotPost();
    after.el("access-code").value = "fresh-fixture-code";
    const reading = after.recover(), call = after.calls[0];
    assert.equal(call.url, "/api/saved-source-receipts"); assert.equal(call.options.method, "GET");
    assert.equal(call.options.headers["Idempotency-Key"], key); assert.equal(Object.hasOwn(call.options, "body"), false);
    assert.equal(call.options.credentials, "omit"); assert.equal(call.options.cache, "no-store"); assert.equal(call.options.redirect, "error");
    call.resolve(response(after.payload())); await reading;
    assert.equal(after.el("saved-text").textContent, fixtures.results.excerpt.saved_text.text);
    assert(after.el("receipt-context").textContent.includes(fixtures.run_id));
    assert(after.el("receipt-context").textContent.includes("原始问题未保存"));
    assert.equal(after.data.get(name), record(key)); await after.cannotPost(); cases++;
  }
}
async function errors() {
  for (const [status, code] of [[400, "invalid_receipt_key"], [401, "access_denied"], [403, "origin_denied"],
    [404, "receipt_not_found"], [404, "not_found"], [405, "method_not_allowed"], [409, "receipt_conflict"],
    [413, "body_too_large"], [415, "unsupported_media_type"], [422, "invalid_request"], [429, "locator_busy"],
    [431, "headers_too_large"], ...["selector_disabled", "controller_closed", "receipt_capacity", "receipt_unavailable", "execution_unavailable", "request_abandoned"].map(c => [503, c])]) {
    const h = harness(), pending = h.submit(); h.calls[0].resolve(response(error(code), status)); await pending;
    h.empty(); assert(h.el("request-status").textContent.includes(code)); await h.risk(); await h.ack(); await h.cannotPost(); cases++;
  }
  for (const [status, payload] of [[410, { ...error("receipt_expired"), detail: "PRIVATE" }],
    [410, error("receipt_not_found")], [404, error("receipt_expired")], [500, error("receipt_expired")],
    [410, { ...error("receipt_expired"), extra: true }]]) {
    const h = harness(), pending = h.submit(); h.calls[0].resolve(response(payload, status)); await pending;
    h.empty(); assert(!h.el("request-status").textContent.includes("PRIVATE"));
    await h.risk(); await h.ack(); await h.cannotPost(); cases++;
  }
}
async function bounds() {
  const casesToRun = ["oversize", "utf8", "json", "duplicate", "type", "bom", "float", "exponent", "split", "lying_length", "boundary"];
  for (const kind of casesToRun) {
    const h = harness(), pending = h.submit(), payload = h.payload();
    let raw = JSON.stringify(payload), contentType = "application/json";
    if (kind === "oversize") raw = " ".repeat(128 * 1024) + raw;
    if (kind === "json") raw = raw.slice(0, -2);
    if (kind === "duplicate") raw = raw.replace('"schema_version":1', '"schema_version":1,"schema_version":1');
    if (kind === "float") raw = raw.replace('"schema_version":1', '"schema_version":1.0');
    if (kind === "exponent") raw = raw.replace('"schema_version":1', '"schema_version":1e0');
    if (kind === "type") contentType = "text/html";
    if (kind === "bom") raw = "\ufeff" + raw;
    if (kind === "boundary") raw += " ".repeat(128 * 1024 - Buffer.byteLength(raw));
    const bytes = kind === "utf8" ? Uint8Array.from([0xc3, 0x28]) : new TextEncoder().encode(raw);
    const stream = new ReadableStream({ start(controller) {
      if (kind === "split") for (let i = 0; i < bytes.length; i += 17) controller.enqueue(bytes.slice(i, i + 17));
      else controller.enqueue(bytes);
      controller.close();
    } });
    h.calls[0].resolve(new Response(stream, { headers: { "content-type": contentType, "content-length": "1" } }));
    await pending;
    if (["split", "lying_length", "boundary"].includes(kind)) assert.equal(h.el("result").hidden, false);
    else { h.empty(); await h.risk(); await h.ack(); }
    await h.cannotPost(); cases++;
  }
}
async function timeout() {
  for (const phase of ["headers", "body"]) {
    const h = harness({ data: new Map([[name, record(storedKey())]]) }), pending = h.recover();
    if (phase === "body") {
      h.calls[0].resolve(new Response(new ReadableStream({ start() {} }), { headers: { "content-type": "application/json" } }));
      await tick();
    }
    assert.equal(h.timers.size, 1); const timer = [...h.timers.values()][0]; assert.equal(timer.ms, 12000);
    timer.fn(); await pending; assert.equal(h.calls[0].options.signal.aborted, true);
    h.empty(); await h.risk(); await h.ack(); await h.cannotPost();
    assert.equal(h.calls.length, 1); assert.equal(h.timers.size, 0); cases++;
  }
}
async function acknowledge() {
  for (const observation of ["terminal", "expired"]) {
    const h = harness();
    if (observation === "terminal") await h.deliver();
    else { const pending = h.submit(); h.calls[0].resolve(response(error("receipt_expired"), 410)); await pending; }
    await h.ack(); assert(h.data.has(name), "Button without explicit checkbox cannot remove");
    await h.risk(); assert.equal(h.el("acknowledge").disabled, false); await h.ack();
    assert.equal(h.data.has(name), false); assert.equal(h.el("locate").disabled, false);
    assert.equal(h.calls.length, 1, "Acknowledging never automatically POSTs"); cases++;
  }
  for (const fault of ["remove", "lost_remove", "get"]) {
    const h = harness(); await h.deliver(); await h.risk(); h.fault(fault); await h.ack();
    h.fault(null); await h.cannotPost(); assert(h.data.has(name)); cases++;
  }
  const h = harness(); await h.deliver(); await h.risk();
  const pending = h.recover(); await h.ack(); assert(h.data.has(name));
  h.calls.at(-1).resolve(response({ ...h.payload(), state: "unknown", delivery: "not_ready", result: null })); await pending;
  await h.risk(); await h.ack(); await h.cannotPost(); cases++;
}
async function actual() {
  const h = harness(), pending = h.submit(), payload = clone(fixtures.actual_reply);
  payload.receipt_key_sha256 = sha(h.key()); payload.expires_at = Number(h.key().split(".")[1]) + 86400;
  h.calls[0].resolve(response(payload)); await pending;
  assert.equal(h.el("saved-text").textContent, payload.result.saved_text.text);
  assert.equal(h.el("receipt").hidden, false); assert.equal(h.el("result").hidden, false);
  assert.equal(Object.keys(JSON.parse(h.el("receipt-facts").textContent)).length, 13);
  await h.cannotPost(); cases++;
}
const scenario = process.argv[2];
const scenarios = { domain, malformed, inputs, lifecycle, storage, recovery, errors, bounds, timeout, acknowledge, actual };
assert(Object.hasOwn(scenarios, scenario));
await scenarios[scenario]();
process.stdout.write(JSON.stringify({ scenario, passed: true, cases }));
