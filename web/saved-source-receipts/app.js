/* This page owns one tab-session intent, never credentials or report persistence. */
import { runPattern, keyPattern, points, isBlank, keys, strictJSON, readBody,
  validReceipt, validError, clearDisplay, renderReceipt } from "./result.js";

const byId = id => document.getElementById(id);
const form = byId("locator-form"), code = byId("access-code"), run = byId("run-id"), question = byId("question");
const storageName = "saved-source-receipts:v1";
let receiptKey = null, storageFault = false, generation = 0, busy = false, terminal = false;
const record = key => JSON.stringify({ version: 1, receipt_key: key });
const validCode = value => typeof value === "string" && /^[\x20-\x7e]{1,4096}$(?![\s\S])/.test(value) && value.trim().length > 0;
const status = (text, kind = "info") => {
  byId("request-status").textContent = text; byId("request-status").dataset.kind = kind;
};

try {
  const raw = sessionStorage.getItem(storageName);
  if (raw !== null) {
    const saved = strictJSON(raw);
    if (!keys(saved, ["version", "receipt_key"]) || saved.version !== 1
        || typeof saved.receipt_key !== "string" || !keyPattern.test(saved.receipt_key)
        || raw !== record(saved.receipt_key)) throw Error("Invalid local receipt");
    receiptKey = saved.receipt_key;
  }
} catch { storageFault = true; }

function sync() {
  byId("locate").disabled = busy || receiptKey !== null || storageFault;
  byId("recover").disabled = busy || receiptKey === null || !validCode(code.value);
  byId("acknowledge").disabled = busy || receiptKey === null || storageFault || !terminal || !byId("risk").checked;
  form.setAttribute("aria-busy", String(busy));
  byId("storage-status").textContent = storageFault
    ? "回执存储已知损坏、丢失或被拒绝：本页持续阻止新提交。若内存仍有回执键，可输入访问码手动查询；不能确认清除。"
    : receiptKey === null ? "没有待处理的本地回执；尚未自动执行任何请求。"
      : "已有回执记录：阻止新提交。输入访问码后，只能手动查询同一回执。";
}
function checkStorage() {
  try {
    if (sessionStorage.getItem(storageName) !== (receiptKey === null ? null : record(receiptKey))) storageFault = true;
  } catch { storageFault = true; }
  // A later successful read never erases a known loss or denial in this page.
  sync();
  return !storageFault;
}
function invalidate() {
  generation++; terminal = false; byId("risk").checked = false;
  clearDisplay(byId); sync();
  status(busy ? "输入已更改；旧显示失效，原请求仍占用本页。回执不会被清除。" : "输入已更改；没有自动请求，已有回执继续保留。" );
}
for (const field of [code, run, question]) field.addEventListener("input", invalidate);
byId("risk").addEventListener("change", sync);
form.addEventListener("reset", event => {
  event.preventDefault(); code.value = ""; run.value = ""; question.value = "";
  invalidate(); code.focus();
});
globalThis.addEventListener("storage", event => {
  if (event.key === storageName || event.key === null) {
    checkStorage(); invalidate();
  }
});

function beginIntent() {
  if (!checkStorage() || receiptKey !== null) return false;
  try {
    const random = new Uint8Array(32);
    crypto.getRandomValues(random);
    const hex = Array.from(random, byte => byte.toString(16).padStart(2, "0")).join("");
    receiptKey = `v1.${Math.floor(Date.now() / 1000)}.${hex}`;
    if (!keyPattern.test(receiptKey)) throw Error("Invalid local key");
    // Commit and read back before dispatch. A lost POST reply must leave this key.
    sessionStorage.setItem(storageName, record(receiptKey));
    if (sessionStorage.getItem(storageName) !== record(receiptKey)) throw Error("Lost local receipt");
    sync();
    return true;
  } catch {
    storageFault = true; sync();
    status("无法在提交前确认回执已保存；没有发送定位请求。新提交已被阻止。", "error");
    return false;
  }
}

