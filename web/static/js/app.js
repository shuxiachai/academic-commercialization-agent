/* Application shell: view state, routing, and event wiring. */

import * as api from "./api.js";
import * as runView from "./run.js";
import * as compareView from "./compare.js";
import * as sidebar from "./sidebar.js";
import * as result from "./result.js";
import * as i18n from "./i18n.js";
import { needsScopeWarning } from "./topic.js";
import { createPaidReceipts } from "./paid_receipts.js";
const t = i18n.t;

// For whoever is looking at a page that does not respond: "scripts" once
// this module runs, "ready" once the boot at the bottom has decided who the
// visitor is. A document without the attribute never ran this file. (The
// test harnesses' document has no element; they are not looking.)
const markBoot = (stage) => { if (document.documentElement) document.documentElement.dataset.boot = stage; };
markBoot("scripts");

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/* One follower at a time. Navigating away from a run must stop its poll loop,
 * or every visited run keeps polling for the life of the page. */
let follower = null;
let activeRunId = null;
// Requests from an old view/session cannot repaint the current identity's
// capability list. A generation also rejects older responses within one login.
let sidebarRevision = 0;

function invalidateSidebar() {
  sidebarRevision++;
  $("#runlist").innerHTML = "";
  // What one identity searched for, and how far it had paged, is not the
  // next identity's starting point.
  sidebar.resetView?.();
  const search = $("#run-search");
  search.value = "";
  search.hidden = true;
}
// Button elements are disposable (polling, language changes, navigation).
// Paid resume intent belongs to the parent run, not the element clicked.
// This is tab-local exclusion, not cross-tab/server/provider idempotency.
const pendingResumes = new Set();
const paidReceipts = createPaidReceipts();
let receiptViewGeneration = 0;
let receiptLookupActive = false;

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

function operationErrorMessage(err) {
  if (err.code === "invalid_byok") return t("invalid_byok");
  if (err.code === "byok_required") return t("msg_byok_required");
  if (err.code === "sign_in_required") return t("msg_sign_in_required");
  if (err.code === "email_unverified") return t("msg_email_unverified");
  if (err.code === "paid_ack_unknown") return t("msg_paid_ack_unknown");
  if (err.code === "paid_receipt_pending") return t("paid_receipt_unknown");
  const key = {
    concurrency_limit: "msg_busy",
    daily_quota_exceeded: "msg_daily_quota",
    account_busy: "msg_account_busy",
    account_daily_quota_exceeded: "msg_account_daily_quota",
    trial_daily_exhausted: "msg_trial_daily_exhausted",
    rate_limited: "msg_rate_limited",
    upload_capacity: "msg_upload_busy",
  }[err.code];
  // Unknown/legacy 429 responses retain the server's reason. Inferring a
  // capacity error from their status used to hide the daily UTC reset rule.
  return err.status === 429 && key ? t(key) : err.message;
}

function rememberAcceptedRun(accepted) {
  // An account's BYOK runs are tagged to it server-side; only a code-less
  // visitor's runs need the session-only list.
  if (!byokMode || accountMode) return;
  try {
    api.addByokRun(accepted.run_id, accepted.topic);
  } catch {
    // A 202 is already a paid acceptance. Optional sidebar storage must not
    // turn it into a failed submit or keep the user on a retryable composer.
    toast(t("msg_history_unavailable"), "error");
  }
}

/* Whether the deployment pays for this account's operations: an administrator
 * on a deployment that says so (sign-in configuration `admin_funded`). Keys
 * saved here are still sent and used first; without them the server runs the
 * operation on its own keys instead of refusing it. */
function operatorPays() {
  return accountMode && accountAdmin && authConfig?.admin_funded === true;
}

/* Whether this account's next assessment runs on its trial: a verified
 * account the server says still has one (`trial_runs_left`, which is 0 for
 * an administrator the deployment funds anyway). A new
 * assessment only; a resume or an upload asks for keys as before. The
 * server decides at the launch, so a count that is stale here costs a
 * refusal with byok_required, never a run nobody agreed to pay for. */
function trialPays() {
  return accountMode && accountVerified && accountTrialLeft > 0;
}

function paintTrialNote() {
  const note = $("#trial-note");
  if (!note) return;
  const show = trialPays() && !api.getByok();
  note.hidden = !show;
  note.textContent = show ? t("trial_note").replace("{n}", String(accountTrialLeft)) : "";
}

async function performPaidRequest(request, deliver, operation = "run") {
  if (accountMode && !accountVerified) { toast(t("msg_email_unverified"), "error"); return; }
  // An account pays with its own keys. Ask for them here, once, rather than
  // letting the server refuse with byok_required after the intent is recorded.
  if (accountMode && !api.getByok() && !operatorPays() && !(operation === "run" && trialPays())) {
    await showGate(null, { keysOnly: true });
    if (!api.getByok()) { toast(t("msg_byok_required"), "error"); return; }
  }
  // Decided before the request: whether this one, if accepted, spent a trial.
  const onTrial = operation === "run" && !api.getByok() && trialPays();
  // Validate locally before recording intent; invalid BYOK cannot cause a
  // request, select operator billing, or manufacture an uncertain receipt.
  api.getByok();
  const settle = paidReceipts.begin();
  let received = false;
  let receiptKey = null;
  try {
    receiptKey = api.beginReceipt(operation);
    // The warning subscribed before this identity existed. Publish the new
    // lookup/storage state before fetch; a stalled reply must not hide it.
    paintPaidReceipt();
    const response = await request(receiptKey);
    received = true;
    await deliver(response);
    // Parsing JSON is not delivery. Keep the marker until the run view or
    // extracted attachment actually receives the acknowledgement.
    api.forgetReceipt(receiptKey);
    settle(true);
    if (onTrial) {
      accountTrialLeft = Math.max(0, accountTrialLeft - 1);
      paintTrialNote();
    }
  } catch (err) {
    // A definite client rejection is a known outcome, not proof of no cost
    // (PDF validation may follow extraction). Transport/5xx/timeouts and UI
    // handoff faults remain uncertain, and never auto-retry the paid POST.
    const definite = !receiptKey || (!received && err.status >= 400 && err.status < 500
      && err.status !== 408 && !err.code?.includes("receipt"));
    if (definite && receiptKey) api.forgetReceipt(receiptKey);
    settle(definite);
    throw err;
  }
}

function requirePaidIdentity(response, field) {
  if (!response || typeof response[field] !== "string" || !response[field].trim()) {
    throw new api.ApiError(0, "Paid acknowledgement has no usable identity.", "paid_ack_unknown");
  }
}

/* ── Views ─────────────────────────────────────────────────────────── */

function stopFollowing() {
  follower?.stop();
  follower = null;
  stopClock();
}

// The locator only receives a run capability in its fragment. Keep this
// stricter than a path-shaped string so an untrusted display value cannot
// become a link target, and never place an access code or receipt key here.
// Logical view state stays authoritative even when optional history writes fail.
const locatorRunPattern = /^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}$(?![\s\S])/;
function syncSourceLocatorLink(runId = activeRunId) {
  const link = $("#source-locator-link");
  if (!link) return; // The default-off feature deliberately omits the link.
  link.href = `/source-locator${typeof runId === "string" && locatorRunPattern.test(runId) ? `#${runId}` : ""}`;
}

// The server injects an English label; follow the interface language.
function localizeSourceLocatorLink() {
  const link = $("#source-locator-link");
  if (!link) return;
  link.textContent = runView.headerLabel("source_locator");
  link.title = runView.headerLabel("source_locator_title");
}

function showCompose() {
  stopFollowing();
  activeRunId = null;
  syncSourceLocatorLink();
  $("#pane-compose").hidden = false;
  $("#pane-run").hidden = true;
  $("#pane-compare").hidden = true;
  try { history.pushState({}, "", "/"); }
  catch { toast(t("msg_history_unavailable"), "error"); }
  refreshSidebar();
  // Re-time capacity polling: the pending timer was scheduled for whichever
  // state we just left, so without this a run starting waits out the idle
  // delay before the display starts tracking it.
  scheduleCapacity();
  refreshQuota();
  $("#topic").focus();
}

