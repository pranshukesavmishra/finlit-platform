// Dashboard markets block: the pure logic (treemap layout, sector categories, which stocks belong to a pill) and the data hooks.
// Index levels and moves come from /api/indices (the provider's own feed); the stocks inside an index come from the exchange's published constituent
// lists (/api/markets/members) and, where a list is not loaded, from FinLit's own sector classification, which the page says in words.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "./api";
import type { IndexRow } from "./indices";
import type { Row } from "./screener";

export type Rect = { x: number; y: number; w: number; h: number };
export type Tile<T> = Rect & { item: T };

/** Squarified treemap (Bruls, Huizing, van Wijk): tiles of area proportional to `value`, as square as the layout allows. Items with no positive value are left out. */
export function treemap<T>(items: readonly T[], value: (t: T) => number, w: number, h: number): Tile<T>[] {
  const list = items.map((item) => ({ item, v: value(item) })).filter((x) => x.v > 0 && Number.isFinite(x.v)).sort((a, b) => b.v - a.v);
  const total = list.reduce((s, x) => s + x.v, 0);
  if (!list.length || w <= 0 || h <= 0) return [];
  const scale = (w * h) / total, nodes = list.map((x) => ({ item: x.item, a: x.v * scale }));
  const out: Tile<T>[] = [];
  let x0 = 0, y0 = 0, rw = w, rh = h, i = 0;
  const worst = (row: { a: number }[], side: number) => {
    const s = row.reduce((t, r) => t + r.a, 0), mx = Math.max(...row.map((r) => r.a)), mn = Math.min(...row.map((r) => r.a));
    return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn));
  };
  while (i < nodes.length) {
    const side = Math.min(rw, rh), row = [nodes[i]];
    let j = i + 1;
    while (j < nodes.length && worst([...row, nodes[j]], side) <= worst(row, side)) row.push(nodes[j++]);
    const s = row.reduce((t, r) => t + r.a, 0);
    if (rw >= rh) {                                   // a column down the left edge
      const cw = s / rh; let y = y0;
      for (const r of row) { const ch = r.a / cw; out.push({ x: x0, y, w: cw, h: ch, item: r.item }); y += ch; }
      x0 += cw; rw -= cw;
    } else {                                          // a row along the top edge
      const ch = s / rw; let x = x0;
      for (const r of row) { const cw = r.a / ch; out.push({ x, y: y0, w: cw, h: ch, item: r.item }); x += cw; }
      y0 += ch; rh -= ch;
    }
    i = j;
  }
  return out;
}

/** Tile colour for a day's move: solid, strong green or red (as the reference), deepening up to a 3% move; grey when flat or unknown. */
export function moveColour(c: number | null | undefined): string {
  if (c == null || Math.abs(c) < 0.005) return "var(--s3)";
  const k = Math.round(52 + Math.min(Math.abs(c), 3) / 3 * 38);
  return `color-mix(in srgb, ${c > 0 ? "var(--gain)" : "var(--loss)"} ${k}%, var(--s1))`;
}

// ---------------------------------------------------------------------------------------------------------------- sector categories
/** One sector pill: the provider's index (matched by name) for its level and move, the exchange list (member code) for its stocks, and a
 *  fallback test on FinLit's sector text for when the list is not loaded. */
export type Pill = { id: string; label: string; index: RegExp; members?: string; sector?: RegExp };
export type Category = { id: string; label: string; pills: Pill[] };

