import type { Job } from "./types";

const BASE = "/api";

export interface RefineInput {
  userMessage: string;
  provider: string;
  model: string;
  key: string;
  maxTokens?: number | null;
}

export async function refineJob(parentJobId: string, input: RefineInput): Promise<Job> {
  const res = await fetch(`${BASE}/jobs/${parentJobId}/refine`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Provider-Key": input.key,
    },
    body: JSON.stringify({
      user_message: input.userMessage,
      provider: input.provider,
      model: input.model,
      max_tokens: input.maxTokens ?? null,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    try {
      const body = JSON.parse(text);
      throw new Error(body.detail ?? text);
    } catch {
      throw new Error(text || `refine failed (${res.status})`);
    }
  }
  return res.json();
}
