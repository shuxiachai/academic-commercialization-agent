"""Production-only failed-receipt explanation remains inert presentation."""

import json
from pathlib import Path
import subprocess

from api import saved_source_production_assets as assets


ROOT = Path(__file__).resolve().parents[1]


def test_outcome_asset_is_whitelisted_without_widening_frozen_aliases():
    """The new pure renderer is an explicit production asset, not directory serving."""
    reply = assets.asset_response("outcome.js")
    assert reply.status_code == 200
    assert reply.body == (ROOT / "web/source-locator/outcome.js").read_bytes()
    assert assets.asset_response("outcome.js/extra").status_code == 404


def test_failed_outcome_is_safe_visible_and_cleared_without_raw_error_injection():
    """The pure renderer safely maps codes; the integration test checks decoding."""
    module = (ROOT / "web/source-locator/outcome.js").resolve().as_uri()
    probe = r'''
import assert from 'node:assert/strict';
const { clearOutcome, renderOutcome } = await import(process.argv[1]);
const node = { textContent: 'stale failure', hidden: false };
const byId = id => { assert.equal(id, 'receipt-outcome'); return node; };
renderOutcome({receipt: {state: 'failed', error_code: 'daily_quota_exceeded'}}, byId);
assert.equal(node.hidden, false);
assert.match(node.textContent, /^定位失败：/);
assert.match(node.textContent, /不代表免费或可自动重试/);
renderOutcome({receipt: {state: 'failed', error_code: '<img src=x onerror=alert(1)>'}}, byId);
assert.equal(node.hidden, false);
assert.match(node.textContent, /^定位失败：没有可安全显示的具体原因/);
assert.doesNotMatch(node.textContent, /img|alert/);
renderOutcome({receipt: {state: 'failed', error_code: 'toString'}}, byId);
assert.match(node.textContent, /^定位失败：没有可安全显示的具体原因/);
assert.doesNotMatch(node.textContent, /function/);
renderOutcome({receipt: {state: 'completed', error_code: null}}, byId);
assert.equal(node.hidden, true);
assert.equal(node.textContent, '');
node.textContent = 'old'; node.hidden = false;
clearOutcome(byId);
assert.equal(node.hidden, true);
assert.equal(node.textContent, '');
console.log('safe outcome rendering verified');
'''
    completed = subprocess.run(["node", "--input-type=module", "-e", probe, module], input=json.dumps({}),
                               capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    assert completed.returncode == 0, completed.stderr
    assert "safe outcome rendering verified" in completed.stdout


def test_real_entry_hooks_validate_render_and_clear_failed_receipts():
    """Execute the production modules; removing either outcome hook must fail."""
    modules = {name: assets.asset_bytes(name).decode("utf-8") for name in
               ("result.js", "receipt.js", "accounting.js", "outcome.js", "entry.js")}
    probe = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createHash, webcrypto} from 'node:crypto';
