// The admin console's boot: which sentence a visitor is shown when the
// console does not open.
//
// Runs the shipped admin.js against a fake document, with the real api.js
// and i18n.js and fetch intercepted. The seam under test is the denial the
// boot shows for each way its two requests can fail, in both interface
// languages, and that an error from the page itself is thrown rather than
// blamed on the server. No socket is opened and nothing paid is reachable:
// every request here is answered by this file.
import assert from "node:assert/strict";
import fs from "node:fs";

const [scenario, language] = process.argv.slice(2);
assert.ok(scenario, "a scenario is required");
const LANG = language === "Simplified Chinese" ? "Simplified Chinese" : "English";

// The interface language is chosen before i18n.js is loaded, as the page
// reads it from storage at import.
const stored = new Map([["ui-language", LANG]]);
globalThis.localStorage = {
  getItem: (key) => stored.get(key) ?? null,
  setItem: (key, value) => stored.set(key, String(value)),
  removeItem: (key) => stored.delete(key),
};
const tab = new Map();
globalThis.sessionStorage = {
  getItem: (key) => tab.get(key) ?? null,
  setItem: (key, value) => tab.set(key, String(value)),
  removeItem: (key) => tab.delete(key),
};
// A toast would otherwise keep the process alive for its 4.6 seconds.
globalThis.setTimeout = () => 0;
globalThis.clearTimeout = () => {};

