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
    const hits = searchStocks(idx.rows, query, 1e9, mine, (i) => passes(idx, i, f));
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
