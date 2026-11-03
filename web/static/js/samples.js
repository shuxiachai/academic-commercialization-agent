/* Sample-report reader: list committed examples and render one.
 *
 * Plain fetch rather than api.js: that client attaches the stored access code
 * and BYOK credentials, and this page must not send either. The two endpoints
 * it reads serve committed files and need neither.
 *
 * Rendering goes through result.js's renderMarkdown, the same escaping path a
 * real report takes (and the one tests/test_web_markdown.py exercises), so a
 * sample cannot reach innerHTML by a less-checked route. */

import { attachCitations, citationIndex, renderMarkdown } from "./result.js";
import * as i18n from "./i18n.js";
import { applySamples, st as t } from "./samples_i18n.js";

const $ = (sel) => document.querySelector(sel);
const listNode = $("#sample-list");
const reader = $("#sample-reader");

let samples = [];
let current = null;
// The sample whose report is on screen, null while one loads or after a failure.
let rendered = null;
// A slow response for a sample the visitor has already left must not paint
// over the one they chose next.
let generation = 0;
// From this width the contents sit beside the report and start open; below
// it they are a block above the report and start closed. samples.css uses
// the same width.
const wide = window.matchMedia?.("(min-width: 1280px)");
let contents = null;
wide?.addEventListener?.("change", () => { if (contents) contents.open = wide.matches; });
// Served for /samples and every /samples/<slug>; shown again whenever no
// sample matches, so an unknown slug does not keep the last sample's name.
const defaultTitle = document.title;

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
      // The commit stays in the notice above the report; a visitor reading the
      // list needs only how old the sample is.
      el("span", "sample-card__meta", t("samples_added").replace("{date}", sample.committed)),
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

/** Name the tab after the open sample, so tabs, bookmarks and history entries
 * for different samples can be told apart. Set when the selection changes,
 * like the list's aria-current, not after the fetch: a slow response for a
 * sample already left is dropped by `generation` and must not leave its name
 * behind either. */
function showTitle(sample) {
  document.title = sample ? `${sample.title} · ${t("samples_title")}` : defaultTitle;
}

/** A contents list linking every section heading of the rendered article.
 * The ids come from a counter, not the heading text, so the Chinese sample
 * gets working links too. Built from the article it is shown with, so
 * another sample or a language switch cannot keep stale entries. */
function contentsFor(article) {
  const headings = [...article.querySelectorAll("h2")];
  if (!headings.length) return null;
  const list = el("ol");
  headings.forEach((heading, index) => {
    heading.id = `section-${index + 1}`;
    const link = el("a", null, heading.textContent);
    link.href = `#${heading.id}`;
    const item = el("li");
    item.append(link);
    list.append(item);
  });
  const block = el("details");
  block.open = wide?.matches ?? false;
  block.append(el("summary", null, t("samples_contents")), list);
  const nav = el("nav", "samples__toc");
  nav.setAttribute("aria-label", t("samples_contents"));
  nav.append(block);
  contents = block;
  return { nav, headings };
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
  rendered = null;
  contents = null;
  paintList();
  showTitle(sample);
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
  // The sample's own reference list feeds the citation cards; there is no
  // source registry behind a sample, so there is no "show in Sources" either.
  const index = citationIndex(markdown);
  attachCitations(article, () => Promise.resolve(index));
  const toc = contentsFor(article);
  reader.replaceChildren(historicalNotice(sample), ...(toc ? [toc.nav] : []), article);
  rendered = slug;
  // The browser looked for a #section-N target before the report existed:
  // a shared link to a section, Back to one from another sample, or a
  // language switch while reading one.
  const anchor = location.hash ? location.hash.slice(1) : "";
  toc?.headings.find((heading) => heading.id === anchor)?.scrollIntoView();
}

function route() {
  // No slug: open the first sample so the page shows a report at once
  // rather than an empty reader the visitor has to work out how to fill.
  const slug = slugFromLocation() ?? samples[0]?.slug ?? null;
  if (slug) open(slug);
  else { showTitle(null); note("samples_choose"); }
}

const langSelect = $("#ui-lang");
langSelect.value = i18n.language();
langSelect.addEventListener("change", () => {
  i18n.setLanguage(langSelect.value);
  applySamples();
  if (current) open(current);
});
window.addEventListener("popstate", () => {
  // Following a contents link changes only the fragment, and Chromium fires
  // popstate for it. The browser has already scrolled to the heading, so
  // re-reading the sample would only throw the position away.
  if (rendered && (slugFromLocation() ?? samples[0]?.slug) === rendered) return;
  route();
});

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
