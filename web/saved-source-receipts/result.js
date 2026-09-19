/* Pure wire validation and inert presentation; no fetch, storage or authority. */
// A plain JS dollar anchor also admits a final newline; require the actual end.
export const runPattern = /^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}$(?![\s\S])/;
export const keyPattern = /^v1\.[0-9]{10}\.[0-9a-f]{64}$(?![\s\S])/;
export const points = value => Array.from(value).length;
// Python str.strip includes U+0085 and U+001C..1F, unlike JavaScript trim.
export const isBlank = value => /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u.test(value);
const integer = (v, min, max) => Number.isSafeInteger(v) && v >= min && v <= max;
const string = (v, min, max) => typeof v === "string" && points(v) >= min && points(v) <= max
  && !/[\uD800-\uDFFF]/u.test(v);
const nullable = (v, max) => v === null || string(v, 0, max);
const hash = v => typeof v === "string" && /^[a-f0-9]{64}$(?![\s\S])/.test(v);
export const keys = (v, expected) => v !== null && typeof v === "object" && !Array.isArray(v)
  && Object.keys(v).length === expected.length && expected.every(k => Object.hasOwn(v, k));
export async function digest(text) {
  const raw = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(raw), byte => byte.toString(16).padStart(2, "0")).join("");
}
// Python canonical JSON string hashing escapes each UTF-16 unit, including DEL.
const canonicalString = text => JSON.stringify(text).replace(/[\u007f-\uffff]/g,
  char => `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`);
