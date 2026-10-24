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

/** Tile colour for a day's move: a vivid green or red (the same on both themes, so tiles stay bold), deepening from a small move to 2%; slate when flat or unknown.
 *  White text sits on every stop at 3:1 or better. */
const GAIN: [number, number, number][] = [[38, 166, 98], [8, 112, 56]], LOSS: [number, number, number][] = [[226, 84, 76], [168, 26, 30]];
export const FLAT_TILE = "#8B95A5";
export function moveColour(c: number | null | undefined): string {
  if (c == null || Math.abs(c) < 0.005) return FLAT_TILE;
  const t = Math.min(Math.abs(c), 2) / 2, [lo, hi] = c > 0 ? GAIN : LOSS;
  return `rgb(${lo.map((v, i) => Math.round(v + (hi[i] - v) * t)).join(", ")})`;
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
export function stocksFor(pill: Pill, rows: readonly Row[], members: Record<string, string[]> | undefined): { stocks: Row[]; basis: Basis; listed: number; missing: string[] } {
  const list = pill.members ? members?.[pill.members] : undefined;
  if (list && list.length >= 5) {
    const by = new Map(rows.map((r) => [r.symbol, r]));
    const stocks = list.map((s) => by.get(s)).filter((r): r is Row => !!r && trade(r));
    const have = new Set(stocks.map((r) => r.symbol));
    return { stocks, basis: "exchange list", listed: list.length, missing: list.filter((s) => !have.has(s)) };   // a constituent with no price today is named, never silently dropped
  }
  const stocks = rows.filter((r) => trade(r) && !!pill.sector && pill.sector.test(r.sector || ""));
  return { stocks, basis: "FinLit sector", listed: stocks.length, missing: [] };
}

/** The N largest traded companies by market cap: the stand-in for a broad index when its list is not loaded. */
export const largest = (rows: readonly Row[], n: number): Row[] => rows.filter(trade).sort((a, b) => (b.market_cap ?? 0) - (a.market_cap ?? 0)).slice(0, n);

/** Average move weighted by market cap (the way an index moves), or null with nothing to weigh. */
export function weightedMove(stocks: readonly Stock[]): number | null {
  const w = stocks.filter((s) => s.change_pct != null && (s.market_cap ?? 0) > 0);
  const t = w.reduce((a, s) => a + (s.market_cap as number), 0);
  return t > 0 ? w.reduce((a, s) => a + (s.change_pct as number) * (s.market_cap as number), 0) / t : null;
}

/** The ~20 broad sectors the snapshot shows. The classification in the data has hundreds of fine industries ("Private Sector Bank", "Computers - Software"...);
 *  a heat-map of hundreds of slivers says nothing, so each is placed in the first broad sector whose pattern matches it. */
const BROAD: [string, RegExp][] = [
  ["Banks", /\bbank/i],
  ["Financial services", /financ|insurance|nbfc|capital market|broking|asset management|stock exchange|credit|lending|housing finance|investment/i],
  ["IT & software", /software|\bit\b|computers|information tech|internet|data process|e-commerce|digital/i],
  ["Pharma & healthcare", /pharma|drug|health|hospital|diagnostic|medical|biotech|life science/i],
  ["Automobiles", /auto|vehicle|tyre|two wheel|tractor|motor/i],
  ["Oil, gas & energy", /oil|gas|refiner|petro|coal|energy|fuel|lubricant/i],
  ["Power & utilities", /power|utilit|electricity|water|renewable|solar|transmission/i],
  ["Metals & mining", /metal|steel|iron|aluminium|copper|zinc|mining|mineral|alloy|ferro/i],
  ["FMCG & food", /fmcg|food|beverage|tobacco|household|personal care|agri|sugar|tea|coffee|edible|dairy|consumer staple|breweries|distill/i],
  ["Consumer & retail", /retail|consumer|apparel|textile|footwear|jewel|leisure|hotel|restaurant|travel|tourism|media|entertain|broadcast|publish|education|durable|appliance/i],
  ["Telecom", /telecom|communication|cable|satellite/i],
  ["Capital goods & industrials", /capital goods|industrial|machinery|engineering|electrical|equipment|defence|aerospace|ship|bearing|castings|forging|tools|manufactur|packaging|paper|plastic|glass/i],
  ["Construction & infra", /construct|infra|cement|building|road|port|logistic|transport|airline|aviation|railway/i],
  ["Real estate", /realty|real estate|housing|property/i],
  ["Chemicals & fertilisers", /chemical|fertili[sz]er|pesticide|agrochem|paint|dye|specialty|petrochemical/i],
];
export const broadSector = (name: string | null | undefined): string => {
  if (!name) return "Other";
  for (const [k, re] of BROAD) if (re.test(name)) return k;
  return "Other";
};

/** Broad sectors of the whole market: cap-weighted move and total market cap, largest first (every sector, grouped into about twenty). */
export function sectorBoard(rows: readonly Row[]): { sector: string; move: number; cap: number; n: number }[] {
  const by = new Map<string, Row[]>();
  for (const r of rows) if (trade(r) && (r.market_cap ?? 0) >= 100 && Math.abs(r.change_pct as number) <= MAX_MOVE) { const k = broadSector(r.sector); by.set(k, [...(by.get(k) || []), r]); }
  return [...by.entries()].map(([sector, rs]) => ({ sector, move: weightedMove(rs) as number, cap: rs.reduce((a, r) => a + (r.market_cap as number), 0), n: rs.length })).sort((a, b) => b.cap - a.cap);
}

/** Exchanges cap a day's move at 20% (rarely 40% or more for a new listing or a relisting); anything beyond this is a data or corporate-action artefact, not a market move. */
export const MAX_MOVE = 40;

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
