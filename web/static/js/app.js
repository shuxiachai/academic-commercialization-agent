/* Application shell: view state, routing, and event wiring. */

import * as api from "./api.js";
import * as runView from "./run.js";
import * as sidebar from "./sidebar.js";
import * as result from "./result.js";
import * as i18n from "./i18n.js";
import { needsScopeWarning } from "./topic.js";
const t = i18n.t;

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/* One follower at a time. Navigating away from a run must stop its poll loop,
 * or every visited run keeps polling for the life of the page. */
let follower = null;
let activeRunId = null;

/* Capacity polling state. Declared here with the other module state rather
 * than beside the scheduler at the bottom: showRun/showCompose re-time the
 * poll and are defined far above it, so leaving these in the boot section
 * made correctness depend on nothing calling those before the module body
 * finished — true today, and not a property worth relying on. */
const CAPACITY_INTERVAL_ACTIVE = 1000;
const CAPACITY_INTERVAL_IDLE = 10000;
let capacityTimer = null;

/* ── Toasts ────────────────────────────────────────────────────────── */

function toast(message, variant = "") {
  const el = document.createElement("div");
  el.className = `toast${variant ? ` toast--${variant}` : ""}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 4600);
}

/* ── Views ─────────────────────────────────────────────────────────── */

function stopFollowing() {
  follower?.stop();
  follower = null;
  stopClock();
}

function showCompose() {
  stopFollowing();
  activeRunId = null;
  $("#pane-compose").hidden = false;
  $("#pane-run").hidden = true;
  history.pushState({}, "", "/");
  refreshSidebar();
  // Re-time capacity polling: the pending timer was scheduled for whichever
  // state we just left, so without this a run starting waits out the idle
  // delay before the display starts tracking it.
  scheduleCapacity();
  $("#topic").focus();
}

function showRun(runId) {
  activeRunId = runId;
  $("#pane-compose").hidden = true;
  $("#pane-run").hidden = false;
  refreshSidebar();
  scheduleCapacity();
}

/* ── Run pane ──────────────────────────────────────────────────────── */

/* The clock ticks locally rather than on poll responses.
 *
 * Elapsed time arrives with each poll, and the poll interval widens to four
 * seconds once a run settles in — so a clock painted only from responses
 * visibly jumped four seconds at a time. Each response re-anchors the local
 * clock instead, which keeps it accurate without tying it to network timing. */
let clock = null;

function stopClock() {
  if (clock) clearInterval(clock);
  clock = null;
}

function startClock(fromSeconds) {
  stopClock();
  const anchor = Date.now();
  const paint = () => {
    const secs = fromSeconds + Math.floor((Date.now() - anchor) / 1000);
    $("#run-elapsed").textContent = runView.formatDuration(secs);
  };
  paint();
  clock = setInterval(paint, 1000);
}

function paintHeader({
  topic, state, elapsed_seconds, source_counts, usage, usage_accounting,
  terminal, status_record_state, checkpointing, recovery, runtime_metadata_unreadable,
}) {
  if (topic) $("#run-title").textContent = topic;

  const pill = $("#run-pill");
  pill.className = `pill pill--${state}`;
  pill.textContent = state;

  if (state === "running") {
    startClock(elapsed_seconds ?? 0);
  } else {
    stopClock();
    $("#run-elapsed").textContent = runView.formatDuration(elapsed_seconds);
  }

  const summary = runView.sourceSummary(source_counts);
  const el = $("#run-sources");
  el.textContent = summary ? `· ${summary}` : "";

  // Shown for failed runs too: a run that died halfway still spent whatever
  // it spent, and that is the bill nobody can otherwise estimate.
  const spend = runView.usageSummary(usage, usage_accounting);
  const spendEl = $("#run-usage");
  spendEl.textContent = spend ? `· ${spend}` : "";
  spendEl.title = spend ? runView.usageTitle(usage, usage_accounting) : "";

  // State alone cannot distinguish a worker failure from a watchdog stop, and
  // a missing/unreadable terminal record must not look like an ordinary clean
  // finish.  Consume the same projection returned by both public endpoints so
  // the last API-to-browser seam preserves the process reason as well.
  const terminalEl = $("#run-terminal");
  const terminalSummary = runView.terminalSummary(terminal, state);
  terminalEl.textContent = terminalSummary ? `· ${terminalSummary}` : "";
  terminalEl.title = runView.terminalTitle(terminal, state);

  // Terminal success is still usable when its live projection is damaged,
  // but missing audit fields must not silently masquerade as a clean read.
  const statusRecordEl = $("#run-status-record");
  statusRecordEl.textContent = status_record_state === "unreadable"
    ? `· ${t("status_record_unreadable")}` : "";

  const runtimeFault = runView.runtimeMetadataSummary(runtime_metadata_unreadable ?? []);
  $("#run-runtime-record").textContent = runtimeFault ? `· ${runtimeFault}` : "";

  const recoveryEl = $("#run-recovery");
  const reused = recovery?.reused_nodes?.length ?? 0;
  const badges = [];
  const details = [];
  if (recovery?.state === "reused" && reused > 0) {
    badges.push(t("recovery_reused_short").replace("{count}", String(reused)));
    if (recovery.source_run_id) details.push(recovery.source_run_id);
  }
  // Reuse and a failed child-side checkpoint write can coexist. Showing only
  // the cache hit would turn degraded recoverability into an apparent pass.
  if (checkpointing?.state === "degraded") {
    badges.push(t("recovery_degraded_short"));
    details.push(...(checkpointing.errors ?? []));
  }
  recoveryEl.textContent = badges.length ? `· ${badges.join(" · ")}` : "";
  recoveryEl.title = details.join("\n");
}

function paintActions(state, checkpointing = null) {
  const actions = $("#run-actions");
  actions.innerHTML = "";

  if (state === "running") {
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "btn btn--danger";
    cancel.textContent = t("cancel");
    cancel.addEventListener("click", async () => {
      cancel.disabled = true;
      try {
        await api.cancelRun(activeRunId);
        toast(t("msg_cancelled"));
      } catch (err) {
        cancel.disabled = false;
        toast(err.message, "error");
      }
    });
    actions.append(cancel);
    return;
  }

  // Not another "New analysis" — that button already lives in the rail, one
  // click away and always visible. A finished run needs a way out of the
  // browser instead.
  if (state === "completed") {
    const icon = `
      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path d="M8 2.5v8m0 0L4.5 7M8 10.5L11.5 7M3 12.5v.5a1 1 0 001 1h8a1 1 0 001-1v-.5"
              stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>`;

    // Markdown first: it is instant, while the PDF renders on first request.
    for (const [suffix, path, label] of [
      ["md", "report", "Markdown"],
      ["pdf", "report.pdf", "PDF"],
    ]) {
      const link = document.createElement("a");
      link.className = "btn btn--secondary";
      link.href = `/api/runs/${activeRunId}/${path}`;
      link.download = `${activeRunId}.${suffix}`;
      link.innerHTML = icon;
      link.append(label);
      actions.append(link);
    }
  }

  const canResume = (
    new Set(["failed", "cancelled", "timeout"]).has(state)
    && checkpointing?.committed_nodes?.includes("retrieval")
  );
  if (canResume) {
    const sourceRunId = activeRunId;
    const resume = document.createElement("button");
    resume.type = "button";
    resume.className = "btn btn--secondary";
    resume.textContent = t("resume");
    resume.addEventListener("click", async () => {
      resume.disabled = true;
      try {
        const accepted = await api.resumeRun(sourceRunId);
        if (byokMode) api.addByokRun(accepted.run_id, accepted.topic);
        toast(t("msg_resumed"), "success");
        openRun(accepted.run_id, { known: accepted });
      } catch (err) {
        resume.disabled = false;
        toast(err.message, "error");
      }
    });
    actions.append(resume);
  }

  // Every terminal state — completed, failed, cancelled, timeout — can be
  // permanently removed; only a still-running one (handled above, which
  // already returned) cannot.
  const del = document.createElement("button");
  del.type = "button";
  del.className = "btn btn--danger";
  del.textContent = t("delete_run");
  del.addEventListener("click", () => handleDeleteRun(activeRunId, $("#run-title").textContent));
  actions.append(del);
}

async function openRun(runId, { known } = {}) {
  stopFollowing();
  showRun(runId);

  const body = $("#run-body");
  body.innerHTML = "";
  paintHeader({ topic: known?.topic ?? "…", state: known?.state ?? "running" });
  paintActions(known?.state ?? "running", known?.checkpointing);
  history.pushState({}, "", `/run/${runId}`);

  follower = runView.follow(runId, {
    onUpdate(progress) {
      paintHeader(progress);
      paintActions(progress.state, progress.checkpointing);
      runView.renderStages(body, runView.stageStates(progress.stage, progress.state));
    },
    onDone(progress) {
      paintHeader(progress);
      paintActions(progress.state, progress.checkpointing);
      runView.renderStages(body, runView.stageStates(progress.stage, progress.state));
      refreshSidebar();

      if (progress.state === "completed") {
        toast(t("msg_complete"), "success");
      } else if (progress.error) {
        toast(progress.error, "error");
      }

      // A failed run keeps its stage list and may now expose a retrieval
      // diagnostic artifact. Where it stopped and what the search rejected
      // are both useful even though no report was produced.
      // The whole progress payload, not just the artifact list. The automated
      // checks it carries — consistency, claim grounding, failed domains, a
      // truncated audit trail — all qualify the score, and passing only the
      // artifact names is how they stayed invisible while being computed,
      // stored and returned on every run.
      if (progress.artifacts.length) {
        result.render(body, runId, progress);
      }
    },
    onError(err) {
      toast(err.message, "error");
    },
  });
}

/* ── Sidebar ───────────────────────────────────────────────────────── */

// Run ids built with create_run_id() start with a UTC timestamp — parsed
// back out client-side so the BYOK sidebar can group "Today"/"Yesterday"
// the same way sidebar.js already does for the server-backed list, with no
// server round trip needed just to learn when a run the visitor just
// submitted was started.
function _startedAtFromRunId(runId) {
  const m = runId.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z-/);
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z` : "";
}

