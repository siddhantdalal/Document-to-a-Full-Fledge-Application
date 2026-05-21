import type { Spec } from "../lib/types";

export function SpecPanel({ spec }: { spec: Spec }) {
  return (
    <div className="space-y-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">{spec.app.name}</h3>
        {spec.app.summary && (
          <p className="mt-0.5 text-sm text-slate-600">{spec.app.summary}</p>
        )}
      </div>

      <div className="grid grid-cols-4 gap-2 text-sm">
        <Stat label="Entities" value={spec.entities.length} />
        <Stat label="Endpoints" value={spec.endpoints.length} />
        <Stat label="Screens" value={spec.screens.length} />
        <Stat label="Auth" value={spec.auth?.type ?? "none"} />
      </div>

      <Section title={`Entities (${spec.entities.length})`} defaultOpen>
        <ul className="space-y-1 text-sm">
          {spec.entities.map((e) => (
            <li key={e.name} className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-medium text-slate-800">{e.name}</span>
              <span className="text-slate-500">
                {e.fields.map((f) => f.name).join(", ")}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`Endpoints (${spec.endpoints.length})`}>
        <ul className="space-y-1 text-sm">
          {spec.endpoints.map((e, i) => (
            <li key={`${e.method}-${e.path}-${i}`} className="flex items-baseline gap-3">
              <span className={`w-16 shrink-0 font-mono text-xs font-semibold ${methodColor(e.method)}`}>
                {e.method}
              </span>
              <span className="font-mono text-slate-700">{e.path}</span>
              {e.auth && <span className="text-xs text-slate-400">· auth</span>}
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`Screens (${spec.screens.length})`}>
        <ul className="space-y-1 text-sm">
          {spec.screens.map((s) => (
            <li key={s.name} className="flex items-baseline gap-2">
              <span className="font-medium text-slate-800">{s.name}</span>
              <span className="font-mono text-xs text-slate-500">{s.route}</span>
              {s.auth && <span className="text-xs text-slate-400">· auth</span>}
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-base font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function Section({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details open={defaultOpen} className="group border-t border-slate-100 pt-3">
      <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium text-slate-700 hover:text-slate-900">
        {title}
        <span className="text-slate-400 transition-transform group-open:rotate-90">›</span>
      </summary>
      <div className="mt-3 text-slate-700">{children}</div>
    </details>
  );
}

function methodColor(m: string): string {
  switch (m) {
    case "GET":
      return "text-emerald-600";
    case "POST":
      return "text-indigo-600";
    case "PUT":
    case "PATCH":
      return "text-amber-600";
    case "DELETE":
      return "text-rose-600";
    default:
      return "text-slate-600";
  }
}