class Element {
  constructor() {
    Object.assign(this, { value: "", disabled: false, hidden: false, dataset: {},
      style: {}, children: [], listeners: {}, textContent: "", className: "", title: "",
      options: [], attributes: {} });
    this.classList = { add: () => {}, remove: () => {}, toggle: () => {} };
  }
  addEventListener(event, handler) { (this.listeners[event] ??= []).push(handler); }
  set innerHTML(_value) { this.children = []; }
  append(...nodes) { this.children.push(...nodes); }
  querySelectorAll() { return []; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() {} select() {} remove() {}
}
const elements = new Map();
// The elements the document itself starts hidden (#console-denied, the
// body…): admin.js shows them and relies on the markup for the rest.
const markup = fs.readFileSync(new URL("../../web/admin.html", import.meta.url), "utf8");
const hiddenAtStart = [...markup.matchAll(/<[^>]*\bid="([\w-]+)"[^>]*\shidden[\s>]/g)].map((match) => match[1]);
assert.ok(hiddenAtStart.includes("console-denied") && hiddenAtStart.includes("console-body"),
  "the document starts with the denial and the body hidden");
const get = (selector) => {
  assert.ok(selector.startsWith("#"), selector);
  const id = selector.slice(1);
  if (!elements.has(id)) {
    const el = new Element();
    el.hidden = hiddenAtStart.includes(id);
    elements.set(id, el);
  }
  return elements.get(id);
};
globalThis.document = {
  title: "",
  documentElement: { lang: "", dataset: {} },
  querySelector: get,
  querySelectorAll: () => [],
  createElement: () => new Element(),
  body: new Element(),
  activeElement: null,
};

const ADMIN = { email: "ops@example.com", admin: true, verified: true };
const ALICE = { email: "alice@example.com", admin: false, verified: true };
const ACCOUNTS = { accounts: [
  { id: "admin-id", email: ADMIN.email, created_at: 1764000000, last_seen_at: 1764000000,
    sessions: 3, runs: 5, disabled: false, verified: true, admin: true, trial_used: 0 },
  { id: "alice-id", email: ALICE.email, created_at: 1764000000, last_seen_at: 1764000000,
    sessions: 1, runs: 0, disabled: false, verified: true, admin: false, trial_used: 0 },
] };
const reply = (body, status = 200, headers = {}) => Promise.resolve(new Response(JSON.stringify(body),
  { status, headers: { "Content-Type": "application/json", ...headers } }));
// The limiter's answer once a caller's budget is spent, as api/main.py writes it (_rate_limit).
const TOLD_TO_WAIT = { body: { detail: "Too many requests. Slow down and retry shortly." }, status: 429,
  headers: { "Retry-After": "10", "X-Error-Code": "rate_limited" } };

// What each scenario's two boot requests answer. The load() after a
// successful boot re-asks for the accounts and the service state; those
// fail here, which the console already tolerates with "could not be read".
const ME = {
  me_401: () => reply({ detail: "Sign in." }, 401),
  me_not_admin: () => reply(ALICE),
  me_429: () => reply(TOLD_TO_WAIT.body, TOLD_TO_WAIT.status, TOLD_TO_WAIT.headers),
  me_unreachable: () => Promise.reject(new TypeError("Failed to fetch")),
  me_500: () => reply({ detail: "Something broke." }, 500),
  accounts_429: () => reply(ADMIN),
  accounts_500: () => reply(ADMIN),
  admin_opens: () => reply(ADMIN),
  page_error_rethrown: () => reply(ADMIN),
};
const ACCOUNTS_REPLY = {
  accounts_429: () => reply(TOLD_TO_WAIT.body, TOLD_TO_WAIT.status, TOLD_TO_WAIT.headers),
  accounts_500: () => reply({ detail: "Something broke." }, 500),
  // No accounts key: the page's own code throws reading it, which is the
  // error the boot must rethrow rather than blame on the server.
  page_error_rethrown: () => reply({}),
  admin_opens: () => reply(ACCOUNTS),
};
globalThis.fetch = async (url) => {
  if (url === "/api/auth/me") return ME[scenario]();
  if (url === "/api/admin/accounts") return (ACCOUNTS_REPLY[scenario] ?? (() => reply(ACCOUNTS)))();
  if (url.startsWith("/api/admin/funnel")) return reply({ detail: "Gone." }, 500);
  if (url === "/api/admin/backups" || url === "/health") return reply({ detail: "Gone." }, 500);
  throw new Error(`unexpected request: ${url}`);
};

// A rethrown boot error surfaces here, not as a denial on the page.
const rejections = [];
process.on("unhandledRejection", (err) => rejections.push(err));

await import(new URL("../../web/static/js/admin.js", import.meta.url).href);

// Let the boot's promise chain and the replies above run to completion.
const settle = async () => { for (let i = 0; i < 25; i++) await new Promise((resolve) => setImmediate(resolve)); };
await settle();

const denied = () => ({ shown: !get("#console-denied").hidden, text: get("#console-denied").textContent });
const who = () => get("#console-who").textContent;
const bodyShown = () => !get("#console-body").hidden;

// The sentences, as the shipped strings state them in each language: the
// console's own for the two denials, the main page's for the three failures.
const EXPECTED = {
  English: {
    denied_signin: "Sign in to the app with an admin account first, then come back here.",
    denied_admin: "This account is not an admin. The console is for the addresses named in ACCOUNTS_ADMIN_EMAILS.",
    boot_failure_rate_limited: "The server has received too many requests from you or your network in the last minute, and asked this page to wait. Try again in a few seconds.",
    msg_network: "Cannot reach the server. Check your connection and try again.",
    boot_failure_server: "The server could not answer just now. Try again in a moment.",
    who: (email) => `Signed in as ${email}. This page is for admin accounts.`,
  },
  "Simplified Chinese": {
    denied_signin: "请先在应用里用管理员账号登录，再回到这里。",
    denied_admin: "这个账号不是管理员。管理后台只对 ACCOUNTS_ADMIN_EMAILS 里列出的邮箱开放。",
    boot_failure_rate_limited: "过去一分钟里，服务器收到了太多来自你或你所在网络的请求，让这个页面稍等。过几秒再试即可。",
    msg_network: "连接不上服务器，请检查网络后重试。",
    boot_failure_server: "服务器暂时没有答复，请稍后再试。",
    who: (email) => `已登录：${email}。本页面仅供管理员账号使用。`,
  },
};
const text = EXPECTED[LANG];

const scenarios = {
  me_401() {
    assert.deepEqual(denied(), { shown: true, text: text.denied_signin },
      "A 401 keeps 'Sign in…'");
    assert.equal(bodyShown(), false);
    assert.equal(who(), "", "Without an answer about the visitor the loading line is gone");
  },
  me_not_admin() {
    assert.deepEqual(denied(), { shown: true, text: text.denied_admin },
      "A signed-in account that is not an admin keeps denied_admin");
    assert.equal(bodyShown(), false);
    assert.equal(who(), text.who(ALICE.email), "The denial names who was refused");
    assert.equal(rejections.length, 0, "Not an admin is a denial, not a thrown error");
  },
  me_429() {
    assert.deepEqual(denied(), { shown: true, text: text.boot_failure_rate_limited },
      "A 429 says the server asked the page to wait");
    assert.equal(bodyShown(), false);
    assert.equal(who(), "");
  },
  me_unreachable() {
    assert.deepEqual(denied(), { shown: true, text: text.msg_network },
      "An unreachable server says it cannot be reached");
    assert.equal(bodyShown(), false);
    assert.equal(who(), "");
  },
  me_500() {
    assert.deepEqual(denied(), { shown: true, text: text.boot_failure_server },
      "Any other status says the server could not answer just now");
    assert.equal(bodyShown(), false);
    assert.equal(who(), "");
  },
  accounts_429() {
    assert.deepEqual(denied(), { shown: true, text: text.boot_failure_rate_limited },
      "The same choice applies when the account list fails after sign-in");
    assert.equal(bodyShown(), false);
    assert.equal(who(), text.who(ADMIN.email), "The visitor is known, so the line stays");
  },
  accounts_500() {
    assert.deepEqual(denied(), { shown: true, text: text.boot_failure_server });
    assert.equal(bodyShown(), false);
    assert.equal(who(), text.who(ADMIN.email));
  },
  admin_opens() {
    assert.deepEqual(denied(), { shown: false, text: "" }, "Nothing changes for an admin whose console opens");
    assert.equal(bodyShown(), true);
    assert.equal(who(), text.who(ADMIN.email));
    assert.equal(get("#accounts-rows").children.length, 2, "The account list is painted");
    assert.equal(rejections.length, 0);
  },
  page_error_rethrown() {
    assert.deepEqual(denied(), { shown: false, text: "" },
      "An error from the page itself is not blamed on the server");
    assert.equal(bodyShown(), false);
    assert.equal(rejections.length, 1, "…it is thrown instead");
    assert.ok(rejections[0] instanceof TypeError, "…the page's own error, unrenamed");
  },
};

assert.ok(scenarios[scenario], `unknown scenario: ${scenario}`);
scenarios[scenario]();
console.log(`PASS ${scenario} ${LANG}`);
