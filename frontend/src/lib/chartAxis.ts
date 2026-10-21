// Shared by the charts that draw one label per period: how often to print a label, and the "From year" window.
import type { PriceRange } from "./api";

/** Print every `n`th label so none overlap: 1 (every label) whenever they all fit in `width` px, otherwise the smallest step that does. */
export function labelEvery(count: number, width: number, longest: number, charPx = 6.2, gap = 10): number {
  if (count <= 1) return 1;
  const fit = Math.max(1, Math.floor(width / (longest * charPx + gap)));
  return Math.max(1, Math.ceil(count / fit));
}

/** Years offered in a "From year" menu: this year back to 2010. */
export const fromYears = (now = new Date().getFullYear()) => Array.from({ length: now - 2009 }, (_, i) => now - i);

/** A price series cut to start in `year` (every parallel array cut at the same index). History that starts later is left as it is. */
export function priceFrom(d: PriceRange, year?: number): PriceRange {
  if (!year) return d;
  const at = d.series.t.findIndex((t) => +t.slice(0, 4) >= year);
  if (at <= 0) return d;
  const cut = <T,>(a: T[] | undefined) => (Array.isArray(a) ? a.slice(at) : a);
  const s = d.series;
  return { ...d, series: { t: s.t.slice(at), o: cut(s.o), h: cut(s.h), l: cut(s.l), c: s.c.slice(at), v: cut(s.v) as never, ema50: cut(s.ema50) as never, ema200: cut(s.ema200) as never } };
}
