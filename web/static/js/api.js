/* HTTP client.
 *
 * Every network call the interface makes goes through here, so error shape and
 * base URL are decided once. Callers see either a resolved value or an
 * ApiError carrying the server's own message.
 */

export class ApiError extends Error {
  constructor(status, detail, code = null) {
    super(detail || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/* ── Access code ───────────────────────────────────────────────────────
 * Set only when a deployment defines ACCESS_CODE (see api/access.py). Stored
 * so the gate is not re-prompted on every reload; a wrong/rotated code is
 * discovered the moment any request comes back 401, at which point it is
 * dropped so the app does not keep resending a code the server will never
 * accept. */

const ACCESS_KEY = "access-code";

// Storage is an optional persistence mechanism, not the authority to send a
// request. Latch a failing slot into page-local memory: retrying a failed
// remove on the next read could resurrect a stale credential. Nothing here
// bypasses server authentication or retries a paid POST. A reload ends this
// fallback; callers must not auto-reload after a failed credential removal.
function credentialSlot(storageName, key) {
  let memory = null, volatile = false;
  return {
    read() {
      if (!volatile) {
        try { memory = globalThis[storageName].getItem(key); }
        catch { volatile = true; }
      }
      return memory;
    },
    write(value) {
      memory = value;
      if (volatile) return false;
      try {
        const storage = globalThis[storageName];
        if (value === null) storage.removeItem(key);
        else storage.setItem(key, value);
        return true;
      } catch { volatile = true; return false; }
    },
    degraded: () => volatile,
  };
}

const accessSlot = credentialSlot("localStorage", ACCESS_KEY);
export const getAccessCode = () => accessSlot.read();

export function setAccessCode(code) {
  return accessSlot.write(code || null);
}

/* ── Bring-your-own-key ───────────────────────────────────────────────
 * The open alternative to the access code: a visitor's own LLM + Serper
 * keys, billed to them. sessionStorage rather than localStorage — these are
 * live third-party credentials, not a code minted for this deployment, so
 * they should not outlive the tab. */

const BYOK_KEY = "byok-credentials";
const byokSlot = credentialSlot("sessionStorage", BYOK_KEY);
export const storageDegraded = () => accessSlot.degraded() || byokSlot.degraded();

// Absence selects operator billing; corruption must never mean absence.
// Keep this allowlist aligned with API models and the visible provider select.
export const BYOK_PROVIDERS = ["deepseek", "qwen", "openai", "anthropic"];
function validateByok(creds) {
  if (!creds || typeof creds !== "object" || Array.isArray(creds)
    || !BYOK_PROVIDERS.includes(creds.provider)
    || ![creds.llmKey, creds.serperKey].every(value => typeof value === "string" && value.trim())) {
    throw new ApiError(0, "Saved BYOK credentials are invalid. Choose your credentials again before a paid operation.", "invalid_byok");
  }
  return creds;
}

export function getByok() {
  const raw = byokSlot.read();
  if (raw === null) return null;
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    // JSON syntax and schema failures share a safe error, never secret bytes.
    return validateByok(null);
  }
  return validateByok(parsed);
}

export function setByok(creds) {
  return byokSlot.write(creds === null ? null : JSON.stringify(validateByok(creds)));
}

/* A BYOK run gets no owner tag server-side (see api/access.py) and so never
 * appears in GET /api/runs for anyone — nothing is recorded past the run
 * directory itself. The sidebar for a BYOK visitor still needs *something*
 * to show, so this keeps a session-only list of the run ids they submitted:
 * gone the moment the tab closes (sessionStorage, not localStorage), fully
 * populated for as long as it's open. */

const BYOK_RUNS_KEY = "byok-runs";

export function getByokRuns() {
  try {
    const entries = JSON.parse(sessionStorage.getItem(BYOK_RUNS_KEY));
    // Browser storage can contain stale but valid JSON. A non-array must not
    // crash accepted-run navigation/refresh merely because parsing succeeded.
    return Array.isArray(entries) ? entries.filter((entry) => entry
      && typeof entry.run_id === "string" && typeof entry.topic === "string") : [];
  } catch {
    return [];
  }
}

export function addByokRun(runId, topic) {
  const runs = getByokRuns();
  runs.unshift({ run_id: runId, topic });
  sessionStorage.setItem(BYOK_RUNS_KEY, JSON.stringify(runs));
}

// Called after a successful deleteRun() so a removed BYOK run does not
// reappear in the sidebar on the next refresh — the server-side directory
// is gone, but this session list is a separate, client-only record of it.
export function removeByokRun(runId) {
  const runs = getByokRuns().filter((r) => r.run_id !== runId);
  sessionStorage.setItem(BYOK_RUNS_KEY, JSON.stringify(runs));
}

async function request(path, options = {}) {
  const paidPost = options.method === "POST"
    && (/^\/api\/(runs|papers)$/.test(path) || /^\/api\/runs\/[^/]+\/resume$/.test(path));
  const acknowledgementUnknown = () => new ApiError(0,
    "The paid request may have been accepted, but its acknowledgement was not received. Check history before submitting again.",
    "paid_ack_unknown");
  const stored = getAccessCode();
  const headers = {
    ...(stored ? { "X-Access-Code": stored } : {}),
    ...(options.headers || {}),
  };

  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch (cause) {
    // Losing the response does not prove a paid POST never reached the server.
    // Never retry automatically or describe that ambiguous outcome as free.
    if (paidPost) throw acknowledgementUnknown();
    throw new ApiError(0, "Cannot reach the server. Is it still running?");
  }

  if (!response.ok) {
    if (response.status === 401) setAccessCode(null);
    let detail = "";
    try {
      const body = await response.json();
      detail = body.detail ?? "";
    } catch {
      detail = await response.text().catch(() => "");
    }
    // Additive response metadata keeps the legacy string detail contract.
    // Status 429 alone cannot distinguish daily quota from transient capacity.
    throw new ApiError(response.status, detail, response.headers.get("X-Error-Code"));
  }

  if (response.status === 204) return null;
  const type = response.headers.get("content-type") ?? "";
  try {
    return type.includes("application/json") ? await response.json() : await response.text();
  } catch (cause) {
    // A truncated 202 body loses the run capability just like a transport
    // failure. This is distinct from the explicit rejected HTTP path above.
    if (paidPost) throw acknowledgementUnknown();
    throw cause;
  }
}

const json = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/* ── Runs ──────────────────────────────────────────────────────────── */

export const health = () => request("/health");

// Verifies a code without storing it — the gate calls this with a candidate
// before persisting it, and once at boot with whatever is already stored (or
// none) to find out whether the deployment is gated at all.
export const checkAccess = (code) =>
  request("/api/access/check", { headers: code ? { "X-Access-Code": code } : {} });

export const listRuns = (limit = 50) => request(`/api/runs?limit=${limit}`);

export const startRun = ({
  topic,
  language,
  weight_profile,
  paper_id,
  decision_context,
}) => {
  const byok = getByok();
  return request("/api/runs", json({
    topic,
    // The API distinguishes "auto-detect" (null) from a forced value; the
    // empty string a <select> yields is neither.
    language: language || null,
    weight_profile: weight_profile || null,
    paper_id: paper_id || null,
    decision_context: decision_context || null,
    // Present only in BYOK mode — omitted (not null) so a plain run without
    // these keys still authorizes on the access code alone server-side.
    ...(byok ? {
      llm_provider: byok.provider,
      llm_api_key: byok.llmKey,
      serper_api_key: byok.serperKey,
    } : {}),
  }));
};

export const resumeRun = (runId) => {
  // Credentials are intentionally supplied again. The source run retains no
  // BYOK secret, and an access-code run is authorized by the normal header.
  const byok = getByok();
  return request(`/api/runs/${runId}/resume`, json({
    ...(byok ? {
      llm_provider: byok.provider,
      llm_api_key: byok.llmKey,
      serper_api_key: byok.serperKey,
    } : {}),
  }));
};

export const getRun = (runId) => request(`/api/runs/${runId}`);

export async function getProgress(runId, since = 0) {
  // Bound only this idempotent read, including its response body. Aborting a
  // paid POST would not cancel provider work and must not share this timeout.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15_000);
  try {
    return await request(`/api/runs/${runId}/progress?since=${since}`, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export const cancelRun = (runId) =>
  request(`/api/runs/${runId}?intent=cancel`, { method: "DELETE" });

// The state can change after the last poll. An explicit intent makes a stale
// button conflict instead of becoming a different destructive operation.
// A second GET before DELETE would still leave that race open.
export const deleteRun = (runId) =>
  request(`/api/runs/${runId}?intent=delete`, { method: "DELETE" });

export const getReport = (runId) => request(`/api/runs/${runId}/report`);

export const getArtifact = (runId, name) =>
  request(`/api/runs/${runId}/${name}`);

/* ── Papers ────────────────────────────────────────────────────────── */

export function uploadPaper(file) {
  const form = new FormData();
  form.append("file", file);
  // Extraction is an LLM call, so it is billed to somebody. A visitor on
  // their own keys sends them here for the same reason they send them with a
  // run: without this the endpoint answered 401 to everyone without a code,
  // and attaching a paper — half of what the composer offers — was closed to
  // exactly the people the BYOK path exists for.
  //
  // The serper key is not sent: extraction reads the PDF and calls the model,
  // and never searches.
  const byok = getByok();
  if (byok) {
    form.append("llm_provider", byok.provider);
    form.append("llm_api_key", byok.llmKey);
  }
  // No Content-Type header: the browser must set it so the multipart
  // boundary matches the body it generates.
  return request("/api/papers", { method: "POST", body: form });
}
