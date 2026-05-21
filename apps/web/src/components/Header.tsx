import { Link } from "react-router-dom";

export function Header() {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/75 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link
          to="/"
          className="flex items-center gap-2 font-semibold tracking-tight text-slate-900"
        >
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-sm">
            <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="currentColor" aria-hidden>
              <path d="M3 2.5A1.5 1.5 0 0 1 4.5 1h5L13 4.5V13.5A1.5 1.5 0 0 1 11.5 15h-7A1.5 1.5 0 0 1 3 13.5v-11ZM9 1.5v3A.5.5 0 0 0 9.5 5h3" />
              <path d="M6 9h4M6 11h3" stroke="white" strokeWidth="1" strokeLinecap="round" />
            </svg>
          </span>
          <span>
            doc<span className="text-indigo-600 px-0.5">→</span>app
          </span>
        </Link>
        <span className="hidden text-xs font-medium text-slate-500 sm:inline-block">
          spec-bound full-stack generator
        </span>
      </div>
    </header>
  );
}
