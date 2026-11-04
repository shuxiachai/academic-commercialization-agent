/* Keyboard focus while the access gate is open.
 *
 * The gate is a fixed overlay after the workbench in the document, and its
 * scrim blurs the page behind it. Without this, Tab went from the gate's last
 * control to the sidebar and composer under that scrim: focus a keyboard user
 * could not see, on controls they cannot use until the gate closes.
 * e2e/keyboard_smoke.py walks the gate with Tab.
 *
 * `inert` takes the whole workbench out of the Tab order and away from
 * clicks while the gate is shown, and gives it back when the gate hides.
 * app.js shows and hides the gate on several paths (boot, logout, the key
 * form for an account), so this follows the gate's hidden attribute instead
 * of hooking each one. Loaded after app.js as its own module, as chrome.js is.
 */

const gate = document.querySelector("#gate");
const workbench = document.querySelector("#workbench");

function sync() {
  if (workbench) workbench.inert = Boolean(gate && !gate.hidden);
}

if (gate) {
  new MutationObserver(sync).observe(gate, { attributes: true, attributeFilter: ["hidden"] });
}
sync();
