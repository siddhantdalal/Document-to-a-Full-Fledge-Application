import type { Stage } from "../lib/types";

const LABELS: Record<string, string> = {
  extract_spec: "Extract Spec",
  generate: "Generate Files",
  package: "Package ZIP",
};

export function StageTimeline({ stages }: { stages: Stage[] }) {
  return (
    <ol className="relative space-y-5">
      <div className="absolute left-[14px] top-3 bottom-3 w-px bg-slate-200" aria-hidden />
      {stages.map((s) => (
        <li key={s.name} className="relative flex gap-4">
          <span
            className={[
              "z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 transition-all duration-300",
              indicatorClasses(s.status),
            ].join(" ")}
          >
            <StageIcon status={s.status} />
          </span>
          <div className="flex-1 pt-0.5">
            <p
              className={[
                "font-medium",
                s.status === "pending" ? "text-slate-400" : "text-slate-900",
              ].join(" ")}
            >
              {LABELS[s.name] ?? s.name}
            </p>
            {s.message && (
              <p className="mt-0.5 text-sm text-slate-500">{s.message}</p>
            )}
            {s.started_at && s.finished_at && (
              <p className="mt-0.5 text-xs text-slate-400">
                {duration(s.started_at, s.finished_at)}
              </p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function indicatorClasses(status: Stage["status"]): string {
  switch (status) {
    case "succeeded":
      return "border-emerald-500 bg-emerald-500 text-white";
    case "running":
      return "border-indigo-500 bg-white text-indigo-500 ring-4 ring-indigo-100";
    case "failed":
      return "border-rose-500 bg-rose-500 text-white";
    default:
      return "border-slate-300 bg-white text-slate-400";
  }
}

function StageIcon({ status }: { status: Stage["status"] }) {
  if (status === "succeeded") {
    return (
      <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden>
        <path
          fillRule="evenodd"
          d="M16.7 5.3a1 1 0 010 1.4l-7 7a1 1 0 01-1.4 0l-4-4a1 1 0 011.4-1.4L9 11.6l6.3-6.3a1 1 0 011.4 0z"
        />
      </svg>
    );
  }
  if (status === "failed") {
    return (
      <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden>
        <path
          fillRule="evenodd"
          d="M4.3 4.3a1 1 0 011.4 0L10 8.6l4.3-4.3a1 1 0 111.4 1.4L11.4 10l4.3 4.3a1 1 0 11-1.4 1.4L10 11.4l-4.3 4.3a1 1 0 11-1.4-1.4L8.6 10 4.3 5.7a1 1 0 010-1.4z"
        />
      </svg>
    );
  }
  if (status === "running") {
    return (
      <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
        />
      </svg>
    );
  }
  return <span className="h-1.5 w-1.5 rounded-full bg-current" />;
}

function duration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}
