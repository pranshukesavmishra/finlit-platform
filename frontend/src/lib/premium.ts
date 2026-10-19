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
