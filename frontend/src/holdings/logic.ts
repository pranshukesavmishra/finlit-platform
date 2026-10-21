// Pure helpers for the holdings section: grouping small positions, sums, change classification, sorting, donut geometry. No DOM, no React.
import type { AssetSplit, Holding, Portfolio } from "./types";

/** Positions below this share of the portfolio (in percent) are drawn as one "Other holdings" slice; every one of them is still listed in a table. */
export const SMALL_BELOW_PCT = 1;
/** Two percentages closer than this (percentage points) count as unchanged: published figures carry two decimals. */
export const CHANGE_EPS = 0.005;

const r6 = (x: number) => Math.round(x * 1e6) / 1e6;
/** Sum of percentages, ignoring missing ones, free of float noise (0.1 + 0.2 = 0.3). */
export const sumPct = (xs: (number | null | undefined)[]) => r6(xs.reduce<number>((a, b) => a + (typeof b === "number" && Number.isFinite(b) ? b : 0), 0));

export type Grouped = { major: Holding[]; small: Holding[]; otherPct: number; otherCount: number; totalPct: number };
/** Split into holdings at or above the threshold (largest first) and the small ones. A holding with no published percent is "small" (listed, never drawn). */
export function groupHoldings(holdings: Holding[], threshold = SMALL_BELOW_PCT): Grouped {
  const byPct = (a: Holding, b: Holding) => (b.pct ?? -1) - (a.pct ?? -1) || a.name.localeCompare(b.name);
  const major = holdings.filter((h) => h.pct != null && h.pct >= threshold).sort(byPct);
  const small = holdings.filter((h) => h.pct == null || h.pct < threshold).sort(byPct);
  return { major, small, otherPct: sumPct(small.map((h) => h.pct)), otherCount: small.length, totalPct: sumPct(holdings.map((h) => h.pct)) };
}

export type Slice = { key: string; label: string; pct: number; sector: string | null; other: boolean; holding?: Holding };
/** Slices for the donut: each major holding, then one "Other holdings" slice for the rest (only if it has weight). */
export function sliceList(g: Grouped): Slice[] {
  const s: Slice[] = g.major.map((h, i) => ({ key: `h${i}`, label: h.name, pct: h.pct as number, sector: h.sector, other: false, holding: h }));
  if (g.otherPct > 0) s.push({ key: "other", label: `Other holdings (${g.otherCount} below ${SMALL_BELOW_PCT}%)`, pct: g.otherPct, sector: null, other: true });
  return s;
}

/** Sum of the n largest holdings' percentages. */
export function topNPct(holdings: Holding[], n = 10): number | null {
  const p = holdings.map((h) => h.pct).filter((x): x is number => typeof x === "number").sort((a, b) => b - a);
  return p.length ? sumPct(p.slice(0, n)) : null;
}

export type ChangeKind = "new" | "exited" | "increased" | "decreased" | "unchanged";
export type ChangeRow = { name: string; isin: string | null; stockSymbol: string | null; kind: ChangeKind; pct: number | null; prevPct: number | null; change: number | null };
/** Month-on-month movement. Needs the previous month: without it (no `previousAsOf`) nothing is classified, returns null. New = no previous percent; exited = in `exited`. */
export function classifyChanges(p: Pick<Portfolio, "holdings" | "exited" | "previousAsOf">): ChangeRow[] | null {
  if (!p.previousAsOf) return null;
  const rows: ChangeRow[] = [];
  for (const h of p.holdings) {
    if (h.pct == null) continue;
    const prev = h.prevPct;
    const ch = prev == null ? null : r6(h.pct - prev);
    const kind: ChangeKind = prev == null ? "new" : Math.abs(ch as number) < CHANGE_EPS ? "unchanged" : (ch as number) > 0 ? "increased" : "decreased";
    rows.push({ name: h.name, isin: h.isin, stockSymbol: h.stockSymbol, kind, pct: h.pct, prevPct: prev, change: kind === "new" ? h.pct : ch });
  }
  for (const e of p.exited) {
    const prev = e.prevPct ?? e.pct ?? null;
    rows.push({ name: e.name || "—", isin: e.isin ?? null, stockSymbol: e.stockSymbol ?? null, kind: "exited", pct: 0, prevPct: prev, change: prev == null ? null : -prev });
  }
  const order: Record<ChangeKind, number> = { new: 0, exited: 1, increased: 2, decreased: 3, unchanged: 4 };
  return rows.sort((a, b) => order[a.kind] - order[b.kind] || Math.abs(b.change ?? 0) - Math.abs(a.change ?? 0) || a.name.localeCompare(b.name));
}

