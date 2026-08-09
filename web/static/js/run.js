/* Live run: stage model, polling, and the progress view. */

import * as api from "./api.js";

/* ── Stage model ───────────────────────────────────────────────────────
 * The worker reports one free-text stage string at a time. The UI shows the
 * whole pipeline at once so a waiting user can see what is done and what is
 * left, which means mapping that string onto a fixed sequence.
 *
 * Matching is by substring against the worker's own labels
 * (pipeline_worker.py). Exact equality would break on any wording change,
 * and the labels carry en dashes and interpuncts that are easy to mistype.
 */
const STAGES = [
  { id: "sources",  match: "Source Collection", label: "Collecting and validating sources" },
  { id: "evidence", match: "Phase 1",           label: "Academic · Patent · Market analysis" },
  { id: "report",   match: "Agent 4",           label: "Writing the report" },
  { id: "review",   match: "Agent 5",           label: "Reviewing citations and claims" },
  { id: "scoring",  match: "Agent 6",           label: "Scoring commercialization readiness" },
];

const TERMINAL = new Set(["completed", "failed", "cancelled", "timeout"]);

/** Index of the stage a status string refers to, or -1 when unrecognised. */
function stageIndex(stage) {
  if (!stage) return -1;
  return STAGES.findIndex((s) => stage.includes(s.match));
}

/**
 * Per-stage state for the current status.
 *
 * "Done" is reported as its own stage rather than as the last one, so a
 * completed run marks every stage done instead of leaving the final one
 * looking stuck.
 */
export function stageStates(stage, state) {
  const done = state === "completed" || stage === "Done";
  const failed = state === "failed" || state === "timeout";
  const current = stageIndex(stage);

  return STAGES.map((s, i) => {
    if (done) return { ...s, state: "done" };
    if (current === -1) return { ...s, state: "pending" };
    if (i < current) return { ...s, state: "done" };
    if (i > current) return { ...s, state: "pending" };
    return { ...s, state: failed ? "failed" : "active" };
  });
}

/* ── Polling ───────────────────────────────────────────────────────────
 * Intervals widen as a run settles in. Source collection produces visible
 * changes every few seconds; the agent phase can sit on one stage for a
 * minute, and polling it at the same rate is wasted traffic.
 */
function intervalFor(elapsedMs) {
  if (elapsedMs < 20_000) return 1200;
  if (elapsedMs < 90_000) return 2500;
  return 4000;
}

/**
 * Follow a run to completion.
 *
 * Returns a handle with stop(); the caller must call it when leaving the
 * view, or a poll loop outlives the run it was watching.
 */
export function follow(runId, { onUpdate, onDone, onError }) {
  let stopped = false;
  let seenSteps = 0;
  let timer = null;
  const startedAt = Date.now();

  async function tick() {
    if (stopped) return;
    try {
      const progress = await api.getProgress(runId, seenSteps);
      if (stopped) return;

      seenSteps += progress.steps.length;
      onUpdate?.(progress);

      if (TERMINAL.has(progress.state)) {
        onDone?.(progress);
        return;
      }
    } catch (err) {
      if (stopped) return;
      // A transient failure should not end the run view: the worker may
      // still be fine and the next tick may well succeed. Only a 404 means
      // the run genuinely is not there.
      if (err.status === 404) {
        onError?.(err);
        return;
      }
    }
    timer = setTimeout(tick, intervalFor(Date.now() - startedAt));
  }

  tick();

  return {
    stop() {
      stopped = true;
      if (timer) clearTimeout(timer);
    },
  };
}

/* ── Formatting ────────────────────────────────────────────────────── */

export function formatDuration(seconds) {
  if (seconds == null) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function sourceSummary(counts) {
  if (!counts) return "";
  const { academic = 0, patent = 0, market = 0 } = counts;
  const total = academic + patent + market;
  if (!total) return "";
  return `${total} sources · ${academic} academic · ${patent} patent · ${market} market`;
}

/* ── Rendering ─────────────────────────────────────────────────────── */

export function renderStages(container, stages) {
  container.innerHTML = "";
  const list = document.createElement("div");
  list.className = "stages";

  for (const stage of stages) {
    const row = document.createElement("div");
    row.className = "stage";
    row.dataset.state = stage.state;

    const dot = document.createElement("span");
    dot.className = "stage__dot";

    const label = document.createElement("span");
    label.className = "stage__label";
    label.textContent = stage.label;

    row.append(dot, label);
    list.append(row);
  }
  container.append(list);
}
