// Pure helpers behind the Equity portfolio page: number text, sector colours, the readings picked for a section, the treemap layout, the sentences that are only
// a count or a range of the page's own figures. No React here. Information only, not investment advice.
import { ordinal } from "../components/diversification/wording";
import type { Meta, Mode, PageObject, Reading, SizeCode } from "./types";

export { ordinal };
export const MINUS = "−";
/** 0.78 -> ".78", -0.01 -> "−.01" (grid cells); full = "0.78". */
export const short2 = (v: number) => (v < 0 ? MINUS : "") + Math.abs(v).toFixed(2).replace(/^0/, "");
export const two = (v: number) => (v < 0 ? MINUS : "") + Math.abs(v).toFixed(2);
export const pct = (v: number) => (v > 0 && v < 0.1 ? "under 0.1%" : `${v.toFixed(1)}%`);
export const signedPct1 = (v: number) => (v < 0 ? MINUS : "") + Math.abs(v).toFixed(1) + "%";
export const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;

export const SIZE_WORD: Record<SizeCode, string> = { L: "Large cap", M: "Mid cap", S: "Small cap", U: "Size not known" };
export const SIZE_PLURAL: Record<SizeCode, string> = { L: "large caps", M: "mid caps", S: "small caps", U: "of unknown size" };
export const NOT_CLASSIFIED = /\(not classified\)$/;

/** Eight chart colours of the site's palette, then a hue walk, one per sector in the order sectors are first listed. */
const PALETTE = ["var(--k1)", "var(--k3)", "var(--k2)", "var(--k6)", "var(--k4)", "var(--k7)", "var(--k5)", "var(--k8)"];
export function sectorColors(sectors: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  [...new Set(sectors)].forEach((s, i) => { out[s] = i < PALETTE.length ? PALETTE[i] : `hsl(${(i * 47) % 360} 45% 48%)`; });
  return out;
}
/** Sectors in the order the page lists them: largest share of the list first (the mode's weights), ties by name. */
export function sectorOrder(page: PageObject, mode: Mode): string[] {
  const w = page.sector_weight[mode];
  const first = Object.keys(w);                                  // the server lists sectors in the order the list first names them: ties keep that order
  return first.map((k, i) => [k, i] as const).sort((a, b) => w[b[0]] - w[a[0]] || a[1] - b[1]).map((x) => x[0]);
}

/** 0 to 5: the grid's colour step of a correlation (the design's six steps). */
export const heatStep = (v: number) => (v < 0.05 ? 0 : v < 0.2 ? 1 : v < 0.35 ? 2 : v < 0.5 ? 3 : v < 0.65 ? 4 : 5);

/** The readings of one section for the chosen mode, highest priority first. `skip` drops rules shown elsewhere. */
export function readingsFor(page: PageObject, mode: Mode, section: Reading["section"], k = 99, skip: string[] = []): Reading[] {
  return page.readings.filter((x) => x.section === section && (x.mode === "both" || x.mode === mode) && !skip.includes(x.rule)).sort((a, b) => b.priority - a.priority).slice(0, k);
}
export const readingRule = (page: PageObject, rule: string, mode: Mode) => page.readings.find((x) => x.rule === rule && (x.mode === "both" || x.mode === mode));

/** "7 sectors · 9 large caps, 3 small caps, no mid caps" from the page's own counts (compact: "7 sectors · 9 large, 3 small"). */
export function sizeLine(page: PageObject, metas: Meta[], compact = false): string {
  const sectors = new Set(metas.map((m) => m.sector || "?")).size;
  const c = page.size_count;
  const word = (k: "L" | "M" | "S", n: number) => (compact ? SIZE_PLURAL[k].replace(/ caps?$/, "") : n === 1 ? SIZE_PLURAL[k].replace(/s$/, "") : SIZE_PLURAL[k]);
  const present = (["L", "M", "S"] as const).filter((k) => c[k]).map((k) => `${c[k]} ${word(k, c[k])}`);
  const absent = compact ? [] : (["L", "M", "S"] as const).filter((k) => !c[k]).map((k) => `no ${SIZE_PLURAL[k]}`);
  const bits = [...present, ...absent];
  if (c.U) bits.push(`${c.U} of unknown size`);
  return `${plural(sectors, "sector")} · ${bits.join(", ")}`;
}

/** Share of the list (percent) held by one cell of the sector and size table. */
export function cellShare(page: PageObject, mode: Mode, shares: string[]) {
  const w = page.share_weight[mode];
  return shares.reduce((a, s) => a + (w[s] ?? 0), 0);
}

/** Moves-with-the-rest sentence for the long layout: the three that move most on their own and the three that move most with the rest. */
export function restSentence(avg: Record<string, number>): string {
  const xs = Object.entries(avg).sort((a, b) => a[1] - b[1]);
  if (xs.length < 6) return "";
  const lo = xs.slice(0, 3), hi = xs.slice(-3).reverse();
  const list = (a: [string, number][]) => (a.length === 3 ? `${a[0][0]}, ${a[1][0]} and ${a[2][0]}` : "");
  return `${list(lo)} move most on their own (${two(lo[0][1])} to ${two(lo[2][1])}). ${list(hi)} move most with the rest (${two(hi[2][1])} to ${two(hi[0][1])}), so they add the least spread.`;
}

// ---------------------------------------------------------------- treemap (squarified, Bruls et al.)
export type Rect = { x: number; y: number; w: number; h: number };
export type Item<T> = { value: number; data: T };
function worst(row: number[], side: number) {
  const s = row.reduce((a, b) => a + b, 0), mx = Math.max(...row), mn = Math.min(...row);
  return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn));
}
/** Lay the items out in a rectangle (units of w x h) so each area is proportional to its value, items kept in the order given (largest first). */
export function squarify<T>(items: Item<T>[], box: Rect): (Rect & { data: T })[] {
  const live = items.filter((i) => i.value > 0);
  const total = live.reduce((a, i) => a + i.value, 0);
  if (!live.length || total <= 0 || box.w <= 0 || box.h <= 0) return [];
  const scale = (box.w * box.h) / total;
  const out: (Rect & { data: T })[] = [];
  let { x, y, w, h } = box, rest = live.map((i) => ({ area: i.value * scale, data: i.data }));
  while (rest.length) {
    const side = Math.min(w, h);
    let row = [rest[0]], k = 1;
    while (k < rest.length && worst([...row, rest[k]].map((r) => r.area), side) <= worst(row.map((r) => r.area), side)) { row.push(rest[k]); k++; }
    const sum = row.reduce((a, r) => a + r.area, 0);
    if (w >= h) { const cw = sum / h; let yy = y; row.forEach((r) => { const rh = r.area / cw; out.push({ x, y: yy, w: cw, h: rh, data: r.data }); yy += rh; }); x += cw; w -= cw; }
    else { const rh = sum / w; let xx = x; row.forEach((r) => { const rw = r.area / rh; out.push({ x: xx, y, w: rw, h: rh, data: r.data }); xx += rw; }); y += rh; h -= rh; }
    rest = rest.slice(row.length);
  }
  return out;
}

/** "30 Oct 2026" from an ISO date. */
export const dateText = (iso: string) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
