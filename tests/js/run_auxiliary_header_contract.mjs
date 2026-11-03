/* Execute the shipped run header against three real API response bodies.
 *
 * The VM supplies only browser globals.  It deliberately suppresses app.js's
 * boot sequence so the contract cannot issue a network request; paintHeader
 * and every run.js formatter remain the production functions. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const storage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
const denyNetwork = () => { throw new Error("Unexpected network request in header contract"); };
globalThis.localStorage = storage;
globalThis.sessionStorage = storage;
globalThis.fetch = denyNetwork;
const actualRunView = await import("../../web/static/js/run.js");
const actualI18n = await import("../../web/static/js/i18n.js");
const appSource = fs.readFileSync(new URL("../../web/static/js/app.js", import.meta.url), "utf8")
  .replace(/^import .*;\r?\n/gm, "")
  // Boot owns routing/polling and is outside this single-header contract.
  // Do not replace paintHeader or any formatter under test.
  .replace(/ensureAccess\(\)\.then\([\s\S]*?\n\}\);\s*$/, "");

class Element {
  constructor() {
    Object.assign(this, { value: "", textContent: "", title: "", className: "", hidden: false,
      scrollHeight: 0,
      disabled: false, dataset: {}, style: {}, children: [], listeners: {} });
  }
  addEventListener(event, listener) { this.listeners[event] = listener; }
  append(...children) { this.children.push(...children); }
  remove() {} focus() {} reset() {} setAttribute() {} removeAttribute() {}
  querySelectorAll() { return []; }
  set innerHTML(_value) { this.children = []; }
}

const elements = new Map();
const get = selector => {
  if (!elements.has(selector)) elements.set(selector, new Element());
  return elements.get(selector);
};
const context = vm.createContext({
  api: { pendingReceiptKeys: () => [], receiptStorageDegraded: () => false },
  runView: { ...actualRunView }, sidebar: {}, result: {}, needsScopeWarning: () => false,
  createPaidReceipts: () => ({ subscribe() {}, state: () => ({ active: false }), begin: () => () => {},
    acknowledge: () => false }),
  i18n: { t: actualI18n.t, language: actualI18n.language, apply() {} },
  document: { querySelector: get, querySelectorAll: () => [], createElement: () => new Element(),
    addEventListener() {}, hidden: false },
  window: { addEventListener() {}, matchMedia: () => ({ matches: false }) },
  history: { pushState() {} }, location: { pathname: "/", reload() {} },
  localStorage: storage, sessionStorage: storage, fetch: denyNetwork,
  setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {}, confirm: () => true,
});
vm.runInContext(appSource, context, { filename: "app.js" });

const [known, missing, unreadable] = process.argv.slice(2, 5).map(JSON.parse);
const fault = process.argv[5] ?? "none";
assert.ok(["none", "drop_auxiliary"].includes(fault), "unsupported harness fault");
assert.equal(known.usage_accounting?.state, "unavailable", "first body must retain Crew unavailability");
assert.equal(known.auxiliary_usage?.pdf_reference?.relation, "reference_only", "first body must be the saved PDF reference");
assert.equal(missing.auxiliary_usage?.record_state, "not_recorded", "second body must be the missing sidecar projection");
assert.equal(unreadable.auxiliary_usage?.record_state, "unreadable", "third body must be the corrupt sidecar projection");
assert.equal(known.usage.total_tokens, 999);
assert.equal(known.usage.cost_usd, 0.1234);
assert.equal(known.auxiliary_usage.observed_tokens, 12);
assert.ok(known.auxiliary_usage.observed_cost_usd > 0);
assert.equal(known.auxiliary_usage.pdf_reference.observation.observed_tokens, 12);
assert.ok(known.auxiliary_usage.pdf_reference.observation.observed_cost_usd > 0);

const paint = body => vm.runInContext(`paintHeader(${JSON.stringify(body)})`, context);
const usage = get("#run-usage");
const assertKnownHeader = () => {
  assert.match(usage.textContent, /Auxiliary LLM only/, "run header lost auxiliary observation");
  assert.match(usage.textContent, /usage unavailable/);
  assert.match(usage.title, /does not mean zero/);
  for (const text of [usage.textContent, usage.title]) {
    assert.match(text, /Auxiliary LLM only/);
    assert.match(text, /historical reference, not a new charge/);
    assert.match(text, /not a full invoice/);
    assert.doesNotMatch(text, /Crew nodes only|not recorded|unreadable/);
    // New helper usage is positive. The positive historical PDF observation
    // and the numeric-but-unavailable Crew snapshot must not be added to it.
    assert.deepEqual([...text.matchAll(/Observed tokens: (\d+)/g)].map(match => match[1]), ["12"]);
    assert.deepEqual([...text.matchAll(/\$([0-9.]+)/g)].map(match => match[1]),
      [String(known.auxiliary_usage.observed_cost_usd)]);
  }
};
const assertUnavailableAuxiliary = label => {
  assert.strictEqual(get("#run-usage"), usage, "updates must reuse the same DOM node");
  for (const text of [usage.textContent, usage.title]) {
    assert.match(text, label);
    assert.match(text, /not zero/);
    assert.doesNotMatch(text, /Observed tokens: 12|\$|historical reference/);
  }
};

// This CLI mutation leaves the real paintHeader and its other formatters
// unchanged. Its caller requires the exact lost-observation AssertionError.
if (fault === "drop_auxiliary") context.runView.auxiliarySummary = () => "";

paint(known); // Actual status response, with both a new charge and a PDF reference.
assertKnownHeader();
// The model name rides inside usage.agents and the revision on the status
// body itself; both must reach the header from the actual HTTP response, not
// only from a formatter fed by hand. The run page is where a reader learns
// which model produced a report on a deployment that rotates models.
assert.equal(known.usage.agents[0].model, "qwen3.7-max-preview", "fixture must name a model");
assert.match(known.pipeline_revision ?? "", /\S/, "status body must carry the revision");
const identity = get("#run-identity");
assert.match(identity.textContent, /qwen3\.7-max-preview/, "run header lost the model name");
assert.match(identity.textContent, new RegExp(known.pipeline_revision.slice(0, 11).replace(/[.]/g, "\\.")),
  "run header lost the pipeline revision");
assert.match(identity.title, /neither name is a quality measurement/);

paint(missing); // Actual progress response after removing the sidecar.
assertUnavailableAuxiliary(/not recorded/);

// Repaint the same known HTTP body so corrupt storage must clear stale costs
// and its tooltip independently of the preceding missing-sidecar transition.
paint(known);
assertKnownHeader();
paint(unreadable);
assertUnavailableAuxiliary(/unreadable/);

console.log("PASS run_auxiliary_header");
