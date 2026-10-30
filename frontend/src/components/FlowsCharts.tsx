// Hand-drawn SVG charts for the FII/DII page and panel: line chart (shared or dual axis), daily bars with a moving average, 30-session
// mini bars, and the GitHub-style calendar. Hover and the arrow keys read values; reduced motion is respected in the CSS.
import { useEffect, useMemo, useRef, useState } from "react";
import { niceTicks } from "../lib/etf";
import { MINUS, dateIN, nf } from "../lib/format";
import { calendar, diiGap, grp, inr, level, type Cal, type Pt, type SideKey } from "../lib/flowsMath";
import type { FlowDay } from "../lib/flows";

export function useWidth(min = 300): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null), [w, setW] = useState(900);
  useEffect(() => {
    const el = ref.current; if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(min, Math.round(e.contentRect.width)))); ro.observe(el); return () => ro.disconnect();
  }, [min]);
  return [ref, w];
}
const t = (d: string) => Date.parse(d + "T00:00:00Z");
const compact = (v: number) => { const a = Math.abs(v), s = v < 0 ? MINUS : ""; return a >= 100000 ? `${s}${nf(a / 100000, a >= 1000000 ? 0 : 1)}L` : a >= 1000 ? `${s}${nf(a / 1000, a >= 10000 ? 0 : 1)}k` : `${s}${nf(a, 0)}`; };
const dlabel = (d: string) => dateIN(d, { day: "numeric", month: "short", year: "numeric" });
function xTicks(t0: number, t1: number, W: number): { x: number; label: string }[] {
  const out: { x: number; label: string }[] = [], days = (t1 - t0) / 864e5, want = Math.max(3, Math.floor(W / 110));
  if (days <= 0) return out;
  const unit = days / 365 > want * 0.9 ? 12 * Math.ceil(days / 365 / want) : days / 30 > want ? Math.ceil(days / 30 / want) : 0;
  if (unit) {
    const s = new Date(t0); s.setUTCDate(1); s.setUTCMonth(unit >= 12 ? 0 : s.getUTCMonth() + 1);
    for (let d = new Date(s); d.getTime() <= t1; d.setUTCMonth(d.getUTCMonth() + unit)) { if (d.getTime() >= t0) out.push({ x: d.getTime(), label: unit >= 12 ? String(d.getUTCFullYear()) : `${dateIN(d.toISOString().slice(0, 10), { month: "short" })} ’${String(d.getUTCFullYear()).slice(2)}` }); }
  } else {
    const step = Math.max(1, Math.ceil(days / want));
    for (let k = 0; k <= days; k += step) { const x = t0 + k * 864e5; out.push({ x, label: dateIN(new Date(x).toISOString().slice(0, 10), { day: "numeric", month: "short" }) }); }
  }
  return out;
}

