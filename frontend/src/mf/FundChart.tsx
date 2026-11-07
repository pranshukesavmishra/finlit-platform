// A line chart of NAV (or NAV rebased to 100) over time, drawn as plain SVG: x by date, one or several funds, no animation.
// Keyboard: focus the chart and use the left and right arrows to read values; the reading is announced politely. Colour is never the only cue:
// every line has its own dash pattern and a label at its end, and the summary is also written out for screen readers.
import { useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { buildLines, nearestIndex, type LineSeries } from "../lib/mf";
import { dateIN } from "../lib/format";

export const SERIES_STYLE = [
  { color: "var(--k1)", dash: "" }, { color: "var(--k2)", dash: "7 4" }, { color: "var(--k3)", dash: "2 4" }, { color: "var(--k7)", dash: "11 4 2 4" },
];
const W = 760, H = 300;

export function FundChart({ series, format, label, base }: { series: LineSeries[]; format: (v: number) => string; label: string; base?: number }) {
  const g = useMemo(() => buildLines(series, W, H, { l: 58, r: series.length > 1 ? 16 : 14, t: 14, b: 28 }), [series]);
  const [cursor, setCursor] = useState<number | null>(null);   // x position in chart units
  const box = useRef<SVGSVGElement>(null);
  const id = useId();
  if (!g) return <div className="mf-chart-empty">Not enough NAV history to draw a chart.</div>;

  const xsOf = (i: number) => g.lines[i].xy.map((p) => p[0]);
  const read = cursor == null ? null : series.map((s, i) => { const k = nearestIndex(xsOf(i), cursor); return { s, i, k, t: s.t[k], v: s.v[k] }; });
  const move = (e: PointerEvent<SVGRectElement>) => {
    const r = box.current!.getBoundingClientRect();
    setCursor(Math.max(g.pad.l, Math.min(W - g.pad.r, ((e.clientX - r.left) / r.width) * W)));
  };
  const key = (e: KeyboardEvent) => {
    if (e.key === "Escape") { setCursor(null); return; }
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight" && e.key !== "Home" && e.key !== "End") return;
    e.preventDefault();
    const xs = xsOf(0), cur = cursor == null ? xs[xs.length - 1] : xs[nearestIndex(xs, cursor)];
    const k = nearestIndex(xs, cur) + (e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0);
    setCursor(e.key === "Home" ? xs[0] : e.key === "End" ? xs[xs.length - 1] : xs[Math.max(0, Math.min(xs.length - 1, k))]);
  };
  const first = series[0], lo = Math.min(...series.flatMap((s) => s.v)), hi = Math.max(...series.flatMap((s) => s.v));
  const summary = `${label}. ` + series.map((s) => `${s.label}: ${format(s.v[0])} on ${dateIN(s.t[0])} to ${format(s.v[s.v.length - 1])} on ${dateIN(s.t[s.t.length - 1])}`).join("; ") + `. Lowest ${format(lo)}, highest ${format(hi)}.`;
  return (
    <div className="mf-chart" tabIndex={0} role="group" aria-label={`${label}. Use the left and right arrow keys to read values.`} onKeyDown={key} onBlur={() => setCursor(null)}>
      <svg ref={box} viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`${id}-t`} preserveAspectRatio="xMidYMid meet">
        <title id={`${id}-t`}>{summary}</title>
        {g.yTicks.map((t) => <g key={t.v}><line x1={g.pad.l} x2={W - g.pad.r} y1={t.at} y2={t.at} stroke="var(--border)" strokeDasharray="3 5" /><text x={g.pad.l - 8} y={t.at + 4} textAnchor="end" fontSize="11" fill="var(--faint)">{format(t.v)}</text></g>)}
        {g.xTicks.map((t, i) => <text key={i} x={t.at} y={H - 8} textAnchor={i === 0 ? "start" : i === g.xTicks.length - 1 ? "end" : "middle"} fontSize="11" fill="var(--faint)">{t.label}</text>)}
        {base != null && g.lo < base && g.hi > base && <line x1={g.pad.l} x2={W - g.pad.r} y1={g.Y(base)} y2={g.Y(base)} stroke="var(--border-strong)" />}
        {g.lines.map((l, i) => <path key={l.key} d={l.d} fill="none" stroke={SERIES_STYLE[i % 4].color} strokeWidth="2.2" strokeDasharray={SERIES_STYLE[i % 4].dash} strokeLinejoin="round" strokeLinecap="round" />)}
        {read && <line x1={cursor!} x2={cursor!} y1={g.pad.t} y2={H - g.pad.b} stroke="var(--border-strong)" />}
        {read && read.map((r) => <circle key={r.s.key} cx={g.lines[r.i].xy[r.k][0]} cy={g.lines[r.i].xy[r.k][1]} r="4.2" fill="var(--s1)" stroke={SERIES_STYLE[r.i % 4].color} strokeWidth="2.2" />)}
        <rect x={g.pad.l} y={g.pad.t} width={W - g.pad.l - g.pad.r} height={H - g.pad.t - g.pad.b} fill="transparent" onPointerMove={move} onPointerDown={move} onPointerLeave={() => setCursor(null)} />
      </svg>
      <div className="mf-tip" aria-live="polite">
        {read ? read.map((r) => <span key={r.s.key}><i style={{ background: SERIES_STYLE[r.i % 4].color }} aria-hidden="true" />{series.length > 1 && <b>{r.s.label}</b>} {format(r.v)}<small> {dateIN(r.t)}</small></span>)
          : <span className="faint">{first.t.length} points from {dateIN(first.t[0])} to {dateIN(first.t[first.t.length - 1])}. Point at the chart, or focus it and use the arrow keys, to read values.</span>}
      </div>
    </div>
  );
}
