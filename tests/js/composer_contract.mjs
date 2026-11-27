/* Execute shipped app/API code with delayed HTTP responses, never a socket.
 * DOM painting is a fixture; request count and submitted paper identity are
 * the seam under test. The opt-in Chromium journey covers real DOM behavior. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createPaidReceipts } from "../../web/static/js/paid_receipts.js";
import { modelKind } from "../../web/static/js/model_kind.js";

globalThis.localStorage = { getItem: () => null, removeItem: () => {} };
globalThis.sessionStorage = { getItem: () => null };
const api = await import("../../web/static/js/api.js");
const actualRunView = await import("../../web/static/js/run.js");
const compareView = await import("../../web/static/js/compare.js");
const source = fs.readFileSync(new URL("../../web/static/js/app.js", import.meta.url), "utf8")
  .replace(/^import .*;\r?\n/gm, "");
const translations = {
  msg_busy: "capacity", msg_daily_quota: "daily quota resets at 00:00 UTC",
  msg_rate_limited: "rate limit", msg_submitting: "submitting",
  msg_paid_ack_unknown: "acceptance unknown; check history",
  msg_history_unavailable: "accepted; bookmark this URL",
};

function fixture(receiptStore = new Map()) {
  const elements = new Map();
  class Element {
    constructor() {
      Object.assign(this, { value: "", disabled: false, hidden: false, dataset: {},
        style: {}, children: [], listeners: {}, textContent: "", scrollHeight: 40 });
    }
    addEventListener(event, handler) { this.listeners[event] = handler; }
    set innerHTML(value) { this.children = []; }
    append(...children) { this.children.push(...children); }
    querySelectorAll() { return []; }
    focus() {} remove() {} reset() {} setAttribute() {} removeAttribute() {}
    showModal() { this.open = true; } close() { this.open = false; }
  }
  const get = (selector) => {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  const requests = [], opened = [], reloads = [], windowEvents = {};
  globalThis.fetch = (url, options) => {
    // Access boot deliberately waits; it cannot start history/capacity timers.
    if (url === "/api/access/check") return new Promise(() => {});
    assert.ok(["/api/runs", "/api/papers", "/api/runs/parent/resume", "/api/receipts", "/api/keys/check", "/api/plan", "/api/auth/login", "/api/auth/logout", "/api/auth/keys", "/api/auth/keys/check", "/api/runs?limit=200", "/api/runs/running-one?intent=cancel"].includes(url), `Unexpected HTTP: ${url}`);
    return new Promise((resolve, reject) => requests.push({ url, options, resolve, reject }));
  };
  const context = vm.createContext({
    createPaidReceipts: () => createPaidReceipts(() => ({
      getItem: key => receiptStore.get(key) ?? null,
      setItem: (key, value) => receiptStore.set(key, value),
      removeItem: key => receiptStore.delete(key),
    })),
    api, runView: { ...actualRunView }, compareView, Event, modelKind,
    sidebar: { refresh: () => Promise.resolve([]) }, result: {}, needsScopeWarning: () => false,
    i18n: { t: (key) => translations[key] || key, language: () => "English", locale: () => "en-GB", apply: () => {},
            pageTitle: (name = "") => (name ? `${name} · brand_full` : "brand_full") },
    document: { querySelector: get, querySelectorAll: (selector) => selector === '[data-resume-run]'
      ? get("#run-actions").children.filter((el) => el.dataset?.resumeRun) : [], createElement: () => new Element(),
      addEventListener: () => {}, hidden: false },
    window: { matchMedia: () => ({ matches: false }), addEventListener: (name, fn) => { windowEvents[name] = fn; } },
    localStorage: globalThis.localStorage, history: { pushState: () => {} },
    location: { pathname: "/", reload: () => reloads.push(true) },
    setTimeout: () => 1, clearTimeout: () => {}, setInterval: () => 1, clearInterval: () => {},
    confirm: () => true, recordOpen: (id) => opened.push(id),
  });
  vm.runInContext(source, context);
  vm.runInContext("globalThis.originalOpenRun = openRun; openRun = (id) => recordOpen(id)", context);
  const run = (text) => vm.runInContext(text, context);
  const topic = (text) => { get("#topic").value = text; run("syncComposer()"); };
  const submit = () => get("#compose-form").listeners.submit({ preventDefault() {} });
  const upload = () => {
    context.file = new File(["%PDF-offline"], "fixture.pdf", { type: "application/pdf" });
    return run("uploadPaper(file)");
  };
  const respond = (index, body, status = 200, code = null) => requests[index].resolve(
    new Response(JSON.stringify(body), { status, headers: {
      "Content-Type": "application/json", ...(code ? { "X-Error-Code": code } : {}),
    } }),
  );
  return { get, run, topic, submit, upload, respond, requests, opened, reloads, windowEvents };
}

function paintResume(f) {
  f.run('activeRunId = "parent"; paintActions("failed", { committed_nodes: ["retrieval"] })');
  return f.get("#run-actions").children.find((el) => el.textContent === "resume");
}

const paper = { paper_id: "paper-one", title: "Fixture paper", commercialization_topic: "Suggested topic" };
const scenarios = {
  async auxiliary_attachment_and_receipt() {
    const mode = process.argv[3];
    const usage = {schema_version: 1, record_state: "recorded", coverage: "partial",
      accounting_scope: "auxiliary_llm", end_to_end_cost_complete: false,
      call_count: 1, provider_attempt_count: null, total_tokens: null,
      observed_tokens: 12, observed_cost_usd: 0.000013, cost_complete: false, calls: [], pdf_reference: null};
    const observation = mode === "missing" ? null : mode === "corrupt" ? {...usage, observed_tokens: true} : usage;
    const verify = text => {
      if (mode === "missing") assert.match(text, /not recorded/);
      else if (mode === "corrupt") assert.match(text, /unreadable/);
      else {
        assert.match(text, /Observed tokens: 12/);
        assert.ok(text.includes("$0.000013"));
        assert.match(text, /Incomplete/);
        assert.match(text, /not a full invoice/);
      }
      if (mode === "missing" || mode === "corrupt") assert.ok(!text.includes("$"));
    };
    const attachmentText = f => f.get("#attachment").children.map(el => el.textContent).join(" ");
    const f = fixture(); f.topic("Unchanged caller topic");
    const pending = f.upload();
    f.respond(0, mode === "failed" ? {detail: "Safe extraction failure", auxiliary_usage: observation}
      : {...paper, auxiliary_usage: observation}, mode === "failed" ? 422 : 200);
    await pending;
    verify(attachmentText(f));
    assert.equal(f.get("#topic").value, "Unchanged caller topic");
    assert.equal(f.requests.length, 1);
    if (mode === "failed") assert.equal(f.run("attachedPaper"), null);

    const lost = fixture(); lost.topic("Lost paper acknowledgement");
    const upload = lost.upload();
    lost.requests[0].reject(new Error("offline lost acknowledgement"));
    await upload;
    const lookup = lost.get("#paid-receipt-lookup").listeners.click();
    assert.equal(lost.requests[1].url, "/api/receipts");
    lost.respond(1, {operation: "paper", state: mode === "failed" ? "failed" : "accepted",
      resource_id: paper.paper_id, auxiliary_usage: observation,
      response: {...paper, auxiliary_usage: observation}});
    await lookup;
    const row = lost.get("#paid-receipt-results").children.at(-1);
    verify(row.textContent);
    if (mode !== "failed") {
      await row.children[0].listeners.click();
      verify(attachmentText(lost));
    }
    assert.equal(lost.requests.filter(r => r.options.method === "POST").length, 1);
  },
  async durable_receipt_lookup() {
    const outcome = process.argv[3];
    const f = fixture(); f.topic("Lost paid acceptance");
    const sent = f.submit();
    const key = f.requests[0].options.headers["Idempotency-Key"];
    assert.equal(f.get("#paid-receipt-lookup").hidden, false, "Saved identity must reach the pending UI before fetch settles");
    assert.match(key, /^v1\.[0-9]{10}\.[0-9a-f]{64}$/);
    f.requests[0].reject(new Error("lost acknowledgement")); await sent;
    assert.equal(api.pendingReceiptKeys()[0].key, key);
    const lookup = f.get("#paid-receipt-lookup").listeners.click();
    assert.equal(f.requests[1].url, "/api/receipts");
    assert.equal(f.requests[1].options.method, undefined);
    assert.equal(f.requests[1].options.headers["Idempotency-Key"], key);
    if (outcome === "late_identity") f.run("applyByokMode()");
    const state = outcome === "unknown" ? "unknown" : "accepted";
    f.respond(1, {operation: "run", state, resource_id: outcome === "mismatch" ? "other" : "accepted-run",
      response: {run_id: "accepted-run", topic: "Accepted topic"}});
    await lookup;
    const rows = f.get("#paid-receipt-results").children;
    if (outcome === "late_identity") assert.equal(rows.length, 0);
    else if (outcome === "unknown") assert.equal(rows[0].textContent, "receipt_unresolved");
    else if (outcome === "mismatch") assert.equal(rows[0].textContent, "receipt_lookup_unavailable");
    else {
      await rows[0].children[0].listeners.click();
      assert.deepEqual(f.opened, ["accepted-run"]);
      assert.equal(api.pendingReceiptKeys().length, 0);
    }
    assert.equal(f.requests.filter(r => r.options.method === "POST").length, 1);
  },
  async sidebar_generation() {
    const mode = process.argv[3];
    const f = fixture();
    f.run(`globalThis.held=[]; globalThis.selected='fixture-A';
      api={...api, listRuns:()=>new Promise(resolve=>held.push(resolve)),
        getRun:()=>new Promise(resolve=>held.push(resolve)),
        getByokRuns:()=>[{run_id:'local-A',topic:'Local A'}],
        setByok:()=>false, setAccessCode:value=>{selected=value;return false;},
        getAccessCode:()=>selected,checkAccess:()=>Promise.resolve({}),
        accessCodeClearConflict:()=>false};`);
    const actualSidebar = fs.readFileSync(new URL('../../web/static/js/sidebar.js', import.meta.url),'utf8')
      .replace(/^import .*;\r?\n/gm,'').replace(/export /g,'');
    f.run(`sidebar=(()=>{${actualSidebar};return {render,refresh};})()`);
    if (mode === 'byok') f.run('byokMode=true');
    const old = f.run('refreshSidebar()');
    const rows = () => f.get('#runlist').children.filter(el=>el.className==='runitem-row')
      .map(el=>el.children[0].dataset.runId);
    if (mode === 'gate') {
      f.run(`sidebar.render(document.querySelector('#runlist'),[{run_id:'old-visible',state:'completed'}],{})`);
      assert.deepEqual(rows(),['old-visible']);
      f.run('exitCredentials()');
      assert.deepEqual(rows(),[], 'Logout must clear an already visible capability');
      f.run(`held[0]({runs:[{run_id:'late-while-gated',state:'completed'}]})`);
      await old;
      assert.deepEqual(rows(),[], 'Pending replies must not repopulate the open login gate');
      assert.equal(f.get('#gate').hidden,false);
      return;
    }
    if (mode === 'ordered') {
      const fresh=f.run('refreshSidebar()');
      f.run(`held[1]({runs:[{run_id:'current',state:'completed'}]})`); await fresh;
      assert.deepEqual(rows(),['current']);
    } else {
      const logout=f.run('exitCredentials()');
      assert.deepEqual(rows(),[], 'Logout clears capability views before opening the gate');
      f.get('#gate-input').value='fixture-B';
      await f.get('#gate-form').onsubmit({preventDefault(){}}); await logout;
      assert.equal(f.get('#gate').hidden,true);
      f.run(`held[1]({runs:[{run_id:'current',state:'completed'}]})`);
      await new Promise(resolve=>setImmediate(resolve));
    }
    f.run(mode === 'byok' ? `held[0]({topic:'Old local A',state:'completed'})`
      : `held[0]({runs:[{run_id:'old-A',state:'completed'}]})`);
    await old;
    assert.deepEqual(rows(),['current'], 'Late responses cannot replace the current history');
    assert.equal(f.requests.length,0);
  },
  async receipt_refresh() {
    const kind = process.argv[3];
    const store = new Map();
    const a = fixture(store); a.topic('Original private topic');
    const pending = kind === 'run' ? a.submit() : kind === 'pdf' ? a.upload() : paintResume(a).listeners.click();
    assert.equal(a.requests.length, 1);
    assert.deepEqual([...store], [['paid-request-unconfirmed-v1', 'unconfirmed']], 'Write only a constant before dispatch');
    let prevented = false; const unload = {preventDefault(){prevented = true;}};
    a.windowEvents.beforeunload(unload);
    assert.equal(prevented, true); assert.equal(unload.returnValue, '');
    // A fresh document gets only session bytes, never the previous JS locks.
    const b = fixture(store); b.topic('Attempted repeat after refresh');
    assert.equal(b.get('#paid-receipt-notice').hidden, false);
    assert.equal(b.get('#paid-receipt-message').textContent, 'paid_receipt_unknown');
    assert.equal(b.get('#run-btn').disabled, true);
    assert.equal(b.get('#attach-btn').disabled, true);
    assert.equal(paintResume(b).disabled, true);
    await b.submit(); await b.upload(); await paintResume(b).listeners.click();
    assert.equal(b.requests.length, 0, 'All three paid dispatch seams remain blocked after refresh');
    b.run('confirm = () => false'); b.get('#paid-receipt-ack').listeners.click();
    await b.submit(); assert.equal(b.requests.length, 0, 'Dismissal is not risk acknowledgement');
    b.run('confirm = () => true'); b.get('#paid-receipt-ack').listeners.click();
    assert.equal(b.requests.length, 0, 'Acknowledgement cannot itself dispatch any POST');
    assert.equal(b.get('#run-btn').disabled, false);
    const next = b.submit(); b.respond(0, {detail:'known rejection'}, 422); await next;
    assert.equal(b.requests.length, 1);
    // Finish the synthetic old document only after all refresh assertions.
    a.respond(0, kind === 'pdf' ? paper : {run_id:'original',topic:'Original'}, kind === 'pdf' ? 200 : 202);
    await pending;
  },
  async receipt_outcome() {
    const [kind, outcome] = process.argv.slice(3);
    const store = new Map(); const f = fixture(store); f.topic('Receipt outcome');
    const pending = kind === 'run' ? f.submit() : kind === 'pdf' ? f.upload() : paintResume(f).listeners.click();
    if (outcome === 'transport') f.requests[0].reject(new TypeError('fixture connection lost'));
    else if (outcome === 'malformed') f.respond(0, {});
    else if (outcome === 'handoff') {
      f.run(kind === 'pdf' ? 'paintAttachment = () => {throw Error("fixture handoff")}'
        : 'openRun = async () => {throw Error("fixture handoff")}');
      f.respond(0, kind === 'pdf' ? paper : {run_id:'accepted',topic:'Accepted'});
    } else f.respond(0, {detail:'fixture response'}, Number(outcome));
    await pending;
    const rejected = ['401','422','429'].includes(outcome);
    assert.equal(store.has('paid-request-unconfirmed-v1'), !rejected);
    assert.equal(f.get('#run-btn').disabled, !rejected);
    assert.equal(f.get('#paid-receipt-ack').hidden, rejected);
    assert.equal(f.requests.length, 1);
    const reloaded = fixture(store); reloaded.topic('New document');
    assert.equal(reloaded.get('#run-btn').disabled, !rejected);
  },
  async receipt_handoff() {
    const store = new Map(); const f = fixture(store); f.topic('Delayed UI delivery');
    f.run('openRun = () => new Promise(resolve => {globalThis.finishDelivery = resolve;})');
    const pending = f.submit(); f.respond(0, {run_id:'accepted',topic:'Accepted'}, 202);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(store.size, 1, 'Parsed JSON must not clear the marker before view handoff');
    assert.equal(f.run('paidReceipts.state().active'), 1);
    assert.equal(f.run('paidReceipts.acknowledge()'), false);
    f.run('finishDelivery()'); await pending;
    assert.equal(store.size, 0);
    let prevented = false; f.windowEvents.beforeunload({preventDefault(){prevented=true;}});
    assert.equal(prevented, false, 'A delivered request no longer needs an unload prompt');
  },
  async receipt_navigation_failure() {
    const store = new Map(); const f = fixture(store); f.topic('Accepted with unavailable URL history');
    // Keep the actual navigation/follow seam, isolate unrelated field renderers.
    f.run(`openRun = originalOpenRun; paintHeader = () => {}; paintActions = () => {};
      history.pushState = () => {throw Error('fixture history denied')};
      runView.follow = (id) => {recordOpen(id); return {stop(){}};}`);
    const pending = f.submit(); f.respond(0, {run_id:'accepted',topic:'Accepted'}, 202); await pending;
    assert.deepEqual(f.opened, ['accepted'], 'URL failure cannot prevent following an accepted run');
    assert.equal(store.size, 0);
    assert.equal(f.get('#pane-run').hidden, false);
    assert.ok(f.get('#toasts').children.some(el => el.textContent === translations.msg_history_unavailable));
  },
  async receipt_storage_failure() {
    const store = {get(){throw Error('denied')}, set(){throw Error('denied')}, delete(){throw Error('denied')}};
    const f = fixture(store); f.topic('Memory-only mode');
    assert.equal(f.get('#paid-receipt-notice').hidden, false);
    assert.equal(f.get('#paid-receipt-message').textContent, 'paid_receipt_unavailable');
    const pending = f.submit(); f.respond(0, {run_id:'accepted',topic:'Accepted'}, 202); await pending;
    assert.deepEqual(f.opened, ['accepted'], 'Storage failure cannot erase accepted delivery');
    assert.equal(f.get('#paid-receipt-message').textContent, 'paid_receipt_unavailable');
  },
  async cross_tab_exit() {
    const local = new Map();
    globalThis.localStorage = {getItem: key => local.get(key) ?? null,
      setItem: (key, value) => local.set(key, value), removeItem: key => local.delete(key)};
    globalThis.sessionStorage.removeItem = () => {};
    const f = fixture(); api.setAccessCode('fixture-A');
    f.topic('Identity A attachment');
    const pending = f.upload(); f.respond(0, paper); await pending;
    local.set('access-code', 'fixture-B');
    f.run('exitCredentials()');
    assert.equal(f.reloads.length, 0, 'A conflict cannot reload into another tab\'s identity');
    assert.equal(f.get('#gate').hidden, false, 'A different saved payer requires explicit selection');
    assert.equal(f.get('#storage-notice').textContent, 'storage_other_identity');
    assert.equal(f.get('#attachment').hidden, true);
    assert.equal(f.get('#topic').value, '');
    assert.equal(api.getAccessCode(), null);
    assert.equal(local.get('access-code'), 'fixture-B');
    assert.equal(f.requests.length, 1);
  },
  async gate_pending() {
    const f = fixture(); f.run('showGate()');
    f.get('#gate-input').value = 'candidate-code';
    f.get('#gate-form').onsubmit({preventDefault(){}}); // Deliberately held access check.
    assert.equal(f.get('#gate-submit').disabled, true);
    f.get('#gate-to-byok').onclick();
    assert.equal(f.get('#byok-form').hidden, true);
    f.get('#byok-provider').value = 'qwen'; f.get('#byok-model').value = 'qwen3.8-27b'; f.get('#byok-llm-key').value = 'fixture-B';
    f.get('#byok-search').value = 'tavily'; f.get('#byok-search-key').value = 'fixture-search-B';
    f.get('#byok-form').onsubmit({preventDefault(){}});
    assert.equal(api.getByok(), null, 'A pending code check cannot race a new BYOK identity');
    assert.equal(f.get('#gate').hidden, false);
    assert.equal(f.requests.length, 0);
  },
  async gate_finished() {
    const f = fixture(); const gate = f.run('showGate()');
    f.get('#byok-provider').value = 'qwen'; f.get('#byok-model').value = 'qwen3.8-27b'; f.get('#byok-llm-key').value = 'fixture-A';
    f.get('#byok-search').value = 'tavily'; f.get('#byok-search-key').value = 'fixture-search';
    f.get('#byok-form').onsubmit({preventDefault(){}}); await gate;
    f.get('#byok-llm-key').value = 'fixture-B';
    f.get('#byok-form').onsubmit({preventDefault(){}});
    assert.equal(api.getByok()?.llmKey, 'fixture-A', 'A finished gate cannot accept stale input events');
    assert.equal(f.requests.length, 0);
  },
  async pending_exit() {
    const kind = process.argv[3];
    const f = fixture(); f.topic("Identity A topic");
    api.setByok({provider:'qwen',llmKey:'fixture-A',serperKey:'fixture-search'});
    f.run("byokMode = true");
    const pending = kind === 'run' ? f.submit() : kind === 'pdf' ? f.upload() : paintResume(f).listeners.click();
    const blockedExit = f.run("exitCredentials()");
    assert.equal(api.getByok()?.llmKey, 'fixture-A', 'A pending reply must retain the submitting payer');
    await blockedExit;
    assert.equal(f.get('#toasts').children.at(-1).textContent, 'logout_wait_paid');
    f.respond(0, kind === 'pdf' ? paper : {run_id:'accepted-A',topic:'Accepted A'}, kind === 'pdf' ? 200 : 202);
    await pending;
    if (kind !== 'pdf') assert.deepEqual(f.opened, ['accepted-A']);
    // Force same-page logout: old attachment/context must not reach identity B.
    globalThis.sessionStorage.removeItem = () => { throw Error('fixture removal denied'); };
    const exit = f.run('exitCredentials()');
    assert.equal(api.getByok(), null);
    assert.equal(f.run('attachedPaper'), null);
    assert.equal(f.get('#topic').value, '');
    f.get('#byok-provider').value = 'qwen'; f.get('#byok-model').value = 'qwen3.8-27b';
    f.get('#byok-llm-key').value = 'fixture-B'; f.get('#byok-search').value = 'tavily'; f.get('#byok-search-key').value = 'fixture-search-B';
    f.get('#byok-form').onsubmit({preventDefault(){}}); await exit;
    f.topic('Identity B topic'); const submitted = f.submit();
    const body = JSON.parse(f.requests[1].options.body);
    assert.equal(body.llm_api_key, 'fixture-B'); assert.equal(body.paper_id, null);
    f.respond(1, {detail:'fixture rejected'}, 422); await submitted;
    assert.equal(f.requests.length, 2);
  },
  async accepted_history_success() {
    for (const kind of ["run", "resume"]) {
      const store = new Map();
      globalThis.sessionStorage.getItem = (key) => store.get(key) || null;
      globalThis.sessionStorage.setItem = (key, value) => store.set(key, value);
      const f = fixture(); f.run("byokMode = true"); f.topic("Accepted history identity");
      const pending = kind === "run" ? f.submit() : paintResume(f).listeners.click();
      f.respond(0, { run_id: "child", topic: "Accepted child" }, 202); await pending;
      assert.deepEqual(JSON.parse(store.get("byok-runs")), [{ run_id: "child", topic: "Accepted child" }]);
      assert.deepEqual(f.opened, ["child"]);
      assert.equal(f.requests.length, 1);
    }
  },
  async accepted_history_failure() {
    for (const kind of ["run", "resume"]) {
      const f = fixture(); f.run("byokMode = true"); f.topic("Accepted despite storage failure");
      globalThis.sessionStorage.setItem = () => { throw new Error("QuotaExceededError"); };
      const pending = kind === "run" ? f.submit() : paintResume(f).listeners.click();
      f.respond(0, { run_id: "accepted", topic: "Accepted despite storage failure" }, 202);
      await pending;
      assert.deepEqual(f.opened, ["accepted"], "A local history fault cannot lose a paid acceptance");
      assert.equal(f.requests.length, 1);
      assert.ok(f.get("#toasts").children.some((el) => el.textContent === translations.msg_history_unavailable));
      assert.ok(!f.get("#toasts").children.some((el) => el.textContent === "QuotaExceededError"));
      if (kind === "run") assert.equal(f.get("#topic").value, "");
    }
  },
  async resume_rerender() {
    const f = fixture();
    const first = paintResume(f).listeners.click();
    const replacement = paintResume(f);
    const repeated = replacement.listeners.click();
    assert.equal(f.requests.length, 1, "Re-render must not allow a duplicate paid resume");
    assert.equal(replacement.disabled, true, "Re-render must preserve the parent's in-flight state");
    await repeated;
    f.respond(0, { detail: "fixture rejected" }, 422); await first;
    assert.equal(replacement.disabled, false, "Rejected resume must unlock the CURRENT element");
    const retry = replacement.listeners.click();
    assert.equal(f.requests.length, 2);
    f.respond(1, { run_id: "child", topic: "Accepted child" }, 202); await retry;
    assert.deepEqual(f.opened, ["child"]);
  },
  async lost_acknowledgement() {
    for (const kind of ["run", "pdf", "resume"]) {
      for (const truncated of [false, true]) {
        const f = fixture(); f.topic("Ambiguous paid operation");
        const pending = kind === "run" ? f.submit() : kind === "pdf" ? f.upload() : paintResume(f).listeners.click();
        if (truncated) f.requests[0].resolve(new Response('{"run_id":', {
          status: 202, headers: { "Content-Type": "application/json" },
        }));
        else f.requests[0].reject(new TypeError("Failed to fetch"));
        await pending;
        assert.equal(f.requests.length, 1, "Ambiguous acceptance must not trigger an automatic retry");
        assert.equal(f.get("#toasts").children.at(-1).textContent, translations.msg_paid_ack_unknown);
        assert.deepEqual(f.opened, []);
      }
    }
  },
  async malformed_history() {
    for (const value of ['{}', 'null', '[null, {}, {"run_id": "valid", "topic": "kept"}]']) {
      globalThis.sessionStorage.getItem = () => value;
      const entries = api.getByokRuns();
      assert.ok(Array.isArray(entries));
      assert.equal(entries.length, value.includes('"valid"') ? 1 : 0);
    }
  },
  async pending_submit() {
    const f = fixture();
    f.topic("Original topic");
    const first = f.submit();
    f.topic("Changed while awaiting acknowledgement");
    const repeated = f.submit();
    assert.equal(f.requests.length, 1, "One user operation must send only one paid POST");
    await repeated;
    assert.equal(f.get("#run-btn").disabled, true);
    assert.equal(JSON.parse(f.requests[0].options.body).topic, "Original topic");
    f.respond(0, { run_id: "accepted", topic: "Original topic" }, 202);
    await first;
    assert.deepEqual(f.opened, ["accepted"]);
    assert.equal(f.get("#topic").value, "");
    assert.equal(f.get("#run-btn").disabled, true, "Empty composer stays disabled after acceptance");
  },
  async rejected_submit() {
    const f = fixture(); f.topic("Retry only after explicit rejection");
    const first = f.submit();
    f.respond(0, { detail: "fixture rejected" }, 422); await first;
    assert.equal(f.get("#run-btn").disabled, false);
    const second = f.submit();
    assert.equal(f.requests.length, 2);
    f.respond(1, { detail: "fixture rejected" }, 422); await second;
  },
  async existing_topic_pdf() {
    const f = fixture(); f.topic("My original topic");
    const pending = f.upload();
    await f.submit();
    assert.deepEqual(f.requests.map((r) => r.url), ["/api/papers"]);
    f.respond(0, paper); await pending;
    assert.equal(f.get("#run-btn").disabled, false);
    const submitted = f.submit();
    const body = JSON.parse(f.requests[1].options.body);
    assert.equal(body.paper_id, paper.paper_id);
    assert.equal(body.topic, "My original topic");
    f.respond(1, { detail: "fixture rejection" }, 422); await submitted;
  },
  async empty_topic_pdf() {
    const f = fixture(); const pending = f.upload();
    f.respond(0, paper); await pending;
    assert.equal(f.get("#topic").value, "Suggested topic");
    assert.equal(f.get("#run-btn").disabled, false);
  },
  async missing_suggestion_pdf() {
    const f = fixture(); const pending = f.upload();
    f.respond(0, { ...paper, commercialization_topic: "" }); await pending;
    assert.equal(f.get("#run-btn").disabled, true);
    f.topic("User supplied topic");
    assert.equal(f.get("#run-btn").disabled, false);
  },
  async serialized_pdf() {
    const f = fixture(); f.topic("Selected paper identity");
    const first = f.upload(); const competing = f.upload();
    assert.equal(f.requests.length, 1, "Do not purchase an overlapping extraction");
    await competing;
    f.respond(0, paper); await first;
    const second = f.upload();
    f.respond(1, { ...paper, paper_id: "paper-two" }); await second;
    const sent = f.submit();
    assert.equal(JSON.parse(f.requests[2].options.body).paper_id, "paper-two");
    f.respond(2, { detail: "fixture rejection" }, 422); await sent;
  },
  async stale_pdf_response() {
    const f = fixture(); f.topic("Cleared selection");
    const pending = f.upload(); f.run("clearAttachment()");
    const competing = f.upload(); const submitted = f.submit();
    assert.equal(f.requests.length, 1, "Clearing a view must not unlock in-flight paid work");
    await competing; await submitted;
    f.respond(0, paper); await pending;
    assert.equal(f.get("#attachment").hidden, true);
    const sent = f.submit();
    assert.equal(JSON.parse(f.requests[1].options.body).paper_id, null);
    f.respond(1, { detail: "fixture rejection" }, 422); await sent;
  },
  async failed_pdf() {
    const f = fixture(); f.topic("Keep this topic");
    const pending = f.upload(); f.respond(0, { detail: "extraction failed" }, 500); await pending;
    assert.equal(f.get("#attachment").hidden, true);
    assert.equal(f.get("#run-btn").disabled, true, 'A 500 cannot prove that extraction did not spend');
    f.get('#paid-receipt-ack').listeners.click();
    assert.equal(f.requests.length, 1, 'Risk acknowledgement is not a retry');
    assert.equal(f.get("#run-btn").disabled, false);
    const sent = f.submit();
    assert.equal(JSON.parse(f.requests[1].options.body).paper_id, null);
    f.respond(1, { detail: "fixture rejection" }, 422); await sent;
  },
  // "Selected PDF text is sent to the configured model provider…" stood
  // under the composer of every visitor, PDF or not (2026-11-20). Choosing a
  // file starts its extraction at once, so the notice cannot wait for the
  // choice: it is the Paper button's own description, before the choice,
  // and the paragraph shows while a PDF is being read or is attached.
  async paper_privacy() {
    const f = fixture(); f.topic("A topic of my own");
    const notice = f.get("#paper-privacy");
    assert.equal(notice.hidden, true, "no PDF: no paragraph");
    const pending = f.upload();
    assert.equal(notice.hidden, false, "shown while the PDF is read and sent");
    f.respond(0, paper); await pending;
    assert.equal(notice.hidden, false, "and while it is attached");
    f.run("clearAttachment()");
    assert.equal(notice.hidden, true, "gone with the attachment");
    const failed = fixture(); failed.topic("Another topic");
    const upload = failed.upload(); failed.respond(0, { detail: "extraction failed" }, 422); await upload;
    assert.equal(failed.get("#paper-privacy").hidden, true, "a failed read leaves nothing attached");
  },
  async upload_during_submit() {
    const f = fixture(); f.topic("Pending assessment");
    const sent = f.submit(); const competing = f.upload();
    assert.deepEqual(f.requests.map((r) => r.url), ["/api/runs"]);
    await competing;
    f.respond(0, { detail: "fixture rejection" }, 422); await sent;
  },
  async classified_errors() {
    for (const [code, message] of [["concurrency_limit", "capacity"],
      ["daily_quota_exceeded", "daily quota resets at 00:00 UTC"],
      ["rate_limited", "rate limit"], [null, "legacy reason"], ["new_code", "legacy reason"]]) {
      for (const kind of ["run", "pdf"]) {
        const f = fixture(); f.topic("Rejected operation");
        const pending = kind === "run" ? f.submit() : f.upload();
        f.respond(0, { detail: "legacy reason" }, 429, code); await pending;
        assert.equal(f.get("#toasts").children.at(-1).textContent, message);
      }
    }
  },
  async account_keys() {
    // A signed-in account saving keys: the providers are asked first, their
    // refusal is advice and never a dead end, and no answer never blocks.
    const outcome = process.argv[3];
    // A browser whose storage works, as an account's does: the form's
    // "Remember" box starts ticked, and the default stand-in above cannot be
    // written to, which is the refused-write case (remembered_keys, refused).
    const browser = (map = new Map()) => ({ getItem: (key) => map.get(key) ?? null,
      setItem: (key, value) => { map.set(key, String(value)); }, removeItem: (key) => { map.delete(key); } });
    globalThis.localStorage = browser(); globalThis.sessionStorage = browser();
    const f = fixture();
    f.run(`accountMode = true; accountEmail = 'a@example.com';
      authConfig = { enabled: true, key_check: ${outcome !== 'off'} }`);
    const gate = f.run('showGate(null, { keysOnly: true })');
    // This scenario is about the check. With the box unticked the keys land
    // in the tab, where it can see whether and when they were accepted; the
    // check followed by saving to the account is saved_keys, checked.
    f.get('#byok-save').checked = false;
    const fill = (llmKey) => {
      f.get('#byok-provider').value = 'qwen'; f.get('#byok-model').value = 'qwen3.8-27b';
      f.get('#byok-llm-key').value = llmKey;
      f.get('#byok-search').value = 'tavily'; f.get('#byok-search-key').value = 'fixture-search';
    };
    const send = () => f.get('#byok-form').onsubmit({preventDefault(){}});
    fill('fixture-A');
    const first = send();
    if (outcome === 'off') {
      await first; await gate;
      assert.equal(f.requests.length, 0, 'A deployment without the check is asked nothing');
      assert.equal(api.getByok()?.llmKey, 'fixture-A');
      assert.equal(f.get('#toasts').children.length, 0);
      return;
    }
    assert.equal(f.requests.length, 1);
    assert.equal(f.requests[0].url, '/api/keys/check');
    const sent = JSON.parse(f.requests[0].options.body);
    assert.deepEqual(sent, {llm_provider:'qwen', llm_api_key:'fixture-A', llm_model:'qwen3.8-27b', tavily_api_key:'fixture-search'});
    assert.equal(api.getByok(), null, 'Nothing is saved while the providers are being asked');
    assert.equal(f.get('#byok-submit').disabled, true);
    assert.equal(f.get('#byok-submit').textContent, 'byok_checking');
    await send();
    assert.equal(f.requests.length, 1, 'A second submit while checking asks nobody again');
    if (outcome === 'accepted') {
      f.respond(0, {checked:true, llm:'accepted', model:'listed', search:'accepted'}); await first; await gate;
      assert.equal(api.getByok()?.llmKey, 'fixture-A');
      assert.equal(f.get('#toasts').children.length, 0);
      assert.equal(f.get('#byok-error').hidden, true);
    } else if (outcome === 'unreachable' || outcome === 'unverified') {
      if (outcome === 'unreachable') f.respond(0, {detail:'fixture'}, 500);
      else f.respond(0, {checked:true, llm:'unverified', model:'unknown', search:'accepted'});
      await first; await gate;
      assert.equal(api.getByok()?.llmKey, 'fixture-A', 'A check without an answer does not block saving');
      assert.equal(f.get('#toasts').children.at(-1).textContent, 'byok_unverified');
    } else if (outcome === 'left') {
      // The person closed the form while the providers were being asked.
      f.get('#byok-skip').onclick(); await gate;
      f.respond(0, {checked:true, llm:'accepted', model:'listed', search:'accepted'}); await first;
      assert.equal(api.getByok(), null, 'A late answer cannot save keys into a gate that has closed');
    } else {
      const verdict = outcome === 'model'
        ? {checked:true, llm:'accepted', model:'not_listed', search:'accepted'}
        : {checked:true, llm:'rejected', model:'unknown', search:'rejected'};
      f.respond(0, verdict); await first;
      assert.equal(api.getByok(), null, 'Keys a provider objected to are not saved by the first submit');
      assert.equal(f.get('#byok-error').hidden, false);
      const said = f.get('#byok-error').textContent;
      if (outcome === 'model') assert.equal(said, 'byok_model_not_listed\nbyok_problem_next');
      else assert.equal(said, 'byok_rejected_llm\nbyok_rejected_search\nbyok_problem_next');
      assert.ok(!said.includes('fixture-A'), 'The message never repeats a key');
      assert.equal(f.get('#byok-submit').textContent, 'byok_save_anyway');
      assert.equal(f.get('#byok-submit').disabled, false);
      // An edit withdraws "save anyway": different keys are asked about again.
      fill('fixture-B'); f.get('#byok-form').oninput();
      assert.equal(f.get('#byok-error').hidden, true);
      assert.equal(f.get('#byok-submit').textContent, 'byok_save');
      const second = send();
      assert.equal(f.requests.length, 2);
      assert.equal(JSON.parse(f.requests[1].options.body).llm_api_key, 'fixture-B');
      f.respond(1, verdict); await second;
      assert.equal(api.getByok(), null);
      // The same keys again are the person's decision: saved with no request.
      await send(); await gate;
      assert.equal(f.requests.length, 2);
      assert.equal(api.getByok()?.llmKey, 'fixture-B');
    }
  },
  async saved_keys() {
    // An account's keys are saved with the account: sent once, kept on the
    // server sealed (tests/test_account_keys.py), and not kept in the
    // browser. This is the page's side of that.
    const kind = process.argv[3];
    const local = new Map(), session = new Map();
    const storage = (map) => ({ getItem: (key) => map.get(key) ?? null,
      setItem: (key, value) => { map.set(key, String(value)); }, removeItem: (key) => { map.delete(key); } });
    globalThis.localStorage = storage(local); globalThis.sessionStorage = storage(session);
    const LEFTOVER = 'byok-remembered-v1', DECLINED = 'byok-remember-off';
    const keys = { provider: 'qwen', llmKey: 'fixture-A', search: 'tavily', searchKey: 'fixture-search', model: 'qwen3.8-27b' };
    const sent = { llm_provider: 'qwen', llm_api_key: 'fixture-A', llm_model: 'qwen3.8-27b', tavily_api_key: 'fixture-search' };
    const summary = { saved: true, llm_provider: 'qwen', llm_model: 'qwen3.8-27b', llm_key_hint: '…re-A',
      search: 'tavily', search_key_hint: '…arch', saved_at: '2026-11-15T10:00:00Z' };
    if (kind === 'leftover' || kind === 'sign_out') local.set(LEFTOVER, JSON.stringify({ owner: 'a@example.com', creds: keys }));
    const f = fixture();
    const account = (saved = false) => f.run(`applyAccountMode({ email: 'a@example.com', keys_saved: ${saved} });
      authConfig = { enabled: true, key_check: false }`);
    const fill = () => {
      f.get('#byok-provider').value = keys.provider; f.get('#byok-model').value = keys.model;
      f.get('#byok-llm-key').value = keys.llmKey;
      f.get('#byok-search').value = keys.search; f.get('#byok-search-key').value = keys.searchKey;
    };
    const send = () => f.get('#byok-form').onsubmit({preventDefault(){}});
    const turn = async () => { for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setImmediate(resolve)); };
    const answered = (index, status = 204) => f.requests[index].resolve(new Response(null, { status }));
    const nowhere = () => {
      for (const map of [local, session]) for (const value of map.values()) {
        assert.ok(!value.includes('fixture-A') && !value.includes('fixture-search'), 'No key is left in the browser');
      }
    };
    const box = f.get('#byok-save'), row = f.get('#byok-save-row'), shown = f.get('#byok-saved');
    const started = async () => {
      // An assessment started now: what the request carries.
      f.topic('A topic to assess');
      const before = f.requests.length;
      const pending = f.submit();
      await turn();
      return { request: f.requests[before], before, pending };
    };

    if (kind === 'saved') {
      account();
      const gate = f.run('showGate(null, { keysOnly: true })');
      assert.equal(row.hidden, false, 'An account is offered the choice');
      assert.equal(box.checked, true, '...and saving to the account is the default');
      assert.equal(shown.hidden, true, 'Nothing is saved yet, so nothing is listed');
      fill();
      const saving = send();
      await turn();
      assert.equal(f.requests.length, 1);
      assert.equal(f.requests[0].url, '/api/auth/keys');
      assert.equal(f.requests[0].options.method, 'PUT');
      assert.deepEqual(JSON.parse(f.requests[0].options.body), sent);
      assert.equal(f.run('accountKeysSaved'), false, 'Not saved until the server says so');
      f.respond(0, summary); await saving; await gate;
      assert.equal(f.run('accountKeysSaved'), true);
      assert.equal(api.getByok(), null, 'The browser keeps no key');
      nowhere();
      assert.equal(f.get('#toasts').children.length, 0);
      assert.equal(f.get('#byok-llm-key').value, '', 'The typed keys do not stay in the form');
      assert.equal(f.get('#byok-search-key').value, '');
      // From then on nothing asks for keys, and a run carries none: the server uses the saved ones.
      const { request } = await started();
      assert.equal(request.url, '/api/runs');
      const body = JSON.parse(request.options.body);
      for (const field of ['llm_provider', 'llm_api_key', 'llm_model', 'tavily_api_key', 'serper_api_key']) {
        assert.ok(!(field in body), `${field} is not sent`);
      }
      assert.equal(f.get('#gate').hidden, true, 'No key form in front of the run');
    } else if (kind === 'checked') {
      // Where the deployment checks keys: the providers are asked first, and
      // only then are the keys sent to be saved. A refusal saves nothing.
      account();
      f.run('authConfig = { enabled: true, key_check: true }');
      const gate = f.run('showGate(null, { keysOnly: true })');
      fill();
      const first = send(); await turn();
      assert.deepEqual(f.requests.map((request) => request.url), ['/api/keys/check'], 'Asked about before anything is saved');
      f.respond(0, { checked: true, llm: 'rejected', model: 'unknown', search: 'accepted' }); await first; await turn();
      assert.equal(f.requests.length, 1, 'Keys a provider refused are not saved by that submit');
      assert.equal(f.get('#byok-error').hidden, false);
      assert.equal(f.run('accountKeysSaved'), false);
      // Pressing again is the person's decision: saved with no second question.
      const second = send(); await turn();
      assert.deepEqual(f.requests.map((request) => request.url), ['/api/keys/check', '/api/auth/keys']);
      assert.equal(f.requests[1].options.method, 'PUT');
      f.respond(1, summary); await second; await gate;
      assert.equal(f.run('accountKeysSaved'), true);
      assert.equal(api.getByok(), null);
      nowhere();
    } else if (kind === 'signed_in') {
      // Signing in on any device: the account says whether it has keys.
      account(true);
      assert.equal(f.run('accountHasKeys()'), true);
      const { request } = await started();
      assert.equal(request.url, '/api/runs', 'Straight to the run: no key form');
      assert.ok(!('llm_api_key' in JSON.parse(request.options.body)));
      f.run(`applyAccountMode({ email: 'b@example.com', keys_saved: false })`);
      assert.equal(f.run('accountHasKeys()'), false, 'Another account signing in here has what its own answer says');
      f.run(`applyAccountMode({ email: 'c@example.com' })`);
      assert.equal(f.run('accountHasKeys()'), false, 'An answer that does not say is not a yes');
    } else if (kind === 'tab_only') {
      account();
      const gate = f.run('showGate(null, { keysOnly: true })');
      box.checked = false; fill(); await send(); await gate;
      assert.equal(f.requests.length, 0, 'Nothing is sent to be saved');
      assert.deepEqual(api.getByok(), keys, 'The keys stay in this tab');
      assert.equal(f.run('accountKeysSaved'), false);
      assert.equal(local.get(DECLINED), '1', 'This device declined');
      const { request } = await started();
      assert.equal(JSON.parse(request.options.body).llm_api_key, 'fixture-A', '...and travel with each request, as before');
      // The form opened again shows the choice made, not the default.
      box.checked = true;
      const again = f.run('showGate(null, { keysOnly: true })');
      assert.equal(box.checked, false);
      // Changing one's mind: ticked and saved, the keys leave the tab for the account.
      box.checked = true; fill();
      const saving = send(); await turn();
      assert.equal(f.requests.at(-1).options.method, 'PUT');
      assert.deepEqual(api.getByok(), keys, 'Still the tab-only keys until the server has saved them');
      f.respond(f.requests.length - 1, summary); await saving; await again;
      assert.equal(api.getByok(), null, 'The tab no longer holds what the account now does');
      assert.equal(f.run('accountKeysSaved'), true);
      assert.equal(local.has(DECLINED), false);
      nowhere();
    } else if (kind === 'declined_here') {
      local.set(DECLINED, '1');
      account();
      const gate = f.run('showGate(null, { keysOnly: true })');
      assert.equal(box.checked, false, 'A device that declined stays declined for an account with nothing saved');
      box.checked = true; fill();
      const saving = send(); await turn();
      f.respond(0, summary); await saving; await gate;
      assert.equal(local.has(DECLINED), false, 'Ticking the box again undoes it');
      // An account that does have keys saved is shown the tick whatever the device said.
      local.set(DECLINED, '1');
      const again = f.run('showGate(null, { keysOnly: true })');
      assert.equal(box.checked, true);
      f.get('#byok-skip').onclick(); await again;
    } else if (kind === 'listed' || kind === 'removed' || kind === 'replaced_untick') {
      account(true);
      const gate = f.run('showGate(null, { keysOnly: true })');
      assert.equal(box.checked, true);
      await turn();
      assert.equal(f.requests[0].url, '/api/auth/keys');
      assert.equal(f.requests[0].options?.method ?? 'GET', 'GET');
      assert.equal(shown.hidden, true, 'Nothing is listed before the server has answered');
      f.respond(0, summary); await turn();
      assert.equal(shown.hidden, false);
      const said = f.get('#byok-saved-text').textContent;
      assert.equal(said, 'byok_saved_summary', 'The stand-in strings have no placeholders to fill');
      assert.equal(f.get('#byok-llm-key').value, '', 'No key comes back into the fields');
      if (kind === 'listed') {
        // The account's own words for it: provider, model, and the ends of the keys.
        translations.byok_saved_summary = '{date} / {provider} / {model} / {llm} / {search} / {searchKey}';
        const again = f.run('showGate(null, { keysOnly: true })');
        await turn(); f.respond(1, summary); await turn();
        // Each hint is kept in one piece: a word joiner follows its ellipsis.
        assert.equal(f.get('#byok-saved-text').textContent, '15 Nov 2026 / qwen / qwen3.8-27b / …\u2060re-A / tavily / …\u2060arch',
          'When they were saved, which provider and model, and the ends of the keys');
        assert.equal(f.get('#byok-tab').hidden, true, 'Nothing is in this tab: the account saved its keys');
        // A server that now says nothing is saved (removed on another device): the page believes it.
        const third = f.run('showGate(null, { keysOnly: true })');
        await turn(); f.respond(2, { saved: false }); await turn();
        assert.equal(shown.hidden, true);
        assert.equal(f.run('accountKeysSaved'), false);
        // Each opening replaced the form's handlers: only the last one is there to be closed.
        f.get('#byok-skip').onclick(); await third;
      } else if (kind === 'removed') {
        const removing = f.get('#byok-saved-remove').onclick();
        await turn();
        assert.equal(f.requests[1].url, '/api/auth/keys');
        assert.equal(f.requests[1].options.method, 'DELETE');
        assert.equal(f.run('accountKeysSaved'), true, 'Still saved until the server has removed them');
        answered(1); await removing;
        assert.equal(f.run('accountKeysSaved'), false);
        assert.equal(shown.hidden, true);
        assert.equal(f.get('#toasts').children.at(-1).textContent, 'byok_saved_removed');
        // A removal the server did not make is said, and nothing is claimed.
        f.run('accountKeysSaved = true');
        const failing = f.get('#byok-saved-remove').onclick();
        await turn(); f.respond(2, { detail: 'fixture' }, 500); await failing;
        assert.equal(f.run('accountKeysSaved'), true);
        assert.equal(f.get('#toasts').children.at(-1).textContent, 'byok_saved_remove_failed');
        f.get('#byok-skip').onclick(); await gate;
      } else {
        // New keys entered with the box unticked: this tab only, and the saved set goes.
        box.checked = false; fill(); await send(); await gate;
        assert.deepEqual(api.getByok(), keys);
        assert.equal(f.run('accountKeysSaved'), false);
        await turn();
        assert.equal(f.requests[1].url, '/api/auth/keys');
        assert.equal(f.requests[1].options.method, 'DELETE', 'Keys saved earlier do not stay in use behind "do not save"');
        answered(1); await turn();
        assert.equal(f.get('#toasts').children.length, 0);
      }
    } else if (kind === 'needed_gate') {
      // The form that opens by itself after sign-in, not the one the
      // composer's button opens: keys saved there left the composer saying
      // keys were needed, with the day's allowance dimmed, until a reload.
      const need = () => !f.get('#keys-needed').hidden;
      const marks = {};
      f.get('#quota').classList = { toggle: (name, on) => { marks[name] = on; } };
      account();
      assert.equal(need(), true);
      const gate = f.run('showGate(null, { keysOnly: true })');
      fill();
      const saving = send(); await turn();
      f.respond(0, summary); await saving; await gate;
      assert.equal(need(), false, 'Saved with the account: nothing is needed');
      assert.equal(marks['composer__quota--muted'], false);
      // Kept in the tab instead: keys all the same.
      f.run('accountKeysSaved = false');
      account();
      assert.equal(need(), true);
      const again = f.run('showGate(null, { keysOnly: true })');
      fill(); box.checked = false;
      await send(); await again;
      assert.equal(api.getByok()?.llmKey, 'fixture-A');
      assert.equal(need(), false, 'In the tab: nothing is needed');
    } else if (kind === 'dismiss') {
      // The form's way out says what leaving means. An account whose keys
      // are saved was offered "Add keys later".
      const skip = f.get('#byok-skip');
      const says = () => [skip.textContent, skip.dataset.i18n];
      account(true);
      const gate = f.run('showGate(null, { keysOnly: true })');
      await turn(); f.respond(0, summary); await turn();
      assert.deepEqual(says(), ['byok_close', 'byok_close'], 'Keys are saved: there is nothing to add later');
      assert.equal(skip.hidden, false);
      // Removed: from then on the keys are for later.
      const removing = f.get('#byok-saved-remove').onclick();
      await turn(); answered(1); await removing;
      assert.deepEqual(says(), ['byok_skip', 'byok_skip'], 'The key the language switch reads changes with the word');
      skip.onclick(); await gate;
      // Keys in the tab are keys too; cleared, they are not.
      api.setByok(keys);
      account();
      const again = f.run('showGate(null, { keysOnly: true })');
      await turn();
      assert.deepEqual(says(), ['byok_close', 'byok_close']);
      f.get('#byok-tab-clear').onclick();
      assert.deepEqual(says(), ['byok_skip', 'byok_skip']);
      skip.onclick(); await again;
      // An account with nothing, opening the form: as it always read.
      account();
      const empty = f.run('showGate(null, { keysOnly: true })');
      await turn();
      assert.deepEqual(says(), ['byok_skip', 'byok_skip']);
      skip.onclick(); await empty;
    } else if (kind.startsWith('model_')) {
      // The saved keys' model, changed on its own: the keys are not typed
      // again, and the page has none to send.
      account(true);
      if (kind === 'model_checked') f.run('authConfig = { enabled: true, key_check: true }');
      // byok_fields.js listens for typing in this field and says when a name
      // is another kind of model's; a saved name reaches it as an input event.
      const announced = [];
      f.run('globalThis.Event = function Event(type, init) { this.type = type; this.bubbles = init?.bubbles === true; }');
      f.get('#byok-saved-model').dispatchEvent = (event) => { announced.push([event.type, event.bubbles, f.get('#byok-saved-model').value]); };
      const gate = f.run('showGate(null, { keysOnly: true })');
      await turn(); f.respond(0, summary); await turn();
      const field = f.get('#byok-saved-model'), save = f.get('#byok-saved-model-save'), line = f.get('#byok-saved-check');
      assert.deepEqual(announced, [['input', true, 'qwen3.8-27b']], 'The saved name is announced once, after the field holds it');
      const type = (value) => { field.value = value; field.oninput(); };
      assert.equal(field.value, 'qwen3.8-27b', 'The field starts with the model that is saved');
      assert.equal(field.dataset.provider, 'qwen', 'The suggestions are the saved provider\'s');
      assert.equal(save.disabled, true, 'Nothing to save until it differs');
      assert.equal(f.get('#byok-llm-key').value, '', 'No key field is filled');
      type('  '); assert.equal(save.disabled, true, 'An empty name is not a model');
      type(' qwen3.8-27b '); assert.equal(save.disabled, true, 'The same name, with spaces, is no change');
      await save.onclick();
      assert.equal(f.requests.length, 1, 'Pressed all the same, it asks for nothing');
      type(' qwen3.8-max ');
      assert.equal(save.disabled, false);
      line.hidden = false; line.textContent = 'what the last check said';
      let prevented = 0;
      const pressing = kind === 'model_enter'
        ? (field.onkeydown({ key: 'a', preventDefault() { prevented += 1; } }),
           field.onkeydown({ key: 'Enter', preventDefault() { prevented += 1; } }))
        : save.onclick();
      if (kind === 'model_enter') assert.equal(prevented, 1, 'Enter must not submit the form for new keys; other keys are typing');
      await turn();
      const sent = f.requests[1];
      assert.equal(sent.url, '/api/auth/keys');
      assert.equal(sent.options.method, 'PATCH');
      assert.deepEqual(JSON.parse(sent.options.body), { llm_model: 'qwen3.8-max' }, 'The model alone, trimmed: no key, no provider');
      assert.equal(save.disabled, true, 'Not twice while it is being changed');
      assert.equal(line.hidden, true, 'What a check said was about the model before');
      await save.onclick();
      assert.equal(f.requests.length, 2);
      const changed = { ...summary, llm_model: 'qwen3.8-max', saved_at: '2026-11-16T09:00:00Z' };
      translations.byok_saved_summary = '{date} / {provider} / {model}';
      translations.byok_saved_model_changed = 'changed to {model}';
      const toasts = () => f.get('#toasts').children.map((node) => node.textContent);
      if (kind === 'model_ok' || kind === 'model_enter') {
        f.respond(1, changed); await pressing; await turn();
        assert.equal(f.get('#byok-saved-text').textContent, '16 Nov 2026 / qwen / qwen3.8-max');
        assert.equal(field.value, 'qwen3.8-max', 'The field holds what is saved now');
        assert.deepEqual(announced.at(-1), ['input', true, 'qwen3.8-max'], 'And the note is told of the new name');
        assert.equal(save.disabled, true, 'Saved: nothing left to save');
        assert.deepEqual(toasts(), ['changed to qwen3.8-max']);
        assert.equal(f.requests.length, 2, 'A deployment that checks no keys asks nobody about the new model');
        assert.equal(line.hidden, true);
        assert.equal(f.run('accountKeysSaved'), true);
        // And back again: the saved name is what a change is measured against.
        type('qwen3.8-27b');
        assert.equal(save.disabled, false);
      } else if (kind === 'model_checked') {
        f.respond(1, changed); await turn();
        assert.equal(f.requests[2].url, '/api/auth/keys/check', 'Where keys are checked, the provider is asked about the set as it now is');
        assert.equal(f.requests[2].options.method, 'POST');
        translations.byok_saved_check_problem = '{time}:';
        f.respond(2, { checked: true, llm: 'accepted', model: 'not_listed', search: 'accepted' }); await pressing;
        assert.equal(line.hidden, false);
        assert.match(line.textContent, /^\d\d:\d\d:\nbyok_model_not_listed\nbyok_saved_check_next$/);
        assert.deepEqual(toasts(), ['changed to qwen3.8-max'], 'Changed all the same: the check advises');
        assert.equal(field.value, 'qwen3.8-max');
      } else if (kind === 'model_invalid') {
        f.respond(1, { detail: [{ loc: ['body', 'llm_model'], msg: 'x', type: 'value_error' }] }, 422); await pressing;
        assert.deepEqual([line.hidden, line.textContent], [false, 'byok_saved_model_invalid']);
        assert.equal(field.value, ' qwen3.8-max ', 'What was typed stays, to be corrected');
        assert.equal(save.disabled, false);
        assert.equal(f.get('#byok-saved-text').textContent.includes('qwen3.8-max'), false, 'Nothing is shown as saved that was not');
        assert.deepEqual(toasts(), []);
      } else if (kind === 'model_empty') {
        // A reply that does not say the set is saved is not a change to announce.
        f.respond(1, { saved: false }); await pressing;
        assert.deepEqual([line.hidden, line.textContent], [false, 'byok_saved_model_failed']);
        assert.deepEqual(toasts(), []);
        assert.equal(f.get('#byok-saved-text').textContent.includes('qwen3.8-max'), false);
        assert.equal(save.disabled, false);
      } else if (kind === 'model_failed') {
        f.respond(1, { detail: 'fixture' }, 500); await pressing;
        assert.deepEqual([line.hidden, line.textContent], [false, 'byok_saved_model_failed']);
        assert.equal(save.disabled, false, 'It can be tried again');
        assert.deepEqual(toasts(), []);
      } else if (kind === 'model_unreachable') {
        f.requests[1].reject(new TypeError('Failed to fetch')); await pressing;
        assert.deepEqual([line.hidden, line.textContent], [false, 'msg_network']);
        assert.equal(save.disabled, false);
      } else if (kind === 'model_gone') {
        // Removed on another device since the form opened.
        f.respond(1, { detail: 'No keys are saved with this account.' }, 409, 'no_saved_keys'); await pressing;
        assert.equal(f.get('#byok-saved').hidden, true);
        assert.equal(f.run('accountKeysSaved'), false);
        assert.equal(f.get('#keys-needed').hidden, false, 'The composer says keys are needed');
        assert.deepEqual(toasts(), []);
      } else {
        assert.equal(kind, 'model_conflict');
        // Replaced on another device while this was changing: what is there now is shown, and said.
        f.respond(1, { detail: 'replaced' }, 409, 'keys_changed'); await turn();
        assert.equal(f.requests[2].url, '/api/auth/keys');
        assert.equal(f.requests[2].options?.method ?? 'GET', 'GET', 'It reads what is saved now');
        f.respond(2, { ...summary, llm_provider: 'deepseek', llm_model: 'deepseek-chat' }); await pressing;
        assert.equal(f.get('#byok-saved-text').textContent, '15 Nov 2026 / deepseek / deepseek-chat');
        assert.equal(field.value, 'deepseek-chat');
        assert.deepEqual([line.hidden, line.textContent], [false, 'byok_saved_model_conflict']);
        assert.deepEqual(toasts(), []);
      }
      f.get('#byok-skip').onclick(); await gate;
    } else if (kind.startsWith('check_')) {
      // "Check these keys": the page has only the ends of the saved keys, so
      // the server asks the providers and the page says what they said, and when.
      account(true);
      const gate = f.run('showGate(null, { keysOnly: true })');
      await turn(); f.respond(0, summary); await turn();
      const line = f.get('#byok-saved-check'), button = f.get('#byok-saved-check-now');
      assert.equal(line.hidden, true, 'Nothing is claimed before anyone was asked');
      translations.byok_saved_check_ok = '{time} | {provider} | {service}';
      translations.byok_saved_check_problem = '{time}:';
      const asking = button.onclick();
      await turn();
      assert.equal(f.requests[1].url, '/api/auth/keys/check');
      assert.equal(f.requests[1].options.method, 'POST');
      assert.equal(f.requests[1].options.body, undefined, 'No key is sent: the page has none to send');
      assert.deepEqual([line.hidden, line.textContent, button.disabled], [false, 'byok_saved_checking', true]);
      await button.onclick();
      assert.equal(f.requests.length, 2, 'A second press while asking asks nobody again');
      const answer = { ok: { checked: true, llm: 'accepted', model: 'listed', search: 'accepted' },
        rejected: { checked: true, llm: 'rejected', model: 'unknown', search: 'accepted' },
        model: { checked: true, llm: 'accepted', model: 'not_listed', search: 'rejected' },
        unverified: { checked: true, llm: 'unverified', model: 'unknown', search: 'accepted' },
        off: { checked: false, llm: 'unverified', model: 'unknown', search: 'unverified' } }[kind.slice(6)];
      if (answer) {
        f.respond(1, answer); await asking;
        const said = line.textContent;
        if (kind === 'check_ok') assert.match(said, /^\d\d:\d\d \| Qwen \| Tavily$/, 'When, and who accepted what');
        else if (kind === 'check_rejected') assert.match(said, /^\d\d:\d\d:\nbyok_rejected_llm\nbyok_saved_check_next$/);
        else if (kind === 'check_model') assert.match(said, /^\d\d:\d\d:\nbyok_model_not_listed\nbyok_rejected_search\nbyok_saved_check_next$/);
        else if (kind === 'check_unverified') assert.equal(said, 'byok_saved_check_unverified', 'No answer is not "accepted"');
        else assert.equal(said, 'byok_saved_check_off');
        assert.ok(!said.includes('byok_problem_next'), 'The advice for keys being typed ("save anyway") is not given for saved ones');
        assert.equal(f.run('accountKeysSaved'), true, 'What the providers say changes nothing by itself');
        assert.equal(f.get('#byok-saved').hidden, false);
      } else if (kind === 'check_failed') {
        f.respond(1, { detail: 'fixture' }, 500); await asking;
        assert.equal(line.textContent, 'byok_saved_check_failed');
      } else if (kind === 'check_limited') {
        f.respond(1, { detail: 'Too many key checks.' }, 429, 'rate_limited'); await asking;
        assert.equal(line.textContent, 'byok_saved_check_failed');
      } else if (kind === 'check_unreachable') {
        f.requests[1].reject(new TypeError('Failed to fetch')); await asking;
        assert.equal(line.textContent, 'msg_network', 'Said as what it is, in the interface language');
      } else {
        assert.equal(kind, 'check_gone');
        // Removed on another device since the form opened.
        f.respond(1, { detail: 'No keys are saved with this account.' }, 409, 'no_saved_keys'); await asking;
        assert.equal(f.get('#byok-saved').hidden, true);
        assert.equal(f.run('accountKeysSaved'), false);
        assert.equal(f.get('#keys-needed').hidden, false, '...and the composer says keys are needed');
      }
      assert.equal(button.disabled, false);
      f.get('#byok-skip').onclick(); await gate;
    } else if (kind === 'folded') {
      // An account that has saved keys opens the form to change something
      // about them far more often than to type a new set. Until 2026-11-18
      // the fields for a new set stood open under the saved ones, on DeepSeek
      // whatever was saved. They are folded away now behind "Replace keys",
      // and open on the saved provider, model and search service.
      const fresh = f.get('#byok-new'), replace = f.get('#byok-replace'), title = f.get('#byok-title');
      const said = {}, focused = [], heard = [];
      // The page announces a filled field as typing or choosing would; this stand-in records it.
      f.run('globalThis.Event = function Event(type, init) { this.type = type; this.bubbles = init?.bubbles === true; }');
      replace.setAttribute = (name, value) => { said[name] = String(value); };
      for (const id of ['#byok-title', '#byok-llm-key', '#byok-replace']) f.get(id).focus = () => { focused.push(id); };
      for (const id of ['#byok-provider', '#byok-search', '#byok-model']) {
        f.get(id).dispatchEvent = (event) => { heard.push([id, event.type, event.bubbles, f.get(id).value]); };
      }
      account(true);
      const gate = f.run('showGate(null, { keysOnly: true })');
      assert.equal(fresh.hidden, true, 'Folded at once: the account said at sign-in that it has keys');
      assert.deepEqual(focused, ['#byok-title'], 'The cursor is not put in a key field that is not shown');
      assert.equal(shown.hidden, true, 'What is saved is listed when the server has said');
      await turn(); f.respond(0, summary); await turn();
      assert.equal(shown.hidden, false);
      assert.equal(fresh.hidden, true, 'Still folded: the saved set and what can be done with it');
      assert.equal(replace.hidden, false);
      assert.equal(said['aria-expanded'], 'false');
      assert.deepEqual(heard, [], 'Nothing is filled in while the fields are folded away');

      replace.onclick();
      assert.equal(fresh.hidden, false, 'One press opens the fields for a new set');
      assert.equal(said['aria-expanded'], 'true');
      assert.deepEqual([f.get('#byok-provider').value, f.get('#byok-search').value, f.get('#byok-model').value],
        ['qwen', 'tavily', 'qwen3.8-27b'], 'They start on what is saved, not on the first provider in the list');
      assert.deepEqual(heard, [['#byok-provider', 'change', true, 'qwen'], ['#byok-search', 'change', true, 'tavily'],
        ['#byok-model', 'input', true, 'qwen3.8-27b']],
        'Each is told as a choice would be, the provider before its model: the notes under the fields follow');
      assert.equal(f.get('#byok-llm-key').value, '', 'No key is filled in: the page has none');
      assert.equal(f.get('#byok-search-key').value, '');
      assert.equal(focused.at(-1), '#byok-llm-key', 'The cursor goes to the first thing to type');
      // Typed something, then thought better of it: folded again, and the next opening starts from what is saved.
      f.get('#byok-provider').value = 'openai'; f.get('#byok-model').value = 'gpt-4o'; f.get('#byok-llm-key').value = 'typed';
      replace.onclick();
      assert.equal(fresh.hidden, true);
      assert.equal(said['aria-expanded'], 'false');
      assert.equal(f.get('#byok-llm-key').value, '', 'A key typed and put away does not wait in a hidden field');
      replace.onclick();
      assert.deepEqual([f.get('#byok-provider').value, f.get('#byok-model').value], ['qwen', 'qwen3.8-27b']);
      // Saving a new set from the opened fields is the submit it always was.
      fill();
      const saving = send(); await turn();
      assert.equal(f.requests.at(-1).options.method, 'PUT');
      f.respond(f.requests.length - 1, summary); await saving; await gate;

      // Removed on another device since sign-in: the server says so, and the fields are what is left to show.
      const second = f.run('showGate(null, { keysOnly: true })');
      assert.equal(fresh.hidden, true);
      await turn(); f.respond(f.requests.length - 1, { saved: false }); await turn();
      assert.equal(fresh.hidden, false, 'Nothing is saved: the form for a new set, as for a new account');
      assert.equal(shown.hidden, true);
      assert.equal(f.run('accountKeysSaved'), false);
      f.get('#byok-skip').onclick(); await second;

      // What is saved could not be read: the fields open, since a card with nothing on it helps nobody.
      f.run('accountKeysSaved = true');
      const third = f.run('showGate(null, { keysOnly: true })');
      assert.equal(fresh.hidden, true);
      await turn(); f.respond(f.requests.length - 1, { detail: 'fixture' }, 500); await turn();
      assert.equal(fresh.hidden, false);
      assert.equal(shown.hidden, true);
      assert.equal(f.run('accountKeysSaved'), true, 'An answer that failed is not an answer that nothing is saved');
      f.get('#byok-skip').onclick(); await third;

      // Removing the saved set from the form leaves the fields for a new one.
      const fourth = f.run('showGate(null, { keysOnly: true })');
      await turn(); f.respond(f.requests.length - 1, summary); await turn();
      assert.equal(fresh.hidden, true);
      const removing = f.get('#byok-saved-remove').onclick();
      await turn(); answered(f.requests.length - 1); await removing;
      assert.equal(fresh.hidden, false);
      assert.equal(shown.hidden, true);
      f.get('#byok-skip').onclick(); await fourth;

      // An account with nothing saved, and a visitor with no account: the fields, open, with the cursor in the first.
      account(false);
      focused.length = 0;
      const fifth = f.run('showGate(null, { keysOnly: true })');
      assert.equal(fresh.hidden, false);
      assert.deepEqual(focused, ['#byok-llm-key']);
      f.get('#byok-skip').onclick(); await fifth;
      f.run('accountMode = false; authConfig = { enabled: false }');
      focused.length = 0;
      const sixth = f.run('showGate(null, { keysOnly: true })');
      assert.equal(fresh.hidden, false);
      assert.deepEqual(focused, ['#byok-llm-key']);
      void sixth; void title;
    } else if (kind === 'tab_listed') {
      // Keys the account chose not to save are in this tab. The form opened
      // empty over them: no telling which they were, and no way to drop them.
      const held = { ...keys, llmKey: 'sk-fixture-model-key-0123abcd', searchKey: 'tvly-fixture-search-9876wxyz' };
      api.setByok(held);
      account();
      translations.byok_tab_summary = '{provider} / {model} / {llm} / {search} / {searchKey}';
      const gate = f.run('showGate(null, { keysOnly: true })');
      await turn();
      assert.equal(f.requests.length, 0, 'Nothing is asked of the server: these keys are not there');
      assert.equal(f.get('#byok-saved').hidden, true);
      assert.equal(f.get('#byok-tab').hidden, false);
      const said = f.get('#byok-tab-text').textContent;
      assert.equal(said, 'qwen / qwen3.8-27b / …\u2060abcd / tavily / …\u2060wxyz', 'Which keys, by their last four characters');
      assert.ok(!said.includes('sk-fixture') && !said.includes('tvly-fixture'), 'Never more of a key than its end');
      assert.equal(f.get('#byok-llm-key').value, '', 'The fields stay empty');
      assert.equal(f.get('#keys-needed').hidden, true, 'The account has keys, in this tab');
      // A key too short for four characters to be a small part of it shows none of it.
      api.setByok(keys);
      const again = f.run('showGate(null, { keysOnly: true })');
      assert.equal(f.get('#byok-tab-text').textContent, 'qwen / qwen3.8-27b / … / tavily / …\u2060arch');
      // Cleared: gone from the tab, and the composer says keys are needed again.
      f.get('#byok-tab-clear').onclick();
      assert.equal(api.getByok(), null);
      assert.equal(session.size, 0);
      assert.equal(f.get('#byok-tab').hidden, true);
      assert.equal(f.get('#toasts').children.at(-1).textContent, 'byok_tab_cleared');
      assert.equal(f.get('#keys-needed').hidden, false);
      assert.equal(f.run('byokMode'), false);
      f.get('#byok-skip').onclick(); await again;
      // A visitor with keys alone is shown no such block: their keys are their way in, and "Exit" is how they leave.
      api.setByok(held);
      f.run('accountMode = false; authConfig = { enabled: false }');
      const third = f.run('showGate(null, { keysOnly: true })');
      assert.equal(f.get('#byok-tab').hidden, true);
      f.get('#byok-llm-key').value = ''; void gate; void third;
    } else if (kind === 'needed') {
      // An account with no keys, no trial and nobody paying: the composer says so.
      const need = () => !f.get('#keys-needed').hidden;
      const marks = {};
      f.get('#quota').classList = { toggle: (name, on) => { marks[name] = on; } };
      const dimmed = () => marks['composer__quota--muted'];
      f.run('paintTrialNote()');
      assert.equal(dimmed(), false);
      assert.equal(need(), false, 'Not said to someone who is not signed in to an account');
      account();
      assert.equal(need(), true);
      assert.equal(f.run('keysNeeded()'), true);
      assert.equal(dimmed(), true, "The day's allowance is not what stands in the way");
      // The button opens the key form; saving there takes the line away.
      const opened = f.get('#keys-needed-add').listeners.click();
      assert.equal(f.get('#byok-form').hidden, false);
      fill();
      const saving = send(); await turn();
      f.respond(0, summary); await saving; await opened;
      assert.equal(need(), false, 'Keys saved: nothing is needed');
      assert.equal(dimmed(), false);
      // Removed again, it comes back; so it does when the server refuses for want of keys.
      const reopened = f.get('#keys-needed-add').listeners.click();
      await turn(); f.respond(1, summary); await turn();
      const removing = f.get('#byok-saved-remove').onclick();
      await turn(); answered(2); await removing;
      assert.equal(need(), true);
      f.get('#byok-skip').onclick(); await reopened;
      // Not for an account that has another way to pay.
      f.run(`applyAccountMode({ email: 'a@example.com', keys_saved: false, verified: true, trial_runs_left: 1 })`);
      assert.equal(need(), false, 'A free first assessment needs no keys');
      f.run(`authConfig = { enabled: true, admin_funded: true }; applyAccountMode({ email: 'a@example.com', keys_saved: false, admin: true })`);
      assert.equal(need(), false, 'An administrator the deployment pays for');
      f.run(`authConfig = { enabled: true }; applyAccountMode({ email: 'a@example.com', keys_saved: true })`);
      assert.equal(need(), false);
      // What the reader is told when the server cannot be reached.
      assert.equal(f.run('errorText({ code: "network_unreachable", message: "English from the client" })'), 'msg_network');
      assert.equal(f.run('errorText({ code: "rate_limited", message: "What the server said" })'), 'What the server said');
      assert.equal(f.run('operationErrorMessage({ code: "network_unreachable", message: "x", status: 0 })'), 'msg_network');
    } else if (kind === 'save_failed') {
      account();
      let finished = false;
      const gate = f.run('showGate(null, { keysOnly: true })').then(() => { finished = true; });
      fill();
      const saving = send(); await turn();
      f.respond(0, { detail: 'fixture' }, 500); await saving; await turn();
      assert.equal(finished, false, 'The form stays: nothing was saved');
      assert.equal(f.get('#byok-error').hidden, false);
      assert.equal(f.get('#byok-error').textContent, 'byok_to_account_failed');
      assert.equal(f.get('#byok-submit').disabled, false);
      assert.equal(f.run('accountKeysSaved'), false);
      assert.equal(api.getByok(), null, 'Keys that could not be saved are not quietly kept in the tab instead');
      assert.equal(f.get('#byok-llm-key').value, 'fixture-A', 'What was typed is still there to try again');
      // The second attempt goes through.
      const again = send(); await turn();
      f.respond(1, summary); await again; await gate;
      assert.equal(f.run('accountKeysSaved'), true);
    } else if (kind === 'refused_later') {
      // The page believed keys were saved; the server found none it could use.
      account(true);
      const { request, before, pending } = await started();
      assert.equal(request.url, '/api/runs');
      f.respond(before, { detail: 'Accounts run on their own API keys.' }, 401, 'byok_required');
      await pending;
      assert.equal(f.run('accountKeysSaved'), false, 'The next attempt asks for keys instead of being refused again');
      assert.equal(f.get('#toasts').children.at(-1).textContent, 'msg_byok_required');
      assert.equal(f.get('#keys-needed').hidden, false, 'The composer says so from then on');
    } else if (kind === 'visitor') {
      // Keys alone and no account: there is no account to save them with.
      f.run('authConfig = { enabled: false }');
      box.checked = true; row.hidden = false; shown.hidden = false;
      const gate = f.run('showGate(null, { keysOnly: true })');
      assert.equal(row.hidden, true, 'The choice is not offered');
      assert.equal(box.checked, false, '...and a tick left from an account does not carry over');
      assert.equal(shown.hidden, true);
      box.checked = true; fill(); await send(); await gate;
      assert.equal(f.requests.length, 0, 'Even a tick that got through saves nothing');
      assert.deepEqual(api.getByok(), keys);
    } else if (kind === 'leftover') {
      // A copy of the keys the earlier design left in this browser: removed at boot, never used.
      assert.equal(local.has(LEFTOVER), false);
      account();
      assert.equal(api.getByok(), null);
      assert.equal(f.run('accountHasKeys()'), false);
    } else {
      assert.equal(kind, 'sign_out');
      account(true);
      local.set(LEFTOVER, JSON.stringify({ owner: 'a@example.com', creds: keys }));
      f.run('location.replace = (url) => { globalThis.wentTo = url; }');
      const exit = f.run('exitCredentials()');
      assert.equal(f.run('accountKeysSaved'), false);
      await turn();
      assert.deepEqual(f.requests.map((request) => request.url), ['/api/auth/logout'],
        'Signing out removes nothing from the account: its keys are there at the next sign-in');
      f.respond(0, { ok: true }); await exit;
      assert.equal(f.run('globalThis.wentTo'), '/', 'A clean sign-out starts over at the front door');
      assert.equal(local.size, 0, 'Nothing of the account is left in this browser');
    }
  },
  async account_preview() {
    // An account's run button first shows how the planner read the topic,
    // on the account's own key; a code holder's preview sends no key.
    const kind = process.argv[3];
    const f = fixture();
    const label = actualRunView.planLabel;
    if (kind === 'signin') {
      // Signing in through the gate: the boot's access check was refused and
      // said nothing about previews; the configuration with the refusal did.
      api.setByok({ provider: 'qwen', llmKey: 'fixture-key', model: 'qwen3.8-27b', search: 'tavily', searchKey: 'fixture-search' });
      f.run('authConfig = { enabled: true, signup_open: true, signup: "open", access_codes: false, plan_preview: true }');
      const gate = f.run('showGate()');
      assert.equal(f.run('planPreviewEnabled'), false);
      f.get('#account-email-input').value = 'a@example.com';
      f.get('#account-password').value = 'a long enough password';
      const signedIn = f.get('#account-form').onsubmit({preventDefault(){}});
      assert.equal(f.requests[0].url, '/api/auth/login');
      f.respond(0, { token: 'fixture-session', email: 'a@example.com', admin: false });
      await signedIn; await gate;
      assert.equal(f.run('accountMode'), true);
      assert.equal(f.run('planPreviewEnabled'), true, 'An account that has just signed in gets the preview too');
      f.topic('hyperloop');
      f.submit();
      assert.equal(f.requests[1].url, '/api/plan');
      assert.equal(JSON.parse(f.requests[1].options.body).llm_api_key, 'fixture-key');
      return;
    }
    const plan = { planned: true, resolved: true, search_topic: 'hyperloop transportation system',
      aliases: ['vacuum tube maglev train'], components: [] };
    // An account with no keys in the tab whose preview the deployment pays
    // for: an administrator it funds, or a newcomer on a trial assessment.
    // Seen on production on 2026-11-11: such a preview ended "one small
    // request on your model key", said to someone with no key.
    const funded = ['admin', 'trial', 'trial_silent'].includes(kind);
    if (kind === 'code') {
      api.setAccessCode('fixture-code');
      f.run('planPreviewEnabled = true');
    } else if (funded) {
      f.run(kind === 'admin'
        ? 'accountMode = true; accountAdmin = true; authConfig = { admin_funded: true }; planPreviewEnabled = true'
        : 'accountMode = true; accountVerified = true; accountTrialLeft = 1; planPreviewEnabled = true');
    } else {
      api.setByok({ provider: 'qwen', llmKey: 'fixture-key', model: 'qwen3.8-27b', search: 'tavily', searchKey: 'fixture-search' });
      f.run(`accountMode = true; byokMode = true; planPreviewEnabled = ${kind !== 'off'}`);
    }
    f.topic('hyperloop');
    const scrolled = [];
    f.get('#plan-panel').scrollIntoView = (options) => scrolled.push(options.block);
    const submitted = f.submit();
    if (kind === 'off') {
      await Promise.resolve();
      assert.equal(f.requests[0].url, '/api/runs', 'With previews off an account starts as before');
      return;
    }
    assert.equal(f.requests.length, 1);
    assert.equal(f.requests[0].url, '/api/plan');
    const sent = JSON.parse(f.requests[0].options.body);
    if (kind === 'code' || funded) {
      assert.deepEqual(sent, { topic: 'hyperloop' }, 'Whoever has no key sends none');
    } else {
      assert.deepEqual(sent, { topic: 'hyperloop', llm_provider: 'qwen', llm_api_key: 'fixture-key',
        llm_model: 'qwen3.8-27b', tavily_api_key: 'fixture-search' });
    }
    // The planner takes seconds. Until 2026-11-11 the only sign that anything
    // had been asked was the run button's tooltip: the page looked as if the
    // press had done nothing. The panel now says so at once, where the
    // reading will appear, with nothing to press yet.
    const waiting = f.get('#plan-panel');
    assert.equal(waiting.hidden, false, 'The panel is there as soon as the planner is asked');
    assert.deepEqual(waiting.children.map((node) => node.textContent), [label('title'), label('previewing')]);
    // On a phone the panel opens below the fold: the composer fills the
    // screen and the reading, with the button that starts the run, appeared
    // where nobody was looking. It is brought into view, and no further than
    // it needs to be.
    assert.deepEqual(scrolled, ['nearest'], 'The waiting line is brought into view');
    const silent = kind === 'silent' || kind === 'trial_silent';
    f.respond(0, silent ? { ...plan, planned: false, search_topic: 'hyperloop', aliases: [] } : plan);
    await submitted;
    assert.deepEqual(scrolled, ['nearest', 'nearest'], '...and so is the reading, which is taller');
    const panel = f.get('#plan-panel');
    assert.equal(panel.hidden, false);
    const [title, lede] = panel.children;
    assert.equal(title.textContent, label('title'));
    const texts = JSON.stringify(panel.children, (key, value) => (key === 'listeners' ? undefined : value));
    if (silent) {
      // "Your model did not answer: check your key under API keys" sends
      // someone with no key to look for one. They are told what a code
      // holder is told: no answer, and the run can be started anyway.
      assert.equal(lede.textContent, label(funded ? 'no_answer' : 'no_answer_own'));
      assert.ok(!texts.includes('"value":"hyperloop"'), 'The topic as typed is not shown as a reading');
    } else {
      const said = { code: 'lede', admin: 'lede_funded', trial: 'lede_funded' }[kind] ?? 'lede_own';
      assert.equal(typeof label(said), 'string');
      assert.equal(lede.textContent, label(said), 'The preview says whose key it was made on');
      assert.ok(texts.includes('hyperloop transportation system'));
    }
    assert.equal(f.requests.length, 1, 'Nothing is started until the reading is confirmed');
  },
  async preview_waiting() {
    // The waiting panel must not outlive the question it was waiting on.
    const kind = process.argv[3];
    const f = fixture();
    api.setAccessCode('fixture-code');
    f.run('planPreviewEnabled = true');
    f.topic('hyperloop');
    const submitted = f.submit();
    const panel = f.get('#plan-panel');
    assert.equal(panel.hidden, false);
    assert.equal(panel.children.length, 2, 'A title and the waiting line, nothing to press');
    if (kind === 'changed') {
      // A reading of a topic the user has since changed would confirm the wrong one.
      f.topic('something else entirely');
      f.respond(0, { planned: true, resolved: true, search_topic: 'hyperloop transportation system', aliases: [], components: [] });
      await submitted;
      assert.equal(panel.hidden, true, 'No reading is shown, and the waiting line is gone with it');
      assert.equal(panel.children.length, 0);
      assert.equal(f.run('planState'), null);
    } else if (kind === 'refused') {
      f.respond(0, { detail: 'Sign in.' }, 401);
      await submitted;
      assert.equal(panel.hidden, true, 'A refusal is said in a toast; the panel does not stay waiting');
      assert.equal(panel.children.length, 0);
    } else {
      // A planner that cannot be reached still ends in the panel, with the reason and a way on.
      f.respond(0, { detail: 'The planner is unavailable.' }, 503);
      await submitted;
      assert.equal(panel.hidden, false);
      assert.ok(panel.children.length > 2, 'The reason and the buttons replace the waiting line');
      assert.notEqual(panel.children[1].textContent, actualRunView.planLabel('previewing'));
    }
  },
  async plan_phrase() {
    // A search phrase edited into Chinese was admitted, counted as the day's
    // run and then stopped before any search (topic_not_translated). The
    // panel now says so before anything is started.
    const kind = process.argv[3];
    const f = fixture();
    const label = actualRunView.planLabel;
    api.setAccessCode('fixture-code');
    f.run('planPreviewEnabled = true');
    f.topic('超级高铁的商业潜力');
    const submitted = f.submit();
    f.respond(0, { planned: true, resolved: true, search_topic: 'hyperloop transportation system',
      aliases: ['vacuum tube maglev train'], components: [] });
    await submitted;
    const phrase = { chinese: '超级高铁', mixed: 'hyperloop 超级高铁', short: ' h ', english: '  hyperloop   ' }[kind];
    f.run(`planState.plan.search_topic = ${JSON.stringify(phrase)}`);
    const started = f.run('startFromPlan()');
    for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setImmediate(resolve));
    if (kind === 'english') {
      // The run's POST is left unanswered: what it carries is the seam.
      assert.equal(f.requests.length, 2);
      assert.equal(f.requests[1].url, '/api/runs');
      assert.deepEqual(JSON.parse(f.requests[1].options.body).search_plan,
        { search_topic: 'hyperloop', aliases: ['vacuum tube maglev train'], components: [] });
      return;
    }
    assert.equal(f.requests.length, 1, 'Nothing is started on a phrase the run would not search');
    await started;
    const said = kind === 'short' ? 'too_short' : 'not_english';
    assert.equal(f.get('#toasts').children.at(-1).textContent, label(said));
  },
  async cancel_feedback() {
    // Every poll repaints the run's actions. Until 2026-11-11 that replaced a
    // Cancel that had just been pressed with a fresh, enabled one: for the
    // seconds the server takes to stop a worker the page looked as if the
    // press had not registered, and invited a second.
    const kind = process.argv[3];
    const f = fixture();
    f.run(`activeRunId = "running-one";
      follower = { stop() {}, poll() { globalThis.polled = (globalThis.polled || 0) + 1; } };
      paintActions("running")`);
    const button = () => f.get('#run-actions').children.find((el) => ['cancel', 'cancelling'].includes(el.textContent));
    const first = button();
    assert.equal(first.textContent, 'cancel');
    assert.equal(first.disabled, false);
    const pressed = first.listeners.click();
    assert.equal(first.disabled, true, 'Pressed once, it cannot be pressed again');
    assert.equal(first.textContent, 'cancelling', '...and it says what is happening');
    assert.equal(f.requests.length, 1);
    assert.equal(f.requests[0].url, '/api/runs/running-one?intent=cancel');
    assert.equal(f.requests[0].options.method, 'DELETE');

    f.run('paintActions("running")');
    const repainted = button();
    assert.notEqual(repainted, first, 'A poll replaced the button');
    assert.equal(repainted.disabled, true, '...and the replacement still knows it was pressed');
    assert.equal(repainted.textContent, 'cancelling');
    // A disabled button takes no clicks in a browser; the handler does not rely on it.
    first.listeners.click();
    repainted.listeners.click();
    assert.equal(f.requests.length, 1, 'One cancel is sent, however often it is pressed');
    f.run('activeRunId = "another-run"; paintActions("running")');
    assert.equal(button().disabled, false, 'Another run\'s Cancel is its own');
    assert.equal(button().textContent, 'cancel');
    f.run('activeRunId = "running-one"; paintActions("running")');
    if (kind === 'pending') return;

    if (kind === 'done') {
      f.respond(0, {});
      await pressed;
      assert.equal(f.run('globalThis.polled'), 1, 'The header is asked for now, not at the next poll');
      assert.equal(f.requests.length, 1);
      f.run('paintActions("running")');
      assert.equal(button().disabled, true, 'Until the run is seen to have stopped, it stays pressed');
      f.run('paintActions("cancelled")');
      assert.equal(button(), undefined, 'A stopped run has no Cancel');
      assert.equal(f.run('cancelling.size'), 0, 'What was pressed is forgotten once the run is seen to have stopped');
    } else {
      f.respond(0, { detail: 'The run already finished.' }, 409);
      await pressed;
      const again = button();
      assert.equal(again.disabled, false, 'A cancel the server refused can be tried again');
      assert.equal(again.textContent, 'cancel');
      assert.equal(f.run('globalThis.polled'), undefined);
    }
  },
  async invite_hint() {
    // Creating an account in invite mode: the form says who gives out codes.
    const kind = process.argv[3];
    const contact = { address: 'ops@example.org', sentence: 'Ask in the <b>help</b> channel', none: null }[kind];
    const f = fixture();
    f.run(`authConfig = { enabled: true, signup_open: true, signup: 'invite', access_codes: false,
      contact: ${JSON.stringify(contact)} }`);
    f.run('showGate()');
    const hint = f.get('#account-invite-hint');
    assert.equal(f.get('#account-invite').hidden, true, 'Signing in asks for no invite code');
    assert.equal(hint.hidden, true);
    f.get('#account-toggle').onclick();
    assert.equal(f.get('#account-invite').hidden, false);
    assert.equal(hint.hidden, false);
    if (kind === 'none') {
      assert.deepEqual(hint.children, ['account_invite_hint_ask']);
    } else {
      const [before, who, after] = hint.children;
      assert.equal(hint.children.length, 3);
      assert.equal(before + after, 'account_invite_hint');
      // The operator's words are placed as text, whatever they contain.
      assert.equal(who.textContent, contact);
      assert.equal(who.children.length, 0);
      assert.equal(who.href, kind === 'address' ? 'mailto:ops@example.org' : undefined);
    }
    // Back to signing in: the hint goes with the field.
    f.get('#account-toggle').onclick();
    assert.equal(hint.hidden, true);
    assert.equal(hint.children.length, 0);
    assert.equal(f.requests.length, 0, 'The contact arrives with the gate; it is not fetched');
  },
  async compare_pick() {
    // "Compare" asks which finished run; the list is the rail's own request,
    // the choice only navigates, and nothing else is sent.
    const f = fixture();
    f.run('activeRunId = "20261106T000000Z-reuse"');
    f.run('paintActions("completed")');
    f.run('globalThis.compared = null; openCompare = (a, b) => { compared = [a, b]; }');
    const compare = f.get('#run-actions').children.find((button) => button.id === 'run-compare');
    const picking = compare.listeners.click();
    assert.equal(f.get('#compare-dialog').open, true);
    assert.equal(f.requests.length, 1);
    assert.equal(f.requests[0].url, '/api/runs?limit=200');
    f.respond(0, { total: 3, runs: [
      { run_id: '20261106T000000Z-reuse', state: 'completed', topic: 'this one' },
      { run_id: '20261105T000000Z-other', state: 'completed', topic: 'the other', owner_label: 'ceshi' },
      { run_id: '20261104T000000Z-broken', state: 'failed', topic: 'did not finish' },
    ] });
    await picking;
    const choices = f.get('#compare-choices').children;
    assert.equal(choices.length, 1, 'Only another finished run can be compared with');
    const choice = choices[0].children[0];
    assert.equal(choice.dataset.runId, '20261105T000000Z-other');
    assert.equal(choice.children[0].textContent, 'the other');
    assert.ok(choice.children[1].textContent.endsWith('ceshi'));
    assert.equal(f.get('#compare-empty').hidden, true);
    choice.listeners.click();
    assert.equal(f.get('#compare-dialog').open, false);
    assert.equal(JSON.stringify(f.run('compared')), JSON.stringify(['20261106T000000Z-reuse', '20261105T000000Z-other']));
    assert.equal(f.requests.length, 1, 'Choosing sends nothing');

    // The runs on this run's topic come first and say so. Here the run being
    // compared is not in the list (it is past the list's end, or another
    // account's that an administrator opened): its topic is the title on screen.
    f.get('#run-title').textContent = '  Hyperloop for freight ';
    const again = compare.listeners.click();
    f.respond(1, { total: 4, runs: [
      { run_id: '20261105T000000Z-other', state: 'completed', topic: 'the other' },
      { run_id: '20261104T000000Z-broken', state: 'failed', topic: 'hyperloop for freight' },
      { run_id: '20261103T000000Z-older', state: 'completed', topic: 'hyperloop for freight.', owner_label: 'ceshi' },
      { run_id: '20261102T000000Z-oldest', state: 'completed', topic: 'HYPERLOOP for freight' },
    ] });
    await again;
    const listed = f.get('#compare-choices').children.map((item) => item.children[0]);
    assert.deepEqual(listed.map((choice) => [choice.dataset.runId.slice(-6), choice.dataset.sameTopic ?? null]),
      [['-older', 'true'], ['oldest', 'true'], ['-other', null]],
      'The same topic first, newest first within it; the unfinished run of that topic is still not offered');
    const said = listed.map((choice) => choice.children[1].textContent);
    assert.ok(said[0].startsWith('compare_pick_same · ') && said[0].endsWith(' · ceshi'), said[0]);
    assert.ok(said[1].startsWith('compare_pick_same · '));
    assert.ok(!said[2].includes('compare_pick_same'), 'A run on another topic is not marked');
    // A title that is still the placeholder names no topic: the list as it came.
    f.get('#run-title').textContent = '—';
    const third = compare.listeners.click();
    f.respond(2, { total: 2, runs: [
      { run_id: '20261105T000000Z-other', state: 'completed', topic: '—' },
      { run_id: '20261103T000000Z-older', state: 'completed', topic: 'hyperloop for freight' },
    ] });
    await third;
    assert.deepEqual(f.get('#compare-choices').children.map((item) => item.children[0].dataset.sameTopic ?? null), [null, null]);
  },
  async failed_run_context() {
    // A topic edit must leave the saved decision intact all the way to the new POST.
    const f = fixture();
    const context = {
      asset_description: "Membrane prototype", target_application: "Reclaim process water",
      decision_owner: "Plant manager", decision_type: "Fund a pilot?",
      jurisdiction: "Australia", time_horizon: "Next quarter", constraints: "Existing plant",
      success_criteria: "Meet the discharge target", success_criteria_authority: "owner_approved",
    };
    const kind = process.argv[3];
    const saved = kind === "full" ? context : kind === "partial" ? {decision_owner: context.decision_owner} : null;
    const status = saved ? "available" : kind === "empty" ? "empty" : "unavailable";
    f.run(`for (const name of ${JSON.stringify(Object.keys(context))}) {
      decisionContextInputs.push({dataset: {contextField: name}, value: "unrelated draft", dispatchEvent() {}});
    }
    activeRunId = "failed-fixture";
    paintActions("failed", null, true, {saved_decision_context: ${JSON.stringify({status, context: saved})}});`);
    f.get("#run-title").textContent = "Narrow membrane topic";
    f.get("#run-actions").children.find(el => el.id === "run-again").listeners.click();
    f.topic("Broader membrane topic");
    assert.equal(f.requests.length, 0, "Editing starts no plan or run");
    const submitted = f.submit();
    assert.equal(f.requests.length, 1);
    const body = JSON.parse(f.requests[0].options.body);
    assert.deepEqual(body.decision_context, saved);
    assert.equal(body.topic, "Broader membrane topic");
    f.respond(0, {run_id: "new-run", topic: body.topic}, 202);
    await submitted;
  },
  async run_reuse() {
    // A finished run offers its topic again and its address; neither sends anything.
    const kind = process.argv[3];
    const f = fixture();
    f.run('activeRunId = "20261106T000000Z-reuse"');
    f.get('#run-title').textContent = 'hyperloop for freight';
    if (kind === 'fallback' || kind === 'refused') {
      // A browser that refuses the page's own write to the clipboard, as the
      // one inside a chat app does. The older way is there; whether it works
      // is the browser's to say.
      f.run('globalThis.navigator = { clipboard: { writeText: async () => { throw new Error("NotAllowedError"); } } }');
      f.run(`globalThis.fields = []; globalThis.commands = []; globalThis.refocused = 0;
        document.activeElement = { focus: () => { refocused += 1; } };
        document.body = { append: (field) => {
          field.select = () => { field.selected = true; };
          field.setSelectionRange = (from, to) => { field.range = [from, to]; };
          field.remove = () => { field.removed = true; };
          fields.push(field);
        } };
        document.execCommand = (command) => {
          commands.push([command, fields.at(-1).value, fields.at(-1).selected === true, fields.at(-1).removed === true]);
          return ${kind === 'fallback'};
        };`);
    } else if (kind !== 'blocked') {
      f.run('globalThis.navigator = { clipboard: { writeText: async (text) => { recordCopy(text); } } }; globalThis.recordCopy = null');
    }
    const state = kind === 'running' ? 'running' : 'failed';
    f.run(`paintActions(${JSON.stringify(state)})`);
    const buttons = f.get('#run-actions').children;
    const byId = (id) => buttons.find((button) => button.id === id);
    const copy = byId('run-copy-link');
    assert.ok(copy, 'A run can be shared while it runs and after it ends');
    assert.equal(copy.textContent, 'copy_link');
    if (kind === 'running') {
      assert.equal(byId('run-again'), undefined, 'A run still going is not offered again');
      return;
    }
    const again = byId('run-again');
    assert.equal(again.textContent, 'run_again');
    const compare = byId('run-compare');
    assert.equal(compare.textContent, 'compare', 'A finished run can be put beside another');
    assert.equal([...buttons].indexOf(compare), [...buttons].indexOf(again) + 1);
    f.get('#topic').value = 'something half typed';
    again.listeners.click();
    assert.equal(f.get('#topic').value, 'hyperloop for freight');
    assert.equal(f.get('#pane-compose').hidden, false);
    assert.equal(f.get('#pane-run').hidden, true);
    assert.equal(f.requests.length, 0, 'Filling the composer starts nothing');

    if (kind === 'blocked') {
      // Neither way exists here. Nothing is claimed, and nothing is thrown.
      await copy.listeners.click();
      assert.equal(f.get('#toasts').children.at(-1).textContent, 'msg_link_copy_failed');
    } else if (kind === 'fallback' || kind === 'refused') {
      f.run('location.origin = "https://example.test"');
      await copy.listeners.click();
      const link = 'https://example.test/run/20261106T000000Z-reuse';
      // Copied while the field held the link and was selected, and before it was taken away.
      // Compared as text: the arrays were made in the page's own realm.
      assert.equal(JSON.stringify(f.run('commands')), JSON.stringify([['copy', link, true, false]]));
      const field = f.run('fields')[0];
      assert.equal(JSON.stringify(field.range), JSON.stringify([0, link.length]));
      assert.equal(field.removed, true, 'The field does not stay in the page, copied or not');
      assert.equal(f.run('fields').length, 1);
      assert.equal(f.run('refocused'), 1, 'Focus goes back to where it was');
      // What the browser said is what the reader is told.
      assert.equal(f.get('#toasts').children.at(-1).textContent,
        kind === 'fallback' ? 'msg_link_copied' : 'msg_link_copy_failed');
    } else {
      f.run('recordCopy = (text) => { copiedLink = text; }; globalThis.copiedLink = null');
      f.run('location.origin = "https://example.test"');
      await copy.listeners.click();
      assert.equal(f.run('copiedLink'), 'https://example.test/run/20261106T000000Z-reuse',
        'The link is to the run the button was drawn for, even after the view moved on');
      assert.equal(f.get('#toasts').children.at(-1).textContent, 'msg_link_copied');
    }
    assert.equal(f.requests.length, 0);
  },
};
assert.ok(scenarios[process.argv[2]], "Unknown contract scenario");
await scenarios[process.argv[2]]();
console.log(`PASS ${process.argv[2]}`);
