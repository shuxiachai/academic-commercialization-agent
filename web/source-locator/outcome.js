/* Production-only receipt outcome presentation; it has no transport or state. */

const explanations = Object.freeze({
  saved_source_missing: "定位失败：此报告的已保存来源不可用，未开始定位。失败不代表免费或可自动重试。",
  saved_source_unavailable: "定位失败：已保存来源无法安全读取，未开始定位。失败不代表免费或可自动重试。",
  execution_unavailable: "定位失败：定位服务当前不可用。失败不代表免费或可自动重试。",
  concurrency_limit: "定位失败：未获得执行名额。请保留回执并按页面流程处理；失败不代表免费或可自动重试。",
  daily_quota_exceeded: "定位失败：已达到当日允许额度。请保留回执并按页面流程处理；失败不代表免费或可自动重试。",
  paid_ledger_unavailable: "定位失败：计费记录不可用，未知用量不会显示为零。失败不代表免费或可自动重试。",
  access_denied: "定位失败：当前访问码无权执行此请求。失败不代表免费或可自动重试。",
  request_abandoned: "定位失败：请求在完成前终止。回执仍保留，不能自动重试，也不代表免费。",
});

export function clearOutcome(byId) {
  const node = byId("receipt-outcome");
  node.textContent = "";
  node.hidden = true;
}

export function renderOutcome(decoded, byId) {
  const node = byId("receipt-outcome");
  const receipt = decoded?.receipt;
  if (receipt?.state !== "failed") return clearOutcome(byId);
  // validReceipt has already strictly decoded and allowlisted this code. Keep a
  // neutral fallback so a future projection cannot turn unknown server text
  // into DOM content.
  node.textContent = Object.hasOwn(explanations, receipt.error_code)
    ? explanations[receipt.error_code]
    : "定位失败：没有可安全显示的具体原因。回执仍按页面流程保留；失败不代表免费或可自动重试。";
  node.hidden = false;
}
