// Sector and market-cap filters shared by every company search of the site (the Ctrl K palette and the company pickers): the pure part, no React.
// The search index carries, beside its rows, a sector table (`sectors`), one sector code per row (`sec`, -1 = unknown) and one market value in
// rupees crore per row (`mc`, 0 = unknown). The screener rows carry `sector` and `market_cap` directly; both feed the same functions through
// `Sized` (sector name + crore). A company whose sector or size is unknown is left out only while that filter is on, and is never shown under a
// sector or band it does not belong to. The size bands are CAP_BUCKETS, the same ones the portfolio checker uses.
import { CAP_BUCKETS, capBucket, type CapBucket } from "./capBuckets";
import { searchStocks } from "./globalSearch";
import type { SearchIndex, SearchRow } from "./api";

export type CapId = CapBucket["id"];
export type StockFilter = { sector: string | null; cap: CapId | null };
export const NO_FILTER: StockFilter = { sector: null, cap: null };
export const filterOn = (f: StockFilter) => !!f.sector || !!f.cap;

export type Facet = { name: string; n: number };
export type CapFacet = { id: CapId; label: string; range: string; n: number };
export type Facets = { sectors: Facet[]; caps: CapFacet[]; unknown: { sector: number; cap: number }; total: number };
/** What a filter needs to know about one company: its sector name and market value in rupees crore (null when unknown). */
export type Sized = { sector: string | null; cap: number | null };

const isCompany = (r: SearchRow) => !!r[0] && !r[0].startsWith("^");

/** The size band of a market value in crore, or null when it is not known. */
export const bandOf = (crore: number | null | undefined): CapBucket | null => (crore != null && crore > 0 ? capBucket(crore) : null);

/** Does a company pass the filter? Unknown sector or size fails only the filter that needs it. */
export function passesValues(sector: string | null | undefined, crore: number | null | undefined, f: StockFilter): boolean {
  if (f.sector && sector !== f.sector) return false;
  if (f.cap && bandOf(crore)?.id !== f.cap) return false;
  return true;
}

/** Sectors that really occur in the data with their company counts (most first, ties by name), the six bands with counts, and how many are unknown. */
export function facetsOf(items: Iterable<Sized>): Facets {
  const sec = new Map<string, number>(), cap = new Map<CapId, number>();
  let unknownSector = 0, unknownCap = 0, total = 0;
  for (const it of items) {
    total += 1;
    if (it.sector) sec.set(it.sector, (sec.get(it.sector) || 0) + 1); else unknownSector += 1;
    const b = bandOf(it.cap);
    if (b) cap.set(b.id, (cap.get(b.id) || 0) + 1); else unknownCap += 1;
  }
  return {
    sectors: [...sec].map(([name, n]) => ({ name, n })).sort((a, b) => b.n - a.n || a.name.localeCompare(b.name)),
    caps: CAP_BUCKETS.map((b) => ({ id: b.id, label: b.label, range: b.range, n: cap.get(b.id) || 0 })),
    unknown: { sector: unknownSector, cap: unknownCap }, total,
  };
}

/** The sector name of index row i, or null when unknown. */
export function sectorAt(idx: SearchIndex | undefined, i: number): string | null {
  const c = idx?.sec?.[i];
  return c != null && c >= 0 ? idx?.sectors?.[c] ?? null : null;
}
/** The size band of index row i, or null when the market value is unknown. */
export function capAt(idx: SearchIndex | undefined, i: number): CapBucket | null {
  return bandOf(idx?.mc?.[i]);
}
/** True when the index carries sector or market-value data at all (an older server sends neither: no controls then). */
export const hasFilterData = (idx: SearchIndex | undefined) => !!(idx?.sec && idx.sectors?.length) || !!idx?.mc?.some((v) => v > 0);

const facetCache = new WeakMap<SearchIndex, Facets>();
/** Facets of the whole search index (companies only; index entries such as "^NSEI" are not companies). */
export function indexFacets(idx: SearchIndex | undefined): Facets {
  if (!idx) return facetsOf([]);
  let f = facetCache.get(idx);
  if (!f) { f = facetsOf(idx.rows.flatMap((r, i) => (isCompany(r) ? [{ sector: sectorAt(idx, i), cap: idx.mc?.[i] ?? null }] : []))); facetCache.set(idx, f); }
  return f;
}

/** Does index row i pass the filter? */
export const passes = (idx: SearchIndex | undefined, i: number, f: StockFilter) => passesValues(sectorAt(idx, i), idx?.mc?.[i], f);

/** Index rows that pass the filter, largest market value first (rows when no filter is on: the index itself, untouched). Companies pickers rank on top of this. */
export function filteredRows(idx: SearchIndex | undefined, f: StockFilter): SearchRow[] {
  const rows = idx?.rows || [];
  if (!filterOn(f)) return rows;
  const at: number[] = [];
  rows.forEach((r, i) => { if (isCompany(r) && passes(idx, i, f)) at.push(i); });
  at.sort((a, b) => (idx?.mc?.[b] || 0) - (idx?.mc?.[a] || 0) || a - b);
  return at.map((i) => rows[i]);
}

