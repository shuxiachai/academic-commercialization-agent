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
// How much of a topic a delete button's name carries before it is cut with "…".
const DELETE_NAME_LIMIT = 60;
// The states the list colours (workbench.css .runitem__state), each with a word in i18n.js (run_state_*).
const STATE_WORDS = new Set(["running", "completed", "failed", "cancelled", "timeout"]);

const TRASH_ICON = `
  <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M3 4.5h10M6.5 4.5V3a1 1 0 011-1h1a1 1 0 011 1v1.5M4.5 4.5l.6 8.4a1 1 0 001 .9h3.8a1 1 0 001-.9l.6-8.4"
          stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;

/* A resumed run and the run it continues are one piece of work.
 *
 * The list showed them as two rows with one name, one failed and one
 * completed, and nothing to say which led to which (production, 2026-11-18).
 * Here the newest run of such a chain keeps its row and the runs it continues
 * are folded under it, nearest first.
 *
 * `runs` is newest first, as the list is; each may name the run it was
 * resumed from (`resumed_from`). Returns [{ run, earlier }] in the same
 * order. Only runs that are in the list can be folded: a parent on a page
 * not loaded yet stays where it is until it is. A run resumed twice goes
 * under its newest resume; the older resume keeps a row of its own, since
 * it is a separate attempt and not a step on the way to the newest. */
export function grouped(runs) {
  const byId = new Map(runs.map((run) => [run.run_id, run]));
  const folded = new Set();
  const earlierOf = new Map();
  for (const run of runs) {
    if (folded.has(run.run_id)) continue;
    const chain = [];
    let source = run.resumed_from;
    while (typeof source === "string" && byId.has(source) && !folded.has(source) && source !== run.run_id) {
      folded.add(source);
      chain.push(byId.get(source));
      source = byId.get(source).resumed_from;
    }
    if (chain.length) earlierOf.set(run.run_id, chain);
  }
  return runs.filter((run) => !folded.has(run.run_id))
    .map((run) => ({ run, earlier: earlierOf.get(run.run_id) ?? [] }));
}

/* What the rail shows before the history has answered, and when it could not
 * be read. `data-state` says which of the three the rail holds: "loading",
 * "failed" or "shown" (render). The markup opens on the same loading rows
 * (index.html #runlist). Until 2026-11-28 it opened on "No runs yet", which
 * every signed-in visit read before its own runs arrived: about a second on
 * production, 4.4 s on DevTools' Slow 4G (tests/test_boot_loading.py). */
export function loading(container) {
  container.innerHTML = "";
  container.dataset.state = "loading";
  const busy = document.createElement("div");
  busy.className = "runlist__loading";
  busy.setAttribute("role", "status");
  busy.setAttribute("aria-busy", "true");
  const said = document.createElement("span");
  said.className = "visually-hidden";
  said.textContent = t("runs_loading");
  busy.append(said);
  for (let row = 0; row < 4; row++) {
    const bar = document.createElement("span");
    bar.className = "runlist__loading-row";
    busy.append(bar);
  }
  container.append(busy);
}

/* A history not read is not an empty one. The button asks the page for the
 * list again (`onChange`, the page's refresh), showing the loading rows meanwhile. */
function unread(container, onChange) {
  container.innerHTML = "";
  container.dataset.state = "failed";
  const note = document.createElement("div");
  note.className = "runlist__empty runlist__failed";
  note.setAttribute("role", "status");
  const line = document.createElement("span");
  line.textContent = t("runs_read_failed");
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "runlist__retry";
  retry.textContent = t("runs_retry");
  retry.addEventListener("click", () => {
    loading(container);
    onChange();
  });
  note.append(line, retry);
  container.append(note);
}

export function render(container, runs, { activeId, onSelect, onDelete, emptyKey = "no_runs" }) {
  container.innerHTML = "";
  container.dataset.state = "shown";

  if (!runs.length) {
    const empty = document.createElement("div");
    empty.className = "runlist__empty";
    empty.textContent = t(emptyKey);
    container.append(empty);
    return;
  }

  // A chain is listed where its newest run belongs.
  const groups = new Map(GROUP_ORDER.map((name) => [name, []]));
  for (const entry of grouped(runs)) groups.get(groupOf(entry.run.started_at)).push(entry);

  /* One row. `earlier` marks a run folded under the run that continued it:
   * its topic is the row above's, so it is named by how it ended and how
   * long it had run. */
  const rowFor = (run, { earlier = false } = {}) => {
    const row = document.createElement("div");
    row.className = earlier ? "runitem-row runitem-row--earlier" : "runitem-row";

    const item = document.createElement("button");
    item.type = "button";
    item.className = "runitem";
    item.dataset.runId = run.run_id;
    if (run.run_id === activeId) item.setAttribute("aria-current", "true");

    const dot = document.createElement("span");
    dot.className = "runitem__state";
    dot.dataset.state = run.state;
    // The dot says the state by colour alone. Every state gets its word:
    // as the dot's tooltip, and as text only a screen reader meets, after
    // the topic. The state nobody could read keeps the sentence it had.
    let spoken = null;
    if (run.state === "unknown") {
      dot.title = t("run_state_unknown");
      item.setAttribute("aria-label", `${run.topic || run.run_id} — ${t("run_state_unknown")}`);
    } else if (STATE_WORDS.has(run.state)) {
      dot.title = t(`run_state_${run.state}`);
      if (!earlier) {
        spoken = document.createElement("span");
        spoken.className = "visually-hidden";
        spoken.textContent = ` — ${t(`run_state_${run.state}`)}`;
      }
    }

    const label = document.createElement("span");
    label.className = "runitem__label";
    const stateWord = STATE_WORDS.has(run.state) ? t(`run_state_${run.state}`) : t("run_state_unknown");
    const lasted = typeof run.duration === "string" && run.duration && run.duration !== "—" ? run.duration : "";
    label.textContent = !earlier ? (run.topic || run.run_id)
      : lasted ? t("run_earlier_row").replace("{state}", stateWord).replace("{duration}", lasted) : stateWord;
    // The rail truncates aggressively, so the full topic lives in the title.
    item.title = run.topic || run.run_id;

    // Only ever present for an admin request (api/access.py owner_label) —
    // an unlabelled merge of every code's history answers "what ran", not
    // "who ran it", which is the entire reason to hold that code rather
    // than just leaving the gate unfiltered for everyone.
    if (run.owner_label && !earlier) {
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
    if (spoken) item.append(spoken);
    item.addEventListener("click", () => onSelect(run.run_id));
    row.append(item);

    // Buttons cannot nest inside a <button>, hence the wrapping row rather
    // than appending this into `item` itself.
    if (onDelete && DELETABLE_STATES.has(run.state)) {
      const del = document.createElement("button");
      del.type = "button";
      del.className = "runitem__delete icon-btn";
      // Named by the run it removes. Every button was "Delete", so a screen
      // reader's list of controls held one per run and nothing to tell them
      // apart (2026-11-20). An earlier attempt shares its topic with the row
      // above it and is told apart by how it ended.
      const topic = run.topic || run.run_id;
      const short = topic.length > DELETE_NAME_LIMIT ? `${topic.slice(0, DELETE_NAME_LIMIT - 1).trimEnd()}…` : topic;
      const named = t("delete_run_named").replace("{topic}", earlier ? `${short} — ${label.textContent}` : short);
      del.setAttribute("aria-label", named);
      del.title = named;
      del.innerHTML = TRASH_ICON;
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        onDelete(run.run_id, run.topic || run.run_id);
      });
      row.append(del);
    }
    return row;
  };

  for (const name of GROUP_ORDER) {
    const entries = groups.get(name);
    if (!entries.length) continue;

    const heading = document.createElement("div");
    heading.className = "runlist__group";
    heading.textContent = t(`group_${name.toLowerCase()}`);
    container.append(heading);

    for (const { run, earlier } of entries) {
      container.append(rowFor(run));
      if (!earlier.length) continue;
      // Folded by default: the newest run is the one to open. Open when the
      // run on screen is one of the folded ones, so the row that is current
      // is never out of sight.
      const fold = document.createElement("details");
      fold.className = "runitem-earlier";
      fold.open = earlier.some((older) => older.run_id === activeId);
      const summary = document.createElement("summary");
      summary.className = "runitem-earlier__summary";
      summary.textContent = earlier.length === 1 ? t("runs_earlier_one")
        : t("runs_earlier_many").replace("{count}", String(earlier.length));
      fold.append(summary);
      for (const older of earlier) fold.append(rowFor(older, { earlier: true }));
      container.append(fold);
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

/* The first page, asked for before the rail is drawn: while the boot's
 * access check is still out (app.js startBootReads), since the list is asked
 * with the identity stored in this page whatever the check says, and the
 * check decides only whether the reply is drawn. It was asked after the check
 * until 2026-11-28, one round trip later (tests/test_boot_loading.py).
 *
 * The next refresh draws it only for the page it asked for and the identity
 * it was asked with; otherwise it is dropped and the page asked again, so a
 * reply cannot cross a sign-in, a sign-out or a search. app.js drops it when
 * the boot stops at the sign-in card, which may stay open for minutes. */
let early = null;

export function prefetch() {
  const limit = Math.min(wanted, FETCH_MAX);
  const reply = api.listRuns(limit);
  reply.catch(() => {});  // read by the refresh that takes it, or by nobody
  early = { limit, session: api.getSessionToken(), code: api.getAccessCode(), reply };
}

export function forgetPrefetch() { early = null; }

function takeEarly(limit) {
  const taken = early;
  early = null;
  if (!taken || taken.limit !== limit) return null;
  if (taken.session !== api.getSessionToken() || taken.code !== api.getAccessCode()) return null;
  return taken.reply;
}

/* The newest `count` runs. One request, exactly as before, unless more than
 * a request's worth is wanted. A run that starts between two requests moves
 * every later one down a place, so a repeat is dropped rather than shown twice. */
async function load(count) {
  const limit = Math.min(count, FETCH_MAX);
  const first = await (takeEarly(limit) ?? api.listRuns(limit));
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
  // What the caller's own account has going, as the newest reply says it.
  return { runs, total, activity: { activeRuns: first?.active_runs ?? [], atCapacity: first?.at_capacity === true } };
}

export async function refresh(container, {
  activeId, onSelect, onDelete, onChange = () => {}, isCurrent = () => true, onActivity = () => {},
}) {
  try {
    const searching = Boolean(query);
    const { runs, total, activity } = await load(searching ? SEARCH_CAP : wanted);
    // A cancelled fetch is only an optimization; a late successful response
    // must independently prove it still belongs to this view and identity.
    if (!isCurrent()) return null;
    // Whether the account has a run going rides on the list (GET /api/runs):
    // handed on before the rows are drawn, so a list that fails to draw
    // cannot leave the composer saying the opposite of the server.
    onActivity(activity);
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
    // A failed refresh leaves a list already drawn in place: an empty rail
    // would read as "your runs are gone". A rail that has drawn none yet
    // says the history could not be read; left as it was, its loading rows
    // would wait for ever. A reply for an older view or identity paints nothing.
    if (isCurrent() && container.dataset.state !== "shown") unread(container, onChange);
    return null;
  }
}
