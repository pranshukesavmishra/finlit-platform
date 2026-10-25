// FinLit Prism charts: score ring, category bars, annual trends and growth. Plain SVG in the house style (see stock/Leadership.tsx):
// every chart states its conclusion in its aria-label and can be shown as a table. Colours come from prism.css tokens.
import { useEffect, useMemo, useRef, useState } from "react";
import { MINUS, nf } from "../../lib/format";
import {
  GROWTH_METRICS, buildFundamentalGrowth, growthPercent, growthSentence, isRated, labelTone, partInfo, partShare, partsOf,
  partsSentence, pctWhole, ringSentence, score1, trendRows, trendSentence, type GrowthKey, type PrismRating, type Trend,
} from "../../lib/prism";

export function useWidth<T extends HTMLElement>(initial = 640): [(el: T | null) => void, number] {
  const [w, setW] = useState(initial);
  const ro = useRef<ResizeObserver | null>(null);
  const ref = (el: T | null) => {
    ro.current?.disconnect();
    if (!el) return;
    setW(Math.max(240, Math.round(el.getBoundingClientRect().width) || initial));
    if (typeof ResizeObserver === "undefined") return;
    ro.current = new ResizeObserver(([e]) => setW(Math.max(240, Math.round(e.contentRect.width))));
    ro.current.observe(el);
  };
  useEffect(() => () => ro.current?.disconnect(), []);
  return [ref, w];
}

export function ShowTable({ on, set }: { on: boolean; set: (b: boolean) => void }) {
  return <button type="button" className="pz-link" aria-expanded={on} onClick={() => set(!on)}>{on ? "Hide table" : "Show as table"}</button>;
}
export function ChartTable({ caption, head, rows }: { caption: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="pz-ctable"><table><caption>{caption}</caption><thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => (j === 0 ? <th scope="row" key={j}>{c}</th> : <td key={j}>{c}</td>))}</tr>)}</tbody></table></div>
  );
}