/** Companies that pass the filter, in display order. With a query: best match first (the shared rank), then size. Without one: largest market value first. */
export function filterStocks(idx: SearchIndex | undefined, query: string, f: StockFilter, limit: number, mine: Set<string> = new Set()): { rows: SearchRow[]; total: number } {
  if (!idx?.rows.length) return { rows: [], total: 0 };
  if (query.trim()) {
    const hits = searchStocks(idx.rows, query, 1e9, mine, (i) => passes(idx, i, f), idx.isin);
    return { rows: hits.slice(0, limit).map((h) => h.row), total: hits.length };
  }
  const all = filteredRows(idx, f);
  return { rows: all.slice(0, limit), total: all.length };
}

/** "Mega-cap Information Technology" (the filter in words; empty when none). */
export function filterPhrase(f: StockFilter): string {
  return [f.cap ? CAP_BUCKETS.find((b) => b.id === f.cap)?.label : "", f.sector].filter(Boolean).join(" ");
}
/** "Mega-cap Information Technology companies", "Information Technology companies", "Mega-cap company" (n = 1). */
export function filterNoun(f: StockFilter, n = 2): string {
  return [filterPhrase(f), n === 1 ? "company" : "companies"].filter(Boolean).join(" ");
}

// ---- why a company is not in the list: the filter hides it, and the reader is told so ----
export type FilterKey = "sector" | "cap";
export type HiddenHit = { symbol: string; name: string; keys: FilterKey[]; why: string };
const capLabel = (id: CapId | null) => (id ? CAP_BUCKETS.find((b) => b.id === id)?.label ?? id : "");

/** The active filters in words, one entry each: ["Sector: Information Technology", "Market cap: Mega-cap"]. Empty when none is on. */
export function filterParts(f: StockFilter): string[] {
  return [f.sector ? `Sector: ${f.sector}` : "", f.cap ? `Market cap: ${capLabel(f.cap)}` : ""].filter(Boolean);
}
/** The filter with some of its parts removed (the part that hides a company). */
export function relaxed(f: StockFilter, keys: readonly FilterKey[]): StockFilter {
  return { sector: keys.includes("sector") ? null : f.sector, cap: keys.includes("cap") ? null : f.cap };
}
/** Which parts of the filter a company fails (unknown sector or size fails only the part that needs it). */
export function failedKeys(sector: string | null | undefined, crore: number | null | undefined, f: StockFilter): FilterKey[] {
  const out: FilterKey[] = [];
  if (f.sector && sector !== f.sector) out.push("sector");
  if (f.cap && bandOf(crore)?.id !== f.cap) out.push("cap");
  return out;
}
/** "Hidden by your filter: Sector Information Technology (this company: Banks)". */
export function whyHidden(keys: readonly FilterKey[], f: StockFilter, sector: string | null | undefined, crore: number | null | undefined): string {
  const bits = keys.map((k) => k === "sector" ? `Sector ${f.sector}${sector ? ` (this one is in ${sector})` : " (this one has no sector on file)"}` : `Market cap ${capLabel(f.cap)}${bandOf(crore) ? ` (this one is ${bandOf(crore)!.label})` : " (this one has no market value on file)"}`);
  return `Hidden by your filter: ${bits.join(" and ")}`;
}

/** Companies that match the typed text by name, symbol, exchange code or ISIN but that the filter leaves out, best match first. */
export function hiddenMatches(idx: SearchIndex | undefined, query: string, f: StockFilter, limit = 3): HiddenHit[] {
  if (!idx?.rows.length || !query.trim() || !filterOn(f)) return [];
  const hits = searchStocks(idx.rows, query, limit, new Set(), (i) => !passes(idx, i, f), idx.isin);
  const at = new Map(idx.rows.map((r, i) => [r[0], i] as [string, number]));
  return hits.map(({ row }) => {
    const i = at.get(row[0])!, sector = sectorAt(idx, i), crore = idx.mc?.[i];
    const keys = failedKeys(sector, crore, f);
    return { symbol: row[0], name: row[1], keys, why: whyHidden(keys, f, sector, crore) };
  });
}
/** The same for picker rows that carry sector and market_cap directly (screener rows). */
export function hiddenRowMatches<T extends { symbol: string; name?: string | null }>(items: readonly T[], size: (t: T) => Sized, query: string, f: StockFilter, limit = 3): HiddenHit[] {
  const t = query.trim().toLowerCase();
  if (!t || !filterOn(f)) return [];
  const out: HiddenHit[] = [];
  for (const it of items) {
    if (out.length >= limit) break;
    if (!it.symbol.toLowerCase().includes(t) && !(it.name || "").toLowerCase().includes(t)) continue;
    const z = size(it), keys = failedKeys(z.sector, z.cap, f);
    if (keys.length) out.push({ symbol: it.symbol, name: it.name || it.symbol, keys, why: whyHidden(keys, f, z.sector, z.cap) });
  }
  return out;
}

const isinCache = new WeakMap<SearchIndex, ReadonlyMap<string, string>>();
/** symbol -> ISIN for the rows that have one (the index sends them as a list parallel to its rows). */
export function isinMap(idx: SearchIndex | undefined): ReadonlyMap<string, string> | undefined {
  if (!idx?.isin?.length) return undefined;
  let m = isinCache.get(idx);
  if (!m) { m = new Map(idx.rows.flatMap((r, i) => (idx.isin![i] ? [[r[0], idx.isin![i]] as [string, string]] : []))); isinCache.set(idx, m); }
  return m;
}
