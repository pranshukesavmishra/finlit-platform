// The 2017-2026 study, in words, built only from the board's `study.figures` (finlit_technicals/data/sector_study.json, shipped with every board).
// Each builder returns null when the figures it needs are missing, so a page leaves the card out (with its reason) instead of printing a made-up number.
// Every sentence describes past averages; none is a forecast.
import { MINUS } from "./format";
import type { StudyFigures } from "./sectors";

const pts = (v: number | null | undefined, d = 1): string => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? MINUS : "") + Math.abs(v).toFixed(d));
const p0 = (v: number | null | undefined): string => (v == null ? "—" : `${Math.round(v)}%`);
const n0 = (v: number | null | undefined): string => (v == null ? "—" : new Intl.NumberFormat("en-IN").format(v));
const has = (o: unknown, ...keys: string[]): boolean => !!o && typeof o === "object" && keys.every((k) => (o as Record<string, unknown>)[k] != null);

export type StudyCard = { key: string; title: string; cases: number | null; text: string };

/** The four cards of the industry page's study box. */
export function studyCards(f: StudyFigures | undefined | null): StudyCard[] {
  if (!f) return [];
  const out: StudyCard[] = [];
  const C = f.C, CAP = f.CAP, Cw = f.C_week_avg, CAPw = f.CAP_week_avg;
  if (has(C, "cases", "win_pct", "edge_pts")) {
    out.push({ key: "C", title: "C thrust", cases: C.cases, text: `The industry index rose 15% before it fell 8% in ${p0(C.win_pct)} of cases, and did ${pts(C.edge_pts)} points better than the same industry usually does over 60 sessions.`
      + (has(Cw, "weeks", "edge_pts") ? ` Cases bunched in the same weeks: averaged week by week (${n0(Cw.weeks)} weeks), the difference was ${pts(Cw.edge_pts)}.` : "") });
  }
  if (has(CAP, "cases", "win_pct", "edge_pts")) {
    out.push({ key: "CAP", title: "CAP thrust", cases: CAP.cases, text: `${p0(CAP.win_pct)} rose 15% first, and ${pts(CAP.edge_pts)} points against usual.`
      + (has(CAP, "edge_ex2020_pts") ? ` Without the 2020 crash and rebound: ${pts(CAP.edge_ex2020_pts)} points.` : "") + (has(CAPw, "weeks", "edge_pts") ? ` Averaged week by week (${n0(CAPw.weeks)} weeks): ${pts(CAPw.edge_pts)}.` : "") });
  }
  const cb = f.C_below_200d, pb = f.CAP_below_200d, ca = f.C_above_200d, pa = f.CAP_above_200d;
  if (has(cb, "edge_pts") && has(pb, "edge_pts", "win_pct", "cases", "weeks") && has(ca, "edge_pts") && has(pa, "edge_pts")) {
    out.push({ key: "market", title: "Market context", cases: null, text: `With the Nifty 50 below its 200-day average, CAP thrusts were followed by ${pts(pb.edge_pts)} points and ${p0(pb.win_pct)} rose 15% first (${n0(pb.cases)} cases in ${n0(pb.weeks)} weeks); C thrusts by ${pts(cb.edge_pts)}. `
      + `Above it: ${pts(pa.edge_pts)} and ${pts(ca.edge_pts)}. Examined after seeing the results.` });
  }
  const cf = f.Confirmed;
  if (has(cf, "cases", "edge_pts")) {
    out.push({ key: "Confirmed", title: "Confirmed", cases: cf.cases, text: `${cf.median_sessions_after_low != null ? `Came a median ${n0(cf.median_sessions_after_low)} sessions after the industry's low: ` : ""}${pts(cf.edge_pts)} points, close to an ordinary period. It describes a trend already under way.` });
  }
  return out;
}

export type StudyRow = { signal: string; cases: number | null; text: string };
/** The table on the Learn page: one row per signal. */
export function studyRows(f: StudyFigures | undefined | null): StudyRow[] {
  if (!f) return [];
  const rows: StudyRow[] = [];
  const C = f.C, CAP = f.CAP;
  if (has(C, "cases", "win_pct", "edge_pts")) rows.push({ signal: "Thrust C", cases: C.cases, text: `In ${p0(C.win_pct)} of cases the industry index rose 15% before it fell 8%. Over 60 sessions it did ${pts(C.edge_pts)} points better than the same industry usually does.${has(f.C_week_avg, "weeks", "edge_pts") ? ` Averaged week by week (${n0(f.C_week_avg.weeks)} weeks): ${pts(f.C_week_avg.edge_pts)}.` : ""}` });
  if (has(CAP, "cases", "win_pct", "edge_pts")) rows.push({ signal: "Thrust CAP", cases: CAP.cases, text: `${p0(CAP.win_pct)} rose 15% first; ${pts(CAP.edge_pts)} points against usual${has(CAP, "edge_ex2020_pts") ? `, but ${pts(CAP.edge_ex2020_pts)} without the 2020 crash and rebound` : ""}.${has(f.CAP_week_avg, "weeks", "edge_pts") ? ` Averaged week by week (${n0(f.CAP_week_avg.weeks)} weeks): ${pts(f.CAP_week_avg.edge_pts)}.` : ""}` });
  const b = f.thrust_below_200d_ex2020;
  if (has(f.C_below_200d, "edge_pts") && has(f.CAP_below_200d, "edge_pts", "win_pct", "cases", "weeks")) rows.push({ signal: "Thrust, Nifty below 200-day", cases: f.filter_n50_above200?.False?.n ?? null,
    text: `C ${pts(f.C_below_200d.edge_pts)} points (${p0(f.C_below_200d.win_pct)} rose 15% first; ${n0(f.C_below_200d.cases)} cases in ${n0(f.C_below_200d.weeks)} weeks). CAP ${pts(f.CAP_below_200d.edge_pts)} points (${p0(f.CAP_below_200d.win_pct)}; ${n0(f.CAP_below_200d.cases)} cases in ${n0(f.CAP_below_200d.weeks)} weeks).${has(b, "edge_pts", "win_pct", "cases", "weeks") ? ` Without 2020: ${pts(b.edge_pts)} points, ${p0(b.win_pct)} (${n0(b.cases)} cases in ${n0(b.weeks)} weeks).` : ""}` });
  if (has(f.C_above_200d, "edge_pts") && has(f.CAP_above_200d, "edge_pts")) rows.push({ signal: "Thrust, Nifty above 200-day", cases: f.filter_n50_above200?.True?.n ?? null,
    text: `C ${pts(f.C_above_200d.edge_pts)} points (${p0(f.C_above_200d.win_pct)} rose 15% first). CAP ${pts(f.CAP_above_200d.edge_pts)} points (${p0(f.CAP_above_200d.win_pct)}).` });
  const r = f.rallies;
  if (has(r, "count", "caught")) rows.push({ signal: "Big rallies", cases: r.count, text: `An industry index rising 25% or more within 120 sessions of a 60-session low. A C or CAP thrust came within 20 sessions of the low in ${n0(r.caught)} of them (${p0((r.caught / r.count) * 100)})${r.median_lag != null ? `, typically ${n0(r.median_lag)} sessions after it` : ""}.` });
  const cf = f.Confirmed;
  if (has(cf, "cases", "edge_pts")) rows.push({ signal: "Confirmed", cases: cf.cases, text: `${cf.median_sessions_after_low != null ? `Came a median ${n0(cf.median_sessions_after_low)} sessions after the low: ` : ""}${pts(cf.edge_pts)} points, close to an ordinary period. It describes a trend already under way.` });
  const fd = f.Fading;
  if (has(fd, "cases", "edge_pts")) rows.push({ signal: "Fading", cases: fd.cases, text: `${pts(fd.edge_pts)} points: no different from an ordinary period. It describes breadth that has weakened; it is not a tested signal.` });
  const t2 = f.flags_tier2, t1 = f.flags_tier1, rm = f.flag_random_member;
  if (has(t2, "cases", "mean_pct", "median_pct", "beat_pct")) rows.push({ signal: "Leader flag, 15%+", cases: t2.cases, text: `${pts(t2.mean_pct)}% against its industry over 120 sessions on average (median ${pts(t2.median_pct)}%; ${p0(t2.beat_pct)} beat it).${has(rm, "mean_pct", "beat_pct") ? ` An average stock of the same industry on the same days: ${pts(rm.mean_pct)}% (${p0(rm.beat_pct)}).` : ""}${has(t2, "mean_2020_pct") ? ` In 2020 flagged stocks did ${pts(t2.mean_2020_pct)}%.` : ""}` });
  if (has(t1, "cases", "mean_pct", "median_pct", "beat_pct")) rows.push({ signal: "Leader flag, 10–15%", cases: t1.cases, text: `${pts(t1.mean_pct)}% on average, median ${pts(t1.median_pct)}%, ${p0(t1.beat_pct)} beat their industry. No difference from an ordinary stock.` });
  const qc = f.quarters_C;
  if (qc && qc["1"] && qc["4"]) rows.push({ signal: "6-month quarter at a C thrust", cases: Object.values(qc as Record<string, { n: number }>).reduce((s, q) => s + (q.n ?? 0), 0), text: `Stock cases. The top quarter did ${pts(qc["1"].mean_pts)} points against its industry over 60 sessions and the bottom quarter ${pts(qc["4"].mean_pts)} points, but the median stock in every quarter trailed the industry index. After a CAP thrust there was no clear order.` });
  const ba = f.bottom_any;
  if (ba && ba["1"]) rows.push({ signal: "Bottomed before the industry", cases: Object.values(ba as Record<string, { n: number }>).reduce((s, q) => s + (q.n ?? 0), 0), text: `Stock cases at thrusts. No meaningful difference: ${pts(ba["1"].mean_pts)} points for stocks that bottomed first and were above their 20-day average; ${ba["2"] ? pts(ba["2"].mean_pts) : "—"} to ${ba["3"] ? pts(ba["3"].mean_pts) : "—"} for the others.` });
  return rows;
}

/** "The main finding": the market mattered more than the thrust. */
export function mainFinding(f: StudyFigures | undefined | null): string | null {
  const b = f?.thrust_below_200d_ex2020, above = f?.filter_n50_above200?.True?.edge_pts;
  if (!has(b, "edge_pts", "win_pct", "cases", "weeks") || above == null) return null;
  return `Averaged over every case, thrusts were followed by industry returns only slightly better than usual, and averaged week by week the difference was about zero. The difference came from the market around them. `
    + `Thrusts while the Nifty 50 was below its 200-day average were followed by ${pts(b.edge_pts)} points over 60 sessions even without 2020, and ${p0(b.win_pct)} rose 15% before falling 8% (${n0(b.cases)} cases in ${n0(b.weeks)} separate weeks). `
    + `Thrusts while it was above were followed by ${pts(above)} points.`;
}
