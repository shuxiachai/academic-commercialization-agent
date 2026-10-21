/* Live run: stage model, polling, and the progress view. */

import * as api from "./api.js";
import { t, language as uiLanguage } from "./i18n.js";

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

// A read failure or an initial request still in flight is not a terminal
// outcome. Share this boundary with actions rather than treating all states
// except running as permission to delete retained artifacts.
export const isTerminalState = (state) => TERMINAL.has(state);

/** Index of the stage a status string refers to, or -1 when unrecognised. */
function stageIndex(stage) {
  if (!stage) return -1;
  return STAGES.findIndex((s) => stage.includes(s.match));
}

/** Seconds spent in each stage, by stage id, from the API's stage_timings. */
function stageSeconds(timings) {
  const seconds = {};
  for (const timing of Array.isArray(timings) ? timings : []) {
    const index = stageIndex(timing?.stage);
    if (index === -1 || !Number.isFinite(timing.duration_seconds)) continue;
    const { id } = STAGES[index];
    seconds[id] = (seconds[id] ?? 0) + timing.duration_seconds;
  }
  return seconds;
}

/**
 * Per-stage state for the current status, with the time each stage took.
 *
 * "Done" is reported as its own stage rather than as the last one, so a
 * completed run marks every stage done instead of leaving the final one
 * looking stuck.
 */
