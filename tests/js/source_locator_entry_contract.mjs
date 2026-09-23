/* Execute the exact server-projected modules, not a copied receipt algorithm. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createHash, webcrypto } from "node:crypto";

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const source = input.modules.map(s => s.replace(/^import[\s\S]*?;\r?\n/gm, "").replace(/^export /gm, "")).join("\n");
const storageName = "source-locator:v1";
const hash = text => createHash("sha256").update(text).digest("hex");
let assertions = 0;

function harness(enabled = "true", saved = new Map(), fragment = "") {
  const calls = [];
  class Element {
    constructor() { this.value = ""; this.checked = false; this.hidden = true; this.dataset = {}; this.listeners = {}; this.children = []; this._text = ""; }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text + this.children.map(c => c.textContent).join(""); }
    set innerHTML(_) { throw Error("Active HTML forbidden"); }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this._text = ""; this.children = nodes; }
    setAttribute() {}
    focus() {}
    addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); }
    async fire(name) { for (const callback of this.listeners[name] ?? []) await callback({ preventDefault() {} }); }
  }
  const elements = Object.fromEntries([...input.html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [id, new Element()]));
  const context = vm.createContext({
    document: { documentElement: { dataset: { receiptContract: "saved_source_receipt_usage_v1", executionAllowed: enabled } },
      getElementById: id => { assert(elements[id], `Missing DOM ${id}`); return elements[id]; }, createElement: () => new Element() },
    window: { location: { hash: fragment } }, crypto: webcrypto, TextEncoder, TextDecoder, Uint8Array, AbortController,
    sessionStorage: { getItem: k => saved.get(k) ?? null, setItem: (k, v) => saved.set(k, v), removeItem: k => saved.delete(k) },
    addEventListener() {}, setTimeout, clearTimeout,
    fetch: (url, options) => new Promise((resolve, reject) => calls.push({url, options, resolve, reject, persisted: saved.get(storageName)})),
  });
  vm.runInContext(source, context);
  assert.equal(calls.length, 0, "Page load never dispatches");
  const el = id => elements[id];
  el("access-code").value = "synthetic-code";
  el("question").value = "  Synthetic question 🙂  ";
  const initialRun = el("run-id").value;
  el("run-id").value = input.fixtures.run_id;
  return {el, calls, saved, initialRun, submit: () => el("locator-form").fire("submit"), recover: () => el("recover").fire("click")};
}

for (const enabled of ["false", "", "TRUE", undefined]) {
  const h = harness(enabled === undefined ? "unavailable" : enabled);
  h.el("locator-consent").checked = true;
  const denied = h.submit();
  assert.equal(h.calls.length, 0, "Disabled execution must not dispatch");
  assert.equal(h.saved.size, 0, "Disabled execution must not reserve local intent");
  await denied;
  assert.match(h.el("request-status").textContent, /关闭/); assertions++;
}
const h = harness();
const unconsented = h.submit();
assert.equal(h.calls.length, 0, "Consent must block before dispatch");
assert.equal(h.saved.size, 0, "Consent must block before local receipt persistence");
await unconsented;
assert.match(h.el("request-status").textContent, /确认/); assertions++;
for (const event of ["question", "run-id", "access-code", "reset"]) {
  h.el("locator-consent").checked = true;
  await h.el(event === "reset" ? "locator-form" : event).fire(event === "reset" ? "reset" : "input");
  assert.equal(h.el("locator-consent").checked, false); assertions++;
}
h.el("access-code").value = "synthetic-code";
h.el("run-id").value = input.fixtures.run_id;
h.el("question").value = "  Synthetic question 🙂  ";
h.el("locator-consent").checked = true;
const paid = h.submit();
assert.equal(h.calls.length, 1);
const post = h.calls[0], key = post.options.headers["Idempotency-Key"];
assert.equal(post.url, `/api/runs/${input.fixtures.run_id}/source-locator`);
assert.equal(post.options.headers["X-Source-Locator-Consent"], "question-catalog-v1");
assert.equal(post.persisted, JSON.stringify({version: 1, receipt_key: key}));
assert.deepEqual(JSON.parse(post.options.body), { question: "  Synthetic question 🙂  " });
post.reject(Error("Lost acknowledgement")); await paid;
assert.equal(h.el("locate").disabled, true); assertions++;

// New document, no transfer consent, execution disabled: authorized GET must
// still recover the existing receipt without another POST or model request.
const reload = harness("false", h.saved);
assert.equal(reload.calls.length, 0);
const work = reload.recover();
assert.equal(reload.calls.length, 1);
const get = reload.calls[0];
assert.equal(get.options.method, "GET"); assert.equal(get.url, "/api/source-locator/receipts");
assert.equal(get.options.headers["X-Source-Locator-Consent"], undefined);
assert.equal(get.options.headers["Idempotency-Key"], key);
const receipt = {schema_version:1, operation:"saved_source_location_v1", state:"completed", run_id:input.fixtures.run_id,
  expires_at:Number(key.split(".")[1])+86400, admission_state:"admitted", provider_usage:"not_observed", provider_cost:"not_observed",
  error_code:null, delivery:"available", delivery_snapshot_reads:1, delivery_source_reads:1,
  receipt_key_sha256:hash(key), result:input.fixtures.results.excerpt};
get.resolve(new Response(JSON.stringify({contract:"saved_source_receipt_usage_v1", receipt, accounting:null}), {
  status:200, headers:{"Content-Type":"application/json"},
}));
await work;
assert.equal(reload.el("saved-text").textContent, input.fixtures.results.excerpt.saved_text.text);
assert.match(reload.el("accounting-cost").textContent, /不可用/);
assert.equal(reload.calls.length, 1); assertions++;
assert.equal(harness("true", new Map(), "#"+input.fixtures.run_id).initialRun, input.fixtures.run_id);
assert.equal(harness("true", new Map(), "#../invalid").initialRun, ""); assertions++;
console.log(JSON.stringify({passed:true, cases:assertions}));
