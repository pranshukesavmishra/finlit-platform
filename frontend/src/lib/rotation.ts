// Sector Rotation: the contract of GET /api/rotation and /api/rotation/{slug} (backend/finlit/sector_api.py, finlit_technicals/rotation.py), the hooks that read them and the pure
// helpers the Rotation tab, the industry card and the stock line share. Every number and every group name is the server's; nothing here is typed in from the design.
// The pages describe past prices against the average industry; they never advise, and every study figure is a past average, not a forecast.
import { useQuery } from "@tanstack/react-query";
import { ApiError, apiGet } from "./api";
import { MINUS } from "./format";
import type { CornerCode, Locked, PlanName, StateName, StateCode } from "./sectors";

export const CORNERS: CornerCode[] = ["ahead_gaining", "ahead_slowing", "behind_slipping", "behind_gaining"];
/** Where each corner sits on the map and in its 2x2 glyph: x = ahead (right) or behind (left) over 6 months, y = gaining (up) or slowing / slipping (down) over the last month. */
export const CORNER_POS: Record<string, { ahead: boolean; gaining: boolean }> = {
  ahead_gaining: { ahead: true, gaining: true }, ahead_slowing: { ahead: true, gaining: false }, behind_slipping: { ahead: false, gaining: false }, behind_gaining: { ahead: false, gaining: true },
};
export const CORNER_WORD: Record<string, string> = { ahead_gaining: "Ahead and gaining", ahead_slowing: "Ahead but slowing", behind_slipping: "Behind and slipping", behind_gaining: "Behind but gaining", middle: "Near the average" };

export type TailPoint = { date: string; strength: number; change: number; corner: CornerCode };
export type RankPoint = { date: string; rank: number | null; corner: CornerCode | null };
export type RotationRow = {
  name: string; slug: string; kind: "industry" | "sector"; sector: string | null; industries: string[];
  corner: CornerCode; corner_name: string; corner_since: string; weeks_in_corner: number; previous_corner: CornerCode | null; previous_corner_name: string | null;
  this_week_reading: CornerCode | null; this_week_reading_name: string | null;
  strength_pts: number | null; change_pts: number | null; vs_average: Record<string, number | null>;
  breadth_above_50: number | null; breadth: "broad" | "narrow" | "between" | null; breadth_name: string | null;
  sector_state: StateName | null; sector_state_code: StateCode | null;
  rank: number | null; ranked: number; score: number | null; rank_change_1w: number | null; rank_change_4w: number | null; rank_best_26w: number | null; rank_worst_26w: number | null;
  tail: TailPoint[]; rank_history: RankPoint[]; summary: string; leader_flags: number | null; stocks_counted: number;
};
export type CornerStudy = { name: string; cases: number; next_1m: number | null; next_3m: number | null; median_3m: number | null; beat_3m: number | null; next_6m: number | null };
export type RotationStudy = {
  period: { from: string; to: string; weeks: number; groups_per_week_median: number };
  corners: Record<string, CornerStudy>;
  spread_3m: { points: number | null; t: number | null; without_2020: number | null; since_2022: number | null; above_200d?: number | null; below_200d?: number | null };
  breadth: Record<string, { broad: { cases: number; mean: number | null; beat: number | null }; narrow: { cases: number; mean: number | null; beat: number | null } }>;
  moves: { median_weeks: number | null; mean_weeks: number | null; next_corner: Record<string, Record<string, number>> };
  rank: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  sector_indices?: { indices: number; benchmark: string; spread_3m: number | null; t: number | null; by_year_3m: Record<string, number | null> };
  text: Record<string, any> & { limits: string[] }; // eslint-disable-line @typescript-eslint/no-explicit-any
};
export type RotationMarket = { date: string; nifty50: number | null; nifty50_200d_average: number | null; pct_vs_200d: number | null; above_200d: boolean | null; average_label?: string; note: string | null };
export type RotationMap = {
  date: string; week_closed: boolean; groups: number; benchmark: string; average_industry: { return_1m: number | null; return_6m: number | null }; market: RotationMarket | null;
  counts: Record<string, number>; corner_meanings: Record<string, string>; rows: RotationRow[];
  moved_this_week: { name: string; slug: string; from: string; to: string }[];
  climbers_4w: { name: string; slug: string; rank: number; change: number }[]; fallers_4w: { name: string; slug: string; rank: number; change: number }[];
  rank_weeks: string[]; method: Record<string, string>; params: Record<string, any>; study: RotationStudy | null; disclaimer: string; locked?: Locked; plan?: PlanName; // eslint-disable-line @typescript-eslint/no-explicit-any
};
export type RotationCard = RotationRow & { reading: boolean; note?: string; study?: CornerStudy | null };

