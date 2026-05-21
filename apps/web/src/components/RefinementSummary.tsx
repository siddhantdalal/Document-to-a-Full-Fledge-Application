import { Link } from "react-router-dom";

import type { DiffOpType, Refinement } from "../lib/types";

const TYPE_STYLES: Record<DiffOpType, string> = {
  added: "bg-emerald-100 text-emerald-700",
  removed: "bg-rose-100 text-rose-700",
  modified: "bg-amber-100 text-amber-700",
};

export function RefinementSummary({ refinement }: { refinement: Refinement }) {
  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-5 shadow-sm">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-indigo-700">
          Refinement
        </h3>
        <Link
          to={`/jobs/${refinement.parent_job_id}`}
          className="text-xs font-medium text-indigo-600 hover:underline"
        >
          ← parent job
        </Link>
      </div>

      <blockquote className="mb-4 rounded-lg border-l-2 border-indigo-300 bg-white px-3 py-2 text-sm text-slate-700">
        {refinement.user_message}
      </blockquote>

      {refinement.diff ? (
        <DiffList diff={refinement.diff} />
      ) : (
        <p className="text-sm text-slate-500">Computing diff…</p>
      )}
    </div>
  );
}

function DiffList({ diff }: { diff: NonNullable<Refinement["diff"]> }) {
  if (diff.operations.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No spec changes — the request matched what was already there.
      </p>
    );
  }
  return (
    <>
      <div className="mb-2 flex gap-2 text-xs">
        <Pill label="added" count={diff.summary.added} type="added" />
        <Pill label="removed" count={diff.summary.removed} type="removed" />
        <Pill label="modified" count={diff.summary.modified} type="modified" />
      </div>
      <ul className="space-y-1.5 text-sm">
        {diff.operations.map((op, i) => (
          <li key={i} className="flex items-baseline gap-2">
            <span
              className={`inline-flex rounded px-1.5 py-0.5 text-xs font-medium capitalize ${TYPE_STYLES[op.type]}`}
            >
              {op.type}
            </span>
            <span className="text-xs uppercase tracking-wide text-slate-500">{op.kind}</span>
            <span className="font-mono text-slate-800">{op.label}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function Pill({
  label,
  count,
  type,
}: {
  label: string;
  count: number;
  type: DiffOpType;
}) {
  if (count === 0) return null;
  return (
    <span className={`rounded-full px-2 py-0.5 font-medium ${TYPE_STYLES[type]}`}>
      {count} {label}
    </span>
  );
}
