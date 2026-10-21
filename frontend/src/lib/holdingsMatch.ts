import type { SearchRow } from "./api";
import { SPLIT_NAMES, canon } from "./aliases";
import { gridFromText, namesFromGrid, tidy, type NameMatcher } from "./holdingsFile";

/** Turning what a person typed, pasted or exported into listed companies. */

const norm = (s: string) => s.toUpperCase().replace(/&/g, " AND ").replace(/\b(LIMITED|LTD|THE|CO|COMPANY|CORPORATION|CORP|INC)\b\.?/g, " ").replace(/[^A-Z0-9]+/g, " ").trim();

/** The names or tickers in pasted text or a CSV: the column of listed companies (or headed symbol/stock/name/company), else the first column. */
export function namesFrom(text: string, matches?: NameMatcher): string[] {
  return namesFromGrid(gridFromText(text), matches);
}

export type How = "exact" | "close" | "split" | "alias" | "scan";   // how sure a match is: exact ticker, code or full name, a name that only starts the same way, a demerged company, a retired ticker, or found inside running text
export type Found = { input: string; symbol: string; name: string; how: How };

/** One lookup, built once per search list: ticker, NSE or BSE code, and the company name without Ltd/Limited/&.
 *  `exact` uses hash lookups only (safe to call on every word window of a document); `find` also accepts a name that starts the same way. */
export function makeLookup(index: SearchRow[]) {
  const byCode = new Map<string, SearchRow>(), byName = new Map<string, SearchRow>();
  for (const r of index) {
    for (const c of [r[0], r[2], r[4]]) if (c && !byCode.has(c.toUpperCase())) byCode.set(c.toUpperCase(), r);
    const n = norm(r[1]); if (n && !byName.has(n)) byName.set(n, r);
  }
  const exact = (input: string): SearchRow | undefined => { const t = tidy(input); return byCode.get(t.toUpperCase()) || byName.get(norm(t)); };
  // normalised names, worked out once and only when a "starts the same way" search is first needed (norm on 6000 names for every unmatched line was seconds on a long statement)
  let norms: string[] | undefined;
  const one = (input: string): { row: SearchRow; how: "exact" | "close" } | undefined => {
    const e = exact(input); if (e) return { row: e, how: "exact" };
    const n = norm(tidy(input));
    let c: SearchRow | undefined;
    if (n.length >= 4) { norms ??= index.map((r) => norm(r[1])); const i = norms.findIndex((m) => m === n || m.startsWith(n + " ")); c = i >= 0 ? index[i] : undefined; }
    return c ? { row: c, how: "close" } : undefined;
  };
  // "Larsen & Toubro Ltd., Mumbai": a broker's registered-office tail after a comma is not part of the name.
  const find = (input: string) => one(input) || (input.includes(",") ? one(input.slice(0, input.indexOf(","))) : undefined);
  return { find, exact, norm };
}

/** Whether a name is a listed company; lets the file reader pick the right column. Empty until the company list has loaded. */
export function makeMatcher(index: SearchRow[]): NameMatcher | undefined {
  if (!index.length) return undefined;
  const { find } = makeLookup(index);
  return (name) => !!find(name) || !!SPLIT_NAMES[tidy(name).toUpperCase().replace(/\s+/g, " ")];
}

/** Match each name to a listed company. The search list is biggest company first, so an ambiguous name picks the larger company. */
export function matchNames(names: string[], index: SearchRow[]): { found: Found[]; missing: string[] } {
  const { find } = makeLookup(index);
  const found: Found[] = [], missing: string[] = [];
  const bySymbol = new Map(index.map((r) => [r[0], r]));
  for (const input of names) {
    const split = SPLIT_NAMES[tidy(input).toUpperCase().replace(/\s+/g, " ")];
    const parts = split ? split.map((sym) => bySymbol.get(sym)).filter((r): r is SearchRow => !!r) : [];
    if (parts.length) { parts.forEach((r) => found.push({ input, symbol: r[0], name: r[1], how: "split" })); continue; }   // a demerged company: the old share is now all of its parts
    const hit = find(input);
    if (hit) { found.push({ input, symbol: hit.row[0], name: hit.row[1], how: hit.how }); continue; }
    const old = bySymbol.get(canon(tidy(input).toUpperCase()));
    if (old) found.push({ input, symbol: old[0], name: old[1], how: "alias" }); else missing.push(input);
  }
  return { found, missing };
}