const reasons = {
  saved_text: "excerpt", saved_text_missing: "missing_text", saved_text_blank: "blank_text",
  empty_snapshot: "no_sources", selector_declined: "declined", selector_refused: "declined",
  selected_text_too_long: "out_of_scope", callback_budget_exceeded: "out_of_scope",
  selector_error: "unavailable", read_error: "unavailable", invalid_assistant_message: "failed",
  unadvertised_tool: "failed", invalid_arguments: "failed", read_id_not_permitted: "failed",
  invalid_decline: "failed", invalid_read_result: "failed", mixed_response: "failed",
};
const labels = {
  excerpt: "已交付保存文本", missing_text: "来源存在，但没有保存文本", blank_text: "保存文本仅含空白",
  no_sources: "保存目录没有来源", declined: "Selector 未选择来源", out_of_scope: "超出本次定位范围",
  unavailable: "定位不可用", failed: "定位契约失败",
};
function validCatalog(c) {
  return keys(c, ["catalog_hash", "catalog_bytes", "total_count", "returned_count", "omitted_count", "coverage", "title_truncation_count"])
    && hash(c.catalog_hash) && integer(c.catalog_bytes, 1, 6144) && integer(c.total_count, 0, 256)
    && integer(c.returned_count, 0, 32) && integer(c.omitted_count, 0, 256)
    && integer(c.title_truncation_count, 0, c.returned_count)
    && c.returned_count + c.omitted_count === c.total_count && (c.total_count === 0 || c.returned_count > 0)
    && c.coverage === (c.omitted_count ? "partial" : "complete");
}
function validSource(s) {
  return keys(s, ["source_id", "group", "title", "publisher", "source_type", "url", "doi", "published_date", "accessed_date", "origin", "stored_length", "snapshot_hash", "source_hash", "summary_hash"])
    && typeof s.source_id === "string" && /^[APM][1-9][0-9]{0,8}$(?![\s\S])/.test(s.source_id)
    && typeof s.group === "string" && Object.hasOwn({ academic: 1, patent: 1, market: 1 }, s.group)
    && s.source_id[0] === { academic: "A", patent: "P", market: "M" }[s.group]
    && string(s.title, 1, 1024) && string(s.publisher, 1, 512) && string(s.source_type, 1, 64)
    && nullable(s.url, 4096) && nullable(s.doi, 512) && nullable(s.published_date, 32)
    && string(s.accessed_date, 1, 32) && ["abstract", "search_snippet", "unknown"].includes(s.origin)
    && integer(s.stored_length, 0, 100000) && [s.snapshot_hash, s.source_hash, s.summary_hash].every(hash);
}
export async function validResult(r) {
  if (!keys(r, ["method_id", "state", "reason", "catalog", "source", "saved_text", "callback_entries", "callback_bytes", "read_attempts", "read_completed", "selection_relevance", "semantic_support"])
      || r.method_id !== "report_evidence_source_locator_v1" || typeof r.reason !== "string"
      || !Object.hasOwn(reasons, r.reason) || reasons[r.reason] !== r.state || !validCatalog(r.catalog)
      || r.selection_relevance !== "not_assessed" || r.semantic_support !== "not_assessed"
      || ![r.callback_entries, r.read_attempts, r.read_completed].every(v => integer(v, 0, 1))) return false;
  const preEntry = ["empty_snapshot", "callback_budget_exceeded"].includes(r.reason);
  if (r.callback_entries !== Number(!preEntry)) return false;
  if (r.reason === "empty_snapshot") {
    if (r.catalog.total_count !== 0 || r.callback_bytes !== null) return false;
  } else if (r.catalog.returned_count === 0 || !integer(r.callback_bytes, 1, Number.MAX_SAFE_INTEGER)
      || (r.callback_bytes > 12288) !== (r.reason === "callback_budget_exceeded")) return false;
  const read = ["saved_text", "saved_text_missing", "saved_text_blank", "read_error", "invalid_read_result"].includes(r.reason);
  if (r.read_attempts !== Number(read) || r.read_completed !== Number(read && r.reason !== "read_error")) return false;
  const hasSource = read || r.reason === "selected_text_too_long";
  if (hasSource ? !validSource(r.source) : r.source !== null) return false;
  if (hasSource && (r.source.stored_length > 1500) !== (r.reason === "selected_text_too_long")) return false;
  if (["excerpt", "blank_text"].includes(r.state)) {
    const t = r.saved_text;
    if (!keys(t, ["text", "start", "end", "window_truncated", "text_sha256", "text_scope"])
        || !string(t.text, 1, 1500) || t.start !== 0 || !integer(t.end, 1, 1500)
        || t.end !== points(t.text) || t.end !== r.source.stored_length || t.window_truncated !== false
        || !hash(t.text_sha256) || t.text_scope !== "saved_summary_only"
        || isBlank(t.text) !== (r.state === "blank_text") || await digest(t.text) !== t.text_sha256
        || await digest(canonicalString(t.text)) !== r.source.summary_hash) return false;
  } else if (r.saved_text !== null) return false;
  return r.state !== "missing_text" || (r.source.stored_length === 0
    && [await digest("null"), await digest('""')].includes(r.source.summary_hash));
}
const receiptErrors = ["saved_source_missing", "saved_source_unavailable", "execution_unavailable", "concurrency_limit",
  "daily_quota_exceeded", "paid_ledger_unavailable", "access_denied", "request_abandoned"];
