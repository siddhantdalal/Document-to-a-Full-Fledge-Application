import type { Job } from "./types";

const BASE = "/api";

export interface CreateJobInput {
  doc: File;
  provider: string;
  model: string;
  key: string;
  maxTokens?: number | null;
}

export async function createJob(input: CreateJobInput): Promise<Job> {
  const fd = new FormData();
  fd.append("doc", input.doc);
  fd.append("provider", input.provider);
  fd.append("model", input.model);
  if (input.maxTokens != null) {
    fd.append("max_tokens", String(input.maxTokens));
  }
  const res = await fetch(`${BASE}/jobs`, {
    method: "POST",
    headers: { "X-Provider-Key": input.key },
    body: fd,
  });
  if (!res.ok) {
    throw new Error(`POST /jobs ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`${BASE}/jobs/${id}`);
  if (!res.ok) {
    throw new Error(`GET /jobs/${id} ${res.status}`);
  }
  return res.json();
}

export function artifactUrl(id: string): string {
  return `${BASE}/jobs/${id}/artifact`;
}
