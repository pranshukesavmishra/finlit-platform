import { useEffect, useRef, useState } from "react";
import { Icon } from "../lib/icons";
import { labelEvery } from "../lib/chartAxis";
import { cr, nf, num, signed } from "../lib/format";
import type { Segments } from "../lib/api";
import {
  axisCr, axisPct, cagrText, chartModel, chartSummary, mixStatus, niceTicks, pp, sortRows, stackTop, tableRows,
  type ChartModel, type SortKey, type TableRow,
} from "../lib/segmentMix";

type Mode = "revenue" | "share";
const rs = (n: number | null | undefined) => (n == null ? "—" : "₹" + cr(n) + " Cr");
const cls = (n: number | null | undefined) => (n == null || Math.abs(n) < 0.05 ? "" : n > 0 ? "pos" : "neg");

/** Stacked bars by fiscal year in plain SVG. Drawn at the real pixel width so the text keeps its size on a phone; hover or focus a year to read it. */
function MixChart({ model, mode }: { model: ChartModel; mode: Mode }) {
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(640);
  const [hv, setHv] = useState<number | null>(null);
  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const n = model.years.length, H = w < 480 ? 250 : 290, pl = mode === "revenue" ? 44 : 40, pr = 8, pt = 10, pb = 26;
  const top = Math.max(...model.years.map((_, i) => stackTop(model, i, mode)), 0);
  const ticks = mode === "share" ? niceTicks(Math.max(100, top), 4) : niceTicks(top, 4);
  const max = ticks[ticks.length - 1] || 1;
  const slot = (w - pl - pr) / Math.max(n, 1), bw = Math.min(46, slot * 0.64);
  const X = (i: number) => pl + (i + 0.5) * slot, Y = (v: number) => pt + (1 - v / max) * (H - pt - pb);
  // Every year gets a label: the full "FY26" when they all fit, otherwise "'26". (labelEvery is the shared fit test; it is never used to skip a year.)
  const label = (y: string) => (labelEvery(n, w - pl - pr, 4) === 1 ? y : "’" + y.slice(2));
  const fmt = mode === "revenue" ? axisCr : axisPct;
  return (
    <div className="mx-chart" ref={box} onMouseLeave={() => setHv(null)}>
      <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} role="img" aria-label={chartSummary(model)}>
        {ticks.map((t) => <g key={t}><line x1={pl} x2={w - pr} y1={Y(t)} y2={Y(t)} stroke="var(--border)" strokeWidth={t === 0 ? 1.2 : 1} /><text x={pl - 6} y={Y(t) + 3.5} textAnchor="end" fontSize="10" fill="var(--faint)" fontFamily="IBM Plex Mono, monospace">{fmt(t)}</text></g>)}
        {model.years.map((y, i) => {
          let acc = 0;
          return (
            <g key={y} opacity={hv == null || hv === i ? 1 : 0.4} style={{ transition: "opacity .15s" }}>
              {model.series.map((s) => {
                const v = Math.max(0, (mode === "revenue" ? s.values[i] : s.shares[i]) ?? 0);
                if (!v) return null;
                const y1 = Y(acc), y0 = Y(acc + v);
                acc += v;
                return <rect key={s.key} x={X(i) - bw / 2} y={y0} width={bw} height={Math.max(1, y1 - y0)} fill={s.color} stroke="var(--s1)" strokeWidth={1} rx={1.5} />;
              })}
              <rect x={X(i) - slot / 2} y={pt} width={slot} height={H - pt - pb} fill="transparent" tabIndex={0} style={{ outline: "none" }}
                onMouseEnter={() => setHv(i)} onFocus={() => setHv(i)} onBlur={() => setHv(null)}
                onKeyDown={(e) => { if (e.key === "Escape") setHv(null); }}
                aria-label={`${y}: ${model.series.filter((s) => s.values[i] != null).map((s) => `${s.label} ${rs(s.values[i])}, ${s.shares[i] == null ? "—" : nf(s.shares[i] as number, 1) + "%"}`).join("; ")}`} />
              <text x={X(i)} y={H - 8} textAnchor="middle" fontSize="10.5" fill="var(--faint)">{label(y)}</text>
            </g>
          );
        })}
        {hv != null && <rect x={X(hv) - slot / 2} y={pt} width={slot} height={H - pt - pb} fill="none" stroke="var(--border-strong)" strokeDasharray="3 3" pointerEvents="none" />}
      </svg>
      {hv != null && (
        <div className="mb-tip mx-tip" role="status" style={{ left: `${Math.min(Math.max((X(hv) / w) * 100, 20), 80)}%` }}>
          <b>{model.years[hv]} · segment revenue {rs(model.totals[hv])}</b>
          {model.series.filter((s) => s.values[hv] != null).map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}<em>{rs(s.values[hv])} · {s.shares[hv] == null ? "—" : nf(s.shares[hv] as number, 1) + "%"}</em></span>)}
        </div>
      )}
    </div>
  );
}

