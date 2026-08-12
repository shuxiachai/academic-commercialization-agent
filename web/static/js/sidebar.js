/* Sidebar run list. */

import * as api from "./api.js";
import { t } from "./i18n.js";

/* Runs are grouped by recency rather than shown as a flat list: with a few
 * dozen entries, "which of these did I run this morning" is the question
 * being asked, and a wall of timestamps does not answer it. */
function groupOf(startedAt) {
  const started = new Date(startedAt);
  if (Number.isNaN(started.getTime())) return "Earlier";

  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  if (started >= startOfToday) return "Today";

  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);
  if (started >= startOfYesterday) return "Yesterday";

  return "Earlier";
}

const GROUP_ORDER = ["Today", "Yesterday", "Earlier"];

// A run still in progress has no delete affordance in the list — DELETE on
// a live run stops it rather than removing it (see api/main.py delete_run),
// and surfacing that as a trash icon here would read as "delete" while
// actually just cancelling, leaving the item sitting right where it was.
// Stopping a run has its own explicit Cancel button in the run pane; once a
// run reaches one of these states, deleting it here means what it says.
const DELETABLE_STATES = new Set(["completed", "failed", "cancelled", "timeout"]);

const TRASH_ICON = `
  <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M3 4.5h10M6.5 4.5V3a1 1 0 011-1h1a1 1 0 011 1v1.5M4.5 4.5l.6 8.4a1 1 0 001 .9h3.8a1 1 0 001-.9l.6-8.4"
          stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;

export function render(container, runs, { activeId, onSelect, onDelete }) {
  container.innerHTML = "";

  if (!runs.length) {
    const empty = document.createElement("div");
    empty.className = "runlist__empty";
    empty.textContent = t("no_runs");
    container.append(empty);
    return;
  }

  const groups = new Map(GROUP_ORDER.map((name) => [name, []]));
  for (const run of runs) groups.get(groupOf(run.started_at)).push(run);

  for (const name of GROUP_ORDER) {
    const entries = groups.get(name);
    if (!entries.length) continue;

    const heading = document.createElement("div");
    heading.className = "runlist__group";
    heading.textContent = t(`group_${name.toLowerCase()}`);
    container.append(heading);

    for (const run of entries) {
      const row = document.createElement("div");
      row.className = "runitem-row";

      const item = document.createElement("button");
      item.type = "button";
      item.className = "runitem";
      item.dataset.runId = run.run_id;
      if (run.run_id === activeId) item.setAttribute("aria-current", "true");

      const dot = document.createElement("span");
      dot.className = "runitem__state";
      dot.dataset.state = run.state;

      const label = document.createElement("span");
      label.className = "runitem__label";
      label.textContent = run.topic || run.run_id;
      // The rail truncates aggressively, so the full topic lives in the title.
      item.title = run.topic || run.run_id;

      item.append(dot, label);

      // Only ever present for an admin request (api/access.py owner_label) —
      // an unlabelled merge of every code's history answers "what ran", not
      // "who ran it", which is the entire reason to hold that code rather
      // than just leaving the gate unfiltered for everyone.
      if (run.owner_label) {
        const owner = document.createElement("span");
        owner.className = "runitem__owner";
        owner.textContent = run.owner_label;
        item.title = `${run.owner_label} · ${item.title}`;
        item.append(owner);
      }
      item.addEventListener("click", () => onSelect(run.run_id));
      row.append(item);

      // Buttons cannot nest inside a <button>, hence the wrapping row rather
      // than appending this into `item` itself.
      if (onDelete && DELETABLE_STATES.has(run.state)) {
        const del = document.createElement("button");
        del.type = "button";
        del.className = "runitem__delete icon-btn";
        del.setAttribute("aria-label", t("delete_run"));
        del.title = t("delete_run");
        del.innerHTML = TRASH_ICON;
        del.addEventListener("click", (e) => {
          e.stopPropagation();
          onDelete(run.run_id, run.topic || run.run_id);
        });
        row.append(del);
      }

      container.append(row);
    }
  }
}

export async function refresh(container, { activeId, onSelect, onDelete }) {
  try {
    const { runs } = await api.listRuns(50);
    render(container, runs, { activeId, onSelect, onDelete });
    return runs;
  } catch {
    // A failed refresh leaves the previous list in place: an empty rail would
    // read as "your runs are gone".
    return null;
  }
}
