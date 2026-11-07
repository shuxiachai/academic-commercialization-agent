/* Theme toggle: lets the reader choose light or dark instead of only following
 * the operating system (#234).
 *
 * tokens.css keeps both palettes and applies the dark one when the system is
 * dark, unless <html data-theme="light"> is set, or whenever
 * <html data-theme="dark"> is set. This module only writes that attribute and
 * remembers the choice in localStorage. Until the reader presses the toggle
 * nothing is stored and nothing is set, so the page keeps following the system,
 * including when the system changes while it is open.
 *
 * Kept out of app.js and i18n.js on purpose: app.js's browser contracts strip
 * and inject its imports, and its strings live in the hash-locked i18n.js. The
 * language still comes from i18n.js; the two labels live here, as the phone
 * menu's do in chrome.js. Loaded after app.js as its own module.
 *
 * localStorage can throw or be empty (private windows, blocked site data), so
 * every access is wrapped and the toggle still works for the current page
 * without it. */

import { language } from "./i18n.js";

const KEY = "aca-theme";
const STRINGS = {
  English: { toDark: "Switch to dark theme", toLight: "Switch to light theme" },
  "Simplified Chinese": { toDark: "切换到深色主题", toLight: "切换到浅色主题" },
};

const root = document.documentElement;
const button = document.querySelector("#theme-toggle");
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

function stored() {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function remember(theme) {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* The choice then lasts only for this page. */
  }
}

/** The theme on screen: the reader's choice, else the system's. */
function effective() {
  return root.dataset.theme || (systemDark.matches ? "dark" : "light");
}

function paint() {
  if (!button) return;
  const now = effective();
  const labels = STRINGS[language()] ?? STRINGS.English;
  const label = now === "dark" ? labels.toLight : labels.toDark;
  button.dataset.themeNow = now;
  button.setAttribute("aria-label", label);
  button.title = label;
}

const saved = stored();
if (saved) root.dataset.theme = saved;

button?.addEventListener("click", () => {
  const next = effective() === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  remember(next);
  paint();
});
// The label follows a language switch, and the icon follows the system while
// the reader has not chosen.
document.querySelector("#ui-lang")?.addEventListener("change", paint);
systemDark.addEventListener?.("change", paint);
paint();