function showRun(runId) {
  activeRunId = runId;
  syncSourceLocatorLink();
  $("#pane-compose").hidden = true;
  $("#pane-run").hidden = false;
  $("#pane-compare").hidden = true;
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
  topic, state, elapsed_seconds, source_counts, usage, usage_accounting, auxiliary_usage,
  terminal, status_record_state, checkpointing, recovery, runtime_metadata_unreadable, steps_read_state,
  stage_timings, eta, pipeline_revision, error, error_code, funded_by, daily_charge, daily_charge_reason,
}) {
  if (topic) $("#run-title").textContent = topic;

  const pill = $("#run-pill");
  pill.className = `pill pill--${state}`;
  pill.textContent = runView.stateLabel(state);

  if (state === "running") {
    startClock(elapsed_seconds ?? 0);
  } else {
    stopClock();
    $("#run-elapsed").textContent = runView.formatDuration(elapsed_seconds);
  }

  // A typical figure from recent runs, for a run still going.
  const etaText = state === "running" ? runView.etaSummary(eta) : "";
  $("#run-eta").textContent = etaText ? `· ${etaText}` : "";
  $("#run-eta").title = etaText ? runView.etaTitle(eta) : "";
  paintNotifyButton(state);

  const summary = runView.sourceSummary(source_counts);
  const el = $("#run-sources");
  el.textContent = summary ? `· ${summary}` : "";

  // Which model and which code: the deployment swaps models without notice,
  // so a report must say what produced it rather than leave the reader to
  // assume today's model. Both values ride on the status payload already.
  const identity = runView.identitySummary(usage, pipeline_revision);
  const identityEl = $("#run-identity");
  identityEl.textContent = identity ? `· ${identity}` : "";
  identityEl.title = identity ? runView.headerLabel("identity_title") : "";

  // Shown for failed runs too: a run that died halfway still spent whatever
  // it spent, and that is the bill nobody can otherwise estimate.
  const spend = runView.usageSummary(usage, usage_accounting);
  const spendEl = $("#run-usage");
  const auxiliary = runView.auxiliarySummary(auxiliary_usage);
  spendEl.textContent = [spend, auxiliary].filter(Boolean).join(" · ");
  spendEl.title = [runView.usageTitle(usage, usage_accounting), auxiliary].filter(Boolean).join("\n");
  // Folded, never dropped: the full accounting text with its caveats stays in
  // the DOM and one click away, while the header leads with the outcome.
  $("#run-usage-details").hidden = !spendEl.textContent;
  $("#run-usage-label").textContent = `· ${runView.headerLabel("usage_details")}`;

  // Where the time went, folded the same way. The stage list shows it while
  // the run is going; the finished view replaces that list.
  const timingEl = $("#run-timing");
  timingEl.textContent = runView.timingSummary(stage_timings);
  $("#run-timing-details").hidden = !timingEl.textContent;
  $("#run-timing-label").textContent = `· ${runView.headerLabel("stage_timing")}`;

  // State alone cannot distinguish a worker failure from a watchdog stop, and
  // a missing/unreadable terminal record must not look like an ordinary clean
  // finish.  Consume the same projection returned by both public endpoints so
  // the last API-to-browser seam preserves the process reason as well.
  const terminalEl = $("#run-terminal");
  const terminalSummary = runView.terminalSummary(terminal, state);
  terminalEl.textContent = terminalSummary ? `· ${terminalSummary}` : "";
  terminalEl.title = runView.terminalTitle(terminal, state);

  // Why it ended and whether it spent one of today's runs, kept with the run
  // rather than in a toast that is gone before the page is read again.
  const outcomeEl = $("#run-outcome");
  const outcome = runView.outcomeSummary({ state, error, error_code, funded_by, daily_charge, daily_charge_reason, checkpointing });
  outcomeEl.textContent = outcome;
  outcomeEl.hidden = !outcome;

  // Terminal success is still usable when its live projection is damaged,
  // but missing audit fields must not silently masquerade as a clean read.
  const statusRecordEl = $("#run-status-record");
  statusRecordEl.textContent = status_record_state === "unreadable"
    ? `· ${t("status_record_unreadable")}` : "";

  const runtimeFault = runView.runtimeMetadataSummary(runtime_metadata_unreadable ?? []);
  $("#run-step-record").textContent = ["partial", "unavailable"].includes(steps_read_state)
    ? `· ${t("steps_" + steps_read_state)}` : "";
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

/* The older way to copy, for where a page may not write to the clipboard
 * itself: the browser inside a chat app, an embedded view, a page not served
 * over HTTPS. The text goes into a field, is selected and copied, and the
 * field is gone before anything is drawn. Focus goes back where it was, so
 * a keyboard user is not left on nothing. True only if the browser said it
 * copied: a guess here would tell someone a link is on their clipboard when
 * what is there is whatever they copied last. */
function copyBySelection(text) {
  let field = null;
  try {
    const focused = document.activeElement;
    field = document.createElement("textarea");
    field.value = text;
    // Read-only keeps a phone's keyboard down; fixed keeps the page from scrolling to it.
    field.setAttribute("readonly", "");
    field.setAttribute("aria-hidden", "true");
    Object.assign(field.style, { position: "fixed", top: "0", left: "0", opacity: "0" });
    document.body.append(field);
    field.select();
    field.setSelectionRange(0, text.length);
    const copied = document.execCommand("copy") === true;
    focused?.focus?.();
    return copied;
  } catch {
    return false;
  } finally {
    field?.remove();
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return copyBySelection(text);
  }
}

/* A run's address is what opens it: anyone holding the link can read the
 * run without a code or an account. Copying it is therefore sharing it, and
 * the confirmation says so. Where the browser allows neither way of
 * copying, the address bar already holds the same link. */
function copyLinkButton() {
  const runId = activeRunId;
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "btn btn--secondary";
  copy.id = "run-copy-link";
  copy.textContent = t("copy_link");
  copy.addEventListener("click", async () => {
    const copied = await copyText(`${location.origin}/run/${runId}`);
    toast(t(copied ? "msg_link_copied" : "msg_link_copy_failed"), copied ? "success" : "error");
  });
  return copy;
}

/* The two ways a finished report leaves the browser. Markdown first: it is
 * instant, while the PDF renders on first request. */
function reportDownloads() {
  const icon = `
      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path d="M8 2.5v8m0 0L4.5 7M8 10.5L11.5 7M3 12.5v.5a1 1 0 001 1h8a1 1 0 001-1v-.5"
              stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>`;
  return [["md", "report", "Markdown"], ["pdf", "report.pdf", "PDF"]].map(([suffix, path, label]) => {
    const link = document.createElement("a");
    link.className = "btn btn--secondary";
    link.href = `/api/runs/${activeRunId}/${path}`;
    link.download = `${activeRunId}.${suffix}`;
    link.innerHTML = icon;
    link.append(label);
    return link;
  });
}

/* Runs whose cancel has been sent and not yet seen to take effect.
 *
 * Every poll repaints a run's actions, and the server takes a few seconds to
 * stop a worker. A Cancel that only disabled itself was replaced at the next
 * poll by a fresh, enabled one reading "Cancel": the page looked as if the
 * press had not registered, and invited a second. The state is kept here, by
 * run, so whichever button is on the page shows it. liveCancel is that
 * button; a refused cancel hands it back, not the one that was pressed. */
const cancelling = new Set();
let liveCancel = null;

function paintCancel() {
  if (!liveCancel) return;
  const pressed = cancelling.has(liveCancel.runId);
  liveCancel.button.disabled = pressed;
  liveCancel.button.textContent = t(pressed ? "cancelling" : "cancel");
}

function paintActions(state, checkpointing = null) {
  const actions = $("#run-actions");
  actions.innerHTML = "";

  if (viewerMode) {
    // Someone else's run: read it, keep it, pass it on. Nothing that changes
    // it or starts a paid step is offered; the server would refuse a reader
    // those anyway, and a button that only fails is worse than none.
    if (state === "completed") actions.append(...reportDownloads());
    if (state === "running" || runView.isTerminalState(state)) actions.append(copyLinkButton());
    return;
  }

  liveCancel = null;
  // What was pressed belongs to that stretch of running, and ends with it.
  if (runView.isTerminalState(state)) cancelling.delete(activeRunId);

  if (state === "running") {
    const runId = activeRunId;
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "btn btn--danger";
    liveCancel = { runId, button: cancel };
    paintCancel();
    cancel.addEventListener("click", async () => {
      if (cancelling.has(runId)) return;
      cancelling.add(runId);
      paintCancel();
      try {
        await api.cancelRun(runId);
        toast(t("msg_cancelled"));
        // The header reads "running" until the next poll, up to four seconds
        // away; ask now, so the stop is seen as soon as the server has made it.
        if (activeRunId === runId) follower?.poll?.();
      } catch (err) {
        cancelling.delete(runId);
        paintCancel();
        toast(err.message, "error");
      }
    });
    actions.append(cancel, copyLinkButton());
    return;
  }

  // No destructive controls before a readable state arrives or while it is
  // unknown. The server separately enforces intent when a stale click races
  // completion; disabling controls alone cannot solve that request race.
  if (!runView.isTerminalState(state)) return;

  // Not another "New analysis" — that button already lives in the rail, one
  // click away and always visible. A finished run needs a way out of the
  // browser instead.
  if (state === "completed") actions.append(...reportDownloads());

  const canResume = (
    new Set(["failed", "cancelled", "timeout"]).has(state)
    && checkpointing?.committed_nodes?.includes("retrieval")
  );
  if (canResume) {
    const sourceRunId = activeRunId;
    const resume = document.createElement("button");
    resume.type = "button";
    // The main thing to do with a run that stopped short, so it reads as
    // such; what it costs is said in the outcome line above the actions.
    resume.className = "btn btn--primary";
    resume.textContent = t("resume");
    resume.dataset.resumeRun = sourceRunId;
    resume.disabled = pendingResumes.has(sourceRunId) || paidReceipts.state().uncertain;
    resume.addEventListener("click", async () => {
      if (pendingResumes.has(sourceRunId)) return;
      pendingResumes.add(sourceRunId);
      resume.disabled = true;
      try {
        await performPaidRequest((key) => api.resumeRun(sourceRunId, key), async (accepted) => {
          requirePaidIdentity(accepted, "run_id");
          rememberAcceptedRun(accepted);
          await openRun(accepted.run_id, { known: accepted });
          toast(t("msg_resumed"), "success");
        }, "resume");
      } catch (err) {
        toast(operationErrorMessage(err), "error");
      } finally {
        pendingResumes.delete(sourceRunId);
        resume.disabled = paidReceipts.state().uncertain;
        // A re-render may have replaced the element while fetch was pending.
        // Unlock only this parent's current controls, never another operation.
        $$('[data-resume-run]').forEach((button) => {
          if (button.dataset.resumeRun === sourceRunId) button.disabled = paidReceipts.state().uncertain;
        });
      }
    });
    actions.append(resume);
  }

  // The same topic, as a new run. It fills the composer and stops there:
  // starting is a paid step and stays the user's own click. Language, profile
  // and decision context are not carried over; the page never had them.
  const again = document.createElement("button");
  again.type = "button";
  again.className = "btn btn--secondary";
  again.id = "run-again";
  again.textContent = t("run_again");
  again.title = t("run_again_title");
  again.addEventListener("click", () => {
    const previous = $("#run-title").textContent.trim();
    showCompose();
    if (previous && previous !== "…") topic.value = previous;
    syncComposer();
    topic.focus();
  });
  actions.append(again, compareButton(), copyLinkButton());

  // Only the known terminal states reaching here offer permanent removal.
  const del = document.createElement("button");
  del.type = "button";
  del.className = "btn btn--danger";
  del.textContent = t("delete_run");
  del.addEventListener("click", () => handleDeleteRun(activeRunId, $("#run-title").textContent));
  actions.append(del);
}

/* ── Finish notice ─────────────────────────────────────────────────────
 * A run takes ten to twenty minutes and people switch tabs. When a run this
 * page watched finishes in a background tab, the tab title says so, and a
 * browser notification appears if the user opted in from the run header.
 * Permission is asked only from that button, never unprompted. */

const baseTitle = document.title;
const notificationsAvailable = () => typeof Notification !== "undefined";
let notifyState = "";

function paintNotifyButton(state) {
  notifyState = state;
  const button = $("#run-notify");
  button.hidden = !(state === "running" && notificationsAvailable() && Notification.permission === "default");
  button.textContent = `· ${runView.headerLabel("notify")}`;
  button.title = runView.headerLabel("notify_title");
}

$("#run-notify").addEventListener("click", async () => {
  if (!notificationsAvailable()) return;
  try { await Notification.requestPermission(); }
  catch { /* A refused or unsupported prompt leaves the title notice. */ }
  paintNotifyButton(notifyState);
});

function announceFinish(progress) {
  if (!document.hidden) return;
  const label = runView.headerLabel(progress.state === "completed" ? "finished_ok" : "finished_bad");
  document.title = `${progress.state === "completed" ? "✓" : "✗"} ${label} · ${baseTitle}`;
  if (notificationsAvailable() && Notification.permission === "granted") {
    try {
      const notice = new Notification(label, { body: progress.topic || "", tag: progress.run_id });
      notice.onclick = () => { window.focus(); notice.close(); };
    } catch {
      // Some mobile browsers allow notifications only from a service worker.
    }
  }
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) document.title = baseTitle;
});

