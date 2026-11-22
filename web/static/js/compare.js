/* Two runs side by side.
 *
 * The same topic run twice, or two topics near each other: the question is
 * what changed, and a reader with two reports open in two tabs answers it by
 * eye. This puts the two scorecards in one table with the difference beside
 * them, and under it the few sentences a decision turns on, one from each.
 *
 * `comparison` is pure: it takes what was loaded for each run and returns
 * rows. `render` draws them. Nothing here starts a run or sends anything
 * but the reads the run page itself makes. */

import * as api from "./api.js";
import { locale, t } from "./i18n.js";
import { DIMENSIONS, decisionAsked, decisionBrief, decisionVerdict, expandButton, verdictLine } from "./result.js";
import { stateLabel } from "./run.js";

const record = value => value !== null && typeof value === "object" && !Array.isArray(value);
const number = (value, max) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= max;

/** When a run started, from its id: 20261021T022241Z-… is the start in UTC. */
export function startedAt(runId) {
  const match = /^(\d{4})(\d\d)(\d\d)T(\d\d)(\d\d)(\d\d)Z-/.exec(String(runId ?? ""));
  if (!match) return null;
  const [, y, mo, d, h, mi, s] = match.map(Number);
  const date = new Date(Date.UTC(y, mo - 1, d, h, mi, s));
  return Number.isNaN(date.getTime()) ? null : date;
}

/** A topic as it is compared: case, letter width, spacing and punctuation
 * aside, so "Hyperloop." and "hyperloop" are one topic. Nothing cleverer:
 * two wordings of one subject are two topics here, and the notice that
 * follows from this says only that the topics differ. */
const topicKey = (topic) => (typeof topic === "string"
  ? topic.normalize("NFKC").toLowerCase().replace(/[\p{P}\p{S}\s]+/gu, " ").trim() : "");

/** True or false for two topics on record; null when either is not, since a
 * run whose topic is unknown cannot be said to differ from anything. */
export function sameTopic(a, b) {
  const [left, right] = [topicKey(a), topicKey(b)];
  return left && right ? left === right : null;
}

/** The runs the picker offers for `runId`, in its order: the finished runs on
 * the same topic first, since comparing those is what the view is for, then
 * the rest, each group in the order the list gave them (newest first). The
 * run's own topic is read from the list; `topic` stands in when the run is
 * not in it. Until 2026-11-18 the list was by date alone, and a second run of
 * a topic stood wherever its date put it among unrelated ones. */
export function pickerOrder(runs, runId, topic = null) {
  const listed = Array.isArray(runs) ? runs.filter(run => record(run) && typeof run.run_id === "string" && run.run_id) : [];
  const own = listed.find(run => run.run_id === runId)?.topic ?? topic;
  const others = listed.filter(run => run.state === "completed" && run.run_id !== runId)
    .map(run => ({ run, same: sameTopic(run.topic, own) === true }));
  return [...others.filter(entry => entry.same), ...others.filter(entry => !entry.same)];
}

/** Everything the comparison reads about one run. Reads only; any read that
 * fails leaves that part empty and the rest still compares. */
export async function load(runId) {
  const reading = api.getRun(runId).catch(() => null);
  // The report's conclusion is read only for a run that was asked for one.
  // `undefined` is a read that failed, which the row says; null is no row.
  const deciding = reading.then(status => (decisionAsked(status)
    ? api.getDecision(runId).catch(() => undefined) : null));
  const [status, scores, markdown, decision] = await Promise.all([
    reading,
    api.getArtifact(runId, "scores").catch(() => null),
    api.getReport(runId).catch(() => ""),
    deciding,
  ]);
  return { id: runId, status, decision,
    scores: record(scores) ? scores : null, markdown: typeof markdown === "string" ? markdown : "" };
}

const CONTEXT_MODES = { orientation: "compare_context_orientation", decision_context_incomplete: "compare_context_incomplete" };

/** What the "Decision context" and "Decision conclusion" rows say of one run.
 * A run from before the gate has neither: nothing is known, and a dash says
 * so. A run that was not asked for a conclusion says that, not a dash, so a
 * reader does not take the other run's DEFER for a difference in the evidence. */
function decisionSide(run, status) {
  const gate = record(status.decision_gate) ? status.decision_gate : null;
  if (!gate) return { context: null, verdict: null };
  if (!decisionAsked(status)) {
    const unfinished = gate.mode === "decision_support" && gate.go_no_go_allowed === true;
    return {
      context: { key: unfinished ? "compare_context_given" : CONTEXT_MODES[gate.mode] ?? "compare_context_unknown" },
      verdict: { key: unfinished ? "compare_verdict_unfinished" : "compare_verdict_not_asked", tone: "muted" },
    };
  }
  const view = decisionVerdict(run.decision === null ? undefined : run.decision);
  if (!view) return { context: { key: "compare_context_given" }, verdict: { key: "verdict_unread", tone: "muted" } };
  return {
    context: view.asked.length ? { asked: view.asked } : { key: "compare_context_given" },
    verdict: verdictLine(view),
  };
}

