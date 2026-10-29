// Pure logic behind the shareholding bar chart: which filings to show, the change in percentage points, the hidden-holder rules and the CSV text.
import type { Ownership } from "./api";
import { ownershipAt, ownershipYears, parsePeriod } from "./ownershipYears";

export type Gran = "quarterly" | "yearly";
export type RangeKey = "1Y" | "3Y" | "5Y" | "All";
export type BarView = "mix" | "change";
export type OwnCat = { key: string; label: string; values: (number | null)[] };
export type OwnBar = {
  /** Position in `o.periods`. */
  index: number; period: string;
  values: Record<string, number | null>;
  /** Percentage-point change against the same quarter a year earlier (quarterly) or the previous year's latest filing (yearly). */
  changes: Record<string, number | null>;
  comparedWith: string | null;
  /** False when no holder has a figure in this filing. */
  filed: boolean;
};

export const CAT_ORDER = ["promoters", "fii", "dii", "public", "government"];
export const CAT_LABEL: Record<string, string> = { promoters: "Promoters", fii: "Foreign institutions", dii: "Domestic institutions", public: "Retail & others", government: "Government & others" };
export const RANGES: RangeKey[] = ["1Y", "3Y", "5Y", "All"];

const r2 = (n: number) => Math.round(n * 100) / 100;
/** a - b in percentage points, null when either figure is missing (never zero). */
export const diffPp = (a: number | null | undefined, b: number | null | undefined): number | null => (a == null || b == null ? null : r2(a - b));

/** One series per holder group. "Government" and "others" are drawn together as one group; a missing figure stays null. */
export function ownCategories(o: Pick<Ownership, "periods" | "series">): OwnCat[] {
  const n = o.periods.length, at = (k: string, i: number) => o.series[k]?.[i] ?? null;
  return CAT_ORDER.map((key) => {
    const values = Array.from({ length: n }, (_, i) => {
      if (key !== "government") return at(key, i);
      const g = at("government", i), x = at("others", i);
      return g == null && x == null ? null : r2((g ?? 0) + (x ?? 0));
    });
    return { key, label: CAT_LABEL[key], values };
  }).filter((c) => c.values.some((x) => x != null));
}

/** Indexes of the filings to draw, oldest first. Quarterly: the last 4 quarters per year of range. Yearly: the latest filing of each of the last N years (at least 2, so there is something to compare). */
export function barIndexes(periods: string[], gran: Gran, range: RangeKey): number[] {
  const years = range === "All" ? Infinity : +range[0];
  if (gran === "quarterly") { const all = periods.map((_, i) => i); return years === Infinity ? all : all.slice(-4 * years); }
  const ys = ownershipYears(periods).map((y) => y.index).reverse();
  return years === Infinity ? ys : ys.slice(-Math.max(years, 2));
}

/** The earlier filing a bar is compared with, or -1. */
export function compareIndex(periods: string[], index: number, gran: Gran): number {
  if (gran === "quarterly") {
    const w = ownershipAt({ periods, series: {}, latest: [] }, index);
    return w?.comparedWith ? periods.indexOf(w.comparedWith) : -1;
  }
  const cur = parsePeriod(periods[index] ?? "");
  if (!cur) return -1;
  const prev = ownershipYears(periods).find((y) => y.year < cur.year); // newest first: the closest earlier year
  return prev ? prev.index : -1;
}

export function buildBars(o: Pick<Ownership, "periods" | "series">, gran: Gran, range: RangeKey): OwnBar[] {
  const cats = ownCategories(o);
  return barIndexes(o.periods, gran, range).map((index) => {
    const cmp = compareIndex(o.periods, index, gran);
    const values: OwnBar["values"] = {}, changes: OwnBar["changes"] = {};
    for (const c of cats) { values[c.key] = c.values[index] ?? null; changes[c.key] = cmp >= 0 ? diffPp(c.values[index], c.values[cmp]) : null; }
    return { index, period: o.periods[index], values, changes, comparedWith: cmp >= 0 ? o.periods[cmp] : null, filed: cats.some((c) => values[c.key] != null) };
  });
}

/** Hide or show a holder group. The last visible group cannot be hidden, so the chart is never empty. */
export function toggleHidden(hidden: string[], key: string, all: string[]): string[] {
  if (hidden.includes(key)) return hidden.filter((k) => k !== key);
  return all.filter((k) => !hidden.includes(k)).length <= 1 ? hidden : [...hidden, key];
}
export const MIX_HIDDEN_NOTE = "Hidden holders are not shown; bars no longer add to 100%";

/** Symmetric scale for the change view, from the biggest visible move: { max, step } in percentage points. */
export function changeScale(bars: OwnBar[], visible: string[]): { max: number; step: number } {
  const m = Math.max(0.1, ...bars.flatMap((b) => visible.map((k) => Math.abs(b.changes[k] ?? 0))));
  const step = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20].find((s) => m / s <= 3) ?? 20;
  return { max: Math.ceil(m / step - 1e-9) * step, step };
}

export const fmtPct = (v: number | null | undefined, d = 2) => (v == null ? "not filed" : v.toFixed(d) + "%");
export const fmtPp = (v: number | null | undefined, d = 2) => (v == null ? "no earlier figure" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d) + " pp");

/** The shown table as CSV text: one row per bar, only the visible holder groups. Missing figures are empty cells. */
export function ownershipCsv(bars: OwnBar[], cats: { key: string; label: string }[], view: BarView): string {
  const q = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  const head = ["Period", ...cats.map((c) => `${c.label} (${view === "mix" ? "% of shares" : "change, pp"})`), ...(view === "change" ? ["Compared with"] : [])];
  const rows = bars.map((b) => [b.period, ...cats.map((c) => { const v = view === "mix" ? b.values[c.key] : b.changes[c.key]; return v == null ? "" : String(v); }), ...(view === "change" ? [b.comparedWith ?? ""] : [])]);
  return [head, ...rows].map((r) => r.map(q).join(",")).join("\n") + "\n";
}

/** Which filing is showing, and whether it is the latest one of its year (a bar clicked in the quarterly chart may not be). */
export function selectionInfo(periods: string[], index: number): { year: number | null; isYearLatest: boolean; yearLatest: string | null } {
  const cur = parsePeriod(periods[index] ?? "");
  if (!cur) return { year: null, isYearLatest: true, yearLatest: null };
  const yl = ownershipYears(periods).find((y) => y.year === cur.year);
  return { year: cur.year, isYearLatest: !yl || yl.index === index, yearLatest: yl ? periods[yl.index] : null };
}

/** Plain-text summary of the chart for screen readers. */
export function barsSummary(bars: OwnBar[], cats: { key: string; label: string }[], view: BarView): string {
  if (bars.length < 2) return "Not enough filings to show a trend.";
  const last = bars[bars.length - 1];
  const parts = cats.map((c) => view === "mix" ? `${c.label} ${fmtPct(last.values[c.key], 1)}` : `${c.label} ${fmtPp(last.changes[c.key], 1)}`);
  return `${view === "mix" ? "Stacked bars of the shareholding pattern" : "Bars of the change in percentage points since a year earlier"}, ${bars.length} filings from ${bars[0].period} to ${last.period}. Latest, ${last.period}: ${parts.join(", ")}.`;
}
