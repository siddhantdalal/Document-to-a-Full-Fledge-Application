import { useEffect, useState } from "react";

export function useElapsedMs(startIso: string | null, tickMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!startIso) return;
    const id = window.setInterval(() => setNow(Date.now()), tickMs);
    return () => window.clearInterval(id);
  }, [startIso, tickMs]);
  if (!startIso) return 0;
  return Math.max(0, now - new Date(startIso).getTime());
}
