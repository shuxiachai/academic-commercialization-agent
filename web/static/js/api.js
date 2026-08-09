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

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (cause) {
    // fetch only rejects on a transport failure, so this is always "the
    // server is unreachable" rather than an application error.
    throw new ApiError(0, "Cannot reach the server. Is it still running?");
  }

  if (!response.ok) {
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

export const listRuns = (limit = 50) => request(`/api/runs?limit=${limit}`);

export const startRun = ({ topic, language, weight_profile, paper_id }) =>
  request("/api/runs", json({
    topic,
    // The API distinguishes "auto-detect" (null) from a forced value; the
    // empty string a <select> yields is neither.
    language: language || null,
    weight_profile: weight_profile || null,
    paper_id: paper_id || null,
  }));

export const getRun = (runId) => request(`/api/runs/${runId}`);

export const getProgress = (runId, since = 0) =>
  request(`/api/runs/${runId}/progress?since=${since}`);

export const cancelRun = (runId) =>
  request(`/api/runs/${runId}`, { method: "DELETE" });

export const getReport = (runId) => request(`/api/runs/${runId}/report`);

export const getArtifact = (runId, name) =>
  request(`/api/runs/${runId}/${name}`);

/* ── Papers ────────────────────────────────────────────────────────── */

export function uploadPaper(file) {
  const form = new FormData();
  form.append("file", file);
  // No Content-Type header: the browser must set it so the multipart
  // boundary matches the body it generates.
  return request("/api/papers", { method: "POST", body: form });
}