export const CATEGORIES: Category[] = [
  { id: "bank", label: "Banking & Financials", pills: [
    { id: "bank", label: "Nifty Bank", index: /^nifty bank$/i, members: "NIFTYBANK", sector: /bank/i },
    { id: "fin", label: "Nifty Fin Service", index: /^nifty (financial services|fin(ancial)? ?serv\w*)$/i, members: "NIFTYFINSERVICE", sector: /bank|financ|insurance|nbfc|capital markets/i },
    { id: "psubank", label: "Nifty PSU Bank", index: /^nifty psu bank$/i, members: "NIFTYPSUBANK", sector: /public sector bank|psu bank/i },
    { id: "pvtbank", label: "Nifty Pvt Bank", index: /^nifty (private|pvt) bank$/i, members: "NIFTYPVTBANK", sector: /private bank/i }] },
  { id: "auto", label: "Automobile & Mobility", pills: [{ id: "auto", label: "Nifty Auto", index: /^nifty auto$/i, members: "NIFTYAUTO", sector: /auto|vehicle|tyre|mobility/i }] },
  { id: "energy", label: "Energy, Oil & Gas", pills: [
    { id: "energy", label: "Nifty Energy", index: /^nifty energy$/i, members: "NIFTYENERGY", sector: /energy|power|refiner|oil|gas|petro/i },
    { id: "oilgas", label: "Nifty Oil & Gas", index: /^nifty oil (&|and) gas$/i, members: "NIFTYOILGAS", sector: /oil|gas|refiner|petro/i }] },
  { id: "fmcg", label: "FMCG & Consumer", pills: [
    { id: "fmcg", label: "Nifty FMCG", index: /^nifty fmcg$/i, members: "NIFTYFMCG", sector: /fmcg|consumer|food|beverage|tobacco|household/i },
    { id: "durables", label: "Consumer Durables", index: /^nifty consumer durables$/i, members: "NIFTYCONSUMERDURABLES", sector: /durable|appliance|electronic|jewel|retail/i }] },
  { id: "health", label: "Healthcare & Pharma", pills: [
    { id: "pharma", label: "Nifty Pharma", index: /^nifty pharma$/i, members: "NIFTYPHARMA", sector: /pharma|drug/i },
    { id: "health", label: "Nifty Healthcare", index: /^nifty health ?care( index)?$/i, members: "NIFTYHEALTHCARE", sector: /health|hospital|pharma|diagnostic/i }] },
  { id: "it", label: "IT & Technology", pills: [{ id: "it", label: "Nifty IT", index: /^nifty it$/i, members: "NIFTYIT", sector: /\bit\b|software|technology|computer|internet/i }] },
  { id: "industrial", label: "Industrials & Manufacturing", pills: [
    { id: "infra", label: "Nifty Infra", index: /^nifty infra\w*$/i, members: "NIFTYINFRA", sector: /infra|construction|capital goods|engineering|industrial/i },
    { id: "mfg", label: "India Manufacturing", index: /^nifty india manufacturing$/i, members: "NIFTYMANUFACTURING", sector: /manufactur|capital goods|industrial|engineering/i }] },
  { id: "realty", label: "Realty & Housing", pills: [{ id: "realty", label: "Nifty Realty", index: /^nifty realty$/i, members: "NIFTYREALTY", sector: /realty|real estate|housing|construction/i }] },
  { id: "media", label: "Media & Entertainment", pills: [{ id: "media", label: "Nifty Media", index: /^nifty media$/i, members: "NIFTYMEDIA", sector: /media|entertain|broadcast/i }] },
  { id: "metals", label: "Metals & Commodities", pills: [
    { id: "metal", label: "Nifty Metal", index: /^nifty metal$/i, members: "NIFTYMETAL", sector: /metal|steel|mining|aluminium|copper/i },
    { id: "commodities", label: "Nifty Commodities", index: /^nifty commodities$/i, members: "NIFTYCOMMODITIES", sector: /metal|mining|oil|cement|chemical|commodit/i }] },
];

/** The provider's index row for a pill (by name), if it carries one. */
export const indexFor = (items: readonly IndexRow[] | undefined, p: Pill) => items?.find((r) => p.index.test(r.name.trim())) ?? null;

export type Basis = "exchange list" | "FinLit sector" | "market cap";
export type Stock = Pick<Row, "symbol" | "name" | "sector" | "price" | "change_pct" | "market_cap">;
const trade = (r: Row) => r.price != null && r.price > 0 && r.change_pct != null && (r.market_cap ?? 0) > 0;

