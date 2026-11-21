/* The page for an address that is no page (web/not_found.html).
 *
 * Its text is in the markup, in both languages, so it reads without this
 * script. What the script adds: showing only the reader's language, chosen
 * by the one rule every page shares (i18n.js), and the language select. It
 * asks the server for nothing. */

import * as i18n from "./i18n.js";

const TITLES = { en: "Page not found", zh: "找不到这个页面" };

const lang = () => (i18n.language() === "Simplified Chinese" ? "zh" : "en");

function paint() {
  const current = lang();
  document.title = i18n.pageTitle(TITLES[current]);
  // The header's name and the select's label, from the strings every page
  // shares; this also sets the document's language.
  i18n.apply();
  for (const block of document.querySelectorAll("[data-lang-block]")) block.hidden = block.dataset.langBlock !== current;
}

const select = document.querySelector("#ui-lang");
select.value = i18n.language();
select.addEventListener("change", () => { i18n.setLanguage(select.value); paint(); });
paint();
