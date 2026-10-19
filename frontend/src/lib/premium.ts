import { useEffect } from "react";
import { keepPreviousData, useQuery, type QueryClient } from "@tanstack/react-query";
import { apiGet, type ApiError } from "./api";
import { useAuth } from "./auth";
import { useUI } from "./ui";

/** Gold-plan market and fundamentals data. The server keeps every answer saved, so repeat views come back in milliseconds. */
export type MarketSection = "ipo" | "results" | "announcements" | "transcripts" | "indices" | "valuations";
export type Feed<T> = { items: T[]; total: number; fetchedAt: string; cached?: boolean; provider: string };

export const useGold = () => { const { isAdmin } = useAuth(); const { has } = useUI(); return isAdmin || has("gold"); };

const call = <T,>(path: string) => apiGet<T>("/api/premium" + path);
const opts = <T,>(path: string, enabled = true) => ({
  queryKey: ["premium", path], queryFn: () => call<T>(path), enabled, staleTime: 120_000, gcTime: 900_000, placeholderData: keepPreviousData,
  retry: (n: number, e: ApiError) => e.status >= 500 && n < 2, retryDelay: 1200,
});

export const usePremium = <T,>(path: string, enabled = true) => useQuery<T, ApiError>(opts<T>(path, enabled));

export const qs = (o: Record<string, string | undefined>) => {
  const p = Object.entries(o).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`).join("&");
  return p ? "?" + p : "";
};

/** Start every tab's default view loading at once, so switching tabs shows data immediately. */
export function prefetchMarkets(qc: QueryClient) {
  for (const s of ["ipo", "results", "announcements", "transcripts", "indices"]) qc.prefetchQuery(opts(`/markets/${s}`));
  qc.prefetchQuery(opts("/commodities?category=monthly_index"));
}

/** Save a table as a CSV file that opens cleanly in Excel (UTF-8 mark, quoted cells). */
export function downloadCsv(name: string, head: string[], rows: (string | number | null | undefined)[][]) {
  const cell = (v: string | number | null | undefined) => { const s = v == null ? "" : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const text = "﻿" + [head, ...rows].map((r) => r.map(cell).join(",")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  a.download = name.replace(/[^\w.-]+/g, "-") + ".csv";
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/** The last few companies a member opened in the Gold tools (this browser only; works without storage too). */
const RECENT = "finlit-premium-recent";
export function readRecent(): string[] {
  try { const v = JSON.parse(localStorage.getItem(RECENT) || "[]"); return Array.isArray(v) ? v.filter((x) => typeof x === "string").slice(0, 6) : []; } catch { return []; }
}
export function pushRecent(symbol: string) {
  try { localStorage.setItem(RECENT, JSON.stringify([symbol, ...readRecent().filter((s) => s !== symbol)].slice(0, 6))); } catch { /* private mode */ }
}

/** Press "/" anywhere on the page to jump to its search box. */
export function useSlashFocus(ref: React.RefObject<HTMLInputElement | null>) {
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.key !== "/" || e.ctrlKey || e.metaKey || (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable))) return;
      e.preventDefault(); ref.current?.focus();
    };
    window.addEventListener("keydown", on); return () => window.removeEventListener("keydown", on);
  }, [ref]);
}
