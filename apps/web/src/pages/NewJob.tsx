import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { FileDrop } from "../components/FileDrop";
import { createJob } from "../lib/job";

const MODELS = [
  { id: "claude-opus-4-7", label: "Claude Opus 4.7" },
  { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
  { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
];

export function NewJob() {
  const navigate = useNavigate();
  const [doc, setDoc] = useState<File | null>(null);
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState(MODELS[0].id);
  const [key, setKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = !!doc && key.length > 0 && !submitting;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!doc) return;
    setSubmitting(true);
    setError(null);
    try {
      const job = await createJob({ doc, provider, model, key });
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
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
        className="space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"
      >
        <FileDrop value={doc} onChange={setDoc} />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Provider">
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className={selectClass}
            >
              <option value="anthropic">Anthropic</option>
            </select>
          </Field>

          <Field label="Model">
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className={selectClass}
            >
              {MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field
          label="API Key"
          hint="Sent only to the orchestrator with this request. Never stored."
        >
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="sk-ant-..."
            autoComplete="off"
            spellCheck={false}
            className={`${selectClass} font-mono`}
          />
        </Field>

        {error && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 font-medium text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {submitting ? "Starting…" : "Generate Application"}
        </button>
      </form>

      <p className="mt-6 text-center text-xs text-slate-400">
        Bring your own key. The generated app is yours to download and run.
      </p>
    </div>
  );
}

const selectClass =
  "mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200";

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
