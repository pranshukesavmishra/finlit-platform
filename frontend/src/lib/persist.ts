// Saved UI state (panel widths, folded sidebar, ...) is versioned: {"v":2,"d":value}. A value written by an older release (a bare "620" or "1"),
// by a newer one, or one that is damaged is thrown away and the default is used, so old saved state can never lay out a new page badly.
export const UI_VERSION = 2;

export function readUi<T>(key: string, ok: (x: unknown) => x is T, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    const o = JSON.parse(raw) as { v?: unknown; d?: unknown } | null;
    if (o && typeof o === "object" && o.v === UI_VERSION && ok(o.d)) return o.d;
    localStorage.removeItem(key);   // unknown version or damaged: forget it
  } catch { try { localStorage.removeItem(key); } catch { /* blocked */ } }
  return fallback;
}

export function writeUi(key: string, d: unknown) {
  try { localStorage.setItem(key, JSON.stringify({ v: UI_VERSION, d })); } catch { /* private mode: not remembered */ }
}

export const isBool = (x: unknown): x is boolean => typeof x === "boolean";
export const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
export const isFlags = (x: unknown): x is Record<string, boolean> => !!x && typeof x === "object" && !Array.isArray(x) && Object.values(x).every((v) => typeof v === "boolean");