function side(run) {
  const status = record(run.status) ? run.status : {};
  const scores = run.scores;
  const finished = status.state === "completed";
  // A run that did not finish may still have left a scores file behind, from
  // a stage before the one that failed. Numbers from a run that did not
  // complete are not its result, and are not compared.
  const scored = finished ? scores : null;
  const overall = scored && number(scored.overall_score, 100) ? scored.overall_score : null;
  const dims = {};
  for (const dim of DIMENSIONS) {
    const value = scored ? scored[dim.key] : undefined;
    dims[dim.key] = number(value, dim.max) && value >= 1 ? value : null;
  }
  const models = [...new Set((status.usage?.agents ?? []).map(a => a?.model).filter(Boolean))];
  return {
    id: run.id,
    topic: typeof status.topic === "string" && status.topic ? status.topic : run.id,
    // Whether `topic` is the run's topic or its id standing in for one.
    named: typeof status.topic === "string" && status.topic.trim() !== "",
    state: typeof status.state === "string" ? status.state : "unknown",
    finished,
    startedAt: startedAt(run.id),
    model: models.join(", ") || null,
    sources: record(status.source_counts) ? status.source_counts : null,
    overall,
    dims,
    brief: scored ? decisionBrief({ scores: scored, markdown: run.markdown }) : null,
    decision: decisionSide(run, status),
  };
}

const delta = (a, b) => (a === null || b === null ? null : Math.round((b - a) * 10) / 10);

/** Pure: two loaded runs in, rows out. `same` says the two ids are one run. */
export function comparison(left, right) {
  const sides = [side(left), side(right)];
  const rows = [{
    key: "overall_score", label: "compare_overall", max: 100,
    values: sides.map(s => s.overall), delta: delta(sides[0].overall, sides[1].overall),
  }];
  for (const dim of DIMENSIONS) {
    const values = sides.map(s => s.dims[dim.key]);
    rows.push({ key: dim.key, label: dim.label, max: dim.max, values, delta: delta(values[0], values[1]) });
  }
  // Rows nobody scored on either side say nothing about the difference.
  const kept = rows.filter(row => row.key === "overall_score" || row.values.some(value => value !== null));
  return { sides, rows: kept, same: String(left.id) === String(right.id),
    // false: two topics, which the view says before it shows a difference.
    sameTopic: sides.every(s => s.named) ? sameTopic(sides[0].topic, sides[1].topic) : null };
}

/* ── Drawing ───────────────────────────────────────────────────────── */

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
};

const fmt = (value, max) => (value === null ? "—" : max === 100 ? value.toFixed(1) : `${value} / ${max}`);
const signed = (value) => (value > 0 ? `+${value}` : String(value));
// The start in the interface's language (not the browser's) and on the
// reader's own clock, which the card says: the run ID next to it is in UTC.
const dateText = (date) => (date
  ? t("compare_local_time").replace("{time}", date.toLocaleString(locale(), { dateStyle: "medium", timeStyle: "short" }))
  : "—");

function sourcesText(counts) {
  if (!counts) return "—";
  const { academic = 0, patent = 0, market = 0 } = counts;
  return `${academic + patent + market} · ${academic} ${t("academic")} · ${patent} ${t("patent")} · ${market} ${t("market")}`;
}

/** A run's card, over its column of the table. The letter is the column's:
 * the table's heading said "A" and "B" and no card said which it was. */
function runCard(s, letter, onOpen) {
  const card = el("div", "compare__run");
  card.dataset.side = letter.toLowerCase();
  card.append(el("span", "compare__letter", letter));
  const title = el("a", "compare__topic", s.topic);
  title.href = `/run/${s.id}`;
  title.addEventListener("click", (event) => { event.preventDefault(); onOpen(s.id); });
  const meta = el("div", "compare__meta");
  const pill = el("span", `pill pill--${s.state}`, stateLabel(s.state));
  meta.append(pill, el("span", "compare__when tabular", dateText(s.startedAt)));
  if (s.model) meta.append(el("span", "compare__model tabular", s.model));
  card.append(title, meta);
  if (!s.finished) card.append(el("p", "empty-note", t("compare_not_finished")));
  return card;
}

/** One row under the table. A cell is text, or `{ text, whole, tone }`: with
 * `whole` the text was cut to fit and one press shows the rest. */
