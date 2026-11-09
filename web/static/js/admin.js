/* The operator's console.
 *
 * Reads what only an admin account may read (/api/admin/...) and offers the
 * two actions an operator does most, each behind the admin's own password:
 * reset an account's password, and stop or allow its sign-in. Everything
 * from the server is placed as text; nothing here builds markup from data. */

import * as api from "./api.js";
import * as i18n from "./i18n.js";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const TEXT = {
  en: {
    back: "Back to the app", title: "Console", loading: "Checking who you are…",
    who: (email) => `Signed in as ${email}. This page is for admin accounts.`,
    denied_signin: "Sign in to the app with an admin account first, then come back here.",
    denied_admin: "This account is not an admin. The console is for the addresses named in ACCOUNTS_ADMIN_EMAILS.",
    service: "Service", accounts: "Accounts", backups: "Account backups", reload: "Reload",
    accounts_note: "Reset sends nothing anywhere: the new password is shown to you once, and you pass it on to the account's own address.",
    col_email: "Email", col_created: "Created", col_seen: "Last seen", col_sessions: "Sign-ins", col_runs: "Runs",
    col_status: "Status", col_actions: "Actions", col_file: "File", col_taken: "Taken", col_size: "Size", col_accounts: "Accounts",
    accounts_empty: "No accounts yet.", backups_empty: "No backups yet.",
    never: "never", you: "you", admin: "admin", active: "active", disabled: "disabled", unverified: "unverified",
    reset: "Reset password", disable: "Disable", enable: "Enable",
    own_row: "Your own account: use Account in the app.",
    reset_title: "Reset the password", reset_text: (email) => `A new random password will replace the one ${email} has, and every sign-in of the account will end.`,
    disable_title: "Disable the account", disable_text: (email) => `${email} will not be able to sign in, and every sign-in of the account will end. Its assessments stay.`,
    enable_title: "Enable the account", enable_text: (email) => `${email} will be able to sign in again with their existing password.`,
    your_password: "Your password", cancel: "Cancel", confirm: "Confirm",
    reset_done: "Password reset", reset_result: (email, ended) => `The new password for ${email}. ${ended} sign-in${ended === 1 ? "" : "s"} ended.`,
    reset_next: "Send it to the account's own address, not to whoever asked, and ask them to change it after signing in. It is not shown again.",
    copy: "Copy", close: "Done", copied: "Copied.", copy_failed: "Could not copy. Select the password and copy it yourself.",
    disabled_done: (email) => `${email} is disabled.`, enabled_done: (email) => `${email} can sign in again.`,
    wrong_password: "That is not your password.", locked: "Too many wrong passwords. Wait a quarter of an hour.",
    failed: "That did not work. Reload and try again.",
    backups_on: (hours, keep) => `The service takes one every ${hours} hours and keeps the newest ${keep}. Each file below was opened and checked just now. These copies are on the same volume as the database; a copy elsewhere is still yours to arrange.`,
    backups_off: "The service is not taking backups by itself here (ACCOUNTS_BACKUP_HOURS is 0, or accounts are off).",
    verify_failed: "did not verify",
    f_revision: "Revision", f_maintenance: "Maintenance", f_alerts: "Alerts", f_runs: "Running now", f_model: "Model",
    m_running: "running, every check passed", m_degraded: (names) => `degraded: ${names} failed`, m_other: (state) => state,
    a_off: "off (no robot set)", a_ready: (channel) => `on, ${channel}`, a_failing: (channel) => `${channel}, the last message was not delivered`,
    a_misconfigured: "misconfigured: the robot setting is not usable",
    health_unavailable: "could not be read",
    link: "Provider link", probe: "Probe now", probing: "Probing… up to three minutes when a path is dead.",
    link_note: "From this server: chat requests of 1, 10, 30 and 100 KB (the last is the report writer's size, 30 KB an evidence agent's) with no key, each on a new connection, to the configured endpoint and, for Bailian, to its sibling across the border. The servers read the body and answer 401, so nothing is billed; the time to that answer is what the path takes. Marks are milliseconds from the start of the request.",
    link_done: (when, timeout) => `Measured ${when}. Each request was given ${timeout} seconds.`,
    link_busy: "A probe is already running; wait for it.", link_none: "No provider endpoint is configured here.",
    col_host: "Endpoint", col_body: "Body", col_connect: "Connected", col_tls: "TLS", col_upload: "Uploaded",
    col_first: "First byte", col_total: "Total", col_result: "Result",
    r_answered: "answered", r_never: "—",
    name_configured: "configured", name_intl: "international sibling", name_mainland: "mainland sibling",
  },
  zh: {
    back: "返回应用", title: "管理后台", loading: "正在确认你的身份……",
    who: (email) => `已登录：${email}。本页面仅供管理员账号使用。`,
    denied_signin: "请先在应用里用管理员账号登录，再回到这里。",
    denied_admin: "这个账号不是管理员。管理后台只对 ACCOUNTS_ADMIN_EMAILS 里列出的邮箱开放。",
    service: "服务状态", accounts: "账号", backups: "账号备份", reload: "刷新",
    accounts_note: "重置密码不会向任何地方发送任何内容：新密码只向你显示一次，由你转交到该账号自己的邮箱。",
    col_email: "邮箱", col_created: "注册时间", col_seen: "最近活动", col_sessions: "登录数", col_runs: "评估数",
    col_status: "状态", col_actions: "操作", col_file: "文件", col_taken: "备份时间", col_size: "大小", col_accounts: "账号数",
    accounts_empty: "还没有账号。", backups_empty: "还没有备份。",
    never: "从未", you: "本人", admin: "管理员", active: "正常", disabled: "已停用", unverified: "邮箱未验证",
    reset: "重置密码", disable: "停用", enable: "启用",
    own_row: "这是你自己的账号：请在应用的“账号”面板操作。",
    reset_title: "重置密码", reset_text: (email) => `将为 ${email} 生成一个新的随机密码，替换现有密码，并结束该账号的全部登录。`,
    disable_title: "停用账号", disable_text: (email) => `${email} 将无法登录，现有登录全部结束。该账号的评估会保留。`,
    enable_title: "启用账号", enable_text: (email) => `${email} 可以用原密码重新登录。`,
    your_password: "你的密码", cancel: "取消", confirm: "确认",
    reset_done: "密码已重置", reset_result: (email, ended) => `${email} 的新密码如下。已结束 ${ended} 个登录。`,
    reset_next: "请发到该账号自己的邮箱，而不是提出请求的人；并请对方登录后立即修改。此密码不会再次显示。",
    copy: "复制", close: "完成", copied: "已复制。", copy_failed: "没能复制。请选中密码自行复制。",
    disabled_done: (email) => `${email} 已停用。`, enabled_done: (email) => `${email} 可以重新登录了。`,
    wrong_password: "这不是你的密码。", locked: "密码错误次数过多，请一刻钟后再试。",
    failed: "操作没有成功。请刷新后重试。",
    backups_on: (hours, keep) => `服务每 ${hours} 小时自动备份一次，保留最新的 ${keep} 份。下面每个文件刚刚都已打开并校验。这些副本和数据库在同一个卷上，异地副本仍需你自行安排。`,
    backups_off: "服务当前没有自动备份（ACCOUNTS_BACKUP_HOURS 为 0，或账号功能未开启）。",
    verify_failed: "校验失败",
    f_revision: "版本", f_maintenance: "维护循环", f_alerts: "告警", f_runs: "正在运行", f_model: "模型",
    m_running: "运行中，各项检查正常", m_degraded: (names) => `降级：${names} 失败`, m_other: (state) => state,
    a_off: "关闭（未设置机器人）", a_ready: (channel) => `开启，${channel}`, a_failing: (channel) => `${channel}，上一条消息未送达`,
    a_misconfigured: "配置有误：机器人设置不可用",
    health_unavailable: "无法读取",
    link: "模型服务链路", probe: "现在探测", probing: "探测中……链路不通时最长需要三分钟。",
    link_note: "由本服务器发出：1、10、30、100 KB 四档对话请求（100 KB 是报告写手请求的大小，30 KB 约为证据智能体的），不带密钥、每次新建连接，发往已配置的端点，百炼还会同时发往境外另一侧的同类端点。服务器读完请求体后回 401，不产生任何计费；到收到这个回答为止的时间就是链路所需的时间。各列是自请求开始起的毫秒数。",
    link_done: (when, timeout) => `测于 ${when}。每个请求最多等 ${timeout} 秒。`,
    link_busy: "已有一次探测在进行，请等它结束。", link_none: "这里没有配置模型服务端点。",
    col_host: "端点", col_body: "请求体", col_connect: "已连接", col_tls: "TLS", col_upload: "已上传",
    col_first: "首字节", col_total: "总计", col_result: "结果",
    r_answered: "已应答", r_never: "—",
    name_configured: "已配置", name_intl: "国际站同类端点", name_mainland: "大陆同类端点",
  },
};
const CHANNELS = { feishu: { en: "Feishu", zh: "飞书" }, wecom: { en: "WeCom", zh: "企业微信" } };

