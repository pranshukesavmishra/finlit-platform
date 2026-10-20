/** "My companies": the ones this person follows (watchlist, portfolio) and has opened. A company outside the always-loaded set takes its few
 *  seconds to build once; after that the server keeps it stored and refreshed for this member, and the browser warms it, so it opens at once.
 *  Signed-in members get the list from the server; the last companies opened in this browser are remembered too (for visitors as well). */
import { useEffect, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, prefetchStock, useSearchIndex, type ApiError } from "./api";
import { useAuth } from "./auth";

export type MyCompany = { symbol: string; name: string | null; ready: boolean; followed: boolean; lastOpened: string | null };
const KEY = "finlit.recents", MAX = 40;

export const recents = {
  get(): string[] { try { const v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v.filter((x) => typeof x === "string").slice(0, MAX) : []; } catch { return []; } },
  add(symbol: string) { try { const s = symbol.toUpperCase(), next = [s, ...recents.get().filter((x) => x !== s)].slice(0, MAX); localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* private mode: not remembered */ } },
};

export function useMyCompanies() {
  const { user } = useAuth();
  const q = useQuery<{ companies: MyCompany[] }, ApiError>({ queryKey: ["my-companies"], queryFn: () => apiGet("/api/me/companies"), enabled: !!user, staleTime: 300_000, retry: false });
  const symbols = useMemo(() => {
    const out: string[] = [];
    for (const s of [...(q.data?.companies || []).map((c) => c.symbol), ...recents.get()]) if (!out.includes(s)) out.push(s);
    return out.slice(0, 60);
  }, [q.data]);
  return { companies: q.data?.companies || [], symbols, isLoading: q.isLoading };
}

/** Quietly warms the first few of my companies once the app is idle, so opening one is instant. Only companies already stored are asked for
 *  (an unprepared one would start a build nobody is waiting for). */
export function useWarmMyCompanies() {
  const qc = useQueryClient();
  const { symbols } = useMyCompanies();
  const idx = useSearchIndex(symbols.length > 0);
  useEffect(() => {
    const ready = new Set((idx.data?.rows || []).filter((r) => r[3]).map((r) => r[0]));
    const todo = symbols.filter((s) => ready.has(s) && !qc.getQueryData(["stock", s, ""])).slice(0, 8);
    if (!todo.length) return;
    const timers = todo.map((s, i) => window.setTimeout(() => prefetchStock(qc, s), 1500 + i * 700));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [symbols.join(","), idx.data]); // eslint-disable-line react-hooks/exhaustive-deps
}
