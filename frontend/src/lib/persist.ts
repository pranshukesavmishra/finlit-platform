// One safe door to localStorage for UI state that changes how the page LOOKS or BEHAVES (collapsed panels, chosen columns, widths).
// Values are stored as {v, data}. Anything that is not exactly that shape, has another version, is corrupt JSON, or fails the caller's
// validator is discarded (and removed) and the default is used, so a browser holding values written by an older release never
// meets new code with a layout it does not understand. Nothing here ever throws (private mode, blocked or full storage).
const store = (): Storage | null => { try { return typeof localStorage === "undefined" ? null : localStorage; } catch { return null; } };

/** The key namespace. New keys live under it so they can never be confused with the raw values older releases wrote. */
export const UI_PREFIX = "finlit:ui:";

/** Read a versioned value. Returns `fallback` for missing, corrupt, other-version or invalid data (the bad entry is removed). */
export function loadUi<T>(key: string, version: number, validate: (data: unknown) => T | null, fallback: T): T {
  const s = store();
  if (!s) return fallback;
  try {
    const raw = s.getItem(UI_PREFIX + key);
    if (raw == null) return fallback;
    const parsed = JSON.parse(raw) as { v?: unknown; data?: unknown } | null;
    if (parsed && typeof parsed === "object" && parsed.v === version && "data" in parsed) {
      const ok = validate(parsed.data);
      if (ok !== null) return ok;
    }
    s.removeItem(UI_PREFIX + key);
  } catch { try { s.removeItem(UI_PREFIX + key); } catch { /* ignore */ } }
  return fallback;
}

/** Save a versioned value. Returns false when storage is unavailable (the choice then lasts for this visit only). */
export function saveUi<T>(key: string, version: number, data: T): boolean {
  const s = store();
  if (!s) return false;
  try { s.setItem(UI_PREFIX + key, JSON.stringify({ v: version, data })); return true; } catch { return false; }
}

export function removeUi(key: string): void { try { store()?.removeItem(UI_PREFIX + key); } catch { /* ignore */ } }

// ------------------------------------------------------------------------------------------------ validators
export const isBool = (d: unknown): boolean | null => (typeof d === "boolean" ? d : null);
/** A map of name -> boolean, with anything else dropped; null when it is not an object at all. */
export const isBoolMap = (d: unknown): Record<string, boolean> | null => {
  if (!d || typeof d !== "object" || Array.isArray(d)) return null;
  const out: Record<string, boolean> = {};
  for (const [k, v] of Object.entries(d as Record<string, unknown>)) if (typeof v === "boolean" && k.length <= 80) out[k] = v;
  return out;
};
/** A list of strings that must all be in `allowed`; unknown entries are dropped; null when nothing valid is left. */
export const isIdList = <T extends string>(allowed: ReadonlySet<string>) => (d: unknown): T[] | null => {
  if (!Array.isArray(d)) return null;
  const ok = d.filter((x): x is T => typeof x === "string" && allowed.has(x));
  return ok.length ? ok : null;
};
export const isNumberIn = (min: number, max: number) => (d: unknown): number | null => (typeof d === "number" && Number.isFinite(d) && d >= min && d <= max ? d : null);

// ------------------------------------------------------------------------------------------------ old keys
/** Remove raw (unversioned) keys written by earlier releases, so old code that is still cached cannot misread them and they stop lingering. */
export function purgeLegacy(keys: readonly string[], prefixes: readonly string[] = []): void {
  const s = store();
  if (!s) return;
  try {
    for (const k of keys) s.removeItem(k);
    if (prefixes.length) for (let i = s.length - 1; i >= 0; i--) { const k = s.key(i) || ""; if (prefixes.some((p) => k.startsWith(p))) s.removeItem(k); }
  } catch { /* ignore */ }
}
