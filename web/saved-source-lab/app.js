/* Independent callback-only UI: no production client, keys or persistence. */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const form = byId("locator-form"), runId = byId("run-id"), question = byId("question");
  const submit = byId("locate"), status = byId("request-status"), result = byId("result");
  const sourceMetadata = byId("source-metadata"), savedText = byId("saved-text");
  const runPattern = /^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}$/;
  const hashPattern = /^[a-f0-9]{64}$/;
  const points = value => Array.from(value).length;
  // Match Python str.strip(), including U+0085 and U+001C..1F (not JS trim).
  const isBlank = value => /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u.test(value);
  const integer = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max;
  const string = (value, min, max) => typeof value === "string" && points(value) >= min && points(value) <= max;
  const nullableString = (value, max) => value === null || string(value, 0, max);
  const hash = value => typeof value === "string" && hashPattern.test(value);
  const keys = (value, expected) => value !== null && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key));
  const reasonStates = {
    saved_text: "excerpt", saved_text_missing: "missing_text", saved_text_blank: "blank_text",
    empty_snapshot: "no_sources", selector_declined: "declined", selector_refused: "declined",
    selected_text_too_long: "out_of_scope", callback_budget_exceeded: "out_of_scope",
    selector_error: "unavailable", read_error: "unavailable", invalid_assistant_message: "failed",
    unadvertised_tool: "failed", invalid_arguments: "failed", read_id_not_permitted: "failed",
    invalid_decline: "failed", invalid_read_result: "failed", mixed_response: "failed",
  };
  const stateLabels = {
    excerpt: "已交付保存文本", missing_text: "来源存在，但没有保存文本",
    blank_text: "保存文本仅含空白", no_sources: "保存目录没有来源",
    declined: "Selector 未选择来源", out_of_scope: "超出本次定位范围",
    unavailable: "定位不可用", failed: "定位契约失败",
  };

  function validCatalog(catalog) {
    return keys(catalog, ["catalog_hash", "catalog_bytes", "total_count", "returned_count", "omitted_count", "coverage", "title_truncation_count"])
      && hash(catalog.catalog_hash) && integer(catalog.catalog_bytes, 1, 6144)
      && integer(catalog.total_count, 0, 256) && integer(catalog.returned_count, 0, 32)
      && integer(catalog.omitted_count, 0, 256) && integer(catalog.title_truncation_count, 0, catalog.returned_count)
      && catalog.returned_count + catalog.omitted_count === catalog.total_count
      && (catalog.total_count === 0 || catalog.returned_count > 0)
      && catalog.coverage === (catalog.omitted_count ? "partial" : "complete");
  }

  function validSource(source) {
    return keys(source, ["source_id", "group", "title", "publisher", "source_type", "url", "doi", "published_date", "accessed_date", "origin", "stored_length", "snapshot_hash", "source_hash", "summary_hash"])
      && typeof source.source_id === "string" && /^[APM][1-9][0-9]{0,8}$/.test(source.source_id)
      && typeof source.group === "string" && Object.hasOwn({ academic: 1, patent: 1, market: 1 }, source.group)
      && source.source_id[0] === { academic: "A", patent: "P", market: "M" }[source.group]
      && string(source.title, 1, 1024) && string(source.publisher, 1, 512)
      && string(source.source_type, 1, 64) && nullableString(source.url, 4096)
      && nullableString(source.doi, 512) && nullableString(source.published_date, 32)
      && string(source.accessed_date, 1, 32) && ["abstract", "search_snippet", "unknown"].includes(source.origin)
      && integer(source.stored_length, 0, 100000)
      && [source.snapshot_hash, source.source_hash, source.summary_hash].every(hash);
  }

  function validText(text, source, state) {
    return keys(text, ["text", "start", "end", "window_truncated", "text_sha256", "text_scope"])
      && string(text.text, 1, 1500) && text.start === 0 && integer(text.end, 1, 1500)
      && text.end === points(text.text) && text.end === source.stored_length
      && text.window_truncated === false && hash(text.text_sha256)
      && text.text_scope === "saved_summary_only" && isBlank(text.text) === (state === "blank_text");
  }

  function validEnvelope(envelope) {
    if (!keys(envelope, ["schema_version", "selector_mode", "billing_integration", "result"])
        || envelope.schema_version !== 1 || envelope.selector_mode !== "injected_callback"
        || envelope.billing_integration !== "not_implemented") return false;
    const r = envelope.result;
    if (!keys(r, ["method_id", "state", "reason", "catalog", "source", "saved_text", "callback_entries", "callback_bytes", "read_attempts", "read_completed", "selection_relevance", "semantic_support"])
        || r.method_id !== "report_evidence_source_locator_v1" || typeof r.reason !== "string" || !Object.hasOwn(reasonStates, r.reason)
        || reasonStates[r.reason] !== r.state || !validCatalog(r.catalog)
        || r.selection_relevance !== "not_assessed" || r.semantic_support !== "not_assessed"
        || !integer(r.callback_entries, 0, 1) || !integer(r.read_attempts, 0, 1) || !integer(r.read_completed, 0, 1)) return false;
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
    const hasText = ["excerpt", "blank_text"].includes(r.state);
    if (hasText ? !validText(r.saved_text, r.source, r.state) : r.saved_text !== null) return false;
    return r.state !== "missing_text" || r.source.stored_length === 0;
  }

  function clearResult() {
    result.hidden = true;
    sourceMetadata.replaceChildren();
    savedText.textContent = "";
    savedText.hidden = true;
    for (const id of ["result-state", "result-context", "catalog-coverage", "semantic-status", "text-status", "execution-facts"]) byId(id).textContent = "";
  }

  function setStatus(text, kind = "info") {
    status.textContent = text;
    status.dataset.kind = kind;
  }

  function render(envelope, input) {
    const r = envelope.result, c = r.catalog;
    byId("result-state").textContent = `${stateLabels[r.state]} · ${r.state}`;
    byId("result-context").textContent = `Run ID: ${input.run}\n问题: ${input.question}`;
    byId("catalog-coverage").textContent = `目录覆盖 ${c.coverage}：展示 ${c.returned_count} / 共 ${c.total_count}；省略 ${c.omitted_count}；标题截短 ${c.title_truncation_count}。标题不是已读证据。`;
    byId("semantic-status").textContent = "选择相关性 selection_relevance: not_assessed · 语义支持 semantic_support: not_assessed。未验证来源真实性或主张支持。";
    if (r.source !== null) {
      const labels = { source_id: "来源 ID", group: "分组", title: "标题", publisher: "发布者", source_type: "类型", url: "保存 URL", doi: "DOI", published_date: "发布日期", accessed_date: "访问日期", origin: "文本来源", stored_length: "保存码点数" };
      for (const [key, label] of Object.entries(labels)) {
        const term = document.createElement("dt"), value = document.createElement("dd");
        term.textContent = label;
        value.textContent = r.source[key] === null ? "未保存（null）" : String(r.source[key]);
        sourceMetadata.append(term, value);
      }
    }
    if (r.saved_text !== null) {
      // Do not trim, clip, normalize Unicode, or interpret saved text as HTML.
      savedText.textContent = r.saved_text.text;
      savedText.hidden = false;
      byId("text-status").textContent = `仅已保存摘要 saved_summary_only；完整 ${r.saved_text.end} 个码点，未截断。${r.state === "blank_text" ? "本段仅含空白，不是实质证据。" : ""}`;
    } else {
      byId("text-status").textContent = `本次没有交付文本（${r.reason}）；这不是语义支持结论。`;
    }
    // Hashes are displayed as identities, not checked authenticity or entailment.
    byId("execution-facts").textContent = JSON.stringify({
      reason: r.reason, callback_entries: r.callback_entries, callback_bytes: r.callback_bytes,
      read_attempts: r.read_attempts, read_completed: r.read_completed,
      catalog_hash: c.catalog_hash, catalog_bytes: c.catalog_bytes,
      snapshot_hash: r.source?.snapshot_hash ?? null, source_hash: r.source?.source_hash ?? null,
      summary_hash: r.source?.summary_hash ?? null, text_sha256: r.saved_text?.text_sha256 ?? null,
    }, null, 2);
    result.hidden = false;
  }

  function errorMessage(response, payload) {
    // Never reflect server detail, exception text, paths or untrusted diagnostics.
    if (!keys(payload, ["detail", "error_code"]) || typeof payload.detail !== "string"
        || typeof payload.error_code !== "string") return "响应格式不可用；未显示任何保存文本。";
    const known = {
      "503:selector_disabled": "Selector 未启用（selector_disabled）；没有执行定位。",
      "503:locator_closing": "隔离服务正在关闭（locator_closing）；请勿自动重试。",
      "429:locator_busy": "另一个定位仍在执行（locator_busy）；没有启动替代请求。",
    };
    return known[`${response.status}:${payload.error_code}`] ?? ({
      404: "未找到已保存来源（404）。", 413: "请求超出大小限制（413）。",
      422: "请求不符合契约（422）。", 502: "Selector 契约失败（502）。",
      503: "保存来源或执行不可用（503）。",
    }[response.status] ?? "定位请求失败；未显示任何保存文本。");
  }

  let generation = 0;
  let inFlight = false;
  function invalidate() {
    generation += 1;
    clearResult();
    setStatus(inFlight ? "输入已更改，旧结果已失效。等待原请求结束后才能再次提交。" : "输入已更改，请手动提交。" );
  }
  runId.addEventListener("input", invalidate);
  question.addEventListener("input", invalidate);
  form.addEventListener("reset", event => {
    event.preventDefault();
    runId.value = "";
    question.value = "";
    invalidate();
    runId.focus();
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (inFlight) return;
    clearResult();
    const input = { run: runId.value, question: question.value };
    if (!runPattern.test(input.run)) {
      setStatus("Run ID 格式无效：需要 YYYYMMDDThhmmssZ-32位小写十六进制。", "error");
      return;
    }
    if (!string(input.question, 1, 4096) || isBlank(input.question)) {
      setStatus("问题需要 1–4096 个 Unicode 码点，且不能仅含空白。", "error");
      return;
    }
    const requestGeneration = ++generation;
    const current = () => requestGeneration === generation && runId.value === input.run && question.value === input.question;
    inFlight = true;
    submit.disabled = true;
    form.setAttribute("aria-busy", "true");
    setStatus("正在定位保存来源；不会自动重试。" );
    try {
      const response = await fetch(`/api/runs/${input.run}/saved-source-location`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: input.question }), credentials: "omit", cache: "no-store", redirect: "error",
      });
      const payload = await response.json();
      if (!current()) return;
      if (response.status !== 200) {
        setStatus(errorMessage(response, payload), "error");
      } else if (!validEnvelope(payload)) {
        setStatus("响应格式不可用；未显示任何保存文本。", "error");
      } else {
        render(payload, input);
        setStatus("本次响应已显示；定位不等于证据支持。" );
      }
    } catch {
      if (current()) {
        clearResult();
        setStatus("请求或响应不可用；原请求可能仍在服务端执行。不会自动重试。", "error");
      }
    } finally {
      // Reset/edit invalidates delivery, never the lifetime of the occupied request.
      inFlight = false;
      submit.disabled = false;
      form.setAttribute("aria-busy", "false");
      if (!current()) setStatus("旧请求已结束，响应已丢弃。请确认当前输入后手动提交。" );
    }
  });
})();
