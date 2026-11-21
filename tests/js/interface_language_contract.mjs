// Which interface language a page opens in, before and after a reader chooses.
//
// Loads the shipped i18n.js into a fresh context for each case, with the
// browser's preferred languages and the page's storage as the case states
// them, and reports what the module decided and what it wrote. The rule is
// i18n.js's alone: the landing, the workbench, the sample reader, the privacy
// page and the operator's console all take their language from it.
//
// Input (argv[2], JSON):
//   { navigator?: { languages?: [...], language?: "...", throws?: true },
//     window?: false,                // no window at all (a script host, not a page)
//     hostNavigator?: { languages }, // a navigator on the global object only
//     stored?: "...", storage?: "throws" | "denies-writes",
//     then?: "English" }             // a choice made after the page has loaded
import fs from "node:fs";
import vm from "node:vm";

const input = JSON.parse(process.argv[2]);
const source = fs.readFileSync(new URL("../../web/static/js/i18n.js", import.meta.url), "utf8")
  .replace(/^export /gm, "");

function load(disk) {
  const writes = [];
  const localStorage = {
    getItem(key) {
      if (input.storage === "throws") throw new Error("SecurityError: storage is disabled");
      return disk.has(key) ? disk.get(key) : null;
    },
    setItem(key, value) {
      if (input.storage === "throws" || input.storage === "denies-writes") throw new Error("QuotaExceededError");
      writes.push([key, String(value)]);
      disk.set(key, String(value));
    },
    removeItem(key) { disk.delete(key); },
  };
  const html = { lang: "en", dataset: {} };
  const document = { documentElement: html, querySelectorAll: () => [] };
  const globals = { localStorage, document };
  if (input.window !== false) {
    const navigator = input.navigator?.throws
      ? { get languages() { throw new Error("blocked"); }, get language() { throw new Error("blocked"); } }
      : input.navigator;
    globals.window = navigator === undefined ? {} : { navigator };
  }
  if (input.hostNavigator) globals.navigator = input.hostNavigator;
  const context = vm.createContext(globals);
  vm.runInContext(source, context, { filename: "i18n.js" });
  return { context, html, writes };
}

const disk = new Map(input.stored === undefined ? [] : [["ui-language", input.stored]]);
const first = load(disk);
first.context.apply();
const report = {
  language: vm.runInContext("language()", first.context),
  locale: vm.runInContext("locale()", first.context),
  lang: first.html.lang,
  title: vm.runInContext('t("landing_title")', first.context),
  writes: first.writes,
};
if (input.then) {
  vm.runInContext(`setLanguage(${JSON.stringify(input.then)})`, first.context);
  report.after_choice = { language: vm.runInContext("language()", first.context), lang: first.html.lang,
    writes: first.writes };
  // The same reader opens the page again, with the browser unchanged.
  const again = load(disk);
  report.next_visit = vm.runInContext("language()", again.context);
}
process.stdout.write(JSON.stringify(report));
