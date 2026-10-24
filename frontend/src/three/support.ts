// Decides whether a visitor gets the WebGL scenes. Everyone else keeps the flat page, which is complete on its own.
let cached: boolean | undefined;

export function supports3d(minWidth = 600): boolean {
  if (typeof window === "undefined" || window.innerWidth < minWidth) return false;
  const nav = navigator as Navigator & { deviceMemory?: number; connection?: { saveData?: boolean } };
  if (nav.connection?.saveData) return false;                              // the visitor asked for less data
  if ((nav.hardwareConcurrency ?? 8) < 4 || (nav.deviceMemory ?? 8) < 4) return false;   // weak device: keep it light
  if (cached === undefined) {
    try { const c = document.createElement("canvas"); cached = !!c.getContext("webgl2"); } catch { cached = false; }
  }
  return cached;
}

/** A scene failed to start on this browser: offer no more 3D for the rest of the visit. */
export function markNo3d(): void { cached = false; }

/** Run `fn` once the browser is idle, so the 3D code never competes with the first paint. */
export function whenIdle(fn: () => void): () => void {
  const w = window as Window & { requestIdleCallback?: (f: () => void, o?: { timeout: number }) => number; cancelIdleCallback?: (n: number) => void };
  if (w.requestIdleCallback) { const id = w.requestIdleCallback(fn, { timeout: 2500 }); return () => w.cancelIdleCallback?.(id); }
  const id = window.setTimeout(fn, 900); return () => clearTimeout(id);
}