export type SortDir = "asc" | "desc";
/** Sort holdings by a column; missing values always last. */
export function sortHoldings(rows: Holding[], key: "name" | "sector" | "pct" | "qty" | "valueLakh", dir: SortDir): Holding[] {
  const sgn = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = a[key], y = b[key];
    if (x == null && y == null) return a.name.localeCompare(b.name);
    if (x == null) return 1;
    if (y == null) return -1;
    const c = typeof x === "string" ? x.localeCompare(y as string) : (x as number) - (y as number);
    return c * sgn || a.name.localeCompare(b.name);
  });
}

/** Asset split rows from published values only (a missing class stays missing, never zero). */
export function assetRows(a: AssetSplit | null | undefined): { key: keyof AssetSplit; label: string; pct: number | null }[] {
  const x = a || { equity: null, debt: null, cash: null, other: null };
  return [{ key: "equity", label: "Equity", pct: x.equity }, { key: "debt", label: "Debt", pct: x.debt }, { key: "cash", label: "Cash and equivalents", pct: x.cash }, { key: "other", label: "Other", pct: x.other }];
}

/** Sector rows: the published summary when present, else worked out from the holdings' sectors (equity rows with a sector). Largest first. */
export function sectorRows(p: Pick<Portfolio, "holdings" | "summary">): { sector: string; pct: number }[] {
  if (p.summary?.sectors?.length) return [...p.summary.sectors].sort((a, b) => b.pct - a.pct);
  const m = new Map<string, number>();
  for (const h of p.holdings) if (h.sector && h.pct != null) m.set(h.sector, (m.get(h.sector) || 0) + h.pct);
  return [...m].map(([sector, pct]) => ({ sector, pct: r6(pct) })).sort((a, b) => b.pct - a.pct);
}

/** SVG path of a donut segment between two fractions (0..1 of the circle, from 12 o'clock, clockwise). */
export function arcPath(cx: number, cy: number, rOut: number, rIn: number, f0: number, f1: number): string {
  const full = f1 - f0 >= 0.99999;
  const f = full ? f0 + 0.99999 : f1;
  const pt = (r: number, fr: number) => { const a = fr * 2 * Math.PI - Math.PI / 2; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; };
  const [x0, y0] = pt(rOut, f0), [x1, y1] = pt(rOut, f), [x2, y2] = pt(rIn, f), [x3, y3] = pt(rIn, f0);
  const large = f - f0 > 0.5 ? 1 : 0;
  const n = (v: number) => v.toFixed(2);
  return `M${n(x0)},${n(y0)}A${rOut},${rOut} 0 ${large} 1 ${n(x1)},${n(y1)}L${n(x2)},${n(y2)}A${rIn},${rIn} 0 ${large} 0 ${n(x3)},${n(y3)}Z`;
}
/** Start and end fractions of each slice, scaled so they fill the circle even when the published percentages sum to a little under or over 100. */
export function sliceFractions(pcts: number[]): [number, number][] {
  const tot = pcts.reduce((a, b) => a + b, 0) || 1;
  let acc = 0;
  return pcts.map((p) => { const a = acc / tot; acc += p; return [a, acc / tot] as [number, number]; });
}
