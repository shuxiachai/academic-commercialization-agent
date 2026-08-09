/* Workbench shell.
 *
 * Stage 2: layout behaviour only — sidebar, composer, view switching. The
 * pipeline wiring lands in stage 3.
 */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/* ── Sidebar ───────────────────────────────────────────────────────── */

const workbench = $("#workbench");
const NARROW = window.matchMedia("(max-width: 860px)");

$("#collapse-btn").addEventListener("click", () => {
  if (NARROW.matches) {
    const open = workbench.dataset.sidebarOpen === "true";
    workbench.dataset.sidebarOpen = String(!open);
  } else {
    const collapsed = workbench.dataset.collapsed === "true";
    workbench.dataset.collapsed = String(!collapsed);
    // Remembered because a collapsed rail is a working preference, not a
    // transient state — it should survive a reload.
    localStorage.setItem("sidebar-collapsed", String(!collapsed));
  }
});

if (localStorage.getItem("sidebar-collapsed") === "true" && !NARROW.matches) {
  workbench.dataset.collapsed = "true";
}

/* ── Composer ──────────────────────────────────────────────────────── */

const topic = $("#topic");
const count = $("#topic-count");
const runBtn = $("#run-btn");
const composer = $("#composer");

function autosize() {
  // Collapse first: without it the box only ever grows.
  topic.style.height = "auto";
  topic.style.height = `${topic.scrollHeight}px`;
}

function syncComposer() {
  const n = topic.value.trim().length;
  runBtn.disabled = n < 3;
  // The counter is noise until the limit is actually in view.
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

/* ── Attachment ────────────────────────────────────────────────────── */

const pdfInput = $("#pdf-input");
$("#attach-btn").addEventListener("click", () => pdfInput.click());

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
  })
);

/* ── Keyboard ──────────────────────────────────────────────────────── */

document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
  if (e.key === "n" && !typing && !e.metaKey && !e.ctrlKey) {
    e.preventDefault();
    showCompose();
  }
});

/* ── Views ─────────────────────────────────────────────────────────── */

export function showCompose() {
  $("#pane-compose").hidden = false;
  $("#pane-run").hidden = true;
  topic.focus();
}

export function showRun() {
  $("#pane-compose").hidden = true;
  $("#pane-run").hidden = false;
}

/* ── Toasts ────────────────────────────────────────────────────────── */

export function toast(message, variant = "") {
  const el = document.createElement("div");
  el.className = `toast${variant ? ` toast--${variant}` : ""}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 4200);
}

/* ── Capacity indicator ────────────────────────────────────────────── */

async function refreshCapacity() {
  try {
    const r = await fetch("/health");
    if (!r.ok) return;
    const { active_runs, max_concurrent } = await r.json();
    const dots = $("#capacity-dots");
    dots.innerHTML = "";
    for (let i = 0; i < max_concurrent; i += 1) {
      const dot = document.createElement("span");
      dot.className = "capacity__dot";
      dot.dataset.busy = String(i < active_runs);
      dots.append(dot);
    }
    $("#capacity-label").textContent = `${active_runs}/${max_concurrent} running`;
  } catch {
    $("#capacity-label").textContent = "offline";
  }
}

/* ── Boot ──────────────────────────────────────────────────────────── */

$("#new-run-btn").addEventListener("click", showCompose);

$("#compose-form").addEventListener("submit", (e) => {
  e.preventDefault();
  toast("Pipeline wiring lands next.");
});

syncComposer();
topic.focus();
refreshCapacity();
setInterval(refreshCapacity, 15000);