/* ---- the headline ring: score out of 100 in the label's colour; the label and status are always written beside it */
export function PrismScoreRing({ rating, size = 168 }: { rating: Pick<PrismRating, "status" | "final" | "label">; size?: number }) {
  const rated = isRated(rating) && rating.final != null;
  const r = size / 2 - 10, c = 2 * Math.PI * r, f = rated ? Math.max(0, Math.min(100, rating.final!)) / 100 : 0;
  const t = labelTone(rating.label);
  return (
    <svg className={"pz-ring " + t.tone} width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={ringSentence(rating)}>
      <circle cx={size / 2} cy={size / 2} r={r} className="pz-ring-track" />
      {rated && <circle cx={size / 2} cy={size / 2} r={r} className="pz-ring-arc" strokeDasharray={`${(c * f).toFixed(1)} ${c.toFixed(1)}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />}
      {[0.35, 0.5, 0.65, 0.8].map((b) => { const a = -Math.PI / 2 + b * 2 * Math.PI; return <line key={b} className="pz-ring-tick" x1={size / 2 + (r - 7) * Math.cos(a)} y1={size / 2 + (r - 7) * Math.sin(a)} x2={size / 2 + (r + 7) * Math.cos(a)} y2={size / 2 + (r + 7) * Math.sin(a)} />; })}
      {rated ? <>
        <text x="50%" y={size / 2 + 4} textAnchor="middle" className="pz-ring-n">{score1(rating.final)}</text>
        <text x="50%" y={size / 2 + 26} textAnchor="middle" className="pz-ring-u">out of 100</text>
      </> : <>
        <text x="50%" y={size / 2 - 2} textAnchor="middle" className="pz-ring-nr">Not rated</text>
        <text x="50%" y={size / 2 + 18} textAnchor="middle" className="pz-ring-u">not enough evidence</text>
      </>}
    </svg>
  );
}

/* ---- the four parts as bars, with their share of the overall score and their coverage */
export function PrismPartBars({ rating }: { rating: PrismRating }) {
  const [table, setTable] = useState(false);
  const rated = isRated(rating);
  const concl = partsSentence(rating);
  return (
    <div className="pz-bars-w">
      <div className="pz-bars" role="img" aria-label={concl}>
        {partsOf(rating).map((k) => {
          const v = rated ? rating.parts[k] : null;
          return (
            <div className="pz-bar-row" key={k} aria-hidden="true">
              <span className="pz-bar-n">{partInfo(k).name}<small>{partShare(rating.partWeights, k)}% of the score</small></span>
              <span className="pz-bar-t"><i style={{ width: `${v ?? 0}%` }} />{[35, 50, 65, 80].map((b) => <u key={b} style={{ left: `${b}%` }} />)}</span>
              <b>{rated ? score1(v) : "—"}</b>
            </div>
          );
        })}
      </div>
      <div className="pz-cfoot"><span className="pz-sm">Ticks mark 35, 50, 65 and 80, the score bands for Weak, Average, Healthy and Strong.</span><ShowTable on={table} set={setTable} /></div>
      {table && <ChartTable caption={concl} head={["Part", "Share of the score", "Score / 100", "Data coverage"]}
        rows={partsOf(rating).map((k) => [partInfo(k).name, `${partShare(rating.partWeights, k)}%`, rated ? score1(rating.parts[k]) : "Not rated", pctWhole(rating.coverage[k])])} />}
    </div>
  );
}

/* ---- annual results: three small charts on their own scales (amounts never share an axis with EPS), as in the PDF */
const path = (pts: ([number, number] | null)[]) => { let d = "", pen = false; pts.forEach((p) => { if (!p) { pen = false; return; } d += (pen ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); pen = true; }); return d; };
const short = (v: number, eps: boolean) => (eps ? (v < 0 ? MINUS : "") + nf(v, 1) : (v < 0 ? MINUS : "") + (Math.abs(v) >= 100000 ? nf(v / 100000, 1) + "L" : nf(v, 0)));

function MiniTrend({ title, unit, trends, k }: { title: string; unit: string; trends: Trend[]; k: "revenue" | "profit" | "eps" }) {
  const [box, W] = useWidth<HTMLDivElement>(300);
  const H = 150, M = { t: 18, r: 14, b: 24, l: 14 };
  const vals = trends.map((t) => t[k]).filter((v): v is number => v != null);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), span = hi - lo || 1;
  const iw = W - M.l - M.r, ih = H - M.t - M.b;
  const X = (i: number) => M.l + (trends.length > 1 ? (i / (trends.length - 1)) * iw : iw / 2);
  const Y = (v: number) => M.t + (1 - (v - lo) / span) * ih;
  const pts = trends.map((t, i) => (t[k] == null ? null : ([X(i), Y(t[k]!)] as [number, number])));
  const concl = trendSentence(title, trends, k);
  const last = [...trends].reverse().find((t) => t[k] != null);
  return (
    <div className={"pz-mini " + k}>
      <div className="pz-mini-h"><b>{title}</b><span>{last ? `${short(last[k]!, k === "eps")} ${unit} · ${last.period}` : "No data"}</span></div>
      <div ref={box} className="pz-chart">
        {vals.length < 2 ? <p className="pz-empty">Not enough reported years for a trend.</p> : (
          <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={concl}>
            {lo < 0 && <line x1={M.l} x2={M.l + iw} y1={Y(0)} y2={Y(0)} className="pz-zero" />}
            <line x1={M.l} x2={M.l + iw} y1={M.t + ih} y2={M.t + ih} className="pz-grid" />
            <path d={path(pts)} className="pz-ln" />
            {pts.map((p, i) => p && <circle key={i} cx={p[0]} cy={p[1]} r={i === pts.length - 1 ? 4 : 3} className="pz-pt" />)}
            {pts.map((p, i) => p && (i === 0 || i === pts.length - 1) && <text key={"v" + i} x={p[0]} y={p[1] - 8} textAnchor={i === 0 ? "start" : "end"} className="pz-val">{short(trends[i][k]!, k === "eps")}</text>)}
            {trends.map((t, i) => (i === 0 || i === trends.length - 1 || W > 360) && <text key={t.period} x={X(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === trends.length - 1 ? "end" : "middle"} className="pz-ax">{W > 360 || i === 0 || i === trends.length - 1 ? t.period : ""}</text>)}
          </svg>
        )}
      </div>
    </div>
  );
}

export function TrendCharts({ trends, income, unit = "year" }: { trends: Trend[]; income: string; unit?: "year" | "quarter" }) {
  const [table, setTable] = useState(false);
  const concl = [trendSentence(income, trends, "revenue"), trendSentence("Net profit", trends, "profit"), trendSentence("EPS", trends, "eps")].join(" ");
  const cell = (v: number | null, d = 2) => (v == null ? "—" : (v < 0 ? MINUS : "") + nf(v, d));
  return (
    <>
      <div className="pz-minis">
        <MiniTrend title={income} unit="₹ Cr" trends={trends} k="revenue" />
        <MiniTrend title="Net profit" unit="₹ Cr" trends={trends} k="profit" />
        <MiniTrend title="EPS" unit="₹ / share" trends={trends} k="eps" />
      </div>
      <div className="pz-cfoot"><span className="pz-sm">{unit === "year" ? "Financial years" : "Quarters"}, oldest to newest. Each chart has its own scale. Missing years are left as gaps.</span><ShowTable on={table} set={setTable} /></div>
      {table && <ChartTable caption={concl} head={[unit === "year" ? "Financial year" : "Quarter", `${income} (₹ Cr)`, "Net profit (₹ Cr)", "EPS (₹)"]} rows={trends.map((t) => [t.period, cell(t.revenue), cell(t.profit), cell(t.eps)])} />}
    </>
  );
}

/* ---- growth against the previous year (port of upstream IncomeGrowthView): latest figures, then the lines with a zero baseline */
export function GrowthView({ trends, income }: { trends: Trend[]; income: string }) {
  const data = useMemo(() => buildFundamentalGrowth(trendRows(trends), "yearly", "yoy"), [trends]);
  const [table, setTable] = useState(false);
  const [box, W] = useWidth<HTMLDivElement>();
  const latest = data[data.length - 1];
  const label = (k: GrowthKey, l: string) => (k === "revenue" ? `${income} growth` : l);
  const has = data.some((p) => GROWTH_METRICS.some((m) => p[m.key] != null));
  const concl = growthSentence(data, income);
  const H = W < 480 ? 210 : 250, M = { t: 14, r: 12, b: 26, l: 46 };
  const vals = data.flatMap((p) => GROWTH_METRICS.map((m) => p[m.key]).filter((v): v is number => v != null)).concat(0);
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = Math.max(2, (hi - lo) * 0.1), y0 = lo - pad, y1 = hi + pad;
  const iw = W - M.l - M.r, ih = H - M.t - M.b;
  const X = (i: number) => M.l + (data.length > 1 ? (i / (data.length - 1)) * iw : iw / 2);
  const Y = (v: number) => M.t + (1 - (v - y0) / (y1 - y0)) * ih;
  const ticks = [0, 1, 2, 3, 4].map((i) => y0 + ((y1 - y0) * i) / 4);
  return (
    <div className="pz-growth">
      <div className="pz-gtiles">
        {GROWTH_METRICS.map((m) => {
          const v = latest?.[m.key] ?? null, why = latest?.[`${m.key}Detail`]?.reason;
          return <div key={m.key} className={"pz-gtile " + m.key}><small>{label(m.key, m.label)}</small><b className={v == null ? "" : v < 0 ? "neg" : "pos"}>{latest ? growthPercent(v) : "N/A"}</b><span>{latest ? latest.period : "No history"}{why ? ` · ${why.toLowerCase()}` : ""}</span></div>;
        })}
      </div>
      <div ref={box} className="pz-chart">
        {!has ? <p className="pz-empty">Not enough comparable data to plot growth.</p> : (
          <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={concl}>
            {ticks.map((t, i) => <g key={i}><line x1={M.l} x2={M.l + iw} y1={Y(t)} y2={Y(t)} className="pz-grid" /><text x={M.l - 6} y={Y(t) + 4} textAnchor="end" className="pz-ax">{Math.round(t)}%</text></g>)}
            <line x1={M.l} x2={M.l + iw} y1={Y(0)} y2={Y(0)} className="pz-zero" />
            {GROWTH_METRICS.map((m) => <path key={m.key} d={path(data.map((p, i) => (p[m.key] == null ? null : [X(i), Y(p[m.key]!)])))} className={"pz-gl " + m.key} />)}
            {GROWTH_METRICS.map((m) => data.map((p, i) => p[m.key] != null && <circle key={m.key + i} cx={X(i)} cy={Y(p[m.key]!)} r="3" className={"pz-gd " + m.key} />))}
            {data.map((p, i) => <text key={p.period} x={X(i)} y={H - 6} textAnchor="middle" className="pz-ax">{W < 420 ? p.period.slice(2) : p.period}</text>)}
          </svg>
        )}
      </div>
      <div className="pz-cfoot">
        <span className="pz-keys">{GROWTH_METRICS.map((m) => <span key={m.key} className={"pz-key " + m.key}><i aria-hidden="true" />{label(m.key, m.label)}</span>)}</span>
        {has && <ShowTable on={table} set={setTable} />}
      </div>
      {table && <ChartTable caption={concl} head={["Financial year", ...GROWTH_METRICS.map((m) => label(m.key, m.label))]} rows={data.map((p) => [p.period, ...GROWTH_METRICS.map((m) => growthPercent(p[m.key]))])} />}
      <p className="pz-sm">Growth = (current − previous year) ÷ previous year × 100. N/M means the value or the comparison year is missing, or the comparison is zero or negative. Gaps are kept.</p>
    </div>
  );
}

/** Stable names for other pages (the stock page comparison). */
export { PrismScoreRing as ScoreRing, PrismPartBars as PartBars };
