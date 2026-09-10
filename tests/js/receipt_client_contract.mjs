/* Fresh JavaScript contexts share only tab storage, not module state.
 * Every fetch is local fixture code and fails if paid intent is repeated. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import {webcrypto} from "node:crypto";

const source = fs.readFileSync(new URL("../../web/static/js/api.js", import.meta.url), "utf8")
  .replace(/^export /gm, "");
const journalName = "paid-receipt-keys-v1";
const data = new Map();
function client(fetch, denied = false) {
  const storage = {getItem: k => data.get(k) ?? null,
    setItem(k, value) {if (denied) throw Error("denied"); data.set(k, value);},
    removeItem(k) {if (denied) throw Error("denied"); data.delete(k);}};
  const context = vm.createContext({crypto: webcrypto, Uint8Array, Date, AbortController,
    setTimeout, clearTimeout, FormData, File, localStorage: storage, sessionStorage: storage, fetch});
  vm.runInContext(source, context);
  return expression => vm.runInContext(expression, context);
}
const mode = process.argv[2];
let calls = 0;
if (["run", "resume", "paper"].includes(mode)) {
  const observed = [];
  const before = client(async (path, options) => {
    calls++;
    // Assertions inside fetch would be wrapped as the deliberately expected
    // network failure. Observe here; assert outside the rejection boundary.
    observed.push({path, options, journal: data.get(journalName)});
    throw Error("acknowledgement lost");
  });
  before("setByok({provider:'qwen',llmKey:'private-llm',serperKey:'private-search'})");
  before(`globalThis.key = beginReceipt('${mode}')`);
  await assert.rejects(before({run: "startRun({topic:'private-topic'},key)",
    resume: "resumeRun('parent',key)", paper: "uploadPaper(new File(['%PDF-private'],'secret.pdf'),key)"}[mode]));
  assert.equal(observed.length, 1);
  const {path, options, journal} = observed[0];
  const saved = JSON.parse(journal ?? "null");
  assert.ok(Array.isArray(saved), "Journal must commit before paid fetch");
  assert.equal(saved.length, 1);
  assert.equal(options.headers["Idempotency-Key"], saved[0].key);
  assert.equal(saved[0].operation, mode);
  assert.equal(options.method, "POST");
  assert.equal(path, {run: "/api/runs", paper: "/api/papers", resume: "/api/runs/parent/resume"}[mode]);
  const key = JSON.parse(data.get(journalName))[0].key;
  assert.ok(!/private|secret|topic/.test(data.get(journalName)), "Journal must contain no inputs or credentials");
  // A fresh document can retrieve the same capability, but never repeat POST.
  const after = client(async (path, options) => {
    assert.equal(path, "/api/receipts");
    assert.equal(options.method, undefined);
    assert.equal(options.headers["Idempotency-Key"], key);
    return new Response(JSON.stringify({state: "unknown"}), {headers: {"content-type": "application/json"}});
  });
  assert.equal((await after("getPaidReceipt(pendingReceiptKeys()[0].key)")).state, "unknown");
  assert.equal(calls, 1);
} else if (mode === "corrupt") {
  data.set(journalName, '{"unknown":true}');
  const run = client(() => {calls++; throw Error("request leaked");});
  assert.throws(() => run("beginReceipt()"), /unreadable/);
  assert.equal(calls, 0);
  assert.equal(data.get(journalName), '{"unknown":true}');
} else if (mode === "denied") {
  const run = client(() => {calls++;}, true);
  run("beginReceipt()");
  assert.equal(run("receiptStorageDegraded()"), true);
  assert.equal(run("pendingReceiptKeys().length"), 1);
  assert.equal(data.has(journalName), false);
  assert.equal(client(() => {}, true)("pendingReceiptKeys().length"), 0);
} else if (mode === "timeout") {
  let observedOptions;
  const run = client((_path, options) => new Promise((_resolve, reject) => {
    calls++;
    observedOptions = options;
    options.signal.addEventListener("abort", () => reject(Error("bounded read")));
  }));
  run("globalThis.setTimeout = (callback) => { queueMicrotask(callback); return 1; }; globalThis.queueMicrotask = callback => Promise.resolve().then(callback)");
  await assert.rejects(run("getPaidReceipt(beginReceipt())"), /Cannot reach/);
  assert.equal(calls, 1);
  assert.equal(observedOptions.method, undefined);
} else assert.fail("Unknown receipt client scenario");
console.log(`PASS ${mode}`);