async function handleDeleteRun(runId, topic) {
  if (!confirm(`${t("confirm_delete_run")}\n\n"${topic}"`)) return;
  try {
    await api.deleteRun(runId);
  } catch (err) {
    toast(err.message, "error");
    return;
  }
  // BYOK history is a client-only list (see api.getByokRuns) — the server
  // has no owner tag to have deleted anything from in the first place, so
  // this is the only place that ever learns the run is gone.
  if (byokMode) api.removeByokRun(runId);
  toast(t("msg_deleted"));
  // The follower already stopped polling once this run reached a terminal
  // state (see run.js follow()), so nothing else will notice it vanished —
  // navigate away explicitly rather than leaving a dead run open.
  if (runId === activeRunId) showCompose();
  else refreshSidebar();
}

async function refreshSidebar() {
  // GET /api/runs (the list) always stays behind the access code, scoped
  // server-side to that code's own runs (api/access.py owner_id). A BYOK
  // visitor has no code at all, so this builds the same view from the
  // session-only list of run ids api.addByokRun() has been recording —
  // gone once the tab closes, complete for as long as it's open.
  if (byokMode) {
    const list = $("#runlist");
    const entries = api.getByokRuns();
    if (!entries.length) {
      list.innerHTML = "";
      const note = document.createElement("div");
      note.className = "runlist__empty";
      note.textContent = t("byok_no_history");
      list.append(note);
      return null;
    }
    const runs = await Promise.all(entries.map(async ({ run_id, topic }) => {
      try {
        const status = await api.getRun(run_id);
        return {
          run_id, topic: status.topic || topic, state: status.state,
          started_at: _startedAtFromRunId(run_id),
        };
      } catch {
        // The run itself is still a capability URL even if this poll
        // failed transiently — keep it in the list rather than dropping it.
        return { run_id, topic, state: "failed", started_at: _startedAtFromRunId(run_id) };
      }
    }));
    sidebar.render(list, runs, {
      activeId: activeRunId,
      onSelect: (id) => openRun(id),
      onDelete: handleDeleteRun,
    });
    return runs;
  }
  return sidebar.refresh($("#runlist"), {
    activeId: activeRunId,
    onSelect: (runId) => openRun(runId),
    onDelete: handleDeleteRun,
  });
}

