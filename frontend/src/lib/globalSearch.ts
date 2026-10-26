// Site-wide search: the pure part (no React), so it is tested without the page.
// Stocks are searched in the browser over the full name list (/api/stocks/search-index) and joined to /api/search/quotes for price, day
// change, score and logo. Funds, ETFs and news come from their own server searches; this file only shapes and orders what they return.
import { companyRank } from "./companySearch";
import type { SearchRow } from "./api";

export type Kind = "stock" | "mf" | "etf" | "news";
export type Tab = "all" | "stocks" | "mf" | "etf" | "news" | "global";
export const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "All" }, { key: "stocks", label: "Stocks" }, { key: "mf", label: "Mutual funds" }, { key: "etf", label: "ETFs" }, { key: "news", label: "News" }, { key: "global", label: "Global" },
];
export type Band = "strong" | "healthy" | "mixed" | "watch" | "insufficient" | "locked" | null;
/** One row of /api/search/quotes. */
export type QuoteRow = [symbol: string, price: number | null, changePct: number | null, priceDate: string | null, score: number | null, band: Band, logo: string | null];
export type Quotes = { fields: string[]; rows: QuoteRow[]; amcLogos: Record<string, string>; level: string; builtAt: number };
export type Quote = { price: number | null; chg: number | null; date: string | null; score: number | null; band: Band; logo: string | null };

export type Item = {
  kind: Kind; key: string; title: string; sub: string; href: string; external?: boolean;
  price?: number | null; chg?: number | null; date?: string | null; score?: number | null; band?: Band; logo?: string | null;
  tag?: string; ready?: boolean; mine?: boolean; meta?: string;
  metrics?: { label: string; value: number | null }[];        // funds and ETFs: the returns the row and the preview show
};
export type Section = { id: string; title: string; items: Item[]; more?: { tab: Tab; label: string } };

export const BAND_LABEL: Record<string, string> = { strong: "Strong", healthy: "Healthy", mixed: "Mixed", watch: "Watch", insufficient: "Not scored", locked: "Silver" };
export const KIND_LABEL: Record<Kind, string> = { stock: "Stock", mf: "Fund", etf: "ETF", news: "News" };

export function quoteMap(q: Quotes | undefined): Map<string, Quote> {
  const m = new Map<string, Quote>();
  for (const r of q?.rows || []) m.set(r[0], { price: r[1], chg: r[2], date: r[3], score: r[4], band: r[5], logo: r[6] });
  return m;
}

/** Fund house as a key, the same way the server's mf.amc_key does: letters and digits only, "mutual fund" dropped. */
export const amcKey = (name: string) => {
  const s = name.normalize("NFKD").toLowerCase().replace(/mutual\s*fund/g, "").replace(/[^a-z0-9]+/g, "");
  return s || name.toLowerCase().replace(/[^a-z0-9]+/g, "");
};
/** Logo path of a fund house: the longest known key the name starts with ("Nippon India Mutual Fund" -> nipponindia). */
export function amcLogo(name: string | null | undefined, logos: Record<string, string> | undefined): string | null {
  if (!name || !logos) return null;
  const k = amcKey(name);
  let best: string | null = null;
  for (const key of Object.keys(logos)) if ((k.startsWith(key) || (key.length >= 4 && k.includes(key))) && (!best || key.length > best.length)) best = key;
  return best ? logos[best] : null;
}

export function stockItem(r: SearchRow, q: Map<string, Quote>, mine?: Set<string>): Item {
  const x = q.get(r[0]);
  return { kind: "stock", key: "stock:" + r[0], title: r[1], sub: r[0], href: `/stocks/${encodeURIComponent(r[0])}`, price: x?.price ?? null, chg: x?.chg ?? null,
    date: x?.date ?? null, score: x?.score ?? null, band: x?.band ?? null, logo: x?.logo ?? null, tag: "Stock", ready: !!r[3], mine: mine?.has(r[0]) };
}

