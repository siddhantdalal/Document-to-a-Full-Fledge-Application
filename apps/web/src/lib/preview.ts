import type { PreviewState } from "./types";

const BASE = "/api";

export async function startPreview(jobId: string): Promise<PreviewState> {
  const res = await fetch(`${BASE}/jobs/${jobId}/preview/start`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`start failed (${res.status}): ${await res.text()}`);
  }
  return res.json();
}

export async function stopPreview(jobId: string): Promise<void> {
  const res = await fetch(`${BASE}/jobs/${jobId}/preview/stop`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`stop failed (${res.status}): ${await res.text()}`);
  }
}

export async function fetchPreviewLogs(jobId: string, tail = 200): Promise<string[]> {
  const res = await fetch(`${BASE}/jobs/${jobId}/preview/logs?tail=${tail}`);
  if (!res.ok) {
    throw new Error(`logs failed (${res.status})`);
  }
  const body = (await res.json()) as { lines: string[] };
  return body.lines;
}
