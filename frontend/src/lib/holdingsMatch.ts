import type { SearchRow } from "./api";
import { gridFromText, namesFromGrid, tidy, type NameMatcher } from "./holdingsFile";

/** Turning what a person typed, pasted or exported into listed companies. */

const norm = (s: string) => s.toUpperCase().replace(/&/g, " AND ").replace(/\b(LIMITED|LTD|THE|CO|COMPANY|CORPORATION|CORP|INC)\b\.?/g, " ").replace(/[^A-Z0-9]+/g, " ").trim();

/** The names or tickers in pasted text or a CSV: the column of listed companies (or headed symbol/stock/name/company), else the first column. */
export function namesFrom(text: string, matches?: NameMatcher): string[] {
  return namesFromGrid(gridFromText(text), matches);
}

/** One lookup, built once per search list: ticker, NSE or BSE code, and the company name without Ltd/Limited/&. */
function lookup(index: SearchRow[]) {
  const byCode = new Map<string, SearchRow>(), byName = new Map<string, SearchRow>();
  for (const r of index) {
    for (const c of [r[0], r[2], r[4]]) if (c && !byCode.has(c.toUpperCase())) byCode.set(c.toUpperCase(), r);
    const n = norm(r[1]); if (n && !byName.has(n)) byName.set(n, r);
  }
  const one = (input: string): SearchRow | undefined => {
    const t = tidy(input), up = t.toUpperCase(), n = norm(t);
    return byCode.get(up) || byName.get(n) || (n.length >= 4 ? index.find((r) => norm(r[1]).startsWith(n + " ") || norm(r[1]) === n) : undefined);
  };
  // "Larsen & Toubro Ltd., Mumbai": a broker's registered-office tail after a comma is not part of the name.
  const find = (input: string): SearchRow | undefined => one(input) || (input.includes(",") ? one(input.slice(0, input.indexOf(","))) : undefined);
  return find;
}

/** Whether a name is a listed company; lets the file reader pick the right column. Empty until the company list has loaded. */
export function makeMatcher(index: SearchRow[]): NameMatcher | undefined {
  if (!index.length) return undefined;
  const find = lookup(index);
  return (name) => !!find(name);
}

/** Match each name to a listed company. The search list is biggest company first, so an ambiguous name picks the larger company. */
export function matchNames(names: string[], index: SearchRow[]): { found: { input: string; symbol: string; name: string }[]; missing: string[] } {
  const find = lookup(index);
  const found: { input: string; symbol: string; name: string }[] = [], missing: string[] = [];
  for (const input of names) { const hit = find(input); if (hit) found.push({ input, symbol: hit[0], name: hit[1] }); else missing.push(input); }
  return { found, missing };
}
