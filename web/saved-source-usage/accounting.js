/* Independent strict accounting validation; no authority, storage or fetch. */
import { keys, runPattern, readBody } from "/receipt-static/result.js";

const usageFields = ["status", "prompt_tokens", "completion_tokens", "total_tokens"];
const costFields = ["currency", "status", "estimated_usd", "reservation_usd", "price_policy_id", "invoice_status"];
const accountingFields = ["schema_version", "method_id", "scope", "receipt_key_sha256", "run_id", "expires_at",
  "publication_state", "dispatch_state", "native_journal_state", "model_matches_authorized", "usage", "cost", "fault_codes"];
const faults = ["not_recorded", "accounting_unavailable", "binding_mismatch", "native_journal_unavailable",
  "native_journal_unresolved", "usage_missing_or_invalid", "model_mismatch", "price_unavailable"];
const money = value => typeof value === "string" && /^(0|[1-9][0-9]{0,8})\.[0-9]{9}$(?![\s\S])/.test(value);
const token = value => Number.isSafeInteger(value) && value >= 0 && value <= 1000000000;
const dollars = nano => `${nano / 1000000000n}.${String(nano % 1000000000n).padStart(9, "0")}`;

export function unavailableAccounting(receipt, fault = "accounting_unavailable") {
  return {
    schema_version: 1, method_id: "saved_source_native_usage_v1", scope: "single_saved_source_selection",
    receipt_key_sha256: receipt.receipt_key_sha256, run_id: receipt.run_id, expires_at: receipt.expires_at,
    publication_state: "unavailable", dispatch_state: "unknown", native_journal_state: "unavailable",
    model_matches_authorized: null,
    usage: { status: "unavailable", prompt_tokens: null, completion_tokens: null, total_tokens: null },
    cost: { currency: "USD", status: "unavailable", estimated_usd: null, reservation_usd: null,
      price_policy_id: null, invoice_status: "not_observed" }, fault_codes: [fault],
  };
}

export function validAccounting(a) {
  if (!keys(a, accountingFields) || a.schema_version !== 1 || a.method_id !== "saved_source_native_usage_v1"
      || typeof a.receipt_key_sha256 !== "string" || !/^[0-9a-f]{64}$(?![\s\S])/.test(a.receipt_key_sha256)
      || typeof a.run_id !== "string" || !runPattern.test(a.run_id)
      || !Number.isSafeInteger(a.expires_at) || a.expires_at < 1
      || a.scope !== "single_saved_source_selection" || !keys(a.usage, usageFields) || !keys(a.cost, costFields)
      || !["pending", "sealed", "unavailable"].includes(a.publication_state)
      || !["not_dispatched", "may_have_dispatched", "response_received", "unknown"].includes(a.dispatch_state)
      || !["not_started", "complete", "unresolved", "unavailable"].includes(a.native_journal_state)
      || ![true, false, null].includes(a.model_matches_authorized)
      || !Array.isArray(a.fault_codes) || !a.fault_codes.every(f => faults.includes(f))
      || JSON.stringify(a.fault_codes) !== JSON.stringify([...new Set(a.fault_codes)].sort())) return false;
  const u = a.usage, c = a.cost;
  if (!["reported_complete", "reported_partial", "unknown", "not_dispatched", "unavailable"].includes(u.status)
      || !["estimated", "partial_estimate", "unknown", "not_applicable", "unavailable"].includes(c.status)
      || c.currency !== "USD" || c.invoice_status !== "not_observed"
      || !(c.reservation_usd === null || money(c.reservation_usd))
      || ![null, "locator_qwen_frozen_rates_v1"].includes(c.price_policy_id)) return false;
  const reported = ["reported_complete", "reported_partial"].includes(u.status);
  if (reported ? ![u.prompt_tokens, u.completion_tokens, u.total_tokens].every(token)
      || u.prompt_tokens + u.completion_tokens !== u.total_tokens
    : ![u.prompt_tokens, u.completion_tokens, u.total_tokens].every(v => v === null)) return false;
  if (reported && a.dispatch_state !== "response_received") return false;
  if (u.status === "reported_complete" && (a.publication_state !== "sealed" || a.native_journal_state !== "complete")) return false;
  if (u.status === "reported_partial" && a.native_journal_state === "complete") return false;
  if (u.status === "not_dispatched" && (a.publication_state !== "sealed" || a.dispatch_state !== "not_dispatched")) return false;
  if ([a.publication_state, u.status, c.status].includes("unavailable") && a.fault_codes.length === 0) return false;
  if (c.status === "not_applicable" && u.status !== "not_dispatched") return false;
  if (a.model_matches_authorized === false && (c.status !== "unavailable" || !a.fault_codes.includes("model_mismatch"))) return false;
  if (["estimated", "partial_estimate"].includes(c.status)) {
    if (u.status !== (c.status === "estimated" ? "reported_complete" : "reported_partial")
        || a.model_matches_authorized !== true || c.price_policy_id !== "locator_qwen_frozen_rates_v1"
        || !money(c.estimated_usd)
        || c.estimated_usd !== dollars(BigInt(u.prompt_tokens) * 573n + BigInt(u.completion_tokens) * 3440n)) return false;
  } else if (c.estimated_usd !== null) return false;
  return true;
}

