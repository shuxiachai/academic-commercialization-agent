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

export function render(container, runs, { activeId, onSelect }) {
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
      container.append(item);
    }
  }
}

export async function refresh(container, { activeId, onSelect }) {
  try {
    const { runs } = await api.listRuns(50);
    render(container, runs, { activeId, onSelect });
    return runs;
  } catch {
    // A failed refresh leaves the previous list in place: an empty rail would
    // read as "your runs are gone".
    return null;
  }
}
