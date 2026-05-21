import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { CoverageCard } from "../components/CoverageCard";
import { PreviewPanel } from "../components/PreviewPanel";
import { SpecPanel } from "../components/SpecPanel";
import { StageTimeline } from "../components/StageTimeline";
import { artifactUrl, getJob } from "../lib/job";
import type { Job, JobStatus as JS } from "../lib/types";

const POLL_MS = 800;

export function JobStatus() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pulse, setPulse] = useState(0);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    let timer: number | undefined;

    async function tick() {
      try {
        const next = await getJob(id!);
        if (cancelled) return;
        setJob(next);
        const jobRunning = next.status === "pending" || next.status === "running";
        const previewStarting = next.preview?.status === "starting";
        if (jobRunning || previewStarting) {
          timer = window.setTimeout(tick, POLL_MS);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }

    tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [id, pulse]);

  if (error) {
    return (
      <Shell>
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-rose-700">
          {error}
        </div>
        <BackLink />
      </Shell>
    );
  }

  if (!job) {
    return (
      <Shell>
        <div className="animate-pulse text-slate-500">Loading job…</div>
      </Shell>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:py-14">
      <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-baseline sm:justify-between">
        <div>
          <BackLink />
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
            {job.spec?.app.name ?? "Generating…"}
          </h1>
          {job.spec?.app.summary && (
            <p className="mt-1 max-w-2xl text-slate-600">{job.spec.app.summary}</p>
          )}
        </div>
        <StatusBadge status={job.status} />
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <aside className="lg:col-span-2">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
            Pipeline
          </h2>
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <StageTimeline stages={job.stages} />
            {(job.usage.total > 0 || job.max_tokens) && (
              <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-3 text-xs">
                <span className="font-medium text-slate-500">Tokens</span>
                <span className="font-mono text-slate-700">
                  {job.usage.total.toLocaleString()}
                  <span className="text-slate-400">
                    {" "}
                    ({job.usage.input.toLocaleString()} in /{" "}
                    {job.usage.output.toLocaleString()} out)
                  </span>
                  {job.max_tokens && (
                    <span className="text-slate-400"> · budget {job.max_tokens.toLocaleString()}</span>
                  )}
                </span>
              </div>
            )}
          </div>

          {job.artifact_ready && (
            <a
              href={artifactUrl(job.id)}
              download
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 font-medium text-white shadow-sm transition hover:bg-emerald-700"
            >
              <DownloadIcon /> Download project ZIP
            </a>
          )}

          {job.reconciliation && (
            <div className="mt-4">
              <CoverageCard reconciliation={job.reconciliation} />
            </div>
          )}

          {job.artifact_ready && (
            <div className="mt-4">
              <PreviewPanel
                jobId={job.id}
                preview={job.preview}
                artifactReady={job.artifact_ready}
                onChange={() => setPulse((p) => p + 1)}
              />
            </div>
          )}

          {job.error && (
            <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
              <p className="font-medium">Pipeline failed</p>
              <p className="mt-1 break-words font-mono text-xs">{job.error}</p>
            </div>
          )}
        </aside>

        <section className="lg:col-span-3">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
            Spec preview
          </h2>
          {job.spec ? (
            <SpecPanel spec={job.spec} />
          ) : (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white/60 p-10 text-center">
              <p className="text-sm font-medium text-slate-600">
                Extracting structured spec from your document…
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Once extracted, every entity, endpoint, and screen will appear here.
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-2xl px-4 py-16">{children}</div>;
}

function BackLink() {
  return (
    <Link
      to="/"
      className="text-sm font-medium text-indigo-600 hover:text-indigo-700 hover:underline"
    >
      ← New job
    </Link>
  );
}

function StatusBadge({ status }: { status: JS }) {
  const map: Record<JS, string> = {
    pending: "bg-slate-100 text-slate-700",
    running: "bg-indigo-100 text-indigo-700",
    succeeded: "bg-emerald-100 text-emerald-700",
    failed: "bg-rose-100 text-rose-700",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 self-start rounded-full px-3 py-1 text-xs font-medium capitalize ${map[status]}`}
    >
      {status === "running" && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      )}
      {status}
    </span>
  );
}

function DownloadIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden>
      <path d="M10 3a1 1 0 011 1v7.586l2.293-2.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 11.586V4a1 1 0 011-1z" />
      <path d="M4 14a1 1 0 011 1v1a1 1 0 001 1h8a1 1 0 001-1v-1a1 1 0 112 0v1a3 3 0 01-3 3H6a3 3 0 01-3-3v-1a1 1 0 011-1z" />
    </svg>
  );
}
