import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./api";

export type FeedItem = { id: number; kind: "news" | "result" | "document"; title: string; symbol: string | null; company: string | null; source: string | null; link: string | null; date: string; category: string | null; period: string | null; summary: string | null; auto: boolean };
export const useFeed = (kind: FeedItem["kind"], opts: { scoped?: boolean; symbols?: string[]; q?: string; limit?: number; fresh?: boolean; from?: string; to?: string; upcoming?: boolean; manual?: boolean; before?: string } = {}) => {
  const sym = (opts.symbols || []).slice(0, 60).join(","), none = !!opts.scoped && !sym;   // "only my watchlist" with an empty watchlist is no companies, not all of them
  return useQuery({
    queryKey: ["feed", kind, none ? "(none)" : sym, opts.q || "", opts.limit || 100, !!opts.fresh, opts.from || "", opts.to || "", !!opts.upcoming, !!opts.manual, opts.before || ""], staleTime: 60_000, retry: 1,
    queryFn: () => none ? Promise.resolve<FeedItem[]>([]) : apiGet<{ items: FeedItem[] }>(`/api/feed?kind=${kind}&limit=${opts.limit || 100}${sym ? `&symbol=${encodeURIComponent(sym)}` : ""}${opts.q ? `&q=${encodeURIComponent(opts.q)}` : ""}${opts.from && opts.to ? `&from_date=${opts.from}&to_date=${opts.to}` : ""}${opts.upcoming ? "&upcoming=true" : ""}${opts.manual ? "&manual=true" : ""}${opts.before ? `&before=${opts.before}` : ""}`, opts.fresh ? { cache: "reload" } : undefined).then((d) => d.items),
  });
};
export const dayLabel = (iso: string) => {
  const d = new Date(iso + "T00:00:00"), t = new Date(new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }) + "T00:00:00");   // "today" is the Indian market day, whatever the browser clock says
  const diff = Math.round((d.getTime() - t.getTime()) / 86_400_000);
  const base = d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: d.getFullYear() === t.getFullYear() ? undefined : "numeric" });
  return diff === 0 ? `Today · ${base}` : diff === 1 ? `Tomorrow · ${base}` : diff === -1 ? `Yesterday · ${base}` : base;
};
export const docType = (i: FeedItem): string => {
  const s = `${i.category || ""} ${i.title}`.toLowerCase();
  return /annual report|integrated report/.test(s) ? "Annual report" : /presentation|investor|analyst/.test(s) ? "Investor presentation" : /transcript|concall|earnings call/.test(s) ? "Call transcript" : /prospectus|offer document|rhp|drhp/.test(s) ? "Offer document" : /result/.test(s) ? "Results filing" : "Other filing";
};

/** What to call a feed row: the ticker, except for BSE-only companies whose "ticker" is a number such as 539984; then the name. */
export const who = (x: { symbol?: string | null; company?: string | null }) => (x.symbol && !/^\d+$/.test(x.symbol) ? x.symbol : x.company || x.symbol || "");

/** What GET /api/results/status says: when each results job last ran and the newest result held. */
export type RunInfo = { at?: string; status?: string; counts?: Record<string, number>; newestResultDate?: string | null; error?: string } | null;
export type ResultsStatus = { todayIST: string; newestResultInDb: string | null; newestFilingInDb: string | null; upcomingCount: number; lastRun: { calendars: RunInfo; results: RunInfo; resultsLight: RunInfo } };
export const useResultsStatus = () => useQuery({ queryKey: ["results-status"], staleTime: 60_000, retry: 0, queryFn: () => apiGet<ResultsStatus>("/api/results/status") });

const dayNum = (iso: string) => Math.round(new Date(iso + "T00:00:00Z").getTime() / 86_400_000);
/** Results seasons in India: the weeks after each quarter closes (15 Jan to 14 Feb, 15 Apr to 31 May, 15 Jul to 14 Aug, 15 Oct to 14 Nov). */
export const inResultsSeason = (iso: string) => { const m = +iso.slice(5, 7), d = +iso.slice(8, 10); return (m === 1 && d >= 15) || (m === 2 && d <= 14) || (m === 4 && d >= 15) || m === 5 || (m === 7 && d >= 15) || (m === 8 && d <= 14) || (m === 10 && d >= 15) || (m === 11 && d <= 14); };
/** A neutral note when, on a weekday in results season, the newest result held is more than 2 days old; else null. */
export const staleResultsNote = (s?: Pick<ResultsStatus, "todayIST" | "newestResultInDb"> | null): string | null => {
  if (!s || !s.todayIST) return null;
  const dow = new Date(s.todayIST + "T00:00:00Z").getUTCDay();
  if (dow === 0 || dow === 6 || !inResultsSeason(s.todayIST)) return null;
  if (s.newestResultInDb && dayNum(s.todayIST) - dayNum(s.newestResultInDb) <= 2) return null;
  const since = s.newestResultInDb ? new Date(s.newestResultInDb + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : null;
  return since ? `The latest results have not been refreshed since ${since}. We are checking again every hour.` : "No results are held yet. We are checking again every hour.";
};
