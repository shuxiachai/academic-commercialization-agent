// The anonymous visit to "/": a landing page first, the workbench after.
//
// Runs the shipped app.js against a fake document, with the real api.js and
// fetch intercepted. The seam under test is which of #landing, #workbench and
// #gate a visitor is shown, and that the landing's buttons lead through the
// existing sign-in card into the workbench. No socket is opened and nothing
// paid is reachable: every request here is answered by this file.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { createPaidReceipts } from "../../web/static/js/paid_receipts.js";

const disk = new Map();
globalThis.localStorage = {
  getItem: (key) => disk.get(key) ?? null,
  setItem: (key, value) => disk.set(key, String(value)),
  removeItem: (key) => disk.delete(key),
};
const tab = new Map();
globalThis.sessionStorage = {
  getItem: (key) => tab.get(key) ?? null,
  setItem: (key, value) => tab.set(key, String(value)),
  removeItem: (key) => tab.delete(key),
};

// As /api/samples lists them: the second without a readiness level, as a
// scorecard that holds none is listed.
const SAMPLES = [
  { slug: "hyperloop", title: "Hyperloop", topic: "hyperloop", committed: "2026-10-21", commit: "a8cc424",
    language: "English", overall_score: 48.6, trl_score: 5,
    decision: { asset_description: "A pod", target_application: "Freight", decision_owner: "An investor",
                decision_type: "Invest" } },
  { slug: "solid-state-batteries-ev-zh", title: "电动汽车用固态电池", topic: "电动汽车用固态电池",
    committed: "2026-10-21", commit: "a8cc424", language: "Simplified Chinese", overall_score: 74.9, trl_score: null },
  { slug: "../etc/passwd", title: "Not a sample", topic: "", committed: "", commit: "" },
];
const ACCOUNTS = { enabled: true, signup_open: true, signup: "open", access_codes: false, password_reset: true, notices: true,
  key_check: false, contact: null, plan_preview: false, daily_quota: false };
const ACCOUNT = { email: "visitor@example.test", admin: false, verified: true };

// The scorecard the landing shows where a picture used to be: one sample's, as
// /api/samples/<slug>/scores serves it.
const PREVIEW_SCORES = "/api/samples/continuous-glucose-monitoring/scores";
const SCORES = { overall_score: 74.0, trl_score: 9, mrl_score: 9, patent_strength: 3, market_accessibility: 3.5,
  evidence_confidence: 4, trl_rationale: "Cleared devices are on the market [A1]." };

// One scenario per process: api.js reads its credential slots once.
const scenario = process.argv[2];
if (scenario === "keys_in_this_tab_never_see_the_landing") {
  tab.set("byok-credentials", JSON.stringify({ provider: "deepseek", llmKey: "sk-fixture-000000000000",
    model: "deepseek-chat", search: "tavily", searchKey: "tvly-fixture-000000000000" }));
}
if (scenario === "unreadable_keys_never_see_the_landing") tab.set("byok-credentials", "{not json");
if (["signed_in", "logout_goes_home", "a_signed_in_boot_told_to_wait_keeps_the_session"].includes(scenario)) {
  disk.set("session-token", "fixture-token");
}
if (scenario === "logout_without_accounts_reloads") disk.set("access-code", "fixture-code");

const api = await import("../../web/static/js/api.js");
const runView = await import("../../web/static/js/run.js");
const { modelKind } = await import("../../web/static/js/model_kind.js");
const compareView = await import("../../web/static/js/compare.js");
// The real grading of a sample's score, so the list's words are the scorecard's.
const { sampleFacts, sampleTitle } = await import("../../web/static/js/result.js");
const source = fs.readFileSync(new URL("../../web/static/js/app.js", import.meta.url), "utf8")
  .replace(/^import .*;\r?\n/gm, "");
// The elements the document itself starts hidden (#gate, #landing, the card's
// forms...): app.js shows them and relies on the markup for the rest.
const markup = fs.readFileSync(new URL("../../web/index.html", import.meta.url), "utf8");
const hiddenAtStart = [...markup.matchAll(/<[^>]*\bid="([\w-]+)"[^>]*\shidden[\s>]/g)].map((match) => match[1]);
assert.ok(hiddenAtStart.includes("gate") && hiddenAtStart.includes("landing"), "the document starts with both hidden");
assert.ok(hiddenAtStart.includes("landing-preview-note"), "the note for a preview that could not be read starts hidden");

