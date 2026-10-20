/* Sample-report reader: list committed examples and render one.
 *
 * Plain fetch rather than api.js: that client attaches the stored access code
 * and BYOK credentials, and this page must not send either. The two endpoints
 * it reads serve committed files and need neither.
 *
 * Rendering goes through result.js's renderMarkdown, the same escaping path a
 * real report takes (and the one tests/test_web_markdown.py exercises), so a
 * sample cannot reach innerHTML by a less-checked route. */

import { renderMarkdown } from "./result.js";
import * as i18n from "./i18n.js";
import { applySamples, st as t } from "./samples_i18n.js";

const $ = (sel) => document.querySelector(sel);
const listNode = $("#sample-list");
const reader = $("#sample-reader");

let samples = [];
let current = null;
// A slow response for a sample the visitor has already left must not paint
// over the one they chose next.
let generation = 0;

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
};

function slugFromLocation() {
  const match = location.pathname.match(/^\/samples\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function note(key) {
  reader.replaceChildren(el("p", "empty-note", t(key)));
}

function paintList() {
  listNode.replaceChildren(...samples.map((sample) => {
    const card = el("a", "sample-card");
    card.href = `/samples/${encodeURIComponent(sample.slug)}`;
    if (sample.slug === current) card.setAttribute("aria-current", "page");
    card.append(
      el("span", "sample-card__title", sample.title),
      el("span", "sample-card__meta", `${sample.committed} · ${sample.commit}`),
    );
    card.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      try { history.pushState({}, "", card.href); } catch { /* still render */ }
      open(sample.slug);
    });
    return card;
  }));
}

function historicalNotice(sample) {
  const text = t("samples_historical")
    .replace("{date}", sample.committed)
    .replace("{commit}", sample.commit);
  return el("p", "samples__notice", text);
}

async function open(slug) {
  const sample = samples.find((item) => item.slug === slug);
  current = sample ? slug : null;
  paintList();
  if (!sample) { note("samples_missing"); return; }

  const mine = ++generation;
  reader.replaceChildren(el("div", "skeleton", ""));
  let markdown;
  try {
    const response = await fetch(`/api/samples/${encodeURIComponent(slug)}`);
    if (!response.ok) throw new Error(String(response.status));
    markdown = await response.text();
  } catch {
    if (mine === generation) note("samples_read_failed");
    return;
  }
  if (mine !== generation) return;

  const article = el("article", "prose");
  article.innerHTML = renderMarkdown(markdown);
  reader.replaceChildren(historicalNotice(sample), article);
}

function route() {
  // No slug: open the first sample so the page shows a report at once
  // rather than an empty reader the visitor has to work out how to fill.
  const slug = slugFromLocation() ?? samples[0]?.slug ?? null;
  if (slug) open(slug);
  else note("samples_choose");
}

const langSelect = $("#ui-lang");
langSelect.value = i18n.language();
langSelect.addEventListener("change", () => {
  i18n.setLanguage(langSelect.value);
  applySamples();
  if (current) open(current);
});
window.addEventListener("popstate", route);

i18n.apply();
applySamples();
try {
  const response = await fetch("/api/samples");
  if (!response.ok) throw new Error(String(response.status));
  samples = await response.json();
  route();
} catch {
  note("samples_list_failed");
}
