// What the mutual fund table's summary cards say, worked out from the schemes shown. Pure, so it is tested without the page.
import type { FundRow, SortKey } from "./mf";

const median = (v: number[]): number | null => { if (!v.length) return null; const s = [...v].sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const has = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

export type Summary = {
  n: number;
  withR1y: number; up1y: number; down1y: number; median1y: number | null; median3y: number | null; median5y: number | null;
  medianSip3y: number | null; withSip: number; medianTer: number | null; withTer: number; largestAum: { name: string; aum: number } | null; withAum: number;
  /** true when none of fund size, expense ratio, SIP returns or checklist is on any scheme shown: they are still being loaded, not "missing". */
  extrasLoading: boolean;
};
export function summarise(items: readonly FundRow[]): Summary {
  const r1 = items.map((r) => r.r1y).filter(has), r3 = items.map((r) => r.r3y).filter(has), r5 = items.map((r) => r.r5y).filter(has);
  const sip = items.map((r) => r.sip3y).filter(has), ter = items.map((r) => r.ter).filter(has), aum = items.filter((r) => has(r.aum));
  const big = aum.reduce<FundRow | null>((b, r) => (b == null || (r.aum as number) > (b.aum as number) ? r : b), null);
  return {
    n: items.length, withR1y: r1.length, up1y: r1.filter((v) => v > 0).length, down1y: r1.filter((v) => v < 0).length,
    median1y: median(r1), median3y: median(r3), median5y: median(r5), medianSip3y: median(sip), withSip: sip.length, medianTer: median(ter), withTer: ter.length,
    largestAum: big ? { name: big.name, aum: big.aum as number } : null, withAum: aum.length,
    extrasLoading: items.length > 0 && !aum.length && !ter.length && !sip.length && !items.some((r) => r.checklist),
  };
}

/** The quick "sort by" pills: a neutral order to read the table in, never a recommendation. */
export const SORT_PILLS: { key: SortKey; dir: "asc" | "desc"; label: string }[] = [
  { key: "aum", dir: "desc", label: "Largest fund size" },
  { key: "r1y", dir: "desc", label: "1Y return, highest first" },
  { key: "r3y", dir: "desc", label: "3Y return, highest first" },
  { key: "r5y", dir: "desc", label: "5Y return, highest first" },
  { key: "sip3y", dir: "desc", label: "3Y SIP return, highest first" },
  { key: "ter", dir: "asc", label: "Lowest expense ratio" },
  { key: "checklist", dir: "desc", label: "Most checks passed" },
  { key: "name", dir: "asc", label: "A to Z" },
];

/** Background tint for a return cell: 0 at zero, up to `max` strength at the largest figure of the column on the page. null when there is no figure. */
export function tintOf(v: number | null | undefined, colMax: number): { tone: "pos" | "neg"; k: number } | null {
  if (!has(v) || v === 0 || !(colMax > 0)) return null;
  return { tone: v > 0 ? "pos" : "neg", k: Math.round(Math.min(1, Math.abs(v) / colMax) * 100) / 100 };
}
