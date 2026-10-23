// Keeping pages working across releases and flaky moments.
// A release replaces the website's files under new names. A tab opened before the release still asks for the old names the next time a page is
// opened; the server (rightly) says "not found", and the page used to stop with "Something went wrong". Now a failed page-file load is retried,
// and if it is still missing the tab reloads once to pick up the new release. Real errors are sent to the server log so they can be fixed.
import { lazy, type ComponentType } from "react";

const RELOAD_KEY = "finlit-reload-at";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Did loading a page's own file fail (as opposed to the page's code failing)? The wording differs by browser and bundler. */
export function isChunkError(e: unknown): boolean {
  const m = String((e as { message?: string } | null)?.message ?? e ?? "");
  return /dynamically imported module|importing a module script failed|error loading dynamically imported|failed to fetch dynamically|ChunkLoadError|Loading chunk .* failed|Unable to preload CSS|module script/i.test(m);
}

/** Reload the tab, but at most once every 30 seconds, so a file that is really gone cannot cause a reload loop. Returns false when it declined. */
export function reloadOnce(now = Date.now()): boolean {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_KEY) || 0);
    if (now - last < 30_000) return false;
    sessionStorage.setItem(RELOAD_KEY, String(now));
  } catch { /* storage blocked: reloading once without a guard could loop, so do not */ return false; }
  location.reload();
  return true;
}

/** An import that, when its file is gone, reloads the tab once to pick up the new release (optionally trying again first, after the given waits). */
export function withRetry<T>(factory: () => Promise<T>, waits: number[] = []): () => Promise<T> {   // browsers remember a failed module load, so a plain retry rarely helps: by default go straight to the reload
  return async () => {
    for (let i = 0; ; i++) {
      try { return await factory(); }
      catch (e) {
        if (!isChunkError(e)) throw e;
        if (i < waits.length) { await sleep(waits[i]); continue; }
        if (reloadOnce()) return new Promise<T>(() => { /* the tab is reloading */ });
        throw e;
      }
    }
  };
}

/** React.lazy with the retry above. */
export const lazyPage = <T extends ComponentType<any>>(factory: () => Promise<{ default: T }>) => lazy(withRetry(factory));   // eslint-disable-line @typescript-eslint/no-explicit-any

// ---------------------------------------------------------------------------------------------------------------- reporting
let sent = 0;
const seen = new Set<string>();
const build = () => (document.querySelector<HTMLScriptElement>('script[type="module"][src*="/assets/index-"]')?.src.split("/").pop() || "dev").slice(0, 40);

/** Tell the server about an error the visitor hit: once per distinct message, at most 5 per page load. Never throws. */
export function reportError(e: unknown, kind: "render" | "chunk" | "script" | "promise" = "render"): void {
  try {
    const err = e as { message?: string; stack?: string } | null;
    const message = String(err?.message ?? e ?? "unknown").slice(0, 300);
    if (sent >= 5 || seen.has(message) || import.meta.env.DEV) return;
    seen.add(message); sent++;
    const body = JSON.stringify({ message, stack: String(err?.stack ?? "").split("\n").slice(0, 6).join("\n").slice(0, 900), path: location.pathname.slice(0, 200), kind, build: build() });
    const url = `${import.meta.env.BASE_URL}api/client-errors`.replace(/\/{2,}/g, "/");
    if (!(navigator.sendBeacon && navigator.sendBeacon(url, new Blob([body], { type: "application/json" })))) void fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true }).catch(() => {});
  } catch { /* reporting must never cause an error of its own */ }
}

/** Page-wide safety nets: a failed preload (Vite's own event) reloads once; uncaught errors and rejected promises are reported. */
export function installResilience(): void {
  window.addEventListener("vite:preloadError", (ev) => { ev.preventDefault(); reportError((ev as unknown as { payload?: unknown }).payload ?? "preload failed", "chunk"); reloadOnce(); });
  window.addEventListener("error", (ev) => { if (ev.error) reportError(ev.error, "script"); });
  window.addEventListener("unhandledrejection", (ev) => reportError(ev.reason, isChunkError(ev.reason) ? "chunk" : "promise"));
}
