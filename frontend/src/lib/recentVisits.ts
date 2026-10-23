// What this visitor opened lately (stocks, funds, ETFs), newest first, for the empty search box. Kept in this browser only; every read and
// write is guarded, so private mode or blocked storage simply means nothing is remembered. Stocks opened before this existed are read
// from the older list (finlit.recents, symbols only).
import { recents } from "./mycompanies";

export type Visit = { k: "stock" | "mf" | "etf"; id: string; name: string; sub?: string; at: number };
const KEY = "finlit.recent-visits", MAX = 12;
const listeners = new Set<() => void>();

function read(): Visit[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(v) ? v.filter((x) => x && typeof x.id === "string" && typeof x.name === "string" && ["stock", "mf", "etf"].includes(x.k)).slice(0, MAX) : [];
  } catch { return []; }
}

export const visits = {
  /** Newest first. Old stock-only recents fill in (names unknown: the caller looks them up) when there is room. */
  get(): Visit[] {
    const out = read();
    for (const s of recents.get()) {
      if (out.length >= MAX) break;
      if (!out.some((x) => x.k === "stock" && x.id === s)) out.push({ k: "stock", id: s, name: "", at: 0 });
    }
    return out;
  },
  add(v: Omit<Visit, "at">) {
    if (!v.id || !v.name) return;
    try {
      const next = [{ ...v, at: Date.now() }, ...read().filter((x) => !(x.k === v.k && x.id === v.id))].slice(0, MAX);
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch { /* storage unavailable: not remembered */ }
    listeners.forEach((f) => f());
  },
  clear() {
    try { localStorage.removeItem(KEY); localStorage.removeItem("finlit.recents"); } catch { /* nothing stored */ }
    listeners.forEach((f) => f());
  },
  subscribe(f: () => void) { listeners.add(f); return () => { listeners.delete(f); }; },
};
