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
    language: "English", overall_score: 48.6, trl_score: 5 },
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
if (scenario === "signed_in" || scenario === "logout_goes_home") disk.set("session-token", "fixture-token");
if (scenario === "logout_without_accounts_reloads") disk.set("access-code", "fixture-code");

const api = await import("../../web/static/js/api.js");
const runView = await import("../../web/static/js/run.js");
const compareView = await import("../../web/static/js/compare.js");
// The real grading of a sample's score, so the list's words are the scorecard's.
const { sampleFacts } = await import("../../web/static/js/result.js");
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
function fixture({ pathname = "/", search = "", hash = "", access, replies = {}, hold = false }) {
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
    focus() {} remove() {} reset() {} select() {} setAttribute() {} removeAttribute() {} scrollIntoView() {}
    showModal() { this.open = true; } close() { this.open = false; }
  }
  const get = (selector) => {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  for (const id of hiddenAtStart) get(`#${id}`).hidden = true;
  const requests = [], navigations = [], reloads = [], sidebarRefreshes = [], replaced = [], summaries = [];
  const reply = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" } }));
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
      return given?.status ? reply(given.body, given.status) : reply(given);
    }
    if (url === "/api/access/check") {
      if (!hold) return reply(access.body, access.status);
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
    result: { sampleFacts, renderScoreSummary: (scores) => {
      summaries.push(scores);
      if (scores?.cannot_be_drawn) throw new TypeError("fixture: the scorecard could not be drawn");
      return typeof scores?.overall_score === "number" ? { className: "scorecard scorecard--summary", scores } : null;
    } },
    needsScopeWarning: () => false,
    i18n: { t: (key) => key, language: () => "English", apply: () => {}, setLanguage: () => {} },
    document: { querySelector: get, querySelectorAll: () => [], createElement: () => new Element(),
      addEventListener: () => {}, hidden: false },
    window: { matchMedia: () => ({ matches: false }), addEventListener: () => {} },
    localStorage: globalThis.localStorage, Event, URLSearchParams,
    history: { pushState: () => {}, replaceState: (_state, _unused, url) => replaced.push(url) },
    location: { pathname, search, hash, reload: () => reloads.push(true), replace: (url) => navigations.push(url) },
    setTimeout: () => 1, clearTimeout: () => {}, setInterval: () => 1, clearInterval: () => {},
    confirm: () => true,
  });
  vm.runInContext(source, context);
  return { get, requests, navigations, reloads, sidebarRefreshes, replaced, summaries, answer: () => answer(),
    deliver: () => deliver(),
    run: (text) => vm.runInContext(text, context) };
}

// Let the boot's promise chain and the replies above run to completion.
const settle = async () => { for (let i = 0; i < 25; i++) await new Promise((resolve) => setImmediate(resolve)); };
const shown = (f) => ({ landing: !f.get("#landing").hidden, workbench: !f.get("#workbench").hidden, gate: !f.get("#gate").hidden });
const refused = (accounts) => ({ status: 401, body: { detail: "Sign in.", ...(accounts ? { accounts } : {}) } });
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
    assert.deepEqual(links.map((a) => a.children.map((c) => [c.className, c.textContent, c.dataset.tone])), [
      [["landing__sample-facts", "48.6 / 100 · Early · TRL 5 · Report in English", "warning"]],
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
  async early_landing_gives_way_when_the_check_cannot_be_reached() {
    // The boot stops on this error, as it always has; what is asserted is
    // what it leaves on screen.
    const stopped = [];
    process.on("unhandledRejection", (error) => stopped.push(error.message));
    const f = fixture({ access: refused(ACCOUNTS), replies: { "/api/access/check": "unreachable" } });
    await settle();
    assert.equal(shown(f).landing, false, "The page that promised a sign-in does not stay when nothing answered");
    assert.equal(shown(f).workbench, true, "...and the visitor is where they were before this change");
    assert.deepEqual(stopped, ["Cannot reach the server. Is it still running?"]);
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
