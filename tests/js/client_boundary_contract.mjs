/* Native JS client contracts with fake fetch/storage; no sockets or keys. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const [scenario, argument] = process.argv.slice(2);
const credentials = { provider: "qwen", llmKey: "fixture-A", serperKey: "fixture-search" };
const requests = [];
const store = new Map();
globalThis.localStorage = { getItem: () => "fixture-operator", removeItem() {} };
globalThis.sessionStorage = {
  getItem: key => store.get(key) ?? null,
  setItem: (key, value) => store.set(key, value), removeItem: key => store.delete(key),
};
globalThis.fetch = async (url, options) => {
  requests.push({ url, options });
  return new Response('{}', { headers: { 'Content-Type': 'application/json' } });
};
const api = await import("../../web/static/js/api.js");

if (scenario === "credentials") {
  const { raw, valid, operation } = JSON.parse(argument);
  if (raw !== null) store.set('byok-credentials', raw);
  const call = () => operation === "run" ? api.startRun({ topic: "Fixture topic" })
    : operation === "resume" ? api.resumeRun("parent")
    : api.uploadPaper(new File(['%PDF-fixture'], 'fixture.pdf'));
  if (!valid) {
    await assert.rejects(Promise.resolve().then(call), err => err.code === 'invalid_byok'
      && !err.message.includes('fixture-secret'));
    assert.equal(requests.length, 0, "Corrupt BYOK must not buy an operator-billed request");
    // An explicit choice, not parsing failure, can switch to operator billing.
    api.setByok(null);
    await call();
    assert.equal(requests.at(-1).options.headers['X-Access-Code'], 'fixture-operator');
  } else {
    await call();
    const sent = requests[0].options.body;
    const expected = raw === null ? null : JSON.parse(raw);
    if (operation === 'pdf') assert.equal(sent.get('llm_api_key'), expected?.llmKey ?? null);
    else {
      const body = JSON.parse(sent);
      assert.equal(body.llm_api_key, expected?.llmKey);
      assert.equal(body.llm_provider, expected?.provider);
      assert.equal(body.serper_api_key, expected?.serperKey);
    }
  }
  assert.equal(requests.length, 1);
} else if (scenario === "setter") {
  api.setByok(credentials);
  assert.throws(() => api.setByok({}), err => err.code === 'invalid_byok');
  assert.deepEqual(api.getByok(), credentials, "Rejected changes cannot erase the current payer");
} else if (["read_timeout", "body_timeout"].includes(scenario)) {
  let expire, timeoutMs, cleared = false;
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout;
  globalThis.setTimeout = (callback, ms) => { timeoutMs = ms; expire = callback; return 41; };
  globalThis.clearTimeout = id => { assert.equal(id, 41); cleared = true; };
  try {
    globalThis.fetch = (url, options) => new Promise((resolve, reject) => {
      assert.ok(url.includes('/progress?since=7'));
      if (scenario === 'body_timeout') resolve({ ok: true, status: 200,
        headers: { get: () => 'application/json' }, json: () => new Promise((yes, no) => {
          options.signal.addEventListener('abort', () => no(new Error('aborted body')));
        }) });
      else options.signal.addEventListener('abort', () => reject(new Error('aborted fixture')));
    });
    const pending = api.getProgress('fixture', 7);
    assert.equal(timeoutMs, 15000, 'A stalled progress read must have the documented finite deadline');
    await Promise.resolve();  // Let the response headers enter the body reader.
    expire();
    await assert.rejects(pending, err => scenario === 'body_timeout' ? err.message === 'aborted body' : err.status === 0);
    assert.ok(cleared, 'Read timeout must release its timer');
    // Only reads get a deadline, never a paid request with unknown acceptance.
    globalThis.fetch = async (url, options) => {
      assert.equal(options.signal, undefined);
      return new Response('{}', { headers: { 'Content-Type': 'application/json' } });
    };
    await api.startRun({ topic: 'Fixture paid boundary' });
  } finally { globalThis.setTimeout = originalSet; globalThis.clearTimeout = originalClear; }
} else if (scenario.startsWith("poll_")) {
  const timers = [], connections = [], updates = [], errors = [], done = [], cursors = [];
  let response, reject;
  const context = vm.createContext({
    api: { getProgress: (id, cursor) => { cursors.push(cursor); return new Promise((yes, no) => { response = yes; reject = no; }); } },
    setTimeout: fn => { timers.push(fn); return 1; }, clearTimeout: () => timers.splice(0),
    connections, updates, errors, done, t: k => k,
  });
  vm.runInContext(fs.readFileSync(new URL('../../web/static/js/run.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '').replace(/export /g, ''), context);
  const handle = vm.runInContext(`follow('fixture', {
    onConnection: x => connections.push(x), onUpdate: x => updates.push(x),
    onError: x => errors.push(x), onDone: x => done.push(x) })`, context);
  const flush = () => new Promise(resolve => setImmediate(resolve));
  const progress = { state: 'running', steps: [], steps_next_cursor: 4 };
  if (scenario === 'poll_missing') {
    reject({ status: 404 }); await flush();
    assert.equal(connections.at(-1).state, 'missing');
    assert.equal(errors.length, 1); assert.equal(timers.length, 0); assert.equal(done.length, 0);
  } else if (scenario === 'poll_stop') {
    handle.stop(); response(progress); await flush();
    assert.deepEqual([connections.length, updates.length, timers.length], [0, 0, 0]);
  } else {
    if (scenario === 'poll_recovery') {
      response(progress); await flush(); timers.shift()();
    }
    for (let i = 0; i < 3; i++) {
      reject({ status: 0 }); await flush();
      assert.equal(connections.at(-1).state, 'stale');
      assert.equal(connections.at(-1).lastSuccessAt === null, scenario !== 'poll_recovery');
      assert.equal(errors.length, 0); assert.equal(done.length, 0);
      assert.equal(timers.length, 1); timers.shift()();
    }
    response({ ...progress, state: 'completed' }); await flush();
    assert.equal(connections.at(-1).state, 'connected');
    assert.equal(done.length, 1); assert.equal(timers.length, 0);
    assert.ok(updates.every(p => ['running', 'completed'].includes(p.state)));
    assert.ok(cursors.slice(1).every(c => c === (scenario === 'poll_recovery' ? 4 : 0)));
  }
} else throw new Error(`Unknown scenario ${scenario}`);
console.log(`PASS ${scenario}`);