/* ── Composer ──────────────────────────────────────────────────────── */

/* True only while an extraction is in flight. Submission is blocked for that
 * window: attachedPaper is null until the response arrives, so a run started
 * mid-extraction would quietly go out without the paper the user attached.
 *
 * Declared here rather than beside the upload handler because syncComposer
 * reads it and runs first — a `let` further down is a temporal dead zone, and
 * the boot-time call threw before anything rendered. */
let extracting = false;

const topic = $("#topic");
const count = $("#topic-count");
const runBtn = $("#run-btn");
const composer = $("#composer");
const decisionContextInputs = $$('[data-context-field]');

function readDecisionContext() {
  const context = {};
  for (const input of decisionContextInputs) {
    const value = input.value.trim();
    if (value) context[input.dataset.contextField] = value;
  }
  // Null and an empty object must share one durable identity. Sending null
  // makes that boundary explicit to direct API clients and the browser alike.
  return Object.keys(context).length ? context : null;
}

function clearDecisionContext() {
  for (const input of decisionContextInputs) input.value = "";
}


function autosize() {
  topic.style.height = "auto";
  topic.style.height = `${topic.scrollHeight}px`;
}

function syncComposer() {
  runBtn.disabled = topic.value.trim().length < 3 || extracting;
  runBtn.title = extracting ? t("msg_wait_extract") : t("run_hint");
  count.textContent = topic.value.length > 240 ? `${topic.value.length} / 300` : "";
  autosize();
}

