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
import { t } from "./i18n.js";
import { DIMENSIONS, decisionBrief } from "./result.js";
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

/** Everything the comparison reads about one run. Reads only; any read that
 * fails leaves that part empty and the rest still compares. */
export async function load(runId) {
  const [status, scores, markdown] = await Promise.all([
    api.getRun(runId).catch(() => null),
    api.getArtifact(runId, "scores").catch(() => null),
    api.getReport(runId).catch(() => ""),
  ]);
  return { id: runId, status, scores: record(scores) ? scores : null, markdown: typeof markdown === "string" ? markdown : "" };
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
    state: typeof status.state === "string" ? status.state : "unknown",
    finished,
    startedAt: startedAt(run.id),
    model: models.join(", ") || null,
    sources: record(status.source_counts) ? status.source_counts : null,
    overall,
    dims,
    brief: scored ? decisionBrief({ scores: scored, markdown: run.markdown }) : null,
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
  return { sides, rows: kept, same: String(left.id) === String(right.id) };
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
const dateText = (date) => (date ? date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—");

function sourcesText(counts) {
  if (!counts) return "—";
  const { academic = 0, patent = 0, market = 0 } = counts;
  return `${academic + patent + market} · ${academic} ${t("academic")} · ${patent} ${t("patent")} · ${market} ${t("market")}`;
}

function runCard(s, onOpen) {
  const card = el("div", "compare__run");
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

function briefRow(label, texts) {
  if (texts.every(text => !text)) return null;
  const row = el("div", "compare__brief-row");
  row.append(el("div", "compare__brief-label", t(label)));
  for (const text of texts) row.append(el("div", "compare__brief-cell", text || "—"));
  return row;
}

export function render(container, model, { onOpen = () => {} } = {}) {
  container.innerHTML = "";
  if (model.same) {
    container.append(el("p", "empty-note", t("compare_same_run")));
    return;
  }
  const [a, b] = model.sides;
  const heads = el("div", "compare__heads");
  heads.append(el("div", "compare__corner", ""), runCard(a, onOpen), runCard(b, onOpen));
  container.append(heads);

  const table = el("table", "compare__table");
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
    briefRow("compare_summary", pick(brief => brief.summary)),
    briefRow("compare_strongest", pick(brief => (brief.strongest ? `${t(brief.strongest.label)} ${brief.strongest.value} / ${brief.strongest.max}` : null))),
    briefRow("compare_weakest", pick(brief => (brief.weakest ? `${t(brief.weakest.label)} ${brief.weakest.value} / ${brief.weakest.max}` : null))),
    briefRow("compare_risk", pick(brief => brief.risk)),
    briefRow("compare_next", pick(brief => brief.next)),
    briefRow("compare_sources", model.sides.map(s => (s.sources ? sourcesText(s.sources) : null))),
  ]) if (row) briefs.append(row);
  if (briefs.children.length) container.append(briefs);
}
