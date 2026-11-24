/* Offline contract for privacy.js retention wording across /api/site states. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [dir, scenario] = process.argv.slice(2);
const { html } = JSON.parse(fs.readFileSync(path.join(dir, "input.json"), "utf8"));

class Element {
  constructor({ hidden = false, dataset = {}, textContent = "" } = {}) {
    this.hidden = hidden;
    this.dataset = { ...dataset };
    this.textContent = textContent;
    this.value = "";
    this.listeners = {};
  }
  addEventListener(name, callback) {
    (this.listeners[name] ??= []).push(callback);
  }
  fire(name) {
    for (const callback of this.listeners[name] ?? []) callback({});
  }
}

const langSelect = new Element();
const langBlocks = [...html.matchAll(/data-lang-block="([^"]+)"/g)].map(
  ([, b]) => new Element({ dataset: { langBlock: b } }),
);
const retentionNodes = [...html.matchAll(/<span data-retention="([^"]+)">([^<]*)<\/span>/g)].map(
  ([, lang, text]) => new Element({ dataset: { retention: lang }, textContent: text }),
);
const autoNodes = [...html.matchAll(/<span data-retention-auto([^>]*)>/g)].map(
  ([, attrs]) => new Element({ hidden: /\bhidden\b/.test(attrs) }),
);

const initialText = retentionNodes.map((n) => n.textContent);
assert.equal(retentionNodes.length, 4);
assert.equal(autoNodes.length, 2);

const stored = new Map();
globalThis.localStorage = {
  getItem: (k) => stored.get(k) ?? null,
  setItem: (k, v) => stored.set(k, String(v)),
};

const bySelectorAll = {
  "[data-lang-block]": langBlocks,
  "[data-legal=back]": [new Element(), new Element()],
  "[data-retention]": retentionNodes,
  "[data-retention-auto]": autoNodes,
  "[data-account-backup]": [],
  "[data-account-backup-days]": [],
  "[data-mail]": [],
  "[data-contact]": [],
};

globalThis.document = {
  title: "Privacy",
  documentElement: { lang: "en", dataset: {} },
  querySelector: (sel) => (sel === "#ui-lang" ? langSelect : null),
  querySelectorAll: (sel) => bySelectorAll[sel] ?? [],
};

let releaseFetch = null;
globalThis.fetch = async (url) => {
  assert.equal(url, "/api/site");
  if (scenario === "loading") {
    return new Promise((resolve) => {
      releaseFetch = resolve;
    });
  }
  if (scenario === "http_503") return new Response("unavailable", { status: 503 });
  if (scenario === "missing") return new Response("{}", { status: 200 });
  if (scenario === "malformed") return new Response(JSON.stringify({ retention_days: "30" }), { status: 200 });
  if (scenario === "days") return new Response(JSON.stringify({ retention_days: 30 }), { status: 200 });
  if (scenario === "null_forever") return new Response(JSON.stringify({ retention_days: null }), { status: 200 });
  throw new Error(`Unknown scenario: ${scenario}`);
};

const settle = async () => {
  for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 0));
};

await import(pathToFileURL(path.join(dir, "privacy.js")).href);
await settle();

const expectedByLang = {
  loading: { en: initialText[0], zh: initialText[2], autoHidden: true },
  http_503: { en: initialText[0], zh: initialText[2], autoHidden: true },
  missing: { en: initialText[0], zh: initialText[2], autoHidden: true },
  malformed: { en: initialText[0], zh: initialText[2], autoHidden: true },
  days: { en: "for 30 days", zh: " 30 天", autoHidden: false },
  null_forever: { en: "until you delete them", zh: "到你删除为止", autoHidden: true },
};

const checkBothLanguages = async () => {
  const expected = expectedByLang[scenario];
  for (const uiLang of ["English", "Simplified Chinese"]) {
    langSelect.value = uiLang;
    langSelect.fire("change");
    await settle();
    for (const node of retentionNodes) {
      assert.equal(node.textContent, expected[node.dataset.retention]);
    }
    for (const node of autoNodes) {
      assert.equal(node.hidden, expected.autoHidden);
    }
  }
};

await checkBothLanguages();
if (releaseFetch) releaseFetch(new Response("{}", { status: 503 }));
console.log(`PASS ${scenario}`);