topic.addEventListener("input", syncComposer);
topic.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (!runBtn.disabled) $("#compose-form").requestSubmit();
  }
});

$$(".starter").forEach((btn) =>
  btn.addEventListener("click", () => {
    topic.value = btn.dataset.topic;
    topic.focus();
    syncComposer();
  })
);

$("#compose-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const submittedTopic = topic.value.trim();
  if (
    needsScopeWarning(submittedTopic, { hasPaper: Boolean(attachedPaper) })
    && !confirm(t("confirm_broad_topic"))
  ) return;
  runBtn.disabled = true;

  try {
    const accepted = await api.startRun({
      topic: submittedTopic,
      language: $("#language").value,
      weight_profile: $("#profile").value,
      paper_id: attachedPaper?.paper_id,
      decision_context: readDecisionContext(),
    });
    // BYOK runs get no server-side history (see api/access.py) — this is
    // the only place that ever learns the run happened, so the sidebar has
    // something to show for the rest of the session.
    if (byokMode) api.addByokRun(accepted.run_id, accepted.topic);
    topic.value = "";
    clearDecisionContext();
    clearAttachment();
    syncComposer();
    openRun(accepted.run_id, { known: accepted });
  } catch (err) {
    runBtn.disabled = false;
    // 429 is the expected answer when both slots are busy, and deserves a
    // sentence rather than a raw status.
    toast(err.status === 429
      ? t("msg_busy")
      : err.message, "error");
  }
});