const retry = (n: number, e: unknown) => !(e instanceof ApiError && e.status < 500) && n < 1;
const STALE = 5 * 60_000;
export const useRotationMap = () => useQuery<RotationMap, ApiError>({ queryKey: ["rotation", "map"], queryFn: () => apiGet<RotationMap>("/api/rotation"), staleTime: STALE, retry });
export const useRotationCard = (slug: string, enabled = true) =>
  useQuery<RotationCard, ApiError>({ queryKey: ["rotation", "card", slug], queryFn: () => apiGet<RotationCard>(`/api/rotation/${encodeURIComponent(slug)}`), staleTime: STALE, retry, enabled: enabled && !!slug });

// ------------------------------------------------------------------------------------------------ words and numbers
export const pts = (v: number | null | undefined, d = 1): string => (v == null || !Number.isFinite(v) ? "—" : (v < 0 ? MINUS : v > 0 ? "+" : "") + Math.abs(v).toFixed(d));
export const ptsWord = (v: number | null | undefined, d = 1): string => (v == null ? "—" : `${pts(v, d)} pts`);
/** "▲3" / "▼3" / "–" (no move) / "new" (a group's first ranked week: the move is null). The arrow is always written, so colour is never the only signal. */
export function rankMove(v: number | null | undefined): { text: string; dir: "up" | "down" | "flat" | "new"; label: string; big: boolean } {
  if (v == null) return { text: "new", dir: "new", label: "new in the ranking this week", big: false };
  if (v === 0) return { text: "–", dir: "flat", label: "no change", big: false };
  const n = Math.abs(v);
  return { text: `${v > 0 ? "▲" : "▼"}${n}`, dir: v > 0 ? "up" : "down", label: `${v > 0 ? "up" : "down"} ${n} ${n === 1 ? "place" : "places"}`, big: n >= 3 };
}
export const weeksText = (n: number): string => `${n} ${n === 1 ? "week" : "weeks"}`;
export const cornerName = (c: string | null | undefined): string => (c ? CORNER_WORD[c] ?? c : "—");
export const shortDate = (iso: string): string => new Date(iso + "T00:00:00Z").toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
export const longDate = (iso: string): string => new Date(iso + "T00:00:00Z").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
export const monthYear = (iso: string): string => new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });

/** A group's name for the small rank grid; the full NSE name stays in the cell's title. */
export function shortName(name: string): string {
  return name.replace(/Pharmaceuticals & Biotechnology/, "Pharma & Biotech").replace(/Industrial Manufacturing/, "Industrial Mfg").replace(/Media Entertainment & Publication/, "Media & Entertainment")
    .replace(/Agricultural Commercial & Construction Vehicles/, "Agri & Construction Vehicles").replace(/Fast Moving Consumer Goods/, "FMCG").replace(/Fertilizers & Agrochemicals/, "Fertilizers & Agrochem").replace(/Electrical Equipment/, "Electrical Equip.");
}

// ------------------------------------------------------------------------------------------------ the study, in numbers taken from the file
/** Where groups went after leaving a corner, as the study measured it: the most common destination, and a second one when it is 20% or more. */
export function nextCorners(study: RotationStudy | null | undefined, c: CornerCode): { to: CornerCode; pct: number }[] {
  const m = study?.moves?.next_corner?.[c];
  if (!m) return [];
  const all = Object.entries(m).map(([to, pct]) => ({ to: to as CornerCode, pct })).sort((a, b) => b.pct - a.pct);
  return all.filter((x, i) => i === 0 || x.pct >= 20).slice(0, 2);
}
export function tileStudyLine(study: RotationStudy | null | undefined, c: CornerCode): string | null {
  const s = study?.corners?.[c];
  if (!s || s.next_3m == null) return null;
  return `Study, next 3 months: ${pts(s.next_3m)} pts${s.beat_3m != null ? `, ${Math.round(s.beat_3m)}% beat the average` : ""}.`;
}

