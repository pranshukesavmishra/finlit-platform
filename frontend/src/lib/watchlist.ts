// Watchlists live in this browser for now (localStorage). When accounts ship, the same shape syncs to the server so lists follow the user to the app.
import { useSyncExternalStore } from "react";

export type List = { id: string; name: string; symbols: string[] };
export type Meta = { note?: string; target?: number; added: number };
export type WState = { lists: List[]; meta: Record<string, Meta>; seeded?: boolean };

const KEY = "finlit-watchlist-v1";
const fresh = (): WState => ({ lists: [{ id: "main", name: "My watchlist", symbols: [] }], meta: {} });
function read(): WState {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || "null") as WState | null;
    if (s && Array.isArray(s.lists) && s.lists.length) return s;
    const st = fresh();
    // carry over stars from the first version of the stock-page button
    for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i) || ""; if (k.startsWith("finlit-watch-")) st.lists[0].symbols.push(k.slice(13)); }
    return st;
  } catch { return fresh(); }
}
let state = read();
const subs = new Set<() => void>();
const emit = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* private mode */ } subs.forEach((f) => f()); };
const set = (fn: (s: WState) => WState) => { state = fn(state); emit(); };
const uid = () => Math.random().toString(36).slice(2, 8);

export const watch = {
  get: () => state,
  subscribe: (f: () => void) => { subs.add(f); return () => subs.delete(f); },
  has: (sym: string) => state.lists.some((l) => l.symbols.includes(sym)),
  total: () => new Set(state.lists.flatMap((l) => l.symbols)).size,
  add: (sym: string, listId = state.lists[0].id) => set((s) => ({ ...s, lists: s.lists.map((l) => (l.id === listId && !l.symbols.includes(sym) ? { ...l, symbols: [...l.symbols, sym] } : l)), meta: { ...s.meta, [sym]: s.meta[sym] || { added: Date.now() } } })),
  remove: (sym: string, listId?: string) => set((s) => ({ ...s, lists: s.lists.map((l) => (!listId || l.id === listId ? { ...l, symbols: l.symbols.filter((x) => x !== sym) } : l)) })),
  move: (sym: string, from: string, to: string) => set((s) => ({ ...s, lists: s.lists.map((l) => (l.id === from ? { ...l, symbols: l.symbols.filter((x) => x !== sym) } : l.id === to && !l.symbols.includes(sym) ? { ...l, symbols: [...l.symbols, sym] } : l)) })),
  create: (name: string) => { const id = uid(); set((s) => ({ ...s, lists: [...s.lists, { id, name: name.trim().slice(0, 28) || "New list", symbols: [] }] })); return id; },
  rename: (id: string, name: string) => set((s) => ({ ...s, lists: s.lists.map((l) => (l.id === id ? { ...l, name: name.trim().slice(0, 28) || l.name } : l)) })),
  drop: (id: string) => set((s) => (s.lists.length > 1 ? { ...s, lists: s.lists.filter((l) => l.id !== id) } : s)),
  setMeta: (sym: string, m: Partial<Meta>) => set((s) => ({ ...s, meta: { ...s.meta, [sym]: { ...s.meta[sym], ...m, added: s.meta[sym]?.added ?? Date.now() } } })),
  seed: (syms: string[]) => set((s) => ({ ...s, seeded: true, lists: s.lists.map((l, i) => (i === 0 ? { ...l, symbols: [...new Set([...l.symbols, ...syms])] } : l)) })),
};
export const useWatchlist = () => useSyncExternalStore(watch.subscribe, watch.get, watch.get);
