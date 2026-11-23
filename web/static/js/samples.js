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
  attachCitations, citationIndex, decisionBrief, decisionVerdict, passageIn, renderDecisionBrief, renderDecisionVerdict,
  renderMarkdown, renderScorecard, sampleFacts, sampleTitle,
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
// The tab's name for /samples, and again whenever no sample matches, so an
// unknown slug does not keep the last sample's name. From the strings, not
// from the served <title>, which is English whatever the reader chose.
const defaultTitle = () => i18n.pageTitle(t("samples_title"));

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

/** Where the cards will be, until the list arrives, as the served markup
 * has them: until 2026-11-21 the reader said "Choose a report above." while
 * nothing was above it yet. */
const PLACEHOLDERS = 4;
function placeholders() {
  listNode.setAttribute("aria-busy", "true");
  listNode.replaceChildren(...Array.from({ length: PLACEHOLDERS }, () => {
    const card = el("span", "sample-card sample-card--placeholder");
    card.setAttribute("aria-hidden", "true");
    return card;
  }));
  reader.replaceChildren(el("div", "skeleton", ""));
}

/* Every card is on the page at every width (samples.css): until 2026-11-21 a
 * screen under 768 px wide showed them as one row that scrolled sideways, and
 * at 717 px two and a half showed. */
