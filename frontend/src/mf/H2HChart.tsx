// Charts and range bars of the head-to-head Fund Compare. Fixed colours per fund (A blue, B orange, category average green dotted) whatever is drawn,
// so a fund with no data never shifts the others' colours. Plain SVG, sized to its box (text stays readable on phones), smooth monotone curves,
// a soft gradient under A and B, a hover / touch / arrow-key crosshair with a floating read-out, and an end badge per line.
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { buildLines, nearestIndex } from "../lib/mf";
import { dateIN } from "../lib/format";
import { smoothPath, type RollStats, type Side } from "../lib/mfCompare";

export const SIDE_COLOR: Record<Side, string> = { a: "var(--k1)", b: "var(--k2)", cat: "var(--k3)" };
export const SIDE_DASH: Record<Side, string> = { a: "", b: "", cat: "2 5" };
export const SIDE_LETTER: Record<Side, string> = { a: "A", b: "B", cat: "C" };
export type SideSeries = { side: Side; label: string; t: string[]; v: number[] };

/** The width of an element, kept up to date (so the chart is drawn at its real size). */
function useWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(760);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setW(Math.max(280, Math.round(el.clientWidth))));
    ro.observe(el);
    setW(Math.max(280, Math.round(el.clientWidth)));
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

export function H2HChart({ series, format, label, base, tipFormat }: { series: SideSeries[]; format: (v: number) => string; label: string; base?: number; tipFormat?: (v: number) => string }) {
  const [wrap, W] = useWidth();
  const H = W < 520 ? 250 : 320;
  const phone = W < 520;
  const pad = { l: phone ? 46 : 58, r: phone ? 30 : 34, t: 14, b: 28 };
  const g = useMemo(() => buildLines(series.map((s) => ({ key: s.side, label: s.label, t: s.t, v: s.v })), W, H, pad), [series, W, H]);   // eslint-disable-line react-hooks/exhaustive-deps
  const [cursor, setCursor] = useState<number | null>(null);
  const box = useRef<SVGSVGElement>(null);
  const uid = useId().replace(/:/g, "");
  if (!g) return <div className="mf-chart-empty">Not enough NAV history to draw a chart.</div>;
  const fmtTip = tipFormat || format;

  const xsOf = (i: number) => g.lines[i].xy.map((p) => p[0]);
  const read = cursor == null ? null : series.map((s, i) => { const k = nearestIndex(xsOf(i), cursor); return { s, i, k, t: s.t[k], v: s.v[k] }; });
  const move = (e: PointerEvent<SVGRectElement>) => {
    const r = box.current!.getBoundingClientRect();
    setCursor(Math.max(g.pad.l, Math.min(W - g.pad.r, ((e.clientX - r.left) / r.width) * W)));
  };
  const key = (e: KeyboardEvent) => {
    if (e.key === "Escape") { setCursor(null); return; }
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const xs = xsOf(0), cur = cursor == null ? xs[xs.length - 1] : xs[nearestIndex(xs, cursor)];
    const k = nearestIndex(xs, cur) + (e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0);
    setCursor(e.key === "Home" ? xs[0] : e.key === "End" ? xs[xs.length - 1] : xs[Math.max(0, Math.min(xs.length - 1, k))]);
  };
  const lo = Math.min(...series.flatMap((s) => s.v)), hi = Math.max(...series.flatMap((s) => s.v));
  const summary = `${label}. ` + series.map((s) => `${s.label}: ${format(s.v[0])} on ${dateIN(s.t[0])} to ${format(s.v[s.v.length - 1])} on ${dateIN(s.t[s.t.length - 1])}`).join("; ") + `. Lowest ${format(lo)}, highest ${format(hi)}.`;
  const bottom = H - g.pad.b;
  // end badges, pushed apart so two lines that finish close together keep readable badges
  const ends = g.lines.map((l, i) => ({ i, x: l.xy[l.xy.length - 1][0], y: l.xy[l.xy.length - 1][1] })).sort((p, q) => p.y - q.y);
  for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 19) ends[k].y = ends[k - 1].y + 19;
  const flip = cursor != null && cursor > W * 0.6;

  return (
    <div className="h2h-chart" ref={wrap} tabIndex={0} role="group" aria-label={`${label}. Use the left and right arrow keys to read values.`} onKeyDown={key} onBlur={() => setCursor(null)}>
      <svg ref={box} width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`${uid}-t`}>
        <title id={`${uid}-t`}>{summary}</title>
        <defs>{series.map((s) => (
          <linearGradient key={s.side} id={`${uid}-${s.side}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={SIDE_COLOR[s.side]} stopOpacity={s.side === "cat" ? 0 : 0.22} /><stop offset="100%" stopColor={SIDE_COLOR[s.side]} stopOpacity="0" />
          </linearGradient>))}</defs>
        {g.yTicks.map((t) => <g key={t.v}><line x1={g.pad.l} x2={W - g.pad.r} y1={t.at} y2={t.at} stroke="var(--border)" strokeDasharray="3 5" /><text x={g.pad.l - 8} y={t.at + 4} textAnchor="end" fontSize="11" fill="var(--faint)">{format(t.v)}</text></g>)}
        {g.xTicks.map((t, i) => <text key={i} x={t.at} y={H - 8} textAnchor={i === 0 ? "start" : i === g.xTicks.length - 1 ? "end" : "middle"} fontSize="11" fill="var(--faint)">{t.label}</text>)}
        {base != null && g.lo < base && g.hi > base && <line x1={g.pad.l} x2={W - g.pad.r} y1={g.Y(base)} y2={g.Y(base)} stroke="var(--border-strong)" strokeWidth="1.2" />}
        {g.lines.map((l, i) => {
          const s = series[i];
          if (s.side === "cat") return null;
          const d = smoothPath(l.xy);
          return <path key={"f" + s.side} d={`${d}L${l.xy[l.xy.length - 1][0].toFixed(1)},${bottom}L${l.xy[0][0].toFixed(1)},${bottom}Z`} fill={`url(#${uid}-${s.side})`} />;
        })}
        {[...g.lines.keys()].sort((p, q) => (series[p].side === "cat" ? -1 : series[q].side === "cat" ? 1 : 0)).map((i) => {
          const s = series[i];
          return <path key={s.side} d={smoothPath(g.lines[i].xy)} fill="none" stroke={SIDE_COLOR[s.side]} strokeWidth={s.side === "cat" ? 2 : 2.4} strokeDasharray={SIDE_DASH[s.side]} strokeLinejoin="round" strokeLinecap="round" />;
        })}
        {ends.map((e) => <g key={"e" + e.i} aria-hidden="true"><circle cx={e.x + 12} cy={e.y} r="9" fill={SIDE_COLOR[series[e.i].side]} /><text x={e.x + 12} y={e.y + 3.6} textAnchor="middle" fontSize="10.5" fontWeight="700" fill="var(--on-gold, #fff)" style={{ fill: "#fff" }}>{SIDE_LETTER[series[e.i].side]}</text></g>)}
        {read && <line x1={cursor!} x2={cursor!} y1={g.pad.t} y2={bottom} stroke="var(--text)" strokeOpacity=".35" strokeDasharray="4 4" />}
        {read && read.map((r) => <circle key={r.s.side} cx={g.lines[r.i].xy[r.k][0]} cy={g.lines[r.i].xy[r.k][1]} r="5" fill="var(--s1)" stroke={SIDE_COLOR[r.s.side]} strokeWidth="2.4" />)}
        <rect x={g.pad.l} y={g.pad.t} width={W - g.pad.l - g.pad.r} height={bottom - g.pad.t} fill="transparent" style={{ touchAction: "pan-y" }} onPointerMove={move} onPointerDown={move} onPointerLeave={() => setCursor(null)} />
      </svg>
      {read && (
        <div className="h2h-tip" style={{ left: `${(cursor! / W) * 100}%`, transform: `translateX(${flip ? "calc(-100% - 12px)" : "12px"})` }} aria-hidden="true">
          <b>{dateIN(read[0].t)}</b>
          {read.map((r) => <span key={r.s.side}><i style={{ background: SIDE_COLOR[r.s.side] }} />{r.s.label}<em>{fmtTip(r.v)}</em></span>)}
        </div>)}
      <div className="mf-tip" aria-live="polite">
        {read ? read.map((r) => <span key={r.s.side}><i style={{ background: SIDE_COLOR[r.s.side] }} aria-hidden="true" /><b>{r.s.label}</b> {fmtTip(r.v)}<small> {dateIN(r.t)}</small></span>)
          : <span className="faint">{series[0].t.length} points from {dateIN(series[0].t[0])} to {dateIN(series[0].t[series[0].t.length - 1])}. Point at the chart, or focus it and use the arrow keys, to read values.</span>}
      </div>
    </div>
  );
}