// `replies` answers the seams a scenario is about beyond the boot's access check.
// `hold: true` keeps the access check unanswered until the scenario calls answer().
// `dark: true` is a system set to its dark theme, as matchMedia reports it.
function fixture({ pathname = "/", search = "", hash = "", access, replies = {}, hold = false, dark = false }) {
  const elements = new Map();
  class Element {
    constructor() {
      Object.assign(this, { value: "", disabled: false, hidden: false, dataset: {}, style: {},
        children: [], listeners: {}, textContent: "", scrollHeight: 40 });
    }
    addEventListener(event, handler) { this.listeners[event] = handler; }
    dispatchEvent(event) {
      this.listeners[event.type]?.(event);
      if (typeof this[`on${event.type}`] === "function") this[`on${event.type}`](event);
    }
    set innerHTML(_value) { this.children = []; }
    append(...nodes) { this.children.push(...nodes); }
    querySelectorAll() { return []; }
    focus() { this.focused = (this.focused ?? 0) + 1; }
    remove() {} reset() {} select() {} removeAttribute() {} scrollIntoView() {}
    setAttribute(name, value) { (this.attributes ??= {})[name] = String(value); }
    // Enough of the DOM's "put this node before me" to see that it was asked for.
    before(...nodes) { (this.placedBefore ??= []).push(...nodes); }
    showModal() { this.open = true; } close() { this.open = false; }
  }
  const get = (selector) => {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  for (const id of hiddenAtStart) get(`#${id}`).hidden = true;
  const requests = [], navigations = [], reloads = [], sidebarRefreshes = [], replaced = [], summaries = [];
  // What the page asked to hear about the system's theme, and the theme it is told.
  const system = { dark, heard: [] };
  // Where app.js writes how far its boot got (markBoot), for whoever reads a failed smoke.
  const documentElement = { dataset: {} };
  // What the strings say: each key as itself, after a prefix a scenario may
  // set to stand for another language, so a line drawn again in it can be
  // told from one left as it was. app.js keeps i18n.t from its first line.
  const speech = { prefix: "" };
  const reply = (body, status = 200, headers = {}) => Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json", ...headers } }));
  let answer = () => {};
  let deliver = () => {};
  globalThis.fetch = (url, options = {}) => {
    requests.push({ url, options });
    if (url in replies) {
      const given = replies[url];
      if (given === "never") return new Promise(() => {});
      // Answered when the scenario says so, with the usual scores.
      if (given === "late") return new Promise((resolve) => { deliver = () => resolve(reply(SCORES)); });
      if (given === "unreachable") return Promise.reject(new TypeError("Failed to fetch"));
      // Answered 200 with a body that is not the JSON its header says it is.
      if (given === "garbled") return Promise.resolve(new Response("<html>", {
        status: 200, headers: { "Content-Type": "application/json" } }));
      return given?.status ? reply(given.body, given.status, given.headers) : reply(given);
    }
    if (url === "/api/access/check") {
      if (!hold) return reply(access.body, access.status, access.headers);
      return new Promise((resolve) => { answer = () => resolve(reply(access.body, access.status)); });
    }
    if (url === "/api/samples") return reply(SAMPLES);
    if (url === PREVIEW_SCORES) return reply(SCORES);
    if (url === "/api/auth/login" || url === "/api/auth/register") return reply({ token: "fixture-token", ...ACCOUNT });
    if (url === "/api/auth/logout") return reply({});
    if (url === "/health") return reply({ retention_days: 30, active_runs: 0, max_concurrent: 5 });
    // History, capacity and quota are other seams; here they never answer.
    return new Promise(() => {});
  };
  const context = vm.createContext({
    createPaidReceipts: () => createPaidReceipts(() => ({ getItem: () => null, setItem: () => {}, removeItem: () => {} })),
    api, runView: { ...runView }, compareView,
    // The real one asks the server for the identity's history; here each call is counted.
    sidebar: { refresh: () => { sidebarRefreshes.push(true); return Promise.resolve([]); }, resetView: () => {} },
    // The real summary is built in tests/test_web_result_readability.py; here
    // it is a stand-in that keeps what it was given and, like the real one,
    // makes nothing of a scorecard without a readable score.
    result: { sampleFacts, sampleTitle, renderScoreSummary: (scores) => {
      summaries.push(scores);
      if (scores?.cannot_be_drawn) throw new TypeError("fixture: the scorecard could not be drawn");
      return typeof scores?.overall_score === "number" ? { className: "scorecard scorecard--summary", scores } : null;
    } },
    needsScopeWarning: () => false, modelKind,
    i18n: { t: (key) => speech.prefix + key, language: () => "English", locale: () => "en-GB", apply: () => {}, setLanguage: () => {},
            pageTitle: (name = "") => (name ? `${name} · brand_full` : "brand_full") },
    document: { querySelector: get, querySelectorAll: () => [], createElement: () => new Element(),
      addEventListener: () => {}, hidden: false, documentElement },
    window: { matchMedia: () => ({ get matches() { return system.dark; },
      addEventListener: (type, handler) => { if (type === "change") system.heard.push(handler); } }), addEventListener: () => {} },
    localStorage: globalThis.localStorage, Event, URLSearchParams,
    history: { pushState: () => {}, replaceState: (_state, _unused, url) => replaced.push(url) },
    location: { pathname, search, hash, reload: () => reloads.push(true), replace: (url) => navigations.push(url) },
    setTimeout: () => 1, clearTimeout: () => {}, setInterval: () => 1, clearInterval: () => {},
    confirm: () => true,
  });
  vm.runInContext(source, context);
  return { get, requests, navigations, reloads, sidebarRefreshes, replaced, summaries, system, speech, answer: () => answer(),
    deliver: () => deliver(), boot: () => documentElement.dataset.boot,
    run: (text) => vm.runInContext(text, context) };
}

// Let the boot's promise chain and the replies above run to completion.
const settle = async () => { for (let i = 0; i < 25; i++) await new Promise((resolve) => setImmediate(resolve)); };
const shown = (f) => ({ landing: !f.get("#landing").hidden, workbench: !f.get("#workbench").hidden, gate: !f.get("#gate").hidden });
const refused = (accounts) => ({ status: 401, body: { detail: "Sign in.", ...(accounts ? { accounts } : {}) } });
// The limiter's answer once a caller's budget is spent, as api/main.py writes it (_rate_limit).
const TOLD_TO_WAIT = { status: 429, body: { detail: "Too many requests. Slow down and retry shortly." },
  headers: { "Retry-After": "10", "X-Error-Code": "rate_limited" } };
// The notice a boot that got no usable answer puts where the page would have been.
const failure = (f) => ({ shown: !f.get("#boot-failure").hidden, title: f.get("#boot-failure-title").textContent,
  text: f.get("#boot-failure-text").textContent });
const DEEP_LINK = "/run/20260926T121212Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const RUN_API = DEEP_LINK.replace("/run/", "/api/runs/");

const scenarios = {
  async anonymous_root() {
    const f = fixture({ access: refused(ACCOUNTS) });
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false },
      "An anonymous visit to / on an accounts deployment lands on the landing, not the gated workbench");
    assert.equal(f.get("#landing-create").hidden, false, "Open sign-up offers an account");
    const links = f.get("#landing-sample-list").children.map((item) => item.children[0]);
    assert.deepEqual(links.map((a) => a.href), ["/samples/hyperloop", "/samples/solid-state-batteries-ev-zh"],
      "Sample links come from /api/samples; a slug that is not one never becomes a path");
    assert.deepEqual(links.map((a) => a.textContent), ["Hyperloop", "电动汽车用固态电池"]);
    // Under each title, what the reader's cards say: the verdict in the
    // scorecard's words, the readiness level where there is one, the language.
    // A sample whose run was given a decision context says so, as its card on /samples does.
    assert.deepEqual(links.map((a) => a.children.map((c) => [c.className, c.textContent, c.dataset.tone])), [
      [["landing__sample-facts", "48.6 / 100 · Early · TRL 5 (score 5 / 9) · Report in English", "warning"],
       ["landing__sample-decision", "With a decision conclusion", undefined]],
      [["landing__sample-facts", "74.9 / 100 · Strong · Report in Chinese", "success"]],
    ]);
    assert.deepEqual(f.replaced, [], "A plain visit to / changes no address");
    assert.equal(f.get("#landing-retention").textContent, "byok_retention",
      "The retention period is the deployment's own, read from /health, as the key form reads it");
    // Where a picture of a scorecard used to be: the scorecard of one sample,
    // drawn by the page from that sample's own scores.
    assert.deepEqual(f.summaries, [SCORES], "The preview is built from the sample's scores as served");
    assert.deepEqual(f.get("#landing-preview").children.map((node) => node.className), ["scorecard scorecard--summary"]);
    assert.equal(f.get("#landing-preview-note").hidden, true);
    assert.equal(f.get("#landing-preview").dataset.state, "shown");
    assert.equal(f.requests.filter((r) => r.url === PREVIEW_SCORES).length, 1);
    assert.equal(f.requests.filter((r) => r.url === "/api/samples").length, 1, "Shown once, asked once");

    f.get("#landing-create").onclick();
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: true }, "Create account opens the card over the landing");
    assert.equal(f.get("#account-form").hidden, false);
    assert.equal(f.get("#account-title").textContent, "account_title_create", "...in its create mode");
    assert.equal(f.get("#gate-back").hidden, false, "The card can be put down again");
    f.get("#gate-back").onclick();
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false }, "Back returns to the landing");

    f.get("#landing-sign-in").onclick();
    await settle();
    assert.equal(f.get("#account-title").textContent, "account_title", "Sign in opens the card in its sign-in mode");
    f.get("#account-email-input").value = ACCOUNT.email;
    f.get("#account-password").value = "a sufficiently long password";
    f.get("#account-form").onsubmit({ preventDefault() {} });
    await settle();
    assert.ok(f.requests.some((r) => r.url === "/api/auth/login"), "The card signs in through the same request as before");
    assert.equal(disk.get("session-token"), "fixture-token");
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: true }, "Keys are asked for next, still on the card");
    assert.equal(f.get("#byok-form").hidden, false);
    assert.equal(f.get("#gate-back").hidden, true, "Once signed in there is no landing to go back to");
    f.get("#byok-skip").onclick();
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: false }, "Signed in: the workbench, and the landing is gone");
    assert.equal(f.get("#landing-preview").children.length, 0, "...with the scorecard it showed");
  },
  async anonymous_root_signup_closed() {
    // The list here is as a deployment without scorecards, or an older server, gives it.
    const f = fixture({ access: refused({ ...ACCOUNTS, signup_open: false, signup: "closed" }),
      replies: { "/api/samples": [{ slug: "hyperloop", title: "Hyperloop" }, { slug: "plain", title: "Plain", overall_score: null, trl_score: null }] } });
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false });
    const links = f.get("#landing-sample-list").children.map((item) => item.children[0]);
    assert.deepEqual(links.map((a) => [a.textContent, a.children.length]), [["Hyperloop", 0], ["Plain", 0]],
      "A sample listed without a score is its title, as before");
    assert.equal(f.get("#landing-create").hidden, true, "No sign-up means no button that would only fail");
    f.get("#landing-sign-in-top").onclick();
    await settle();
    assert.equal(shown(f).gate, true, "The header's sign-in opens the card too");
    assert.equal(f.get("#account-title").textContent, "account_title");
  },
  // ── Before the access check answers ──────────────────────────────────
  // The landing used to wait for the check: until it answered, an anonymous
  // visit to / was an empty page (1.4 s to the first paint from Sydney on
  // 2026-11-13). With nothing stored that could sign the visit in, the page
  // is shown at once and corrected when the answer comes.
  async landing_before_the_check_answers() {
    const f = fixture({ access: refused(ACCOUNTS), hold: true });
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false }, "Shown while the check is still out");
    assert.equal(f.get("#landing-sample-list").children.length, 2, "...with its samples");
    assert.deepEqual(f.get("#landing-preview").children.map((node) => node.className), ["scorecard scorecard--summary"]);
    assert.equal(f.get("#landing-retention").textContent, "byok_retention");
    assert.equal(f.get("#landing-trial").hidden, true, "Nothing is said about a free first run before the deployment says so");
    assert.equal(f.get("#landing-key-guide-trial").hidden, true);
    assert.equal(f.get("#landing-create").hidden, false, "The buttons are as the markup has them");
    f.answer();
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false }, "The answer leaves it standing");
    assert.equal(f.requests.filter((r) => r.url === "/api/samples").length, 1, "Painted once: no second request");
    assert.equal(f.requests.filter((r) => r.url === PREVIEW_SCORES).length, 1);
    assert.equal(f.requests.filter((r) => r.url === "/health").length, 1);
    assert.equal(f.get("#landing-preview").children.length, 1, "...and no second scorecard");
    f.get("#landing-sign-in").onclick();
    await settle();
    assert.equal(shown(f).gate, true, "The buttons work as on any visit");
    assert.equal(f.get("#account-title").textContent, "account_title");
  },
  async a_button_pressed_before_the_answer_opens_its_form_after_it() {
    const f = fixture({ access: refused(ACCOUNTS), hold: true });
    await settle();
    f.get("#landing-create").onclick();
    await settle();
    assert.equal(shown(f).gate, false, "The card cannot open before the deployment has said what it offers");
    f.answer();
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: true }, "The press is kept, not lost");
    assert.equal(f.get("#account-title").textContent, "account_title_create");
    f.get("#gate-back").onclick();
    await settle();
    assert.equal(shown(f).gate, false);
    f.get("#landing-sign-in").onclick();
    await settle();
    assert.equal(f.get("#account-title").textContent, "account_title", "...and it is kept once: the next press is its own");
  },
  async the_last_press_before_the_answer_is_the_one_kept() {
    const f = fixture({ access: refused(ACCOUNTS), hold: true });
    await settle();
    f.get("#landing-create").onclick();
    f.get("#landing-sign-in-top").onclick();
    f.answer();
    await settle();
    assert.equal(f.get("#account-title").textContent, "account_title", "Sign in was pressed last");
  },
  async a_press_before_the_answer_where_sign_up_is_closed() {
    const f = fixture({ access: refused({ ...ACCOUNTS, signup_open: false, signup: "closed" }), hold: true });
    await settle();
    f.get("#landing-create").onclick();
    f.answer();
    await settle();
    assert.equal(f.get("#landing-create").hidden, true, "The button goes once the deployment says it takes no new accounts");
    assert.equal(f.get("#account-title").textContent, "account_title", "...and the press opens the sign-in");
  },
  async the_link_from_a_sample_waits_for_the_answer_too() {
    const f = fixture({ hash: "#create-account", access: refused(ACCOUNTS), hold: true });
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false });
    f.answer();
    await settle();
    assert.equal(shown(f).gate, true);
    assert.equal(f.get("#account-title").textContent, "account_title_create");
    assert.deepEqual(f.replaced, ["/"]);
  },
  async early_landing_gives_way_to_an_open_deployment() {
    const f = fixture({ access: { status: 200, body: { ok: true } }, hold: true });
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false },
      "Nothing stored, at /: the landing is shown until the deployment says there is nothing to sign in to");
    f.get("#landing-create").onclick();
    f.answer();
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: false }, "...then the workbench, as always");
    assert.equal(f.get("#gate").hidden, true, "A press on a page that turned out not to apply opens nothing");
    // The scorecard it had drawn goes with it. Left in the document, hidden,
    // it was a second ".scorecard" beside the one a run's page draws; the
    // browser smoke met exactly that.
    assert.equal(f.get("#landing-preview").children.length, 0, "A landing put away takes its scorecard with it");
  },
  async a_scorecard_that_arrives_after_the_landing_left_is_not_drawn() {
    const f = fixture({ access: { status: 200, body: { ok: true } }, hold: true, replies: { [PREVIEW_SCORES]: "late" } });
    await settle();
    assert.equal(shown(f).landing, true);
    f.answer();
    await settle();
    assert.equal(shown(f).landing, false);
    f.deliver();
    await settle();
    assert.equal(f.get("#landing-preview").children.length, 0, "Nothing is drawn into a landing nobody is looking at");
    assert.equal(f.get("#landing-preview-note").hidden, true, "...and nothing is said to have failed");
    assert.deepEqual(f.summaries, [], "The scores are not even rendered");
  },
  async early_landing_gives_way_to_the_code_card() {
    const f = fixture({ access: refused(null), hold: true });
    await settle();
    assert.equal(shown(f).landing, true);
    f.answer();
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: true });
    assert.equal(f.get("#gate-form").hidden, false);
  },
  // The boot's one request can end three ways that are not "you may enter"
  // and not "sign in": the limiter told the page to wait, nothing answered,
  // or the server answered with a failure. Until 2026-11-18 all three left
  // the visitor on an empty workbench that could do nothing, and said
  // nothing. Each is now said, with a way to try again.
  async a_boot_told_to_wait_says_so_and_can_be_tried_again() {
    const stopped = [];
    process.on("unhandledRejection", (error) => stopped.push(error.message));
    const f = fixture({ access: TOLD_TO_WAIT });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: false, gate: false },
      "Neither the landing, whose buttons could open nothing, nor a workbench nobody was let into");
    assert.deepEqual(failure(f), { shown: true, title: "boot_failure_title", text: "boot_failure_rate_limited" });
    assert.equal(f.boot(), "failed", "A smoke that stops here can read why");
    assert.deepEqual(stopped, [], "Said on the page, not thrown past it");
    assert.deepEqual(f.sidebarRefreshes, [], "Nothing of the workbench starts behind the notice");
    assert.deepEqual(f.reloads, []);
    assert.equal(f.get("#boot-failure-retry").focused, 1, "The one control on the page is where the keyboard already is");
    f.get("#boot-failure-retry").onclick();
    assert.deepEqual(f.reloads, [true], "Trying again is the page loaded again, so the boot runs whole");
  },
  async a_boot_that_cannot_reach_the_server_says_so() {
    const stopped = [];
    process.on("unhandledRejection", (error) => stopped.push(error.message));
    const f = fixture({ access: refused(ACCOUNTS), replies: { "/api/access/check": "unreachable" } });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: false, gate: false },
      "The page that promised a sign-in does not stay when nothing answered");
    assert.deepEqual(failure(f), { shown: true, title: "boot_failure_title", text: "msg_network" });
    assert.equal(f.boot(), "failed");
    assert.deepEqual(stopped, []);
  },
  async a_boot_the_server_could_not_answer_says_so() {
    const f = fixture({ access: { status: 503, body: { detail: "upstream connect error or disconnect/reset before headers" } } });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: false, gate: false });
    assert.deepEqual(failure(f), { shown: true, title: "boot_failure_title", text: "boot_failure_server" },
      "In the page's words: what a proxy wrote in the body is not shown to a visitor");
  },
  async a_signed_in_boot_told_to_wait_keeps_the_session() {
    // An account spends its own budget, so this is the account's own page
    // asking too fast. The session is not what was refused.
    const f = fixture({ access: TOLD_TO_WAIT });
    await settle();
    assert.deepEqual(failure(f), { shown: true, title: "boot_failure_title", text: "boot_failure_rate_limited" });
    assert.equal(shown(f).workbench, false, "A workbench with no history and no account in it would say they are signed out");
    assert.equal(disk.get("session-token"), "fixture-token", "Trying again finds them still signed in");
    assert.deepEqual(f.sidebarRefreshes, []);
  },
  async a_shared_link_whose_boot_was_told_to_wait_says_so() {
    const f = fixture({ pathname: DEEP_LINK, access: TOLD_TO_WAIT });
    await settle();
    assert.deepEqual(failure(f), { shown: true, title: "boot_failure_title", text: "boot_failure_rate_limited" });
    assert.deepEqual(shown(f), { landing: false, workbench: false, gate: false });
    assert.equal(f.get("#viewer-bar").hidden, true, "Not the reader's bar over a report that was never asked for");
    assert.ok(!f.requests.some((r) => r.url.startsWith(RUN_API)), "The run waits for a boot that answers");
  },
  async a_boot_that_broke_in_the_page_is_not_blamed_on_the_server() {
    // A 200 the page cannot read is not an answer about the visitor, and not
    // something a reload a few seconds later is known to cure. It stops the
    // boot as it always has, where a maintainer's console shows it.
    const stopped = [];
    process.on("unhandledRejection", (error) => stopped.push(error.name));
    const f = fixture({ access: refused(ACCOUNTS), replies: { "/api/access/check": "garbled" } });
    await settle();
    assert.equal(failure(f).shown, false, "No sentence about the server for what the server did not do");
    assert.deepEqual(stopped, ["SyntaxError"]);
    assert.equal(f.boot(), "scripts");
  },
  async keys_in_this_tab_never_see_the_landing() {
    // Keys alone boot without a request. The landing must not be painted
    // first and taken away: it would ask the visitor to sign in.
    const f = fixture({ access: refused(ACCOUNTS), hold: true });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: false });
    assert.ok(!f.requests.some((r) => r.url === "/api/samples" || r.url === PREVIEW_SCORES));
  },
  async unreadable_keys_never_see_the_landing() {
    const f = fixture({ access: refused(ACCOUNTS), hold: true });
    await settle();
    assert.equal(shown(f).landing, false, "Corrupted keys go to the card that says so, with no landing under it");
    assert.equal(shown(f).gate, true);
    assert.ok(!f.requests.some((r) => r.url === "/api/samples"));
  },
  // ── The scorecard in place of the picture ────────────────────────────
  async preview_that_cannot_be_read_is_a_quiet_line() {
    for (const given of [{ status: 404, body: { detail: "No such sample." } }, { status: 500, body: {} }, "unreachable",
      { overall_score: "74" }, [], null, { overall_score: 74, cannot_be_drawn: true }]) {
      const f = fixture({ access: refused(ACCOUNTS), replies: { [PREVIEW_SCORES]: given } });
      await settle();
      assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false }, "The landing stands without it");
      assert.equal(f.get("#landing-preview").children.length, 0, `${JSON.stringify(given)} draws nothing`);
      assert.equal(f.get("#landing-preview-note").hidden, false, "...and one line says the preview is not there");
      assert.equal(f.get("#landing-preview").dataset.state, "missing", "The frame gives up the height it was holding");
      assert.equal(f.get("#landing-sample-list").children.length, 2, "The sample list does not depend on it");
    }
    const waiting = fixture({ access: refused(ACCOUNTS), replies: { [PREVIEW_SCORES]: "never" } });
    await settle();
    assert.equal(waiting.get("#landing-preview-note").hidden, true, "While it is still loading, nothing is said to have failed");
    assert.equal(waiting.get("#landing-preview").dataset.state, undefined, "...and the frame is as the markup has it");
    waiting.get("#landing-sign-in").onclick();
    await settle();
    assert.equal(shown(waiting).gate, true, "...and nothing waits for it");
  },
  // The sample reader ends with "Create account" or "Sign in", which are
  // links to / that name the form. The landing opens it, and takes the
  // fragment off the address so Back or a reload does not open it again.
  async create_account_link() {
    const f = fixture({ hash: "#create-account", access: refused(ACCOUNTS) });
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: true }, "The card opens over the landing");
    assert.equal(f.get("#account-title").textContent, "account_title_create", "...in its create mode");
    assert.deepEqual(f.replaced, ["/"]);
    f.get("#gate-back").onclick();
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false }, "Put down, it leaves the landing as any visit finds it");
    f.get("#landing-sign-in").onclick();
    await settle();
    assert.equal(f.get("#account-title").textContent, "account_title", "The landing's own buttons still work afterwards");
  },
  async sign_in_link() {
    const f = fixture({ hash: "#sign-in", access: refused(ACCOUNTS) });
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: true });
    assert.equal(f.get("#account-title").textContent, "account_title", "The card opens in its sign-in mode");
    assert.deepEqual(f.replaced, ["/"]);
  },
  async create_account_link_when_sign_up_is_closed() {
    const f = fixture({ hash: "#create-account", access: refused({ ...ACCOUNTS, signup_open: false, signup: "closed" }) });
    await settle();
    assert.equal(shown(f).gate, true);
    assert.equal(f.get("#account-title").textContent, "account_title", "A deployment that takes no new accounts shows the sign-in");
    assert.deepEqual(f.replaced, ["/"]);
  },
  async another_fragment_opens_nothing() {
    const f = fixture({ hash: "#section-2", access: refused(ACCOUNTS) });
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false });
    assert.deepEqual(f.replaced, [], "...and is left on the address");
  },
  async anonymous_deep_link() {
    // Until 2026-11-11 this asked for the sign-in directly. "Copy link" hands
    // the address to someone else, the server has always answered a run's
    // reads to whoever holds its id, and the card stood between the two: the
    // person the link was for had to create an account to read one report.
    const f = fixture({ pathname: DEEP_LINK, access: refused(ACCOUNTS) });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: false },
      "A shared run opens for whoever holds its link; nobody is asked to sign in to read it");
    assert.equal(f.get("#viewer-bar").hidden, false, "A bar says this is a shared report and offers the way in");
    assert.equal(f.get("#workbench").dataset.viewer, "true", "...and the workbench is marked, so the rail is not shown");
    assert.equal(f.get("#viewer-create").hidden, false, "Open sign-up offers an account");
    assert.ok(f.requests.some((r) => r.url.startsWith(RUN_API)), "The run itself is read, by its id");
    assert.equal(f.sidebarRefreshes.length, 0, "No history is asked for: there is no identity whose history it would be");
    assert.ok(!f.requests.some((r) => r.url === "/api/samples"), "No landing, no sample request");
    assert.ok(!f.requests.some((r) => r.url === PREVIEW_SCORES), "...and no scorecard for it either");

    // What a reader may do with someone else's run: read it, keep it, pass it on.
    const actions = (state) => {
      f.run(`paintActions(${JSON.stringify(state)}, { committed_nodes: ["retrieval"] })`);
      return f.get("#run-actions").children.map((node) => node.id || node.textContent || node.download || "");
    };
    const finished = actions("completed");
    assert.ok(finished.some((label) => label.endsWith(".md")) && finished.some((label) => label.endsWith(".pdf")),
      "A finished report can be downloaded");
    for (const state of ["completed", "failed", "running", "cancelled", "timeout"]) {
      const offered = actions(state);
      for (const forbidden of ["cancel", "resume", "delete_run", "run-again", "run-compare"]) {
        assert.ok(!offered.includes(forbidden), `${forbidden} is not offered to a reader of a ${state} run`);
      }
    }
  },
  async anonymous_deep_link_signup_closed() {
    const f = fixture({ pathname: DEEP_LINK, access: refused({ ...ACCOUNTS, signup_open: false, signup: "closed" }) });
    await settle();
    assert.equal(f.get("#viewer-bar").hidden, false);
    assert.equal(f.get("#viewer-create").hidden, true, "No sign-up means no button that would only fail");
    assert.equal(f.get("#viewer-sign-in").hidden, false);
  },
  async anonymous_compare_link() {
    const f = fixture({ pathname: "/compare/20260926T121212Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/20260927T121212Z-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      access: refused(ACCOUNTS) });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: false }, "A shared comparison is read the same way");
    assert.equal(f.get("#viewer-bar").hidden, false);
  },
  async anonymous_other_path_still_meets_the_card() {
    // Only a run or a comparison is something a link can share. Any other
    // address on a gated deployment is the workbench, which needs an identity.
    const f = fixture({ pathname: "/verify", access: refused(ACCOUNTS) });
    await settle();
    assert.equal(shown(f).gate, true);
    assert.equal(f.get("#viewer-bar").hidden, true);
  },
  async viewer_signs_in() {
    const f = fixture({ pathname: DEEP_LINK, access: refused(ACCOUNTS) });
    await settle();
    f.get("#viewer-sign-in").onclick();
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: true }, "Sign in opens the card over the report");
    assert.equal(f.get("#account-title").textContent, "account_title");
    assert.equal(f.get("#gate-back").hidden, false, "The card can be put down again");
    f.get("#gate-back").onclick();
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: false }, "Put down, the report is still there");
    assert.equal(f.get("#viewer-bar").hidden, false);

    f.get("#viewer-create").onclick();
    await settle();
    assert.equal(f.get("#account-title").textContent, "account_title_create", "Create account opens the card in its create mode");
    f.get("#account-toggle").onclick();
    f.get("#account-email-input").value = ACCOUNT.email;
    f.get("#account-password").value = "a sufficiently long password";
    f.get("#account-form").onsubmit({ preventDefault() {} });
    await settle();
    assert.equal(disk.get("session-token"), "fixture-token");
    f.get("#byok-skip").onclick();
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: false });
    assert.equal(f.get("#viewer-bar").hidden, true, "Signed in, the reader is a user: the bar goes");
    assert.notEqual(f.get("#workbench").dataset.viewer, "true", "...and the rail comes back");
    assert.ok(f.sidebarRefreshes.length > 0, "...with the account's own history");
    f.run('paintActions("completed")');
    assert.ok(f.get("#run-actions").children.some((node) => node.id === "run-again"), "...and the full actions");
    assert.ok(f.get("#run-actions").children.some((node) => node.textContent === "delete_run"), "...Delete among them");
  },
  // One form signs in or creates an account. Until 2026-11-14 it showed a
  // returning visitor what only a newcomer needs: how runs are paid for, that
  // creating an account accepts the terms, and a password rule ("at least 10
  // characters") for a password they already have.
  async the_card_in_sign_in_mode_says_only_what_signing_in_needs() {
    // What i18n.apply() repaints on a change of language is each element's
    // key, so the key has to follow the mode too: the card used to turn back
    // into "Sign in" over a create form when the language was switched.
    const keyed = (f, id) => [f.get(id).textContent, f.get(id).dataset.i18n];
    const state = (f) => ({ title: f.get("#account-title").textContent, keys: !f.get("#account-sub").hidden,
      trial: !f.get("#account-sub-trial").hidden, terms: !f.get("#account-legal").hidden,
      placeholder: f.get("#account-password").placeholder, key: f.get("#account-password").dataset.i18nPlaceholder,
      autocomplete: f.get("#account-password").autocomplete });
    const signIn = { title: "account_title", keys: false, trial: false, terms: false,
      placeholder: "account_password_plain", key: "account_password_plain", autocomplete: "current-password" };
    const create = { title: "account_title_create", keys: true, trial: false, terms: true,
      placeholder: "account_password_placeholder", key: "account_password_placeholder", autocomplete: "new-password" };

    const f = fixture({ access: refused(ACCOUNTS) });
    await settle();
    f.get("#landing-sign-in").onclick();
    await settle();
    assert.deepEqual(state(f), signIn);
    assert.deepEqual(["#account-title", "#account-submit", "#account-toggle"].map((id) => keyed(f, id)),
      [["account_title", "account_title"], ["account_sign_in", "account_sign_in"], ["account_toggle_to_create", "account_toggle_to_create"]]);
    f.get("#account-toggle").onclick();
    await settle();
    assert.deepEqual(state(f), create, "Creating an account: how runs are paid for, the terms, the password rule");
    assert.deepEqual(["#account-title", "#account-submit", "#account-toggle"].map((id) => keyed(f, id)),
      [["account_title_create", "account_title_create"], ["account_create", "account_create"],
       ["account_toggle_to_sign_in", "account_toggle_to_sign_in"]], "...and a change of language repaints this mode, not the other");
    f.get("#account-toggle").onclick();
    await settle();
    assert.deepEqual(state(f), signIn, "...and back again");
    f.get("#gate-back").onclick();
    await settle();
    f.get("#landing-create").onclick();
    await settle();
    assert.deepEqual(state(f), create, "Opened in its create mode, the card is the same as when switched to it");

    // Where the first assessment is free, the newcomer's sentence is the trial's; a returning visitor sees neither.
    const trial = fixture({ access: refused({ ...ACCOUNTS, trial_runs: 1 }) });
    await settle();
    trial.get("#landing-sign-in").onclick();
    await settle();
    assert.deepEqual(state(trial), signIn);
    trial.get("#account-toggle").onclick();
    await settle();
    assert.deepEqual(state(trial), { ...create, keys: false, trial: true });
  },
  async the_key_guide_under_the_keys_form_knows_a_free_run_is_left() {
    // An account with its free assessment still to use is not asked for keys
    // at the door, but may open the form itself; the steps then say what
    // they are for. An account that has used it reads the steps plainly.
    const left = fixture({ access: { status: 200, body: { ok: true,
      account: { ...ACCOUNT, trial_runs_left: 1 }, accounts: { ...ACCOUNTS, trial_runs: 1 } } } });
    await settle();
    assert.equal(shown(left).gate, false, "A free run left: no keys asked for on the way in");
    left.run("showGate(null, { keysOnly: true })");
    await settle();
    assert.equal(left.get("#byok-form").hidden, false);
    assert.equal(left.get("#byok-key-guide-trial").hidden, false);

    const used = fixture({ access: { status: 200, body: { ok: true,
      account: { ...ACCOUNT, trial_runs_left: 0 }, accounts: { ...ACCOUNTS, trial_runs: 1 } } } });
    await settle();
    assert.equal(used.get("#byok-form").hidden, false, "The free run used: keys are asked for");
    assert.equal(used.get("#byok-key-guide-trial").hidden, true);
  },
  // ── The run header ───────────────────────────────────────────────────
  // Its first line read "COMPLETED · 6:12 · 24 sources · deepseek-v4.1-flash-1017
  // · git:08d26f5 · Usage & cost · Stage timing · worker completed". The
  // model, the revision and the worker's word for an ordinary finish are for
  // whoever maintains the thing; they are under one fold now. A run that
  // ended any other way keeps its reason in the line.
  // The tab's name and the landing's sample list are in the reader's
  // language. Until 2026-11-15 the tab kept the served English <title>, and
  // the list was drawn once: a visitor who switched language on the landing
  // kept the names and facts in the language the page had loaded in.
  async a_change_of_language_renames_the_tab_and_redraws_the_landing_samples() {
    const f = fixture({ access: refused(ACCOUNTS) });
    await settle();
    assert.equal(f.run("document.title"), "brand_full", "At boot the tab is named from the strings");
    const list = f.get("#landing-sample-list");
    const drawn = list.children;
    assert.equal(drawn.length, 2);
    f.run('document.title = "what the markup said"');
    f.get("#ui-lang").listeners.change();
    await settle();
    assert.equal(f.run("document.title"), "brand_full", "...and again when the language changes");
    assert.equal(list.children.length, 2);
    assert.notEqual(list.children[0], drawn[0], "The list is drawn again, in the words of the new language");
    assert.deepEqual(list.children.map((item) => item.children[0].href), drawn.map((item) => item.children[0].href));
    assert.equal(f.requests.filter((r) => r.url === "/api/samples").length, 1, "...from the list it had already read");
  },
  // The scorecard beside the pitch and the retention line under "How long is
  // my data kept?" are drawn by the page, not marked for i18n.apply(). Until
  // 2026-11-21 both were drawn once: a visitor who switched the landing to
  // Chinese went on reading "Strong", "COMMERCIALIZATION READINESS" and
  // "...stored on this server for 90 days..." until a reload, and one who
  // switched back to English read them in Chinese.
  async a_change_of_language_redraws_the_scorecard_and_the_retention_line() {
    const f = fixture({ access: refused(ACCOUNTS) });
    await settle();
    const frame = f.get("#landing-preview");
    const drawn = frame.children[0];
    assert.deepEqual(f.summaries, [SCORES]);
    assert.equal(f.get("#landing-retention").textContent, "byok_retention");
    for (const [prefix, round] of [["zh:", 2], ["en:", 3]]) {
      f.speech.prefix = prefix;
      f.get("#ui-lang").listeners.change();
      await settle();
      assert.deepEqual(f.summaries, Array(round).fill(SCORES),
        `The scorecard is drawn again (${prefix}), from the scores already read`);
      assert.equal(frame.children.length, 1, "...in place of the one drawn before");
      assert.notEqual(frame.children[0], drawn);
      assert.equal(frame.dataset.state, "shown");
      assert.equal(f.get("#landing-preview-note").hidden, true);
      assert.equal(f.get("#landing-retention").textContent, `${prefix}byok_retention`,
        "The retention line is said in the new language");
    }
    assert.equal(f.requests.filter((r) => r.url === PREVIEW_SCORES).length, 1, "Nothing is asked for again");
    assert.equal(f.requests.filter((r) => r.url === "/health").length, 1);

    // A scorecard that could not be read stays the quiet line in every
    // language, and a retention period the server did not give stays unsaid.
    const missing = fixture({ access: refused(ACCOUNTS), replies: { [PREVIEW_SCORES]: { status: 404, body: {} },
      "/health": "unreachable" } });
    await settle();
    missing.speech.prefix = "zh:";
    missing.get("#ui-lang").listeners.change();
    await settle();
    assert.equal(missing.get("#landing-preview").children.length, 0);
    assert.equal(missing.get("#landing-preview").dataset.state, "missing");
    assert.equal(missing.get("#landing-preview-note").hidden, false);
    assert.equal(missing.get("#landing-retention").textContent, "");
    assert.equal(missing.requests.filter((r) => r.url === PREVIEW_SCORES).length, 1);

    // A change of language while the scores are still on their way leaves the
    // frame waiting, not "missing": the card is drawn once, when they arrive,
    // in the language then in use.
    const late = fixture({ access: refused(ACCOUNTS), replies: { [PREVIEW_SCORES]: "late" } });
    await settle();
    late.speech.prefix = "zh:";
    late.get("#ui-lang").listeners.change();
    await settle();
    assert.deepEqual(late.summaries, []);
    assert.equal(late.get("#landing-preview").dataset.state, undefined, "Untouched: the markup's \"loading\" stands");
    assert.equal(late.get("#landing-preview-note").hidden, true, "No word of a failure that has not happened");
    late.deliver();
    await settle();
    assert.deepEqual(late.summaries, [SCORES]);
    assert.equal(late.get("#landing-preview").dataset.state, "shown");

    // A deployment that keeps what it is given until it is deleted says so in
    // the new language too, as /health puts it: with no retention period.
    const kept = fixture({ access: refused(ACCOUNTS), replies: { "/health": { active_runs: 0, max_concurrent: 5 } } });
    await settle();
    assert.equal(kept.get("#landing-retention").textContent, "byok_retention_forever");
    kept.speech.prefix = "zh:";
    kept.get("#ui-lang").listeners.change();
    await settle();
    assert.equal(kept.get("#landing-retention").textContent, "zh:byok_retention_forever");

    // A deployment that put the landing away draws neither on a change of language.
    const open = fixture({ access: { status: 200, body: { ok: true } } });
    await settle();
    assert.equal(shown(open).landing, false);
    const before = open.summaries.length;
    open.speech.prefix = "zh:";
    open.get("#ui-lang").listeners.change();
    await settle();
    assert.equal(open.summaries.length, before, "No scorecard is drawn for a landing nobody sees");
    assert.equal(open.get("#landing-preview").children.length, 0);
  },
  // The screenshot of a finished assessment, further down the landing: one
  // file for each theme, width and language, named by the page.
  async the_screenshot_is_asked_for_once_the_landing_stays_in_the_theme_and_language_in_use() {
    const shot = (f) => ({ desk: f.get("#landing-shot").src, phone: f.get("#landing-shot-phone").srcset });
    const sizes = (f) => [f.get("#landing-shot").width, f.get("#landing-shot").height,
      f.get("#landing-shot-phone").width, f.get("#landing-shot-phone").height];
    const file = (size, theme, language) => `/static/landing/decision-conclusion-${size}-${theme}-${language}.png`;
    const f = fixture({ access: refused(ACCOUNTS), hold: true });
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false });
    assert.deepEqual(shot(f), { desk: undefined, phone: undefined },
      "Not before the deployment has said the landing stays: the picture is below the first screen");
    f.answer();
    await settle();
    assert.deepEqual(shot(f), { desk: file("desktop", "light", "en"), phone: file("phone", "light", "en") });
    assert.deepEqual(sizes(f), [1744, 836, 764, 1416], "Each file's own size, so the page does not move when it loads");
    assert.equal(f.get("#landing-shot").alt, "landing_shot_alt", "Described in the reader's language");
    // The interface language changes: the capture of the interface changes with it.
    f.run('i18n.language = () => "Simplified Chinese"');
    f.get("#ui-lang").listeners.change();
    await settle();
    assert.deepEqual(shot(f), { desk: file("desktop", "light", "zh"), phone: file("phone", "light", "zh") });
    assert.deepEqual(sizes(f), [1744, 836, 764, 1336]);
    // The system goes dark while the page is open, and the page is told.
    assert.equal(f.system.heard.length, 1, "The page listens for the system's theme once");
    f.system.dark = true;
    f.system.heard[0]();
    assert.deepEqual(shot(f), { desk: file("desktop", "dark", "zh"), phone: file("phone", "dark", "zh") });
    // A theme the reader chose with the toggle wins over the system's.
    f.run('document.documentElement.dataset.theme = "light"; paintLandingShot()');
    assert.equal(shot(f).desk, file("desktop", "light", "zh"));
    f.run('document.documentElement.dataset.theme = "dark"; i18n.language = () => "English"; paintLandingShot()');
    assert.deepEqual(shot(f), { desk: file("desktop", "dark", "en"), phone: file("phone", "dark", "en") });

    // A visit that starts in a dark system gets the dark capture from the first.
    const night = fixture({ access: refused(ACCOUNTS), dark: true });
    await settle();
    assert.deepEqual(shot(night), { desk: file("desktop", "dark", "en"), phone: file("phone", "dark", "en") });

    // A deployment that puts the landing away again never asks for the picture,
    // and a change of language there has no picture to change.
    const open = fixture({ access: { status: 200, body: { ok: true } }, hold: true });
    await settle();
    assert.equal(shown(open).landing, true);
    open.answer();
    await settle();
    assert.equal(shown(open).landing, false);
    open.get("#ui-lang").listeners.change();
    assert.deepEqual(shot(open), { desk: undefined, phone: undefined });
    assert.equal(open.system.heard.length, 0);
  },
  // A run on the live site failed at the evidence step on an OCR model, and
  // the one prominent button was "Resume from checkpoint": the same step, on
  // the same model, for another of the day's runs.
  async a_run_that_did_not_finish_offers_what_fits_its_cause() {
    const f = fixture({ access: { status: 200, body: { ok: true } } });
    await settle();
    const OCR = "qwen-vl-ocr-2025-11-20";
    const agents = (model, each) => ["Academic Literature Analyst for x", "Patent Landscape Analyst for x",
      "Market and Competitive Intelligence Analyst for x"].map((role) => ({ role, model, requests: 3, completion_tokens: each * 3 }));
    const flat = (node) => [node, ...(node.children ?? []).flatMap(flat)];
    const paint = (state, facts, { committed = ["retrieval"], canModify = true } = {}) => {
      f.run(`activeRunId = "fixture-run"; paintActions(${JSON.stringify(state)}, ${JSON.stringify({ committed_nodes: committed })},
        ${canModify}, ${JSON.stringify(facts)})`);
      // "Behind More" is in the row and hidden until More is pressed.
      const all = f.get("#run-actions").children.flatMap(flat);
      const top = f.get("#run-actions").children.filter((node) => !node.hidden);
      const named = (node) => node.id || node.textContent;
      return { top: top.map(named), all: all.map(named),
        main: all.filter((node) => String(node.className).includes("btn--primary")).map(named),
        button: (name) => all.find((node) => named(node) === name),
        advice: f.get("#run-advice").hidden ? null : f.get("#run-advice").textContent,
        note: f.get("#run-resume-note").hidden ? null : f.get("#run-resume-note").textContent };
    };

    // The run that prompted this: its model's name says it is another kind of model.
    let page = paint("failed", { error_code: "quality_checks", funded_by: "own_keys", artifacts: ["sources"],
      usage: { agents: agents(OCR, 280) } });
    assert.deepEqual(page.main, ["run-fix"], "Changing the model is the one main action");
    assert.equal(page.top[0], "run-fix", "...and comes first");
    assert.equal(page.button("run-fix").textContent, "Change the model");
    assert.equal(page.button("run-fix").type, "button");
    assert.equal(page.button("run-fix").listeners.click, f.run("openKeyForm"), "It opens the key form, where the model can be changed alone");
    assert.equal(page.button("resume").className, "btn btn--secondary", "Resuming is still there, and is no longer the main thing");
    assert.match(page.advice, new RegExp(`^The model this run used, ${OCR}, does not look like a general chat model\\.`));
    assert.ok(!page.all.includes("run-compare"), "No report was written: nothing to compare");
    assert.equal(page.note, "Resuming starts again at the evidence analysis and reuses what was saved before it.",
      "No allowance on this deployment and no model known to the page: neither is guessed");

    // An ordinary model whose evidence answers were far shorter than any saved run's.
    page = paint("failed", { error_code: "quality_checks", funded_by: "own_keys", artifacts: ["sources"],
      usage: { agents: agents("some-model", 280) } });
    assert.deepEqual(page.main, ["run-fix"]);
    assert.match(page.advice, /^Each answer some-model gave in the evidence step was under 500 tokens/);
    // The same cause with answers of ordinary length: resuming is the main action, and nothing is said about the model.
    page = paint("failed", { error_code: "quality_checks", funded_by: "own_keys", artifacts: ["sources"],
      usage: { agents: agents("some-model", 900) } });
    assert.deepEqual([page.main, page.advice, page.all.includes("run-fix")], [["resume"], null, false]);

    // A key the provider refused: the key form, named for that.
    page = paint("failed", { error_code: "provider_auth", funded_by: "own_keys", artifacts: [] });
    assert.deepEqual(page.main, ["run-fix"]);
    assert.equal(page.button("run-fix").textContent, "Check your API keys");
    assert.equal(page.advice, null);
    // The same refusal on the deployment's keys: not the reader's key, so no such button, and nothing is the main action.
    page = paint("failed", { error_code: "provider_auth", funded_by: "deployment", artifacts: [] });
    assert.deepEqual([page.main, page.all.includes("run-fix")], [[], false]);
    assert.equal(page.button("resume").className, "btn btn--secondary");

    // Out of time with a checkpoint: resuming is the main action.
    page = paint("timeout", { error_code: "timeout_resumable", funded_by: "own_keys", artifacts: ["sources"] });
    assert.deepEqual(page.main, ["resume"]);
    // Out of time with nothing saved: the same topic as a new run, in the row and not behind More.
    page = paint("timeout", { error_code: "timeout", funded_by: "own_keys", artifacts: [] }, { committed: [] });
    assert.deepEqual(page.main, ["run-again"]);
    assert.ok(page.top.includes("run-again") && !page.all.includes("resume"));
    assert.equal(page.note, null, "Nothing to resume from: no note about resuming");
    // Otherwise "Run again" stays behind More.
    page = paint("failed", { error_code: "provider_unreachable", funded_by: "own_keys", artifacts: ["sources"] });
    assert.ok(!page.top.includes("run-again") && page.all.includes("run-again"));
    // The same cause with nothing saved: the page tells the guide so, and the
    // main action is one that exists.
    page = paint("failed", { error_code: "provider_unreachable", funded_by: "own_keys", artifacts: [] }, { committed: [] });
    assert.deepEqual(page.main, ["run-again"]);
    assert.ok(page.top.includes("run-again") && !page.all.includes("resume"));

    // Someone else's run: nothing of this is theirs.
    page = paint("failed", { error_code: "quality_checks", funded_by: "own_keys", artifacts: ["sources"],
      usage: { agents: agents(OCR, 280) } }, { canModify: false });
    assert.deepEqual([page.main, page.advice, page.note, page.all.includes("run-fix"), page.all.includes("resume")],
      [[], null, null, false, false]);

    // Comparing reads two reports: offered for a run that wrote one, whatever its end.
    assert.ok(paint("completed", { artifacts: ["report", "scores", "sources"] }).all.includes("run-compare"));
    assert.ok(paint("failed", { error_code: "quality_checks", funded_by: "own_keys", artifacts: ["report", "sources"] })
      .all.includes("run-compare"));
    assert.ok(!paint("cancelled", { funded_by: "own_keys", artifacts: ["sources"] }).all.includes("run-compare"));
    // A run first seen by its state alone is offered what it always was.
    f.run('activeRunId = "fixture-run"; paintActions("failed", { committed_nodes: ["retrieval"] })');
    const legacy = f.get("#run-actions").children;
    assert.equal(legacy.find((node) => node.textContent === "resume").className, "btn btn--primary");
    assert.ok(legacy.flatMap(flat).some((node) => node.id === "run-compare"));

    // The note beside "Resume" names the model a resume would use now.
    f.run('deploymentModel = "qwen3.8-max"; quotaEnabled = true; lastQuota = { remaining: 2, limit: 3 }');
    page = paint("failed", { error_code: "provider_unreachable", funded_by: "deployment", artifacts: ["sources"],
      usage: { agents: agents("deepseek-v4.1-flash-1017", 900) } });
    assert.equal(page.note, "Resuming uses one more of today's runs. It starts again at the evidence analysis and reuses what "
      + "was saved before it. It will run on qwen3.8-max, not on deepseek-v4.1-flash-1017, which this run used.");
    // An account's own keys: the model saved with the account now, asked of the server.
    // The page's client is a module and cannot be changed in place: the name is given another object with two answers of its own.
    f.run(`accountMode = true; accountKeysSaved = true;
      api = { ...api, savedKeys: async () => ({ saved: true, llm_model: "qwen3.8-max" }), getByok: () => null }`);
    page = paint("failed", { error_code: "quality_checks", funded_by: "own_keys", artifacts: ["sources"],
      usage: { agents: agents(OCR, 280) } });
    assert.ok(!page.note.includes("It will run on"), "Not said before the server has answered");
    await settle();
    assert.ok(f.get("#run-resume-note").textContent.endsWith(`It will run on qwen3.8-max, not on ${OCR}, which this run used.`));
    // Keys kept in the tab are what a resume would send: their model, with nothing asked.
    f.run('api = { ...api, savedKeys: async () => { throw new Error("not asked"); }, getByok: () => ({ model: "tab-model" }) }');
    page = paint("failed", { error_code: "quality_checks", funded_by: "own_keys", artifacts: ["sources"],
      usage: { agents: agents(OCR, 280) } });
    assert.ok(page.note.endsWith(`It will run on tab-model, not on ${OCR}, which this run used.`));

    // An answer that comes back after the page has painted another run's
    // actions is that other run's no longer: it is not written over them.
    f.run(`globalThis.heldKeys = new Promise((resolve) => { globalThis.letGo = resolve; });
      api = { ...api, savedKeys: () => globalThis.heldKeys, getByok: () => null }`);
    paint("failed", { error_code: "quality_checks", funded_by: "own_keys", artifacts: ["sources"],
      usage: { agents: agents(OCR, 280) } });
    page = paint("failed", { error_code: "provider_unreachable", funded_by: "deployment", artifacts: ["sources"] });
    assert.ok(page.note.endsWith("It will run on qwen3.8-max."));
    f.run('globalThis.letGo({ saved: true, llm_model: "late-model" })');
    await settle();
    assert.ok(f.get("#run-resume-note").textContent.endsWith("It will run on qwen3.8-max."), "The late answer is dropped");

    // The model can be changed in the key form. When the form closes, the
    // note says the model that is saved now.
    f.run(`globalThis.savedNow = "first-model"; showGate = async () => { globalThis.savedNow = "changed-in-the-form"; };
      api = { ...api, savedKeys: async () => ({ saved: true, llm_model: globalThis.savedNow }), getByok: () => null }`);
    paint("failed", { error_code: "quality_checks", funded_by: "own_keys", artifacts: ["sources"],
      usage: { agents: agents(OCR, 280) } });
    await settle();
    assert.ok(f.get("#run-resume-note").textContent.includes("It will run on first-model,"));
    f.run("openKeyForm()");
    await settle();
    assert.ok(f.get("#run-resume-note").textContent.includes("It will run on changed-in-the-form,"),
      "Read again after the form: the run would now use the model chosen there");
  },

  // A run takes minutes and does not need the page it was started from.
  async a_run_that_is_going_says_the_page_can_be_closed() {
    const f = fixture({ access: { status: 200, body: { ok: true } } });
    await settle();
    const leave = f.get("#run-leave"), offer = f.get("#run-leave-notify");
    const paint = (body) => f.run(`paintHeader(${JSON.stringify({ topic: "t", ...body })})`);
    paint({ state: "running", viewer_can_modify: true });
    assert.equal(leave.hidden, false);
    assert.equal(f.get("#run-leave-text").textContent, "You can close this page. When the assessment finishes, it is in the history on the left.");
    assert.equal(offer.hidden, true, "No account, or no mail on this deployment: no email to offer");
    // An account on a deployment that sends no mail: an offer there would
    // open a setting that does nothing.
    f.run("accountMode = true; authConfig = { enabled: true, notices: false }; accountNotify = false");
    paint({ state: "running", viewer_can_modify: true });
    assert.deepEqual([leave.hidden, offer.hidden], [false, true]);
    f.run("authConfig = { enabled: true }");
    paint({ state: "running", viewer_can_modify: true });
    assert.equal(offer.hidden, true, "Not said by the deployment: not assumed");
    // An account on a deployment that sends mail, which has not asked for the email: offered, and it opens the settings.
    f.run("accountMode = true; authConfig = { enabled: true, notices: true }; accountNotify = false");
    paint({ state: "running", viewer_can_modify: true });
    assert.equal(offer.hidden, false);
    assert.equal(offer.textContent, "Email me when it finishes");
    assert.equal(offer.listeners.click, f.run("openAccountSettings"));
    f.run("accountNotify = true");
    paint({ state: "running", viewer_can_modify: true });
    assert.equal(offer.hidden, true, "Already asked for");
    assert.equal(leave.hidden, false);
    // Not said of a run that is over, nor to a reader of someone else's.
    for (const state of ["completed", "failed", "cancelled", "timeout", "unknown"]) {
      paint({ state, viewer_can_modify: true });
      assert.equal(leave.hidden, true, state);
    }
    f.run("accountNotify = false");
    paint({ state: "running", viewer_can_modify: false });
    assert.deepEqual([leave.hidden, offer.hidden], [true, true]);
  },

  async the_header_folds_what_only_a_maintainer_reads() {
    const f = fixture({ access: { status: 200, body: { ok: true } } });
    await settle();
    const usage = { total_tokens: 100, agents: [{ model: "deepseek-v4.1-flash-1017" }, { model: "deepseek-v4.1-flash-1017" }] };
    const revision = "git:08d26f5" + "0".repeat(33);
    const paint = (body) => f.run(`paintHeader(${JSON.stringify({ topic: "Solid oxide fuel cells", usage, pipeline_revision: revision, ...body })})`);
    const tech = f.get("#run-tech-details"), terminal = f.get("#run-terminal");

    paint({ state: "completed", terminal: { record_state: "committed", reason_code: "worker_completed" } });
    assert.equal(tech.hidden, false);
    assert.equal(f.get("#run-tech-label").textContent, "· Technical details");
    assert.equal(f.get("#run-identity").textContent, "deepseek-v4.1-flash-1017 · git:08d26f5", "The model and the revision, inside the fold");
    assert.deepEqual(tech.children, [terminal], "An ordinary finish: the worker's word for it goes inside too");
    assert.equal(terminal.textContent, "· worker completed", "...with its text as it was, for whoever opens it");
    assert.equal(f.get("#run-status-record").placedBefore, undefined);

    // The same for the other ordinary endings: the worker's word says what
    // the state already says ("worker failed" beside a pill that reads FAILED).
    const ordinary = [
      { state: "failed", terminal: { record_state: "committed", reason_code: "worker_exception" } },
      { state: "timeout", terminal: { record_state: "committed", reason_code: "hard_timeout" } },
      { state: "cancelled", terminal: { record_state: "committed", reason_code: "user_cancelled" } },
    ];
    for (const body of ordinary) {
      paint(body);
      assert.deepEqual(tech.children.at(-1), terminal, `${JSON.stringify(body)} goes inside the fold`);
      assert.equal(f.get("#run-status-record").placedBefore, undefined, "...and is not left in the line");
      assert.equal(tech.hidden, false);
      assert.equal(f.run(`runView.isOrdinaryEnding(${JSON.stringify(body.terminal)}, ${JSON.stringify(body.state)})`), true);
    }
    const folded = tech.children.length;

    // Anything else is not folded: the reason is put back in the line. A
    // record that is missing or unreadable, a reason that disagrees with the
    // state, or one this page does not know, is not an ordinary ending.
    const endings = [
      { state: "completed", terminal: { record_state: "unreadable", reason_code: "worker_completed" } },
      { state: "failed", terminal: { record_state: "unreadable", reason_code: "worker_exception" } },
      { state: "failed", terminal: null },
      { state: "failed", terminal: { record_state: "committed", reason_code: "hard_timeout" } },
      { state: "cancelled", terminal: { record_state: "committed", reason_code: "worker_exception" } },
      { state: "completed", terminal: null },
      { state: "failed", terminal: { record_state: "committed", reason_code: "worker_completed" } },
      // A finished run whose record gives any other reason: not the plain case.
      { state: "completed", terminal: { record_state: "committed", reason_code: "status_reconciled" } },
    ];
    for (const [index, body] of endings.entries()) {
      paint(body);
      assert.equal(f.get("#run-status-record").placedBefore.length, index + 1, `${JSON.stringify(body)} stays in the line`);
      assert.equal(f.get("#run-status-record").placedBefore.at(-1), terminal);
      assert.equal(tech.children.length, folded, "...and is not put in the fold again");
      assert.equal(tech.hidden, false, "The fold is still there for the model and the revision");
    }
    for (const body of endings) {
      assert.equal(f.run(`runView.isPlainCompletion(${JSON.stringify(body.terminal)}, ${JSON.stringify(body.state)})`), false);
      assert.equal(f.run(`runView.isOrdinaryEnding(${JSON.stringify(body.terminal)}, ${JSON.stringify(body.state)})`), false);
    }
    assert.equal(f.run('runView.isPlainCompletion({ reason_code: "worker_completed" }, "completed")'), true);

    // Nothing to put in it: no fold.
    f.run('paintHeader({ topic: "t", state: "running" })');
    assert.equal(tech.hidden, true);
    assert.equal(f.get("#run-identity").textContent, "");
  },
  // ── The header a reader of a shared link is shown ────────────────────
  // A shared link is how a report travels: a technology transfer office or
  // an investor forwards it to a colleague. Until 2026-11-21 that colleague
  // read the header written for whoever ran it: "COMPLETED · 3:57", the
  // source counts, "About 31.8k tokens · no cost shown, as no unit price is
  // on record yet for qwen3.8-2.4t-a95b; see your provider's console for the
  // exact amount", two folds and a paragraph about resuming, some 430 px
  // before the report (production run 20261120T131247Z). They have no
  // console, the 3:57 was the resume's part of a 29-minute assessment, and
  // nothing said when the evidence was gathered.
  async a_reader_of_a_shared_run_is_shown_a_header_written_for_them() {
    const f = fixture({ access: { status: 200, body: { ok: true } } });
    await settle();
    for (const id of ["run-assessed", "run-model"]) assert.ok(hiddenAtStart.includes(id), `#${id} starts hidden in the markup`);
    const MODEL = "qwen3.8-2.4t-a95b";
    const PARENT = "20261120T125001Z-" + "b".repeat(32);
    // The two reads of that run, in the shape the API gives them.
    const resumed = {
      run_id: "20261120T131247Z-55c74e5736d56d0f54ba79d24f1bbae7", topic: "Solid oxide fuel cells",
      state: "completed", elapsed_seconds: 237, funded_by: "own_keys", llm_model: MODEL,
      daily_charge: "not_charged", source_counts: { academic: 12, patent: 8, market: 9 },
      usage: { total_tokens: 31_800, cost_usd: null, cost_complete: false, unpriced_models: [MODEL],
        accounting_scope: "crew_nodes", agents: [{ role: "Scorer", model: MODEL, total_tokens: 31_800 }] },
      usage_accounting: { state: "complete" },
      auxiliary_usage: { record_state: "recorded", call_count: 1, observed_tokens: 12, observed_cost_usd: 0.0001 },
      stage_timings: [{ stage: "Agent 6 — Commercialization Scoring", started_at: "2026-11-20T13:12:50+00:00", duration_seconds: 230 }],
      pipeline_revision: "git:49ad312" + "0".repeat(33),
      terminal: { record_state: "committed", reason_code: "worker_completed" },
      recovery: { state: "reused", source_run_id: PARENT, next_node: "scorer",
        reused_nodes: ["retrieval", "academic", "patent", "market", "writer", "reviewer"] },
      lineage: {
        earlier: [{ run_id: PARENT, record: "available", state: "failed", elapsed_seconds: 1531, total_tokens: 124_600,
          usage_state: "lower_bound", cost_usd: null, cost_complete: false }],
        combined: { runs: 2, elapsed_seconds: 1768, elapsed_complete: true, total_tokens: 156_400,
          usage_state: "lower_bound", cost_usd: null, cost_complete: false },
      },
    };
    const paint = (body) => f.run(`paintHeader(${JSON.stringify(body)})`);
    const shown = (id) => (f.get(id).hidden ? null : f.get(id).textContent);
    const line = () => ["#run-assessed", "#run-model", "#run-elapsed", "#run-eta", "#run-sources"].map(shown);
    const folds = () => ["#run-usage-details", "#run-timing-details", "#run-tech-details", "#run-lineage"]
      .map((id) => !f.get(id).hidden);

    // Its owner: the header as it was, every word of it.
    paint({ ...resumed, viewer_can_modify: true });
    assert.deepEqual(line(), [null, null, "3:57", null, "· 29 sources · 12 academic · 8 patent · 9 market"]);
    assert.deepEqual(folds(), [true, true, true, true]);
    assert.match(f.get("#run-usage-label").textContent, /see your provider's console for the exact amount$/);
    assert.match(f.get("#run-lineage").children.join(""), /In all: 29:28 \(3:57 here \+ 25:31 before\)/);

    // Anyone else: when, on what, how long in all; nothing about tokens, money, stages or resuming.
    for (const reader of [{ viewer_can_modify: false }, { viewer_can_modify: null }]) {
      paint({ ...resumed, ...reader });
      assert.deepEqual(line(), ["Assessed 20 Nov 2026", `· Model: ${MODEL}`, "· took 29:28 in all", null, ""], JSON.stringify(reader));
      assert.deepEqual(folds(), [false, false, false, false], "No token count, no cost, no stage times, no resume paragraph");
      assert.equal(f.get("#run-assessed").title, "Dates are in UTC.");
      // Not hidden with the words still in them: a hidden fold is still in the page's text.
      assert.deepEqual(["#run-usage", "#run-timing", "#run-identity"].map((id) => f.get(id).textContent), ["", "", ""]);
      assert.equal(f.get("#run-usage").title, "");
      assert.equal(f.get("#run-usage-label").textContent, "· Usage & cost");
    }
    // An anonymous reader is one whatever the read says.
    f.run("viewerMode = true");
    paint({ ...resumed, viewer_can_modify: true });
    assert.equal(shown("#run-assessed"), "Assessed 20 Nov 2026");
    assert.deepEqual(folds(), [false, false, false, false]);
    f.run("viewerMode = false");

    // The owner again: nothing of the reader's header is left behind.
    paint({ ...resumed, viewer_can_modify: true });
    assert.deepEqual(line(), [null, null, "3:57", null, "· 29 sources · 12 academic · 8 patent · 9 market"]);

    const reader = (body) => { paint({ ...resumed, viewer_can_modify: false, ...body }); return line().slice(0, 3); };
    // A run that is not a resume: its own time, said as what it took.
    assert.deepEqual(reader({ recovery: null, lineage: null, run_id: "20261120T131247Z-" + "c".repeat(32) }),
      ["Assessed 20 Nov 2026", `· Model: ${MODEL}`, "· took 3:57"]);
    // A total the server cannot vouch for (an earlier run's time is not known) is not written.
    assert.deepEqual(reader({ lineage: { ...resumed.lineage, combined: { ...resumed.lineage.combined, elapsed_complete: false } } }),
      ["Assessed 20 Nov 2026", `· Model: ${MODEL}`, ""]);
    // The evidence was gathered when the first run began: a chain over two days says both.
    const older = "20261118T231500Z-" + "d".repeat(32);
    assert.deepEqual(reader({ lineage: { ...resumed.lineage, earlier: [...resumed.lineage.earlier, { run_id: older, record: "missing" }] } })[0],
      "Assessed 18 Nov 2026 – 20 Nov 2026");
    // A resume that could reuse nothing gathered its own evidence.
    assert.equal(reader({ run_id: "20261121T010000Z-" + "e".repeat(32), recovery: { state: "cold_start", source_run_id: PARENT } })[0],
      "Assessed 21 Nov 2026");
    // Still going: the time so far, and a run that did not finish says it ran.
    assert.deepEqual(reader({ state: "running", recovery: null, lineage: null, elapsed_seconds: 120,
      eta: { low_seconds: 300, high_seconds: 900, basis_runs: 5 } }).slice(2), ["· running for 2:00"]);
    for (const id of ["#run-eta", "#run-deadline", "#run-current-step", "#run-deadline-note"]) {
      assert.equal(shown(id), null, "Live timing details are for the person running this assessment");
      assert.equal(f.get(id).textContent, "");
    }
    assert.deepEqual(reader({ state: "running", elapsed_seconds: 120,
      lineage: { ...resumed.lineage, combined: { ...resumed.lineage.combined, elapsed_seconds: 1651 } } }).slice(2),
      ["· running for 27:31 in all"]);
    assert.deepEqual(reader({ state: "failed", recovery: null, lineage: null, run_id: "20261120T131247Z-" + "f".repeat(32) }),
      ["Started 20 Nov 2026", `· Model: ${MODEL}`, "· ran for 3:57"]);
    // Nothing to go by: nothing said. The model falls back to the usage record's.
    assert.deepEqual(reader({ run_id: "legacy-id", stage_timings: [], llm_model: null, recovery: null, lineage: null, elapsed_seconds: null }),
      [null, `Model: ${MODEL}`, ""]);
    assert.deepEqual(reader({ run_id: "legacy-id", stage_timings: [], llm_model: null, usage: null, recovery: null, lineage: null }),
      [null, null, "took 3:57"]);
    // An id that does not say when the run began: its first stage does.
    assert.equal(reader({ run_id: "legacy-id", recovery: null, lineage: null,
      stage_timings: [{ stage: "Source Collection & Validation", started_at: "2026-11-19T10:00:00+00:00" }] })[0], "Assessed 19 Nov 2026");
    // A failure's reason stays; whether it spent the owner's daily run is the owner's business.
    paint({ ...resumed, state: "failed", error: "The run stopped.", error_code: null, daily_charge: "charged",
      recovery: null, lineage: null, viewer_can_modify: false });
    assert.equal(shown("#run-outcome"), "The run stopped.");
    paint({ ...resumed, state: "failed", error: "The run stopped.", error_code: null, daily_charge: "charged",
      recovery: null, lineage: null, viewer_can_modify: true });
    assert.equal(shown("#run-outcome"), "The run stopped. This run counted toward today's quota.");
  },
  // ── A link to a run that is not there ────────────────────────────────
  // Deleted by its owner, past the deployment's retention, or cut short when
  // it was copied: until 2026-11-21 such a link opened a header reading "…",
  // "UNKNOWN" and "— · Usage & cost" over one small line, "The server could
  // not find this run. Automatic polling has stopped.", and a blank page.
  // Every shared link turns into this once its run reaches the retention age.
  async a_link_to_a_run_that_is_gone_says_so_and_offers_a_way_on() {
    for (const id of ["run-gone", "run-gone-retention"]) assert.ok(hiddenAtStart.includes(id), `#${id} starts hidden in the markup`);
    assert.ok(!hiddenAtStart.includes("run-head"), "The run's header is shown until a read says the run is gone");
    const gone = { status: 404, body: { detail: "No run with id 20260926T121212Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" } };
    const f = fixture({ pathname: DEEP_LINK, access: refused(ACCOUNTS), replies: { [`${RUN_API}/progress?since=0`]: gone } });
    await settle();
    assert.equal(f.get("#viewer-bar").hidden, false, "A reader, as for any shared link");
    assert.deepEqual([f.get("#run-gone").hidden, f.get("#run-head").hidden, f.get("#run-body").hidden], [false, true, true],
      "The page says the assessment cannot be opened, in place of an empty run");
    assert.equal(f.get("#run-gone-retention").hidden, false);
    assert.equal(f.get("#run-gone-retention").textContent, "gone_retention_days",
      "The retention period is the deployment's own, read from /health (tests/test_shared_link_pages.py words it)");
    assert.equal(f.get("#run-connection").textContent, "", "No word about polling");
    assert.deepEqual(f.get("#toasts").children.map((node) => node.textContent), [], "...and no toast saying it again");
    assert.equal(f.requests.filter((r) => r.url.startsWith(`${RUN_API}/progress`)).length, 1, "Asked once: nothing left to follow");

    // A deployment that keeps assessments until they are deleted: no such reason to give.
    const forever = fixture({ pathname: DEEP_LINK, access: refused(ACCOUNTS),
      replies: { [`${RUN_API}/progress?since=0`]: gone, "/health": { retention_days: 0, active_runs: 0, max_concurrent: 5 } } });
    await settle();
    assert.equal(forever.get("#run-gone").hidden, false);
    assert.equal(forever.get("#run-gone-retention").hidden, true);

    // Another run opened from here gets its header back.
    f.run('openRun("20260926T131313Z-" + "c".repeat(32))');
    assert.deepEqual([f.get("#run-gone").hidden, f.get("#run-head").hidden, f.get("#run-body").hidden], [true, false, false]);
  },
  // ── Whose run it is ──────────────────────────────────────────────────
  // A run's link opens for whoever holds it. Until 2026-11-15 a signed-in
  // reader of someone else's run was offered Delete, and Cancel while it
  // ran; the server refused them, and nothing said the report was not
  // theirs. The run's reads now say whether this caller may change it
  // (tests/test_viewer_can_modify.py), and the page offers accordingly.
  async the_owners_actions_keep_the_rare_ones_behind_more() {
    const f = fixture({ access: { status: 200, body: { ok: true } } });
    await settle();
    const names = () => f.get("#run-actions").children.map((node) => node.id || node.textContent || node.download || "");
    const shown = () => f.get("#run-actions").children.filter((node) => !node.hidden)
      .map((node) => node.id || node.textContent || node.download || "");
    const paint = (state, canModify, checkpointing = null) =>
      f.run(`activeRunId = "fixture-run"; paintActions(${JSON.stringify(state)}, ${JSON.stringify(checkpointing)}, ${canModify})`);

    paint("completed", true);
    assert.deepEqual(names(), ["fixture-run.pdf", "run-copy-link", "run-more", "fixture-run.md", "run-again", "run-compare", "delete_run"],
      "The PDF and the link stay out; Delete is last");
    assert.deepEqual(shown(), ["fixture-run.pdf", "run-copy-link", "run-more"], "The rest is behind More until it is asked for");
    const more = f.get("#run-actions").children.find((node) => node.id === "run-more");
    assert.equal(more.type, "button");
    assert.equal(more.attributes["aria-expanded"], "false");
    more.listeners.click();
    assert.equal(shown().length, 7, "One press shows them");
    assert.equal(f.get("#run-actions").children.find((node) => node.id === "run-more").attributes["aria-expanded"], "true");
    // A repaint (a poll, a change of language) leaves an opened More open.
    paint("completed", true);
    assert.equal(shown().length, 7);
    f.get("#run-actions").children.find((node) => node.id === "run-more").listeners.click();
    assert.deepEqual(shown(), ["fixture-run.pdf", "run-copy-link", "run-more"], "...and a second press puts them away");
    // Another run starts with More closed.
    f.get("#run-actions").children.find((node) => node.id === "run-more").listeners.click();
    f.run('activeRunId = "another-run"; paintActions("completed", null, true)');
    assert.equal(shown().length, 3);

    paint("failed", true, { committed_nodes: ["retrieval"] });
    assert.deepEqual(names(), ["resume", "run-copy-link", "run-more", "run-again", "run-compare", "delete_run"],
      "A run that stopped short leads with Resume");
    paint("cancelled", true);
    assert.deepEqual(names(), ["run-copy-link", "run-more", "run-again", "run-compare", "delete_run"]);
    paint("running", true);
    assert.deepEqual(names(), ["cancel", "run-copy-link"], "A running run has two actions and no More");
    assert.equal(f.get("#run-shared").hidden, true, "Nothing says 'shared with you' on one's own run");
  },
  async a_signed_in_reader_of_someone_elses_run_is_told_so_and_offered_no_owner_action() {
    const f = fixture({ access: { status: 200, body: { ok: true } } });
    await settle();
    const names = () => f.get("#run-actions").children.map((node) => node.id || node.textContent || node.download || "");
    const paint = (state, checkpointing = null) =>
      f.run(`activeRunId = "fixture-run"; paintActions(${JSON.stringify(state)}, ${JSON.stringify(checkpointing)}, false)`);

    paint("completed");
    assert.deepEqual(names(), ["fixture-run.pdf", "run-copy-link", "run-more", "fixture-run.md", "run-again"],
      "Read it, keep it, pass it on, or assess the topic oneself: no Compare, no Delete");
    const again = f.get("#run-actions").children.find((node) => node.id === "run-again");
    assert.equal(again.textContent, "run_again_own", "Named for what it is: a new assessment of one's own");
    assert.equal(f.get("#run-shared").hidden, false, "A line says the assessment was shared and is read-only");

    paint("running");
    assert.deepEqual(names(), ["run-copy-link"], "No Cancel on someone else's running assessment");
    paint("failed", { committed_nodes: ["retrieval"] });
    assert.deepEqual(names(), ["run-copy-link", "run-again"], "No Resume, which is paid for by the owner; one extra needs no More");
    for (const state of ["completed", "failed", "running", "cancelled", "timeout"]) {
      paint(state, { committed_nodes: ["retrieval"] });
      for (const forbidden of ["cancel", "resume", "delete_run", "run-compare"]) {
        assert.ok(!names().includes(forbidden), `${forbidden} is not offered to a signed-in reader of a ${state} run`);
      }
    }
    // The notice's button starts a new assessment of the reader's own.
    f.get("#pane-compose").hidden = true;
    f.get("#pane-run").hidden = false;
    f.get("#run-shared-new").onclick();
    assert.equal(f.get("#pane-compose").hidden, false);
    assert.equal(f.get("#pane-run").hidden, true);

    // Back on a run of one's own, the notice goes.
    f.run('activeRunId = "fixture-run"; paintActions("completed", null, true)');
    assert.equal(f.get("#run-shared").hidden, true);
  },
  async what_the_server_says_decides_and_a_run_with_no_owner_is_this_tabs_or_not() {
    const f = fixture({ access: { status: 200, body: { ok: true } } });
    await settle();
    const may = (progress) => f.run(`activeRunId = "fixture-run"; mayModify(${JSON.stringify(progress)})`);
    assert.equal(may({ viewer_can_modify: true }), true);
    assert.equal(may({ viewer_can_modify: false }), false);
    // Null: no owner on record, a keys-only run. The server cannot say whose
    // it is; this tab can, for the runs it submitted itself.
    assert.equal(may({ viewer_can_modify: null }), false, "Someone else's keys-only run, opened from a link");
    tab.set("byok-runs", JSON.stringify([{ run_id: "fixture-run", topic: "t" }]));
    assert.equal(may({ viewer_can_modify: null }), true, "A keys-only run this tab submitted");
    tab.set("byok-runs", JSON.stringify([{ run_id: "some-other-run", topic: "t" }]));
    assert.equal(may({ viewer_can_modify: null }), false);
    // A server that does not say (older than the field), or no status yet: as before.
    assert.equal(may({}), true);
    assert.equal(may(undefined), true);
    assert.equal(may({ viewer_can_modify: "yes" }), true, "Only a boolean or null is an answer");
  },
  async trial_said_on_the_way_in() {
    // With a first assessment on the deployment's keys (#370), the landing and
    // the card must not still tell a newcomer that every run needs keys.
    const trial = fixture({ access: refused({ ...ACCOUNTS, trial_runs: 1 }) });
    await settle();
    assert.equal(trial.get("#landing-trial").hidden, false, "The landing says the first assessment is free");
    assert.equal(trial.get("#landing-key-guide-trial").hidden, false,
      "...and the three steps to two keys say they are for the assessments after it");
    trial.get("#landing-create").onclick();
    await settle();
    assert.equal(trial.get("#account-sub").hidden, true, "The card's sentence about paying with keys gives way");
    assert.equal(trial.get("#account-sub-trial").hidden, false, "...to one that says the first assessment needs none");

    const none = fixture({ access: refused(ACCOUNTS) });
    await settle();
    assert.equal(none.get("#landing-trial").hidden, true, "Nothing is promised where the operator offers no trial");
    assert.equal(none.get("#landing-key-guide-trial").hidden, true, "...and the steps stand as they are: keys come first there");
    none.get("#landing-create").onclick();
    await settle();
    assert.equal(none.get("#account-sub").hidden, false);
    assert.equal(none.get("#account-sub-trial").hidden, true);
  },
  async anonymous_codes_only() {
    const f = fixture({ access: refused(null) });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: true },
      "A deployment without accounts is invite-only; its visitors meet the code card as before");
    assert.equal(f.get("#gate-form").hidden, false);
  },
  async signed_in() {
    const f = fixture({ access: { status: 200, body: { ok: true, account: ACCOUNT, accounts: ACCOUNTS } } });
    await settle();
    const state = shown(f);
    assert.equal(state.landing, false, "A stored session skips the landing");
    assert.equal(state.workbench, true);
    assert.equal(state.gate, true, "...and an account without keys is asked for them, as before");
    assert.equal(f.get("#byok-form").hidden, false);
    assert.ok(!f.requests.some((r) => r.url === "/api/samples" || r.url === PREVIEW_SCORES),
      "A stored session never paints the landing, so nothing is asked for it");
  },
  async signed_in_admin_funded() {
    const admin = { ...ACCOUNT, admin: true };
    const f = fixture({ access: { status: 200, body: { ok: true, account: admin, accounts: { ...ACCOUNTS, admin_funded: true } } } });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: false },
      "An administrator the deployment funds goes straight to the workbench: no keys to ask for");
    const plain = fixture({ access: { status: 200, body: { ok: true, account: admin, accounts: ACCOUNTS } } });
    await settle();
    assert.equal(shown(plain).gate, true, "...only where the deployment says it funds them");
    const member = fixture({ access: { status: 200, body: { ok: true, account: ACCOUNT, accounts: { ...ACCOUNTS, admin_funded: true } } } });
    await settle();
    assert.equal(shown(member).gate, true, "...and only an administrator");
  },
  async ungated() {
    const f = fixture({ access: { status: 200, body: { ok: true } } });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: false }, "No gate at all: the workbench, as always");
    assert.equal(f.boot(), "ready");
    assert.equal(f.get("#boot-failure").hidden, true, "The notice is for a boot that got no answer");
  },
  async logout_goes_home() {
    const f = fixture({ pathname: DEEP_LINK, access: { status: 200, body: { ok: true, account: ACCOUNT, accounts: ACCOUNTS } } });
    await settle();
    await f.get("#account-exit").listeners.click();
    await settle();
    assert.ok(f.requests.some((r) => r.url === "/api/auth/logout"));
    assert.equal(disk.get("session-token"), undefined);
    assert.deepEqual(f.navigations, ["/"], "Signing out of an account leaves for the front door, not a reload of the run just left");
    assert.deepEqual(f.reloads, []);
  },
  async reset_link() {
    // The page a reset link opens. No session decides anything: the card
    // opens on the new-password form and then signs in with the new password.
    disk.set("session-token", "stale-token");   // a browser that was signed in when the password was lost
    const f = fixture({ pathname: "/reset", search: "?token=link-token", access: refused(ACCOUNTS),
      replies: { "/api/auth/config": ACCOUNTS, "/api/auth/password/reset": { email: ACCOUNT.email } } });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: true }, "A reset link opens the card, not the landing");
    assert.equal(f.get("#reset-form").hidden, false, "...on the new-password form");
    assert.equal(f.get("#account-form").hidden, true);
    assert.ok(f.requests.some((r) => r.url === "/api/auth/config"), "The sign-in configuration comes from its own request");
    assert.ok(!f.requests.some((r) => r.url === "/api/access/check"), "...not from an access check nobody could pass");
    f.get("#reset-password").value = "a new password long enough";
    f.get("#reset-form").onsubmit({ preventDefault() {} });
    await settle();
    const posted = f.requests.find((r) => r.url === "/api/auth/password/reset");
    assert.deepEqual(JSON.parse(posted.options.body), { token: "link-token", new_password: "a new password long enough" },
      "The token from the link goes with the password");
    assert.equal(f.get("#reset-form").hidden, true, "Then the sign-in form, with the address filled in");
    assert.equal(f.get("#account-form").hidden, false);
    assert.equal(f.get("#account-email-input").value, ACCOUNT.email);
    assert.equal(disk.get("session-token"), undefined, "The stale session is dropped: every session of the account ended");
    f.get("#account-password").value = "a new password long enough";
    f.get("#account-form").onsubmit({ preventDefault() {} });
    await settle();
    assert.equal(disk.get("session-token"), "fixture-token", "Signing in with the new password works from the same card");
    assert.equal(f.get("#byok-form").hidden, false);
  },
  async reset_link_refused() {
    const f = fixture({ pathname: "/reset", search: "?token=stale", access: refused(ACCOUNTS),
      replies: { "/api/auth/config": ACCOUNTS } });
    globalThis.fetch = ((inner) => (url, options) => url === "/api/auth/password/reset"
      ? Promise.resolve(new Response(JSON.stringify({ detail: "expired" }), { status: 410,
          headers: { "Content-Type": "application/json", "X-Error-Code": "reset_expired" } }))
      : inner(url, options))(globalThis.fetch);
    await settle();
    f.get("#reset-password").value = "a new password long enough";
    f.get("#reset-form").onsubmit({ preventDefault() {} });
    await settle();
    assert.equal(f.get("#reset-error").hidden, false, "A spent or stale link is said so on the form");
    assert.equal(f.get("#reset-error").textContent, "reset_expired");
    assert.equal(f.get("#reset-form").hidden, false, "...which stays, so the person can read it");
    f.get("#reset-back").onclick();
    assert.equal(f.get("#account-form").hidden, false, "Back to sign in, where the forgot button asks for a new link");
    assert.equal(f.get("#account-forgot").hidden, false);
  },
  async forgot_from_sign_in() {
    const f = fixture({ pathname: DEEP_LINK, access: refused(ACCOUNTS), replies: { "/api/auth/password/forgot": {} } });
    await settle();
    f.get("#viewer-sign-in").onclick();
    await settle();
    assert.equal(f.get("#account-forgot").hidden, false, "With mail, the sign-in form offers the reset");
    f.get("#account-email-input").value = ACCOUNT.email;
    f.get("#account-forgot").onclick();
    assert.equal(f.get("#forgot-form").hidden, false);
    assert.equal(f.get("#account-form").hidden, true);
    assert.equal(f.get("#forgot-email").value, ACCOUNT.email, "The address typed on the sign-in form is carried over");
    f.get("#forgot-form").onsubmit({ preventDefault() {} });
    await settle();
    const posted = f.requests.find((r) => r.url === "/api/auth/password/forgot");
    assert.deepEqual(JSON.parse(posted.options.body), { email: ACCOUNT.email });
    assert.equal(f.get("#forgot-sent").hidden, false, "The same words whether or not an account has the address");
    assert.equal(f.get("#forgot-error").hidden, true);
    f.get("#forgot-back").onclick();
    assert.equal(f.get("#account-form").hidden, false);
    assert.equal(f.get("#forgot-form").hidden, true);
    f.get("#account-toggle").onclick();
    assert.equal(f.get("#account-forgot").hidden, true, "Creating an account, there is no password to have forgotten");
  },
  async forgot_absent_without_mail() {
    const f = fixture({ pathname: DEEP_LINK, access: refused({ ...ACCOUNTS, password_reset: false }) });
    await settle();
    f.get("#viewer-sign-in").onclick();
    await settle();
    assert.equal(f.get("#account-form").hidden, false);
    assert.equal(f.get("#account-forgot").hidden, true, "Without mail there is no link to send; the privacy page names the operator");
  },
  // ── The account's corner of the rail ─────────────────────────────────
  // Until 2026-11-15: one line, "Signed in as" with a cut-off address and
  // three small underlined links; drawn once, so it stayed in the language
  // it was first drawn in.
  async the_account_menu_names_the_account_and_opens_on_request() {
    const f = fixture({ access: { status: 200, body: { ok: true, account: { ...ACCOUNT, email: "émilie.durand@example.test" }, accounts: ACCOUNTS } } });
    await settle();
    f.get("#byok-skip").onclick();
    await settle();
    const button = f.get("#account-menu-button"), menu = f.get("#account-menu");
    assert.equal(f.get("#account-badge").hidden, false);
    assert.equal(f.get("#account-avatar").textContent, "É", "The address's first letter, as a capital");
    assert.equal(f.get("#account-email").textContent, "émilie.durand@example.test", "The address, not a sentence around it");
    assert.equal(f.get("#account-menu-email").textContent, "émilie.durand@example.test", "...and whole, in the menu");
    assert.equal(button.attributes["aria-label"], "account_menu_label");
    assert.equal(button.title, "émilie.durand@example.test");
    assert.equal(f.get("#account-console").hidden, true, "The console is an administrator's");
    // Closed until asked for.
    menu.hidden = true;
    assert.equal(button.attributes["aria-expanded"], "false");
    button.listeners.click();
    assert.deepEqual([menu.hidden, button.attributes["aria-expanded"]], [false, "true"]);
    button.listeners.click();
    assert.deepEqual([menu.hidden, button.attributes["aria-expanded"]], [true, "false"], "A second press closes it");
    // The keys are heard on the account area as a whole, so they work with
    // focus on the button (where a click leaves it) as well as in the menu.
    const area = f.get("#account-badge");
    assert.equal(menu.listeners.keydown, undefined, "Not on the menu alone: Escape on the button would not reach it");
    const items = [f.get("#account-manage"), f.get("#account-keys"), f.get("#account-exit")];
    menu.querySelectorAll = () => items;
    const press = (key, onPrevent = () => {}) => area.listeners.keydown({ key, preventDefault: onPrevent });
    // Down or Up on the closed button opens it on the first or the last item; no other key opens it.
    for (const [key, landed] of [["ArrowDown", items[0]], ["ArrowUp", items[2]]]) {
      let prevented = false;
      const before = landed.focused ?? 0;
      press(key, () => { prevented = true; });
      assert.deepEqual([menu.hidden, prevented, landed.focused], [false, true, before + 1], key);
      button.listeners.click();
    }
    for (const key of ["a", "Home", "End", "Enter", "Escape", "Tab"]) {
      press(key, () => { throw new Error(`${key} is not the closed menu's key`); });
      assert.equal(menu.hidden, true, key);
    }
    // Escape closes it and gives focus back to the button; Tab closes it and moves on.
    button.listeners.click();
    const before = button.focused ?? 0;
    let escaped = false;
    press("Escape", () => { escaped = true; });
    assert.deepEqual([menu.hidden, escaped, button.focused], [true, true, before + 1]);
    button.listeners.click();
    press("Tab", () => { throw new Error("Tab is left to the browser"); });
    assert.deepEqual([menu.hidden, button.focused], [true, before + 1], "Tab does not pull focus back");
    // A hidden item (the console, for an ordinary account) is not a stop.
    items.splice(2, 0, Object.assign(f.get("#account-console"), { hidden: true }));
    press("ArrowUp");
    assert.equal(f.get("#account-console").focused, undefined);
    // ...also on the way past it: Up from Sign out lands on API keys.
    const keysBefore = f.get("#account-keys").focused ?? 0;
    f.run("document").activeElement = f.get("#account-exit");
    press("ArrowUp");
    assert.equal(f.get("#account-console").focused, undefined, "The hidden console is skipped");
    assert.equal(f.get("#account-keys").focused, keysBefore + 1);
    f.run("document").activeElement = undefined;
    button.listeners.click();
    // Choosing an item closes it; a press on the menu's own padding does not.
    button.listeners.click();
    menu.listeners.click({ target: { closest: () => null } });
    assert.equal(menu.hidden, false);
    menu.listeners.click({ target: { closest: (selector) => (selector === '[role="menuitem"]' ? {} : null) } });
    assert.equal(menu.hidden, true);
    // A change of language repaints the name the button goes by.
    button.attributes["aria-label"] = "stale";
    f.get("#account-avatar").textContent = "stale";
    f.get("#ui-lang").listeners.change();
    await settle();
    assert.equal(button.attributes["aria-label"], "account_menu_label");
    assert.equal(f.get("#account-avatar").textContent, "É");
    // The keys within the menu.
    const target = (key, index, count) => f.run(`menuKeyTarget(${JSON.stringify(key)}, ${index}, ${count})`);
    assert.deepEqual([target("ArrowDown", 0, 3), target("ArrowDown", 2, 3), target("ArrowDown", -1, 3)], [1, 0, 0]);
    assert.deepEqual([target("ArrowUp", 0, 3), target("ArrowUp", 2, 3), target("ArrowUp", -1, 3)], [2, 1, 2]);
    assert.deepEqual([target("Home", 2, 3), target("End", 0, 3)], [0, 2]);
    assert.deepEqual([target("Enter", 0, 3), target("a", 0, 3), target("ArrowDown", 0, 0)], [null, null, null]);
    // An administrator's menu has the console; an address with no letter gets a mark, not nothing.
    f.run('applyAccountMode({ email: "@", admin: true, verified: true })');
    assert.equal(f.get("#account-console").hidden, false);
    assert.equal(f.get("#account-avatar").textContent, "?");
    assert.equal(menu.hidden, true, "Signing in leaves the menu closed");
  },
  // "0/5 running" and five dots are the whole deployment's slots: a number
  // about other people's work, and cut off in the phone's rail.
  async the_slots_are_an_administrators_and_everyone_else_is_told_only_when_full() {
    const f = fixture({ access: { status: 200, body: { ok: true, account: ACCOUNT, accounts: ACCOUNTS } } });
    await settle();
    f.get("#byok-skip").onclick();
    await settle();
    const line = () => ({ shown: !f.get("#capacity").hidden, dots: !f.get("#capacity-dots").hidden,
      label: f.get("#capacity-label").textContent, title: f.get("#capacity-label").title });
    const reading = (active, max) => f.run(`capacityReading = { active_paid_operations: ${active}, max_concurrent: ${max}, retention_days: 7 };
      paintCapacityLabel()`);
    reading(0, 5);
    assert.equal(line().shown, false, "An ordinary account is not shown the slots");
    reading(4, 5);
    assert.equal(line().shown, false);
    reading(5, 5);
    assert.deepEqual(line(), { shown: true, dots: false, label: "capacity_busy", title: "capacity_busy_title" },
      "...until every one is taken, and then in words");
    reading(6, 5);
    assert.equal(line().shown, true);
    reading(0, 0);
    assert.equal(line().shown, false, "A deployment that reports no slots is not 'busy'");
    f.run('capacityReading = "offline"; paintCapacityLabel()');
    assert.deepEqual([line().shown, line().dots, line().label], [true, false, "offline"], "Not reaching the server is everyone's business");
    // An administrator sees the count, as before, and at once on signing in.
    f.run(`capacityReading = { active_paid_operations: 2, max_concurrent: 5, retention_days: 7 };
      applyAccountMode({ email: "${ACCOUNT.email}", admin: true, verified: true })`);
    assert.deepEqual([line().shown, line().dots, line().label], [true, true, "2/5 running_label"]);
    // Signed out, the count is nobody's again.
    f.run('accountMode = false; accountAdmin = false; paintCapacityLabel()');
    assert.equal(line().shown, false);
  },
  async opening_the_account_panel_does_not_put_the_cursor_in_a_password_field() {
    const f = fixture({ access: { status: 200, body: { ok: true, account: ACCOUNT, accounts: ACCOUNTS } } });
    await settle();
    f.get("#byok-skip").onclick();
    await settle();
    await f.get("#account-manage").listeners.click();
    assert.equal(f.get("#account-settings").hidden, false);
    assert.equal(f.get("#account-settings-title").focused, 1, "The heading takes focus");
    for (const field of ["#settings-current-password", "#settings-new-password", "#settings-delete-password"]) {
      assert.equal(f.get(field).focused, undefined, field);
    }
  },
  async notice_switch() {
    // The Account panel's switch: saved on change, shown as the account has it.
    const f = fixture({ access: { status: 200, body: { ok: true, account: { ...ACCOUNT, notify_done: false }, accounts: ACCOUNTS } },
      replies: { "/api/auth/notify": {} } });
    await settle();
    f.get("#byok-skip").onclick();
    await settle();
    await f.get("#account-manage").listeners.click();
    assert.equal(f.get("#account-settings").hidden, false, "The badge opens the panel");
    assert.equal(f.get("#settings-notify-row").hidden, false, "With mail, the switch is offered");
    assert.equal(f.get("#settings-notify").checked, false, "...off, as the account has it");
    assert.equal(f.get("#settings-notify-hint").textContent, "account_notify_hint".replace("{email}", ACCOUNT.email));
    f.get("#settings-notify").checked = true;
    await f.get("#settings-notify").onchange();
    const posted = f.requests.find((r) => r.url === "/api/auth/notify");
    assert.deepEqual(JSON.parse(posted.options.body), { enabled: true }, "Saved as soon as it is changed");
    assert.equal(f.get("#settings-notify").checked, true);
    assert.equal(f.get("#settings-notify").disabled, false);
    f.get("#settings-close").onclick();
    await f.get("#account-manage").listeners.click();
    assert.equal(f.get("#settings-notify").checked, true, "Reopened, the panel shows what was saved");
  },
  async notice_switch_refused() {
    const f = fixture({ access: { status: 200, body: { ok: true, account: { ...ACCOUNT, notify_done: true }, accounts: ACCOUNTS } } });
    globalThis.fetch = ((inner) => (url, options) => url === "/api/auth/notify"
      ? Promise.resolve(new Response(JSON.stringify({ detail: "no mail" }), { status: 503,
          headers: { "Content-Type": "application/json", "X-Error-Code": "mail_unavailable" } }))
      : inner(url, options))(globalThis.fetch);
    await settle();
    f.get("#byok-skip").onclick();
    await settle();
    await f.get("#account-manage").listeners.click();
    assert.equal(f.get("#settings-notify").checked, true, "On, as the account has it");
    f.get("#settings-notify").checked = false;
    await f.get("#settings-notify").onchange();
    assert.equal(f.get("#settings-notify").checked, true, "Not taken by the server: put back, so the box never lies");
  },
  async notice_switch_absent_without_mail() {
    const f = fixture({ access: { status: 200, body: { ok: true, account: ACCOUNT, accounts: { ...ACCOUNTS, notices: false } } } });
    await settle();
    f.get("#byok-skip").onclick();
    await settle();
    await f.get("#account-manage").listeners.click();
    assert.equal(f.get("#account-settings").hidden, false);
    assert.equal(f.get("#settings-notify-row").hidden, true, "Without mail there is nothing to switch on");
  },
  async logout_without_accounts_reloads() {
    const f = fixture({ access: { status: 200, body: { ok: true } } });
    await settle();
    await f.get("#code-exit").listeners.click();
    await settle();
    assert.deepEqual(f.reloads, [true], "A code deployment has no landing; sign-out reloads in place as it always did");
    assert.deepEqual(f.navigations, []);
  },
};

const run = scenarios[scenario];
if (!run) throw new Error(`Unknown scenario ${scenario}`);
await run();
console.log(`PASS ${scenario}`);
// A reader's run view polls with a real fifteen-second timer in run.js; the
// assertions are done, so do not wait for a request this file never answers.
process.exit(0);
