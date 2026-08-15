/* HTTP client.
 *
 * Every network call the interface makes goes through here, so error shape and
 * base URL are decided once. Callers see either a resolved value or an
 * ApiError carrying the server's own message.
 */

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
  }
}

/* ── Access code ───────────────────────────────────────────────────────
 * Set only when a deployment defines ACCESS_CODE (see api/access.py). Stored
 * so the gate is not re-prompted on every reload; a wrong/rotated code is
 * discovered the moment any request comes back 401, at which point it is
 * dropped so the app does not keep resending a code the server will never
 * accept. */

const ACCESS_KEY = "access-code";

export const getAccessCode = () => localStorage.getItem(ACCESS_KEY);

export function setAccessCode(code) {
  if (code) localStorage.setItem(ACCESS_KEY, code);
  else localStorage.removeItem(ACCESS_KEY);
}

/* ── Bring-your-own-key ───────────────────────────────────────────────
 * The open alternative to the access code: a visitor's own LLM + Serper
 * keys, billed to them. sessionStorage rather than localStorage — these are
 * live third-party credentials, not a code minted for this deployment, so
 * they should not outlive the tab. */

const BYOK_KEY = "byok-credentials";

export function getByok() {
  try {
    return JSON.parse(sessionStorage.getItem(BYOK_KEY));
  } catch {
    return null;
  }
}

export function setByok(creds) {
  if (creds) sessionStorage.setItem(BYOK_KEY, JSON.stringify(creds));
  else sessionStorage.removeItem(BYOK_KEY);
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
    return JSON.parse(sessionStorage.getItem(BYOK_RUNS_KEY)) || [];
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
  const stored = getAccessCode();
  const headers = {
    ...(stored ? { "X-Access-Code": stored } : {}),
    ...(options.headers || {}),
  };

  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch (cause) {
    // fetch only rejects on a transport failure, so this is always "the
    // server is unreachable" rather than an application error.
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
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return null;
  const type = response.headers.get("content-type") ?? "";
  return type.includes("application/json") ? response.json() : response.text();
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

export const startRun = ({ topic, language, weight_profile, paper_id }) => {
  const byok = getByok();
  return request("/api/runs", json({
    topic,
    // The API distinguishes "auto-detect" (null) from a forced value; the
    // empty string a <select> yields is neither.
    language: language || null,
    weight_profile: weight_profile || null,
    paper_id: paper_id || null,
    // Present only in BYOK mode — omitted (not null) so a plain run without
    // these keys still authorizes on the access code alone server-side.
    ...(byok ? {
      llm_provider: byok.provider,
      llm_api_key: byok.llmKey,
      serper_api_key: byok.serperKey,
    } : {}),
  }));
};

export const getRun = (runId) => request(`/api/runs/${runId}`);

export const getProgress = (runId, since = 0) =>
  request(`/api/runs/${runId}/progress?since=${since}`);

export const cancelRun = (runId) =>
  request(`/api/runs/${runId}`, { method: "DELETE" });

// Same endpoint as cancelRun — the server stops a live run or deletes a
// finished one depending on its state (see api/main.py delete_run). Two
// names for the one call because the two call sites mean different things:
// this one is only ever reached for a run already known to be terminal.
export const deleteRun = (runId) =>
  request(`/api/runs/${runId}`, { method: "DELETE" });

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
