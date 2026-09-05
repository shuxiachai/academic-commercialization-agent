/* Live run: stage model, polling, and the progress view. */

import * as api from "./api.js";
import { t } from "./i18n.js";

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
  { id: "sources",  match: "Source Collection", key: "stage_sources" },
  { id: "evidence", match: "Phase 1",           key: "stage_evidence" },
  { id: "report",   match: "Agent 4",           key: "stage_report" },
  { id: "review",   match: "Agent 5",           key: "stage_review" },
  { id: "scoring",  match: "Agent 6",           key: "stage_scoring" },
];

// "unknown" is absent on purpose: a runtime record was unreadable, which says
// nothing about whether the run finished. Treating it as terminal would stop
// polling and show a still-running analysis as over.
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
  // The mutable stage can still say Done when a stronger outcome is damaged
  // or the process failed during finalization. Only verified completion may
  // paint every stage green; unknown cannot certify even a partial prefix.
  const done = state === "completed";
  const failed = state === "failed" || state === "timeout";
  const current = stageIndex(stage);

  return STAGES.map((s, i) => {
    if (state === "unknown") return { ...s, state: "pending" };
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
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function sourceSummary(counts) {
  if (!counts) return "";
  const { academic = 0, patent = 0, market = 0 } = counts;
  const total = academic + patent + market;
  if (!total) return "";
  return `${total} ${t("sources_suffix")} · ${academic} ${t("academic")}`
       + ` · ${patent} ${t("patent")} · ${market} ${t("market")}`;
}

/**
 * Tokens and cost for a finished run.
 *
 * Tokens are measured and always shown. Cost is an estimate from a price the
 * server cannot verify, so it is shown only when there is one, and a partial
 * total is prefixed with ~ and marked in the tooltip rather than being
 * rounded up into a figure that looks authoritative. A run whose model has no
 * price shows its tokens and no dollar figure at all — which is the honest
 * output, and the reason this is not simply `cost ?? 0`.
 */
export function usageSummary(usage, accounting = null) {
  if (!usage || !usage.total_tokens) {
    if (accounting?.state === "unavailable") return t("usage_unavailable");
    // Zero observed counters can still be a lower bound when a provider
    // accepted an in-flight request but never returned its usage payload.
    if (accounting?.state === "lower_bound") return t("usage_partial");
    return "";
  }
  const tokens = usage.total_tokens >= 1000
    ? `${(usage.total_tokens / 1000).toFixed(1)}k`
    : String(usage.total_tokens);
  const parts = [`${tokens} ${t("tokens_suffix")}`];
  if (usage.cost_usd != null) {
    const approx = usage.cost_complete ? "" : "~";
    parts.push(`${approx}$${usage.cost_usd.toFixed(4)}`);
  }
  if (accounting?.state === "lower_bound") parts.push(t("usage_partial"));
  return parts.join(" · ");
}

/** Tooltip spelling out where the cost figure came from, if anywhere. */
export function usageTitle(usage, accounting = null) {
  const lines = [];
  if (accounting?.state === "lower_bound") {
    lines.push(t("usage_partial_detail"));
  } else if (accounting?.state === "unavailable") {
    lines.push(t("usage_unavailable_detail"));
  }
  if (!usage) return lines.join("\n");
  if (usage.price_basis) lines.push(`${t("price_basis")}: ${usage.price_basis}`);
  if (usage.cost_complete === false && usage.unpriced_models?.length) {
    lines.push(t("cost_partial").replace("{models}", usage.unpriced_models.join(", ")));
  }
  for (const agent of usage.agents ?? []) {
    const cost = agent.cost_usd == null ? "—" : `$${agent.cost_usd.toFixed(4)}`;
    lines.push(`${agent.role}: ${agent.total_tokens} · ${cost}`);
  }
  return lines.join("\n");
}

/**
 * Human-readable cause for an immutable terminal outcome.
 *
 * The state pill already says completed/failed/cancelled/timeout, but that is
 * only a lifecycle category.  The terminal record says *why* the process
 * entered it.  Keep the known reasons translated and preserve an unknown
 * code verbatim: hiding a future reason behind a generic state would make the
 * browser less inspectable than the API, while textContent keeps it inert.
 */
export function terminalSummary(terminal, state = "") {
  const terminalStates = new Set(["completed", "failed", "cancelled", "timeout"]);
  if (!terminal) {
    return terminalStates.has(state) ? t("terminal_missing") : "";
  }
  if (terminal.record_state === "unreadable") return t("terminal_unreadable");

  const known = {
    worker_completed: "terminal_worker_completed",
    worker_exception: "terminal_worker_exception",
    user_cancelled: "terminal_user_cancelled",
    hard_timeout: "terminal_hard_timeout",
  };
  const key = known[terminal.reason_code];
  if (key) return t(key);
  if (terminal.reason_code) {
    return t("terminal_other_reason").replace("{reason}", terminal.reason_code);
  }
  return t("terminal_missing");
}

/** Raw reason and stop method for the run-header tooltip and audit inspection. */
export function terminalTitle(terminal, state = "") {
  if (!terminal) {
    return new Set(["completed", "failed", "cancelled", "timeout"]).has(state)
      ? t("terminal_missing_detail")
      : "";
  }
  if (terminal.record_state === "unreadable") return t("terminal_unreadable_detail");

  const lines = [];
  if (terminal.reason_code) {
    lines.push(t("terminal_reason_detail").replace("{reason}", terminal.reason_code));
  }
  if (terminal.termination_method) {
    lines.push(t("terminal_method_detail").replace("{method}", terminal.termination_method));
  }
  return lines.join("\n");
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
    label.textContent = t(stage.key);

    row.append(dot, label);
    list.append(row);
  }
  container.append(list);
}
