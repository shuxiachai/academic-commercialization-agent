/* Privacy and terms page.
 *
 * The page's text is in its markup, in both languages, so it reads without
 * this script. What the script adds: showing only the reader's language, and
 * what belongs to the deployment rather than to the page — how long
 * assessments are kept, who to contact, and whether it sends email. Plain fetch, like the sample
 * reader: nothing here may send a credential. */

import * as i18n from "./i18n.js";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const LABELS = {
  en: { back: "Back to the app", title: "Privacy and terms · Commercialization Assessment",
        days: (n) => `for ${n} days`, forever: "until you delete them" },
  zh: { back: "返回应用", title: "隐私与条款 · 商业化评估",
        days: (n) => ` ${n} 天`, forever: "到你删除为止" },
};
let site = null;

const lang = () => (i18n.language() === "Simplified Chinese" ? "zh" : "en");

function paint() {
  const current = lang();
  document.documentElement.lang = current === "zh" ? "zh-CN" : "en";
  document.title = LABELS[current].title;
  for (const block of $$("[data-lang-block]")) block.hidden = block.dataset.langBlock !== current;
  for (const node of $$("[data-legal=back]")) node.textContent = LABELS[current].back;
  if (!site) return;
  const kept = Number.isSafeInteger(site.retention_days) && site.retention_days > 0;
  for (const node of $$("[data-retention]")) {
    const labels = LABELS[node.dataset.retention];
    node.textContent = kept ? labels.days(site.retention_days) : labels.forever;
  }
  // "Deleted automatically" is only true where the deployment sets a period.
  for (const node of $$("[data-retention-auto]")) node.hidden = !kept;
  // Only where this deployment takes its own backups, and with its number.
  const backupDays = Number.isSafeInteger(site.account_backup_days) && site.account_backup_days > 0
    ? site.account_backup_days : null;
  for (const node of $$("[data-account-backup]")) node.hidden = backupDays === null;
  for (const node of $$("[data-account-backup-days]")) node.textContent = backupDays === null ? "" : String(backupDays);
  // Which of the two sentences about email is this deployment's. Neither is
  // shown until the server has said: the paragraph already states both cases.
  for (const node of $$("[data-mail]")) {
    node.hidden = typeof site.mail !== "boolean" || (node.dataset.mail === "on") !== site.mail;
  }
  // textContent, never markup: the contact line is the operator's free text.
  if (typeof site.contact === "string" && site.contact.trim()) {
    for (const node of $$("[data-contact]")) node.textContent = site.contact.trim();
  }
}

const select = $("#ui-lang");
select.value = i18n.language();
select.addEventListener("change", () => { i18n.setLanguage(select.value); paint(); });
paint();

// Silent on failure: the page already states the general case in words, and
// an unreachable server must not leave a number on screen nothing confirmed.
fetch("/api/site").then((r) => (r.ok ? r.json() : null)).then((body) => {
  if (body && typeof body === "object") { site = body; paint(); }
}).catch(() => {});