/** Stocks for a query, best first: the shared typo-tolerant rank, then companies the visitor follows, then size (the index order). `keep` limits it to the rows (by index position) that pass a filter. */
export function searchStocks(rows: readonly SearchRow[] | undefined, query: string, limit: number, mine: Set<string> = new Set(), keep?: (i: number) => boolean): { row: SearchRow; rank: number }[] {
  if (!rows?.length || !query.trim()) return [];
  const qs = query.trim().toUpperCase();
  const out: { row: SearchRow; rank: number; i: number }[] = [];
  rows.forEach((r, i) => {
    if (!r[0] || r[0].startsWith("^") || (keep && !keep(i))) return;
    let rank = companyRank(query, r[0], r[1]);
    if (rank > 800 && rank < 900) rank = 899;                                // any symbol prefix: the larger company (index order) goes first
    if (r[2] && r[2] === qs) rank = Math.max(rank, 950);                    // BSE code
    if (r[4] && r[4].toUpperCase().startsWith(qs)) rank = Math.max(rank, 880);   // NSE code when it differs
    if (rank > 0) out.push({ row: r, rank: rank + (mine.has(r[0]) ? 5 : 0), i });
  });
  out.sort((a, b) => b.rank - a.rank || a.i - b.i);
  return out.slice(0, limit).map(({ row, rank }) => ({ row, rank }));
}

/** Largest companies (index order) that moved most today, up and down: the empty search box's "moving today" list. */
export function moversToday(rows: readonly SearchRow[] | undefined, q: Map<string, Quote>, today: string, n = 6, pool = 200): SearchRow[] {
  const top = (rows || []).slice(0, pool).filter((r) => { const x = q.get(r[0]); return x?.chg != null && x.date === today; });
  const by = (r: SearchRow) => q.get(r[0])!.chg as number;
  const up = [...top].sort((a, b) => by(b) - by(a)).filter((r) => by(r) > 0).slice(0, Math.ceil(n / 2));
  const down = [...top].sort((a, b) => by(a) - by(b)).filter((r) => by(r) < 0).slice(0, Math.floor(n / 2));
  return [...up, ...down];
}

/** The text split into plain and matched parts, for <mark>. Matches each query word at a word start first, else anywhere. */
export function highlight(text: string, query: string): { t: string; hit: boolean }[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter((w) => w.length >= 1).sort((a, b) => b.length - a.length);
  if (!words.length || !text) return [{ t: text, hit: false }];
  const low = text.toLowerCase(), marks = new Array<boolean>(text.length).fill(false);
  for (const w of words) {
    let at = -1;
    for (let i = low.indexOf(w); i >= 0; i = low.indexOf(w, i + 1)) { if (i === 0 || !/[a-z0-9]/.test(low[i - 1])) { at = i; break; } if (at < 0) at = i; }
    if (at >= 0) for (let k = at; k < at + w.length; k++) marks[k] = true;
  }
  const out: { t: string; hit: boolean }[] = [];
  for (let i = 0; i < text.length; i++) {
    const last = out[out.length - 1];
    if (last && last.hit === marks[i]) last.t += text[i]; else out.push({ t: text[i], hit: marks[i] });
  }
  return out;
}

/** Sections for the All tab with a query: one best match on top when a stock is a clear hit, then each kind, capped. */
export function allSections(stocks: Item[], best: Item | null, funds: Item[], etfs: Item[], news: Item[]): Section[] {
  const rest = best ? stocks.filter((s) => s.key !== best.key) : stocks;
  const out: Section[] = [];
  if (best) out.push({ id: "best", title: "Best match", items: [best] });
  if (rest.length) out.push({ id: "stocks", title: "Stocks", items: rest.slice(0, 5), more: { tab: "stocks", label: "All stock matches" } });
  if (funds.length) out.push({ id: "mf", title: "Mutual funds", items: funds.slice(0, 3), more: { tab: "mf", label: "All fund matches" } });
  if (etfs.length) out.push({ id: "etf", title: "ETFs", items: etfs.slice(0, 3), more: { tab: "etf", label: "All ETF matches" } });
  if (news.length) out.push({ id: "news", title: "News", items: news.slice(0, 3), more: { tab: "news", label: "All news" } });
  return out;
}

/** Every selectable row in display order (the keyboard moves through this one list across sections). */
export const flat = (sections: Section[]): Item[] => sections.flatMap((s) => s.items);

/** Today in India as YYYY-MM-DD (prices carry their own date; an older close is labelled, never shown as today's move). */
export const todayIST = (now = new Date()) => new Date(now.getTime() + 5.5 * 3_600_000).toISOString().slice(0, 10);
