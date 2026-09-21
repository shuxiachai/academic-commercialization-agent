/* Execute shipped modules; only DOM/network/storage are controlled test doubles. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createHash, webcrypto } from "node:crypto";

const fixtures = JSON.parse(fs.readFileSync(0, "utf8"));
const root = new URL("../../", import.meta.url);
const read = path => fs.readFileSync(new URL(path, root), "utf8");
const modules = ["web/saved-source-receipts/result.js", "web/saved-source-receipts/app.js",
  "web/saved-source-usage/accounting.js", "web/saved-source-usage/app.js"];
const source = modules.map(path => read(path).replace(/^import[\s\S]*?;\r?\n/gm, "").replace(/^export /gm, "")).join("\n");
const html = read("web/saved-source-usage/index.html");
const storageName = "saved-source-usage:v1";
const sha = text => createHash("sha256").update(text).digest("hex");
const record = key => JSON.stringify({ version: 1, receipt_key: key });
const oldKey = () => `v1.${Math.floor(Date.now() / 1000)}.${"9".repeat(64)}`;
const response = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
let cases = 0;

function harness({ data = new Map(), fault = null } = {}) {
  const calls = [], forbidden = [], timers = new Map();
  let failure = fault;
  const deny = label => () => { forbidden.push(label); throw Error(label); };
  class Element {
    constructor(tag) { this.tagName = tag.toUpperCase(); this.value = ""; this.hidden = true; this.disabled = false;
      this.checked = false; this.dataset = {}; this.listeners = {}; this.children = []; this.attributes = {}; this._text = ""; }
    set textContent(v) { this._text = String(v); this.children = []; }
    get textContent() { return this._text + this.children.map(n => n.textContent).join(""); }
    set innerHTML(_) { deny("innerHTML")(); }
    set href(_) { deny("active URL")(); }
    replaceChildren(...nodes) { this._text = ""; this.children = nodes; }
    append(...nodes) { this.children.push(...nodes); }
    setAttribute(k, v) { this.attributes[k] = v; }
    focus() {}
    addEventListener(k, fn) { (this.listeners[k] ??= []).push(fn); }
    async dispatch(k) { await Promise.all((this.listeners[k] ?? []).map(fn => fn({ preventDefault() {} }))); }
  }
  const elements = Object.fromEntries([...html.matchAll(/<([\w-]+)[^>]*\bid="([^"]+)"/g)].map(([, tag, id]) => [id, new Element(tag)]));
  const storage = {
    getItem(k) { if (failure === "get") throw Error("denied"); return data.get(k) ?? null; },
    setItem(k, v) { if (failure === "set") throw Error("denied"); if (failure !== "lost_write") data.set(k, v); },
    removeItem(k) { if (failure === "remove") throw Error("denied"); if (failure !== "lost_remove") data.delete(k); },
  };
  const context = vm.createContext({ crypto: webcrypto, TextEncoder, TextDecoder, Uint8Array, AbortController,
    document: {
      documentElement: { dataset: { receiptContract: "saved_source_receipt_usage_v1" } },
      getElementById(id) { assert(elements[id], `Missing shipped DOM ${id}`); return elements[id]; },
      createElement(tag) { assert(["dt", "dd"].includes(tag)); return new Element(tag); },
    },
    sessionStorage: storage, addEventListener() {},
    fetch(url, options) { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; });
      calls.push({ url, options, resolve, reject, persisted: data.get(storageName) }); return promise; },
    setTimeout(fn, ms) { const id = timers.size + 1; timers.set(id, { fn, ms }); return id; }, clearTimeout(id) { timers.delete(id); },
    setInterval: deny("poll"), localStorage: { getItem: deny("localStorage") }, indexedDB: { open: deny("indexedDB") },
    navigator: { sendBeacon: deny("beacon") }, WebSocket: deny("websocket"), XMLHttpRequest: deny("xhr"),
  });
  vm.runInContext(source, context);
  assert.equal(calls.length, 0, "Refresh must not POST or auto-poll");
  assert.throws(() => context.startSavedSourceReceiptPage(), /already started/, "Single boot only");
  const el = id => elements[id];
  el("access-code").value = "synthetic-code"; el("run-id").value = fixtures.run_id; el("question").value = "same question";
  const submit = () => el("locator-form").dispatch("submit"), recover = () => el("recover").dispatch("click");
  const key = () => calls.at(-1)?.options.headers["Idempotency-Key"] ?? JSON.parse(data.get(storageName)).receipt_key;
  function payload() {
    const receiptKey = key();
    const receipt = { schema_version: 1, operation: "saved_source_location_v1", receipt_key_sha256: sha(receiptKey),
      state: "completed", run_id: fixtures.run_id, expires_at: Number(receiptKey.split(".")[1]) + 86400,
      admission_state: "admitted", provider_usage: "not_observed", provider_cost: "not_observed", error_code: null,
      delivery: "available", delivery_snapshot_reads: 0, delivery_source_reads: 0, result: structuredClone(fixtures.results.excerpt) };
    return { contract: "saved_source_receipt_usage_v1", receipt, accounting: {
      schema_version: 1, method_id: "saved_source_native_usage_v1", scope: "single_saved_source_selection",
      receipt_key_sha256: receipt.receipt_key_sha256, run_id: receipt.run_id, expires_at: receipt.expires_at,
      publication_state: "sealed", dispatch_state: "response_received", native_journal_state: "complete", model_matches_authorized: true,
      usage: { status: "reported_complete", prompt_tokens: 100, completion_tokens: 20, total_tokens: 120 },
      cost: { currency: "USD", status: "estimated", estimated_usd: "0.000126100", reservation_usd: "0.011149312",
        price_policy_id: "locator_qwen_frozen_rates_v1", invoice_status: "not_observed" }, fault_codes: [],
    } };
  }
  async function deliver(change = () => {}) { const work = submit(); assert.equal(calls.length, 1); const p = payload(); change(p);
    calls[0].resolve(response(p)); await work; assert.deepEqual(forbidden, []); return p; }
  function excerpt() { assert.equal(el("result").hidden, false); assert.equal(el("saved-text").textContent, fixtures.results.excerpt.saved_text.text);
    assert.equal(el("saved-text").children.length, 0); }
  function empty() { for (const id of ["result", "receipt", "accounting"]) assert.equal(el(id).hidden, true);
    assert.equal(el("saved-text").textContent, ""); assert.equal(el("accounting-facts").textContent, ""); }
  async function blocked() { const n = calls.length; await submit(); assert.equal(calls.length, n); assert.equal(el("locate").disabled, true); }
  async function ack() { el("risk").checked = true; await el("risk").dispatch("change"); await el("acknowledge").dispatch("click"); }
  return { el, calls, timers, context, data, submit, recover, key, payload, deliver, excerpt, empty, blocked, ack,
    fault: f => { failure = f; } };
}

async function accounting() {
  const good = harness(); const p = await good.deliver(); good.excerpt();
  assert.equal(good.el("accounting").hidden, false);
  assert.equal(good.el("accounting-cost").textContent, "estimated · USD 0.000126100");
  assert.deepEqual(JSON.parse(good.el("accounting-facts").textContent), p.accounting); cases++;
  const mutations = [p => { p.accounting = null; }, p => { delete p.accounting; }, p => { p.accounting.extra = "bad"; },
    p => { p.accounting.usage.prompt_tokens = true; }, p => { p.accounting.usage.total_tokens++; },
    p => { p.accounting.cost.estimated_usd = "0.00"; }, p => { p.accounting.cost.estimated_usd = "0.000000000"; },
    p => { p.accounting.cost.invoice_status = "paid"; }, p => { p.accounting.cost.reservation_usd = 0; },
    p => { p.accounting.fault_codes = ["<img src=x>"]; }, p => { p.accounting.publication_state = "pending"; },
    p => { p.accounting.cost.estimated_usd = "1e-7"; }, p => { p.accounting.cost.estimated_usd = "<script>x</script>"; },
    p => { p.accounting.model_matches_authorized = false; }, p => { p.accounting.extra = "x".repeat(5000); }];
  for (const field of Object.keys(p.accounting)) mutations.push(p => { delete p.accounting[field]; });
  for (const part of ["usage", "cost"]) for (const field of Object.keys(p.accounting[part])) mutations.push(p => { delete p.accounting[part][field]; });
  for (const change of mutations) {
    const h = harness(); await h.deliver(change); h.excerpt(); await h.blocked();
    assert(h.el("accounting-cost").textContent.includes("不可用"));
    assert(h.el("accounting-usage").textContent.includes("未知"));
    assert(!h.el("accounting-cost").textContent.includes("USD 0")); cases++;
  }
}
async function identity() {
  for (const field of ["receipt_key_sha256", "run_id", "expires_at"]) {
    const h = harness(); await h.deliver(p => { p.accounting[field] = field === "expires_at" ? p.accounting[field] + 1
      : field === "run_id" ? fixtures.run_id.slice(0, -32) + "f".repeat(32) : "0".repeat(64); });
    h.excerpt(); assert(h.el("accounting-facts").textContent.includes("binding_mismatch")); cases++;
  }
  for (const change of [p => { p.contract = "old"; }, p => { p.extra = null; }, p => { delete p.receipt; },
    p => { delete p.receipt.result; }, p => { p.receipt.receipt_key_sha256 = "0".repeat(64); },
    p => { p.receipt.extra = null; }]) {
    const h = harness(); await h.deliver(change); h.empty(); await h.blocked(); cases++;
  }
}
async function lifecycle() {
  const h = harness(), work = h.submit();
  assert.equal(h.calls[0].persisted, record(h.key()), "Persist before POST");
  assert.equal(h.calls[0].url, `/api/runs/${fixtures.run_id}/saved-source-usage`);
  assert.equal(h.calls[0].options.method, "POST"); assert.equal(h.calls[0].options.signal, undefined);
  h.calls[0].reject(Error("Lost actual upstream acknowledgement")); await work; h.empty(); await h.blocked();
  const reload = harness({ data: h.data }); assert.equal(reload.calls.length, 0); await reload.blocked();
  const lookup = reload.recover(); assert.equal(reload.calls[0].url, "/api/saved-source-usage-receipts");
  assert.equal(reload.calls[0].options.method, "GET"); assert.equal(reload.key(), h.key());
  assert.equal(reload.calls[0].options.body, undefined); assert.equal(reload.calls[0].options.redirect, "error");
  const first = reload.payload(); reload.calls[0].resolve(response(first)); await lookup; reload.excerpt();
  await reload.ack(); assert.equal(reload.data.size, 0); const next = reload.submit(); assert.equal(reload.calls.length, 2);
  assert.notEqual(reload.key(), h.key(), "Same question still has a distinct intent key");
  const second = reload.payload(); second.accounting.cost.reservation_usd = "0.099000000";
  reload.calls[1].resolve(response(second)); await next;
  assert.deepEqual(JSON.parse(reload.el("accounting-facts").textContent), second.accounting);
  assert.equal(reload.data.size, 1); assert.equal(JSON.parse(reload.data.get(storageName)).receipt_key, reload.key()); cases++;
}
async function storage() {
  for (const fault of ["get", "set", "lost_write"]) {
    const h = harness({ fault }); await h.submit(); assert.equal(h.calls.length, 0); h.empty(); await h.blocked(); cases++;
  }
  const corrupt = harness({ data: new Map([[storageName, "{bad"]]) }); await corrupt.blocked(); cases++;
  for (const fault of ["remove", "lost_remove"]) {
    const h = harness(); await h.deliver(); h.fault(fault); await h.ack(); await h.blocked(); cases++;
  }
}
async function late() {
  for (const field of ["access-code", "run-id", "question"]) {
    const h = harness(), work = h.submit(), p = h.payload();
    h.el(field).value += "newer"; await h.el(field).dispatch("input"); h.empty();
    h.calls[0].resolve(response(p)); await work; h.empty(); await h.blocked(); cases++;
  }
  const h = harness(); await h.deliver(); const work = h.recover(), p = h.payload();
  h.el("access-code").value = "new-code"; await h.el("access-code").dispatch("input");
  h.calls[1].resolve(response(p)); await work; h.empty(); await h.blocked(); cases++;
}
async function states() {
  for (const state of ["pending", "unknown", "failed"]) {
    const h = harness(); await h.deliver(p => {
      Object.assign(p.receipt, { state, result: null, delivery: "not_ready", error_code: state === "failed" ? "execution_unavailable" : null });
      p.accounting = h.context.unavailableAccounting(p.receipt);
    }); assert.equal(h.el("receipt").hidden, false); assert.equal(h.el("result").hidden, true);
    assert(h.el("accounting-usage").textContent.includes("未知")); await h.blocked(); cases++;
  }
  const h = harness(); await h.deliver(p => {
    p.accounting.usage = { status: "unknown", prompt_tokens: null, completion_tokens: null, total_tokens: null };
    p.accounting.cost.status = "unknown"; p.accounting.cost.estimated_usd = null;
  }); h.excerpt(); assert(h.el("accounting-usage").textContent.includes("未知"));
  assert(h.el("accounting-reservation").textContent.includes("0.011149312")); cases++;
  for (const error_code of ["receipt_not_found", "receipt_unavailable"]) {
    const fresh = harness({ data: new Map([[storageName, record(oldKey())]]) }), work = fresh.recover();
    fresh.calls[0].resolve(response({ detail: "Saved-source receipt request could not be completed.", error_code }, error_code === "receipt_not_found" ? 404 : 503));
    await work; fresh.empty(); await fresh.blocked(); cases++;
  }
}
async function bounds() {
  for (const raw of ["{bad", "x".repeat(131073), '{"contract":NaN}']) {
    const h = harness(), work = h.submit(); h.calls[0].resolve(new Response(raw, { headers: { "content-type": "application/json" } }));
    await work; h.empty(); await h.blocked(); cases++;
  }
  const h = harness({ data: new Map([[storageName, record(oldKey())]]) }), work = h.recover();
  for (const { fn, ms } of h.timers.values()) { assert.equal(ms, 12000); fn(); }
  await work; h.empty(); await h.blocked(); cases++;
}
async function actual() {
  const h = harness({ data: new Map([[storageName, record(fixtures.actual_key)]]) });
  const work = h.recover(); h.calls[0].resolve(response(fixtures.actual_reply)); await work;
  assert.equal(h.el("receipt").hidden, false);
  assert.equal(h.el("saved-text").textContent, fixtures.actual_reply.receipt.result?.saved_text?.text ?? "");
  assert.deepEqual(JSON.parse(h.el("accounting-facts").textContent), fixtures.actual_reply.accounting);
  assert.equal(h.el("saved-text").children.length, 0); await h.blocked(); cases++;
}
async function numeric_accounting() {
  // Preserve the numeric spelling in the HTTP bytes. JSON.stringify of a
  // pre-parsed object erases 1e0/1.0 and cannot detect this parser seam.
  for (const literal of ["0.0001261", "1e0", "1.0", "9007199254740992", "1e999"] ) {
    const h = harness(), work = h.submit();
    const raw = JSON.stringify(h.payload()).replace('"estimated_usd":"0.000126100"', `"estimated_usd":${literal}`);
    assert(raw.includes(`"estimated_usd":${literal}`));
    assert.throws(() => h.context.strictJSON(raw), /./, "Legacy parser has no accounting exemption");
    h.calls[0].resolve(new Response(raw, { headers: { "content-type": "application/json" } }));
    await work; h.excerpt();
    assert(h.el("accounting-cost").textContent.includes("不可用"));
    assert(h.el("accounting-facts").textContent.includes("accounting_unavailable"));
    await h.blocked(); cases++;
  }
  for (const change of [raw => raw.replace('"prompt_tokens":100', '"prompt_tokens":1e2'),
    raw => raw.replace('"accounting":{"schema_version":1', '"accounting":{"schema_version":1e0')]) {
    const h = harness(), work = h.submit(), raw = change(JSON.stringify(h.payload()));
    assert.throws(() => h.context.strictJSON(raw), /./);
    h.calls[0].resolve(new Response(raw, { headers: { "content-type": "application/json" } }));
    await work; h.excerpt();
    assert(h.el("accounting-facts").textContent.includes("accounting_unavailable"), "Numeric normalization must not manufacture valid accounting");
    await h.blocked(); cases++;
  }
}
async function numeric_boundaries() {
  // Receipt integer spelling remains strict even if accounting would degrade.
  for (const literal of ["1e0", "1.0", "0.5", "9007199254740992"]) {
    const h = harness(), work = h.submit();
    const raw = JSON.stringify(h.payload()).replace('"schema_version":1', `"schema_version":${literal}`)
      .replace('"estimated_usd":"0.000126100"', '"estimated_usd":0.0001261');
    assert.throws(() => h.context.strictJSON(raw), /./, "Legacy default parser remains strict");
    h.calls[0].resolve(new Response(raw, { headers: { "content-type": "application/json" } }));
    await work; h.empty(); await h.blocked(); cases++;
  }
  const mutations = [
    raw => raw.replace('"estimated_usd":"0.000126100"', '"estimated_usd":1e0,"estimated_usd":1e0'),
    raw => raw.replace('"contract":"saved_source_receipt_usage_v1"', '"contract":"saved_source_receipt_usage_v1","contract":"saved_source_receipt_usage_v1"'),
    raw => raw.replace('"schema_version":1', '"schema_version":1,"schema_version":1'),
    raw => ' '.repeat(128 * 1024) + raw,
    raw => raw.replace('"estimated_usd":"0.000126100"', `"estimated_usd":${'['.repeat(30)}1e0${']'.repeat(30)}`),
    ...["01", "+1", "1.", "1e+", "NaN", "Infinity"].map(value => raw => raw.replace('"estimated_usd":"0.000126100"', `"estimated_usd":${value}`)),
  ];
  for (const mutate of mutations) {
    const h = harness(), work = h.submit(), raw = mutate(JSON.stringify(h.payload()));
    h.calls[0].resolve(new Response(raw, { headers: { "content-type": "application/json" } }));
    await work; h.empty(); await h.blocked(); cases++;
  }
}
await ({ accounting, identity, lifecycle, storage, late, states, bounds, actual, numeric_accounting, numeric_boundaries })[process.argv[2]]();
console.log(JSON.stringify({ passed: true, cases }));