async function request(recover) {
  if (busy) return;
  checkStorage();
  if (!validCode(code.value)) {
    status("请输入 1–4096 个可打印 ASCII 字符的访问码；访问码仅保留在本页内存。", "error"); return;
  }
  if (recover ? receiptKey === null : receiptKey !== null || storageFault) return;
  if (!recover && (!runPattern.test(run.value) || points(question.value) < 1 || points(question.value) > 4096
      || isBlank(question.value) || /[\uD800-\uDFFF]/u.test(question.value))) {
    status("Run ID 格式无效，或问题不符合 1–4096 个非空白 Unicode 码点要求。", "error"); return;
  }
  if (!recover && !beginIntent()) return;
  const input = { code: code.value, run: run.value, question: question.value, key: receiptKey };
  const ownedGeneration = ++generation;
  const current = () => generation === ownedGeneration && receiptKey === input.key
    && code.value === input.code && run.value === input.run && question.value === input.question;
  busy = true; terminal = false; byId("risk").checked = false; clearDisplay(byId); sync();
  status(recover ? "正在查询同一回执；不会重新定位。" : "回执已保存，正在提交一次定位；不会自动重试。" );
  let timer;
  const abort = recover ? new AbortController() : null;
  try {
    const options = {
      method: recover ? "GET" : "POST", credentials: "omit", cache: "no-store", redirect: "error",
      headers: { "Idempotency-Key": input.key, "X-Access-Code": input.code },
    };
    if (recover) options.signal = abort.signal;
    else {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify({ question: input.question });
    }
    // Timeout only the read, including its streamed body. Never timeout a POST.
    const transport = async () => {
      const response = await fetch(recover ? "/api/saved-source-receipts" : `/api/runs/${input.run}/saved-source-location`, options);
      return { response, payload: await readBody(response) };
    };
    const responseWork = transport();
    const observation = recover ? await Promise.race([responseWork, new Promise((_, reject) => {
      timer = setTimeout(() => { abort.abort(); reject(Error("Receipt read timed out")); }, 12000);
    })]) : await responseWork;
    const { response, payload } = observation;
    if (!current()) return;
    if (response.status === 200) {
      if (!await validReceipt(payload, input.key, recover ? null : input.run)) throw Error("Invalid receipt response");
      if (!current()) return;
      checkStorage();
      renderReceipt(payload, byId, recover);
      terminal = ["completed", "failed"].includes(payload.state);
      status(terminal ? "已显示经过格式与身份校验的终态；确认风险后才可结束本地记录。"
        : "回执仍为 pending/unknown；保持阻止新提交。没有自动查询或重试。" );
    } else {
      if (!validError(response.status, payload)) throw Error("Invalid safe error");
      terminal = response.status === 410;
      status(`请求未完成（${payload.error_code}）；${terminal ? "回执已明确过期，确认风险后可结束记录。" : "保留回执，不允许新提交。"}`, "error");
      // Even a current 401 does not erase credentials; a stale 401 is ignored.
    }
  } catch {
    if (current()) {
      clearDisplay(byId); terminal = false;
      status("请求、响应或校验不可用；服务端可能已经执行。保留回执，只能手动查询，不能重新提交。", "error");
    }
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    busy = false; sync();
    if (!current()) status("旧请求已结束，响应已丢弃。回执仍保留；输入访问码后手动查询。" );
  }
}
form.addEventListener("submit", event => { event.preventDefault(); return request(false); });
byId("recover").addEventListener("click", () => request(true));
byId("acknowledge").addEventListener("click", () => {
  if (busy || !terminal || !byId("risk").checked || receiptKey === null || !checkStorage()) return;
  try {
    // Only remove the exact record this page owns, then verify actual absence.
    sessionStorage.removeItem(storageName);
    if (sessionStorage.getItem(storageName) !== null) throw Error("Removal unconfirmed");
    receiptKey = null;
    invalidate();
    status("本地终态记录已结束。没有自动提交；下一次手动提交将产生新的意图。" );
  } catch {
    storageFault = true; terminal = false; sync();
    status("无法确认回执已移除；持续阻止新提交，内存回执仍可手动查询。", "error");
  }
});
sync();