const {modules, html} = JSON.parse(fs.readFileSync(0, 'utf8'));
const storageName = 'source-locator:v1';
function harness(omit = '') {
  class Element {
    constructor() { this.hidden = true; this.value = ''; this.checked = false; this.dataset = {}; this.listeners = {}; this.textContent = ''; }
    addEventListener(name, fn) { (this.listeners[name] ??= []).push(fn); }
    async fire(name) { for (const fn of this.listeners[name] ?? []) await fn({preventDefault() {}}); }
    setAttribute() {}
    focus() {}
    replaceChildren() { this.textContent = ''; }
    set innerHTML(_) { throw Error('unsafe HTML'); }
  }
  const nodes = Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(m => [m[1], new Element()]));
  const el = id => { assert.ok(nodes[id], 'shipped DOM ID ' + id); return nodes[id]; };
  const saved = new Map(), calls = [];
  let mode = 'failed';
  const context = vm.createContext({
    crypto: webcrypto, TextEncoder, TextDecoder, Uint8Array, AbortController, setTimeout, clearTimeout,
    document: { getElementById: el, documentElement: {dataset: {
      receiptContract: 'saved_source_receipt_usage_v1', executionAllowed: 'true'}} },
    window: {location: {hash: ''}}, addEventListener() {},
    sessionStorage: {getItem: k => saved.get(k) ?? null, setItem: (k, v) => saved.set(k, v), removeItem: k => saved.delete(k)},
    async fetch(url, options) {
      const key = options.headers['Idempotency-Key'];
      assert.equal(JSON.parse(saved.get(storageName)).receipt_key, key, 'persist before request');
      calls.push({url, options});
      const receipt = {schema_version: 1, operation: 'saved_source_location_v1',
        receipt_key_sha256: createHash('sha256').update(key).digest('hex'),
        state: mode === 'pending' ? 'pending' : 'failed', run_id: el('run-id').value,
        expires_at: Number(key.split('.')[1]) + 86400, admission_state: 'not_admitted',
        provider_usage: 'not_observed', provider_cost: 'not_observed',
        error_code: mode === 'pending' ? null : mode === 'invalid' ? '<img src=x>' : 'saved_source_missing',
        delivery: 'not_ready', delivery_snapshot_reads: 0, delivery_source_reads: 0, result: null};
      if (mode === 'wrong_identity') receipt.receipt_key_sha256 = '0'.repeat(64);
      return new Response(JSON.stringify({contract: 'saved_source_receipt_usage_v1', receipt}),
        {status: 200, headers: {'Content-Type': 'application/json'}});
    },
  });
  let source = Object.values(modules).join('\n').replace(/^import[\s\S]*?;\r?\n/gm, '').replace(/^export /gm, '');
  if (omit) {
    const hook = omit === 'render' ? 'renderOutcome(decoded, byId);' : 'clearOutcome(byId);';
    // clearOutcome also occurs inside its own renderer; mutate only the entry.
    const entry = modules['entry.js'];
    assert.equal(entry.split(hook).length, 2, 'one entry hook');
    source = source.replace(entry.replace(/^import[\s\S]*?;\r?\n/gm, ''),
      entry.replace(hook, '').replace(/^import[\s\S]*?;\r?\n/gm, ''));
  }
  vm.runInContext(source, context);
  assert.equal(calls.length, 0, 'boot cannot POST');
  el('access-code').value = 'synthetic-code';
  el('run-id').value = '20260926T010101Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  el('question').value = 'synthetic question'; el('locator-consent').checked = true;
  return {el, calls, saved, mode(value) {mode = value;},
    submit: () => el('locator-form').fire('submit'), get: () => el('recover').fire('click'),
    reset: () => el('locator-form').fire('reset')};
}
const visibleFailure = h => {
  assert.equal(h.el('receipt').hidden, false);
  assert.equal(h.el('receipt-outcome').hidden, false);
  assert.match(h.el('receipt-outcome').textContent, /^定位失败：此报告的已保存来源不可用/);
  assert.match(h.el('receipt-outcome').textContent, /不代表免费或可自动重试/);
};
const cleared = h => {
  assert.equal(h.el('receipt-outcome').hidden, true);
  assert.equal(h.el('receipt-outcome').textContent, '');
};
const h = harness();
await h.submit(); visibleFailure(h);
assert.equal(h.calls[0].options.headers['X-Source-Locator-Consent'], 'question-catalog-v1');
assert.equal(h.el('accounting').hidden, false);
assert.match(h.el('accounting-usage').textContent, /未知/);
const record = h.saved.get(storageName);
await h.reset(); cleared(h);
assert.equal(h.saved.get(storageName), record, 'clearing prose cannot clear a receipt');
assert.equal(h.el('locate').disabled, true);
for (const mode of ['invalid', 'wrong_identity', 'pending']) {
  const candidate = harness();
  await candidate.submit(); visibleFailure(candidate);
  candidate.mode(mode); await candidate.get(); cleared(candidate);
  assert.equal(candidate.calls.length, 2);
  assert.equal(candidate.calls[1].options.method, 'GET');
  assert.equal(candidate.el('locate').disabled, true);
  assert.equal(candidate.el('acknowledge').disabled, true);
  assert.equal(candidate.el('receipt').hidden, mode !== 'pending');
}
const noRender = harness('render');
await noRender.submit();
assert.throws(() => visibleFailure(noRender), assert.AssertionError, 'old entry must fail the visibility assertion');
const noClear = harness('clear');
await noClear.submit(); visibleFailure(noClear);
await noClear.reset();
assert.throws(() => cleared(noClear), assert.AssertionError, 'omitted reset hook must fail the clearing assertion');
console.log('production entry hooks and negative controls verified');
'''
    completed = subprocess.run(["node", "--input-type=module", "-e", probe],
                               input=json.dumps({"modules": modules, "html": assets.page_response(True).body.decode()}),
                               capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    assert completed.returncode == 0, completed.stderr
    assert "production entry hooks and negative controls verified" in completed.stdout