async function openRun(runId, { known } = {}) {
  stopFollowing();
  showRun(runId);
  $("#run-connection").textContent = "";

  const body = $("#run-body");
  body.innerHTML = "";
  paintHeader({ topic: known?.topic ?? "…", state: known?.state ?? "unknown" });
  paintActions(known?.state ?? "unknown", known?.checkpointing);
  try { history.pushState({}, "", `/run/${runId}`); }
  catch {
    // Optional URL persistence cannot strand an accepted run before follow.
    toast(t("msg_history_unavailable"), "error");
  }

  // A run first seen already finished is history, not news: announce only a
  // completion this page watched happen. (Errors are still always shown.)
  let watchedActive = false;
  follower = runView.follow(runId, {
    onConnection({ state, lastSuccessAt }) {
      // Connectivity is a fact about our read, not a new worker state. Stop
      // extrapolating elapsed time until a fresh progress response anchors it.
      $("#run-connection").textContent = state === "stale"
        ? t(lastSuccessAt === null ? "run_connection_unconfirmed" : "run_connection_stale")
        : state === "missing" ? t("run_connection_missing") : "";
      if (state !== "connected") stopClock();
    },
    onUpdate(progress) {
      if (progress.state === "running") watchedActive = true;
      paintHeader(progress);
      paintActions(progress.state, progress.checkpointing);
      runView.renderStages(body, runView.stageStates(progress.stage, progress.state, progress.stage_timings));
    },
    onDone(progress) {
      paintHeader(progress);
      paintActions(progress.state, progress.checkpointing);
      runView.renderStages(body, runView.stageStates(progress.stage, progress.state, progress.stage_timings));
      refreshSidebar();

      if (progress.state === "completed") {
        if (watchedActive) toast(t("msg_complete"), "success");
      } else if (progress.error) {
        // The same wording as the line that stays with the run.
        toast(runView.failureText(progress), "error");
      }
      if (watchedActive) announceFinish(progress);

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
  if (byokMode && !accountMode) api.removeByokRun(runId);
  toast(t("msg_deleted"));
  // The follower already stopped polling once this run reached a terminal
  // state (see run.js follow()), so nothing else will notice it vanished —
  // navigate away explicitly rather than leaving a dead run open.
  if (runId === activeRunId) showCompose();
  else refreshSidebar();
}

async function refreshSidebar() {
  // A reader has no identity whose history this would be; the list stays
  // behind the gate and asking would only earn a refusal.
  if (viewerMode) return;
  const revision = ++sidebarRevision;
  const isCurrent = () => revision === sidebarRevision;
  // GET /api/runs (the list) always stays behind the access code, scoped
  // server-side to that code's own runs (api/access.py owner_id). A BYOK
  // visitor has no code at all, so this builds the same view from the
  // session-only list of run ids api.addByokRun() has been recording —
  // gone once the tab closes, complete for as long as it's open.
  if (byokMode && !accountMode) {
    const list = $("#runlist");
    $("#run-search").hidden = true;
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
        // A transport/HTTP failure says nothing about the worker. Marking it
        // failed would expose Delete, which older servers interpreted as
        // cancellation if the run was actually still active.
        return { run_id, topic, state: "unknown", started_at: _startedAtFromRunId(run_id) };
      }
    }));
    if (!isCurrent()) return null;
    sidebar.render(list, runs, {
      activeId: activeRunId,
      onSelect: (id) => openRun(id),
      onDelete: handleDeleteRun,
    });
    return runs;
  }
  return sidebar.refresh($("#runlist"), {
    isCurrent,
    activeId: activeRunId,
    onSelect: (runId) => openRun(runId),
    onDelete: handleDeleteRun,
    onChange: refreshSidebar,
  });
}

/* Filtering waits for a pause in typing: a search may load the rest of the
 * history, and doing that on every keystroke would ask for it several times. */
let searchTimer = null;
$("#run-search").addEventListener("input", (event) => {
  clearTimeout(searchTimer);
  const text = event.target.value;
  searchTimer = setTimeout(() => {
    sidebar.setQuery?.(text);
    refreshSidebar();
  }, 200);
});

/* ── Composer ──────────────────────────────────────────────────────── */

/* True only while an extraction is in flight. Submission is blocked for that
 * window: attachedPaper is null until the response arrives, so a run started
 * mid-extraction would quietly go out without the paper the user attached.
 *
 * Declared here rather than beside the upload handler because syncComposer
 * reads it and runs first — a `let` further down is a temporal dead zone, and
 * the boot-time call threw before anything rendered. */
let extracting = false;
// Identity flags, declared up here for the same reason: refreshSidebar and
// rememberAcceptedRun read them, and both can run before the gate section
// below has been evaluated.
let byokMode = false;
// A signed-in account (api/accounts.py). Its runs are paid for with the keys
// in the BYOK slot, so byokMode is true as well once keys are added; what
// differs is that the server tags and lists its runs, and that it never
// draws on the deployment's key (no plan preview, no operator quota).
let accountMode = false;
let accountEmail = null;
// False only for an account that has not yet opened its verification link.
// Such an account can sign in, save keys and preview; a run is refused, here
// before any intent is recorded and on the server with email_unverified.
let accountVerified = true;
// The signed-in account is an administrator (the console link, and on a
// deployment that funds administrators, runs without keys of their own).
let accountAdmin = false;
// Whether the account asked for an email when a run of its ends (Account panel).
let accountNotify = false;
// A visitor with no identity reading a run or a comparison someone shared
// (enterViewer). They see the report and a bar that offers the way in; no
// history is asked for and nothing that changes the run is offered.
let viewerMode = false;
// Assessments the account may still start without keys, on the deployment's
// own (a verified account's trial); the server's number, counted down here
// when one is accepted.
let accountTrialLeft = 0;
let authConfig = null;
// A disabled button is only a projection, not an operation lock: input events
// used to re-enable it while a paid POST was still awaiting acknowledgement.
// This is tab-local exclusion, not server/provider exactly-once delivery.
let submitting = false;
let uploadGeneration = 0;
// Search-plan preview: offered by the deployment (access check), for code
// holders only. previewing locks the run button while the reading is fetched;
// planState holds the reading the panel shows, for the topic it was read from.
let planPreviewEnabled = false;
let previewing = false;
let planState = null;
// Paid operations left today: shown when the deployment advertises a cap.
let quotaEnabled = false;
let quotaGeneration = 0;
let lastQuota = null;

const topic = $("#topic");
const count = $("#topic-count");
const runBtn = $("#run-btn");
const composer = $("#composer");
const planPanel = $("#plan-panel");
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
  for (const input of decisionContextInputs) {
    input.value = "";
    // decision_context.js recounts the starred fields on input.
    input.dispatchEvent(new Event("input"));
  }
}


function autosize() {
  topic.style.height = "auto";
  topic.style.height = `${topic.scrollHeight}px`;
}

function syncComposer() {
  runBtn.disabled = topic.value.trim().length < 3 || extracting || submitting || previewing
    || paidReceipts.state().uncertain;
  runBtn.title = submitting ? t("msg_submitting")
    : previewing ? runView.planLabel("previewing")
    : extracting ? t("msg_wait_extract") : t("run_hint");
  planPanel.querySelectorAll("button, input").forEach((control) => {
    control.disabled = submitting || paidReceipts.state().uncertain;
  });
  attachBtn.disabled = extracting || submitting || paidReceipts.state().uncertain;
  // Keep the submitted payload stable in the visible composer as well. The
  // handler guard still matters for programmatic submits and queued events.
  for (const input of [topic, $("#language"), $("#profile"), ...decisionContextInputs]) {
    input.disabled = submitting;
  }
  $$(".starter").forEach((button) => { button.disabled = submitting; });
  attachment.querySelectorAll("button").forEach((button) => { button.disabled = submitting; });
  count.textContent = topic.value.length > 240 ? `${topic.value.length} / 300` : "";
  autosize();
}

topic.addEventListener("input", syncComposer);
topic.addEventListener("input", () => {
  if (planState && topic.value.trim() !== planState.topic) hidePlan();
});
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
  if (submitting || extracting || previewing || topic.value.trim().length < 3) return;
  // Before the preview, not only before the start: an account that cannot
  // run yet should not spend a model call learning that.
  if (accountMode && !accountVerified) { toast(t("msg_email_unverified"), "error"); return; }
  const submittedTopic = topic.value.trim();
  if (planState?.topic === submittedTopic) {
    // The panel already shows this topic's reading; Enter must not re-read it.
    $("#plan-start")?.focus();
    return;
  }
  if (
    needsScopeWarning(submittedTopic, { hasPaper: Boolean(attachedPaper) })
    && !confirm(t("confirm_broad_topic"))
  ) return;
  // A code holder previews on the deployment's key. An account previews on
  // its own, which it has by now: the gate above asked for keys; an
  // administrator the deployment funds previews on the deployment's key, as
  // a code holder does. A visitor whose keys are their only identity starts
  // as before.
  if (planPreviewEnabled && (accountMode ? (Boolean(api.getByok()) || operatorPays() || trialPays()) : !byokMode)) {
    await previewPlan(submittedTopic);
    return;
  }
  await submitAssessment(submittedTopic, null);
});

async function submitAssessment(submittedTopic, searchPlan) {
  if (submitting || extracting) return;
  submitting = true;
  syncComposer();

  try {
    await performPaidRequest((key) => api.startRun({
      topic: submittedTopic,
      language: $("#language").value,
      weight_profile: $("#profile").value,
      paper_id: attachedPaper?.paper_id,
      decision_context: readDecisionContext(),
      search_plan: searchPlan,
    }, key), async (accepted) => {
      requirePaidIdentity(accepted, "run_id");
      rememberAcceptedRun(accepted);
      await openRun(accepted.run_id, { known: accepted });
      topic.value = "";
      hidePlan();
      clearDecisionContext();
      clearAttachment();
      syncComposer();
    });
  } catch (err) {
    toast(operationErrorMessage(err), "error");
  } finally {
    submitting = false;
    syncComposer();
    refreshQuota();
  }
}

/* ── Search-plan preview ───────────────────────────────────────────────
 * The planner's reading of a topic decides every query. A wrong reading
 * ("hyperloop" renamed, vertical farming drifting) used to show only after
 * the run had spent its stages and one of the code's daily runs. With a
 * code, the run button first shows that reading; the user confirms or edits
 * it, and the run searches exactly that. Unresolved topics stop here.
 *
 * An account gets the same step on its own model key, and is told so: a
 * wrong reading costs an account the whole run, on its own bill. When the
 * model gives no answer the reply says so, and the page says so too rather
 * than showing the topic as typed as if it were a reading. */

/* The planner takes seconds, and until 2026-11-11 the only sign that it had
 * been asked was the run button's tooltip: the press looked as if it had done
 * nothing. The panel says so at once, where the reading will appear, with
 * nothing to press yet. On a phone that place is below the fold, so the panel
 * is brought into view, here and again when the reading (which is taller, and
 * ends in the button that starts the run) replaces the line. "nearest" moves
 * the page no further than it has to, and not at all when the panel shows. */
function showPlanWaiting() {
  hidePlan();
  const label = runView.planLabel;
  planPanel.hidden = false;
  planPanel.append(planNode("h2", "plan-panel__title", label("title")),
    planNode("p", "plan-panel__lede", label("previewing")));
  planPanel.scrollIntoView?.({ block: "nearest" });
}