/* ── Attachment ─────────────────────────────────────────────────────
 * An uploaded paper becomes source A1 and the pipeline searches around its
 * specific contribution. Extraction takes a few seconds and involves an LLM
 * call, so the control reports progress rather than appearing to hang. */

let attachedPaper = null;
const attachment = $("#attachment");
const attachBtn = $("#attach-btn");
const pdfInput = $("#pdf-input");

function clearAttachment() {
  attachedPaper = null;
  extracting = false;
  attachment.hidden = true;
  attachment.removeAttribute("data-loading");
  attachment.innerHTML = "";
  attachBtn.dataset.active = "false";
  pdfInput.value = "";      // so re-picking the same file still fires change
  syncComposer();
}

function paintAttachment(paper) {
  attachment.hidden = false;
  attachment.removeAttribute("data-loading");
  attachment.innerHTML = "";

  const title = document.createElement("span");
  title.style.flex = "1";
  title.style.minWidth = "0";
  title.style.overflow = "hidden";
  title.style.textOverflow = "ellipsis";
  title.style.whiteSpace = "nowrap";
  title.textContent = paper.title;
  title.title = paper.title;

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "icon-btn";
  remove.setAttribute("aria-label", "Remove paper");
  remove.textContent = "×";
  remove.addEventListener("click", clearAttachment);

  attachment.append(title, remove);
  attachBtn.dataset.active = "true";

  // The extracted topic is a better starting point than whatever the user
  // typed before attaching — but it stays editable, since the model's
  // reading of a paper is a proposal, not a verdict.
  if (paper.commercialization_topic && !topic.value.trim()) {
    topic.value = paper.commercialization_topic;
    syncComposer();
  }
}

async function uploadPaper(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    toast(t("msg_not_pdf"), "error");
    return;
  }

  extracting = true;
  attachment.hidden = false;
  attachment.dataset.loading = "true";
  attachment.innerHTML = "";
  const dot = document.createElement("span");
  dot.className = "attachment__dot";
  const label = document.createElement("span");
  label.textContent = `${t("msg_reading")} ${file.name}…`;
  attachment.append(dot, label);
  attachBtn.dataset.active = "true";
  syncComposer();

  try {
    const paper = await api.uploadPaper(file);
    attachedPaper = paper;
    extracting = false;
    paintAttachment(paper);
    toast(t("msg_paper_attached"), "success");
  } catch (err) {
    clearAttachment();
    toast(err.status === 413
      ? t("msg_too_large")
      : err.message, "error");
  }
}

attachBtn.addEventListener("click", () => {
  if (attachedPaper) clearAttachment();
  else pdfInput.click();
});

pdfInput.addEventListener("change", () => uploadPaper(pdfInput.files?.[0]));

["dragenter", "dragover"].forEach((evt) =>
  composer.addEventListener(evt, (e) => {
    e.preventDefault();
    composer.dataset.dragging = "true";
  })
);
["dragleave", "drop"].forEach((evt) =>
  composer.addEventListener(evt, (e) => {
    e.preventDefault();
    composer.dataset.dragging = "false";
    if (evt === "drop") uploadPaper(e.dataTransfer?.files?.[0]);
  })
);

/* ── Sidebar chrome ────────────────────────────────────────────────── */

const workbench = $("#workbench");
const NARROW = window.matchMedia("(max-width: 860px)");

$("#collapse-btn").addEventListener("click", () => {
  if (NARROW.matches) {
    workbench.dataset.sidebarOpen = String(workbench.dataset.sidebarOpen !== "true");
  } else {
    const next = workbench.dataset.collapsed !== "true";
    workbench.dataset.collapsed = String(next);
    localStorage.setItem("sidebar-collapsed", String(next));
  }
});

if (localStorage.getItem("sidebar-collapsed") === "true" && !NARROW.matches) {
  workbench.dataset.collapsed = "true";
}

$("#new-run-btn").addEventListener("click", showCompose);

