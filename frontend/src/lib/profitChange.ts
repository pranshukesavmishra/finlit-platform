import { MINUS, nf } from "./format";

/** CHANGE column of the profitability table: the last year minus the first year shown, in percentage points (every row is a per-cent ratio).
 *  Never bridges a gap: if either end year has no figure there is no change, and the reason says which one is missing. */
export type PtsChange = { pts: number | null; text: string; dir: "up" | "down" | "flat" | "none"; reason: string | null };

export function ptsChange(first: number | null | undefined, last: number | null | undefined, firstLabel: string, lastLabel: string): PtsChange {
  if (first == null || last == null) {
    const missing = first == null && last == null ? `${firstLabel} or ${lastLabel}` : first == null ? firstLabel : lastLabel;
    return { pts: null, text: "—", dir: "none", reason: `No ${missing} figure` };
  }
  const pts = last - first, r = Math.round(Math.abs(pts) * 10) / 10;
  if (r === 0) return { pts, text: "0.0 pts", dir: "flat", reason: null };
  return { pts, text: `${pts > 0 ? "+" : MINUS}${nf(r, 1)} pts`, dir: pts > 0 ? "up" : "down", reason: null };
}