async function previewPlan(submittedTopic) {
  previewing = true;
  syncComposer();
  showPlanWaiting();
  let next;
  try {
    const own = accountMode;
    const plan = await api.planTopic(submittedTopic, { ownKeys: own });
    next = plan?.planned === false
      ? { topic: submittedTopic, failure: own ? "no_answer_own" : "no_answer", plan: null }
      : plan?.resolved
        ? { topic: submittedTopic, failure: null, own, plan: {
          search_topic: plan.search_topic, aliases: [...plan.aliases], components: [...plan.components] } }
        : { topic: submittedTopic, failure: "unresolved", plan: null };
  } catch (err) {
    if (err.status === 401) {
      hidePlan();
      toast(operationErrorMessage(err), "error");
      return;
    }
    next = { topic: submittedTopic, plan: null, reason: err.message,
      failure: err.code === "plan_preview_limit" ? "limit" : "unavailable" };
  } finally {
    previewing = false;
    syncComposer();
  }
  // A reading of a topic the user has since changed would confirm the wrong one.
  if (topic.value.trim() !== submittedTopic) {
    hidePlan();
    return;
  }
  planState = next;
  renderPlan();
  (planState.plan ? $("#plan-topic") : $("#plan-start") ?? $("#plan-edit"))?.focus();
  planPanel.scrollIntoView?.({ block: "nearest" });
}

function hidePlan() {
  planState = null;
  planPanel.hidden = true;
  planPanel.innerHTML = "";
}

/* Remaining daily runs, so a code holder learns of the cap before a
 * submission is refused rather than from the refusal. */
function paintQuota() {
  const el = $("#quota");
  const summary = runView.quotaSummary(lastQuota);
  el.hidden = !summary.text;
  el.textContent = summary.text;
  el.title = summary.title;
  el.classList?.toggle("composer__quota--empty", summary.exhausted);
}

async function refreshQuota() {
  const generation = ++quotaGeneration;
  // An account has an allowance of its own; a visitor on their own keys has none.
  if (!quotaEnabled || (byokMode && !accountMode)) {
    lastQuota = null;
    paintQuota();
    return;
  }
  try {
    const quota = await api.getQuota();
    if (generation !== quotaGeneration) return;
    lastQuota = quota;
  } catch {
    if (generation !== quotaGeneration) return;
    lastQuota = null;
  }
  paintQuota();
}

function readConfirmedPlan() {
  const searchTopic = planState.plan.search_topic.split(/\s+/).filter(Boolean).join(" ");
  if (searchTopic.length < 3) return null;
  // An edited phrase may now equal an alternative; searching it twice adds nothing.
  const distinct = (phrases) => phrases.filter((p) => p.toLowerCase() !== searchTopic.toLowerCase());
  const components = distinct(planState.plan.components);
  return {
    search_topic: searchTopic,
    aliases: distinct(planState.plan.aliases),
    components: components.length >= 2 ? components : [],
  };
}

function planNode(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function renderPlan() {
  if (!planState) return;
  const label = runView.planLabel;
  planPanel.innerHTML = "";
  planPanel.hidden = false;
  planPanel.append(planNode("h2", "plan-panel__title", label("title")));
  const message = planState.failure === null ? label(planState.own ? "lede_own" : "lede")
    : label(planState.failure).replace("{reason}", planState.reason || "—");
  planPanel.append(planNode("p", "plan-panel__lede", message));

  if (planState.plan) {
    const field = planNode("label", "plan-panel__group");
    const input = planNode("input");
    input.id = "plan-topic";
    input.type = "text";
    input.maxLength = 200;
    input.value = planState.plan.search_topic;
    input.addEventListener("input", () => { planState.plan.search_topic = input.value; });
    input.addEventListener("keydown", (e) => {
      // Inside the composer form, Enter would otherwise submit it again.
      if (e.key === "Enter") { e.preventDefault(); startFromPlan(); }
    });
    field.append(planNode("span", "plan-panel__label", label("search_topic")), input);
    planPanel.append(field);
    for (const kind of ["aliases", "components"]) {
      const phrases = planState.plan[kind];
      if (!phrases.length) continue;
      const group = planNode("div", "plan-panel__group");
      group.dataset.planGroup = kind;
      const chips = planNode("ul", "plan-panel__chips");
      phrases.forEach((phrase, index) => {
        const chip = planNode("li", "plan-chip");
        const remove = planNode("button", null, "×");
        remove.type = "button";
        remove.setAttribute("aria-label", `${label("remove")}: ${phrase}`);
        remove.addEventListener("click", () => {
          planState.plan[kind].splice(index, 1);
          renderPlan();
        });
        chip.append(planNode("span", null, phrase), remove);
        chips.append(chip);
      });
      group.append(planNode("span", "plan-panel__label", label(kind)), chips);
      planPanel.append(group);
    }
  }

  const actions = planNode("div", "plan-panel__actions");
  if (planState.failure !== "unresolved") {
    const start = planNode("button", "btn btn--primary", label(planState.plan ? "start" : "start_without"));
    start.type = "button";
    start.id = "plan-start";
    start.addEventListener("click", startFromPlan);
    actions.append(start);
  }
  const edit = planNode("button", "btn btn--secondary", label("edit"));
  edit.type = "button";
  edit.id = "plan-edit";
  edit.addEventListener("click", () => { hidePlan(); topic.focus(); });
  actions.append(edit);
  planPanel.append(actions);
  syncComposer();
}

async function startFromPlan() {
  if (!planState || submitting) return;
  let searchPlan = null;
  if (planState.plan) {
    searchPlan = readConfirmedPlan();
    if (!searchPlan) {
      toast(runView.planLabel("too_short"), "error");
      return;
    }
  }
  await submitAssessment(planState.topic, searchPlan);
}

/* ── Attachment ─────────────────────────────────────────────────────
 * An uploaded paper becomes source A1 and the pipeline searches around its
 * specific contribution. Extraction takes a few seconds and involves an LLM
 * call, so the control reports progress rather than appearing to hang. */

let attachedPaper = null;
const attachment = $("#attachment");
const attachBtn = $("#attach-btn");
const pdfInput = $("#pdf-input");

function clearAttachment() {
  // Invalidating a response does not cancel its provider call. Keep the
  // extraction lock until that request settles, even if the view is cleared.
  uploadGeneration += 1;
  attachedPaper = null;
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
  remove.addEventListener("click", () => {
    if (!submitting) clearAttachment();
  });

  attachment.append(title, remove);
  const usage = document.createElement("span");
  usage.textContent = runView.auxiliarySummary(paper.auxiliary_usage);
  usage.title = usage.textContent;
  attachment.append(usage);
  attachBtn.dataset.active = "true";

  // Suggest a topic only for an empty composer. The user's existing topic
  // remains authoritative; a model's reading is a proposal, not a verdict.
  if (paper.commercialization_topic && !topic.value.trim()) {
    topic.value = paper.commercialization_topic;
    syncComposer();
  }
}

async function uploadPaper(file) {
  if (!file) return;
  // Serialize paid extraction, including drop/change events that bypass the
  // disabled attachment button. Aborting fetch would not cancel provider work.
  if (extracting || submitting) {
    toast(t(extracting ? "msg_wait_extract" : "msg_submitting"), "error");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    toast(t("msg_not_pdf"), "error");
    return;
  }

  extracting = true;
  const generation = ++uploadGeneration;
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
    await performPaidRequest((key) => api.uploadPaper(file, key), (paper) => {
      requirePaidIdentity(paper, "paper_id");
      // Explicit attachment removal discards the returned selection, not
      // the knowledge that extraction finished. No automatic re-extraction.
      if (generation !== uploadGeneration) return;
      attachedPaper = paper;
      paintAttachment(paper);
      toast(t("msg_paper_attached"), "success");
    }, "paper");
  } catch (err) {
    if (generation !== uploadGeneration) return;
    clearAttachment();
    if (err.auxiliary_usage != null) {
      attachment.hidden = false;
      const observation = document.createElement("span");
      observation.textContent = runView.auxiliarySummary(err.auxiliary_usage);
      attachment.append(observation);
    }
    toast(err.status === 413
      ? t("msg_too_large")
      : operationErrorMessage(err), "error");
  } finally {
    extracting = false;
    // Always update the control, even when an existing topic meant that
    // paintAttachment did not auto-fill it (and therefore did not sync it).
    syncComposer();
    refreshQuota();
  }
}

attachBtn.addEventListener("click", () => {
  if (extracting || submitting) return;
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
    try { localStorage.setItem("sidebar-collapsed", String(next)); }
    catch { /* Sidebar persistence is optional; the current DOM already reflects the click. */ }
  }
});

try {
  if (localStorage.getItem("sidebar-collapsed") === "true" && !NARROW.matches) {
    workbench.dataset.collapsed = "true";
  }
} catch { /* A default-open sidebar must not stop access checks or routing. */ }

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

// The last /health reading, kept so a language switch can relabel the
// capacity line at once instead of leaving it in the old language until the
// next poll. null until the first reading; "offline" after a failed one.
let capacityReading = null;

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
    capacityReading = { active_paid_operations, max_concurrent, retention_days };
  } catch {
    capacityReading = "offline";
  }
  paintCapacityLabel();
}

