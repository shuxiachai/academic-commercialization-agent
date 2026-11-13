/* Sample-report reader: list committed examples and render one.
 *
 * Plain fetch rather than api.js: that client attaches the stored access code
 * and BYOK credentials, and this page must not send either. The sample
 * endpoints serve committed files and need neither; the one other read,
 * /api/site, is the deployment's public facts, of which this page wants one:
 * whether it has accounts and takes new ones.
 *
 * Rendering goes through result.js's renderMarkdown, the same escaping path a
 * real report takes (and the one tests/test_web_markdown.py exercises), so a
 * sample cannot reach innerHTML by a less-checked route. */

import {
  attachCitations, citationIndex, decisionBrief, renderDecisionBrief, renderMarkdown, renderScorecard, sampleFacts,
} from "./result.js";
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
// The run's scorecard, in a block above the report. It follows the same
// width: open where the contents beside the report make the report one press
// away, closed on a narrow screen, where it is two screens of its own between
// the reader and the report they came for.
let scorecard = null;
wide?.addEventListener?.("change", () => {
  if (contents) contents.open = wide.matches;
  if (scorecard) scorecard.open = wide.matches;
});
// What this deployment offers someone who has read a sample and wants a
// report of their own: null until the server has said, and for good when it
// could not be asked.
let accounts = null;
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
  let active = null;
  listNode.replaceChildren(...samples.map((sample) => {
    const card = el("a", "sample-card");
    card.href = `/samples/${encodeURIComponent(sample.slug)}`;
    if (sample.slug === current) { card.setAttribute("aria-current", "page"); active = card; }
    // The verdict, the readiness level and the report's language, where the
    // list carried them. The six samples run from 48.6 to 74.9; before
    // 2026-11-13 a visitor had to open each one to learn that.
    const facts = sampleFacts(sample);
    card.append(el("span", "sample-card__title", sample.title));
    if (facts.verdict) {
      const verdict = el("span", "sample-card__verdict", facts.verdict);
      verdict.dataset.tone = facts.tone;
      card.append(verdict);
    }
    card.append(
      // The commit stays in the notice above the report; a visitor reading the
      // list needs only how old the sample is.
      el("span", "sample-card__meta", [facts.trl, facts.language, t("samples_added").replace("{date}", sample.committed)].filter(Boolean).join(" · ")),
    );
    card.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      try { history.pushState({}, "", card.href); } catch { /* still render */ }
      open(sample.slug);
    });
    return card;
  }));
  // On a phone the cards are one row that scrolls sideways (samples.css), so
  // the open sample's card has to be brought into it; where the cards wrap,
  // the row has nowhere to scroll and this changes nothing.
  if (active && Number.isFinite(active.offsetLeft) && Number.isFinite(listNode.offsetLeft)) {
    listNode.scrollLeft = Math.max(0, active.offsetLeft - listNode.offsetLeft);
  }
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

/** A plain same-origin link to the committed Markdown, so a visitor can keep
 * the file. No extra fetch and no credentials: the browser saves what
 * /api/samples/<slug>?view=saved serves. That is the file as committed, not the
 * display text the reader renders. Built per open sample, so it follows the one
 * on screen and, with the reader reopened on a language switch, the language. */
function downloadLink(sample) {
  const link = el("a", "samples__download", t("samples_download"));
  link.href = `/api/samples/${encodeURIComponent(sample.slug)}?view=saved`;
  link.download = `${sample.slug}.md`;
  return link;
}

function historicalNotice(sample) {
  const text = t("samples_historical")
    .replace("{date}", sample.committed)
    .replace("{commit}", sample.commit)
    .replace("{model}", sample.model);
  return el("p", "samples__notice", text);
}

/** The scorecard of the sample's run, or null. The report is the sample: a
 * scorecard that is missing, refused or unreadable costs the brief and the
 * card, never the report, so every failure here is the same null. */
async function readScores(slug) {
  try {
    const response = await fetch(`/api/samples/${encodeURIComponent(slug)}/scores`);
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

/** What a run delivers beside its report: the decision brief and the
 * scorecard, built by the functions the run page uses, from the scorecard the
 * sample's run wrote. Until 2026-11-11 a sample was the report alone, so a
 * visitor deciding whether to sign up never saw the verdict, the five
 * dimensions or the reasons for them. A sample keeps no checks and no source
 * registry, so the brief's lines that come from those are absent and its
 * closing note says so; without a readable verdict neither block is shown. */
function scoreBlocks(scores, markdown, index) {
  // The report's own reference list rates its sources, so the brief can name
  // the best-rated one the strongest dimension cites, with its title. It is
  // used for that and nothing else: no line that needs the run's checks or
  // its registry appears because of it.
  const data = scores ? decisionBrief({ scores, markdown, references: index }) : null;
  if (!data) return [];
  const brief = renderDecisionBrief(data, { note: t("samples_brief_note") });
  const card = renderScorecard(scores);
  for (const node of [brief, card]) attachCitations(node, () => Promise.resolve(index));
  const block = el("details", "samples__scorecard");
  block.open = wide?.matches ?? false;
  block.append(el("summary", null, t("samples_scorecard")), card);
  scorecard = block;
  return [brief, block];
}

/** Whether this deployment has accounts and takes new ones, from its public
 * facts. Not the access check: this page sends no credential, so that would
 * refuse it, and a refusal is an error in the console of everyone who reads a
 * sample. Any answer that is not those facts, or none, is null. Never rejects. */
async function readAccounts() {
  try {
    const response = await fetch("/api/site");
    const site = response.ok ? await response.json() : null;
    if (!site || typeof site !== "object" || typeof site.accounts !== "boolean") return null;
    return { enabled: site.accounts, signup_open: site.signup_open === true };
  } catch {
    return null;
  }
}
const accountsRead = readAccounts().then((answer) => { accounts = answer; });

/** Where a reader goes next. Until 2026-11-13 the page ended with the
 * report's last reference and no way on but the back link in its head. The
 * link names what this deployment offers: an account where it takes new
 * ones, the sign-in where it has accounts and takes none, and otherwise just
 * the app, whose own first screen says what it needs. */
function nextStep() {
  const offer = !accounts?.enabled ? "open" : accounts.signup_open ? "create" : "signin";
  const link = el("a", "samples__next-link", t(`samples_next_${offer}`));
  link.href = { create: "/#create-account", signin: "/#sign-in", open: "/" }[offer];
  const block = el("aside", "samples__next");
  block.append(el("p", "samples__next-text", t("samples_next")), link);
  return block;
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
  // Asked for at the same time as the report and awaited after it; readScores
  // never rejects.
  const scoresRead = readScores(slug);
  try {
    const response = await fetch(`/api/samples/${encodeURIComponent(slug)}`);
    if (!response.ok) throw new Error(String(response.status));
    markdown = await response.text();
  } catch {
    if (mine === generation) note("samples_read_failed");
    return;
  }
  const scores = await scoresRead;
  await accountsRead;
  if (mine !== generation) return;

  const article = el("article", "prose");
  article.innerHTML = renderMarkdown(markdown);
  // The sample's own reference list feeds the citation cards; there is no
  // source registry behind a sample, so there is no "show in Sources" either.
  const index = citationIndex(markdown);
  attachCitations(article, () => Promise.resolve(index));
  const toc = contentsFor(article);
  reader.replaceChildren(
    historicalNotice(sample), downloadLink(sample), ...scoreBlocks(scores, markdown, index),
    ...(toc ? [toc.nav] : []), article, nextStep(),
  );
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
