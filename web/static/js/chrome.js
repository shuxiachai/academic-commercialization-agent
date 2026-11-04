/* Phone chrome: the menu button that opens the overlay sidebar, and the scrim
 * that closes it.
 *
 * Below 860px the sidebar slides over the page, and its only toggle
 * (#collapse-btn) sits inside it — off-screen with the rest of it — so on a
 * phone the run history, "new analysis" and the language switch could not be
 * reached at all. This module adds the missing way in and out. app.js still
 * owns data-sidebar-open; this only writes the same attribute and mirrors it
 * into the scrim and the button's ARIA state.
 *
 * Kept out of app.js on purpose: app.js's browser contracts strip and inject
 * its imports, and its strings live in the hash-locked i18n.js. The language
 * still comes from i18n.js; the two labels live here, as the BYOK field
 * strings do in byok_fields.js. Loaded after app.js as its own module.
 *
 * It also keeps keyboard focus where the user can see it (#237;
 * e2e/keyboard_smoke.py walks it with Tab). The closed sidebar is translated
 * off-screen, not hidden, so its controls were still Tab stops; it is inert
 * while closed. The sidebar comes before this button in the document, so after
 * opening, Tab used to run on through the page under it; opening now moves
 * focus into the sidebar, and the rest of #main except the scrim is inert
 * until it closes. Closing it from inside (Escape, its own toggle, a run in
 * the list) would leave focus in a now-inert sidebar, so it goes back to the
 * menu button; "New analysis" then moves it on to the topic. */

import { language } from "./i18n.js";

const STRINGS = {
  English: { open: "Open menu", close: "Close menu" },
  "Simplified Chinese": { open: "打开菜单", close: "关闭菜单" },
};

const $ = (sel) => document.querySelector(sel);
const workbench = $("#workbench");
const sidebar = $("#sidebar");
const main = $("#main");
const menu = $("#mobile-menu");
const scrim = $("#sidebar-scrim");
const NARROW = window.matchMedia("(max-width: 860px)");
const FOCUSABLE = "a[href], button:not([disabled]), select, input, textarea, summary";

const isOpen = () => workbench?.dataset.sidebarOpen === "true";
let wasOpen = false;

function sync() {
  const open = NARROW.matches && isOpen();
  const stranded = NARROW.matches && !open && sidebar?.contains(document.activeElement);
  if (sidebar) sidebar.inert = NARROW.matches && !open;
  for (const child of main?.children ?? []) {
    if (child !== scrim) child.inert = open;
  }
  if (scrim) scrim.hidden = !open;
  if (menu) {
    const labels = STRINGS[language()] ?? STRINGS.English;
    menu.setAttribute("aria-expanded", String(open));
    menu.setAttribute("aria-label", open ? labels.close : labels.open);
  }
  if (open && !wasOpen && !sidebar?.contains(document.activeElement)) {
    // The first control that is shown; the badges for other identities are hidden.
    [...(sidebar?.querySelectorAll(FOCUSABLE) ?? [])].find((el) => el.getClientRects().length)?.focus();
  }
  if (stranded) menu?.focus();
  wasOpen = open;
}

function setOpen(open) {
  if (!workbench) return;
  workbench.dataset.sidebarOpen = String(open);
  sync();
}

menu?.addEventListener("click", () => setOpen(!isOpen()));
scrim?.addEventListener("click", () => setOpen(false));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && NARROW.matches && isOpen()) setOpen(false);
});
// Choosing a run or starting a new one should show it, not leave the menu
// lying over it. The delete icon sits beside .runitem, not inside it, so a
// delete confirmation keeps the menu open. Capture phase: the menu closes
// before app.js's own handler runs, so the focus that handler gives (the
// topic, for "New analysis") lands on a page that is no longer inert.
$("#sidebar")?.addEventListener("click", (e) => {
  if (NARROW.matches && e.target.closest(".runitem, #new-run-btn")) setOpen(false);
}, true);

// The sidebar's own toggle also flips data-sidebar-open; follow it, a resize
// across the breakpoint, and a language change.
if (workbench) {
  new MutationObserver(sync).observe(workbench, { attributes: true, attributeFilter: ["data-sidebar-open"] });
}
NARROW.addEventListener?.("change", sync);
$("#ui-lang")?.addEventListener("change", sync);
sync();
