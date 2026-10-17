// Appearance and dashboard layout. Kept in this browser for everyone and mirrored to the account when signed in,
// so the same choices follow a member to a new device (and later to the mobile app).
import { useSyncExternalStore } from "react";
import { isPalette, type PaletteId } from "./palettes";

export type Density = "comfortable" | "compact";
export type WidgetSize = "half" | "full";
export type WidgetPref = { id: string; on: boolean; size: WidgetSize };
export type Prefs = { palette: PaletteId; density: Density; dashboard: WidgetPref[] };

/** Everything the dashboard can show. `min` is the plan a widget needs (its data is gated on the server too). */
export const WIDGETS: { id: string; label: string; blurb: string; min: "basic" | "bronze" | "gold"; size: WidgetSize }[] = [
  { id: "snapshot", label: "Market snapshot", blurb: "Broad market and index moves at a glance.", min: "basic", size: "full" },
  { id: "movers", label: "Watchlist movers", blurb: "Biggest moves among the stocks you follow.", min: "bronze", size: "half" },
  { id: "results", label: "Latest quarter results", blurb: "Newest quarter for your stocks: year-on-year and quarter-on-quarter.", min: "basic", size: "full" },
  { id: "second", label: "Worth a second look", blurb: "Strong FinLit scores trading below their usual valuation.", min: "bronze", size: "half" },
  { id: "screens", label: "My saved screens", blurb: "Open a saved screen and see how many companies match today.", min: "basic", size: "half" },
  { id: "buckets", label: "Watchlist by band", blurb: "How your watchlist splits across FinLit score bands.", min: "gold", size: "half" },
  { id: "learn", label: "Term of the day", blurb: "One plain-words finance term, every day.", min: "basic", size: "half" },
];
const DEFAULTS: Prefs = { palette: "gold", density: "comfortable", dashboard: WIDGETS.map((w) => ({ id: w.id, on: true, size: w.size })) };

const KEY = "finlit-prefs-v1";
function normalise(raw: Partial<Prefs> | null | undefined): Prefs {
  const known = new Map(WIDGETS.map((w) => [w.id, w]));
  const seen = new Set<string>();
  const dash: WidgetPref[] = [];
  for (const w of raw?.dashboard ?? []) if (known.has(w.id) && !seen.has(w.id)) { seen.add(w.id); dash.push({ id: w.id, on: !!w.on, size: w.size === "full" ? "full" : "half" }); }
  for (const w of WIDGETS) if (!seen.has(w.id)) dash.push({ id: w.id, on: true, size: w.size }); // new widgets appear for existing members
  return { palette: isPalette(raw?.palette) ? raw!.palette! : "gold", density: raw?.density === "compact" ? "compact" : "comfortable", dashboard: dash };
}
function read(): Prefs { try { return normalise(JSON.parse(localStorage.getItem(KEY) || "null")); } catch { return normalise(null); } }

let state = typeof localStorage === "undefined" ? DEFAULTS : read();
const subs = new Set<() => void>();
type Listener = (p: Prefs) => void;
let onChange: Listener | null = null;

export const prefs = {
  get: () => state,
  subscribe: (f: () => void) => { subs.add(f); return () => subs.delete(f); },
  /** The account layer registers here to save changes. */
  onSave: (f: Listener | null) => { onChange = f; },
  set(patch: Partial<Prefs>, fromServer = false) {
    state = normalise({ ...state, ...patch });
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* private mode */ }
    subs.forEach((f) => f());
    if (!fromServer) onChange?.(state);
  },
  reset: () => prefs.set({ ...DEFAULTS, dashboard: normalise(null).dashboard }),
};
export const usePrefs = () => useSyncExternalStore(prefs.subscribe, prefs.get, prefs.get);
