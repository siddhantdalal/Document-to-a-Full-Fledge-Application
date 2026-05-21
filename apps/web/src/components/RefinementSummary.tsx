import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getJob } from "../lib/job";
import type { DiffOpType, Job, Refinement } from "../lib/types";

const TYPE_STYLES: Record<DiffOpType, string> = {
  added: "bg-emerald-100 text-emerald-700",
  removed: "bg-rose-100 text-rose-700",
  modified: "bg-amber-100 text-amber-700",
};

interface LineageNode {
  id: string;
  name: string;
}

export function RefinementSummary({ refinement }: { refinement: Refinement }) {
  const [lineage, setLineage] = useState<LineageNode[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    buildLineage(refinement.parent_job_id, 6)
      .then((chain) => {
        if (!cancelled) setLineage(chain);
      })
      .catch(() => {
        if (!cancelled) setLineage([]);
      });
    return () => {
      cancelled = true;
    };
  }, [refinement.parent_job_id]);

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-5 shadow-sm animate-rise-in">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-indigo-700">
          Refinement
        </h3>
        {lineage && lineage.length > 0 && <LineageBreadcrumb chain={lineage} />}
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

function LineageBreadcrumb({ chain }: { chain: LineageNode[] }) {
  return (
    <nav aria-label="Refinement lineage" className="text-xs">
      <ol className="flex flex-wrap items-center gap-1">
        {chain.map((node, i) => (
          <li key={node.id} className="flex items-center gap-1">
            <Link
              to={`/jobs/${node.id}`}
              className="rounded px-1.5 py-0.5 font-medium text-indigo-600 hover:bg-indigo-100"
              title={node.id}
            >
              {node.name}
            </Link>
            {i < chain.length - 1 && <span className="text-slate-300">›</span>}
          </li>
        ))}
        <li className="flex items-center gap-1">
          <span className="text-slate-300">›</span>
          <span className="font-medium text-slate-500">current</span>
        </li>
      </ol>
    </nav>
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

async function buildLineage(seedJobId: string, maxDepth: number): Promise<LineageNode[]> {
  const visited = new Set<string>();
  const out: LineageNode[] = [];
  let currentId: string | null = seedJobId;
  for (let i = 0; i < maxDepth && currentId; i++) {
    if (visited.has(currentId)) break;
    visited.add(currentId);
    let job: Job;
    try {
      job = await getJob(currentId);
    } catch {
      break;
    }
    const name = job.spec?.app?.name ?? "(unnamed)";
    out.unshift({ id: currentId, name });
    currentId = job.refinement?.parent_job_id ?? null;
  }
  return out;
}
