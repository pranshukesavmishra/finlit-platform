import { useId, useState } from "react";
import { useWidth } from "../components/prism/PrismCharts";
import { axisUnit, buildSeries, chartDomain, changeVs, chartCsv, chartSummary, fmtChange, fmtCr, labelIndices, tableRows, tooltipText, type Series } from "../lib/outlookChart";
import { KIND_LABEL, type Kind } from "../lib/outlook";
import { saveFile } from "../stock/derive";

export { buildSeries };

const COLOR: Record<Kind, string> = { revenue: "var(--c1)", profit: "var(--c2)" };   // blue and orange: apart for the common colour-vision types; solid/dashed and filled/hollow carry the same meaning
const ALT = "var(--c4)";

/** One line chart for one metric: reported years as a solid line with filled dots, estimate years as a dashed line with hollow dots, joined at the last reported year.
 *  `who` names whose estimate the dashed line is ("Your weights" / "FinLit model"); a second dashed line (the model's) is drawn when the series carries one.
 *  Annual figures only: the model works on financial years. Hover, touch or arrow keys read a year; "Show as table" opens the same numbers. */
export function OutlookChart({ kind, symbol, series, who, horizonLabel }: { kind: Kind; symbol: string; series: Series; who: string; horizonLabel: string }) {
  const uid = useId().replace(/:/g, "");
  const [ref, width] = useWidth<HTMLDivElement>(640);
  const [active, setActive] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const color = COLOR[kind], name = KIND_LABEL[kind];
  const pts = series.points, n = pts.length;
  const vals = pts.flatMap((p) => [p.value, p.alt]).filter((v): v is number => v != null);
  if (n < 1 || !vals.length) return <p className="ol-empty">No reported {name.toLowerCase()} figures are stored for this company, so there is nothing to chart.</p>;

  const dom = chartDomain(vals), unit = axisUnit(Math.max(...vals.map(Math.abs), Math.abs(dom.min), Math.abs(dom.max)), dom.step);
  const W = Math.max(280, width), H = W < 520 ? 270 : 310;
  const pl = 14 + Math.max(...dom.ticks.map((t) => unit.fmt(t).length)) * 6.6, pr = W < 520 ? 14 : 22, pt = 30, pb = 30, pw = W - pl - pr;
  const X = (i: number) => (n === 1 ? pl + pw / 2 : pl + (i * pw) / (n - 1));
  const Y = (v: number) => pt + (1 - (v - dom.min) / (dom.max - dom.min || 1)) * (H - pt - pb);
  const showLabel = labelIndices(n, pw, Math.max(...pts.map((p) => p.period.length), 1));
  const crossesZero = dom.min < 0 && dom.max > 0;

  // solid line: runs of reported points (a missing year breaks the line, it is never bridged)
  const runs: number[][] = [];
  pts.forEach((p, i) => { if (p.status === "actual" && p.value != null) { const r = runs[runs.length - 1]; if (r && r[r.length - 1] === i - 1) r.push(i); else runs.push([i]); } });
  const d = (idx: number[], f: (i: number) => number) => idx.map((i, k) => `${k ? "L" : "M"}${X(i).toFixed(1)},${Y(f(i)).toFixed(1)}`).join("");
  const est = pts.map((p, i) => (p.status === "estimate" ? i : -1)).filter((i) => i >= 0);
  const joint = series.lastActual;
  const estPath = est.length && joint >= 0 ? d([joint, ...est], (i) => pts[i].value as number) : "";
  const altIdx = series.hasAlt ? est.filter((i) => pts[i].alt != null) : [];
  const altPath = altIdx.length && joint >= 0 ? d([joint, ...altIdx], (i) => (i === joint ? (pts[i].value as number) : (pts[i].alt as number))) : "";
  const divX = est.length ? (X(joint) + X(est[0])) / 2 : null;
  const summary = chartSummary(kind, series, who);

  const move = (e: React.PointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect(), x = ((e.clientX - r.left) / r.width) * pw;
    setActive(n === 1 ? 0 : Math.max(0, Math.min(n - 1, Math.round((x / pw) * (n - 1)))));
  };
  const key = (e: React.KeyboardEvent) => {
    const to = e.key === "ArrowRight" ? Math.min(n - 1, (active ?? -1) + 1) : e.key === "ArrowLeft" ? Math.max(0, (active ?? n) - 1) : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : e.key === "Escape" ? null : undefined;
    if (to !== undefined) { e.preventDefault(); setActive(to); }
  };
  const tip = active != null ? pts[active] : null;
  const ch = active != null ? changeVs(pts, active) : null;
  const tipY = tip && tip.value != null ? Y(tip.value) : pt;

  return (
    <div className="ol-chart" ref={ref}>
      <div className="ol-chart-top">
        <h3 style={{ color }}>{name}</h3>
        <div className="ol-chart-acts">
          <button type="button" className="ol-link" aria-expanded={table} onClick={() => setTable((v) => !v)}>{table ? "Hide table" : "Show as table"}</button>
          <button type="button" className="ol-link" onClick={() => saveFile(`FinLit-${symbol}-${kind}-estimate.csv`, chartCsv(kind, symbol, series, who, horizonLabel), "text/csv;charset=utf-8")}>Download CSV</button>
        </div>
      </div>
      <div className="ol-plot" tabIndex={0} role="group" aria-label={`${name} chart. Use the left and right arrow keys to read one year at a time.`} aria-describedby={`${uid}-sum`}
        onKeyDown={key} onFocus={() => setActive((a) => a ?? Math.max(0, series.lastActual))} onBlur={() => setActive(null)} onPointerLeave={() => setActive(null)}>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary}>
          <text x={4} y={14} textAnchor="start" className="ol-ax" fill="var(--faint)">{unit.name}</text>
          {dom.ticks.map((t) => (
            <g key={t}><line x1={pl} x2={W - pr} y1={Y(t)} y2={Y(t)} stroke={t === 0 && crossesZero ? "var(--border-strong)" : "var(--border)"} strokeWidth={t === 0 && crossesZero ? 1.6 : 1} strokeDasharray={t === 0 && crossesZero ? undefined : "3 5"} />
              <text x={pl - 8} y={Y(t) + 4} textAnchor="end" className="ol-ax mono" fill={t === 0 && crossesZero ? "var(--text)" : "var(--faint)"}>{unit.fmt(t)}</text></g>))}
          {est.length > 0 && divX != null && (
            <g><rect x={divX} y={pt} width={W - pr - divX} height={H - pt - pb} fill={color} opacity=".05" />
              <line x1={divX} x2={divX} y1={pt - 6} y2={H - pb} stroke="var(--border-strong)" strokeWidth="1.2" />
              <text x={divX + (divX > W * 0.62 ? -6 : 6)} y={pt - 11} textAnchor={divX > W * 0.62 ? "end" : "start"} className="ol-ax" fontWeight="600" fill="var(--muted)">Forecast starts {pts[est[0]].period}</text></g>)}
          {pts.map((p, i) => showLabel(i) && <text key={i} x={X(i)} y={H - 9} textAnchor="middle" className="ol-ax" fill={p.status === "estimate" ? "var(--muted)" : "var(--faint)"}>{p.period}</text>)}
          {active != null && <line x1={X(active)} x2={X(active)} y1={pt} y2={H - pb} stroke="var(--border-strong)" />}
          {runs.map((r, k) => <path key={k} d={d(r, (i) => pts[i].value as number)} fill="none" stroke={color} strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />)}
          {altPath && <path d={altPath} fill="none" stroke={ALT} strokeWidth="2.2" strokeDasharray="2 5" strokeLinecap="round" />}
          {estPath && <path d={estPath} fill="none" stroke={color} strokeWidth="2.8" strokeDasharray="7 6" strokeLinecap="round" strokeLinejoin="round" />}
          {pts.map((p, i) => p.value != null && (
            <circle key={i} cx={X(i)} cy={Y(p.value)} r={i === active ? 6.5 : 4.5} fill={p.status === "actual" ? color : "var(--s1)"} stroke={color} strokeWidth="2.4" />))}
          {altIdx.map((i) => <circle key={"a" + i} cx={X(i)} cy={Y(pts[i].alt as number)} r={i === active ? 5.5 : 3.6} fill="var(--s1)" stroke={ALT} strokeWidth="2" />)}
          <rect x={pl} y={pt} width={pw} height={H - pt - pb} fill="transparent" onPointerMove={move} onPointerDown={move} />
        </svg>
        {tip && (
          <div className="ol-tip" style={{ left: `${Math.min(W - 120, Math.max(120, X(active as number)))}px`, top: Math.max(4, Math.min(tipY - 8, H - 150)) }} aria-hidden="true">
            <b>{tip.period}</b>
            <span className={"ol-tip-kind " + tip.status}><i />{tip.value == null ? "Not reported" : tip.status === "actual" ? "Reported" : "Estimate"}</span>
            {tip.value != null && <em>{fmtCr(tip.value)}</em>}
            {ch && <small>{fmtChange(ch)} on the year before</small>}
            {tip.alt != null && <small>FinLit model: {fmtCr(tip.alt)}</small>}
            {tip.adjusted && <small>Adjusted for one-off items (reported {fmtCr(tip.reported)})</small>}
          </div>)}
      </div>
      <p className="sr-only" id={`${uid}-sum`}>{summary}</p>
      <p className="sr-only" aria-live="polite">{active != null ? tooltipText(series, active) : ""}</p>
      <ul className="ol-legend" aria-label="How to read the chart">
        <li><svg width="34" height="12" aria-hidden="true"><line x1="1" x2="33" y1="6" y2="6" stroke={color} strokeWidth="2.8" strokeLinecap="round" /><circle cx="17" cy="6" r="4" fill={color} stroke={color} strokeWidth="2" /></svg>Reported</li>
        {est.length > 0 && <li><svg width="34" height="12" aria-hidden="true"><line x1="1" x2="33" y1="6" y2="6" stroke={color} strokeWidth="2.8" strokeDasharray="6 4" strokeLinecap="round" /><circle cx="17" cy="6" r="4" fill="var(--s1)" stroke={color} strokeWidth="2" /></svg>Estimate ({who})</li>}
        {altPath && <li><svg width="34" height="12" aria-hidden="true"><line x1="1" x2="33" y1="6" y2="6" stroke={ALT} strokeWidth="2.2" strokeDasharray="2 5" strokeLinecap="round" /><circle cx="17" cy="6" r="3.4" fill="var(--s1)" stroke={ALT} strokeWidth="2" /></svg>Estimate (FinLit model)</li>}
      </ul>
      {table && (
        <div className="ol-ctable"><table><caption>{name}, ₹ crore, by financial year</caption>
          <thead><tr>{["Year", "Type", "Value", "Change on year before", ...(series.hasAlt ? ["FinLit model estimate"] : [])].map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
          <tbody>{tableRows(series).map((r, i) => <tr key={i}>{r.map((c, j) => (j === 0 ? <th scope="row" key={j}>{c}</th> : <td key={j}>{c}</td>))}</tr>)}</tbody></table></div>)}
    </div>
  );
}
