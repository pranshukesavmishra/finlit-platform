// Sector and market-cap filters of the site search: the pure part (no React), so it is tested without the page.
// The search index carries, beside its rows, a sector table (`sectors`), one sector code per row (`sec`, -1 = unknown) and one market value in
// rupees crore per row (`mc`, 0 = unknown). A company whose sector or size is unknown is left out only while that filter is on, and is never
// shown under a sector or band it does not belong to. The size bands are CAP_BUCKETS, the same ones the portfolio checker uses.
import { CAP_BUCKETS, capBucket, type CapBucket } from "./capBuckets";
import { searchStocks } from "./globalSearch";
import type { SearchIndex, SearchRow } from "./api";

export type CapId = CapBucket["id"];
export type StockFilter = { sector: string | null; cap: CapId | null };
export const NO_FILTER: StockFilter = { sector: null, cap: null };
export const filterOn = (f: StockFilter) => !!f.sector || !!f.cap;

export type Facet = { name: string; n: number };
export type CapFacet = { id: CapId; label: string; range: string; n: number };

const isCompany = (r: SearchRow) => !!r[0] && !r[0].startsWith("^");

/** The sector name of row i, or null when unknown. */
export function sectorAt(idx: SearchIndex | undefined, i: number): string | null {
  const c = idx?.sec?.[i];
  return c != null && c >= 0 ? idx?.sectors?.[c] ?? null : null;
}
/** The size band of row i, or null when the market value is unknown. */
export function capAt(idx: SearchIndex | undefined, i: number): CapBucket | null {
  const v = idx?.mc?.[i];
  return v != null && v > 0 ? capBucket(v) : null;
}

/** Sectors that really occur in the data with how many companies each has, most companies first (ties by name). */
export function sectorFacets(idx: SearchIndex | undefined): Facet[] {
  if (!idx?.sec || !idx.sectors) return [];
  const n = new Map<string, number>();
  idx.rows.forEach((r, i) => { if (!isCompany(r)) return; const s = sectorAt(idx, i); if (s) n.set(s, (n.get(s) || 0) + 1); });
  return [...n].map(([name, c]) => ({ name, n: c })).sort((a, b) => b.n - a.n || a.name.localeCompare(b.name));
}
/** The six bands (largest first) with how many companies fall in each. */
export function capFacets(idx: SearchIndex | undefined): CapFacet[] {
  const n = new Map<CapId, number>();
  if (idx?.mc) idx.rows.forEach((r, i) => { if (!isCompany(r)) return; const b = capAt(idx, i); if (b) n.set(b.id, (n.get(b.id) || 0) + 1); });
  return CAP_BUCKETS.map((b) => ({ id: b.id, label: b.label, range: b.range, n: n.get(b.id) || 0 }));
}
/** How many companies have no sector / no market value in the index (they drop out while that filter is on). */
export function unknownCounts(idx: SearchIndex | undefined): { sector: number; cap: number } {
  let sector = 0, cap = 0;
  idx?.rows.forEach((r, i) => { if (!isCompany(r)) return; if (!sectorAt(idx, i)) sector += 1; if (!capAt(idx, i)) cap += 1; });
  return { sector, cap };
}

/** Does row i pass the filter? */
export function passes(idx: SearchIndex | undefined, i: number, f: StockFilter): boolean {
  if (f.sector && sectorAt(idx, i) !== f.sector) return false;
  if (f.cap && capAt(idx, i)?.id !== f.cap) return false;
  return true;
}

/** Companies that pass the filter, in display order. With a query: best match first (the shared rank), then size. Without one: largest market value first. */
export function filterStocks(idx: SearchIndex | undefined, query: string, f: StockFilter, limit: number, mine: Set<string> = new Set()): { rows: SearchRow[]; total: number } {
  const all = idx?.rows;
  if (!all?.length) return { rows: [], total: 0 };
  if (query.trim()) {
    const hits = searchStocks(all, query, 1e9, mine, (i) => passes(idx, i, f));
    return { rows: hits.slice(0, limit).map((h) => h.row), total: hits.length };
  }
  const at: number[] = [];
  all.forEach((r, i) => { if (isCompany(r) && passes(idx, i, f)) at.push(i); });
  at.sort((a, b) => (idx?.mc?.[b] || 0) - (idx?.mc?.[a] || 0) || a - b);
  return { rows: at.slice(0, limit).map((i) => all[i]), total: at.length };
}

/** "Mega-cap Information Technology" (the filter in words; empty when none). */
export function filterPhrase(f: StockFilter): string {
  return [f.cap ? CAP_BUCKETS.find((b) => b.id === f.cap)?.label : "", f.sector].filter(Boolean).join(" ");
}
/** "Mega-cap Information Technology companies", "Information Technology companies", "Mega-cap company" (n = 1). */
export function filterNoun(f: StockFilter, n = 2): string {
  return [filterPhrase(f), n === 1 ? "company" : "companies"].filter(Boolean).join(" ");
}