export async function readUsageBody(response) {
  let invalidAccountingNumber = false;
  const payload = await readBody(response, { onInvalidNumber(path) {
    if (path[0] !== "accounting") return false;
    invalidAccountingNumber = true;
    return true;
  } });
  // Finish syntax/duplicate/depth checks before discarding the whole component.
  // Placeholder nulls must never be reinterpreted as valid unknown token facts,
  // nor may 1e0 become a schema_version or token count after lexical information
  // is lost. Receipt numbers and every other subtree remain default-strict.
  if (invalidAccountingNumber) payload.accounting = null;
  return payload;
}

export function decodeUsage(payload) {
  // Only accounting may degrade. An unknown envelope or malformed receipt is
  // still rejected by the shared state machine's unchanged validReceipt check.
  if (!(keys(payload, ["contract", "receipt", "accounting"]) || keys(payload, ["contract", "receipt"]))
      || payload.contract !== "saved_source_receipt_usage_v1") {
    throw Error("Invalid usage envelope");
  }
  const receipt = payload.receipt;
  let accounting;
  try {
    // Match the server's ASCII JSON byte bound, including escaped UTF-16 units.
    const raw = JSON.stringify(payload.accounting).replace(/[\u007f-\uffff]/g,
      char => `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`);
    if (raw.length > 4096 || !validAccounting(payload.accounting)) throw Error("Invalid accounting");
    accounting = ["receipt_key_sha256", "run_id", "expires_at"].every(k => payload.accounting[k] === receipt[k])
      ? payload.accounting : unavailableAccounting(receipt, "binding_mismatch");
  } catch { accounting = unavailableAccounting(receipt); }
  return { receipt, accounting };
}

export function clearAccounting(byId) {
  byId("accounting").hidden = true;
  for (const id of ["accounting-status", "accounting-usage", "accounting-cost", "accounting-reservation", "accounting-facts"]) byId(id).textContent = "";
}

export function renderAccounting({ accounting: a }, byId) {
  byId("accounting").hidden = false;
  byId("accounting-status").textContent = `核算发布：${a.publication_state} · 派发：${a.dispatch_state} · 原生账本：${a.native_journal_state}`;
  const u = a.usage, c = a.cost;
  byId("accounting-usage").textContent = `${u.status} · 输入 ${u.prompt_tokens === null ? "未知" : u.prompt_tokens} / 输出 ${u.completion_tokens === null ? "未知" : u.completion_tokens} / 合计 ${u.total_tokens === null ? "未知" : u.total_tokens} tokens`;
  // Preserve all nine decimal places. A tiny positive estimate must not become
  // $0.00; null is unavailable observation, never a free operation.
  byId("accounting-cost").textContent = `${c.status} · ${c.estimated_usd === null ? "费用估算不可用" : `USD ${c.estimated_usd}`}`;
  byId("accounting-reservation").textContent = `预算预留：${c.reservation_usd === null ? "未知" : `USD ${c.reservation_usd}`}（不是消费或退款）`;
  byId("accounting-facts").textContent = JSON.stringify(a, null, 2);
}
