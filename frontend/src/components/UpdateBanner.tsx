// A calm bar that tells a member a newer release is on the server. It never blocks anything and nothing is lost by ignoring it.
// Checks version.json when the tab regains focus or becomes visible, and about every 5 minutes (with jitter) while visible.
import { useEffect, useRef, useState } from "react";
import { APP_VERSION, fetchServerVersion, isStale, nextDelay, type ServerVersion } from "../lib/version";
import "../styles/update-banner.css";

const DISMISS = "finlit-update-dismissed";
const MIN_GAP = 30_000;   // never ask more than twice a minute, however often the tab gains focus
const readDismissed = () => { try { return sessionStorage.getItem(DISMISS); } catch { return null; } };

/** Poll the server version. `check` is injectable for tests. */
export function useServerVersion(fetchFn: () => Promise<ServerVersion | null> = fetchServerVersion, enabled = import.meta.env.PROD): ServerVersion | null {
  const [server, setServer] = useState<ServerVersion | null>(null);
  const last = useRef(0);
  useEffect(() => {
    if (!enabled) return;
    let timer = 0, live = true;
    const run = async (force = false) => {
      if (document.hidden && !force) return;
      const now = Date.now();
      if (now - last.current < MIN_GAP) return;
      last.current = now;
      const v = await fetchFn();
      if (live && v) setServer(v);
    };
    const schedule = () => { window.clearTimeout(timer); timer = window.setTimeout(async () => { await run(); schedule(); }, nextDelay()); };
    const wake = () => { if (!document.hidden) void run(); };
    void run(true); schedule();
    document.addEventListener("visibilitychange", wake); window.addEventListener("focus", wake);
    return () => { live = false; window.clearTimeout(timer); document.removeEventListener("visibilitychange", wake); window.removeEventListener("focus", wake); };
  }, [enabled, fetchFn]);
  return server;
}

export function UpdateBanner({ fetchFn, enabled }: { fetchFn?: () => Promise<ServerVersion | null>; enabled?: boolean } = {}) {
  const server = useServerVersion(fetchFn, enabled);
  const [dismissed, setDismissed] = useState<string | null>(readDismissed);
  const [stuck, setStuck] = useState(false);   // a page file failed to load and the automatic reload was already used
  useEffect(() => { const f = () => setStuck(true); window.addEventListener("finlit:stale-assets", f); return () => window.removeEventListener("finlit:stale-assets", f); }, []);
  const newer = isStale(APP_VERSION, server);
  const key = server?.version ?? "stuck";
  if (!(newer || stuck) || dismissed === key) return null;
  const dismiss = () => { setDismissed(key); try { sessionStorage.setItem(DISMISS, key); } catch { /* private mode: hidden until the next page load */ } };
  return <BannerBar onRefresh={() => location.reload()} onDismiss={dismiss} />;
}

export function BannerBar({ onRefresh, onDismiss }: { onRefresh: () => void; onDismiss: () => void }) {
  return (
    <div className="upd" role="status" aria-live="polite">
      <span className="upd-t">A new version of FinLit is available. Refresh to get it.</span>
      <span className="upd-a">
        <button type="button" className="upd-b upd-go" onClick={onRefresh}>Refresh</button>
        <button type="button" className="upd-b" onClick={onDismiss} aria-label="Dismiss this notice for this version">Dismiss</button>
      </span>
    </div>
  );
}