/** Lowest to highest rolling return of each fund on one shared scale: a bar for the range, a tick for the median, a line at zero. */
export function RangeBars({ stats, names, fmt, unit }: { stats: Record<Side, RollStats>; names: Record<Side, string>; fmt: (v: number) => string; unit: string }) {
  const sides = (["a", "b", "cat"] as Side[]).filter((s) => stats[s].min != null && stats[s].max != null && stats[s].median != null);
  if (!sides.length) return null;
  const lo = Math.min(0, ...sides.map((s) => stats[s].min!)), hi = Math.max(0, ...sides.map((s) => stats[s].max!));
  const span = hi - lo || 1, pos = (v: number) => `${(((v - lo) / span) * 100).toFixed(2)}%`;
  return (
    <div className="h2h-rb" role="group" aria-label={`Range of the rolling returns, ${unit}`}>
      {sides.map((s) => {
        const st = stats[s];
        return (
          <div className="h2h-rb-row" key={s} role="img" aria-label={`${names[s]}: lowest ${fmt(st.min!)}, median ${fmt(st.median!)}, highest ${fmt(st.max!)}${st.positive != null ? `, a gain in ${Math.round(st.positive)}% of windows` : ""}`}>
            <div className="h2h-rb-name">{s === "cat" ? <span className="h2h-key-line" style={{ borderTopColor: SIDE_COLOR.cat }} aria-hidden="true" /> : <span className={`h2h-badge ${s}`} aria-hidden="true">{SIDE_LETTER[s]}</span>}<span>{names[s]}</span></div>
            <div className="h2h-rb-track">
              <span className="h2h-rb-zero" style={{ left: pos(0) }} />
              <span className="h2h-rb-bar" style={{ left: pos(st.min!), width: `${(((st.max! - st.min!) / span) * 100).toFixed(2)}%`, background: `linear-gradient(90deg, color-mix(in srgb, ${SIDE_COLOR[s]} 35%, transparent), ${SIDE_COLOR[s]})` }} />
              <i className="h2h-rb-med" style={{ left: pos(st.median!) }} />
            </div>
            <div className="h2h-rb-vals"><span>{fmt(st.min!)}</span><b>{fmt(st.median!)}<small> median</small></b><span>{fmt(st.max!)}</span></div>
          </div>);
      })}
      <div className="h2h-rb-row axis" aria-hidden="true"><span /><div className="h2h-rb-scale"><span style={{ left: pos(lo) }}>{fmt(lo)}</span>{lo < 0 && hi > 0 && <span style={{ left: pos(0) }}>0</span>}<span style={{ left: pos(hi) }}>{fmt(hi)}</span></div><span /></div>
    </div>
  );
}
