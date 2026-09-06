/* Execute shipped app/API code with delayed HTTP responses, never a socket.
 * DOM painting is a fixture; request count and submitted paper identity are
 * the seam under test. The opt-in Chromium journey covers real DOM behavior. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

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

function fixture() {
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
    focus() {} remove() {} setAttribute() {} removeAttribute() {}
  }
  const get = (selector) => {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  const requests = [], opened = [];
  globalThis.fetch = (url, options) => {
    // Access boot deliberately waits; it cannot start history/capacity timers.
    if (url === "/api/access/check") return new Promise(() => {});
    assert.ok(["/api/runs", "/api/papers", "/api/runs/parent/resume"].includes(url), `Unexpected HTTP: ${url}`);
    return new Promise((resolve, reject) => requests.push({ url, options, resolve, reject }));
  };
  const context = vm.createContext({
    api, runView: { isTerminalState: (state) => ["completed", "failed", "cancelled", "timeout"].includes(state) },
    sidebar: {}, result: {}, needsScopeWarning: () => false,
    i18n: { t: (key) => translations[key] || key, language: () => "English", apply: () => {} },
    document: { querySelector: get, querySelectorAll: (selector) => selector === '[data-resume-run]'
      ? get("#run-actions").children.filter((el) => el.dataset?.resumeRun) : [], createElement: () => new Element(),
      addEventListener: () => {}, hidden: false },
    window: { matchMedia: () => ({ matches: false }), addEventListener: () => {} },
    localStorage: globalThis.localStorage, history: { pushState: () => {} }, location: { pathname: "/" },
    setTimeout: () => 1, clearTimeout: () => {}, setInterval: () => 1, clearInterval: () => {},
    confirm: () => true, recordOpen: (id) => opened.push(id),
  });
  vm.runInContext(source, context);
  vm.runInContext("openRun = (id) => recordOpen(id)", context);
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
  return { get, run, topic, submit, upload, respond, requests, opened };
}

function paintResume(f) {
  f.run('activeRunId = "parent"; paintActions("failed", { committed_nodes: ["retrieval"] })');
  return f.get("#run-actions").children.find((el) => el.textContent === "resume");
}

const paper = { paper_id: "paper-one", title: "Fixture paper", commercialization_topic: "Suggested topic" };
const scenarios = {
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
