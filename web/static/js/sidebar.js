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

export function render(container, runs, { activeId, onSelect, onDelete, emptyKey = "no_runs" }) {
  container.innerHTML = "";

  if (!runs.length) {
    const empty = document.createElement("div");
    empty.className = "runlist__empty";
    empty.textContent = t(emptyKey);
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
      if (run.state === "unknown") {
        dot.title = t("run_state_unknown");
        item.setAttribute("aria-label", `${run.topic || run.run_id} — ${t("run_state_unknown")}`);
      }

      const label = document.createElement("span");
      label.className = "runitem__label";
      label.textContent = run.topic || run.run_id;
      // The rail truncates aggressively, so the full topic lives in the title.
      item.title = run.topic || run.run_id;

      // Only ever present for an admin request (api/access.py owner_label) —
      // an unlabelled merge of every code's history answers "what ran", not
      // "who ran it", which is the entire reason to hold that code rather
      // than just leaving the gate unfiltered for everyone.
      if (run.owner_label) {
        const owner = document.createElement("span");
        owner.className = "runitem__owner";
        owner.textContent = run.owner_label;
        item.title = `${run.owner_label} · ${item.title}`;
        // Under the topic rather than beside it: beside it, the badge and the
        // delete button left the topic about a dozen characters of the rail.
        const text = document.createElement("span");
        text.className = "runitem__text";
        text.append(label, owner);
        item.className = "runitem runitem--owned";
        item.append(dot, text);
      } else {
        item.append(dot, label);
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

/* How much of the history the rail shows, and what it is filtered by.
 *
 * The list used to stop at the newest fifty with no way past them. It now
 * grows a page at a time, and a search box filters it. The filter runs in
 * the page: a topic can be an unpublished idea, and words sent as a query
 * string would be written to the server's access log, so they are never
 * sent. Searching therefore needs the history loaded, and loads it, up to
 * a bound that is said on screen when a history is longer than it.
 */
const PAGE = 50;          // what the rail shows at first, and each "show more" adds
const FETCH_MAX = 200;    // the most one request may ask for
const SEARCH_CAP = 1000;  // the most a search loads
const SEARCH_FROM = 8;    // below this a search box is clutter

let wanted = PAGE;
let query = "";

export function setQuery(text) { query = String(text ?? "").trim(); }
export function showMore() { wanted += PAGE; }
export function resetView() { wanted = PAGE; query = ""; }
export const matches = (run, needle) => [run.topic, run.owner_label, run.run_id]
  .some((text) => String(text ?? "").toLocaleLowerCase().includes(needle));

/* The newest `count` runs. One request, exactly as before, unless more than
 * a request's worth is wanted. A run that starts between two requests moves
 * every later one down a place, so a repeat is dropped rather than shown twice. */
async function load(count) {
  const first = await api.listRuns(Math.min(count, FETCH_MAX));
  const runs = [...(first?.runs ?? [])];
  const total = Number.isFinite(first?.total) ? first.total : runs.length;
  const seen = new Set(runs.map((run) => run.run_id));
  let offset = runs.length;
  while (offset < Math.min(count, total)) {
    const next = await api.listRuns(Math.min(FETCH_MAX, count - offset), offset);
    if (!next?.runs?.length) break;
    offset += next.runs.length;
    for (const run of next.runs) {
      if (!seen.has(run.run_id)) { seen.add(run.run_id); runs.push(run); }
    }
  }
  return { runs, total };
}

export async function refresh(container, { activeId, onSelect, onDelete, onChange = () => {}, isCurrent = () => true }) {
  try {
    const searching = Boolean(query);
    const { runs, total } = await load(searching ? SEARCH_CAP : wanted);
    // A cancelled fetch is only an optimization; a late successful response
    // must independently prove it still belongs to this view and identity.
    if (!isCurrent()) return null;
    const needle = query.toLocaleLowerCase();
    const shown = searching ? runs.filter((run) => matches(run, needle)) : runs;
    render(container, shown, { activeId, onSelect, onDelete, emptyKey: searching ? "runs_no_match" : "no_runs" });
    const box = document.querySelector("#run-search");
    if (box) box.hidden = !searching && total < SEARCH_FROM;
    if (searching && total > runs.length) {
      const note = document.createElement("div");
      note.className = "runlist__note";
      note.textContent = t("runs_search_capped").replace("{count}", String(runs.length));
      container.append(note);
    } else if (!searching && runs.length < total) {
      const more = document.createElement("button");
      more.type = "button";
      more.className = "runlist__more";
      more.textContent = t("runs_show_more").replace("{left}", String(total - runs.length));
      more.addEventListener("click", () => { showMore(); onChange(); });
      container.append(more);
    }
    return runs;
  } catch {
    // A failed refresh leaves the previous list in place: an empty rail would
    // read as "your runs are gone".
    return null;
  }
}
