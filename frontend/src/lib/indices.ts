import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "./api";

/** Market indices from /api/indices: every NSE and BSE index with today's level and valuation (public),
 *  and each index's daily P/E, P/B and dividend yield for up to five years (Gold). */
export type IndexRow = {
  code: string; name: string; group: "Broad market" | "Sector" | "Strategy & theme" | "Volatility"; exchange: "NSE" | "BSE";
  close: number | null; changePct: number | null; points: number | null; open: number | null; high: number | null; low: number | null;
  pe: number | null; pb: number | null; divYield: number | null; date: string | null;
  /** "dhan": live level, move and range (time = Dhan's last update); "finedge": last close. P/E, P/B and yield are always FinEdge's, of valDate. */
  source?: "dhan" | "finedge"; time?: string | null; valDate?: string | null;
};
export type IndexFeed = { items: IndexRow[]; key: string[]; asOf: string | null; marketOpen: boolean; live?: boolean };
export type Stat = { now: number; median: number; mean: number; sd: number; min: number; max: number; pctile: number; n: number };
export type IndexHistory = {
  code: string; name: string; years: number; from: string | null; to: string | null;
  rows: { d: string; pe: number | null; pb: number | null; dy: number | null }[];
  stats: { pe: Stat | null; pb: Stat | null; dy: Stat | null };
};

/** Refreshed every minute while the page is open; the server keeps a saved copy, so this answers at once. */
export const useIndices = (enabled = true) =>
  useQuery<IndexFeed, ApiError>({ queryKey: ["indices"], queryFn: () => apiGet("/api/indices"), enabled, staleTime: 30_000, refetchInterval: 60_000, retry: 1 });

export const useIndexHistory = (code: string, years: number, enabled = true) =>
  useQuery<IndexHistory, ApiError>({
    queryKey: ["index-history", code, years], queryFn: () => apiGet(`/api/indices/${encodeURIComponent(code)}/valuation?years=${years}`),
    enabled: enabled && !!code, staleTime: 3_600_000, placeholderData: keepPreviousData, retry: (n, e) => e.status >= 500 && n < 1,
  });
