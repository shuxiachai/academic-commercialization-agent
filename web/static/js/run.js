/* Live run: stage model, polling, and the progress view. */

import * as api from "./api.js";
import { t, language as uiLanguage, locale } from "./i18n.js";

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
  { id: "sources",  match: "Source Collection", key: "stage_sources",  nodes: ["retrieval"] },
  { id: "evidence", match: "Phase 1",           key: "stage_evidence", nodes: ["academic", "patent", "market"] },
  { id: "report",   match: "Agent 4",           key: "stage_report",   nodes: ["writer"] },
  { id: "review",   match: "Agent 5",           key: "stage_review",   nodes: ["reviewer"] },
  { id: "scoring",  match: "Agent 6",           key: "stage_scoring",  nodes: ["scorer"] },
];

/* The stages a resumed run took whole from the run it continues: every
 * checkpoint behind the stage was reused (the node names are the
 * checkpoints' own, checkpoint_runtime.TASK_NODES plus "retrieval"; a test
 * holds the lists together). A stage of which only part was reused ran here
 * and is not one of these. Empty for a run that reused nothing. */
export function reusedStages(recovery) {
  const reused = recovery?.state === "reused" && Array.isArray(recovery.reused_nodes) ? recovery.reused_nodes : [];
  return new Set(STAGES.filter((s) => s.nodes.every((node) => reused.includes(node))).map((s) => s.id));
}

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

/**
 * Seconds spent in each stage, by stage id, from the API's stage_timings.
 *
 * With `recovery`, a resumed run's seconds are shown where they were spent.
 * Until 2026-11-19 the worker left a resume's stage on the evidence phase
 * until its first task completed, so a resume that only scored recorded its
 * scoring time under "Phase 1": the production resume of 2026-11-18 still
 * read "Evidence 3:33" in its timing fold. Those records are not rewritten.
 * But a stage a run took whole from the earlier run ran nothing in it, so
 * seconds recorded under one were spent in the first step the run did run,
 * which its own record names (`recovery.next_node`), and are shown there.
 * The first stage is left alone: its seconds are the run starting up, under
 * that label then and now. A record written since has no seconds under a
 * reused stage, and a run that reused nothing has no reused stage: for
 * both, nothing moves.
 */
