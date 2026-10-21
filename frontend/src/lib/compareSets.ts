// Custom comparison: the default measures, shareable link, saved sets (this browser, mirrored to the account when the plan allows),
// and which company is best or worst on a measure.
import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { apiGet, apiSend } from "./api";
import { DEMO } from "./demo";
import { useAuth } from "./auth";
import { RANK } from "./ui";

export type SavedSet = { name: string; keys: string[] };
export const MAX_PICK = 60;          // most measures on screen at once
export const MAX_PICK_PHONE = 24;    // narrow screens: the table stays readable
export const NAME_MAX = 40;
export const KEY_RE = /^[a-z0-9_]{2,40}$/;

/** Shown first; whatever the plan locks is left out. */
export const DEFAULT_KEYS = ["market_cap", "price", "pe", "pb", "roe", "roce", "operating_margin", "debt_to_equity", "sales_cagr_5y", "profit_cagr_5y", "dividend_yield", "ret_1y"];

/** Starter sets everyone can load; the user's own are kept apart. */
export const STARTERS: SavedSet[] = [
  { name: "Value", keys: ["pe", "pb", "ev_ebitda", "ev_cfo", "pfcf", "dividend_yield", "earnings_yield", "peg"] },
  { name: "Quality", keys: ["roe", "roce", "operating_margin", "net_margin", "interest_coverage", "debt_to_equity", "cfo_to_pat"] },
  { name: "Growth", keys: ["sales_cagr_5y", "profit_cagr_5y", "eps_cagr_5y", "sales_growth", "profit_growth", "q_sales_yoy", "q_profit_yoy"] },
  { name: "Balance sheet", keys: ["debt_to_equity", "net_debt", "net_debt_to_ebitda", "current_ratio", "interest_coverage", "cash_to_debt"] },
];

export const cleanKeys = (raw: string[], known?: (k: string) => boolean, max = MAX_PICK): string[] => {
  const out: string[] = [];
  for (const k of raw) if (KEY_RE.test(k) && !out.includes(k) && (!known || known(k))) out.push(k);
  return out.slice(0, max);
};

/** The `m=` part of the link: measure keys, comma separated. */
export const encodeKeys = (keys: string[]): string => cleanKeys(keys, undefined, 200).join(",");
export const decodeKeys = (raw: string | null, known?: (k: string) => boolean): string[] => (raw ? cleanKeys(raw.split(","), known) : []);

// ------------------------------------------------------------------ best and worst, aware of direction
export type Mark = { best: string[]; worst: string[] };
/** `better` is the catalogue's direction. Needs two or more known values that are not all equal; "none" never marks anything. Ties share the mark. */
export function bestWorst(values: Record<string, number | null | undefined>, better: "higher" | "lower" | "none"): Mark {
  const empty: Mark = { best: [], worst: [] };
  if (better === "none") return empty;
  const known = Object.entries(values).filter((e): e is [string, number] => typeof e[1] === "number" && Number.isFinite(e[1]));
  if (known.length < 2) return empty;
  const hi = Math.max(...known.map((e) => e[1])), lo = Math.min(...known.map((e) => e[1]));
  if (hi === lo) return empty;
  const at = (x: number) => known.filter((e) => e[1] === x).map((e) => e[0]);
  return better === "higher" ? { best: at(hi), worst: at(lo) } : { best: at(lo), worst: at(hi) };
}

// ------------------------------------------------------------------ saved sets
const KEY = "finlit-compare-sets";
function read(): SavedSet[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(v) ? v.filter((s) => s && typeof s.name === "string" && Array.isArray(s.keys)).map((s) => ({ name: String(s.name).slice(0, NAME_MAX), keys: cleanKeys(s.keys.map(String), undefined, 200) })).filter((s) => s.name && s.keys.length) : [];
  } catch { return []; }
}
let list: SavedSet[] = typeof localStorage === "undefined" ? [] : read();
const subs = new Set<() => void>();
const commit = (next: SavedSet[]) => {
  list = next;
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch { /* private mode: the sets last for this visit only */ }
  subs.forEach((f) => f());
};
const sameName = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();

export const sets = {
  get: () => list,
  subscribe: (f: () => void) => { subs.add(f); return () => { subs.delete(f); }; },
  save: (name: string, keys: string[], max = 30): SavedSet[] => { const n = name.trim().slice(0, NAME_MAX); if (!n || !keys.length) return list; commit([{ name: n, keys: cleanKeys(keys, undefined, 200) }, ...list.filter((s) => !sameName(s.name, n))].slice(0, max)); return list; },
  remove: (name: string) => commit(list.filter((s) => !sameName(s.name, name))),
  replace: (next: SavedSet[]) => commit(next),
  /** Server copy first, then any local-only sets, up to the limit. */
  merge: (remote: SavedSet[], max: number): SavedSet[] => [...remote, ...list.filter((l) => !remote.some((r) => sameName(r.name, l.name)))].slice(0, max),
};

export const useSavedSets = () => useSyncExternalStore(sets.subscribe, sets.get, sets.get);

/** Plan allowance for keeping sets in the account (the server enforces the same). */
export const ACCOUNT_SETS: Record<string, number> = { basic: 0, silver: 10, gold: 30 };

/** Mirrors the sets to the account when signed in on Silver or Gold; Basic and visitors keep them in this browser. Returns `save` and `remove`. */
export function useSetsSync() {
  const { user, plan } = useAuth();
  const uid = user?.id ?? null, allow = ACCOUNT_SETS[plan] ?? 0;
  const ready = useRef(false);
  useEffect(() => {
    ready.current = false;
    if (DEMO || !uid || !allow || RANK[plan] < RANK.silver) return;
    let off = false;
    apiGet<{ sets: SavedSet[] }>("/api/compare/sets").then((r) => {
      if (off) return;
      const merged = sets.merge(r.sets || [], allow);
      sets.replace(merged);
      ready.current = true;
      if (JSON.stringify(merged) !== JSON.stringify(r.sets || [])) apiSend("PUT", "/api/compare/sets", { sets: merged }).catch(() => undefined);
    }).catch(() => undefined);
    return () => { off = true; };
  }, [uid, allow, plan]);
  const push = useCallback(() => { if (!DEMO && uid && allow && ready.current) apiSend("PUT", "/api/compare/sets", { sets: sets.get() }).catch(() => undefined); }, [uid, allow]);
  return {
    save: (name: string, keys: string[]) => { sets.save(name, keys, allow || 30); push(); },
    remove: (name: string) => { sets.remove(name); push(); },
    where: allow ? "your account and this browser" : "this browser",
  };
}
