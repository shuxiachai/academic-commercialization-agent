/* Execute shipped app/API code with delayed HTTP responses, never a socket.
 * DOM painting is a fixture; request count and submitted paper identity are
 * the seam under test. The opt-in Chromium journey covers real DOM behavior. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createPaidReceipts } from "../../web/static/js/paid_receipts.js";

globalThis.localStorage = { getItem: () => null, removeItem: () => {} };
globalThis.sessionStorage = { getItem: () => null };
const api = await import("../../web/static/js/api.js");
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
  }
  const get = (selector) => {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  const requests = [], opened = [], reloads = [], windowEvents = {};
  globalThis.fetch = (url, options) => {
    // Access boot deliberately waits; it cannot start history/capacity timers.
    if (url === "/api/access/check") return new Promise(() => {});
    assert.ok(["/api/runs", "/api/papers", "/api/runs/parent/resume", "/api/receipts"].includes(url), `Unexpected HTTP: ${url}`);
    return new Promise((resolve, reject) => requests.push({ url, options, resolve, reject }));
  };
  const context = vm.createContext({
    createPaidReceipts: () => createPaidReceipts(() => ({
      getItem: key => receiptStore.get(key) ?? null,
      setItem: (key, value) => receiptStore.set(key, value),
      removeItem: key => receiptStore.delete(key),
    })),
    api, runView: { isTerminalState: (state) => ["completed", "failed", "cancelled", "timeout"].includes(state) },
    sidebar: { refresh: () => Promise.resolve([]) }, result: {}, needsScopeWarning: () => false,
    i18n: { t: (key) => translations[key] || key, language: () => "English", apply: () => {} },
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
    f.get('#byok-provider').value = 'qwen'; f.get('#byok-llm-key').value = 'fixture-B';
    f.get('#byok-serper-key').value = 'fixture-search-B';
    f.get('#byok-form').onsubmit({preventDefault(){}});
    assert.equal(api.getByok(), null, 'A pending code check cannot race a new BYOK identity');
    assert.equal(f.get('#gate').hidden, false);
    assert.equal(f.requests.length, 0);
  },
  async gate_finished() {
    const f = fixture(); const gate = f.run('showGate()');
    f.get('#byok-provider').value = 'qwen'; f.get('#byok-llm-key').value = 'fixture-A';
    f.get('#byok-serper-key').value = 'fixture-search';
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
    f.get('#byok-provider').value = 'qwen';
    f.get('#byok-llm-key').value = 'fixture-B'; f.get('#byok-serper-key').value = 'fixture-search-B';
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
};
assert.ok(scenarios[process.argv[2]], "Unknown contract scenario");
await scenarios[process.argv[2]]();
console.log(`PASS ${process.argv[2]}`);