const lang = () => (i18n.language() === "Simplified Chinese" ? "zh" : "en");
const t = (key, ...args) => {
  const value = TEXT[lang()][key] ?? TEXT.en[key] ?? key;
  return typeof value === "function" ? value(...args) : value;
};

let me = null;
let accountList = [];
let health = null;
let backupData = null;

function toast(message, variant = "") {
  const el = document.createElement("div");
  el.className = `toast${variant ? ` toast--${variant}` : ""}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 4600);
}

const when = (seconds) => {
  if (!Number.isFinite(seconds)) return t("never");
  return new Date(seconds * 1000).toLocaleString(lang() === "zh" ? "zh-CN" : "en-GB",
    { dateStyle: "medium", timeStyle: "short" });
};
const bytes = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);

function cell(text, className = "") {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}
function pill(text, kind) {
  const span = document.createElement("span");
  span.className = `pill pill--${kind}`;
  span.textContent = text;
  return span;
}

/* Static labels, both languages in one table so the page follows the
 * reader's choice in the app. */
function paintLabels() {
  const current = lang();
  document.documentElement.lang = current === "zh" ? "zh-CN" : "en";
  document.title = `${t("title")} · ${current === "zh" ? "商业化评估" : "Commercialization Assessment"}`;
  for (const node of $$("[data-text]")) node.textContent = t(node.dataset.text);
}

function paintService() {
  const facts = $("#service-facts");
  facts.innerHTML = "";
  const add = (label, value) => {
    const dt = document.createElement("dt");
    dt.textContent = t(label);
    const dd = document.createElement("dd");
    dd.textContent = value;
    facts.append(dt, dd);
  };
  if (!health) {
    add("f_maintenance", t("health_unavailable"));
    return;
  }
  const maintenance = health.maintenance ?? {};
  const failed = Object.entries(maintenance.checks ?? {}).filter(([, v]) => v === "failed").map(([k]) => k);
  add("f_revision", String(health.pipeline_revision ?? "—"));
  add("f_maintenance", maintenance.state === "running" ? t("m_running")
    : maintenance.state === "degraded" ? t("m_degraded", failed.join(", ")) : t("m_other", String(maintenance.state ?? "—")));
  const alerts = health.alerts ?? {};
  const channel = CHANNELS[alerts.channel]?.[lang()] ?? String(alerts.channel ?? "");
  add("f_alerts", alerts.state === "ready" ? t("a_ready", channel) : alerts.state === "failing" ? t("a_failing", channel)
    : alerts.state === "misconfigured" ? t("a_misconfigured") : t("a_off"));
  add("f_runs", `${health.active_runs ?? 0} / ${health.max_concurrent ?? "—"}`);
  if (health.llm_model) add("f_model", `${health.llm_provider ?? ""} ${health.llm_model}`.trim());
}

function paintAccounts() {
  const rows = $("#accounts-rows");
  rows.innerHTML = "";
  $("#accounts-empty").hidden = accountList.length > 0;
  for (const account of accountList) {
    const tr = document.createElement("tr");
    const own = me && account.id === me.id;
    if (own) tr.classList.add("is-you");
    tr.append(cell(account.email, "is-email"), cell(when(account.created_at)), cell(when(account.last_seen_at)),
      cell(String(account.sessions), "is-number"), cell(String(account.runs), "is-number"));
    const status = document.createElement("td");
    status.append(pill(account.disabled ? t("disabled") : t("active"), account.disabled ? "failed" : "completed"));
    if (account.verified === false) status.append(pill(t("unverified"), "unknown"));
    if (account.admin) status.append(pill(t("admin"), "running"));
    if (own) status.append(pill(t("you"), "unknown"));
    tr.append(status);
    const actions = document.createElement("td");
    actions.className = "is-actions";
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "btn btn--secondary";
    reset.textContent = t("reset");
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = account.disabled ? "btn btn--secondary" : "btn btn--danger";
    toggle.textContent = account.disabled ? t("enable") : t("disable");
    if (own) {
      // Not a permission the server lacks: it refuses too. A disabled button
      // says why before the click rather than after.
      for (const button of [reset, toggle]) { button.disabled = true; button.title = t("own_row"); }
    } else {
      reset.addEventListener("click", () => confirmAction("reset", account));
      toggle.addEventListener("click", () => confirmAction(account.disabled ? "enable" : "disable", account));
    }
    actions.append(reset, toggle);
    tr.append(actions);
    rows.append(tr);
  }
}

function paintBackups() {
  const rows = $("#backups-rows");
  rows.innerHTML = "";
  const data = backupData;
  $("#backups-note").textContent = !data ? t("health_unavailable")
    : data.scheduled ? t("backups_on", data.every_hours, data.keep) : t("backups_off");
  const list = data?.backups ?? [];
  $("#backups-empty").hidden = list.length > 0;
  for (const backup of list) {
    const tr = document.createElement("tr");
    tr.append(cell(backup.name), cell(when(backup.taken_at)), cell(bytes(backup.size), "is-number"));
    const td = document.createElement("td");
    td.className = "is-number";
    if (backup.accounts === null || backup.accounts === undefined) {
      td.className = "console__problem";
      td.textContent = `${t("verify_failed")}: ${backup.problem ?? ""}`;
    } else {
      td.textContent = String(backup.accounts);
    }
    tr.append(td);
    rows.append(tr);
  }
}

/* ── The provider link ───────────────────────────────────────────────── */

let probeData = null;
const ms = (value) => (value === null || value === undefined ? t("r_never") : `${value} ms`);
// Decimal, as the note says "100 KB": the body is 100,000 bytes, not 97.7 KiB.
const kb = (n) => (n >= 1000 ? `${Math.round(n / 1000)} KB` : `${n} B`);

function paintProbe() {
  const rows = $("#link-rows");
  rows.innerHTML = "";
  if (!probeData) return;
  $("#link-state").textContent = t("link_done", when(Date.parse(probeData.taken_at) / 1000), probeData.timeout_seconds);
  for (const target of probeData.targets) {
    for (const r of target.readings) {
      const tr = document.createElement("tr");
      tr.append(cell(`${target.host} (${t(`name_${target.name}`)})`), cell(kb(r.body_bytes), "is-number"),
        cell(ms(r.connect_ms), "is-number"), cell(ms(r.tls_ms), "is-number"), cell(ms(r.upload_ms), "is-number"),
        cell(ms(r.first_byte_ms), "is-number"), cell(ms(r.total_ms), "is-number"));
      // 401 is the answer a request without a key earns once the server has
      // read it: the path carried the body. Anything else is named as is.
      const result = r.error ? cell(r.error, "console__problem")
        : cell(r.status === 401 ? t("r_answered") : String(r.status));
      tr.append(result);
      rows.append(tr);
    }
  }
}

async function probe() {
  const button = $("#link-probe");
  button.disabled = true;
  $("#link-state").textContent = t("probing");
  try {
    probeData = await api.adminLinkProbe();
    paintProbe();
  } catch (err) {
    const status = err?.status;
    $("#link-state").textContent = status === 409 ? t("link_busy") : status === 503 ? t("link_none") : t("failed");
  } finally {
    button.disabled = false;
  }
}

function paint() {
  paintLabels();
  if (me) $("#console-who").textContent = t("who", me.email);
  if (!$("#console-denied").hidden) $("#console-denied").textContent = t(denial);
  if ($("#console-body").hidden) return;
  paintService();
  paintAccounts();
  paintBackups();
  paintProbe();
}

let denial = "denied_signin";

async function load() {
  const [accountsAnswer, backupsAnswer, healthAnswer] = await Promise.allSettled([
    api.adminAccounts(), api.adminBackups(), api.health(),
  ]);
  accountList = accountsAnswer.status === "fulfilled" ? accountsAnswer.value.accounts : [];
  backupData = backupsAnswer.status === "fulfilled" ? backupsAnswer.value : null;
  health = healthAnswer.status === "fulfilled" ? healthAnswer.value : null;
  if (accountsAnswer.status === "rejected") toast(t("failed"), "error");
  paint();
}

/* ── The two actions ──────────────────────────────────────────────────── */

let pending = null;   // { kind, account }

function confirmAction(kind, account) {
  pending = { kind, account };
  $("#confirm-title").textContent = t(`${kind}_title`);
  $("#confirm-text").textContent = t(`${kind}_text`, account.email);
  $("#confirm-go").textContent = t("confirm");
  $("#confirm-go").className = kind === "disable" ? "btn btn--danger" : "btn btn--primary";
  $("#confirm-password").value = "";
  $("#confirm-error").hidden = true;
  $("#confirm-dialog").showModal();
  $("#confirm-password").focus();
}

function refusalText(err) {
  if (err?.code === "invalid_credentials" || err?.status === 401) return t("wrong_password");
  if (err?.code === "locked" || err?.status === 429) return t("locked");
  return err?.message || t("failed");
}

$("#confirm-cancel").addEventListener("click", () => $("#confirm-dialog").close());
$("#confirm-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!pending) return;
  const { kind, account } = pending;
  const password = $("#confirm-password").value;
  const go = $("#confirm-go");
  go.disabled = true;
  try {
    if (kind === "reset") {
      const result = await api.adminResetPassword(account.id, password);
      $("#confirm-dialog").close();
      $("#result-text").textContent = t("reset_result", result.email, result.sessions_ended);
      $("#result-password").textContent = result.temporary_password;
      $("#result-dialog").showModal();
    } else {
      await api.adminSetDisabled(account.id, password, kind === "disable");
      $("#confirm-dialog").close();
      toast(t(kind === "disable" ? "disabled_done" : "enabled_done", account.email), "success");
    }
    pending = null;
    await load();
  } catch (err) {
    const error = $("#confirm-error");
    error.textContent = refusalText(err);
    error.hidden = false;
    $("#confirm-password").select();
  } finally {
    go.disabled = false;
  }
});

/* The same two ways of copying as the run page's "Copy link": the first is
 * refused by some embedded browsers, and a password read out by hand is a
 * password mistyped. */
function copyBySelection(text) {
  let field = null;
  try {
    const focused = document.activeElement;
    field = document.createElement("textarea");
    field.value = text;
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

$("#result-copy").addEventListener("click", async () => {
  const copied = await copyText($("#result-password").textContent);
  toast(t(copied ? "copied" : "copy_failed"), copied ? "success" : "error");
});
$("#result-close").addEventListener("click", () => {
  // Gone from the page with the dialog: the server never had it in the clear either.
  $("#result-password").textContent = "";
  $("#result-dialog").close();
});
$("#accounts-reload").addEventListener("click", load);
$("#link-probe").addEventListener("click", probe);

const select = $("#ui-lang");
select.value = i18n.language();
select.addEventListener("change", () => { i18n.setLanguage(select.value); paint(); });
paintLabels();

/* ── Boot: who is this? ───────────────────────────────────────────────── */

(async () => {
  try {
    const who = await api.me();
    if (!who.admin) {
      denial = "denied_admin";
      $("#console-who").textContent = t("who", who.email);
      throw new Error("not an admin");
    }
    const accounts = await api.adminAccounts();
    accountList = accounts.accounts;
    me = { email: who.email, id: accountList.find((a) => a.email === who.email)?.id ?? null };
    $("#console-who").textContent = t("who", who.email);
    $("#console-body").hidden = false;
    await load();
  } catch {
    $("#console-denied").textContent = t(denial);
    $("#console-denied").hidden = false;
    if (denial === "denied_signin") $("#console-who").textContent = "";
  }
})();