function briefRow(label, cells) {
  const shown = cells.map(cell => (typeof cell === "string" ? { text: cell } : cell));
  if (shown.every(cell => !cell?.text)) return null;
  const row = el("div", "compare__brief-row");
  row.dataset.row = label;
  row.append(el("div", "compare__brief-label", t(label)));
  for (const cell of shown) {
    // Text straight on the cell, as every row had it; a cut one gets a span
    // for its text beside the button that completes it.
    const node = el("div", "compare__brief-cell", cell?.whole ? null : cell?.text || "—");
    if (cell?.tone) node.dataset.tone = cell.tone;
    if (cell?.whole) {
      const text = el("span", "compare__brief-text", cell.text);
      node.append(text, expandButton(text, cell.whole));
    }
    row.append(node);
  }
  return row;
}

const contextText = (context) => (!context ? null : context.key ? t(context.key)
  : context.asked.map(item => `${t(item.label)}${t("verdict_label_colon")}${item.value}`).join(" · "));
const verdictText = (verdict) => (!verdict ? null : verdict.key ? { text: t(verdict.key), tone: verdict.tone } : verdict);

export function render(container, model, { onOpen = () => {} } = {}) {
  container.innerHTML = "";
  if (model.same) {
    container.append(el("p", "empty-note", t("compare_same_run")));
    return;
  }
  const [a, b] = model.sides;
  if (model.sameTopic === false) {
    // Before the cards and the table: a difference between two topics is not
    // a change in one. Not said when a topic is unknown.
    const notice = el("p", "compare__notice", t("compare_different_topics"));
    notice.setAttribute("role", "note");
    container.append(notice);
  }
  // Four cells, as the table has four columns: each card stands over its own.
  const heads = el("div", "compare__heads");
  heads.append(el("div", "compare__corner", ""), runCard(a, "A", onOpen), runCard(b, "B", onOpen), el("div", "compare__corner", ""));
  container.append(heads);

  const table = el("table", "compare__table");
  // The widths the cards above and the rows below are laid out on (result.css).
  const columns = el("colgroup");
  for (const name of ["label", "run", "run", "delta"]) columns.append(el("col", `compare__col--${name}`));
  table.append(columns);
  const thead = el("thead");
  const headRow = el("tr");
  for (const text of [t("compare_metric"), "A", "B", t("compare_delta")]) headRow.append(el("th", "", text));
  thead.append(headRow);
  table.append(thead);
  const body = el("tbody");
  for (const row of model.rows) {
    const tr = el("tr", row.key === "overall_score" ? "compare__row--overall" : "");
    tr.append(el("th", "", t(row.label)));
    for (const value of row.values) tr.append(el("td", "tabular", fmt(value, row.max)));
    const diff = el("td", "tabular compare__delta");
    if (row.delta === null) diff.textContent = "—";
    else {
      diff.textContent = row.delta === 0 ? "0" : signed(row.delta);
      diff.dataset.sign = row.delta > 0 ? "up" : row.delta < 0 ? "down" : "same";
    }
    tr.append(diff);
    body.append(tr);
  }
  table.append(body);
  const wrap = el("div", "table-wrap");
  wrap.append(table);
  container.append(wrap);
  if (model.rows.length === 1 && model.rows[0].values.every(value => value === null)) {
    container.append(el("p", "empty-note", t("compare_no_scores")));
  }

  const briefs = el("div", "compare__briefs");
  const pick = (fn) => model.sides.map(s => (s.brief ? fn(s.brief) : null));
  for (const row of [
    // What each run was asked and what its report answered, ahead of the rest:
    // two runs asked different questions are not two answers to one.
    briefRow("compare_context", model.sides.map(s => contextText(s.decision.context))),
    briefRow("compare_verdict", model.sides.map(s => verdictText(s.decision.verdict))),
    briefRow("compare_summary", pick(brief => brief.summary)),
    // As the brief says them, TRL as a level and a score (result.js trlReading).
    briefRow("compare_strongest", pick(brief => (brief.strongest ? `${t(brief.strongest.label)} ${brief.strongest.shown}` : null))),
    briefRow("compare_weakest", pick(brief => (brief.weakest ? `${t(brief.weakest.label)} ${brief.weakest.shown}` : null))),
    briefRow("compare_risk", pick(brief => brief.risk)),
    briefRow("compare_next", pick(brief => (brief.next ? { text: brief.next, whole: brief.nextWhole } : null))),
    briefRow("compare_sources", model.sides.map(s => (s.sources ? sourcesText(s.sources) : null))),
  ]) if (row) briefs.append(row);
  if (briefs.children.length) container.append(briefs);
}
