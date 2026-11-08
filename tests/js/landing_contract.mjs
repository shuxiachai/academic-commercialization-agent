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
globalThis.sessionStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };

const SAMPLES = [
  { slug: "hyperloop", title: "Hyperloop", topic: "hyperloop", committed: "2026-10-21", commit: "a8cc424" },
  { slug: "solid-state-batteries-ev-zh", title: "电动汽车用固态电池", topic: "电动汽车用固态电池",
    committed: "2026-10-21", commit: "a8cc424" },
  { slug: "../etc/passwd", title: "Not a sample", topic: "", committed: "", commit: "" },
];
const ACCOUNTS = { enabled: true, signup_open: true, signup: "open", access_codes: false, password_reset: true, notices: true,
  key_check: false, contact: null, plan_preview: false, daily_quota: false };
const ACCOUNT = { email: "visitor@example.test", admin: false, verified: true };

// One scenario per process: api.js reads its credential slots once.
const scenario = process.argv[2];
if (scenario === "signed_in" || scenario === "logout_goes_home") disk.set("session-token", "fixture-token");
if (scenario === "logout_without_accounts_reloads") disk.set("access-code", "fixture-code");

const api = await import("../../web/static/js/api.js");
const runView = await import("../../web/static/js/run.js");
const compareView = await import("../../web/static/js/compare.js");
const source = fs.readFileSync(new URL("../../web/static/js/app.js", import.meta.url), "utf8")
  .replace(/^import .*;\r?\n/gm, "");
// The elements the document itself starts hidden (#gate, #landing, the card's
// forms...): app.js shows them and relies on the markup for the rest.
const markup = fs.readFileSync(new URL("../../web/index.html", import.meta.url), "utf8");
const hiddenAtStart = [...markup.matchAll(/<[^>]*\bid="([\w-]+)"[^>]*\shidden[\s>]/g)].map((match) => match[1]);
assert.ok(hiddenAtStart.includes("gate") && hiddenAtStart.includes("landing"), "the document starts with both hidden");
// The scorecard picture's address travels in data-src, not src (see index.html).
const previewSource = markup.match(/<img id="landing-preview" data-src="([^"]+)"/)[1];

// `replies` answers the seams a scenario is about beyond the boot's access check.
function fixture({ pathname = "/", search = "", access, replies = {} }) {
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
  get("#landing-preview").dataset.src = previewSource;
  const requests = [], navigations = [], reloads = [];
  const reply = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" } }));
  globalThis.fetch = (url, options = {}) => {
    requests.push({ url, options });
    if (url in replies) return reply(replies[url]);
    if (url === "/api/access/check") return reply(access.body, access.status);
    if (url === "/api/samples") return reply(SAMPLES);
    if (url === "/api/auth/login" || url === "/api/auth/register") return reply({ token: "fixture-token", ...ACCOUNT });
    if (url === "/api/auth/logout") return reply({});
    if (url === "/health") return reply({ retention_days: 30, active_runs: 0, max_concurrent: 5 });
    // History, capacity and quota are other seams; here they never answer.
    return new Promise(() => {});
  };
  const context = vm.createContext({
    createPaidReceipts: () => createPaidReceipts(() => ({ getItem: () => null, setItem: () => {}, removeItem: () => {} })),
    api, runView: { ...runView }, compareView,
    sidebar: { refresh: () => Promise.resolve([]), resetView: () => {} }, result: {}, needsScopeWarning: () => false,
    i18n: { t: (key) => key, language: () => "English", apply: () => {}, setLanguage: () => {} },
    document: { querySelector: get, querySelectorAll: () => [], createElement: () => new Element(),
      addEventListener: () => {}, hidden: false },
    window: { matchMedia: () => ({ matches: false }), addEventListener: () => {} },
    localStorage: globalThis.localStorage, Event, URLSearchParams,
    history: { pushState: () => {}, replaceState: () => {} },
    location: { pathname, search, reload: () => reloads.push(true), replace: (url) => navigations.push(url) },
    setTimeout: () => 1, clearTimeout: () => {}, setInterval: () => 1, clearInterval: () => {},
    confirm: () => true,
  });
  vm.runInContext(source, context);
  return { get, requests, navigations, reloads, run: (text) => vm.runInContext(text, context) };
}

// Let the boot's promise chain and the replies above run to completion.
const settle = async () => { for (let i = 0; i < 25; i++) await new Promise((resolve) => setImmediate(resolve)); };
const shown = (f) => ({ landing: !f.get("#landing").hidden, workbench: !f.get("#workbench").hidden, gate: !f.get("#gate").hidden });
const refused = (accounts) => ({ status: 401, body: { detail: "Sign in.", ...(accounts ? { accounts } : {}) } });
const DEEP_LINK = "/run/20260926T121212Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

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
    assert.equal(f.get("#landing-retention").textContent, "byok_retention",
      "The retention period is the deployment's own, read from /health, as the key form reads it");
    assert.equal(f.get("#landing-preview").src, "/static/brand/report-preview.png", "The scorecard picture is fetched once the landing shows");

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
  },
  async anonymous_root_signup_closed() {
    const f = fixture({ access: refused({ ...ACCOUNTS, signup_open: false, signup: "closed" }) });
    await settle();
    assert.deepEqual(shown(f), { landing: true, workbench: false, gate: false });
    assert.equal(f.get("#landing-create").hidden, true, "No sign-up means no button that would only fail");
    f.get("#landing-sign-in-top").onclick();
    await settle();
    assert.equal(shown(f).gate, true, "The header's sign-in opens the card too");
    assert.equal(f.get("#account-title").textContent, "account_title");
  },
  async anonymous_deep_link() {
    const f = fixture({ pathname: DEEP_LINK, access: refused(ACCOUNTS) });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: true },
      "A deep link asks for the sign-in directly; whoever follows it came for the run, not the pitch");
    assert.ok(!f.requests.some((r) => r.url === "/api/samples"), "No landing, no sample request");
    assert.equal(f.get("#landing-preview").src, undefined, "...and no picture either: the hidden image is never given a src");
  },
  async anonymous_codes_only() {
    const f = fixture({ access: refused(null) });
    await settle();
    assert.deepEqual(shown(f), { landing: false, workbench: true, gate: true },
      "A deployment without accounts is invite-only; its visitors meet the code card as before");
    assert.equal(f.get("#gate-form").hidden, false);
    assert.ok(!f.requests.some((r) => r.url === "/api/samples"));
  },
  async signed_in() {
    const f = fixture({ access: { status: 200, body: { ok: true, account: ACCOUNT, accounts: ACCOUNTS } } });
    await settle();
    const state = shown(f);
    assert.equal(state.landing, false, "A stored session skips the landing");
    assert.equal(state.workbench, true);
    assert.equal(state.gate, true, "...and an account without keys is asked for them, as before");
    assert.equal(f.get("#byok-form").hidden, false);
    assert.ok(!f.requests.some((r) => r.url === "/api/samples"));
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
    assert.ok(!f.requests.some((r) => r.url === "/api/samples"));
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