function paintCapacityLabel() {
  if (capacityReading === null) return;
  const label = $("#capacity-label");
  if (capacityReading === "offline") {
    label.textContent = t("offline");
    return;
  }
  const { active_paid_operations, max_concurrent, retention_days } = capacityReading;
  label.textContent = `${active_paid_operations}/${max_concurrent} ${t("running_label")}`;
  // Someone who uploads an unpublished paper is entitled to know how long it
  // stays here — and a deletion nobody was told about reads as data loss
  // rather than as policy. Shown on the capacity line rather than in a
  // dialog because it is a standing fact about the deployment, not an event.
  label.title = retention_days
    ? t("retention_note").replace("{days}", retention_days)
    : t("retention_forever");
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


function applyAccountMode(me) {
  receiptViewGeneration++;
  $("#paid-receipt-results").innerHTML = "";
  invalidateSidebar();
  accountMode = true;
  accountEmail = me.email;
  api.setAccessCode(null);
  byokMode = Boolean(api.getByok());
  $("#byok-badge").hidden = true;
  $("#code-badge").hidden = true;
  $("#account-email").textContent = t("account_badge").replace("{email}", me.email);
  $("#account-email").title = me.email;   // the badge ellipsizes a long address
  $("#account-console").hidden = me.admin !== true;
  $("#account-badge").hidden = false;
  accountVerified = me.verified !== false;
  accountNotify = me.notify_done === true;
  accountAdmin = me.admin === true;
  accountTrialLeft = Number.isInteger(me.trial_runs_left) ? me.trial_runs_left : 0;
  paintVerifyNotice();
  paintTrialNote();
  hidePlan();
  refreshQuota();
}

function paintVerifyNotice() {
  const notice = $("#verify-notice");
  notice.hidden = !accountMode || accountVerified;
  if (!notice.hidden) $("#verify-text").textContent = t("verify_notice").replace("{email}", accountEmail);
}

$("#verify-resend").addEventListener("click", async () => {
  const button = $("#verify-resend");
  if (button.disabled) return;
  button.disabled = true;
  try {
    await api.resendVerification();
    toast(t("verify_sent"), "success");
  } catch (err) {
    if (err.code === "already_verified") {
      accountVerified = true;
      paintVerifyNotice();
      toast(t("verify_done"), "success");
      // A trial waits for the address to be proven; ask what the account has now.
      api.me().then((me) => {
        accountTrialLeft = Number.isInteger(me.trial_runs_left) ? me.trial_runs_left : 0;
        paintTrialNote();
      }).catch(() => {});
    } else {
      toast(t(err.code === "verification_cooldown" ? "verify_cooldown" : "verify_failed"), "error");
    }
  } finally {
    button.disabled = false;
  }
});

/* The page a verification link opens. The token is sent from here, by POST,
 * so a mail client or scanner fetching the link on the reader's behalf does
 * not verify anything. Returns the message to show once the page is up, or
 * called only for such a visit. The address is removed from the location
 * either way: a token in the URL bar is not something to bookmark. */
async function consumeVerificationLink() {
  const token = new URLSearchParams(location.search).get("token");
  try { history.replaceState({}, "", "/"); } catch { /* keep the URL; the token has been read */ }
  if (!token) return { key: "verify_invalid", variant: "error" };
  try {
    await api.verifyEmail(token);
  } catch (err) {
    return { key: err.code === "verification_expired" ? "verify_expired" : "verify_invalid", variant: "error" };
  }
  return { key: "verify_done", variant: "success" };
}

/* The page a reset link opens (/reset?token=…). Only the token is read here;
 * the gate asks for the new password and posts both. The address leaves the
 * location at once, as the verification token does. */
function takeResetToken() {
  const token = new URLSearchParams(location.search).get("token") || "";
  try { history.replaceState({}, "", "/"); } catch { /* keep the URL; the token has been read */ }
  return token;
}

function applyByokMode() {
  receiptViewGeneration++;
  $("#paid-receipt-results").innerHTML = "";
  invalidateSidebar();
  byokMode = true;
  api.setAccessCode(null);
  $("#byok-badge").hidden = false;
  hidePlan();
  refreshQuota();
}

function showStorageNotice(key = "storage_unavailable") {
  const notice = $("#storage-notice");
  notice.dataset.i18n = key;
  notice.textContent = t(key);
  notice.hidden = false;
}

async function exitCredentials() {
  // A pending paid reply may carry the only link to accepted work. Do not
  // discard it, relabel it as the next identity, or abort a provider request
  // merely to make logout immediate. This guards logout's own reload, not a
  // browser refresh, close, crash or navigation outside this handler.
  if (submitting || extracting || pendingResumes.size) {
    toast(t("logout_wait_paid"), "error");
    return;
  }
  receiptViewGeneration++;
  $("#paid-receipt-results").innerHTML = "";
  const receiptsCleared = api.clearReceiptJournal();
  invalidateSidebar();
  clearAttachment();
  clearDecisionContext();
  topic.value = "";
  syncComposer();
  const byokCleared = api.setByok(null);
  const codeCleared = api.setAccessCode(null);
  if (accountMode) {
    // Best effort: the token is forgotten locally either way, and the server
    // expires it on its own schedule if this request is lost.
    try { await api.logout(); } catch { /* already out, or unreachable */ }
  }
  const sessionCleared = api.setSessionToken(null);
  if (byokCleared && codeCleared && sessionCleared && receiptsCleared) {
    // A clean sign-out starts over at the front door. On a deployment with
    // accounts that is the landing at "/"; reloading in place would reopen
    // the run or comparison just left, under the sign-in card. A code
    // deployment has no landing and reloads where it is, as it always did.
    if (authConfig?.enabled) location.replace("/");
    else location.reload();
    return;
  }
  // Failed removal or a different shared selection must not be undone by
  // reloading: that would read stale/other credentials again. End this page's
  // session and ask for explicit login, without claiming global sign-out.
  stopFollowing();
  stopClock();
  activeRunId = null;
  byokMode = false;
  accountMode = false;
  accountEmail = null;
  accountTrialLeft = 0;
  paintTrialNote();
  $("#byok-badge").hidden = true;
  $("#code-badge").hidden = true;
  $("#account-badge").hidden = true;
  $("#verify-notice").hidden = true;
  $("#pane-run").hidden = true;
  $("#pane-compose").hidden = true;
  showStorageNotice((api.accessCodeClearConflict() || api.sessionClearConflict()) && byokCleared
    ? "storage_other_identity" : "storage_logout_incomplete");
  await showGate();
  showCompose();
}

$("#byok-exit").addEventListener("click", exitCredentials);

// Mutually exclusive with applyByokMode(): shown only when a stored code is
// what got the visitor past the gate, never when the gate is off entirely
// (nothing to log out of then) and never alongside the BYOK badge.
function applyCodeMode() {
  receiptViewGeneration++;
  $("#paid-receipt-results").innerHTML = "";
  invalidateSidebar();
  api.setByok(null);
  byokMode = false;
  $("#byok-badge").hidden = true;
  $("#code-badge").hidden = false;
  hidePlan();
}

$("#code-exit").addEventListener("click", exitCredentials);
$("#account-exit").addEventListener("click", exitCredentials);
// Change or add keys without signing out; the account's history stays.
$("#account-keys").addEventListener("click", async () => {
  if (submitting || extracting) return;
  await showGate(null, { keysOnly: true });
});
$("#account-manage").addEventListener("click", () => {
  if (submitting || extracting || pendingResumes.size) return;
  showAccountSettings();
});

/* Account self-service: change the password, or delete the account with
 * everything recorded under it. Shown on the gate card because it is the
 * same kind of moment: the page stops and asks who you are again. Both
 * actions send the password; the server refuses a session alone. */
function showAccountSettings() {
  const gate = $("#gate");
  const panel = $("#account-settings");
  const passwordForm = $("#settings-password-form");
  const deleteForm = $("#settings-delete-form");
  const passwordError = $("#settings-password-error");
  const deleteError = $("#settings-delete-error");
  for (const id of ["#gate-form", "#byok-form", "#account-form", "#forgot-form", "#reset-form"]) $(id).hidden = true;
  passwordForm.reset();
  deleteForm.reset();
  passwordError.hidden = true;
  deleteError.hidden = true;
  $("#account-settings-email").textContent = t("account_badge").replace("{email}", accountEmail ?? "");
  panel.hidden = false;
  gate.hidden = false;
  $("#settings-current-password").focus();

  const close = () => { panel.hidden = true; gate.hidden = true; };
  const message = (err) => {
    const key = {
      invalid_credentials: "account_error_current", weak_password: "account_error_same",
      locked: "account_error_locked", active_runs: "account_error_active_runs",
    }[err.code];
    return key ? t(key) : err.message;
  };
  $("#settings-close").onclick = close;

  // The notice switch: only where the deployment can send mail. Saved on
  // change, and put back if the server did not take it, so the box never
  // shows a state the account does not have.
  const notifyRow = $("#settings-notify-row");
  const notifyBox = $("#settings-notify");
  notifyRow.hidden = !authConfig?.notices;
  notifyBox.checked = accountNotify;
  notifyBox.disabled = false;
  $("#settings-notify-hint").textContent = t("account_notify_hint").replace("{email}", accountEmail ?? "");
  notifyBox.onchange = async () => {
    const wanted = notifyBox.checked;
    notifyBox.disabled = true;
    try {
      await api.setNotify(wanted);
      accountNotify = wanted;
      toast(t(wanted ? "account_notify_on" : "account_notify_off"), "success");
    } catch {
      notifyBox.checked = accountNotify;
      toast(t("account_notify_failed"), "error");
    } finally {
      notifyBox.disabled = false;
    }
  };

  passwordForm.onsubmit = async (e) => {
    e.preventDefault();
    const submit = $("#settings-password-submit");
    if (submit.disabled) return;
    submit.disabled = true;
    passwordError.hidden = true;
    try {
      await api.changePassword($("#settings-current-password").value, $("#settings-new-password").value);
      toast(t("account_password_changed"), "success");
      close();
    } catch (err) {
      passwordError.textContent = message(err);
      passwordError.hidden = false;
    } finally {
      submit.disabled = false;
    }
  };

  deleteForm.onsubmit = async (e) => {
    e.preventDefault();
    const submit = $("#settings-delete-submit");
    if (submit.disabled || !confirm(t("account_delete_confirm"))) return;
    submit.disabled = true;
    deleteError.hidden = true;
    try {
      await api.deleteAccount($("#settings-delete-password").value);
    } catch (err) {
      deleteError.textContent = message(err);
      deleteError.hidden = false;
      submit.disabled = false;
      return;
    }
    // The account is gone server-side. Forget everything that named it here,
    // then start over as a visitor; a failed local removal still ends up at
    // the gate, because the stored token no longer opens anything.
    api.clearReceiptJournal();
    api.setByok(null);
    api.setSessionToken(null);
    location.reload();
  };
}

/* ── Landing ───────────────────────────────────────────────────────────
 * What an anonymous visitor to "/" sees on a deployment with accounts: a
 * page about the product, with the sign-in card opening from its buttons,
 * instead of the empty workbench with that card already over it. Only
 * there: a stored session goes straight to the workbench; a deep link to a
 * run, a comparison or a verification page meets the card directly, since
 * whoever followed it came for that and not for an introduction; and a
 * deployment without accounts is invite-only by access code, so its
 * visitors already know what they were sent to. Resolves once the card has
 * let someone in, when the workbench takes over. */
/* An address a link can share: one run, or two side by side. */
function sharedPath() {
  return /^\/run\/[^/]+$/.test(location.pathname) || /^\/compare\/[^/]+\/[^/]+$/.test(location.pathname);
}

/* A visitor with no identity who followed a link to a run.
 *
 * "Copy link" hands the address to someone else, and the server has always
 * answered a run's reads to whoever holds its id (api/main.py, the gate's
 * exemption for /api/runs/{id}/...). The page did not: it put the sign-in
 * card in front of the report, so the person a link was for had to create
 * an account to read one. They read it now. What they are not given is
 * anything that belongs to an identity: no history, no composer, nothing
 * that changes the run. The bar is the way in, through the same card. */
function enterViewer() {
  viewerMode = true;
  $("#workbench").dataset.viewer = "true";
  $("#viewer-bar").hidden = false;
  $("#viewer-create").hidden = !authConfig?.signup_open;
  $("#viewer-sign-in").hidden = false;
  let opening = false;
  const open = (creating) => async () => {
    if (opening) return;
    opening = true;
    try {
      // "back" is the card put down again: the report stays, the bar too.
      if (await showGate(null, { creating, back: true }) !== "back") leaveViewer();
    } finally {
      opening = false;
    }
  };
  $("#viewer-create").onclick = open(true);
  $("#viewer-sign-in").onclick = open(false);
}

/* Signed in from the bar: the reader is a user of this deployment now. */
function leaveViewer() {
  viewerMode = false;
  $("#workbench").dataset.viewer = "false";
  $("#viewer-bar").hidden = true;
  routeFromLocation();
  refreshSidebar();
}

function landingWanted() {
  return Boolean(authConfig?.enabled) && location.pathname === "/";
}

async function showLanding() {
  const landing = $("#landing");
  const workbench = $("#workbench");
  landing.hidden = false;
  workbench.hidden = true;
  // Without sign-up the button would only ever fail; sign-in stands alone.
  $("#landing-create").hidden = !authConfig?.signup_open;
  // Said only where the deployment pays for a newcomer's first assessment.
  $("#landing-trial").hidden = !(authConfig?.trial_runs > 0);
  // The sidebar's language select is hidden with the workbench; this one
  // drives it, so every listener on the original still runs.
  const lang = $("#landing-lang");
  lang.value = i18n.language();
  lang.onchange = () => {
    langSelect.value = lang.value;
    langSelect.dispatchEvent(new Event("change"));
  };
  paintLandingSamples();
  paintLandingRetention();
  // The scorecard picture is fetched only now: the markup carries it as
  // data-src, since a hidden image is requested all the same.
  const preview = $("#landing-preview");
  if (preview.dataset.src) {
    preview.src = preview.dataset.src;
    delete preview.dataset.src;
  }
  let opening = false;
  await new Promise((resolve) => {
    const open = (creating) => async () => {
      if (opening) return;
      opening = true;
      try {
        // "back" is the card put down again: the landing stays, buttons live.
        if (await showGate(null, { creating, back: true }) !== "back") resolve();
      } finally {
        opening = false;
      }
    };
    $("#landing-create").onclick = open(true);
    $("#landing-sign-in").onclick = open(false);
    $("#landing-sign-in-top").onclick = open(false);
  });
  landing.hidden = true;
  workbench.hidden = false;
}

/* The finished reports a visitor can read before signing in, by their real
 * titles. /api/samples needs no credentials and reads no deployment state.
 * Titles are placed as text; a slug becomes a path only when it has the
 * shape the server's allowlist uses. Failure leaves the "all samples"
 * link, which stands on its own. */
async function paintLandingSamples() {
  const list = $("#landing-sample-list");
  list.innerHTML = "";
  let samples;
  try { samples = await api.listSamples(); } catch { return; }
  if (!Array.isArray(samples)) return;
  for (const sample of samples.slice(0, 5)) {
    if (typeof sample?.slug !== "string" || !/^[a-z0-9-]+$/.test(sample.slug)) continue;
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = `/samples/${sample.slug}`;
    link.textContent = String(sample.title ?? sample.slug);
    item.append(link);
    list.append(item);
  }
}

/* How long this deployment keeps what a visitor hands it, said next to who
 * pays. The key form says the same (showByokRetention), but by then the
 * visitor has signed up; this is the moment they decide to. Silent on
 * failure for the same reason as there: no line beats a wrong one. */
async function paintLandingRetention() {
  const node = $("#landing-retention");
  try {
    const { retention_days } = await api.health();
    node.textContent = retention_days
      ? t("byok_retention").replace("{days}", retention_days)
      : t("byok_retention_forever");
  } catch {
    node.textContent = "";
  }
}

/* Whether this visit could end on the landing: at its address, with nothing
 * stored that would sign the visit in. Decided before the access check, so
 * the workbench is not painted for the length of one request and then
 * replaced by a page about it; a visitor the check does let in sees the
 * workbench one request later, exactly as before. */
function mayLand() {
  return location.pathname === "/" && !api.getSessionToken() && !api.getAccessCode();
}

async function ensureAccess() {
  if (mayLand()) $("#workbench").hidden = true;
  try {
    await decideAccess();
  } finally {
    $("#workbench").hidden = false;
  }
}

async function decideAccess() {
  if (location.pathname === "/reset") {
    // The person holding the link has no password, so no session decides
    // anything here: the gate opens on the new-password form, and signs
    // them in with it afterwards. The sign-in configuration comes from its
    // own request, since the boot's access check is skipped. A deployment
    // without accounts has no such page and falls through to its usual boot.
    const token = takeResetToken();
    authConfig = await api.authConfig().catch(() => null);
    if (authConfig?.enabled) {
      await showGate(null, { reset: token });
      return;
    }
  }
  if (location.pathname === "/verify") {
    // Said before the boot below, which waits at the gate when nobody is
    // signed in here: a link opened in another browser must still get its
    // answer. With a session stored, the boot reads the account's state
    // after the token was spent, so the notice is already gone when the
    // page appears.
    const verified = await consumeVerificationLink();
    const key = verified.key === "verify_done" && !api.getSessionToken() ? "verify_done_sign_in" : verified.key;
    toast(t(key), verified.variant);
  }
  try {
    // Keys alone boot without a request, as they always have. With a session
    // stored, the access check below decides instead; on a deployment with
    // accounts, a keys-only visitor learns to sign in at their first paid
    // request and reaches the gate through the badge.
    if (api.getByok() && !api.getSessionToken()) {
      applyByokMode();
      return;
    }
  } catch (err) {
    if (err.code !== "invalid_byok") throw err;
    // Even a valid residual access code cannot choose a different payer for
    // a corrupted BYOK session. Only an explicit gate submission can do so.
    await showGate("invalid_byok");
    return;
  }
  try {
    // One boot request, carrying the stored code and session, answers
    // everything: whether the deployment is gated, whether this is an
    // account, and what the gate should offer if it is not.
    const access = await api.checkAccess(api.getAccessCode());
    planPreviewEnabled = access?.plan_preview === true;
    quotaEnabled = access?.daily_quota === true;
    authConfig = access?.accounts ?? null;
    if (access?.account) {
      applyAccountMode(access.account);
      // Not for an account about to use its trial: the keys card would be the
      // first thing a newcomer sees, in front of the one run that needs none.
      if (!api.getByok() && !operatorPays() && !trialPays()) await showGate(null, { keysOnly: true });
      return;
    }
    if (api.getAccessCode()) applyCodeMode();
    refreshQuota();
    return;
  } catch (err) {
    if (err.status !== 401) throw err;
    // The refusal says what the gate may offer; no second request needed.
    authConfig = err.body?.accounts ?? null;
  }
  // A shared run or comparison is read without an identity; everything
  // else on a gated deployment is the workbench, which needs one.
  if (sharedPath()) {
    enterViewer();
    return;
  }
  if (landingWanted()) await showLanding();
  else await showGate();
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

/* Beside the invite code field: who gives out codes.
 *
 * The operator's contact is whatever they chose to publish on the privacy
 * page, an address or a sentence, so it is placed as text and never as
 * markup. It becomes a mail link only when it is plainly an address. With
 * no contact published, the line says what the access code form has always
 * said: ask whoever shared the link.
 */
function paintInviteHint(shown) {
  const hint = $("#account-invite-hint");
  hint.hidden = !shown;
  hint.innerHTML = "";
  if (!shown) return;
  const contact = typeof authConfig?.contact === "string" ? authConfig.contact.trim() : "";
  if (!contact) {
    hint.append(t("account_invite_hint_ask"));
    return;
  }
  const [before, after = ""] = t("account_invite_hint").split("{contact}");
  const address = /^[^\s@<>"']+@[^\s@<>"']+\.[^\s@<>"']+$/.test(contact);
  const who = document.createElement(address ? "a" : "span");
  who.textContent = contact;
  if (address) who.href = `mailto:${contact}`;
  hint.append(before, who, after);
}

/* What to tell an account about keys a provider did not accept, or null.
 *
 * Names the service, never quotes it: provider error text can repeat part of
 * the key. A model the provider does not list is reported the same way, since
 * a misspelt model name fails a run exactly as a wrong key does. */
const PROVIDER_NAMES = { deepseek: "DeepSeek", qwen: "Qwen", openai: "OpenAI", anthropic: "Anthropic" };
const SEARCH_NAMES = { tavily: "Tavily", serper: "Serper" };
function keyProblem(verdict, creds) {
  if (!verdict || verdict.checked === false) return null;
  const provider = PROVIDER_NAMES[creds.provider] ?? creds.provider;
  const service = SEARCH_NAMES[creds.search] ?? creds.search;
  const problems = [];
  if (verdict.llm === "rejected") problems.push(t("byok_rejected_llm").replace("{provider}", provider));
  else if (verdict.model === "not_listed") {
    problems.push(t("byok_model_not_listed").replace("{provider}", provider).replace("{model}", creds.model));
  }
  if (verdict.search === "rejected") problems.push(t("byok_rejected_search").replace("{service}", service));
  // One line each (the element keeps line breaks): reads the same in every language.
  return problems.length ? [...problems, t("byok_problem_next")].join("\n") : null;
}

/* `creating` opens the account form ready to register, as the landing's
 * "Create account" promises; `back` shows a way to put the card down again,
 * resolving "back" instead of letting anyone in. Both are the landing's. */
// `reset` is the token from a reset link: the card opens on the new-password form.
function showGate(errorKey = null, { keysOnly = false, creating: startCreating = false, back = false, reset = null } = {}) {
  const gate = $("#gate");
  // The card always sits on one of the two pages. The boot may have kept the
  // workbench back in case this visit ended on the landing; it did not.
  if ($("#landing").hidden) $("#workbench").hidden = false;
  const codeForm = $("#gate-form");
  const codeInput = $("#gate-input");
  const codeError = $("#gate-error");
  const codeSubmit = $("#gate-submit");
  const byokForm = $("#byok-form");
  const accountForm = $("#account-form");
  const forgotForm = $("#forgot-form");
  const resetForm = $("#reset-form");
  const accountError = $("#account-error");
  const accountSubmit = $("#account-submit");
  const accountsOn = Boolean(authConfig?.enabled);
  // Whether the key form belongs to a signed-in account (keys saved, no
  // payer change) or to an anonymous visitor (keys are the identity).
  const forAccount = () => accountMode;
  let creating = startCreating && Boolean(authConfig?.signup_open);
  let inviteNeeded = false;
  // Shown only while there is a landing under the card to go back to: not
  // once an account is in, when the card has become its own key form.
  const backButton = $("#gate-back");
  const syncBack = () => { backButton.hidden = !back || forAccount(); };

  // Storage-denied logout reuses this document. Clear previous inputs and
  // replace the gate-owned handlers below instead of accumulating closures
  // that would validate one submission several times after repeated login.
  codeForm.reset();
  byokForm.reset();
  accountForm.reset();
  forgotForm.reset();
  resetForm.reset();
  $("#forgot-sent").hidden = true;
  $("#forgot-error").hidden = true;
  $("#reset-error").hidden = true;
  $("#account-settings").hidden = true;
  codeError.hidden = !errorKey;
  codeError.textContent = errorKey ? t(errorKey) : "";
  // With a first assessment on the deployment's keys the card must not
  // tell a newcomer that every run is paid for with keys they bring.
  $("#account-sub").hidden = authConfig?.trial_runs > 0;
  $("#account-sub-trial").hidden = !(authConfig?.trial_runs > 0);
  accountError.hidden = true;
  gate.hidden = false;

  const byokError = $("#byok-error");
  const byokSubmit = $("#byok-submit");
  // The key set a provider objected to and the person chose to keep anyway.
  let overridden = null;
  let checking = false;
  const byokLabel = () => t(overridden ? "byok_save_anyway" : forAccount() ? "byok_save" : "byok_submit");
  const clearKeyProblem = () => {
    overridden = null;
    byokError.hidden = true;
    byokError.textContent = "";
    if (!checking) byokSubmit.textContent = byokLabel();
  };
  byokError.hidden = true;
  byokSubmit.disabled = false;
  // Any edit asks for a fresh check: "save anyway" belongs to the exact keys
  // the provider was asked about, not to whatever is typed next.
  byokForm.oninput = clearKeyProblem;
  byokForm.onchange = clearKeyProblem;

  const showKeys = () => {
    codeForm.hidden = true;
    accountForm.hidden = true;
    forgotForm.hidden = true;
    resetForm.hidden = true;
    byokForm.hidden = false;
    const account = forAccount();
    $("#byok-account-note").hidden = !account;
    $("#byok-sub").hidden = account;
    if (account) $("#byok-account-note").textContent = t(operatorPays() ? "byok_admin_note" : trialPays() ? "byok_trial_note" : "byok_account_note").replace("{email}", accountEmail);
    clearKeyProblem();
    $("#byok-to-gate").hidden = account || !authConfig?.access_codes && accountsOn;
    $("#byok-skip").hidden = !account;
    syncBack();
    $("#byok-llm-key").focus();
    showByokRetention();
  };
  const showAccount = () => {
    codeForm.hidden = true;
    byokForm.hidden = true;
    forgotForm.hidden = true;
    resetForm.hidden = true;
    accountForm.hidden = false;
    $("#account-title").textContent = t(creating ? "account_title_create" : "account_title");
    accountSubmit.textContent = t(creating ? "account_create" : "account_sign_in");
    $("#account-toggle").textContent = t(creating ? "account_toggle_to_sign_in" : "account_toggle_to_create");
    $("#account-toggle").hidden = !creating && !authConfig?.signup_open;
    $("#account-to-code").hidden = !authConfig?.access_codes;
    // Only when the deployment can send the link; a visitor creating an
    // account has no password to have forgotten.
    $("#account-forgot").hidden = creating || !authConfig?.password_reset;
    $("#account-password").autocomplete = creating ? "new-password" : "current-password";
    // Invite mode asks up front; a reserved address asks after the server
    // says so (invite_required), so the field stays hidden until needed.
    const inviteShown = creating && (authConfig?.signup === "invite" || inviteNeeded);
    $("#account-invite").hidden = !inviteShown;
    paintInviteHint(inviteShown);
    syncBack();
    $("#account-email-input").focus();
  };
  const showCode = () => {
    accountForm.hidden = true;
    byokForm.hidden = true;
    forgotForm.hidden = true;
    resetForm.hidden = true;
    codeForm.hidden = false;
    $("#gate-to-byok").hidden = accountsOn;
    $("#gate-to-account").hidden = !accountsOn;
    syncBack();
    codeInput.focus();
  };
  const showForgot = () => {
    codeForm.hidden = true;
    byokForm.hidden = true;
    accountForm.hidden = true;
    resetForm.hidden = true;
    forgotForm.hidden = false;
    // The address they were about to sign in with is the one they mean.
    if (!$("#forgot-email").value) $("#forgot-email").value = $("#account-email-input").value.trim();
    $("#forgot-sent").hidden = true;
    $("#forgot-error").hidden = true;
    syncBack();
    $("#forgot-email").focus();
  };
  const showReset = () => {
    codeForm.hidden = true;
    byokForm.hidden = true;
    accountForm.hidden = true;
    forgotForm.hidden = true;
    resetForm.hidden = false;
    $("#reset-error").hidden = true;
    syncBack();
    $("#reset-password").focus();
  };
  if (reset !== null) showReset();
  else if (keysOnly) showKeys();
  else if (accountsOn) showAccount();
  else showCode();

  return new Promise((resolve) => {
    let finished = false;
    const finish = () => {
      finished = true;
      gate.hidden = true;
      if (api.storageDegraded()) showStorageNotice();
      resolve();
    };

    $("#gate-to-byok").onclick = () => {
      if (codeSubmit.disabled || finished) return;
      showKeys();
    };
    $("#gate-to-account").onclick = () => {
      if (codeSubmit.disabled || finished) return;
      showAccount();
    };
    $("#account-to-code").onclick = () => {
      if (accountSubmit.disabled || finished) return;
      showCode();
    };
    $("#account-toggle").onclick = () => {
      if (accountSubmit.disabled || finished) return;
      creating = !creating;
      accountError.hidden = true;
      showAccount();
    };
    $("#byok-to-gate").onclick = () => {
      if (codeSubmit.disabled || finished) return;
      if (accountsOn && !authConfig?.access_codes) showAccount();
      else showCode();
    };
    $("#byok-skip").onclick = () => {
      if (finished) return;
      finish();
    };
    backButton.onclick = () => {
      if (finished || backButton.hidden || accountSubmit.disabled || codeSubmit.disabled || checking) return;
      finished = true;
      gate.hidden = true;
      resolve("back");
    };

    $("#account-forgot").onclick = () => {
      if (accountSubmit.disabled || finished) return;
      showForgot();
    };
    $("#forgot-back").onclick = $("#reset-back").onclick = () => {
      if (finished || $("#forgot-submit").disabled || $("#reset-submit").disabled) return;
      creating = false;
      accountError.hidden = true;
      showAccount();
    };

    forgotForm.onsubmit = async (e) => {
      e.preventDefault();
      const email = $("#forgot-email").value.trim();
      const submit = $("#forgot-submit");
      const sent = $("#forgot-sent");
      const error = $("#forgot-error");
      if (!email || submit.disabled || finished) return;
      submit.disabled = true;
      sent.hidden = true;
      error.hidden = true;
      try {
        await api.forgotPassword(email);
        // The same words whether or not an account has the address: the
        // server said nothing either way, and neither does the page.
        sent.textContent = t("forgot_sent").replace("{email}", email);
        sent.hidden = false;
      } catch (err) {
        error.textContent = err.code === "mail_unavailable" ? t("forgot_unavailable") : err.message;
        error.hidden = false;
      } finally {
        submit.disabled = false;
      }
    };

    resetForm.onsubmit = async (e) => {
      e.preventDefault();
      const password = $("#reset-password").value;
      const submit = $("#reset-submit");
      const error = $("#reset-error");
      if (!password || submit.disabled || finished) return;
      submit.disabled = true;
      error.hidden = true;
      try {
        if (!reset) throw Object.assign(new Error(t("reset_invalid")), { code: "reset_invalid" });
        const done = await api.resetPassword(reset, password);
        // Every session of the account ended on the server, one stored in
        // this browser included; the new password is the way in now.
        api.setSessionToken(null);
        reset = null;
        toast(t("reset_done"), "success");
        creating = false;
        showAccount();
        $("#account-email-input").value = done.email;
        $("#account-password").focus();
      } catch (err) {
        const key = {
          reset_invalid: "reset_invalid", reset_expired: "reset_expired",
          weak_password: "account_error_weak", disabled: "reset_disabled",
        }[err.code];
        error.textContent = key ? t(key) : err.message;
        error.hidden = false;
        $("#reset-password").select();
      } finally {
        submit.disabled = false;
      }
    };

    accountForm.onsubmit = async (e) => {
      e.preventDefault();
      const email = $("#account-email-input").value.trim();
      const password = $("#account-password").value;
      if (!email || !password || accountSubmit.disabled || finished) return;
      accountSubmit.disabled = true;
      accountError.hidden = true;
      try {
        const invite = $("#account-invite").value.trim() || null;
        const session = creating ? await api.register(email, password, invite) : await api.login(email, password);
        api.setSessionToken(session.token);
        applyAccountMode(session);
        // The boot's access check was refused, so it told the page nothing
        // about previews; the sign-in configuration that came with that
        // refusal does. Without this an account that had just signed in
        // started its first run with no preview, and one that reloaded got one.
        planPreviewEnabled = authConfig?.plan_preview === true;
        // Likewise the account's own daily allowance, so it shows from the first run.
        quotaEnabled = authConfig?.daily_quota === true;
        refreshQuota();
        // Keys next, on the same card, unless the account has them already
        // or the deployment pays for this administrator's runs.
        if (api.getByok() || operatorPays() || trialPays()) { finish(); return; }
        showKeys();
      } catch (err) {
        const key = {
          invalid_credentials: "account_error_credentials", email_taken: "account_error_taken",
          weak_password: "account_error_weak", invalid_email: "account_error_email",
          signup_closed: "account_error_closed", locked: "account_error_locked",
          invite_required: "account_error_invite", signup_throttled: "account_error_throttled",
        }[err.code];
        accountError.textContent = key ? t(key) : err.message;
        accountError.hidden = false;
        if (err.code === "invite_required") {
          inviteNeeded = true;
          $("#account-invite").hidden = false;
          paintInviteHint(true);
          $("#account-invite").focus();
        } else {
          $("#account-password").select();
        }
      } finally {
        accountSubmit.disabled = false;
      }
    };

    codeForm.onsubmit = async (e) => {
      e.preventDefault();
      const code = codeInput.value.trim();
      if (!code || codeSubmit.disabled || finished) return;

      codeSubmit.disabled = true;
      codeError.hidden = true;
      try {
        const access = await api.checkAccess(code);
        planPreviewEnabled = access?.plan_preview === true;
        quotaEnabled = access?.daily_quota === true;
        api.setAccessCode(code);
        applyCodeMode();
        refreshQuota();
        finish();
      } catch (err) {
        codeError.textContent = err.status === 401 ? t("gate_error") : err.message;
        codeError.hidden = false;
        codeInput.select();
      } finally {
        codeSubmit.disabled = false;
      }
    };

    byokForm.onsubmit = async (e) => {
      e.preventDefault();
      if (codeSubmit.disabled || finished || checking) return;
      const provider = $("#byok-provider").value;
      const llmKey = $("#byok-llm-key").value.trim();
      // Required, like the keys: there is no default model to fall back on.
      const model = $("#byok-model").value.trim();
      const search = $("#byok-search").value;
      const searchKey = $("#byok-search-key").value.trim();
      if (!llmKey || !model || !searchKey) return;
      const creds = { provider, llmKey, search, searchKey, ...(model ? { model } : {}) };

      // An account saving keys has the providers asked about them first. Only
      // an account: for an anonymous visitor the keys are the identity and
      // saving them stays the single synchronous step it has always been.
      let unverified = false;
      const fingerprint = JSON.stringify(creds);
      if (forAccount() && authConfig?.key_check === true && overridden !== fingerprint) {
        checking = true;
        byokSubmit.disabled = true;
        byokSubmit.textContent = t("byok_checking");
        byokError.hidden = true;
        let verdict = null;
        try {
          verdict = await api.checkKeys(creds);
        } catch {
          // No answer is not a refusal: a check that cannot run never stands
          // between an account and keys that may be perfectly good.
          verdict = null;
        }
        checking = false;
        byokSubmit.disabled = false;
        byokSubmit.textContent = byokLabel();
        // The gate may have moved on while the providers were being asked.
        if (finished || byokForm.hidden || !forAccount()) return;
        const problem = keyProblem(verdict, creds);
        if (problem) {
          overridden = fingerprint;
          byokError.textContent = problem;
          byokError.hidden = false;
          // The card scrolls; keep what the provider said next to the button just pressed.
          byokError.scrollIntoView?.({ block: "nearest" });
          byokSubmit.textContent = byokLabel();
          return;
        }
        unverified = !verdict || verdict.checked === false
          || verdict.llm !== "accepted" || verdict.search !== "accepted";
      }

      try {
        api.setByok(creds);
      } catch (err) {
        toast(operationErrorMessage(err), "error");
        return;
      }
      if (forAccount()) {
        // Keys saved for the account; the identity and its history are unchanged.
        byokMode = true;
        invalidateSidebar();
        if (unverified) toast(t("byok_unverified"));
        finish();
        return;
      }
      applyByokMode();
      finish();
    };
  });
}

/* ── Comparing two runs ────────────────────────────────────────────── */

/* The run page's "Compare": pick a second finished run, then the view at
 * /compare/<this>/<that>. The list is the identity's own history, from the
 * same request the rail makes; the dialog sends nothing else. */
function compareButton() {
  const runId = activeRunId;
  const compare = document.createElement("button");
  compare.type = "button";
  compare.className = "btn btn--secondary";
  compare.id = "run-compare";
  compare.textContent = t("compare");
  compare.title = t("compare_title_hint");
  compare.addEventListener("click", () => pickComparison(runId));
  return compare;
}

async function pickComparison(runId) {
  const dialog = $("#compare-dialog");
  const list = $("#compare-choices");
  list.innerHTML = "";
  $("#compare-empty").hidden = true;
  dialog.showModal();
  let runs = [];
  try {
    runs = (await api.listRuns(200)).runs ?? [];
  } catch (err) {
    dialog.close();
    toast(operationErrorMessage(err), "error");
    return;
  }
  const others = runs.filter((run) => run.state === "completed" && run.run_id !== runId);
  $("#compare-empty").hidden = others.length > 0;
  for (const run of others) {
    const item = document.createElement("li");
    const choose = document.createElement("button");
    choose.type = "button";
    choose.className = "picker__choice";
    choose.dataset.runId = run.run_id;
    const when = compareView.startedAt(run.run_id);
    const label = document.createElement("span");
    label.className = "picker__topic";
    label.textContent = run.topic || run.run_id;
    const meta = document.createElement("span");
    meta.className = "picker__meta tabular";
    meta.textContent = [when ? when.toLocaleDateString() : null, run.owner_label || null].filter(Boolean).join(" · ");
    choose.append(label, meta);
    choose.addEventListener("click", () => {
      dialog.close();
      openCompare(runId, run.run_id, { push: true });
    });
    item.append(choose);
    list.append(item);
  }
}

$("#compare-cancel").addEventListener("click", () => $("#compare-dialog").close());

let comparePair = null;      // [a, b] on screen
let compareModel = null;

function showCompare() {
  stopFollowing();
  activeRunId = null;
  syncSourceLocatorLink();
  $("#pane-compose").hidden = true;
  $("#pane-run").hidden = true;
  $("#pane-compare").hidden = false;
  refreshSidebar();
  scheduleCapacity();
}

function renderCompare() {
  if (!compareModel) return;
  compareView.render($("#compare-body"), compareModel, { onOpen: (id) => openRun(id) });
}

async function openCompare(a, b, { push = false } = {}) {
  showCompare();
  comparePair = [a, b];
  compareModel = null;
  const body = $("#compare-body");
  body.innerHTML = "";
  body.append(Object.assign(document.createElement("p"), { className: "empty-note", textContent: t("compare_loading") }));
  if (push) {
    try { history.pushState({}, "", `/compare/${a}/${b}`); }
    catch { toast(t("msg_history_unavailable"), "error"); }
  }
  const [left, right] = await Promise.all([compareView.load(a), compareView.load(b)]);
  // The reader may have moved on while the reads were out.
  if (!comparePair || comparePair[0] !== a || comparePair[1] !== b) return;
  compareModel = compareView.comparison(left, right);
  renderCompare();
}

$("#compare-swap").addEventListener("click", () => {
  if (!comparePair) return;
  const [a, b] = comparePair;
  openCompare(b, a, { push: true });
});
$("#compare-back").addEventListener("click", () => {
  if (comparePair) openRun(comparePair[0]);
});

/* ── Routing ───────────────────────────────────────────────────────── */

function routeFromLocation() {
  const match = location.pathname.match(/^\/run\/([^/]+)$/);
  const pair = location.pathname.match(/^\/compare\/([^/]+)\/([^/]+)$/);
  if (match) {
    openRun(match[1]);
  } else if (pair) {
    openCompare(pair[1], pair[2]);
  } else {
    stopFollowing();
    activeRunId = null;
    syncSourceLocatorLink();
    $("#pane-compose").hidden = false;
    $("#pane-run").hidden = true;
    $("#pane-compare").hidden = true;
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
  paintTrialNote();
  localizeSourceLocatorLink();
  renderPlan();
  paintQuota();
  paintPaidReceipt();
  paintCapacityLabel();
  renderCompare();
  topic.placeholder = t("topic_placeholder");
  // Re-render whatever is on screen so switching mid-run does not leave a
  // half-translated pane behind.
  refreshSidebar();
  if (activeRunId) openRun(activeRunId);
});

/* ── Boot ──────────────────────────────────────────────────────────── */

i18n.apply();
localizeSourceLocatorLink();
topic.placeholder = t("topic_placeholder");
syncComposer();

function paintPaidReceipt() {
  const state = paidReceipts.state();
  let saved = [], unreadable = false;
  try { saved = api.pendingReceiptKeys(); } catch { unreadable = true; }
  const degraded = state.unavailable || api.receiptStorageDegraded();
  $("#paid-receipt-notice").hidden = !state.uncertain && !state.active && !degraded && !saved.length && !unreadable;
  $("#paid-receipt-message").textContent = [
    state.uncertain ? t("paid_receipt_unknown") : state.active ? t("paid_receipt_inflight") : "",
    state.unavailable ? t("paid_receipt_unavailable") : "",
  ].filter(Boolean).join(" ");
  $("#paid-receipt-helper").textContent = [
    api.receiptStorageDegraded() && !state.unavailable ? t("paid_receipt_unavailable") : "",
    unreadable ? t("receipt_history_unreadable") : saved.length ? t("receipt_lookup_hint") : "",
  ].filter(Boolean).join(" ");
  $("#paid-receipt-lookup").hidden = !saved.length;
  $("#paid-receipt-lookup").disabled = receiptLookupActive || Boolean(state.active);
  $("#paid-receipt-ack").hidden = !state.uncertain;
  $("#paid-receipt-ack").disabled = Boolean(state.active);
  syncComposer();
  $$('[data-resume-run]').forEach((button) => {
    button.disabled = state.uncertain || pendingResumes.has(button.dataset.resumeRun);
  });
}
$("#paid-receipt-lookup").addEventListener("click", async () => {
  if (receiptLookupActive || paidReceipts.state().active) return;
  const generation = receiptViewGeneration;
  const entries = api.pendingReceiptKeys();
  const container = $("#paid-receipt-results");
  container.innerHTML = "";
  receiptLookupActive = true;
  paintPaidReceipt();
  try {
    // Only bounded GETs; neither an absent receipt nor an unknown outcome
    // may become an automatic POST, resume, cancellation or quota refund.
    for (const entry of entries) {
      if (generation !== receiptViewGeneration) break;
      const row = document.createElement("p");
      container.append(row);
      try {
        const receipt = await api.getPaidReceipt(entry.key);
        if (generation !== receiptViewGeneration) break;
        if (receipt.state !== "accepted") {
          row.textContent = t(receipt.state === "failed" ? "receipt_failed" : "receipt_unresolved");
          if (receipt.operation === "paper") row.textContent += " · " + runView.auxiliarySummary(receipt.auxiliary_usage);
          continue;
        }
        const body = receipt.response;
        const paper = receipt.operation === "paper";
        requirePaidIdentity(body, paper ? "paper_id" : "run_id");
        if (receipt.operation !== entry.operation || receipt.resource_id !== body[paper ? "paper_id" : "run_id"])
          throw new api.ApiError(503, "Receipt identity mismatch", "receipt_unavailable");
        row.textContent = paper ? t("receipt_paper_found") : t("receipt_run_found");
        if (paper) row.textContent += " · " + runView.auxiliarySummary(receipt.auxiliary_usage);
        const open = document.createElement("button");
        open.type = "button";
        open.className = "btn btn--secondary";
        open.textContent = t("receipt_open");
        open.addEventListener("click", async () => {
          if (generation !== receiptViewGeneration || submitting || extracting || pendingResumes.size) return;
          open.disabled = true;
          try {
            if (paper) {
              showCompose();
              clearAttachment();
              attachedPaper = body;
              paintAttachment(body);
            } else {
              rememberAcceptedRun(body);
              await openRun(body.run_id, {known: body});
            }
            api.forgetReceipt(entry.key);
            row.remove();
            paintPaidReceipt();
          } catch (err) { toast(operationErrorMessage(err), "error"); open.disabled = false; }
        });
        row.append(open);
      } catch (err) {
        if (generation !== receiptViewGeneration) break;
        // 404 may also mean a different code, not a free or unstarted request.
        row.textContent = t("receipt_lookup_unavailable");
      }
    }
  } finally { receiptLookupActive = false; paintPaidReceipt(); }
});
paidReceipts.subscribe(paintPaidReceipt);
$("#paid-receipt-ack").addEventListener("click", () => {
  if (!paidReceipts.state().active && confirm(t("paid_receipt_confirm"))) paidReceipts.acknowledge();
});
window.addEventListener("beforeunload", (event) => {
  if (!paidReceipts.state().active) return;
  // Best effort only: forced close/mobile process death may skip this event.
  // Do not send cancellation, retry, or a beacon from the unload handler.
  event.preventDefault();
  event.returnValue = "";
});
paintPaidReceipt();

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
  if (api.storageDegraded()) showStorageNotice();
  routeFromLocation();
  refreshSidebar();
  refreshCapacity();
  scheduleCapacity();
  markBoot("ready");
});
