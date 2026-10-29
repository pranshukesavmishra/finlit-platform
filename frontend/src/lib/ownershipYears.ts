// Year picker for the shareholding pattern: pick a calendar year and read the pattern as of the LATEST filing in it.
import type { Ownership } from "./api";

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

/** "Sep 2026" -> { year: 2026, month: 8 }, or null when the label is not a quarter label. */
export function parsePeriod(p: string): { year: number; month: number } | null {
  const m = /^([A-Za-z]{3})\w*\s+(\d{4})$/.exec((p || "").trim());
  const month = m ? MONTHS.indexOf(m[1].toLowerCase()) : -1;
  return m && month >= 0 ? { year: +m[2], month } : null;
}

/** Calendar years that have at least one filing, newest first, each with the index of its latest filing in `periods`. */
export function ownershipYears(periods: string[]): { year: number; index: number }[] {
  const last = new Map<number, { index: number; month: number }>();
  periods.forEach((p, i) => {
    const d = parsePeriod(p);
    if (!d) return;
    const cur = last.get(d.year);
    if (!cur || d.month >= cur.month) last.set(d.year, { index: i, month: d.month });
  });
  return [...last.entries()].map(([year, v]) => ({ year, index: v.index })).sort((a, b) => b.year - a.year);
}

export type OwnershipView = {
  asOf: string; index: number; year: number | null;
  comparedWith: string | null;
  /** "same quarter a year earlier", "previous year-end filing", or null when there is no earlier filing. */
  basis: "same quarter a year earlier" | "latest filing of the previous year" | null;
  latest: { key: string; label: string; value: number | null; change1yPts: number | null; before: number | null }[];
};

/** The shareholding pattern as of `periods[index]`, compared with the same quarter a year earlier when it was filed,
 *  else with the latest filing of the previous calendar year. */
export function ownershipAt(o: Pick<Ownership, "periods" | "series" | "latest">, index: number): OwnershipView | null {
  const n = o.periods.length;
  if (index < 0 || index >= n) return null;
  const cur = parsePeriod(o.periods[index]);
  let cmp = -1, basis: OwnershipView["basis"] = null;
  if (cur) {
    cmp = o.periods.findIndex((p) => { const d = parsePeriod(p); return !!d && d.month === cur.month && d.year === cur.year - 1; });
    if (cmp >= 0) basis = "same quarter a year earlier";
    else {
      const prev = ownershipYears(o.periods).find((y) => y.year === cur.year - 1);
      if (prev) { cmp = prev.index; basis = "latest filing of the previous year"; }
    }
  }
  const labels = Object.fromEntries(o.latest.map((l) => [l.key, l.label]));
  const latest = Object.keys(o.series).filter((k) => labels[k]).map((key) => {
    const value = o.series[key][index] ?? null, before = cmp >= 0 ? o.series[key][cmp] ?? null : null;
    return { key, label: labels[key], value, before, change1yPts: value != null && before != null ? Math.round((value - before) * 100) / 100 : null };
  }).filter((l) => l.value != null);
  return { asOf: o.periods[index], index, year: cur?.year ?? null, comparedWith: cmp >= 0 ? o.periods[cmp] : null, basis: cmp >= 0 ? basis : null, latest };
}