function paintList() {
  listNode.removeAttribute("aria-busy");
  listNode.replaceChildren(...samples.map((sample) => {
    const card = el("a", "sample-card");
    card.href = `/samples/${encodeURIComponent(sample.slug)}`;
    if (sample.slug === current) card.setAttribute("aria-current", "page");
    // The verdict, the readiness level and the report's language, where the
    // list carried them. The samples run from 48.6 to 74.9; before
    // 2026-11-13 a visitor had to open each one to learn that.
    const facts = sampleFacts(sample);
    card.append(el("span", "sample-card__title", sampleTitle(sample)));
    if (facts.verdict) {
      const verdict = el("span", "sample-card__verdict", facts.verdict);
      verdict.dataset.tone = facts.tone;
      card.append(verdict);
    }
    // The one kind of sample that shows a conclusion for a decision-maker
    // says so on its card: otherwise a visitor finds it by opening each.
    if (decisionOf(sample)) card.append(el("span", "sample-card__decision", t("samples_card_decision")));
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
}

/** Name the tab after the open sample, so tabs, bookmarks and history entries
 * for different samples can be told apart. Set when the selection changes,
 * like the list's aria-current, not after the fetch: a slow response for a
 * sample already left is dropped by `generation` and must not leave its name
 * behind either. */
function showTitle(sample) {
  document.title = sample ? `${sampleTitle(sample)} · ${t("samples_title")}` : defaultTitle();
  // The list's name for a screen reader: the same words as the page's.
  listNode.setAttribute("aria-label", t("samples_title"));
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

/** When and with which model the sample was made, and what it is not. The
 * pipeline's commit is a term to a reader ("on pipeline 9bd948c", until
 * 2026-11-21): it is under "Technical details", one press away. */
function historicalNotice(sample) {
  const text = t("samples_historical")
    .replace("{date}", () => sample.committed)
    .replace("{model}", () => sample.model);
  const notice = el("div", "samples__notice");
  const tech = el("details", "samples__tech");
  tech.append(el("summary", null, t("samples_tech")),
    el("p", null, t("samples_revision").replace("{commit}", () => sample.commit)));
  notice.append(el("p", "samples__notice-text", text), tech);
  return notice;
}

/** The decision context a sample's run was given, as the list carries it:
 * its four fields, each a line of text, or null. A list from before the
 * field, or an entry that carries something else, is a sample without one. */
const DECISION_FIELDS = ["asset_description", "target_application", "decision_owner", "decision_type"];
function decisionOf(sample) {
  const given = sample?.decision;
  if (!given || typeof given !== "object") return null;
  return DECISION_FIELDS.every((field) => typeof given[field] === "string" && given[field].trim()) ? given : null;
}

/** What the run was asked, in the reader's language around the words as they
 * were entered: the asset and the application, which appear nowhere else on
 * the page; without them "License the technology" does not say which
 * technology. The owner and the decision are the conclusion card's, under
 * it; until 2026-11-21 this sentence said them too, and the page twice. */
function decisionContext(given) {
  const text = t("samples_decision_context")
    .replace("{asset}", () => given.asset_description.trim())
    .replace("{application}", () => given.target_application.trim());
  return el("p", "samples__context", text);
}

/** What the sample's report concludes for the decision its run was asked
 * about: the answer of /api/samples/<slug>/decision, or undefined when it
 * could not be read. The card then says the read failed, as a run's page
 * does; an empty space would read as "the report concluded nothing". */
async function readDecision(slug) {
  try {
    const response = await fetch(`/api/samples/${encodeURIComponent(slug)}/decision`);
    return response.ok ? await response.json() : undefined;
  } catch {
    return undefined;
  }
}

/** The run page's decision-conclusion card, for a sample whose run was given
 * a decision context. Its link opens the quoted passage in the report under
 * it: the paragraph, else its section's heading, else the top of the report,
 * as the run page's does in its report tab. */
function decisionCard(reply, article, index) {
  const view = decisionVerdict(reply);
  if (!view) return null;
  let found = null;
  const card = renderDecisionVerdict(view, {
    onOpen: (needle, section) => {
      const blocks = [...article.querySelectorAll("p, li, td, h2, h3, h4")];
      const target = blocks[passageIn(blocks, needle, section)] ?? article;
      found?.classList.remove("prose__found");
      found = target === article ? null : target;
      found?.classList.add("prose__found");
      // Focus goes with the reader, so a keyboard continues from the passage.
      target.tabIndex = -1;
      target.focus({ preventScroll: true });
      target.scrollIntoView({ block: found ? "center" : "start" });
    },
  });
  attachCitations(card, () => Promise.resolve(index));
  return card;
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
function scoreBlocks(scores, markdown, index, given) {
  // The report's own reference list rates its sources, so the brief can name
  // the best-rated one the strongest dimension cites, with its title. It is
  // used for that and nothing else: no line that needs the run's checks or
  // its registry appears because of it.
  //
  // A run that was given a decision context says that one thing more. The
  // brief otherwise closes with "a decision context turns this into a
  // GO / NO-GO", which is false of the one sample that had one.
  const context = given ? { progress: { decision_gate: { mode: "decision_support" } } } : {};
  const data = scores ? decisionBrief({ scores, markdown, references: index, ...context }) : null;
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

/** The samples either side of the open one, named as links, between the
 * report and the sign-up block: at the end of a report the only way to
 * another sample was back up past the whole report to the list, many
 * screens on a phone. The order is the list's — the order /api/samples
 * returned — never one of this block's own. A link is followed as a card
 * is, so Back returns to the sample the reader came from; and the reader
 * is brought back into view, because the link sits at the foot of the old
 * report, which is not where the new one starts. The first sample has no
 * previous and the last no next; a list of one gets no block. */
function neighbours(sample) {
  const index = samples.findIndex((item) => item.slug === sample.slug);
  const links = [];
  const add = (neighbour, key) => {
    if (!neighbour) return;
    const link = el("a", "samples__neighbour", t(key).replace("{title}", () => sampleTitle(neighbour)));
    link.href = `/samples/${encodeURIComponent(neighbour.slug)}`;
    link.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      try { history.pushState({}, "", link.href); } catch { /* still render */ }
      open(neighbour.slug);
      reader.scrollIntoView();
    });
    links.push(link);
  };
  add(samples[index - 1], "samples_previous");
  add(samples[index + 1], "samples_next_sample");
  if (!links.length) return null;
  const block = el("nav", "samples__neighbours");
  block.setAttribute("aria-label", t("samples_neighbours"));
  block.append(...links);
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
  // never rejects, nor does readDecision. A sample whose run was given no
  // decision context is not asked what it concluded.
  const scoresRead = readScores(slug);
  const given = decisionOf(sample);
  const decisionRead = given ? readDecision(slug) : null;
  try {
    const response = await fetch(`/api/samples/${encodeURIComponent(slug)}`);
    if (!response.ok) throw new Error(String(response.status));
    markdown = await response.text();
  } catch {
    if (mine === generation) note("samples_read_failed");
    return;
  }
  const scores = await scoresRead;
  const decision = await decisionRead;
  await accountsRead;
  if (mine !== generation) return;

  const article = el("article", "prose");
  article.innerHTML = renderMarkdown(markdown);
  // The sample's own reference list feeds the citation cards; there is no
  // source registry behind a sample, so there is no "show in Sources" either.
  const index = citationIndex(markdown);
  attachCitations(article, () => Promise.resolve(index));
  const toc = contentsFor(article);
  // Under the notice, in a run page's order: what was asked, the conclusion
  // the report states, then the brief and the scorecard.
  const verdict = given ? decisionCard(decision, article, index) : null;
  const beside = neighbours(sample);
  reader.replaceChildren(
    historicalNotice(sample), downloadLink(sample),
    ...(given ? [decisionContext(given)] : []), ...(verdict ? [verdict] : []),
    ...scoreBlocks(scores, markdown, index, given),
    ...(toc ? [toc.nav] : []), article, ...(beside ? [beside] : []), nextStep(),
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
  else { paintList(); showTitle(null); note("samples_choose"); }
}

const langSelect = $("#ui-lang");
langSelect.value = i18n.language();
langSelect.addEventListener("change", () => {
  i18n.setLanguage(langSelect.value);
  applySamples();
  if (current) open(current);
  else showTitle(null);
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
placeholders();
try {
  const response = await fetch("/api/samples");
  if (!response.ok) throw new Error(String(response.status));
  samples = await response.json();
  if (!Array.isArray(samples)) throw new Error("not a list");
  route();
} catch {
  // No placeholder is left standing for a list that will not come.
  samples = [];
  listNode.removeAttribute("aria-busy");
  listNode.replaceChildren();
  note("samples_list_failed");
}
