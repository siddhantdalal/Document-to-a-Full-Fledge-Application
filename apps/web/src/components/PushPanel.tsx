import { useState, type FormEvent } from "react";

import { pushToGitHub, type PushResult } from "../lib/push";

const inputClass =
  "mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200";

export function PushPanel({ jobId, artifactReady }: { jobId: string; artifactReady: boolean }) {
  const [token, setToken] = useState("");
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [isPrivate, setIsPrivate] = useState(true);
  const [pushing, setPushing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PushResult | null>(null);

  if (!artifactReady) return null;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setPushing(true);
    setError(null);
    try {
      const out = await pushToGitHub(jobId, {
        token,
        owner: owner.trim(),
        repo: repo.trim(),
        private: isPrivate,
      });
      setResult(out);
      setToken("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPushing(false);
    }
  }

  const canSubmit =
    !pushing && token.length > 0 && owner.trim().length > 0 && repo.trim().length > 0;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
        Push to GitHub
      </h3>

      {result ? (
        <SuccessView result={result} onPushAnother={() => setResult(null)} />
      ) : (
        <form onSubmit={onSubmit} className="space-y-3">
          <Field
            label="Personal Access Token"
            hint="Needs the 'repo' scope. Stays in this browser; sent once per push."
          >
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="ghp_..."
              autoComplete="off"
              spellCheck={false}
              className={`${inputClass} font-mono`}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Owner">
              <input
                type="text"
                value={owner}
                onChange={(e) => setOwner(e.target.value)}
                placeholder="your-username"
                className={inputClass}
              />
            </Field>
            <Field label="Repo name">
              <input
                type="text"
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                placeholder="generated-app"
                className={inputClass}
              />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={isPrivate}
              onChange={(e) => setIsPrivate(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-200"
            />
            Create as private repo
          </label>
          {error && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={!canSubmit}
            className="w-full rounded-lg bg-slate-900 px-4 py-2 font-medium text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {pushing ? "Pushing…" : "Push to GitHub"}
          </button>
        </form>
      )}
    </div>
  );
}

function SuccessView({ result, onPushAnother }: { result: PushResult; onPushAnother: () => void }) {
  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
        <p className="text-sm font-medium text-emerald-700">Pushed successfully</p>
        <a
          href={result.repo_url}
          target="_blank"
          rel="noreferrer noopener"
          className="mt-1 block break-words font-mono text-xs text-emerald-700 underline"
        >
          {result.repo_url}
        </a>
        <p className="mt-1 text-xs text-emerald-700">
          {result.branch} · {result.commit_sha.slice(0, 7)}
        </p>
      </div>
      <button
        type="button"
        onClick={onPushAnother}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        Push to another repo
      </button>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}