/** The stocks a pill shows and how they were chosen: the exchange's constituent list when it is loaded, else companies whose FinLit sector text matches. */
export function stocksFor(pill: Pill, rows: readonly Row[], members: Record<string, string[]> | undefined): { stocks: Row[]; basis: Basis } {
  const list = pill.members ? members?.[pill.members] : undefined;
  if (list && list.length >= 5) {
    const by = new Map(rows.map((r) => [r.symbol, r]));
    return { stocks: list.map((s) => by.get(s)).filter((r): r is Row => !!r && trade(r)), basis: "exchange list" };
  }
  return { stocks: rows.filter((r) => trade(r) && !!pill.sector && pill.sector.test(r.sector || "")), basis: "FinLit sector" };
}

/** The N largest traded companies by market cap: the stand-in for a broad index when its list is not loaded. */
export const largest = (rows: readonly Row[], n: number): Row[] => rows.filter(trade).sort((a, b) => (b.market_cap ?? 0) - (a.market_cap ?? 0)).slice(0, n);

/** Average move weighted by market cap (the way an index moves), or null with nothing to weigh. */
export function weightedMove(stocks: readonly Stock[]): number | null {
  const w = stocks.filter((s) => s.change_pct != null && (s.market_cap ?? 0) > 0);
  const t = w.reduce((a, s) => a + (s.market_cap as number), 0);
  return t > 0 ? w.reduce((a, s) => a + (s.change_pct as number) * (s.market_cap as number), 0) / t : null;
}

/** Broad sectors of the whole market: cap-weighted move and total market cap, largest first (every sector, not just the biggest few). */
export function sectorBoard(rows: readonly Row[]): { sector: string; move: number; cap: number; n: number }[] {
  const by = new Map<string, Row[]>();
  for (const r of rows) if (trade(r) && (r.market_cap ?? 0) >= 100) by.set(r.sector || "Other", [...(by.get(r.sector || "Other") || []), r]);
  return [...by.entries()].map(([sector, rs]) => ({ sector, move: weightedMove(rs) as number, cap: rs.reduce((a, r) => a + (r.market_cap as number), 0), n: rs.length })).sort((a, b) => b.cap - a.cap);
}

export const gainers = <T extends Stock>(s: readonly T[], n: number) => [...s].filter((x) => (x.change_pct ?? 0) > 0).sort((a, b) => (b.change_pct as number) - (a.change_pct as number)).slice(0, n);
export const losers = <T extends Stock>(s: readonly T[], n: number) => [...s].filter((x) => (x.change_pct ?? 0) < 0).sort((a, b) => (a.change_pct as number) - (b.change_pct as number)).slice(0, n);

// ---------------------------------------------------------------------------------------------------------------- data
export type Members = { indices: Record<string, string[]>; asOf: string | null };
export const useMembers = () => useQuery<Members, ApiError>({ queryKey: ["markets-members"], queryFn: () => apiGet<Members>("/api/markets/members"), staleTime: 3_600_000, retry: 1 });

export type Levels = { code: string; name: string; years: number; rows: { d: string; c: number }[]; from: string | null; to: string | null };
export const useLevels = (code: string, years: number, enabled = true) =>
  useQuery<Levels, ApiError>({ queryKey: ["index-levels", code, years], queryFn: () => apiGet<Levels>(`/api/indices/${encodeURIComponent(code)}/history?years=${years}`),
    enabled: enabled && !!code, staleTime: 600_000, placeholderData: keepPreviousData, retry: (n, e) => e.status >= 500 && n < 1 });

export const RANGES = [["1M", 21], ["3M", 63], ["6M", 126], ["1Y", 252], ["5Y", 0]] as const;
/** The last n sessions of a daily series (0 = all). */
export const lastN = <T,>(rows: readonly T[], n: number): T[] => (n > 0 ? rows.slice(-n) : [...rows]);
