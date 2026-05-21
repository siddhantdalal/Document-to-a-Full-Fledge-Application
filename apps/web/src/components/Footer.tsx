export function Footer() {
  return (
    <footer className="mt-12 border-t border-slate-200 bg-white/60">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-1 px-4 py-5 text-xs text-slate-500 sm:flex-row sm:justify-between">
        <p>Bring your own AI provider key. The generated app is yours to keep.</p>
        <p className="font-mono text-slate-400">
          extract · generate · validate · reconcile · package
        </p>
      </div>
    </footer>
  );
}
