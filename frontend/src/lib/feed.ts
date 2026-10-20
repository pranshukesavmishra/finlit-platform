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
  const d = new Date(iso + "T00:00:00"), t = new Date(); t.setHours(0, 0, 0, 0);
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
