/* Check production transfer consent before the shared machine records intent. */
import "/source-locator-static/receipt.js";
import { runPattern } from "/source-locator-static/result.js";
import { readUsageBody, decodeUsage, clearAccounting, renderAccounting } from "/source-locator-static/accounting.js";

const byId = id => document.getElementById(id);
const consent = byId("locator-consent");
const executionAllowed = document.documentElement.dataset.executionAllowed === "true";
// Hide new-intent controls in receipt-only mode without disabling the code
// field needed by recovery. The server remains the execution authority.
byId("locate").hidden = !executionAllowed;
consent.disabled = !executionAllowed;
const status = text => {
  byId("request-status").textContent = text;
  byId("request-status").dataset.kind = "error";
};
// Fragment convenience is never authority and never persists the run identity.
const fragment = window.location.hash.slice(1);
if (runPattern.test(fragment)) byId("run-id").value = fragment;
for (const name of ["access-code", "run-id", "question"]) {
  byId(name).addEventListener("input", () => { consent.checked = false; });
}
byId("locator-form").addEventListener("reset", () => { consent.checked = false; });
byId("execution-status").textContent = executionAllowed
  ? "服务端已允许提交。只有当前访问码拥有的报告可以使用；每次定位最多调用一次模型。"
  : "新定位已关闭。已有回执仍可手动查询，查询不会重新调用模型。";

globalThis.startSavedSourceReceiptPage({
  storageName: "source-locator:v1",
  postPath: run => `/api/runs/${run}/source-locator`,
  getPath: "/api/source-locator/receipts",
  // Hooks exist only in the exact production projection of the frozen browser
  // machine. GET needs neither transfer consent nor a second paid intent.
  beforeSubmit: () => {
    if (!executionAllowed) {
      status("新定位已关闭；未创建回执，也未发送定位请求。");
      return false;
    }
    if (!consent.checked) {
      status("请先确认本次问题和来源标题目录的发送范围；尚未创建回执或发送请求。");
      return false;
    }
    return true;
  },
  requestHeaders: () => ({ "X-Source-Locator-Consent": "question-catalog-v1" }),
  readResponse: readUsageBody,
  decode: decodeUsage,
  clearExtra: clearAccounting,
  renderExtra: renderAccounting,
});
