import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";

import { FileDrop } from "../components/FileDrop";
import { createJob } from "../lib/job";
import { clearKey, loadKey, saveKey } from "../lib/keyStore";

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

const selectClass =
  "mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200";

export function NewJob() {
  const navigate = useNavigate();
  const [doc, setDoc] = useState<File | null>(null);
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState(MODELS_BY_PROVIDER.anthropic[0].id);
  const [key, setKey] = useState("");
  const [remember, setRemember] = useState(false);
  const [maxTokens, setMaxTokens] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const models = MODELS_BY_PROVIDER[provider] ?? [];
  const canSubmit = !!doc && key.length > 0 && !submitting;

  useEffect(() => {
    let cancelled = false;
    loadKey()
      .then((stored) => {
        if (cancelled || !stored) return;
        setProvider(stored.provider);
        const list = MODELS_BY_PROVIDER[stored.provider] ?? [];
        if (list.length > 0) setModel(list[0].id);
        setKey(stored.key);
        setRemember(true);
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

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!doc) return;
    setSubmitting(true);
    setError(null);
    try {
      if (remember) {
        await saveKey(provider, key);
      } else {
        clearKey();
      }
      const parsedMax = maxTokens ? Number(maxTokens) : null;
      const job = await createJob({
        doc,
        provider,
        model,
        key,
        maxTokens: parsedMax,
      });
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLFormElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canSubmit) {
      e.preventDefault();
      e.currentTarget.requestSubmit();
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-12 sm:py-16">
      <header className="mb-8 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
          Document <span className="text-indigo-600">→</span> Application
        </h1>
        <p className="mx-auto mt-3 max-w-md text-slate-600">
          Upload a requirements document. We extract a structured spec and
          generate a runnable full-stack app — exactly what the document
          describes.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        onKeyDown={onKeyDown}
        className="space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8 animate-rise-in"
      >
        <FileDrop value={doc} onChange={setDoc} accept=".md,.markdown,.txt,.pdf,.docx" />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Provider">
            <select
              value={provider}
              onChange={(e) => changeProvider(e.target.value)}
              className={selectClass}
            >
              {PROVIDERS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Model">
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className={selectClass}
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field
          label="API Key"
          hint="Sent only to the orchestrator with this request. Never logged."
        >
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={KEY_PLACEHOLDER[provider] ?? "sk-..."}
            autoComplete="off"
            spellCheck={false}
            className={`${selectClass} font-mono`}
          />
        </Field>

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-200"
          />
          <span className="flex-1">
            <span className="font-medium text-slate-700">Remember key on this device</span>
            <span className="block text-xs text-slate-500">
              Stored in your browser only, encrypted with a non-extractable AES-GCM key.
            </span>
          </span>
        </label>

        <details className="group rounded-lg border border-slate-200 bg-slate-50/50 px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium text-slate-700 group-open:mb-3">
            Advanced
          </summary>
          <Field
            label="Max tokens per job"
            hint="Optional. Pipeline aborts if total input + output exceeds this."
          >
            <input
              type="number"
              min={1}
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
              placeholder="unlimited"
              className={selectClass}
            />
          </Field>
        </details>

        {error && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={!canSubmit}
          className="group flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 font-medium text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {submitting ? "Starting…" : "Generate application"}
          {canSubmit && !submitting && (
            <kbd className="rounded border border-white/40 px-1.5 py-0.5 text-[10px] font-mono opacity-80 group-hover:opacity-100">
              ⌘↵
            </kbd>
          )}
        </button>
      </form>
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
