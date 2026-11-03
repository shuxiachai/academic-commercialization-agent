/* Decision Context on the composer: quick picks and a live line saying
 * whether the report may give a GO/NO_GO.
 *
 * Only the four starred fields decide that (run_spec.DecisionContext's
 * assessment_mode). So they stay in view, and the other five fold into "More
 * details". A pick fills its field with an editable starting value; nothing is
 * filled unless the visitor picks it.
 *
 * Kept out of app.js, whose browser contracts strip imports, as starters.js
 * is. Loaded after app.js, so a language change has already been applied when
 * this module's listener rewrites the line. */

import { t } from "./i18n.js";

export const CORE_FIELDS = ["asset_description", "target_application", "decision_owner", "decision_type"];

const filled = (value) => String(value ?? "").trim() !== "";

/** The line for the current field values, mirroring DecisionContext's modes. */
export function gateLine(values) {
  const answered = CORE_FIELDS.filter((name) => filled(values[name])).length;
  if (answered === CORE_FIELDS.length) return t("decision_status_ready");
  if (answered === 0 && !Object.values(values).some(filled)) return t("decision_status_none");
  return t("decision_status_partial").replace("{n}", String(answered));
}

function wire() {
  const line = document.querySelector("#decision-context-status");
  const inputs = [...document.querySelectorAll("[data-context-field]")];
  const refresh = () => {
    if (!line) return;
    line.textContent = gateLine(Object.fromEntries(inputs.map((input) => [input.dataset.contextField, input.value])));
  };
  for (const input of inputs) input.addEventListener("input", refresh);
  for (const pick of document.querySelectorAll("[data-fills]")) {
    pick.addEventListener("click", () => {
      const field = document.getElementById(pick.dataset.fills);
      if (!field) return;
      field.value = pick.textContent.trim();
      field.dispatchEvent(new Event("input", { bubbles: true }));
      field.focus();
    });
  }
  document.querySelector("#ui-lang")?.addEventListener("change", refresh);
  refresh();
}

if (typeof document !== "undefined") wire();
