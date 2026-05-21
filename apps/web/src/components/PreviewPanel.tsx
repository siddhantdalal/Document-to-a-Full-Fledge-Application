import { useCallback, useEffect, useRef, useState } from "react";

import { fetchPreviewLogs, startPreview, stopPreview } from "../lib/preview";
import type { PreviewState } from "../lib/types";

const LOG_POLL_MS = 2500;

interface Props {
  jobId: string;
  preview: PreviewState | null;
  artifactReady: boolean;
  onChange: () => void;
}

export function PreviewPanel({ jobId, preview, artifactReady, onChange }: Props) {
  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [showLogs, setShowLogs] = useState(false);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  const status = preview?.status ?? null;
  const isRunning = status === "running";
  const isStarting = status === "starting";

  const pullLogs = useCallback(async () => {
    if (!isRunning) return;
    try {
      const lines = await fetchPreviewLogs(jobId, 300);
      setLogs(lines);
    } catch (err) {
      setLogs([`[client] ${err instanceof Error ? err.message : String(err)}`]);
    }
  }, [jobId, isRunning]);

  useEffect(() => {
    if (!isRunning || !showLogs) return;
    pullLogs();
    const id = window.setInterval(pullLogs, LOG_POLL_MS);
    return () => window.clearInterval(id);
  }, [isRunning, showLogs, pullLogs]);

  useEffect(() => {
    if (showLogs && logEndRef.current) {
      logEndRef.current.scrollIntoView({ block: "end" });
    }
  }, [logs, showLogs]);

  async function onLaunch() {
    setActing(true);
    setActionError(null);
    try {
      await startPreview(jobId);
      onChange();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActing(false);
    }
  }

  async function onStop() {
    setActing(true);
    setActionError(null);
    try {
      await stopPreview(jobId);
      setLogs([]);
      onChange();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActing(false);
    }
  }

  if (!artifactReady) {
    return null;
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          Live preview
        </h3>
        {status && <PreviewBadge status={status} />}
      </div>

      {!preview && (
        <>
          <p className="mb-3 text-sm text-slate-600">
            Spin up the generated app in Docker. Frontend on
            {" "}
            <code className="rounded bg-slate-100 px-1">:15173</code>,
            backend on <code className="rounded bg-slate-100 px-1">:18000</code>.
          </p>
          <button
            type="button"
            onClick={onLaunch}
            disabled={acting}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {acting ? "Starting…" : "Launch Preview"}
          </button>
        </>
      )}

      {isStarting && (
        <p className="text-sm text-slate-600">
          Building images and starting containers — this can take a minute or two on first run.
        </p>
      )}

      {isRunning && preview && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <PreviewLink label="Frontend" url={preview.frontend_url!} />
            <PreviewLink label="API" url={preview.backend_url!} />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowLogs((s) => !s)}
              className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              {showLogs ? "Hide logs" : "View logs"}
            </button>
            <button
              type="button"
              onClick={onStop}
              disabled={acting}
              className="rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {acting ? "Stopping…" : "Stop"}
            </button>
          </div>
          {showLogs && (
            <div className="max-h-72 overflow-y-auto rounded-lg bg-slate-900 p-3 font-mono text-xs leading-relaxed text-slate-200">
              {logs.length === 0 ? (
                <p className="text-slate-500">Waiting for output…</p>
              ) : (
                logs.map((line, i) => (
                  <div key={i} className="whitespace-pre-wrap break-all">
                    {line}
                  </div>
                ))
              )}
              <div ref={logEndRef} />
            </div>
          )}
        </div>
      )}

      {status === "failed" && preview && (
        <div className="space-y-2">
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            <p className="font-medium">Preview failed to start</p>
            <p className="mt-1 break-words font-mono text-xs">{preview.error}</p>
          </div>
          <button
            type="button"
            onClick={onLaunch}
            disabled={acting}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {acting ? "Retrying…" : "Try again"}
          </button>
        </div>
      )}

      {actionError && (
        <p className="mt-2 text-sm text-rose-700">{actionError}</p>
      )}
    </div>
  );
}

function PreviewBadge({ status }: { status: NonNullable<PreviewState["status"]> }) {
  const styles: Record<typeof status, string> = {
    starting: "bg-amber-100 text-amber-700",
    running: "bg-emerald-100 text-emerald-700",
    failed: "bg-rose-100 text-rose-700",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${styles[status]}`}
    >
      {status === "starting" && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      )}
      {status === "running" && (
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
      )}
      {status}
    </span>
  );
}

function PreviewLink({ label, url }: { label: string; url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer noopener"
      className="block rounded-lg border border-slate-200 bg-slate-50 p-3 transition hover:border-indigo-300 hover:bg-indigo-50"
    >
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-0.5 truncate font-mono text-xs text-indigo-600">{url}</p>
    </a>
  );
}
