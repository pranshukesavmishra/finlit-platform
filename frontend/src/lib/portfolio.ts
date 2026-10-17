// Holdings live in this browser and, for signed-in Bronze and Gold members, in their account (see lib/sync.tsx).
import { useSyncExternalStore } from "react";

export type Holding = { id: string; symbol: string; qty: number; price: number; date?: string; note?: string };
export type PState = { holdings: Holding[] };
const KEY = "finlit-portfolio-v1";
const fresh = (): PState => ({ holdings: [] });
function read(): PState {
  try { const s = JSON.parse(localStorage.getItem(KEY) || "null") as PState | null; return s && Array.isArray(s.holdings) ? s : fresh(); } catch { return fresh(); }
}
let state: PState = typeof localStorage === "undefined" ? fresh() : read();
const subs = new Set<() => void>();
let onSave: ((s: PState) => void) | null = null;
const emit = (remote = false) => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* private mode */ } subs.forEach((f) => f()); if (!remote) onSave?.(state); };
const uid = () => Math.random().toString(36).slice(2, 10);

export const portfolio = {
  get: () => state,
  subscribe: (f: () => void) => { subs.add(f); return () => subs.delete(f); },
  onSave: (f: ((s: PState) => void) | null) => { onSave = f; },
  replace: (s: PState) => { state = s?.holdings ? s : fresh(); emit(true); },
  reset: () => { state = fresh(); emit(true); },
  add: (h: Omit<Holding, "id">) => { state = { holdings: [...state.holdings, { ...h, symbol: h.symbol.toUpperCase(), id: uid() }] }; emit(); },
  update: (id: string, h: Partial<Holding>) => { state = { holdings: state.holdings.map((x) => (x.id === id ? { ...x, ...h } : x)) }; emit(); },
  remove: (id: string) => { state = { holdings: state.holdings.filter((x) => x.id !== id) }; emit(); },
  addMany: (hs: Omit<Holding, "id">[]) => { state = { holdings: [...state.holdings, ...hs.map((h) => ({ ...h, symbol: h.symbol.toUpperCase(), id: uid() }))] }; emit(); },
};
export const usePortfolio = () => useSyncExternalStore(portfolio.subscribe, portfolio.get, portfolio.get);

/** Parse pasted or uploaded text: symbol, quantity, average buy price and an optional date (YYYY-MM-DD), comma or tab separated. */
export function parseHoldings(text: string): { rows: Omit<Holding, "id">[]; skipped: number } {
  const rows: Omit<Holding, "id">[] = []; let skipped = 0;
  for (const line of text.split(/\r?\n/)) {
    const p = line.split(/[,\t;]/).map((x) => x.trim().replace(/^"|"$/g, ""));
    if (p.length < 3 || /^symbol$/i.test(p[0]) || !p[0]) { if (p[0] && !/^symbol$/i.test(p[0])) skipped++; continue; }
    const qty = Number(p[1].replace(/,/g, "")), price = Number(p[2].replace(/[,₹]/g, ""));
    if (!/^[A-Za-z0-9&_.-]{1,24}$/.test(p[0]) || !(qty > 0) || !(price >= 0)) { skipped++; continue; }
    rows.push({ symbol: p[0].toUpperCase(), qty, price, ...(p[3] && /^\d{4}-\d{2}-\d{2}$/.test(p[3]) ? { date: p[3] } : {}) });
  }
  return { rows, skipped };
}