// ------------------------------------------------------------------------------------------------------------- lines
export type LineSeries = { key: string; label: string; color: string; pts: Pt[]; axis?: "l" | "r"; dashed?: boolean; fmt?: (v: number) => string };
export function LineChart({ series, height = 320, label, zero = true }: { series: LineSeries[]; height?: number; label: string; zero?: boolean }) {
  const [box, W] = useWidth(), svg = useRef<SVGSVGElement>(null), [hover, setHover] = useState<number | null>(null);
  const dual = series.some((s) => s.axis === "r");
  const H = W < 560 ? Math.round(height * 0.8) : height, L = W < 560 ? 46 : 62, R = dual ? (W < 560 ? 46 : 62) : 14, T = 14, B = 26;
  const live = series.filter((s) => s.pts.length);
  const m = useMemo(() => {
    const all = live.flatMap((s) => s.pts.map((p) => t(p[0])));
    const t0 = Math.min(...all), t1 = Math.max(...all);
    const ax = (side: "l" | "r") => {
      const v = live.filter((s) => (s.axis ?? "l") === side).flatMap((s) => s.pts.map((p) => p[1]));
      if (!v.length) return null;
      const lo = zero && side === "l" ? Math.min(0, ...v) : Math.min(...v), hi = zero && side === "l" ? Math.max(0, ...v) : Math.max(...v);
      const ticks = niceTicks(lo, hi, 5); return { ticks, lo: ticks[0], hi: ticks[ticks.length - 1] };
    };
    const maps = live.map((s) => new Map(s.pts));
    return { t0, t1, l: ax("l"), r: ax("r"), maps };
  }, [live, zero]);
  if (!live.length) return <p className="fl-empty">No data for this range.</p>;
  const X = (d: string | number) => L + (((typeof d === "number" ? d : t(d)) - m.t0) / (m.t1 - m.t0 || 1)) * (W - L - R);
  const Y = (v: number, side: "l" | "r") => { const a = (side === "r" ? m.r : m.l)!; return T + (1 - (v - a.lo) / (a.hi - a.lo || 1)) * (H - T - B); };
  const base = live[0].pts, pathOf = (s: LineSeries) => s.pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)} ${Y(p[1], s.axis ?? "l").toFixed(1)}`).join("");
  const idxAt = (x: number) => { let b = 0, bd = Infinity; for (let i = 0; i < base.length; i++) { const dd = Math.abs(X(base[i][0]) - x); if (dd < bd) { bd = dd; b = i; } } return b; };
  const hi = hover == null ? null : idxAt(hover), anchor = hi == null ? null : base[hi][0];
  const move = (e: React.PointerEvent) => { const r = svg.current!.getBoundingClientRect(); setHover(((e.clientX - r.left) / r.width) * W); };
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); const cur = hi ?? base.length - 1; setHover(X(base[Math.max(0, Math.min(base.length - 1, cur + (e.key === "ArrowRight" ? 1 : -1)))][0])); }
    else if (e.key === "Home") { e.preventDefault(); setHover(X(base[0][0])); } else if (e.key === "End") { e.preventDefault(); setHover(X(base[base.length - 1][0])); } else if (e.key === "Escape") setHover(null);
  };
  return (
    <div className="fl-chart" ref={box}>
      <svg ref={svg} viewBox={`0 0 ${W} ${H}`} role="img" tabIndex={0} aria-label={`${label}. Use the left and right arrow keys to read each session.`} onPointerMove={move} onPointerLeave={() => setHover(null)} onKeyDown={key} onBlur={() => setHover(null)}>
        {m.l!.ticks.map((v) => <g key={v} className="fl-grid"><line x1={L} x2={W - R} y1={Y(v, "l")} y2={Y(v, "l")} className={v === 0 ? "zero" : ""} /><text x={L - 8} y={Y(v, "l") + 4} textAnchor="end">{compact(v)}</text></g>)}
        {m.r && m.r.ticks.map((v) => <text key={v} className="fl-rt" x={W - R + 8} y={Y(v, "r") + 4}>{nf(v, 0)}</text>)}
        {xTicks(m.t0, m.t1, W - L - R).map((k) => <text key={k.x} className="fl-xt" x={X(k.x)} y={H - 7} textAnchor="middle">{k.label}</text>)}
        {live.map((s) => <path key={s.key} d={pathOf(s)} fill="none" stroke={s.color} strokeWidth="2.2" strokeDasharray={s.dashed ? "6 4" : undefined} strokeLinejoin="round" className="fl-line" />)}
        {anchor && <g className="fl-hv"><line x1={X(anchor)} x2={X(anchor)} y1={T} y2={H - B} />{live.map((s, i) => { const v = m.maps[i].get(anchor); return v == null ? null : <circle key={s.key} cx={X(anchor)} cy={Y(v, s.axis ?? "l")} r="4.5" fill={s.color} />; })}</g>}
      </svg>
      {anchor && (
        <div className="fl-tip" style={{ left: `${Math.min(86, Math.max(14, (X(anchor) / W) * 100))}%` }} role="status">
          <b>{dlabel(anchor)}</b>
          {live.map((s, i) => { const v = m.maps[i].get(anchor); return <span key={s.key}><i style={{ background: s.color }} />{s.label}<em>{v == null ? "—" : s.fmt ? s.fmt(v) : inr(v)}</em></span>; })}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- daily bars
export function BarChart({ rows, ma, maLabel, name, height = 300 }: { rows: { d: string; v: number | null }[]; ma?: (number | null)[]; maLabel?: string; name: string; height?: number }) {
  const [box, W] = useWidth(), svg = useRef<SVGSVGElement>(null), [hover, setHover] = useState<number | null>(null);
  const H = W < 560 ? Math.round(height * 0.8) : height, L = W < 560 ? 46 : 62, R = 14, T = 14, B = 26;
  const vals = rows.map((r) => r.v).filter((v): v is number => v != null).concat((ma ?? []).filter((v): v is number => v != null));
  if (!vals.length) return <p className="fl-empty">No data for this range.</p>;
  const ticks = niceTicks(Math.min(0, ...vals), Math.max(0, ...vals), 5), lo = ticks[0], hi = ticks[ticks.length - 1];
  const n = rows.length, pw = W - L - R, step = pw / n, bw = Math.max(1, Math.min(14, step * 0.72));
  const X = (i: number) => L + (i + 0.5) * step, Y = (v: number) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B), y0 = Y(0);
  const maPath = (ma ?? []).map((v, i) => (v == null ? null : [i, v] as const)).filter(Boolean).map((p, k) => `${k ? "L" : "M"}${X(p![0]).toFixed(1)} ${Y(p![1]).toFixed(1)}`).join("");
  const at = (x: number) => Math.max(0, Math.min(n - 1, Math.floor((x - L) / step)));
  const move = (e: React.PointerEvent) => { const r = svg.current!.getBoundingClientRect(); setHover(at(((e.clientX - r.left) / r.width) * W)); };
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); setHover(Math.max(0, Math.min(n - 1, (hover ?? n - 1) + (e.key === "ArrowRight" ? 1 : -1)))); }
    else if (e.key === "Home") { e.preventDefault(); setHover(0); } else if (e.key === "End") { e.preventDefault(); setHover(n - 1); } else if (e.key === "Escape") setHover(null);
  };
  const xs = xTicks(t(rows[0].d), t(rows[n - 1].d), pw);
  const xOf = (ms: number) => L + ((ms - t(rows[0].d)) / ((t(rows[n - 1].d) - t(rows[0].d)) || 1)) * (pw - step) + step / 2;
  const r = hover == null ? null : rows[hover];
  return (
    <div className="fl-chart" ref={box}>
      <svg ref={svg} viewBox={`0 0 ${W} ${H}`} role="img" tabIndex={0} aria-label={`Daily net ${name} flow in rupees crore, green for buying and red for selling${ma ? `, with a ${maLabel} line` : ""}. Use the left and right arrow keys to read each session.`} onPointerMove={move} onPointerLeave={() => setHover(null)} onKeyDown={key} onBlur={() => setHover(null)}>
        {ticks.map((v) => <g key={v} className="fl-grid"><line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} className={v === 0 ? "zero" : ""} /><text x={L - 8} y={Y(v) + 4} textAnchor="end">{compact(v)}</text></g>)}
        {xs.map((k) => <text key={k.x} className="fl-xt" x={xOf(k.x)} y={H - 7} textAnchor="middle">{k.label}</text>)}
        {rows.map((q, i) => q.v == null ? null : <rect key={q.d} x={X(i) - bw / 2} width={bw} y={q.v >= 0 ? Y(q.v) : y0} height={Math.max(0.5, Math.abs(Y(q.v) - y0))} className={q.v >= 0 ? "fl-up" : "fl-dn"} opacity={hover == null || hover === i ? 1 : 0.55} />)}
        {maPath && <path d={maPath} fill="none" stroke="var(--gold)" strokeWidth="2.2" strokeLinejoin="round" className="fl-ma" />}
        {hover != null && <line className="fl-cross" x1={X(hover)} x2={X(hover)} y1={T} y2={H - B} />}
      </svg>
      {r && hover != null && (
        <div className="fl-tip" style={{ left: `${Math.min(86, Math.max(14, (X(hover) / W) * 100))}%` }} role="status">
          <b>{dlabel(r.d)}</b>
          <span><i className={r.v != null && r.v >= 0 ? "up" : "dn"} />{name} net<em>{r.v == null ? "—" : (r.v >= 0 ? "▲ " : "▼ ") + inr(r.v)}</em></span>
          {ma && <span><i style={{ background: "var(--gold)" }} />{maLabel}<em>{ma[hover] == null ? "—" : inr(ma[hover])}</em></span>}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- mini bars (panel)
export function MiniBars({ rows, name }: { rows: { d: string; v: number | null }[]; name: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const vals = rows.map((r) => r.v).filter((v): v is number => v != null); if (!vals.length) return null;
  const mx = Math.max(...vals.map(Math.abs)) || 1, W = 300, H = 46, n = rows.length, step = W / n, mid = H / 2;
  const r = hover == null ? null : rows[hover];
  return (
    <div className="fl-mini">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" tabIndex={0} aria-label={`${name}: net flow of each of the last ${n} sessions, green buying and red selling. Arrow keys read each session.`}
        onPointerMove={(e) => { const b = e.currentTarget.getBoundingClientRect(); setHover(Math.max(0, Math.min(n - 1, Math.floor(((e.clientX - b.left) / b.width) * n)))); }} onPointerLeave={() => setHover(null)}
        onKeyDown={(e) => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); setHover(Math.max(0, Math.min(n - 1, (hover ?? n - 1) + (e.key === "ArrowRight" ? 1 : -1)))); } else if (e.key === "Escape") setHover(null); }} onBlur={() => setHover(null)}>
        <line x1="0" x2={W} y1={mid} y2={mid} className="fl-zero" />
        {rows.map((q, i) => { if (q.v == null) return null; const h = Math.max(1, (Math.abs(q.v) / mx) * (mid - 2)); return <rect key={q.d} x={i * step + step * 0.15} width={step * 0.7} y={q.v >= 0 ? mid - h : mid} height={h} className={q.v >= 0 ? "fl-up" : "fl-dn"} opacity={hover == null || hover === i ? 1 : 0.5} />; })}
      </svg>
      <span className="fl-mini-t" aria-live="polite">{r ? `${name} · ${dlabel(r.d)}: ${r.v == null ? "no figure" : (r.v >= 0 ? "▲ " : "▼ ") + inr(r.v)}` : `${name} · last ${n} sessions`}</span>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- calendar
const WD = ["Mon", "Tue", "Wed", "Thu", "Fri"];
export function CalendarHeat({ days, side, selected, onSelect, name, publishedFrom }: { days: FlowDay[]; side: SideKey; selected: string | null; onSelect: (d: string) => void; name: string; publishedFrom?: string | null }) {
  const cal: Cal = useMemo(() => calendar(days, side), [days, side]);
  const labels = useMemo(() => new Map(cal.cells.map((c) => {
    const un = c.v == null && side === "dii" && diiGap(c.d, publishedFrom) === "unpublished";
    if (un) return [c.d, { title: `${dlabel(c.d)}: not published (the official DII report begins ${dlabel(publishedFrom!)})`, aria: `${dlabel(c.d)}: ${name} not published, the official report begins ${dlabel(publishedFrom!)}` }] as const;
    const w = `${dlabel(c.d)}: ${c.v == null ? "no figure" : (c.v > 0 ? "▲ " : c.v < 0 ? "▼ " : "") + inr(c.v)}`;
    return [c.d, { title: w, aria: `${dlabel(c.d)}: ${name} ${c.v == null ? "no figure published" : (c.v > 0 ? "net buying " : c.v < 0 ? "net selling " : "flat ") + inr(c.v)}` }] as const;
  })), [cal, name, side, publishedFrom]);
  const scroller = useRef<HTMLDivElement>(null), byDate = useMemo(() => new Map(cal.cells.map((c) => [c.d, c])), [cal]);
  useEffect(() => { const el = scroller.current; if (el) el.scrollLeft = el.scrollWidth; }, [cal]);
  const dates = useMemo(() => cal.cells.map((c) => c.d), [cal]);
  const focusDate = (d: string) => { onSelect(d); requestAnimationFrame(() => scroller.current?.querySelector<HTMLButtonElement>(`[data-d="${d}"]`)?.focus()); };
  const key = (e: React.KeyboardEvent, d: string) => {
    const i = dates.indexOf(d); if (i < 0) return;
    const shift = (days: number) => { const base = t(d) + days * 864e5; for (const off of [0, 1, -1, 2, -2]) { const x = new Date(base + off * 864e5).toISOString().slice(0, 10); if (byDate.has(x)) return x; } return null; };
    const next = e.key === "ArrowRight" ? shift(7) : e.key === "ArrowLeft" ? shift(-7) : e.key === "ArrowDown" ? dates[i + 1] : e.key === "ArrowUp" ? dates[i - 1] : e.key === "Home" ? dates[0] : e.key === "End" ? dates[dates.length - 1] : null;
    if (next) { e.preventDefault(); focusDate(next); }
  };
  const tabbable = selected && byDate.has(selected) ? selected : dates[dates.length - 1];
  return (
    <div className="fl-cal">
      <div className="fl-cal-sc" ref={scroller}>
        <div className="fl-cal-in" role="group" aria-label={`${name} flow by day for the last year. Press a day to read its figures. Arrow keys move between days.`}>
          <div className="fl-cal-m" style={{ gridTemplateColumns: `repeat(${cal.cols}, minmax(0, 1fr))` }}>{cal.months.map((m) => <span key={m.col} style={{ gridColumn: `${m.col + 1} / span 4` }}>{m.label}</span>)}</div>
          <div className="fl-cal-body">
            <div className="fl-cal-wd">{WD.map((w, i) => <span key={w} style={{ visibility: i % 2 === 0 ? "visible" : "hidden" }}>{w}</span>)}</div>
            <div className="fl-cal-g" style={{ gridTemplateColumns: `repeat(${cal.cols}, minmax(0, 1fr))` }}>
              {cal.cells.map((c) => {
                const l = level(c.v, cal.scale);
                return <button key={c.d} type="button" data-d={c.d} data-l={l} data-n={c.v == null ? (side === "dii" && diiGap(c.d, publishedFrom) === "unpublished" ? 2 : 1) : undefined} className={"fl-cell" + (selected === c.d ? " sel" : "")} style={{ gridColumn: c.col + 1, gridRow: c.row + 1 }} tabIndex={c.d === tabbable ? 0 : -1}
                  aria-pressed={selected === c.d} aria-label={labels.get(c.d)!.aria} title={labels.get(c.d)!.title}
                  onClick={() => onSelect(c.d)} onKeyDown={(e) => key(e, c.d)} />;
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
export const CAL_LEGEND = [-4, -3, -2, -1, 0, 1, 2, 3, 4];
export { grp };
