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
 * strings do in byok_fields.js. Loaded after app.js as its own module. */

import { language } from "./i18n.js";

const STRINGS = {
  English: { open: "Open menu", close: "Close menu" },
  "Simplified Chinese": { open: "打开菜单", close: "关闭菜单" },
};

const $ = (sel) => document.querySelector(sel);
const workbench = $("#workbench");
const menu = $("#mobile-menu");
const scrim = $("#sidebar-scrim");
const NARROW = window.matchMedia("(max-width: 860px)");

const isOpen = () => workbench?.dataset.sidebarOpen === "true";

function sync() {
  const open = NARROW.matches && isOpen();
  if (scrim) scrim.hidden = !open;
  if (menu) {
    const labels = STRINGS[language()] ?? STRINGS.English;
    menu.setAttribute("aria-expanded", String(open));
    menu.setAttribute("aria-label", open ? labels.close : labels.open);
  }
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
// delete confirmation keeps the menu open.
$("#sidebar")?.addEventListener("click", (e) => {
  if (NARROW.matches && e.target.closest(".runitem, #new-run-btn")) setOpen(false);
});

// The sidebar's own toggle also flips data-sidebar-open; follow it, a resize
// across the breakpoint, and a language change.
if (workbench) {
  new MutationObserver(sync).observe(workbench, { attributes: true, attributeFilter: ["data-sidebar-open"] });
}
NARROW.addEventListener?.("change", sync);
$("#ui-lang")?.addEventListener("change", sync);
sync();