function Spark({ values, color }: { values: (number | null)[]; color: string }) {
  const pts = values.map((v, i) => [i, v] as const).filter((p): p is readonly [number, number] => p[1] != null);
  if (pts.length < 2) return <span className="faint">—</span>;
  const hi = Math.max(...pts.map((p) => p[1])), lo = Math.min(...pts.map((p) => p[1])), W = 74, H = 22, span = hi - lo || 1, nx = Math.max(values.length - 1, 1);
  const X = (i: number) => 2 + (i / nx) * (W - 4), Y = (v: number) => 3 + (1 - (v - lo) / span) * (H - 6);
  // draw each unbroken run as its own line so a gap in the data stays a gap
  const runs: (readonly [number, number])[][] = [];
  values.forEach((v, i) => { if (v == null) { runs.push([]); } else { if (!runs.length) runs.push([]); runs[runs.length - 1].push([i, v]); } });
  const lastPt = pts[pts.length - 1];
  return (
    <svg className="mx-spark" width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      {runs.filter((r) => r.length > 1).map((r, k) => <polyline key={k} points={r.map(([i, v]) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ")} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />)}
      <circle cx={X(lastPt[0])} cy={Y(lastPt[1])} r="2.2" fill={color} />
    </svg>
  );
}

const TAG_CLASS: Record<string, string> = { growing: "up", declining: "down", steady: "ghost", new: "info", discontinued: "ghost", short: "ghost" };

function TrendTable({ rows, latest, sort, setSort }: { rows: TableRow[]; latest: string; sort: SortKey; setSort: (k: SortKey) => void }) {
  const sorted = sortRows(rows, sort);
  const th = (k: SortKey, text: string) => <th scope="col" aria-sort={sort === k ? "descending" : undefined}><button type="button" className={"mx-sort" + (sort === k ? " on" : "")} aria-pressed={sort === k} onClick={() => setSort(sort === k ? "default" : k)} title={`Sort by ${text.toLowerCase()}`}>{text}<span aria-hidden="true">{sort === k ? " ↓" : ""}</span></button></th>;
  return (
    <div className="mx-tw">
      <table className="mx-t">
        <thead><tr>
          <th scope="col">Segment</th><th scope="col">Revenue {latest}</th>
          {th("share", "Share now")}<th scope="col">Share change</th>
          {th("growth", "Growth a year")}<th scope="col">Last year</th><th scope="col">Margin</th><th scope="col">Trend</th><th scope="col"><span className="sr-only">Revenue history</span></th>
        </tr></thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.name} className={r.notReported ? "gone" : ""} style={{ "--bc": r.color } as React.CSSProperties}>
              <th scope="row" data-l="Segment"><i className="mx-dot" aria-hidden="true" /><span>{r.name}</span>{r.flag && <small className="mx-fl" title={r.flag}><Icon name="alert" /> Definition may have changed</small>}</th>
              {r.notReported ? (
                <td className="mx-gone" colSpan={7} data-l=""><span className="chip ghost">{r.trendLabel || "Discontinued / merged"}</span> Not reported in {latest}{r.lastReported ? `. Last reported in ${r.lastReported}${r.lastRevenue != null ? ` (${rs(r.lastRevenue)})` : ""}` : ""}.</td>
              ) : (<>
                <td data-l={`Revenue ${latest}`}>{rs(r.revenue)}</td>
                <td data-l="Share now">{r.sharePct == null ? "—" : nf(r.sharePct, 1) + "%"}</td>
                <td data-l="Share change" className={cls(r.shareChangePp)}>{r.window && r.years >= 2 ? <>{pp(r.shareChangePp)}<small>since {r.window[0]}</small></> : "—"}</td>
                <td data-l="Growth a year" className={cls(r.cagrPct)}>{r.cagrPct == null ? <span className="faint" title={r.trend === "new" || r.trend === "short" ? "Fewer than three comparable years" : undefined}>{r.trend ? "Not enough years" : "—"}</span> : <>{cagrText(r.cagrPct)}<small>{r.window?.[0]} to {r.window?.[1]}</small></>}</td>
                <td data-l="Last year" className={cls(r.yoyPct)}>{r.yoyPct == null ? "—" : signed(r.yoyPct, 1)}</td>
                <td data-l="Margin">{r.marginPct == null ? "—" : <>{num(r.marginPct, 1)}%{r.marginChangePp != null && <small className={cls(r.marginChangePp)}>{pp(r.marginChangePp)}</small>}</>}</td>
                <td data-l="Trend">{r.trendLabel ? <span className={"chip " + (TAG_CLASS[r.trend || "steady"] || "ghost")}>{r.trendLabel}</span> : <span className="faint">—</span>}{r.note && r.trend !== "discontinued" && <small>{r.note}</small>}</td>
                <td data-l="" className="mx-sp"><Spark values={r.spark} color={r.color} /></td>
              </>)}
            </tr>))}
        </tbody>
      </table>
    </div>
  );
}

