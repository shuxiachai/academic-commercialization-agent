/* Translate the main page's links to /samples.
 *
 * A separate module rather than a call inside app.js: app.js's browser
 * contracts load it with its imports stripped and its dependencies injected,
 * so a new import there would need every harness changed. Loaded after app.js,
 * it shares the same i18n.js instance, so by the time this change listener
 * runs app.js's listener has already switched the language. */

import { applySamples } from "./samples_i18n.js";

applySamples();
document.querySelector("#ui-lang")?.addEventListener("change", () => applySamples());