// ------------------------------------------------------------------------------------------------ filters
export type CornerFilter = "all" | CornerCode;
export const asFilter = (v: string | null | undefined): CornerFilter => (CORNERS.includes(v as CornerCode) ? (v as CornerCode) : "all");
export const inCorner = (r: Pick<RotationRow, "corner">, f: CornerFilter): boolean => f === "all" || r.corner === f;
export const rowsByRank = (rows: RotationRow[]): RotationRow[] => [...rows].sort((a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9) || a.name.localeCompare(b.name));

// ------------------------------------------------------------------------------------------------ the map's geometry
export type MapDot = { slug: string; name: string; x: number; y: number; row: RotationRow; hollow: boolean; label: boolean; path: string; points: { x: number; y: number }[] };
export type MapGeo = { w: number; h: number; x: (v: number) => number; y: (v: number) => number; xTicks: number[]; yTicks: number[]; x0: number; y0: number; dots: MapDot[]; left: number; right: number; top: number; bottom: number };
const ticks = (lo: number, hi: number, step: number) => { const out: number[] = []; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v)); return out; };
/** Pixel positions for the map: x = strength, y = change, each axis fitted to its data and always holding 0.
 *  `weeks` tail points are drawn (4 or 8); `labelTop` limits the labels to that many groups by rank (null: every dot is labelled). */
export function mapGeometry(rows: RotationRow[], w: number, h: number, weeks: number, labelTop: number | null, pad = { left: 44, right: 16, top: 14, bottom: 34 }): MapGeo {
  const tails = (r: RotationRow) => r.tail.slice(-weeks);
  const xs: number[] = [0], ys: number[] = [0];
  for (const r of rows) { for (const p of tails(r)) { xs.push(p.strength); ys.push(p.change); } if (r.strength_pts != null) xs.push(r.strength_pts); if (r.change_pts != null) ys.push(r.change_pts); }
  const grow = (lo: number, hi: number) => { const span = Math.max(hi - lo, 10) * 0.06; return [lo - span, hi + span]; };
  const [xl, xh] = grow(Math.min(...xs), Math.max(...xs)), [yl, yh] = grow(Math.min(...ys), Math.max(...ys));
  const left = pad.left, right = w - pad.right, top = pad.top, bottom = h - pad.bottom;
  const x = (v: number) => left + ((v - xl) / (xh - xl)) * (right - left);
  const y = (v: number) => bottom - ((v - yl) / (yh - yl)) * (bottom - top);
  const stepOf = (span: number) => (span > 120 ? 40 : span > 60 ? 20 : span > 30 ? 10 : span > 14 ? 5 : 2);
  const labelled = new Set(rowsByRank(rows).slice(0, labelTop ?? rows.length).map((r) => r.slug));
  const dots = rows.map((r) => {
    const pts2 = tails(r).map((p) => ({ x: x(p.strength), y: y(p.change) }));
    const cx = x(r.strength_pts ?? 0), cy = y(r.change_pts ?? 0);
    const path = pts2.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join("") + (pts2.length ? `L${cx.toFixed(1)} ${cy.toFixed(1)}` : "");
    return { slug: r.slug, name: r.name, x: cx, y: cy, row: r, hollow: !!r.this_week_reading, label: labelled.has(r.slug), path, points: pts2 };
  });
  return { w, h, x, y, xTicks: ticks(xl, xh, stepOf(xh - xl)), yTicks: ticks(yl, yh, stepOf(yh - yl)), x0: x(0), y0: y(0), dots, left, right, top, bottom };
}