/** The history half of the segment card: how the mix has changed (chart), segment trends (table), insights and honest empty states. */
export function SegmentHistory({ seg }: { seg?: Segments }) {
  const [mode, setMode] = useState<Mode>("revenue");
  const [sort, setSort] = useState<SortKey>("default");
  const { status, text } = mixStatus(seg);
  if (!seg) return null;
  if (status === "none" || status === "single") return <p className="mx-empty muted">{text}</p>;
  const model = chartModel(seg), rows = tableRows(seg);
  const latest = seg.periods[seg.periods.length - 1] || "";
  const ins = seg.insights;
  const many = model.years.length >= 2;
  return (
    <div className="mx">
      <div className="mx-h">
        <h4>How the mix has changed</h4>
        {many && <div className="seg" role="group" aria-label="Chart values"><button type="button" aria-pressed={mode === "revenue"} onClick={() => setMode("revenue")}>Revenue (₹ Cr)</button><button type="button" aria-pressed={mode === "share"} onClick={() => setMode("share")}>Share of revenue (%)</button></div>}
      </div>
      {status === "short" && <p className="mx-empty muted">{text}</p>}
      {many ? (
        <>
          <MixChart model={model} mode={mode} />
          <ul className="mx-leg" aria-label="Segments">{model.series.map((s) => <li key={s.key} title={s.members ? s.members.join(", ") : undefined}><i style={{ background: s.color }} aria-hidden="true" />{s.label}</li>)}</ul>
          <div className="sr-only"><table>
            <caption>Revenue by segment and fiscal year, ₹ crore, with share of the sum of segment revenues</caption>
            <thead><tr><th scope="col">Segment</th>{model.years.map((y) => <th scope="col" key={y}>{y}</th>)}</tr></thead>
            <tbody>{model.series.map((s) => <tr key={s.key}><th scope="row">{s.label}</th>{model.years.map((y, i) => <td key={y}>{s.values[i] == null ? "not reported" : `${nf(s.values[i] as number, 0)} Cr, ${s.shares[i] == null ? "—" : nf(s.shares[i] as number, 1) + "%"}`}</td>)}</tr>)}</tbody>
          </table></div>
        </>
      ) : null}

      {many && (
        <>
          <div className="mx-h"><h4>Segment trends</h4></div>
          <TrendTable rows={rows} latest={latest} sort={sort} setSort={setSort} />
        </>
      )}

      {ins && status === "ok" && (ins.sentences.length > 0 || ins.cautions.length > 0) && (
        <div className="mx-ins">
          <h4><Icon name="info" /> Insights</h4>
          {ins.sentences.length > 0 && <ul>{ins.sentences.map((s) => <li key={s}>{s}</li>)}</ul>}
          {ins.cautions.length > 0 && <div className="mx-caut"><b><Icon name="alert" /> Read with care</b><ul>{ins.cautions.map((c) => <li key={c}>{c}</li>)}</ul></div>}
        </div>
      )}
      {!ins && many && status === "ok" && <p className="mx-foot faint">Growth rates and trend tags appear here once this report is refreshed.</p>}
      <p className="mx-foot faint">{ins?.basis || "Shares are of the sum of the segment revenues, which can differ from reported revenue because inter-segment sales are removed."} Information only, not advice.</p>
    </div>
  );
}