/* ── Keyboard ──────────────────────────────────────────────────────── */

document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
  if (e.key === "n" && !typing && !e.metaKey && !e.ctrlKey) {
    e.preventDefault();
    showCompose();
  }
});

/* ── Capacity ──────────────────────────────────────────────────────── */

async function refreshCapacity() {
  try {
    const {
      active_runs,
      active_paid_operations = active_runs,
      max_concurrent,
      retention_days,
    } = await api.health();
    const dots = $("#capacity-dots");
    dots.innerHTML = "";
    for (let i = 0; i < max_concurrent; i += 1) {
      const dot = document.createElement("span");
      dot.className = "capacity__dot";
      dot.dataset.busy = String(i < active_paid_operations);
      dots.append(dot);
    }
    $("#capacity-label").textContent =
      `${active_paid_operations}/${max_concurrent} ${t("running_label")}`;
    // Someone who uploads an unpublished paper is entitled to know how long it
    // stays here — and a deletion nobody was told about reads as data loss
    // rather than as policy. Shown on the capacity line rather than in a
    // dialog because it is a standing fact about the deployment, not an event.
    $("#capacity-label").title = retention_days
      ? t("retention_note").replace("{days}", retention_days)
      : t("retention_forever");
  } catch {
    $("#capacity-label").textContent = t("offline");
  }
}

/* ── Access gate ───────────────────────────────────────────────────────
 * Only deployments with ACCESS_CODE set (see api/access.py) ever show this —
 * elsewhere the boot-time check comes back ok with no header at all, and the
 * gate never becomes visible. Blocks routing/sidebar/capacity, all of which
 * hit endpoints the gate would otherwise reject anyway.
 *
 * Two ways through: the operator's access code, or a visitor's own LLM +
 * Serper keys (POST /api/runs accepts either — see api/access.py
 * authorizes_run). The second path is never verified up front — there is no
 * cheap way to check a BYOK key without spending a real call — so a bad key
 * only surfaces once a run actually fails, with the provider's own error. */

let byokMode = false;

function applyByokMode() {
  byokMode = true;
  api.setAccessCode(null);
  $("#byok-badge").hidden = false;
}

$("#byok-exit").addEventListener("click", () => {
  api.setByok(null);
  location.reload();
});

// Mutually exclusive with applyByokMode(): shown only when a stored code is
// what got the visitor past the gate, never when the gate is off entirely
// (nothing to log out of then) and never alongside the BYOK badge.
function applyCodeMode() {
  $("#code-badge").hidden = false;
}

$("#code-exit").addEventListener("click", () => {
  api.setAccessCode(null);
  location.reload();
});

async function ensureAccess() {
  if (api.getByok()) {
    applyByokMode();
    return;
  }
  try {
    await api.checkAccess(api.getAccessCode());
    if (api.getAccessCode()) applyCodeMode();
    return;
  } catch (err) {
    if (err.status !== 401) throw err;
  }
  await showGate();
}

/* How long the deployment keeps what a visitor is about to hand it.
 *
 * The line above this one is about the API keys and is true of them. Someone
 * about to upload an unpublished paper reads it as covering everything, and
 * the assessment and the PDF do stay on the server — so the retention window
 * is stated here, next to the form, rather than only in a tooltip on a
 * capacity indicator they have not reached yet.
 *
 * Silent on failure: /health is unauthenticated and this is the one moment the
 * gate is up, so an unreachable server must not leave a claim on screen that
 * nothing has confirmed. No line is better than a wrong one.
 */
async function showByokRetention() {
  const node = $("#byok-retention");
  if (!node || node.textContent) return;
  try {
    const { retention_days } = await api.health();
    node.textContent = retention_days
      ? t("byok_retention").replace("{days}", retention_days)
      : t("byok_retention_forever");
  } catch {
    node.textContent = "";
  }
}

