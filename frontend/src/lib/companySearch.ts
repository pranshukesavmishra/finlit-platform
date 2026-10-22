// Typo-tolerant company search over the search index (/api/stocks/search-index rows: [symbol, name, bse, ready, nse?]).
// Order: exact symbol > symbol prefix > name words > fuzzy (a near-miss symbol beats a near-miss name, so "relaince" puts RELIANCE first).
// Pure, so it is tested without the page. Reuses the edit distance and word matching of metricSearch.
import { distance, score, tokens } from "./metricSearch";

export type CompanyRow = readonly [symbol: string, name: string, ...rest: unknown[]];
export type CompanyHit = { symbol: string; name: string; rank: number };

const allow = (n: number) => (n <= 3 ? 0 : n <= 5 ? 1 : 2);
/** Index rows that are not companies (Graph Studio prefixes indices with "^"). */
const isCompany = (sym: string) => !!sym && !sym.startsWith("^");

/** Rank of one row for a query; 0 = no match. Higher is better. */
export function companyRank(query: string, symbol: string, name: string): number {
  const q = query.trim();
  if (!q) return 0;
  const qs = q.toUpperCase().replace(/\s+/g, ""), sym = symbol.toUpperCase();
  if (sym === qs) return 1000;
  if (sym.startsWith(qs)) return 900 - Math.min(99, sym.length - qs.length);
  const n = score(q, name);                       // 100 exact, 90 prefix, 80 every word starts a name word, 60 contained, 40 near miss
  if (n >= 60) return 400 + n;
  const qc = tokens(q).join(""), sc = sym.toLowerCase().replace(/[^a-z0-9]/g, "");
  const symNear = qc.length >= 4 && (distance(qc, sc) <= allow(qc.length) || distance(qc, sc.slice(0, qc.length)) <= allow(qc.length));
  if (symNear) return 300 - distance(qc, sc);
  return n > 0 ? 200 : 0;
}

/** Best matches first; ties keep shorter names first (the parent company before its subsidiaries), then the index order. */
export function rankCompanies(rows: readonly CompanyRow[] | undefined, query: string, limit = 8, exclude: readonly string[] = []): CompanyHit[] {
  if (!rows?.length || !query.trim()) return [];
  const skip = new Set(exclude.map((s) => s.toUpperCase()));
  const out: (CompanyHit & { i: number })[] = [];
  rows.forEach((r, i) => {
    const symbol = String(r[0] ?? ""), name = String(r[1] ?? symbol);
    if (!isCompany(symbol) || skip.has(symbol.toUpperCase())) return;
    const rank = companyRank(query, symbol, name);
    if (rank > 0) out.push({ symbol, name, rank, i });
  });
  out.sort((a, b) => b.rank - a.rank || a.name.length - b.name.length || a.i - b.i);
  return out.slice(0, limit).map(({ symbol, name, rank }) => ({ symbol, name, rank }));
}