export function stageStates(stage, state, timings = []) {
  // The mutable stage can still say Done when a stronger outcome is damaged
  // or the process failed during finalization. Only verified completion may
  // paint every stage green; unknown cannot certify even a partial prefix.
  const done = state === "completed";
  const failed = state === "failed" || state === "timeout";
  const current = stageIndex(stage);
  const seconds = stageSeconds(timings);

  const stateOf = (i) => {
    if (state === "unknown") return "pending";
    if (done) return "done";
    if (current === -1) return "pending";
    if (i < current) return "done";
    if (i > current) return "pending";
    return failed ? "failed" : "active";
  };
  // A pending row shows no time, even when an unverifiable outcome has
  // repainted stages the worker did record as finished.
  return STAGES.map((s, i) => {
    const rowState = stateOf(i);
    return { ...s, state: rowState, seconds: rowState === "pending" ? null : seconds[s.id] ?? null };
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
export function follow(runId, { onUpdate, onDone, onError, onConnection }) {
  let stopped = false;
  let seenSteps = 0;
  let timer = null;
  let lastSuccessAt = null;
  const startedAt = Date.now();

  async function tick() {
    if (stopped) return;
    try {
      const progress = await api.getProgress(runId, seenSteps);
      if (stopped) return;

      lastSuccessAt = Date.now();
      onConnection?.({ state: "connected", lastSuccessAt });

      // A rejected physical line still advances the server cursor. Fall back
      // only for old deployments which have not introduced this field yet.
      seenSteps = Number.isSafeInteger(progress.steps_next_cursor)
        && progress.steps_next_cursor >= seenSteps
        ? progress.steps_next_cursor : seenSteps + progress.steps.length;
      onUpdate?.(progress);

      if (TERMINAL.has(progress.state)) {
        onDone?.(progress);
        return;
      }
    } catch (err) {
      if (stopped) return;
      // Retry reads, but never present silence as evidence that the worker
      // still runs. A later successful poll clears this independent warning.
      onConnection?.({ state: err.status === 404 ? "missing" : "stale", lastSuccessAt });
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
  // An unavailable collector can still leave numeric defaults in its payload.
  // Honor the accounting fact before looking at either tokens or prices.
  if (accounting?.state === "unavailable") return t("usage_unavailable");
  if (!usage || !usage.total_tokens) {
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
  parts.push(t(usage.accounting_scope === "crew_nodes" ? "usage_scope_crew" : "usage_scope_unknown"));
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
  if (!usage || accounting?.state === "unavailable") return lines.join("\n");
  lines.push(t(usage.accounting_scope === "crew_nodes" ? "usage_scope_detail" : "usage_scope_unknown"));
  if (usage.pricing_warnings?.length) lines.push(t("usage_pricing_warning"));
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

// i18n.js is a byte-frozen SLC observer asset. New production-only labels
// stay here, not in that historical asset or its manifest/hash allowlist.
const AUXILIARY_STRINGS = {
  English: {
    aux_not_recorded: "Auxiliary LLM usage not recorded (not zero)",
    aux_unreadable: "Auxiliary LLM usage unreadable (not zero)",
    aux_scope: "Auxiliary LLM only",
    aux_calls: "Invocations",
    aux_tokens: "Observed tokens",
    aux_estimate: "Observed cost estimate",
    aux_partial: "Incomplete / lower bound",
    aux_write_failed: "Accounting storage failed",
    aux_reference: "PDF extraction is a historical reference, not a new charge",
    aux_limits: "Excludes Crew/search-provider costs; not a full invoice",
  },
  "Simplified Chinese": {
    aux_not_recorded: "辅助 LLM 用量未记录（并非零费用）",
    aux_unreadable: "辅助 LLM 用量不可读（并非零费用）",
    aux_scope: "仅辅助 LLM",
    aux_calls: "调用次数",
    aux_tokens: "已观测 token",
    aux_estimate: "已观测估算费用",
    aux_partial: "不完整／下界",
    aux_write_failed: "用量记录存储失败",
    aux_reference: "PDF 提取仅为历史引用，不是新费用",
    aux_limits: "不含 Crew／搜索提供商费用；不是完整账单",
  },
};

// Run-header labels, kept out of the byte-frozen i18n.js like AUXILIARY_STRINGS.
const HEADER_STRINGS = {
  English: {
    usage_details: "Usage & cost",
    stage_timing: "Stage timing",
    source_locator: "Saved-source locator",
    source_locator_title: "Experimental: pick the saved source behind a question about a report and read its saved text",
  },
  "Simplified Chinese": {
    usage_details: "用量与费用",
    stage_timing: "阶段耗时",
    source_locator: "已保存来源定位",
    source_locator_title: "实验功能：针对报告中的问题，找出对应的已保存来源并显示其原文",
  },
};

// English keeps the API's own state words (the pill uppercases them, and the
// browser tests read them); Chinese readers get words rather than codes.
const STATE_LABELS = {
  "Simplified Chinese": {
    running: "运行中", completed: "已完成", failed: "失败",
    cancelled: "已取消", timeout: "已超时", unknown: "状态未知",
  },
};

export function headerLabel(key) {
  return (HEADER_STRINGS[uiLanguage()] ?? HEADER_STRINGS.English)[key] ?? HEADER_STRINGS.English[key];
}

export function stateLabel(state) {
  return STATE_LABELS[uiLanguage()]?.[state] ?? state;
}

// Short stage names for the one-line timing summary; the stage list keeps the
// long ones from i18n.js.
const STAGE_SHORT_LABELS = {
  English: { sources: "Sources", evidence: "Evidence", report: "Report", review: "Review", scoring: "Scoring" },
  "Simplified Chinese": { sources: "来源", evidence: "证据分析", report: "报告撰写", review: "审查", scoring: "评分" },
};

/** "Sources 0:40 · Evidence 1:00 · Report 0:25…" from stage_timings; "" without any. */
export function timingSummary(timings) {
  const labels = STAGE_SHORT_LABELS[uiLanguage()] ?? STAGE_SHORT_LABELS.English;
  const seconds = stageSeconds(timings);
  const active = new Set((Array.isArray(timings) ? timings : [])
    .filter((timing) => timing?.active)
    .map((timing) => STAGES[stageIndex(timing.stage)]?.id));
  return STAGES
    .filter((s) => seconds[s.id] != null)
    .map((s) => `${labels[s.id]} ${formatDuration(seconds[s.id])}${active.has(s.id) ? "…" : ""}`)
    .join(" · ");
}

/** Independent helper observations; never folded into Crew's numeric total. */
export function auxiliarySummary(value) {
  const labels = AUXILIARY_STRINGS[uiLanguage()] ?? AUXILIARY_STRINGS.English;
  const t = key => labels[key];
  if (value == null || value?.record_state === "not_recorded") return t("aux_not_recorded");
  const count = v => v === null || (Number.isSafeInteger(v) && v >= 0);
  const cost = v => v === null || (typeof v === "number" && Number.isFinite(v) && v >= 0);
  if (typeof value !== "object" || Array.isArray(value) || value.schema_version !== 1
      || value.accounting_scope !== "auxiliary_llm" || value.end_to_end_cost_complete !== false
      || !["recorded", "write_failed", "unreadable"].includes(value.record_state)
      || !["complete", "partial", "pending", "unavailable"].includes(value.coverage)
      || typeof value.cost_complete !== "boolean"
      || ![value.call_count, value.provider_attempt_count, value.total_tokens, value.observed_tokens].every(count)
      || !cost(value.observed_cost_usd)) return t("aux_unreadable");
  if (value.record_state === "unreadable") return t("aux_unreadable");
  const parts = [t("aux_scope"), `${t("aux_calls")}: ${value.call_count ?? "—"}`,
    `${t("aux_tokens")}: ${value.observed_tokens ?? "—"}`,
    `${t("aux_estimate")}: ${value.observed_cost_usd === null ? "—" : "$" + String(value.observed_cost_usd)}`];
  if (value.coverage !== "complete" || !value.cost_complete) parts.push(t("aux_partial"));
  if (value.record_state === "write_failed") parts.push(t("aux_write_failed"));
  if (value.pdf_reference?.relation === "reference_only") parts.push(t("aux_reference"));
  parts.push(t("aux_limits"));
  return parts.join(" · ");
}

/** Code-owned read faults, not inferred billing or checkpoint success. */
export function runtimeMetadataSummary(fields = []) {
  const labels = {
    usage: "runtime_usage", usage_accounting: "runtime_accounting",
    checkpointing: "runtime_checkpointing", recovery: "runtime_recovery",
  };
  const names = fields.filter(field => Object.hasOwn(labels, field)).map(field => t(labels[field]));
  return names.length ? t("runtime_metadata_unreadable").replace("{fields}", names.join(", ")) : "";
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
    if (stage.seconds != null) {
      const time = document.createElement("span");
      time.className = "stage__meta";
      time.textContent = formatDuration(stage.seconds);
      row.append(time);
    }
    list.append(row);
  }
  container.append(list);
}