function stageSeconds(timings, recovery = null) {
  const seconds = {};
  for (const timing of Array.isArray(timings) ? timings : []) {
    const index = stageIndex(timing?.stage);
    if (index === -1 || !Number.isFinite(timing.duration_seconds)) continue;
    const { id } = STAGES[index];
    seconds[id] = (seconds[id] ?? 0) + timing.duration_seconds;
  }
  const reused = reusedStages(recovery);
  const began = STAGES.find((s) => s.nodes.includes(recovery?.next_node));
  if (began && !reused.has(began.id)) {
    for (const stage of STAGES.slice(1)) {
      if (!reused.has(stage.id) || seconds[stage.id] == null) continue;
      seconds[began.id] = (seconds[began.id] ?? 0) + seconds[stage.id];
      delete seconds[stage.id];
    }
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
export function stageStates(stage, state, timings = [], recovery = null) {
  // The mutable stage can still say Done when a stronger outcome is damaged
  // or the process failed during finalization. Only verified completion may
  // paint every stage green; unknown cannot certify even a partial prefix.
  const done = state === "completed";
  const failed = state === "failed" || state === "timeout";
  const current = stageIndex(stage);
  const seconds = stageSeconds(timings, recovery);
  const reused = reusedStages(recovery);

  const stateOf = (i) => {
    if (state === "unknown") return "pending";
    // A finished stage this run did not run itself is said to be the earlier
    // run's: "done" with a time beside it would claim work that was not done
    // here. Only a finished row: the stage a run is in, or stopped in, is its own.
    const finished = reused.has(STAGES[i].id) ? "reused" : "done";
    if (done) return finished;
    if (current === -1) return "pending";
    if (i < current) return finished;
    if (i > current) return "pending";
    return failed ? "failed" : "active";
  };
  // A pending row shows no time, even when an unverifiable outcome has
  // repainted stages the worker did record as finished. Nor does a reused
  // one: the seconds it took were the earlier run's.
  return STAGES.map((s, i) => {
    const rowState = stateOf(i);
    const timed = rowState !== "pending" && rowState !== "reused";
    return { ...s, state: rowState, seconds: timed ? seconds[s.id] ?? null : null };
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
 *
 * The handle's poll() asks now rather than at the next interval, for the
 * moment the page has just changed the run itself: after a cancel, a run
 * past its first ninety seconds went on reading "running" for up to four.
 * One question is out at a time. If one is already out, its answer may have
 * been formed before the change, so one more follows it at once.
 */
export function follow(runId, { onUpdate, onDone, onError, onConnection }) {
  let stopped = false;
  let ended = false;
  let asking = false;
  let askAgain = false;
  let seenSteps = 0;
  let timer = null;
  let lastSuccessAt = null;
  const startedAt = Date.now();

  /* One question. Resolves to whether the run is still worth asking about. */
  async function ask() {
    try {
      const progress = await api.getProgress(runId, seenSteps);
      if (stopped) return false;

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
        return false;
      }
    } catch (err) {
      if (stopped) return false;
      // Retry reads, but never present silence as evidence that the worker
      // still runs. A later successful poll clears this independent warning.
      onConnection?.({ state: err.status === 404 ? "missing" : "stale", lastSuccessAt });
      // A transient failure should not end the run view: the worker may
      // still be fine and the next tick may well succeed. Only a 404 means
      // the run genuinely is not there.
      if (err.status === 404) {
        onError?.(err);
        return false;
      }
    }
    return true;
  }

  async function tick() {
    if (stopped || ended) return;
    timer = null;
    asking = true;
    const goOn = await ask();
    asking = false;
    if (stopped) return;
    if (!goOn) {
      ended = true;
      return;
    }
    if (askAgain) {
      askAgain = false;
      tick();
      return;
    }
    timer = setTimeout(tick, intervalFor(Date.now() - startedAt));
  }

  tick();

  return {
    stop() {
      stopped = true;
      if (timer) clearTimeout(timer);
    },
    poll() {
      if (asking) {
        askAgain = true;
        return;
      }
      if (timer) clearTimeout(timer);
      tick();
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

/**
 * The line that heads the header's "Usage & cost" fold: what the run used
 * and what that is estimated to have cost, in a reader's words.
 *
 * The fold was headed by its name alone, and opened on the full accounting:
 * "105.5k tokens · Crew nodes only · Auxiliary LLM only · Invocations: 0 ·
 * Observed tokens: 0 · Observed cost estimate: $0 · ...". The only sum in
 * sight was the helper ledger's $0, on a run that had used a hundred
 * thousand tokens. That text is the record and stays inside the fold; this
 * line is what a reader gets without opening it.
 *
 * No sum is ever invented: a run whose model has no price says no cost is
 * shown and names the model, and one whose recorded cost is zero says the
 * cost cannot be estimated; a partial sum is a floor and is said as one. ""
 * where no tokens are on record or the collector says its record is
 * unavailable: the fold then keeps its plain name, and the text inside says
 * why.
 *
 * `fundedBy` is the run's `funded_by`. "cost cannot be estimated: no price
 * on record for qwen3.8-2.4t-a95b" headed every run on the account's saved
 * model and on the deployment's default (production, 2026-11-20): a sentence
 * about this site's price table. A reader who paid with their own key is
 * told where the exact amount is; a run the site paid for is not sent to a
 * console its reader does not have.
 */
export function usageHeadline(usage, accounting = null, fundedBy = null) {
  if (accounting?.state === "unavailable") return "";
  const tokens = usage?.total_tokens;
  if (!Number.isFinite(tokens) || tokens <= 0) return "";
  const floor = accounting?.state === "lower_bound";
  const head = say(floor ? "usage_head_tokens_floor" : "usage_head_tokens", { tokens: tokenAmount(tokens) });

  const names = (list) => [...new Set((Array.isArray(list) ? list : []).filter((name) => typeof name === "string" && name))];
  const models = names((usage.agents ?? []).map((agent) => agent?.model));
  const unpriced = names(usage.unpriced_models);
  const priced = Number.isFinite(usage.cost_usd) && usage.cost_usd > 0;
  let cost;
  if (!priced) {
    // A record from before unpriced_models was kept says nothing but a null
    // cost; its models are the unpriced ones. A zero is not "no price".
    const missing = unpriced.length ? unpriced : usage.cost_usd == null ? models : [];
    const key = fundedBy === "own_keys" ? "usage_head_no_price_own" : "usage_head_no_price";
    cost = missing.length ? say(key, { models: missing.join(", ") }) : say("usage_head_no_cost_plain");
  } else {
    const sum = usage.cost_usd < 0.01 ? say("usage_head_under_a_cent") : `$${usage.cost_usd.toFixed(2)}`;
    if (usage.cost_complete === false && unpriced.length) {
      cost = say("usage_head_cost_missing", { cost: sum, models: unpriced.join(", ") });
    } else {
      const key = floor || usage.cost_complete === false ? "usage_head_cost_floor" : "usage_head_cost";
      cost = models.length ? say(key, { cost: sum, models: models.join(", ") }) : say(key + "_plain", { cost: sum });
    }
  }
  return `${head} · ${cost}`;
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

// Production-only labels written while i18n.js was hash-locked by the SLC
// comparison. That comparison now reads a snapshot (evals/
// source_locator_observer_v1), so new labels may also go in i18n.js.
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

// Run-header labels, kept beside AUXILIARY_STRINGS.
const HEADER_STRINGS = {
  English: {
    usage_details: "Usage & cost",
    tech_details: "Technical details",
    // The fold's heading when the run has tokens on record (usageHeadline).
    usage_head_tokens: "About {tokens} tokens",
    usage_head_tokens_floor: "At least {tokens} tokens",
    usage_head_cost: "estimated cost {cost} at the price on record for {models}",
    usage_head_cost_plain: "estimated cost {cost}",
    usage_head_cost_floor: "estimated cost at least {cost} at the price on record for {models}",
    usage_head_cost_floor_plain: "estimated cost at least {cost}",
    usage_head_cost_missing: "estimated cost at least {cost}; no price on record for {models}",
    usage_head_under_a_cent: "under $0.01",
    usage_head_no_price: "no cost shown, as no unit price is on record yet for {models}",
    usage_head_no_price_own: "no cost shown, as no unit price is on record yet for {models}; see your provider's console for the exact amount",
    usage_head_no_cost_plain: "cost cannot be estimated",
    stage_timing: "Stage timing",
    eta_left: "about {range} left",
    eta_left_others: "about {range} left, going by runs on other models",
    eta_range: "{low}–{high} min",
    eta_range_one: "{high} min",
    eta_soon: "under a minute left",
    eta_over: "The remaining time for the current step cannot yet be estimated.",
    eta_over_later: "In the last {runs} runs, the subsequent steps ({steps}) took {range} in total.",
    eta_minutes_short: "under a minute",
    eta_heading: "Historical estimate",
    eta_missing: "No historical estimate is available yet.",
    eta_sample_model: "Based on the last {runs} completed runs on {model}.",
    eta_sample_pool: "Based on {runs} recent completed runs across models. There were too few runs on this model alone.",
    deadline_stage: "Current step · {stage}",
    deadline_limit: "Run limit {limit} · up to {left} remaining (min:sec)",
    deadline_pending: "Run limit {limit} (min:sec) reached. Waiting for the server to confirm the outcome.",
    deadline_unknown: "Time limit for this run is unavailable.",
    deadline_cap_only: "Run limit {limit} (min:sec). Remaining time until the limit is unavailable.",
    deadline_unbounded: "This run has no configured time limit.",
    deadline_writer: "If the run times out, the saved writer checkpoint may provide a draft.",
    deadline_reviewer: "If the run times out, the saved review checkpoint may provide a reviewed draft.",
    deadline_sources: "The saved sources may still be available if the run times out.",
    deadline_checkpoints: "Completed checkpoints may be reused if the run times out.",
    deadline_partial: "Some checkpoints were saved. Recovery after a timeout depends on which checkpoints remain usable.",
    deadline_no_saved: "No completed checkpoint or saved sources have been confirmed yet.",
    eta_title: "What the last {runs} completed runs on {model} here took from this step to the end, fastest to slowest. Not a guarantee.",
    eta_title_others: "{model} has fewer than three completed runs here, so this is what the last {runs} completed runs on other models took from this step to the end, fastest to slowest. Not a guarantee.",
    eta_title_any: "What the last {runs} completed runs here took from this step to the end, fastest to slowest. Not a guarantee.",
    // A resumed run, under its header (lineageSummary).
    stage_reused: "reused from the earlier run",
    lineage_reused: "This run continues {earlier}. Reused from it: {reused}. Run here: {ran}.",
    lineage_reused_all: "This run continues {earlier}. Everything was reused from it: {reused}.",
    lineage_cold: "This run was started to continue {earlier}, but nothing that run had saved could be reused, so every step ran again.",
    lineage_earlier: "an earlier run",
    lineage_sep: ", ",
    lineage_total: "In all: {time} ({own} here + {before} before){usage}.",
    lineage_total_running: "Before this run: {before}{usage}.",
    lineage_usage: " · {tokens} tokens ({own} here + {before} before)",
    lineage_usage_before: " · {before} tokens",
    lineage_usage_none: " · token use before this run is not on record",
    lineage_cost: " · estimated cost {cost}",
    lineage_at_least: "at least {value}",
    lineage_missing: "The earlier run's record has been deleted, so these figures cover this run only.",
    // On the run a resume continued (the reads' continued_by).
    continued_note: "This run was resumed later.",
    continued_open: "Open the run that continued it",
    // The header a reader of someone else's run is shown (readerHeader).
    reader_assessed: "Assessed {date}",
    reader_started: "Started {date}",
    reader_assessed_range: "Assessed {from} – {to}",
    reader_started_range: "Started {from} – {to}",
    reader_dates_title: "Dates are in UTC.",
    reader_model: "Model: {model}",
    reader_took: "took {time}",
    reader_took_all: "took {time} in all",
    reader_ran: "ran for {time}",
    reader_ran_all: "ran for {time} in all",
    reader_running: "running for {time}",
    reader_running_all: "running for {time} in all",
    // While the account's own assessment is going (activeRunNotice).
    busy_banner: "You have an assessment in progress: {topic}.",
    busy_banner_plain: "You have an assessment in progress.",
    busy_view: "View it",
    busy_reason: "Your account cannot preview or start another assessment while one is in progress. Wait for it to finish, or cancel it; what you typed stays here.",
    busy_reason_other: "Your account has an operation in progress, such as an uploaded paper being read. Another can be previewed or started when it has finished; what you typed stays here.",
    // A failure the reader cannot fix alone (operatorHelp).
    help_run_id: "Run ID",
    help_copy: "Copy",
    help_copied: "Run ID copied.",
    help_copy_failed: "The run ID could not be copied. Select it and copy it by hand.",
    help_contact: "Operator: {contact}",
    help_no_contact: "This deployment has published no operator contact.",
    notify: "Notify me when done",
    notify_title: "Shows a browser notification when this run finishes while the tab is in the background.",
    finished_ok: "Assessment complete",
    finished_bad: "Assessment did not finish",
    quota_left: "{remaining} of {limit} runs left today",
    quota_none: "No runs left today · resets {time}",
    quota_title: "Each run and each PDF extraction uses one. Resets at 00:00 UTC ({time} your time).",
    source_locator: "Saved-source locator",
    source_locator_title: "Experimental: pick the saved source behind a question about a report and read its saved text",
    identity_title: "The model this run's stages requested and the pipeline code that served it. The deployment changes models without notice; neither name is a quality measurement.",
    // Beside a failed run's reason: a code holder has three runs a day and
    // should not have to guess whether a failure spent one of them.
    outcome_charged: "This run counted toward today's quota.",
    shortage_validation: "Academic sources fell short after validation ({accepted} passed, minimum {required}).",
    shortage_relevance: "Academic sources fell short after final filtering ({accepted} retained, minimum {required}).",
    shortage_before_report: "The assessment stopped before a report was written.",
    shortage_no_report: "No report is available.",
    // Under a run that did not finish: what the model's own record suggests (failureGuide).
    advice_model_kind: "The model this run used, {model}, does not look like a general chat model. Change to a model this project has measured before trying again: resuming repeats the same step on the model that is saved now.",
    advice_model_short: "Each answer {model} gave in the evidence step was under {limit} tokens, where every run this project has saved wrote more. Change to a model this project has measured before trying again: resuming repeats the same step on the model that is saved now.",
    // Beside "Resume from checkpoint" (resumeNote): what it costs, where it starts, on which model.
    resume_note_quota: "Resuming uses one more of today's runs.",
    resume_note_step: "It starts again at {step} and reuses what was saved before it.",
    resume_note_step_first: "Resuming starts again at {step} and reuses what was saved before it.",
    resume_note_model: "It will run on {model}.",
    resume_note_model_changed: "It will run on {model}, not on {ranOn}, which this run used.",
    resume_step_evidence: "the evidence analysis",
    resume_step_writing: "writing the report",
    resume_step_review: "the review",
    resume_step_scoring: "the scoring",
    // The main action when the cause is the reader's model or key.
    fix_model: "Change the model",
    fix_keys: "Check your API keys",
    // While a run is going: it does not need the page.
    leave_note: "You can close this page. When the assessment finishes, it is in the history on the left.",
    leave_notify: "Email me when it finishes",
    outcome_refunded: "This run did not count toward today's quota: it failed before any work began.",
    outcome_refunded_unreachable: "This run did not count toward today's quota: the model provider could not be reached, which nothing in your request caused.",
    outcome_not_charged: "This run did not use the daily quota.",
  },
  "Simplified Chinese": {
    usage_details: "用量与费用",
    tech_details: "技术信息",
    usage_head_tokens: "约 {tokens} token",
    usage_head_tokens_floor: "至少 {tokens} token",
    usage_head_cost: "估算费用 {cost}（按 {models} 的记录价格）",
    usage_head_cost_plain: "估算费用 {cost}",
    usage_head_cost_floor: "估算费用至少 {cost}（按 {models} 的记录价格）",
    usage_head_cost_floor_plain: "估算费用至少 {cost}",
    usage_head_cost_missing: "估算费用至少 {cost}；{models} 没有记录价格",
    usage_head_under_a_cent: "不到 $0.01",
    usage_head_no_price: "{models} 还没有登记单价，所以不显示费用",
    usage_head_no_price_own: "{models} 还没有登记单价，所以不显示费用；准确金额请看你的服务商控制台",
    usage_head_no_cost_plain: "费用无法估算",
    stage_timing: "阶段耗时",
    eta_left: "预计还需约 {range}",
    eta_left_others: "预计还需约 {range}（按其他模型的运行）",
    eta_range: "{low}–{high} 分钟",
    eta_range_one: "{high} 分钟",
    eta_soon: "预计不到 1 分钟",
    eta_over: "当前阶段剩余时间暂时无法估计。",
    eta_over_later: "最近 {runs} 次运行中，后续步骤（{steps}）合计用时 {range}。",
    eta_minutes_short: "不到 1 分钟",
    eta_heading: "历史耗时估算",
    eta_missing: "暂时没有可用的历史耗时估算。",
    eta_sample_model: "参考了最近 {runs} 次使用 {model} 完成的运行。",
    eta_sample_pool: "当前模型的样本不足，参考了跨模型的 {runs} 次近期已完成运行。",
    deadline_stage: "当前阶段 · {stage}",
    deadline_limit: "本次运行时限 {limit} · 最多还可运行 {left}（分:秒）",
    deadline_pending: "已达到本次运行时限 {limit}（分:秒），正在等待服务器确认结果。",
    deadline_unknown: "暂未取得本次运行的时限。",
    deadline_cap_only: "本次运行时限 {limit}（分:秒）。暂未取得距时限的剩余时间。",
    deadline_unbounded: "本次运行未设置时限。",
    deadline_writer: "撰写阶段已保存检查点。如果超时，仍可能从中读取报告草稿。",
    deadline_reviewer: "审查阶段已保存检查点。如果超时，仍可能从中读取已审查的草稿。",
    deadline_sources: "如果超时，仍可能查看已保存的来源。",
    deadline_checkpoints: "如果超时，仍可能从已保存的检查点恢复运行。",
    deadline_partial: "已有部分检查点保存。如果超时，可恢复的内容取决于哪些检查点仍然有效。",
    deadline_no_saved: "暂未确认有已完成的检查点或已保存的来源。",
    eta_title: "本站最近 {runs} 次用 {model} 完成的运行，从这一步到结束的实际用时（最快到最慢）。仅供参考，不是保证。",
    eta_title_others: "{model} 在本站完成的运行还不到 3 次，所以这是最近 {runs} 次其他模型完成的运行从这一步到结束的实际用时（最快到最慢）。仅供参考，不是保证。",
    eta_title_any: "本站最近 {runs} 次完成的运行，从这一步到结束的实际用时（最快到最慢）。仅供参考，不是保证。",
    stage_reused: "沿用上次结果",
    lineage_reused: "这是一次续跑，接着{earlier}做。沿用上次结果：{reused}。本次重做：{ran}。",
    lineage_reused_all: "这是一次续跑，接着{earlier}做。全部沿用上次结果：{reused}。",
    lineage_cold: "这次运行本来要接着{earlier}做，但那次保存的结果都用不上，所以每一步都重做了。",
    lineage_earlier: "上一次运行",
    lineage_sep: "、",
    lineage_total: "合计用时 {time}（本次 {own} + 之前 {before}）{usage}。",
    lineage_total_running: "在这次之前：{before}{usage}。",
    lineage_usage: "；合计 {tokens} token（本次 {own} + 之前 {before}）",
    lineage_usage_before: "，{before} token",
    lineage_usage_none: "；之前的 token 用量没有记录",
    lineage_cost: "；估算费用 {cost}",
    lineage_at_least: "至少 {value}",
    lineage_missing: "上一次运行的记录已被删除，所以这些数字只包含本次运行。",
    continued_note: "这次运行后来已被续跑。",
    continued_open: "打开接着它做的那次运行",
    reader_assessed: "评估于 {date}",
    reader_started: "开始于 {date}",
    reader_assessed_range: "评估于 {from}至{to}",
    reader_started_range: "开始于 {from}至{to}",
    reader_dates_title: "日期按 UTC 计。",
    reader_model: "模型：{model}",
    reader_took: "用时 {time}",
    reader_took_all: "合计用时 {time}",
    reader_ran: "运行了 {time}",
    reader_ran_all: "合计运行了 {time}",
    reader_running: "已运行 {time}",
    reader_running_all: "合计已运行 {time}",
    busy_banner: "你有一份评估正在进行：{topic}。",
    busy_banner_plain: "你有一份评估正在进行。",
    busy_view: "查看",
    busy_reason: "有评估在进行时，你的账号不能预览或开始另一份。等它结束，或先取消它；已输入的内容会保留。",
    busy_reason_other: "你的账号有一项操作正在进行，比如正在读取上传的论文。等它结束后才能预览或开始另一份；已输入的内容会保留。",
    help_run_id: "运行 ID",
    help_copy: "复制",
    help_copied: "运行 ID 已复制。",
    help_copy_failed: "运行 ID 没能复制。请手动选中后复制。",
    help_contact: "运营者：{contact}",
    help_no_contact: "本站没有公布运营者的联系方式。",
    notify: "完成时提醒我",
    notify_title: "标签页在后台时，运行结束后弹出浏览器通知。",
    finished_ok: "评估已完成",
    finished_bad: "评估未完成",
    quota_left: "今日剩余 {remaining}/{limit} 次",
    quota_none: "今日次数已用完 · {time} 重置",
    quota_title: "每次运行和每次 PDF 提取各占 1 次。每天 UTC 0 点重置（你的当地时间 {time}）。",
    source_locator: "已保存来源定位",
    source_locator_title: "实验功能：针对报告中的问题，找出对应的已保存来源并显示其原文",
    identity_title: "本次运行各阶段请求的模型，以及产出它的流水线代码版本。本站会不定期更换模型；两者都不是质量指标。",
    outcome_charged: "本次运行已计入今日额度。",
    shortage_validation: "有 {accepted} 条学术来源通过验证，至少需要 {required} 条。",
    shortage_relevance: "最终筛选后保留了 {accepted} 条学术来源，至少需要 {required} 条。",
    shortage_before_report: "评估在写报告前停止。",
    shortage_no_report: "没有可查看的报告。",
    advice_model_kind: "这次运行用的模型 {model} 看起来不是通用对话模型。请先换成本项目实测过的模型再试：续跑会在当前保存的模型上重做同一步。",
    advice_model_short: "{model} 在证据分析这一步的每次回答都不到 {limit} token，而本项目保存的每一次运行都比这长。请先换成本项目实测过的模型再试：续跑会在当前保存的模型上重做同一步。",
    resume_note_quota: "续跑会再用 1 次今日额度。",
    resume_note_step: "它从{step}重新开始，之前已保存的部分会沿用。",
    resume_note_step_first: "续跑从{step}重新开始，之前已保存的部分会沿用。",
    resume_note_model: "它会在 {model} 上运行。",
    resume_note_model_changed: "它会在 {model} 上运行，而不是这次运行所用的 {ranOn}。",
    resume_step_evidence: "证据分析",
    resume_step_writing: "撰写报告",
    resume_step_review: "核查",
    resume_step_scoring: "评分",
    fix_model: "更换模型",
    fix_keys: "检查 API Key",
    leave_note: "可以关掉这个页面，完成后在左侧历史里找到它。",
    leave_notify: "完成时发邮件给我",
    outcome_refunded: "本次运行未计入今日额度：它在开始工作前就失败了。",
    outcome_refunded_unreachable: "本次运行未计入今日额度：模型服务暂时无法连接，与你的请求无关。",
    outcome_not_charged: "本次运行不占用每日额度。",
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

/**
 * "qwen3.7-max · git:1b69b06": which model and which code produced a run.
 *
 * The public deployment rotates models without a code change, so two runs a
 * week apart can come from different models while the page looks the same.
 * The model names come from the usage record (one per Crew node, usually all
 * the same), so a run still going shows only its revision until usage lands.
 * Nothing here is a quality claim; the tooltip says so.
 */
export function identitySummary(usage, pipelineRevision) {
  const models = [...new Set((usage?.agents ?? []).map((a) => a?.model).filter(Boolean))];
  const parts = [models.join(", ")];
  if (typeof pipelineRevision === "string" && pipelineRevision) {
    // git:<40 hex> reads as its short form; any other revision string
    // (a source hash) is kept whole, since no prefix of it is conventional.
    const git = /^git:([0-9a-f]{7})[0-9a-f]*$/.exec(pipelineRevision);
    parts.push(git ? `git:${git[1]}` : pipelineRevision);
  }
  return parts.filter(Boolean).join(" · ");
}

/* Header text with its {names} filled in. A function as the replacement, so
 * a "$" in a model name or a contact line is text and not a pattern. */
function say(key, values = {}) {
  return Object.entries(values).reduce(
    (text, [name, value]) => text.replace(`{${name}}`, () => String(value)), headerLabel(key));
}

/* "12–25 min" from a range in seconds. The low end is rounded down and the
 * high end up, so the range said is never narrower than the one measured. */
function minutesRange(low, high) {
  const from = Math.max(1, Math.floor(low / 60));
  const to = Math.max(from, Math.ceil(high / 60));
  return from === to ? say("eta_range_one", { high: to }) : say("eta_range", { low: from, high: to });
}

/**
 * "about 12–25 min left" for a running run; "" without an estimate.
 *
 * The range is what recent completed runs took from this step to their end
 * (api/eta.py), not one typical figure: the page said "about 7 min" at the
 * start of a run that took 24 min 40 s. Where the range comes from runs of
 * other models the line says so, since a model's speed is most of the
 * answer. A run slower at its step than every run in the pool is told that,
 * with what the later steps took, instead of a countdown that has run out.
 */
export function etaSummary(eta, stage) {
  const low = eta?.low_seconds;
  const high = eta?.high_seconds;
  if (!Number.isFinite(low) || !Number.isFinite(high) || low < 0 || high < low) return "";
  const runs = Number.isFinite(eta.basis_runs) ? eta.basis_runs : "";
  if (eta.overdue) {
    const unknown = headerLabel("eta_over");
    const current = stageIndex(stage);
    if (eta.basis !== "stages" || current < 0 || current === STAGES.length - 1) return unknown;
    const labels = STAGE_SHORT_LABELS[uiLanguage()] ?? STAGE_SHORT_LABELS.English;
    const steps = STAGES.slice(current + 1).map((s) => labels[s.id]).join(" → ");
    const range = high < 60 ? headerLabel("eta_minutes_short") : minutesRange(low, high);
    return unknown + " " + say("eta_over_later", { runs, steps, range });
  }
  if (high < 60) return headerLabel("eta_soon");
  return say(eta.same_model ? "eta_left" : "eta_left_others", { range: minutesRange(low, high) });
}

/** Where the range comes from: whose runs, and how many. `model` is the run's own. */
export function etaTitle(eta, model = null) {
  if (!Number.isFinite(eta?.basis_runs)) return "";
  const runs = eta.basis_runs;
  if (eta.overdue) {
    return eta.same_model && eta.model ? say("eta_sample_model", { runs, model: eta.model })
      : say("eta_sample_pool", { runs });
  }
  if (eta.same_model && eta.model) return say("eta_title", { runs, model: eta.model });
  return model ? say("eta_title_others", { runs, model }) : say("eta_title_any", { runs });
}

export function currentStep(stage) {
  const known = STAGES[stageIndex(stage)];
  return known ? say("deadline_stage", { stage: t(known.key) }) : "";
}

// Only the server can anchor the countdown for this run. Between polls the
// caller supplies monotonic seconds since that observation, never time spent
// by a parent run or time inferred from a historical sample.
export function deadlineView(progress, sincePoll = 0) {
  const budget = progress.runtime_budget;
  const limit = budget?.hard_timeout_seconds;
  const observed = budget?.remaining_seconds;
  if (budget?.state !== "active" || !Number.isSafeInteger(limit) || limit <= 0) {
    return { line: headerLabel(budget?.state === "unbounded_cli" ? "deadline_unbounded" : "deadline_unknown"), note: "" };
  }
  if (!Number.isSafeInteger(observed) || observed < 0 || observed > limit) {
    return { line: say("deadline_cap_only", { limit: formatDuration(limit) }), note: "" };
  }
  const remaining = Math.max(0, observed - sincePoll);
  const line = say(remaining ? "deadline_limit" : "deadline_pending", {
    limit: formatDuration(limit), left: formatDuration(remaining),
  });
  if (remaining > Math.min(300, limit / 5)) return { line, note: "" };
  const nodes = progress.checkpointing?.committed_nodes;
  const saved = Array.isArray(nodes) ? nodes : [];
  const notes = [];
  if (saved.includes("reviewer")) notes.push(headerLabel("deadline_reviewer"));
  else if (saved.includes("writer")) notes.push(headerLabel("deadline_writer"));
  else if (saved.includes("retrieval")) notes.push(headerLabel("deadline_checkpoints"));
  else if (saved.length) notes.push(headerLabel("deadline_partial"));
  if (progress.artifacts?.includes("sources")) notes.push(headerLabel("deadline_sources"));
  return { line, note: notes.join(" ") || headerLabel("deadline_no_saved") };
}

/* A token count as a reader says it: 105,500 is "105.5k" in English and
 * "10.6 万" in Chinese; small counts are said as they are. */
export function tokenAmount(tokens) {
  if (uiLanguage() === "Simplified Chinese") {
    return tokens >= 10_000 ? `${(tokens / 10_000).toFixed(1)} 万` : String(tokens);
  }
  return tokens >= 1000 ? `${(tokens / 1000).toFixed(1)}k` : String(tokens);
}

/**
 * What a resumed run says under its header: what it took from the run it
 * continues, and what the two took together.
 *
 * The header used to end in "6 checkpoint stages reused", a count of
 * checkpoints in the pipeline's own word, set after the model name and the
 * usage fold; and the time and tokens beside it were the resume's alone,
 * 3:48 and about 35,000 for a report that had taken 29 minutes and at least
 * 176,000 (production, 2026-11-18).
 *
 * Returns { reuse, earlier, totals, missing }: `reuse` is the sentence about
 * the stages, with "{earlier}" where the link to the earlier run goes and
 * `earlier` that run's id (null when it cannot be opened); `totals` is the
 * sum, and `missing` the sentence for an earlier run whose record is gone.
 * Each "" when there is nothing to say; null for a run that is not a resume.
 *
 * The usage rule is the server's (runs._lineage) and is only worded here: a
 * sum that is a floor is said as "at least", a count that is not on record
 * is said to be missing, and neither is ever shown as a plain total.
 */
export function lineageSummary({ state, recovery, lineage, elapsed_seconds, usage, usage_accounting } = {}) {
  const requested = ["reused", "cold_start"].includes(recovery?.state) && typeof recovery?.source_run_id === "string";
  if (!requested && !lineage) return null;
  const labels = STAGE_SHORT_LABELS[uiLanguage()] ?? STAGE_SHORT_LABELS.English;
  const list = (ids) => ids.map((id) => labels[id]).join(headerLabel("lineage_sep"));

  let reuse = "";
  if (recovery?.state === "cold_start") {
    reuse = headerLabel("lineage_cold");
  } else if (recovery?.state === "reused") {
    const reused = reusedStages(recovery);
    const taken = STAGES.filter((s) => reused.has(s.id)).map((s) => s.id);
    const ran = STAGES.filter((s) => !reused.has(s.id)).map((s) => s.id);
    if (taken.length) {
      reuse = ran.length ? say("lineage_reused", { reused: list(taken), ran: list(ran) })
        : say("lineage_reused_all", { reused: list(taken) });
    }
  }

  const nearest = lineage?.earlier?.[0];
  const earlier = nearest?.record === "available" ? nearest.run_id : null;
  const combined = lineage?.combined;
  if (!combined) return { reuse, earlier, totals: "", missing: "" };

  const rows = Array.isArray(lineage.earlier) ? lineage.earlier : [];
  const missing = rows.some((row) => row.record !== "available") ? headerLabel("lineage_missing") : "";
  const atLeast = (value, floor) => (floor ? say("lineage_at_least", { value }) : value);
  const number = (value) => Number.isFinite(value) && value >= 0;

  // Time: this run's and the earlier runs', each said only where it is known.
  const beforeTimes = rows.map((row) => row.elapsed_seconds).filter(number);
  const beforeTime = beforeTimes.length
    ? atLeast(formatDuration(beforeTimes.reduce((a, b) => a + b, 0)), beforeTimes.length < rows.length) : null;

  // Tokens: a floor in any run makes that part, and the sum, a floor.
  const counted = rows.filter((row) => number(row.total_tokens));
  const beforeFloor = counted.length < rows.length || counted.some((row) => row.usage_state !== "complete");
  const beforeTokens = counted.length
    ? atLeast(tokenAmount(counted.reduce((sum, row) => sum + row.total_tokens, 0)), beforeFloor) : null;
  const ownCounted = usage_accounting?.state !== "unavailable" && number(usage?.total_tokens);
  const ownTokens = ownCounted ? atLeast(tokenAmount(usage.total_tokens), usage_accounting?.state !== "complete") : null;

  const running = !isTerminalState(state);
  let usageText = "";
  if (running) {
    usageText = beforeTokens ? say("lineage_usage_before", { before: beforeTokens }) : headerLabel("lineage_usage_none");
  } else if (number(combined.total_tokens) && combined.usage_state !== "unavailable" && ownTokens && beforeTokens) {
    usageText = say("lineage_usage", {
      tokens: atLeast(tokenAmount(combined.total_tokens), combined.usage_state !== "complete"),
      own: ownTokens, before: beforeTokens,
    });
    if (number(combined.cost_usd) && combined.cost_usd > 0) {
      const sum = combined.cost_usd < 0.01 ? headerLabel("usage_head_under_a_cent") : `$${combined.cost_usd.toFixed(2)}`;
      usageText += say("lineage_cost", {
        cost: atLeast(sum, !(combined.cost_complete && combined.usage_state === "complete")),
      });
    }
  } else if (!beforeTokens) {
    usageText = headerLabel("lineage_usage_none");
  }

  let totals = "";
  if (running) {
    if (beforeTime) totals = say("lineage_total_running", { before: beforeTime, usage: usageText });
  } else if (number(combined.elapsed_seconds) && number(elapsed_seconds) && beforeTime) {
    totals = say("lineage_total", {
      time: atLeast(formatDuration(combined.elapsed_seconds), combined.elapsed_complete === false),
      own: formatDuration(elapsed_seconds), before: beforeTime, usage: usageText,
    });
  }
  // Chinese sets no space between a word and the "至少" that follows it.
  return { reuse, earlier, totals: totals.replace(/([一-鿿]) (?=至少)/g, "$1"), missing };
}

/* When a run was started, from its id: create_run_id() begins every id with
 * that moment in UTC. null for an id that does not. */
export function runStartedAt(runId) {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z-/.exec(typeof runId === "string" ? runId : "");
  if (!m) return null;
  const when = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
  return Number.isNaN(when.getTime()) ? null : when;
}

/**
 * The header a reader of someone else's run is shown: when it was assessed,
 * on which model, and how long it took. The header under the title was
 * written for whoever ran it, and a shared link is how a report travels: a
 * colleague it was forwarded to read token counts, "see your provider's
 * console", the stage times and a paragraph about resuming, and "3:57" for
 * an assessment that had taken 29 minutes over two runs (production run
 * 20261120T131247Z, 2026-11-21). app.js shows this instead of those to
 * anyone who may not modify the run; its owner's header is unchanged.
 *
 * Returns { assessed, title, model, seconds, timeKey }, each "" or null when
 * there is nothing sure to say:
 *  - `assessed`: the day the assessment began, which is when its evidence
 *    was gathered. A resume takes its evidence from the run it continues,
 *    so a chain begins with its oldest run (every id in `lineage`, which the
 *    reads give any reader), unless this run could reuse nothing and
 *    gathered its own (`cold_start`); a chain over several days is said as
 *    a span. In UTC, as the ids are, and the title says so.
 *  - `model`: the model the run was configured with, else its usage record's.
 *  - `seconds` and `timeKey`: how long it took, in all for a resume. The
 *    total follows the server's rule (runs._lineage): written only when it
 *    knows every run's time (`elapsed_complete`), never a partial sum.
 */
export function readerHeader({ run_id, state, llm_model, usage, elapsed_seconds, lineage, recovery, stage_timings } = {}) {
  const firstStage = Array.isArray(stage_timings) ? new Date(stage_timings[0]?.started_at ?? NaN) : null;
  const own = runStartedAt(run_id) ?? (firstStage && !Number.isNaN(firstStage.getTime()) ? firstStage : null);
  const earlier = Array.isArray(lineage?.earlier) ? lineage.earlier : [];
  let from = own;
  if (own && recovery?.state !== "cold_start") {
    for (const row of earlier) {
      const began = runStartedAt(row?.run_id);
      if (began && began < from) from = began;
    }
  }
  const day = (when) => new Intl.DateTimeFormat(locale(), { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })
    .format(when);
  const done = state === "completed";
  let assessed = "";
  if (own) {
    assessed = day(from) === day(own)
      ? say(done ? "reader_assessed" : "reader_started", { date: day(own) })
      : say(done ? "reader_assessed_range" : "reader_started_range", { from: day(from), to: day(own) });
  }

  const configured = typeof llm_model === "string" ? llm_model.trim() : "";
  const recorded = [...new Set((usage?.agents ?? []).map((agent) => agent?.model).filter((name) => typeof name === "string" && name))];
  const named = configured || recorded.join(", ");

  const known = (value) => Number.isFinite(value) && value >= 0;
  const all = Boolean(lineage);
  const combined = lineage?.combined;
  const seconds = !all ? (known(elapsed_seconds) ? elapsed_seconds : null)
    : combined?.elapsed_complete === true && known(combined.elapsed_seconds) ? combined.elapsed_seconds : null;
  const verb = state === "running" ? "reader_running" : done ? "reader_took" : "reader_ran";
  return {
    assessed,
    title: assessed ? headerLabel("reader_dates_title") : "",
    model: named ? say("reader_model", { model: named }) : "",
    seconds,
    timeKey: all ? `${verb}_all` : verb,
  };
}

/** "took 29:28 in all": a reader's time line for `seconds`, by readerHeader's key. */
export function readerTime(timeKey, seconds) {
  return say(timeKey, { time: formatDuration(seconds) });
}

/**
 * What the workbench says while the account already has an assessment going.
 *
 * An account runs one assessment at a time, and the refusal was the first
 * the page said of it: a second topic went through its plan preview, one
 * small request on the account's key, and was told only when Start was
 * pressed (production, 2026-11-18). Nothing on the workbench showed a run in
 * progress, and on a phone the history is off screen.
 *
 * `activeRuns` and `atCapacity` are the server's (GET /api/runs), the same
 * count its admission makes. Returns:
 *  - `banner`: the line above the panes, { runId, text, view }, for the
 *    newest run in progress; null when there is none or its own page is the
 *    one open (`openRunId`), where the header already says "running";
 *  - `blocked`: whether another preview, start or upload would be refused;
 *  - `reason`: the sentence said beside the controls that are off, "" when
 *    nothing is. The server can be at capacity with no run to point at (an
 *    uploaded paper being read holds the slot), and says that instead.
 */
export function activeRunNotice({ activeRuns, atCapacity = false, openRunId = null } = {}) {
  const going = (Array.isArray(activeRuns) ? activeRuns : [])
    .filter((entry) => typeof entry?.run_id === "string" && entry.run_id);
  const first = going[0] ?? null;
  const topic = typeof first?.topic === "string" ? first.topic.trim() : "";
  const banner = first && first.run_id !== openRunId ? {
    runId: first.run_id,
    text: topic ? say("busy_banner", { topic }) : headerLabel("busy_banner_plain"),
    view: headerLabel("busy_view"),
  } : null;
  const blocked = atCapacity === true;
  return { banner, blocked, reason: blocked ? headerLabel(first ? "busy_reason" : "busy_reason_other") : "" };
}

/* Whether a run's failure is one its reader cannot fix alone, so the page
 * shows the run's ID to copy and the operator's contact.
 *
 * The sentence for an unrecognised failure has always ended "contact the
 * operator with the run ID", on a page that showed neither the ID nor a
 * contact (production, 2026-11-18). Those are: a cause the API could not
 * name (`unknown`, or a code this page does not know), and, for a run the
 * reader's own keys did not pay for, the causes only the operator can act
 * on, which FAILURE_NEXT marks with no next step. A cancelled run is the
 * reader's own doing and needs no one. */
export function needsOperator({ state, error_code, funded_by } = {}) {
  if (state !== "failed" && state !== "timeout") return false;
  if (!Object.hasOwn(FAILURE_NEXT, error_code ?? "") || error_code === "unknown") return true;
  return funded_by !== "own_keys" && FAILURE_NEXT[error_code][1] === null;
}

/** Composer line for GET /api/quota; text "" when the deployment has no cap. */
export function quotaSummary(quota) {
  if (!quota || !Number.isFinite(quota.limit) || !Number.isFinite(quota.remaining)) {
    return { text: "", title: "", exhausted: false };
  }
  const reset = new Date(quota.resets_at);
  const time = Number.isNaN(reset.getTime()) ? "00:00 UTC"
    : reset.toLocaleTimeString(uiLanguage() === "Simplified Chinese" ? "zh-CN" : "en", { hour: "2-digit", minute: "2-digit" });
  const exhausted = quota.remaining <= 0;
  const text = headerLabel(exhausted ? "quota_none" : "quota_left")
    .replace("{remaining}", String(quota.remaining)).replace("{limit}", String(quota.limit))
    .replace("{time}", time);
  return { text, title: headerLabel("quota_title").replace("{time}", time), exhausted };
}

export function stateLabel(state) {
  return STATE_LABELS[uiLanguage()]?.[state] ?? state;
}

// Search-plan preview panel.
const PLAN_STRINGS = {
  English: {
    title: "Check the search before starting",
    lede: "Papers, patents and market sources will be searched with these terms. "
      + "Edit them if the topic was read wrongly; this check does not use a daily run.",
    // An account: the check was made on the account's own key, and says so.
    lede_own: "Papers, patents and market sources will be searched with these terms. "
      + "Edit them if the topic was read wrongly. This check was one small request on your model key.",
    // An account with no keys whose check the deployment made: an
    // administrator it funds, or a newcomer on a trial assessment.
    lede_funded: "Papers, patents and market sources will be searched with these terms. "
      + "Edit them if the topic was read wrongly. "
      + "This check was paid for by this site, not with a key of yours, and does not use a daily run.",
    search_topic: "Search phrase",
    aliases: "Also searched as",
    components: "Parts searched separately",
    remove: "Remove",
    start: "Start assessment",
    edit: "Change topic",
    start_without: "Start without a preview",
    previewing: "Reading the topic…",
    unresolved: "No technology or research subject could be identified in this description. "
      + "Name the technology, for example “sodium-ion batteries for grid storage”.",
    unavailable: "The search preview is unavailable ({reason}). You can start anyway; the run will choose its own search terms.",
    limit: "Today's search previews are used up. You can start anyway; the run will choose its own search terms.",
    no_answer: "The model did not answer, so the search could not be previewed. "
      + "You can start anyway; the run will choose its own search terms.",
    no_answer_own: "Your model did not answer, so the search could not be previewed. "
      + "If your key or model name is wrong the run will fail too: check them under API keys. You can also start anyway.",
    too_short: "The search phrase needs at least 3 characters.",
  },
  "Simplified Chinese": {
    title: "开始前确认检索方向",
    lede: "系统将用以下检索词查找论文、专利和市场资料。如果理解有误，可以直接修改；这一步不占用每日运行次数。",
    lede_own: "系统将用以下检索词查找论文、专利和市场资料。如果理解有误，可以直接修改。这一步用你的模型密钥发了一次很小的请求。",
    lede_funded: "系统将用以下检索词查找论文、专利和市场资料。如果理解有误，可以直接修改。这一步的费用由本站承担，没有使用你的密钥，也不占用每日运行次数。",
    search_topic: "检索词",
    aliases: "同时检索",
    components: "分别检索的组成部分",
    remove: "移除",
    start: "开始评估",
    edit: "修改题目",
    start_without: "跳过预览直接开始",
    previewing: "正在理解题目…",
    unresolved: "没能从描述中识别出可评估的技术或研究对象。请写明具体技术，例如“钠离子电池用于电网储能”。",
    unavailable: "检索方向预览暂不可用（{reason}）。可以直接开始，由系统自动确定检索词。",
    limit: "今天的检索预览次数已用完。可以直接开始，由系统自动确定检索词。",
    no_answer: "模型没有应答，无法预览检索方向。可以直接开始，由系统自动确定检索词。",
    no_answer_own: "你的模型没有应答，无法预览检索方向。如果密钥或模型名称有误，运行同样会失败：请在“API Key”里检查。也可以直接开始。",
    too_short: "检索词至少需要 3 个字符。",
  },
};

export function planLabel(key) {
  return (PLAN_STRINGS[uiLanguage()] ?? PLAN_STRINGS.English)[key] ?? PLAN_STRINGS.English[key];
}

// Short stage names for the one-line timing summary; the stage list keeps the
// long ones from i18n.js.
const STAGE_SHORT_LABELS = {
  English: { sources: "Sources", evidence: "Evidence", report: "Report", review: "Review", scoring: "Scoring" },
  "Simplified Chinese": { sources: "来源", evidence: "证据分析", report: "报告撰写", review: "审查", scoring: "评分" },
};

/** "Sources 0:40 · Evidence 1:00 · Report 0:25…" from stage_timings; "" without any. */
export function timingSummary(timings, recovery = null) {
  const labels = STAGE_SHORT_LABELS[uiLanguage()] ?? STAGE_SHORT_LABELS.English;
  // `recovery` puts a resume's seconds under the step it ran (stageSeconds).
  const seconds = stageSeconds(timings, recovery);
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
/* Why a run stopped, in the reader's language.
 *
 * The fallback in English is the API's own allowlisted sentence. A saved
 * academic shortfall supplies the counts for a more specific reason. For
 * another language the API's `error_code` names the cause and `funded_by`
 * says who can act on it, and this table words the pair. A code this table
 * does not know, or a reply without one, keeps the API's sentence rather
 * than a guess; tests/test_failure_reasons.py keeps the table complete.
 *
 * Three readers, as in api/runs.py: `deployment` is a run under an access
 * code, whose reader cannot change the model or the key; `own_keys` is an
 * account's run, whose reader is the only one who can.
 */
const FAILURE_STRINGS = {
  "Simplified Chinese": {
    cancelled: "已按请求取消。",
    provider_empty_answer: "模型在某一步连续三次没有返回任何文字，分析无法完成。请重试，或换一个模型。",
    "provider_empty_answer:own_keys": "你填写的模型在某一步连续三次没有返回任何文字。请重新开始，或在“API Key”里换一个模型。",
    provider_output_limit: "模型没写完回答就到了输出上限，分析无法完成。请换用输出上限更大的模型后重试。",
    "provider_output_limit:deployment": "本站所用的模型没写完回答就到了输出上限。这不是你的请求造成的；运营者可以凭运行 ID 查到原因。",
    "provider_output_limit:own_keys": "你填写的模型没写完回答就到了输出上限。请在“API Key”里换一个输出上限更大的模型，然后重新开始。",
    timeout: "分析超出了时间限制。请缩小主题范围后重试。",
    timeout_resumable: "分析超出了时间限制。可以从最近一个已校验的检查点续跑，或重新开始一次运行。",
    provider_auth: "上游服务商拒绝了身份验证。请检查已配置的凭据。",
    "provider_auth:deployment": "本站的模型服务商拒绝了本站的凭据。这不是你的请求造成的；运营者可以凭运行 ID 查到原因。",
    "provider_auth:own_keys": "有一个服务商拒绝了你的密钥。请在“API Key”里检查模型密钥和检索密钥，然后重新开始。",
    provider_free_quota: "所配置模型的免费额度已用完。请换一个模型或开通付费后重试。",
    "provider_free_quota:deployment": "本站所用模型的免费额度已用完。这不是你的请求造成的；运营者可以凭运行 ID 查到原因。",
    "provider_free_quota:own_keys": "你填写的模型的免费额度已用完。请在“API Key”里换一个模型，或在服务商处开通付费，然后重新开始。",
    provider_billing: "模型服务商账户无法扣费。请检查余额后重试。",
    "provider_billing:deployment": "本站的模型服务商账户无法扣费。这不是你的请求造成的；运营者可以凭运行 ID 查到原因。",
    "provider_billing:own_keys": "你的模型服务商账户无法扣费。请在服务商处检查余额，然后重新开始。",
    provider_model_unavailable: "所配置的模型对本站的密钥不可用。请检查模型设置。",
    "provider_model_unavailable:deployment": "本站设置的模型对它的密钥不可用。这不是你的请求造成的；运营者可以凭运行 ID 查到原因。",
    "provider_model_unavailable:own_keys": "你的密钥不能使用你填写的模型。请在“API Key”里检查模型名称，然后重新开始。",
    provider_request_rejected: "所配置的模型拒绝了请求。请确认模型设置填写的是本流程支持的模型。",
    "provider_request_rejected:deployment": "本站设置的模型拒绝了请求。这不是你的请求造成的；运营者可以凭运行 ID 查到原因。",
    "provider_request_rejected:own_keys": "你填写的模型拒绝了请求。请在“API Key”里换成支持 JSON 输出的模型，然后重新开始。",
    provider_rate_limited: "上游服务商的速率或额度限制已触发。请稍后重试。",
    "provider_rate_limited:own_keys": "你的某个服务商触发了速率或额度限制。请稍后重试，或在服务商处检查额度。",
    insufficient_evidence: "系统未能为这个主题收集到足够的已校验证据。请稍后重试或调整主题。",
    provider_response_format: "模型的回答没有按要求的格式返回（需要结构化的 JSON），无法读取。",
    "provider_response_format:own_keys": "你填写的模型的回答没有按要求的格式返回（需要结构化的 JSON），无法读取。如果再次出现，请在“API Key”里换一个模型。",
    quality_checks: "模型的回答没有按要求的格式返回，因此没有通过分析的检查。",
    "quality_checks:own_keys": "你填写的模型的回答没有按要求的格式返回，因此没有通过分析的检查。如果再次出现，请在“API Key”里换一个模型。",
    provider_unreachable: "无法连接上游服务。请稍后重试。",
    unknown: "分析失败。请重试，或把运行 ID 发给运营者。",
  },
};

/** The sentence to show for why a run stopped; "" when there is nothing to say. */
export function failureText({ state, error, error_code, funded_by, retrieval_shortfall, artifacts } = {}) {
  const table = FAILURE_STRINGS[uiLanguage()];
  const localized = table?.[`${error_code}:${funded_by}`] ?? table?.[error_code];
  const reason = typeof localized === "string" ? localized : typeof error === "string" ? error : "";
  if (state !== "failed" || error_code !== "insufficient_evidence") return reason;

  const { stage, accepted_sources: accepted, required_sources: required } = retrieval_shortfall ?? {};
  const hasCounts = (stage === "academic_validation" || stage === "academic_relevance_filter")
    && Number.isSafeInteger(accepted) && Number.isSafeInteger(required) && accepted >= 0 && accepted < required;
  const sentences = [hasCounts
    ? headerLabel(stage === "academic_validation" ? "shortage_validation" : "shortage_relevance")
      .replace("{accepted}", accepted).replace("{required}", required)
    : reason];
  if (Array.isArray(artifacts) && !artifacts.includes("report") && !artifacts.includes("draft")) {
    sentences.push(headerLabel(hasCounts ? "shortage_before_report" : "shortage_no_report"));
  }
  return sentences.filter(Boolean).join(uiLanguage() === "Simplified Chinese" ? "" : " ");
}

/* What to do next, cause by cause: the page's one table for it.
 *
 * A run on the live site (2026-11-15) failed at the evidence step on an OCR
 * model, and the page's one prominent button was "Resume from checkpoint":
 * the same step, on the same model, for another of the day's runs. Which
 * action is the main one depends on the cause, and on whose keys paid.
 *
 * Each row: the main action for a reader whose own keys paid, then for anyone
 * else. `keys` opens the key form (the model can be changed there alone),
 * `resume` continues from the checkpoint, `again` is the same topic as a new
 * run, and null is nothing the reader can do: the deployment's model and key
 * are the operator's. The cause's code is the API's (api/runs.py) and is not
 * decided here; a code this table does not know is read as `unknown`.
 * tests/test_failure_next_steps.py holds a row for every code the API names. */
export const FAILURE_NEXT = {
  quality_checks: ["resume", "resume"],
  provider_response_format: ["resume", "resume"],
  provider_empty_answer: ["resume", "resume"],
  provider_auth: ["keys", null],
  provider_billing: ["keys", null],
  provider_free_quota: ["keys", null],
  provider_model_unavailable: ["keys", null],
  provider_request_rejected: ["keys", null],
  provider_output_limit: ["keys", null],
  provider_rate_limited: ["resume", "resume"],
  provider_unreachable: ["resume", "resume"],
  insufficient_evidence: ["again", "again"],
  timeout: ["again", "again"],
  timeout_resumable: ["resume", "resume"],
  cancelled: ["resume", "resume"],
  unknown: ["resume", "resume"],
};
// Where the key form is the main action because a key is the trouble, not the model.
const KEY_CAUSES = new Set(["provider_auth", "provider_billing"]);
// The causes a model that cannot do the step produces: its answers fail the checks or cannot be read.
const MODEL_CAUSES = new Set(["quality_checks", "provider_response_format"]);

/* An evidence answer shorter than this, from every analyst that answered,
 * is not one a model that can do the step writes. Measured on outputs/
 * (2026-11-16): over the 269 saved runs with all three analysts on record,
 * no analyst averaged under 643 completion tokens a request, failures
 * included; the run that prompted this averaged 250 to 300. */
export const SHORT_EVIDENCE_ANSWER = 500;
// The crew's own names for the three (config/agents.yaml), each followed there by the topic.
export const EVIDENCE_ROLES = ["Academic Literature Analyst", "Patent Landscape Analyst", "Market and Competitive Intelligence Analyst"];

/** Whether every evidence analyst answered far shorter than any saved run; null where the usage does not say. */
export function shortEvidenceAnswers(usage) {
  const agents = Array.isArray(usage?.agents) ? usage.agents : [];
  const averages = [];
  for (const name of EVIDENCE_ROLES) {
    const agent = agents.find((row) => typeof row?.role === "string" && row.role.trim().startsWith(name));
    const requests = Number(agent?.requests);
    const written = Number(agent?.completion_tokens);
    if (!agent || !(requests > 0) || !Number.isFinite(written)) return null;
    averages.push(written / requests);
  }
  return averages.every((average) => average < SHORT_EVIDENCE_ANSWER);
}

/**
 * What a run that did not finish offers first, and what its record suggests.
 *
 * `primary` is "keys", "resume", "again" or null; `keys` says which the key
 * form is opened for ("model" or "keys"); `suspect` is "kind" when the
 * model's name says it is another kind of model (`otherKind`, the caller's
 * reading of the name), "short" when its evidence answers were far shorter
 * than any saved run's, and `advice` is the sentence for either. The model
 * is a suspect only for the causes such a model produces, and only to the
 * reader who can change it. null for a run that is not over or that finished.
 */
export function failureGuide({
  state, error_code, funded_by, usage, model, otherKind = false, resumable = false, canModify = true,
} = {}) {
  if (!["failed", "timeout", "cancelled"].includes(state)) return null;
  const nothing = { primary: null, keys: null, suspect: null, advice: "" };
  if (!canModify) return nothing;
  const code = state === "cancelled" ? "cancelled"
    : Object.hasOwn(FAILURE_NEXT, error_code ?? "") ? error_code : "unknown";
  const own = funded_by === "own_keys";
  let primary = FAILURE_NEXT[code][own ? 0 : 1];
  let suspect = null;
  if (own && MODEL_CAUSES.has(code)) {
    suspect = otherKind ? "kind" : shortEvidenceAnswers(usage) === true ? "short" : null;
    if (suspect) primary = "keys";
  }
  if (primary === "resume" && !resumable) primary = "again";
  const advice = suspect
    ? headerLabel(suspect === "kind" ? "advice_model_kind" : "advice_model_short")
      .replace("{model}", () => model || "?").replace("{limit}", () => String(SHORT_EVIDENCE_ANSWER))
    : "";
  return { primary, keys: primary === "keys" ? (KEY_CAUSES.has(code) ? "keys" : "model") : null, suspect, advice };
}

/* Where a resumed run starts again: the first of these whose nodes are not
 * all saved. The node names are the checkpoints' own
 * (checkpoint_runtime.TASK_NODES), and the steps are the stages above, one
 * for one, so this note and the resumed run's own "Run here" line name the
 * same step; a test holds all three together. The reviewer and the scorer
 * were one step until 2026-11-20, when a run that failed in scoring with its
 * reviewer saved was said to start again "at the review and scoring" and its
 * resume ran the scoring alone. */
export const RESUME_STEPS = [
  { stage: "evidence", label: "resume_step_evidence", nodes: ["academic", "patent", "market"] },
  { stage: "report", label: "resume_step_writing", nodes: ["writer"] },
  { stage: "review", label: "resume_step_review", nodes: ["reviewer"] },
  { stage: "scoring", label: "resume_step_scoring", nodes: ["scorer"] },
];

/** The step a resume from these saved checkpoints starts at (the last one when all are saved). */
export function resumeStep(committed) {
  const saved = Array.isArray(committed) ? committed : [];
  return RESUME_STEPS.find((step) => !step.nodes.every((node) => saved.includes(node))) ?? RESUME_STEPS.at(-1);
}

/**
 * Beside "Resume from checkpoint": what it costs, where it starts, on which model.
 *
 * `quota` is whether this reader has a daily allowance at all; `model` is
 * what a resume would run on now and `ranOn` what this run used. A part the
 * page does not know is left out, never guessed. "" when nothing was saved
 * to resume from.
 */
export function resumeNote({ committed, quota = false, model = null, ranOn = null } = {}) {
  if (!Array.isArray(committed) || !committed.includes("retrieval")) return "";
  const next = resumeStep(committed);
  const parts = [];
  if (quota) parts.push(headerLabel("resume_note_quota"));
  parts.push(headerLabel(quota ? "resume_note_step" : "resume_note_step_first").replace("{step}", () => headerLabel(next.label)));
  if (model) {
    parts.push(headerLabel(ranOn && ranOn !== model ? "resume_note_model_changed" : "resume_note_model")
      .replace("{model}", () => model).replace("{ranOn}", () => ranOn ?? ""));
  }
  return parts.join(uiLanguage() === "Simplified Chinese" ? "" : " ");
}

/** The model a run's steps asked for, as its usage records it; null when it records none. */
export function runModel(usage) {
  const agents = Array.isArray(usage?.agents) ? usage.agents : [];
  const named = agents.find((row) => typeof row?.model === "string" && row.model);
  return named ? named.model : null;
}

/**
 * Why a run ended, and whether it spent one of today's runs; "" otherwise.
 *
 * A toast with the reason disappears, and a run opened from the list later
 * never had one. This line stays with the run. The quota sentence comes
 * only from the API's launch-time record: an old run without one, or a
 * damaged one, gets the reason alone rather than a guess.
 */
export function outcomeSummary(progress = {}) {
  const { state, daily_charge, daily_charge_reason } = progress;
  if (!["failed", "timeout", "cancelled"].includes(state)) return "";
  const parts = [];
  const reason = failureText(progress);
  if (reason) parts.push(reason);
  if (daily_charge === "charged") {
    // What resuming would cost is said beside the button that does it (resumeNote).
    parts.push(headerLabel("outcome_charged"));
  } else if (daily_charge === "refunded") {
    // A refund recorded before reasons were keeps the sentence it always had.
    parts.push(headerLabel(daily_charge_reason === "provider_unreachable"
      ? "outcome_refunded_unreachable" : "outcome_refunded"));
  } else if (daily_charge === "not_charged") {
    parts.push(headerLabel("outcome_not_charged"));
  }
  return parts.join(" ");
}

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

/** Whether a run simply finished: completed, by the worker's own record, with nothing else to tell.
 *  Only then may the header fold the terminal reason away; every other
 *  ending, and a record that is missing or unreadable, stays in sight. */
/* Whether the worker's word for how a run ended belongs under "Technical
 * details". It does when it says what the state already says: a failed run
 * whose worker raised, a cancelled one the user stopped, a timeout the clock
 * ended, a completion. "worker failed" stood in the header of every failed
 * run, beside a pill that reads FAILED and a line that says why. Anything
 * else stays in the line: a record that is missing or unreadable, a reason
 * this page does not know, or one that disagrees with the state. */
const ORDINARY_ENDINGS = {
  completed: "worker_completed", failed: "worker_exception", cancelled: "user_cancelled", timeout: "hard_timeout",
};
export function isOrdinaryEnding(terminal, state = "") {
  return Boolean(terminal) && terminal.record_state !== "unreadable"
    && Object.hasOwn(ORDINARY_ENDINGS, state) && terminal.reason_code === ORDINARY_ENDINGS[state];
}

export function isPlainCompletion(terminal, state = "") {
  return state === "completed" && Boolean(terminal) && terminal.record_state !== "unreadable"
    && terminal.reason_code === "worker_completed";
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
    if (stage.state === "reused") {
      // In place of a time: the stage was the earlier run's, not done here.
      const note = document.createElement("span");
      note.className = "stage__meta stage__meta--reused";
      note.textContent = headerLabel("stage_reused");
      row.append(note);
    } else if (stage.seconds != null) {
      const time = document.createElement("span");
      time.className = "stage__meta";
      time.textContent = formatDuration(stage.seconds);
      row.append(time);
    }
    list.append(row);
  }
  container.append(list);
}