export async function validReceipt(p, key, expectedRun = null) {
  if (!keys(p, ["schema_version", "operation", "receipt_key_sha256", "state", "run_id", "expires_at", "admission_state", "provider_usage", "provider_cost", "error_code", "delivery", "delivery_snapshot_reads", "delivery_source_reads", "result"])
      || p.schema_version !== 1 || p.operation !== "saved_source_location_v1" || !hash(p.receipt_key_sha256)
      || p.receipt_key_sha256 !== await digest(key) || typeof p.run_id !== "string" || !runPattern.test(p.run_id)
      || (expectedRun !== null && p.run_id !== expectedRun) || !integer(p.expires_at, 1, Number.MAX_SAFE_INTEGER)
      || p.expires_at !== Number(key.split(".")[1]) + 86400
      || !["not_admitted", "unknown", "admitted"].includes(p.admission_state)
      || p.provider_usage !== "not_observed" || p.provider_cost !== "not_observed"
      || ![p.delivery_snapshot_reads, p.delivery_source_reads].every(v => integer(v, 0, 1))
      || p.delivery_source_reads > p.delivery_snapshot_reads) return false;
  if (["pending", "unknown", "failed"].includes(p.state)) {
    const beforeAdmission = ["saved_source_missing", "saved_source_unavailable", "concurrency_limit",
      "daily_quota_exceeded", "access_denied", "request_abandoned"];
    if (p.state === "failed" && beforeAdmission.includes(p.error_code) && p.admission_state !== "not_admitted") return false;
    return p.delivery === "not_ready" && p.result === null && p.delivery_snapshot_reads === 0
      && p.delivery_source_reads === 0 && (p.state === "failed" ? receiptErrors.includes(p.error_code) : p.error_code === null);
  }
  if (p.state !== "completed" || p.error_code !== null || p.admission_state === "unknown") return false;
  if (p.delivery === "available") {
    if (!await validResult(p.result) || p.admission_state !== (p.result.callback_entries ? "admitted" : "not_admitted")) return false;
    const reread = ["excerpt", "blank_text", "missing_text"].includes(p.result.state);
    return p.delivery_source_reads === Number(p.delivery_snapshot_reads === 1 && reread);
  }
  return ["expired", "changed", "unavailable"].includes(p.delivery) && p.result === null
    && p.delivery_snapshot_reads === 1 && (p.delivery === "unavailable" || p.delivery_source_reads === 0);
}
const safeErrors = {
  400: ["invalid_receipt_key"], 401: ["access_denied"], 403: ["origin_denied"],
  404: ["receipt_not_found", "not_found"], 405: ["method_not_allowed"], 409: ["receipt_conflict"],
  410: ["receipt_expired"], 413: ["body_too_large"], 415: ["unsupported_media_type"], 422: ["invalid_request"],
  429: ["locator_busy"], 431: ["headers_too_large"],
  503: ["selector_disabled", "controller_closed", "receipt_capacity", "receipt_unavailable", "execution_unavailable", "request_abandoned"],
};
export function validError(status, p) {
  return keys(p, ["detail", "error_code"]) && p.detail === "Saved-source receipt request could not be completed."
    && typeof p.error_code === "string" && (safeErrors[status] ?? []).includes(p.error_code);
}
// Reject duplicate JSON members too: JSON.parse alone silently keeps the last.
export function strictJSON(raw) {
  let pos = 0;
  const fail = () => { throw Error("Invalid response JSON"); };
  const whitespace = () => { while (/[\t\n\r ]/.test(raw[pos] ?? "!") && pos < raw.length) pos++; };
  function quoted() {
    const start = pos++;
    while (pos < raw.length) {
      const char = raw[pos++];
      if (char === '"') return JSON.parse(raw.slice(start, pos));
      if (char === "\\") pos++;
    }
    return fail();
  }
  function value(depth = 0) {
    if (depth > 24) return fail();
    whitespace();
    if (raw[pos] === '"') return quoted();
    if (raw[pos] === "{" || raw[pos] === "[") {
      const object = raw[pos++] === "{", end = object ? "}" : "]";
      const result = object ? Object.create(null) : [];
      whitespace();
      if (raw[pos] === end) { pos++; return result; }
      while (pos < raw.length) {
        whitespace();
        if (object) {
          if (raw[pos] !== '"') return fail();
          const key = quoted(); whitespace();
          if (Object.hasOwn(result, key) || raw[pos++] !== ":") return fail();
          result[key] = value(depth + 1);
        } else result.push(value(depth + 1));
        whitespace();
        if (raw[pos] === end) { pos++; return result; }
        if (raw[pos++] !== ",") return fail();
      }
      return fail();
    }
    const token = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(raw.slice(pos));
    if (!token) return fail();
    pos += token[0].length;
    const parsed = JSON.parse(token[0]);
    // This wire contains integer facts only. Preserve strict Python int types
    // instead of accepting 1.0/1e0 after JavaScript has erased that distinction.
    if (typeof parsed === "number" && (!Number.isSafeInteger(parsed) || /[.eE]/.test(token[0]))) return fail();
    return parsed;
  }
  const result = value(); whitespace();
  if (pos !== raw.length) return fail();
  return result;
}
export async function readBody(response) {
  if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(response.headers.get("content-type") ?? "")
      || !response.body || typeof response.body.getReader !== "function") throw Error("Invalid response type");
  const reader = response.body.getReader(), chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array)) throw Error("Invalid response bytes");
      size += value.byteLength;
      if (size > 128 * 1024) throw Error("Response too large");
      chunks.push(value);
    }
  } catch (error) {
    // Do not wait for cancellation of an untrusted/failed stream to settle.
    void reader.cancel().catch(() => {});
    throw error;
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return strictJSON(new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes));
}
export function clearDisplay(byId) {
  byId("receipt").hidden = true; byId("result").hidden = true; byId("saved-text").hidden = true;
  byId("source-metadata").replaceChildren();
  for (const id of ["receipt-context", "receipt-facts", "result-state", "catalog-coverage", "semantic-status", "saved-text", "text-status", "execution-facts"]) byId(id).textContent = "";
}
export function renderReceipt(p, byId, recovered) {
  byId("receipt-context").textContent = `Run ID: ${p.run_id}\n${recovered ? "恢复查询：原始问题未保存在浏览器，不能从回执还原。" : "本次提交的回执；原始问题不会写入浏览器存储。"}`;
  const { result: r, ...facts } = p;
  byId("receipt-facts").textContent = JSON.stringify(facts, null, 2);
  byId("receipt").hidden = false;
  if (r === null) return;
  const c = r.catalog;
  byId("result-state").textContent = `${labels[r.state]} · ${r.state}`;
  byId("catalog-coverage").textContent = `目录覆盖 ${c.coverage}：展示 ${c.returned_count} / 共 ${c.total_count}；省略 ${c.omitted_count}；标题截短 ${c.title_truncation_count}。标题不是已读证据。`;
  byId("semantic-status").textContent = "选择相关性 selection_relevance: not_assessed · 语义支持 semantic_support: not_assessed。未验证来源真实性或主张支持。";
  if (r.source !== null) {
    const fields = { source_id: "来源 ID", group: "分组", title: "标题", publisher: "发布者", source_type: "类型", url: "保存 URL", doi: "DOI", published_date: "发布日期", accessed_date: "访问日期", origin: "文本来源", stored_length: "保存码点数" };
    for (const [key, label] of Object.entries(fields)) {
      const term = document.createElement("dt"), value = document.createElement("dd");
      term.textContent = label; value.textContent = r.source[key] === null ? "未保存（null）" : String(r.source[key]);
      byId("source-metadata").append(term, value);
    }
  }
  if (r.saved_text !== null) {
    // Preserve every code point and whitespace; never HTML, links or Markdown.
    byId("saved-text").textContent = r.saved_text.text;
    byId("saved-text").hidden = false;
    byId("text-status").textContent = `仅已保存摘要 saved_summary_only；完整 ${r.saved_text.end} 个码点，未截断。${r.state === "blank_text" ? "仅含空白，不是实质证据。" : ""}`;
  } else byId("text-status").textContent = `未交付文本（${r.reason}），不是语义支持结论。`;
  byId("execution-facts").textContent = JSON.stringify({
    reason: r.reason, callback_entries: r.callback_entries, callback_bytes: r.callback_bytes,
    read_attempts: r.read_attempts, read_completed: r.read_completed,
    catalog_hash: c.catalog_hash, catalog_bytes: c.catalog_bytes,
    snapshot_hash: r.source?.snapshot_hash ?? null, source_hash: r.source?.source_hash ?? null,
    summary_hash: r.source?.summary_hash ?? null, text_sha256: r.saved_text?.text_sha256 ?? null,
  }, null, 2);
  byId("result").hidden = false;
}
