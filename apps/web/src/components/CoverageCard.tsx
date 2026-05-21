import type { CoverageBucket, Reconciliation } from "../lib/types";

const LABELS: Record<string, string> = {
  entities: "Entities",
  endpoints: "Endpoints",
  screens: "Screens",
};

export function CoverageCard({ reconciliation }: { reconciliation: Reconciliation }) {
  const { ok, coverage, missing, extra } = reconciliation;
  return (
    <div
      className={[
        "rounded-xl border p-5 shadow-sm",
        ok
          ? "border-emerald-200 bg-emerald-50/50"
          : "border-amber-200 bg-amber-50/50",
      ].join(" ")}
    >
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3
          className={[
            "text-sm font-semibold uppercase tracking-wider",
            ok ? "text-emerald-700" : "text-amber-700",
          ].join(" ")}
        >
          {ok ? "Spec fully covered" : "Coverage gaps"}
        </h3>
        <span
          className={[
            "text-xs font-medium",
            ok ? "text-emerald-600" : "text-amber-600",
          ].join(" ")}
        >
          {totalCovered(coverage)}/{totalAll(coverage)}
        </span>
      </div>

      <div className="space-y-2">
        {Object.entries(coverage).map(([key, bucket]) => (
          <Row key={key} label={LABELS[key] ?? key} bucket={bucket} ok={ok} />
        ))}
      </div>

      {missing.length > 0 && (
        <details className="mt-4 group">
          <summary className="cursor-pointer text-xs font-medium text-amber-700 hover:text-amber-800">
            {missing.length} missing item{missing.length === 1 ? "" : "s"}
          </summary>
          <ul className="mt-2 space-y-0.5 text-xs text-amber-700">
            {missing.map((m, i) => (
              <li key={i} className="font-mono">· {m}</li>
            ))}
          </ul>
        </details>
      )}

      {extra.length > 0 && (
        <details className="mt-2 group">
          <summary className="cursor-pointer text-xs font-medium text-slate-500 hover:text-slate-700">
            {extra.length} extra artifact{extra.length === 1 ? "" : "s"}
          </summary>
          <ul className="mt-2 space-y-0.5 text-xs text-slate-500">
            {extra.map((e, i) => (
              <li key={i} className="font-mono">· {e}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Row({ label, bucket, ok }: { label: string; bucket: CoverageBucket; ok: boolean }) {
  const pct = bucket.total === 0 ? 100 : Math.round((bucket.covered / bucket.total) * 100);
  const full = bucket.covered === bucket.total && bucket.total > 0;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="font-medium text-slate-700">{label}</span>
        <span className={full ? "text-emerald-700" : ok ? "text-emerald-700" : "text-amber-700"}>
          {bucket.covered}/{bucket.total}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white">
        <div
          className={[
            "h-full transition-all duration-500",
            full ? "bg-emerald-500" : "bg-amber-500",
          ].join(" ")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function totalCovered(c: Reconciliation["coverage"]): number {
  return Object.values(c).reduce((acc, b) => acc + b.covered, 0);
}

function totalAll(c: Reconciliation["coverage"]): number {
  return Object.values(c).reduce((acc, b) => acc + b.total, 0);
}
