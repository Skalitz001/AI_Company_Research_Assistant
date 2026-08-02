/** API client — native fetch only, snake_case fields, no secrets exposed. */

const BASE = "/api/v1";

/**
 * GET /api/v1/config — browser-safe configuration.
 * @returns {Promise<{ready:boolean, default_model:string, model_suggestions:string[], discord_enabled:boolean}>}
 */
export async function fetchConfig() {
  const res = await fetch(`${BASE}/config`);
  if (!res.ok) throw new Error(`Config request failed (${res.status})`);
  return res.json();
}

/**
 * GET /api/v1/health
 * @returns {Promise<{status:string}>}
 */
export async function fetchHealth() {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed (${res.status})`);
  return res.json();
}

/**
 * POST /api/v1/research — streams NDJSON events.
 *
 * @param {{query:string, model_id:string}} body
 * @param {AbortSignal} signal
 * @param {(event:object) => void} onEvent
 * @returns {Promise<void>}  resolves when the stream ends.
 */
export async function streamResearch(body, signal, onEvent) {
  const res = await fetch(`${BASE}/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  /* Pre-stream errors (validation, 503 CONFIG_MISSING, etc.) */
  if (!res.ok) {
    let payload;
    try {
      payload = await res.json();
    } catch {
      throw new Error(`Research request failed (${res.status})`);
    }
    /* Backend sends { error: { code, message, retryable } } or { detail: ... } */
    if (payload.error) {
      onEvent({ type: "error", error: payload.error });
      return;
    }
    throw new Error(payload.detail || `Research request failed (${res.status})`);
  }

  /* NDJSON line reader using ReadableStream */
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    /* Keep partial last line in the buffer */
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        onEvent(JSON.parse(trimmed));
      } catch {
        /* Ignore malformed lines */
      }
    }
  }
  /* Flush remaining buffer */
  if (buffer.trim()) {
    try {
      onEvent(JSON.parse(buffer.trim()));
    } catch {
      /* ignore */
    }
  }
}

/**
 * POST /api/v1/pdf — returns a Blob for download.
 *
 * @param {object} report  The validated research report.
 * @returns {Promise<Blob>}
 */
export async function fetchPdf(report) {
  const res = await fetch(`${BASE}/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ report }),
  });
  if (!res.ok) {
    let msg = `PDF generation failed (${res.status})`;
    try {
      const payload = await res.json();
      msg = payload.detail || payload.error?.message || msg;
    } catch {
      /* use default */
    }
    throw new Error(msg);
  }
  return res.blob();
}

/**
 * Trigger a browser download from a Blob.
 */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
