import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { loadKey } from "../lib/keyStore";
import { refineJob } from "../lib/refine";

const PROVIDERS = [
  { id: "anthropic", label: "Anthropic" },
  { id: "openai", label: "OpenAI" },
  { id: "gemini", label: "Google Gemini" },
];

const MODELS_BY_PROVIDER: Record<string, { id: string; label: string }[]> = {
  anthropic: [
    { id: "claude-opus-4-7", label: "Claude Opus 4.7" },
    { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
    { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
  ],
  openai: [
    { id: "gpt-4o", label: "GPT-4o" },
    { id: "gpt-4o-mini", label: "GPT-4o mini" },
    { id: "o1", label: "o1" },
  ],
  gemini: [
    { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
    { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
  ],
};

const KEY_PLACEHOLDER: Record<string, string> = {
  anthropic: "sk-ant-...",
  openai: "sk-...",
  gemini: "AIza...",
};

const inputClass =
  "mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200";

export function RefinePanel({ jobId, hasSpec }: { jobId: string; hasSpec: boolean }) {
  const navigate = useNavigate();
  const [message, setMessage] = useState("");
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState(MODELS_BY_PROVIDER.anthropic[0].id);
  const [key, setKey] = useState("");
  const [hasStoredKey, setHasStoredKey] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadKey()
      .then((stored) => {
        if (cancelled || !stored) return;
        setProvider(stored.provider);
        const list = MODELS_BY_PROVIDER[stored.provider] ?? [];
        if (list.length > 0) setModel(list[0].id);
        setKey(stored.key);
        setHasStoredKey(true);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  function changeProvider(next: string) {
    setProvider(next);
    const list = MODELS_BY_PROVIDER[next] ?? [];
    if (list.length > 0) setModel(list[0].id);
  }

  if (!hasSpec) return null;

  const canSubmit = message.trim().length > 0 && key.length > 0 && !submitting;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const child = await refineJob(jobId, {
        userMessage: message.trim(),
        provider,
        model,
        key,
      });
      navigate(`/jobs/${child.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          Refine
        </h3>
        <p className="mt-1 text-xs text-slate-500">
          Describe a change. The spec is updated by the AI; everything you didn't ask
          to change stays the same.
        </p>
      </div>

      <form onSubmit={onSubmit} className="space-y-3">
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="e.g. Add a 'priority' field to Todo, with values 'low', 'medium', 'high'."
          rows={3}
          className={`${inputClass} resize-y`}
        />

        <details className="rounded-lg border border-slate-200 bg-slate-50/50 px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium text-slate-600">
            Provider &amp; key {hasStoredKey && <span className="text-emerald-600">· stored</span>}
          </summary>
          <div className="mt-3 space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <span className="text-xs font-medium text-slate-600">Provider</span>
                <select
                  value={provider}
                  onChange={(e) => changeProvider(e.target.value)}
                  className={inputClass}
                >
                  {PROVIDERS.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="text-xs font-medium text-slate-600">Model</span>
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className={inputClass}
                >
                  {(MODELS_BY_PROVIDER[provider] ?? []).map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="block">
              <span className="text-xs font-medium text-slate-600">API key</span>
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder={KEY_PLACEHOLDER[provider] ?? "sk-..."}
                autoComplete="off"
                spellCheck={false}
                className={`${inputClass} font-mono`}
              />
            </label>
          </div>
        </details>

        {error && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {submitting ? "Refining…" : "Send change"}
        </button>
      </form>
    </div>
  );
}