/** Places for the labels so that they do not stack on one another: right of the dot if that spot is free, else left, above or below (greedy, best rank first). */
export function placeLabels(dots: MapDot[], charW = 6.6, lineH = 14, w = 0): Record<string, { x: number; y: number; anchor: "start" | "end" }> {
  const taken: { x1: number; x2: number; y1: number; y2: number }[] = [];
  const out: Record<string, { x: number; y: number; anchor: "start" | "end" }> = {};
  const hit = (b: { x1: number; x2: number; y1: number; y2: number }) => taken.some((t) => b.x1 < t.x2 && b.x2 > t.x1 && b.y1 < t.y2 && b.y2 > t.y1);
  for (const d of [...dots].filter((q) => q.label).sort((a, b) => (a.row.rank ?? 99) - (b.row.rank ?? 99))) {
    const wd = shortName(d.name).length * charW;
    const tries: { x: number; y: number; anchor: "start" | "end" }[] = [
      { x: d.x + 9, y: d.y + 4, anchor: "start" }, { x: d.x - 9, y: d.y + 4, anchor: "end" }, { x: d.x + 9, y: d.y - 9, anchor: "start" }, { x: d.x + 9, y: d.y + 16, anchor: "start" },
      { x: d.x - 9, y: d.y - 9, anchor: "end" }, { x: d.x - 9, y: d.y + 16, anchor: "end" },
    ];
    let pick = tries[0];
    for (const t of tries) {
      const x1 = t.anchor === "start" ? t.x : t.x - wd;
      const b = { x1, x2: x1 + wd, y1: t.y - lineH + 3, y2: t.y + 3 };
      if (!hit(b) && (!w || (b.x1 >= 0 && b.x2 <= w))) { pick = t; break; }
    }
    const x1 = pick.anchor === "start" ? pick.x : pick.x - wd;
    taken.push({ x1, x2: x1 + wd, y1: pick.y - lineH + 3, y2: pick.y + 3 });
    out[d.slug] = pick;
  }
  return out;
}

// ------------------------------------------------------------------------------------------------ the rank grid and sparklines
/** The last `n` weekly closes of each group's rank, in today's rank order: rows[i].cells[j] is the rank at weeks[j] (null: not ranked that week). */
export function rankGrid(rows: RotationRow[], n = 12): { weeks: string[]; rows: { row: RotationRow; cells: (number | null)[] }[] } {
  const ordered = rowsByRank(rows);
  const weeks = (ordered.find((r) => r.rank_history.length >= n) ?? ordered[0])?.rank_history.slice(-n).map((p) => p.date) ?? [];
  return { weeks, rows: ordered.map((row) => { const byDate = new Map(row.rank_history.map((p) => [p.date, p.rank])); return { row, cells: weeks.map((d) => byDate.get(d) ?? null) }; }) };
}
/** Shade bucket 1 (the top fifth of ranks) to 5 from a rank among `ranked`; 0 when the group was not ranked that week. */
export const shade = (rank: number | null, ranked: number): 0 | 1 | 2 | 3 | 4 | 5 => (rank == null || !ranked ? 0 : (Math.min(5, Math.max(1, Math.ceil((rank / ranked) * 5))) as 1 | 2 | 3 | 4 | 5));
/** A polyline for a rank history: rank 1 at the top, the worst rank at the bottom; a week with no rank breaks the line. */
export function sparkPath(hist: { rank: number | null }[], w: number, h: number, worst: number, pad = 2): string {
  const n = hist.length;
  if (!n) return "";
  let s = "", pen = false;
  hist.forEach((p, i) => {
    if (p.rank == null) { pen = false; return; }
    const x = pad + (n > 1 ? (i / (n - 1)) * (w - 2 * pad) : 0), y = pad + ((p.rank - 1) / Math.max(1, worst - 1)) * (h - 2 * pad);
    s += `${pen ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
    pen = true;
  });
  return s;
}

export function failureText(e: unknown): string {
  if (e instanceof ApiError) {
    const b = e.body as { reason?: string; detail?: string };
    if (b?.reason) return b.reason;
    if (e.status === 404) return "There is no rotation reading for this address.";
    if (e.status >= 500) return b?.detail || "The rotation data could not be read just now. Please try again in a moment.";
    return e.message;
  }
  return "The rotation data could not be loaded. Please check your connection and try again.";
}
