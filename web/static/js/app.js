/* Application shell: view state, routing, and event wiring. */

import * as api from "./api.js";
import * as runView from "./run.js";
import * as sidebar from "./sidebar.js";
import * as result from "./result.js";
import * as i18n from "./i18n.js";
const t = i18n.t;

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/* One follower at a time. Navigating away from a run must stop its poll loop,
 * or every visited run keeps polling for the life of the page. */
let follower = null;
let activeRunId = null;

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
  $("#topic").focus();
}

function showRun(runId) {
  activeRunId = runId;
  $("#pane-compose").hidden = true;
  $("#pane-run").hidden = false;
  refreshSidebar();
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

function paintHeader({ topic, state, elapsed_seconds, source_counts }) {
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
}

function paintActions(state) {
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
    const download = document.createElement("a");
    download.className = "btn btn--secondary";
    download.href = `/api/runs/${activeRunId}/report`;
    download.download = `${activeRunId}.md`;
    download.innerHTML = `
      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path d="M8 2.5v8m0 0L4.5 7M8 10.5L11.5 7M3 12.5v.5a1 1 0 001 1h8a1 1 0 001-1v-.5"
              stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>`;
    download.append(t("download_report"));
    actions.append(download);
  }
}

async function openRun(runId, { known } = {}) {
  stopFollowing();
  showRun(runId);

  const body = $("#run-body");
  body.innerHTML = "";
  paintHeader({ topic: known?.topic ?? "…", state: known?.state ?? "running" });
  paintActions(known?.state ?? "running");
  history.pushState({}, "", `/run/${runId}`);

  follower = runView.follow(runId, {
    onUpdate(progress) {
      paintHeader(progress);
      paintActions(progress.state);
      runView.renderStages(body, runView.stageStates(progress.stage, progress.state));
    },
    onDone(progress) {
      paintHeader(progress);
      paintActions(progress.state);
      runView.renderStages(body, runView.stageStates(progress.stage, progress.state));
      refreshSidebar();

      if (progress.state === "completed") {
        toast(t("msg_complete"), "success");
      } else if (progress.error) {
        toast(progress.error, "error");
      }

      // A failed run keeps its stage list: where it stopped is the useful
      // information, and it has no artifacts to show anyway.
      if (progress.artifacts.length) {
        result.render(body, runId, { artifacts: progress.artifacts });
      }
    },
    onError(err) {
      toast(err.message, "error");
    },
  });
}

/* ── Sidebar ───────────────────────────────────────────────────────── */

function refreshSidebar() {
  return sidebar.refresh($("#runlist"), {
    activeId: activeRunId,
    onSelect: (runId) => openRun(runId),
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
  runBtn.disabled = true;

  try {
    const accepted = await api.startRun({
      topic: topic.value.trim(),
      language: $("#language").value,
      weight_profile: $("#profile").value,
      paper_id: attachedPaper?.paper_id,
    });
    topic.value = "";
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
    const { active_runs, max_concurrent } = await api.health();
    const dots = $("#capacity-dots");
    dots.innerHTML = "";
    for (let i = 0; i < max_concurrent; i += 1) {
      const dot = document.createElement("span");
      dot.className = "capacity__dot";
      dot.dataset.busy = String(i < active_runs);
      dots.append(dot);
    }
    $("#capacity-label").textContent = `${active_runs}/${max_concurrent} ${t("running_label")}`;
  } catch {
    $("#capacity-label").textContent = t("offline");
  }
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
routeFromLocation();
refreshSidebar();
refreshCapacity();
setInterval(refreshCapacity, 15000);
