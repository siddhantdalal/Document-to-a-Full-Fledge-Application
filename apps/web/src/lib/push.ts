const BASE = "/api";

export interface PushRequest {
  token: string;
  owner: string;
  repo: string;
  private: boolean;
  commitMessage?: string;
}

export interface PushResult {
  repo_url: string;
  branch: string;
  commit_sha: string;
}

export async function pushToGitHub(jobId: string, input: PushRequest): Promise<PushResult> {
  const res = await fetch(`${BASE}/jobs/${jobId}/push`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      token: input.token,
      owner: input.owner,
      repo: input.repo,
      private: input.private,
      commit_message: input.commitMessage,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    try {
      const body = JSON.parse(text);
      throw new Error(body.detail ?? text);
    } catch {
      throw new Error(text || `push failed (${res.status})`);
    }
  }
  return res.json();
}
