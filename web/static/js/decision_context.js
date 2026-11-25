/* Decision Context on the composer: quick picks and a live line saying
 * whether the report may give a GO/NO_GO.
 *
 * Only the four starred fields decide that (run_spec.DecisionContext's
 * assessment_mode). So they stay in view, and the other five fold into "More
 * details". A pick fills its field with an editable starting value; nothing is
 * filled unless the visitor picks it. While the field holds what a pick put
 * there, the pick is marked as chosen (aria-pressed): until 2026-11-18 a
 * pressed pick looked like the ones beside it as soon as the pointer left.
 *
 * The multi-line fields are as tall as their text. They were two or three
 * rows with the rest scrolled out of sight, so a four-line description showed
 * its last lines and no sign of the first.
 *
 * Kept out of app.js, whose browser contracts strip imports, as starters.js
 * is. Loaded after app.js, so a language change has already been applied when
 * this module's listener rewrites the line. */

import { locale, t } from "./i18n.js";

export const CORE_FIELDS = ["asset_description", "target_application", "decision_owner", "decision_type"];

const filled = (value) => String(value ?? "").trim() !== "";

/** The line for the current field values, mirroring DecisionContext's modes. */
export function gateLine(values, retryStatus) {
  const missing = CORE_FIELDS.filter((name) => !filled(values[name]));
  if (!missing.length) return t("decision_status_ready");
  const hasContext = Object.values(values).some(filled);
  const mode = hasContext
    ? t("decision_status_partial").replace("{n}", String(CORE_FIELDS.length - missing.length))
    : t("decision_status_none");
  if (!retryStatus || (retryStatus === "empty" && !hasContext)) return mode;

  const labels = { asset_description: "decision_asset", target_application: "decision_application",
    decision_owner: "decision_owner", decision_type: "decision_type" };
  const fields = new Intl.ListFormat(locale()).format(missing.map((name) => t(labels[name]).replace(/\s*\*$/, "")));
  const hint = t(retryStatus === "unavailable" ? "decision_retry_unavailable" : "decision_retry_missing");
  return mode + " " + hint.replace("{fields}", fields);
}

/** Whether a pick is the answer in its field: the same words, whatever surrounds them. */
export function pickChosen(pickText, fieldValue) {
  return filled(fieldValue) && String(fieldValue).trim() === String(pickText ?? "").trim();
}

/** Make a multi-line field as tall as its text and say the height given, or
 * null when nothing could be measured. A field inside a closed fold measures
 * nothing, and is left to the rows its markup gives it until the fold opens.
 * The text's height excludes the field's borders and the field's own height
 * includes them (box-sizing: border-box), so they are added back. */
export function fitHeight(field) {
  if (!field?.style) return null;
  field.style.height = "auto";
  const text = field.scrollHeight;
  if (!text) return null;
  const borders = Math.max(0, (field.offsetHeight ?? 0) - (field.clientHeight ?? 0));
  field.style.height = `${text + borders}px`;
  return text + borders;
}

function wire() {
  const line = document.querySelector("#decision-context-status");
  const inputs = [...document.querySelectorAll("[data-context-field]")];
  const picks = [...document.querySelectorAll("[data-fills]")];
  const growing = inputs.filter((input) => input.tagName === "TEXTAREA");
  const refresh = () => {
    if (!line) return;
    const values = Object.fromEntries(inputs.map((input) => [input.dataset.contextField, input.value]));
    line.textContent = gateLine(values, line.dataset.retryStatus);
  };
  // A pick is chosen while its field holds its words: the ones it shows now,
  // or the ones it put there before the interface language changed its name.
  const mark = () => {
    for (const pick of picks) {
      const value = document.getElementById(pick.dataset.fills)?.value;
      const chosen = pickChosen(pick.textContent, value) || (filled(pick.dataset.filled) && pickChosen(pick.dataset.filled, value));
      pick.setAttribute("aria-pressed", String(chosen));
    }
  };
  const fitAll = () => { for (const field of growing) fitHeight(field); };
  for (const input of inputs) {
    input.addEventListener("input", refresh);
    input.addEventListener("input", mark);
  }
  for (const field of growing) field.addEventListener("input", () => fitHeight(field));
  for (const pick of picks) {
    pick.addEventListener("click", () => {
      const field = document.getElementById(pick.dataset.fills);
      if (!field) return;
      field.value = pick.textContent.trim();
      pick.dataset.filled = field.value;
      field.dispatchEvent(new Event("input", { bubbles: true }));
      field.focus();
    });
  }
  // Closed, the folds give their fields no size to measure; a narrower window wraps the text anew.
  for (const fold of document.querySelectorAll("#decision-context, .decision-context__more")) {
    fold.addEventListener("toggle", fitAll);
  }
  if (typeof window !== "undefined") window.addEventListener?.("resize", fitAll);
  document.querySelector("#ui-lang")?.addEventListener("change", () => { refresh(); mark(); });
  refresh();
  mark();
  fitAll();
}

if (typeof document !== "undefined") wire();