function showGate() {
  const gate = $("#gate");
  const codeForm = $("#gate-form");
  const codeInput = $("#gate-input");
  const codeError = $("#gate-error");
  const codeSubmit = $("#gate-submit");
  const byokForm = $("#byok-form");

  gate.hidden = false;
  codeForm.hidden = false;
  byokForm.hidden = true;
  codeInput.focus();

  return new Promise((resolve) => {
    const finish = () => {
      gate.hidden = true;
      resolve();
    };

    $("#gate-to-byok").addEventListener("click", () => {
      codeForm.hidden = true;
      byokForm.hidden = false;
      $("#byok-llm-key").focus();
      showByokRetention();
    });
    $("#byok-to-gate").addEventListener("click", () => {
      byokForm.hidden = true;
      codeForm.hidden = false;
      codeInput.focus();
    });

    codeForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const code = codeInput.value.trim();
      if (!code) return;

      codeSubmit.disabled = true;
      codeError.hidden = true;
      try {
        await api.checkAccess(code);
        api.setAccessCode(code);
        applyCodeMode();
        finish();
      } catch (err) {
        codeError.textContent = err.status === 401 ? t("gate_error") : err.message;
        codeError.hidden = false;
        codeInput.select();
      } finally {
        codeSubmit.disabled = false;
      }
    });

    byokForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const provider = $("#byok-provider").value;
      const llmKey = $("#byok-llm-key").value.trim();
      const serperKey = $("#byok-serper-key").value.trim();
      if (!llmKey || !serperKey) return;

      api.setByok({ provider, llmKey, serperKey });
      applyByokMode();
      finish();
    });
  });
}

/* ── Routing ───────────────────────────────────────────────────────── */

function routeFromLocation() {
  const match = location.pathname.match(/^\/run\/([^/]+)$/);
  if (match) {
    openRun(match[1]);
  } else {
    $("#pane-compose").hidden = false;
    $("#pane-run").hidden = true;
    topic.focus();
  }
}

window.addEventListener("popstate", routeFromLocation);

/* ── Boot ──────────────────────────────────────────────────────────── */

/* ── Language ──────────────────────────────────────────────────────── */

const langSelect = $("#ui-lang");
langSelect.value = i18n.language();
langSelect.addEventListener("change", () => {
  i18n.setLanguage(langSelect.value);
  topic.placeholder = t("topic_placeholder");
  // Re-render whatever is on screen so switching mid-run does not leave a
  // half-translated pane behind.
  refreshSidebar();
  if (activeRunId) openRun(activeRunId);
});

/* ── Boot ──────────────────────────────────────────────────────────── */

i18n.apply();
topic.placeholder = t("topic_placeholder");
syncComposer();

/* Capacity polling.
 *
 * A fixed 1s interval ran for as long as the tab existed, whether or not it
 * was visible and whether or not anything was running: a tab left open
 * overnight sent ~86k requests to say the deployment was idle, on a platform
 * that meters them.
 *
 * Two changes. It backs off to 10s when no run is active — capacity only
 * changes when someone starts or finishes a run, and this client knows when
 * it started one. And it stops entirely while the tab is hidden, resuming
 * with an immediate refresh so a returning user never reads a stale number.
 */
function scheduleCapacity() {
  if (capacityTimer) clearTimeout(capacityTimer);
  if (document.hidden) return;
  const delay = activeRunId ? CAPACITY_INTERVAL_ACTIVE : CAPACITY_INTERVAL_IDLE;
  capacityTimer = setTimeout(async () => {
    await refreshCapacity();
    scheduleCapacity();
  }, delay);
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    if (capacityTimer) clearTimeout(capacityTimer);
    capacityTimer = null;
  } else {
    refreshCapacity();
    scheduleCapacity();
  }
});

ensureAccess().then(() => {
  routeFromLocation();
  refreshSidebar();
  refreshCapacity();
  scheduleCapacity();
});
