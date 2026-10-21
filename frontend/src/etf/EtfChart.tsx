// A price chart for one ETF, or several ETFs rebased to 100. Plain SVG drawn at the width it is shown, no animation.
// Keyboard: focus the chart, then Left/Right move through the dates (Shift for ten at a time), Home/End jump, Escape lets go.
// Screen readers get a summary of the whole line, the active point read aloud, and the numbers as a table underneath.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { MINUS, nf } from "../lib/format";
import { axisDate, dateTicks, day, frameOf, linePath, nearest, niceTicks, px, py, rupee, spanDays, type Frame, type Point } from "../lib/etf";

export type ChartSeries = { key: string; label: string; points: Point[]; color: string; dash?: string };

const fmtValue = (mode: "price" | "index", v: number) => (mode === "price" ? rupee(v) : nf(v, 1));
const tickText = (mode: "price" | "index", v: number) => (mode === "price" ? nf(v, v >= 100 ? 0 : 2) : nf(v, 0));

export function EtfChart({ series, mode, summary, caption }: { series: ChartSeries[]; mode: "price" | "index"; summary: string; caption: string }) {
  const id = useId().replace(/:/g, "");
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  const [active, setActive] = useState<number | null>(null);          // index into the first series
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW((o) => (Math.abs(o - Math.round(e.contentRect.width)) > 1 ? Math.round(e.contentRect.width) : o)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const h = w < 520 ? 240 : 320;
  const f: Frame | null = useMemo(() => (w >= 120 ? frameOf(series.map((s) => s.points), w, h, { l: mode === "price" ? 48 : 40, r: 12, t: 12, b: 28 }) : null), [series, w, h, mode]);
  const lead = series[0]?.points ?? [];
  useEffect(() => setActive(null), [series]);

  if (!lead.length) return <div ref={box} className="etf-chart empty">No chart for this range.</div>;
  const ticks = f ? niceTicks(f.vMin, f.vMax, 5).filter((v) => v >= f.vMin - 1e-9 && v <= f.vMax + 1e-9) : [];
  const span = f ? spanDays(f) : 0;
  const at = (s: ChartSeries, iso: string): Point => s.points[nearest(f!, s.points, px(f!, iso))];
  const cur = active != null ? lead[Math.min(active, lead.length - 1)] : null;
  const move = (to: number) => setActive(Math.max(0, Math.min(lead.length - 1, to)));
  const onKey = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 10 : 1, i = active ?? lead.length - 1;
    if (e.key === "ArrowLeft") { e.preventDefault(); move(i - step); }
    else if (e.key === "ArrowRight") { e.preventDefault(); move(i + step); }
    else if (e.key === "Home") { e.preventDefault(); move(0); }
    else if (e.key === "End") { e.preventDefault(); move(lead.length - 1); }
    else if (e.key === "Escape") setActive(null);
  };
  const onPoint = (e: React.PointerEvent<SVGRectElement>) => {
    if (!f) return;
    const r = e.currentTarget.getBoundingClientRect();
    setActive(nearest(f, lead, f.x0 + ((e.clientX - r.left) / r.width) * (f.x1 - f.x0)));
  };
  const rows = tableRows(series, 12);
  const tipLeft = f && cur ? Math.min(Math.max(px(f, cur[0]), 90), w - 90) : 0;

  return (
    <div className="etf-chart" ref={box}>
      <div className="etf-chart-focus" tabIndex={0} role="group" aria-roledescription="chart" aria-label={caption + ". Use the left and right arrow keys to move through the dates."} onKeyDown={onKey} onBlur={() => setActive(null)}>
        {f && (
          <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={summary}>
            <defs>
              {series.length === 1 && <linearGradient id={`${id}-a`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={series[0].color} stopOpacity=".28" /><stop offset="1" stopColor={series[0].color} stopOpacity="0" /></linearGradient>}
            </defs>
            {ticks.map((v) => (
              <g key={v}>
                <line x1={f.x0} x2={f.x1} y1={py(f, v)} y2={py(f, v)} stroke="var(--border)" strokeDasharray={v === ticks[0] ? "" : "3 5"} />
                <text x={f.x0 - 6} y={py(f, v) + 4} textAnchor="end" fontSize="11" fill="var(--faint)" fontFamily="var(--mono)">{tickText(mode, v)}</text>
              </g>
            ))}
            {dateTicks(f, 6).map((d, i, a) => (
              <text key={d} x={px(f, d)} y={h - 8} textAnchor={i === 0 ? "start" : i === a.length - 1 ? "end" : "middle"} fontSize="11" fill="var(--faint)">{axisDate(d, span)}</text>
            ))}
            {mode === "index" && <line x1={f.x0} x2={f.x1} y1={py(f, 100)} y2={py(f, 100)} stroke="var(--border-strong)" strokeDasharray="2 4" />}
            {series.length === 1 && <path d={`${linePath(f, series[0].points)}L${px(f, series[0].points[series[0].points.length - 1][0])},${f.y0}L${px(f, series[0].points[0][0])},${f.y0}Z`} fill={`url(#${id}-a)`} />}
            {series.map((s) => <path key={s.key} d={linePath(f, s.points)} fill="none" stroke={s.color} strokeWidth={2.2} strokeDasharray={s.dash} strokeLinejoin="round" strokeLinecap="round" />)}
            {cur && (
              <g pointerEvents="none">
                <line x1={px(f, cur[0])} x2={px(f, cur[0])} y1={f.y1} y2={f.y0} stroke="var(--border-strong)" />
                {series.map((s) => { const p = at(s, cur[0]); return <circle key={s.key} cx={px(f, p[0])} cy={py(f, p[1])} r={4.2} fill="var(--s1)" stroke={s.color} strokeWidth={2.2} />; })}
              </g>
            )}
            <rect x={f.x0} y={f.y1} width={f.x1 - f.x0} height={f.y0 - f.y1} fill="transparent" onPointerMove={onPoint} onPointerDown={onPoint} onPointerLeave={() => setActive(null)} />
          </svg>
        )}
        {cur && f && (
          <div className="etf-tip" style={{ left: tipLeft }} aria-hidden="true">
            <b>{day(cur[0])}</b>
            {series.map((s) => { const p = at(s, cur[0]); return <span key={s.key}><i style={{ background: s.color }} />{series.length > 1 ? s.label : "Close"}<em>{fmtValue(mode, p[1])}</em></span>; })}
          </div>
        )}
      </div>
      <div className="sr-only" aria-live="polite">{cur ? `${day(cur[0])}: ${series.map((s) => `${series.length > 1 ? s.label + " " : ""}${fmtValue(mode, at(s, cur[0])[1])}`).join(", ")}` : ""}</div>
      <details className="etf-datatable">
        <summary>Show the numbers as a table</summary>
        <div className="tw"><table>
          <caption className="sr-only">{caption}</caption>
          <thead><tr><th scope="col">Date</th>{series.map((s) => <th key={s.key} scope="col">{s.label}{mode === "index" ? " (start = 100)" : " (₹)"}</th>)}</tr></thead>
          <tbody>{rows.map((r) => <tr key={r.date}><th scope="row">{day(r.date)}</th>{r.values.map((v, i) => <td key={i}>{v == null ? "—" : mode === "price" ? nf(v, 2) : nf(v, 1).replace(/^-/, MINUS)}</td>)}</tr>)}</tbody>
        </table></div>
      </details>
    </div>
  );
}

/** About `n` evenly spaced dates of the first series with each series' value on or just before that date. */
export function tableRows(series: ChartSeries[], n: number): { date: string; values: (number | null)[] }[] {
  const lead = series[0]?.points ?? [];
  if (!lead.length) return [];
  const idx = [...new Set(Array.from({ length: Math.min(n, lead.length) }, (_, i) => Math.round((i * (lead.length - 1)) / Math.max(1, Math.min(n, lead.length) - 1))))];
  return idx.map((i) => {
    const date = lead[i][0];
    return { date, values: series.map((s) => { let v: number | null = null; for (const p of s.points) { if (p[0] <= date) v = p[1]; else break; } return v; }) };
  });
}
