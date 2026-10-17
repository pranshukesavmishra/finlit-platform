// Saved screener filters. Kept in this browser and mirrored to the account when signed in (see lib/sync.tsx).
import { useSyncExternalStore } from "react";
import type { State } from "./screener";

export type SavedScreen = { name: string; state: State };
const KEY = "finlit-saved-screens";
function read(): SavedScreen[] { try { const v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v : []; } catch { return []; } }

let list: SavedScreen[] = typeof localStorage === "undefined" ? [] : read();
const subs = new Set<() => void>();
let onSave: ((s: SavedScreen[]) => void) | null = null;
const commit = (next: SavedScreen[], remote = false) => {
  list = next;
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch { /* private mode */ }
  subs.forEach((f) => f());
  if (!remote) onSave?.(list);
};

export const screens = {
  get: () => list,
  subscribe: (f: () => void) => { subs.add(f); return () => subs.delete(f); },
  save: (name: string, state: State, max: number) => commit([{ name, state }, ...list.filter((s) => s.name !== name)].slice(0, max)),
  remove: (name: string) => commit(list.filter((s) => s.name !== name)),
  replace: (next: SavedScreen[]) => commit(next, true),
  onSave: (f: ((s: SavedScreen[]) => void) | null) => { onSave = f; },
};
export const useSavedScreens = () => useSyncExternalStore(screens.subscribe, screens.get, screens.get);
