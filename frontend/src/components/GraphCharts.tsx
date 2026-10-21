// Graph Studio chart renderers. Plain SVG with explicit colours (so a chart can be exported as PNG), a hover/keyboard readout on every chart.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { MINUS } from "../lib/format";
import { axisUnits, domain, fitLine, ms, ticks, strength, type Matrix } from "../lib/graphData";
import { fmtTick, fmtValue, UNITS, type Pt, type UnitId } from "../lib/graphMetrics";

export type Colors = { s: string[]; surface: string; text: string; muted: string; grid: string; axis: string; gain: string; loss: string; pos: string; neg: string; mid: string };
export type PS = { key: string; label: string; unit: UnitId; pts: Pt[]; color: string; as: "bar" | "line"; periodic: boolean };
const H = 300, M = { l: 52, r: 52, t: 14, b: 30 };

export function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  useEffect(() => { const el = ref.current; if (!el) return; const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width))); ro.observe(el); return () => ro.disconnect(); }, []);
  return { ref, w };
}

function Tip({ x, y, w, children }: { x: number; y: number; w: number; children: ReactNode }) {
  const right = x > w / 2;
  return <div className="gx-tip" style={{ top: Math.max(4, y), ...(right ? { right: w - x + 12 } : { left: x + 12 }) }} role="status">{children}</div>;
}
const dlabel = (t: string, l?: string) => l ?? new Date(ms(t)).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const Y = (v: number, [lo, hi]: [number, number]) => M.t + (1 - (v - lo) / (hi - lo || 1)) * (H - M.t - M.b);

/** line, area, column and combo over time, with one or two value axes (one per unit). */
export function TimeChart({ kind, series, c, w }: { kind: "line" | "area" | "column" | "combo"; series: PS[]; c: Colors; w: number }) {
  const [hi, setHi] = useState<number | null>(null);
  const units = axisUnits(series.map((s) => s.unit)) ?? [series[0].unit];
  const kindOf = (s: PS) => (kind === "column" ? "bar" : kind === "combo" ? s.as : "line");
  const dates = [...new Set(series.flatMap((s) => s.pts.filter((p) => p.v != null).map((p) => p.t)))].sort();
  const labelOf = new Map(series.flatMap((s) => s.pts.map((p) => [p.t, p.l] as const)).filter((x) => x[1]));
  const allPeriodic = series.every((s) => s.periodic);
  const pw = w - M.l - M.r, t0 = ms(dates[0]), t1 = ms(dates[dates.length - 1]);
  const X = (t: string) => allPeriodic ? M.l + (dates.length < 2 ? pw / 2 : ((pw - 0) * (dates.indexOf(t) + 0.5)) / dates.length) : M.l + (t1 === t0 ? pw / 2 : ((ms(t) - t0) / (t1 - t0)) * pw);
  const hasBars = series.some((s) => kindOf(s) === "bar");
  const doms = units.map((u) => domain(series.filter((s) => s.unit === u || (units.length === 1)).flatMap((s) => s.pts.filter((p) => p.v != null).map((p) => p.v as number)), hasBars || kind === "area"));
  const ax = (s: PS) => Math.max(0, units.indexOf(s.unit));
  const gap = dates.length > 1 ? Math.min(...dates.slice(1).map((d, i) => Math.abs(X(d) - X(dates[i])))) : pw / 2;
  const nBars = series.filter((s) => kindOf(s) === "bar").length || 1, group = Math.min(56, gap * 0.72), bw = Math.max(1, group / nBars - 2);
  const tickDates = allPeriodic ? dates.filter((_, i) => i % Math.ceil(dates.length / Math.max(2, Math.floor(pw / (Math.max(...dates.map((d) => (labelOf.get(d) ?? d.slice(0, 7)).length)) * 6.5 + 12)))) === 0)
    : (() => { const out: string[] = [], yrs = (t1 - t0) / (365.25 * 86400000), step = yrs > 8 ? 2 : 1; for (let y = new Date(t0).getUTCFullYear() + 1; y <= new Date(t1).getUTCFullYear(); y += yrs > 1.5 ? step : 1) out.push(`${y}-01-01`); return yrs > 1.5 && out.length > 0 ? out : dates.filter((_, i) => i % Math.ceil(dates.length / 5) === 0); })();
  const tl = (d: string) => (allPeriodic ? labelOf.get(d) ?? d.slice(0, 7) : (t1 - t0) / 86400000 > 550 ? d.slice(0, 4) : new Date(ms(d)).toLocaleDateString("en-IN", { month: "short", year: "2-digit", timeZone: "UTC" }));
  const move = (e: React.PointerEvent<SVGSVGElement>) => { const r = e.currentTarget.getBoundingClientRect(), px = e.clientX - r.left; let b = 0; dates.forEach((d, i) => { if (Math.abs(X(d) - px) < Math.abs(X(dates[b]) - px)) b = i; }); setHi(b); };
  const key = (e: React.KeyboardEvent) => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); setHi((h) => Math.max(0, Math.min(dates.length - 1, (h ?? dates.length - 1) + (e.key === "ArrowRight" ? 1 : -1)))); } if (e.key === "Escape") setHi(null); };
  const d = hi != null ? dates[Math.min(hi, dates.length - 1)] : null;
  return (
    <div className="gx-plot" onPointerLeave={() => setHi(null)}>
      <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} tabIndex={0} role="img" aria-label={`${kind} chart of ${series.map((s) => s.label).join(", ")}. Arrow keys move through ${dates.length} dates.`} onPointerMove={move} onKeyDown={key} onBlur={() => setHi(null)}>
        {ticks(doms[0][0], doms[0][1]).map((t) => <g key={t}><line x1={M.l} x2={w - M.r} y1={Y(t, doms[0])} y2={Y(t, doms[0])} stroke={t === 0 ? c.axis : c.grid} /><text x={M.l - 6} y={Y(t, doms[0]) + 4} textAnchor="end" fill={c.muted} fontSize="11">{fmtTick(t, units[0])}</text></g>)}
        {units[1] && ticks(doms[1][0], doms[1][1]).map((t) => <text key={t} x={w - M.r + 6} y={Y(t, doms[1]) + 4} fill={c.muted} fontSize="11">{fmtTick(t, units[1])}</text>)}
        <text x={M.l - 6} y={9} textAnchor="end" fill={c.muted} fontSize="10">{UNITS[units[0]].label}</text>
        {units[1] && <text x={w - M.r + 6} y={9} fill={c.muted} fontSize="10">{UNITS[units[1]].label}</text>}
        {tickDates.map((t) => <text key={t} x={allPeriodic ? X(t) : Math.max(M.l, Math.min(w - M.r, X(t)))} y={H - 10} textAnchor="middle" fill={c.muted} fontSize="11">{tl(t)}</text>)}
        {series.filter((s) => kindOf(s) === "bar").map((s, bi) => s.pts.filter((p) => p.v != null).map((p) => { const dm = doms[ax(s)], y0 = Y(0, dm), y1 = Y(p.v as number, dm), x = X(p.t) - group / 2 + bi * (group / nBars) + 1; return <rect key={s.key + p.t} x={x} y={Math.min(y0, y1)} width={bw} height={Math.max(1, Math.abs(y1 - y0))} rx={Math.min(3, bw / 2)} fill={s.color} opacity={d && d !== p.t ? 0.55 : 1} />; }))}
        {series.filter((s) => kindOf(s) !== "bar").map((s) => {
          const dm = doms[ax(s)]; const segs: Pt[][] = []; let cur: Pt[] = [];
          s.pts.forEach((p) => { if (p.v == null) { if (cur.length) segs.push(cur); cur = []; } else cur.push(p); }); if (cur.length) segs.push(cur);
          const path = (g: Pt[]) => g.map((p, i) => `${i ? "L" : "M"}${X(p.t).toFixed(1)},${Y(p.v as number, dm).toFixed(1)}`).join("");
          return <g key={s.key}>{segs.map((g, i) => <g key={i}>{kind === "area" && <path d={`${path(g)}L${X(g[g.length - 1].t)},${Y(Math.max(dm[0], 0), dm)}L${X(g[0].t)},${Y(Math.max(dm[0], 0), dm)}Z`} fill={s.color} opacity=".16" />}<path d={path(g)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" /></g>)}
            {s.pts.filter((p) => p.v != null).length <= 24 && s.pts.filter((p) => p.v != null).map((p) => <circle key={p.t} cx={X(p.t)} cy={Y(p.v as number, dm)} r="4" fill={s.color} stroke={c.surface} strokeWidth="2" />)}</g>;
        })}
        {d && <line x1={X(d)} x2={X(d)} y1={M.t} y2={H - M.b} stroke={c.muted} strokeDasharray="3 3" />}
        {d && series.filter((s) => kindOf(s) !== "bar").map((s) => { const p = s.pts.find((q) => q.t === d); return p?.v != null ? <circle key={s.key} cx={X(d)} cy={Y(p.v, doms[ax(s)])} r="5" fill={s.color} stroke={c.surface} strokeWidth="2" /> : null; })}
      </svg>
      {d && <Tip x={X(d)} y={M.t} w={w}><b>{dlabel(d, labelOf.get(d))}</b>{series.map((s) => { const p = s.pts.find((q) => q.t === d); return <div key={s.key}><i style={{ background: s.color }} />{p?.v != null ? <strong>{fmtValue(p.v, s.unit)}</strong> : <strong>—</strong>}<span>{s.label}</span></div>; })}</Tip>}
    </div>
  );
}

/** Horizontal bars: the latest value of each series (or each slice of a breakdown), largest first. */
export function HBars({ rows, unit, c, w }: { rows: { key: string; label: string; v: number; color: string; note?: string }[]; unit: UnitId; c: Colors; w: number }) {
  const sorted = [...rows].sort((a, b) => b.v - a.v), mx = Math.max(...sorted.map((r) => Math.abs(r.v)), 1), lw = Math.min(150, w * 0.38), rh = 30;
  return <svg width={w} height={sorted.length * rh + 8} role="img" aria-label={"Latest values: " + sorted.map((r) => `${r.label} ${fmtValue(r.v, unit)}`).join("; ")}>
    {sorted.map((r, i) => <g key={r.key}><title>{`${r.label}: ${fmtValue(r.v, unit)}${r.note ? ". " + r.note : ""}`}</title>
      <text x={lw - 8} y={i * rh + 20} textAnchor="end" fill={c.text} fontSize="12">{r.label.length > 22 ? r.label.slice(0, 21) + "…" : r.label}</text>
      <rect x={lw} y={i * rh + 6} width={Math.max(2, (Math.abs(r.v) / mx) * (w - lw - 90))} height={18} rx="3" fill={r.color} />
      <text x={lw + Math.max(2, (Math.abs(r.v) / mx) * (w - lw - 90)) + 6} y={i * rh + 20} fill={c.text} fontSize="12">{fmtValue(r.v, unit)}</text></g>)}
  </svg>;
}

export function Pie({ cats, unit, c, w }: { cats: { name: string; value: number; note?: string }[]; unit: UnitId; c: Colors; w: number }) {
  const [hi, setHi] = useState<number | null>(null);
  const pos = cats.filter((x) => x.value > 0).sort((a, b) => b.value - a.value);
  const top = pos.slice(0, 7), rest = pos.slice(7), slices = rest.length ? [...top, { name: "Other", value: rest.reduce((s, x) => s + x.value, 0), note: rest.map((x) => x.name).join(", ") }] : top;
  const total = slices.reduce((s, x) => s + x.value, 0), size = Math.min(w, 260), R = size / 2 - 4;
  let a = 0;
  return <div className="gx-pie"><svg width={size} height={size} role="img" aria-label={"Breakdown: " + slices.map((s) => `${s.name} ${((s.value / total) * 100).toFixed(1)}%`).join("; ")}>
    {slices.map((s, i) => { const a0 = a, a1 = (a += (s.value / total) * Math.PI * 2), big = a1 - a0 > Math.PI ? 1 : 0, p = (r: number, t: number) => `${size / 2 + r * Math.sin(t)},${size / 2 - r * Math.cos(t)}`;
      const d = slices.length === 1 ? `M${size / 2},${size / 2 - R}A${R},${R} 0 1 1 ${size / 2 - 0.01},${size / 2 - R}Z` : `M${size / 2},${size / 2}L${p(R, a0)}A${R},${R} 0 ${big} 1 ${p(R, a1)}Z`;
      return <path key={s.name} d={d} fill={c.s[i % 8]} stroke={c.surface} strokeWidth="2" opacity={hi != null && hi !== i ? 0.6 : 1} tabIndex={0} onPointerEnter={() => setHi(i)} onPointerLeave={() => setHi(null)} onFocus={() => setHi(i)} onBlur={() => setHi(null)}><title>{`${s.name}: ${((s.value / total) * 100).toFixed(1)}% (${fmtValue(s.value, unit)})`}</title></path>; })}
  </svg><ul>{slices.map((s, i) => <li key={s.name} className={hi === i ? "on" : ""}><i style={{ background: c.s[i % 8] }} /><span>{s.name}</span><b>{((s.value / total) * 100).toFixed(1)}%</b>{s.note && <small>{s.note}</small>}</li>)}</ul>
    {cats.length !== pos.length && <p className="faint">{cats.length - pos.length} zero or negative item(s) left out of the pie.</p>}</div>;
}

export function Scatter({ xs, ys, labels, xl, yl, xu, yu, r, c, w }: { xs: number[]; ys: number[]; labels: string[]; xl: string; yl: string; xu: UnitId; yu: UnitId; r: number | null; c: Colors; w: number }) {
  const [hi, setHi] = useState<number | null>(null);
  const dx = domain(xs, false), dy = domain(ys, false), pw = w - M.l - 16, X = (v: number) => M.l + ((v - dx[0]) / (dx[1] - dx[0] || 1)) * pw;
  const fit = fitLine(xs, ys), near = (e: React.PointerEvent<SVGSVGElement>) => { const b = e.currentTarget.getBoundingClientRect(), px = e.clientX - b.left, py = e.clientY - b.top; let k = 0, best = Infinity; xs.forEach((x, i) => { const dd = (X(x) - px) ** 2 + (Y(ys[i], dy) - py) ** 2; if (dd < best) { best = dd; k = i; } }); setHi(k); };
  return <div className="gx-plot" onPointerLeave={() => setHi(null)}><svg width={w} height={H} tabIndex={0} role="img" aria-label={`Scatter of ${yl} against ${xl}, ${xs.length} points${r != null ? `, Pearson r ${r.toFixed(2)}` : ""}`} onPointerMove={near}
    onKeyDown={(e) => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); setHi((h) => Math.max(0, Math.min(xs.length - 1, (h ?? xs.length - 1) + (e.key === "ArrowRight" ? 1 : -1)))); } }}>
    {ticks(dy[0], dy[1]).map((t) => <g key={t}><line x1={M.l} x2={w - 16} y1={Y(t, dy)} y2={Y(t, dy)} stroke={c.grid} /><text x={M.l - 6} y={Y(t, dy) + 4} textAnchor="end" fill={c.muted} fontSize="11">{fmtTick(t, yu)}</text></g>)}
    {ticks(dx[0], dx[1], 5).map((t) => <text key={t} x={X(t)} y={H - 12} textAnchor="middle" fill={c.muted} fontSize="11">{fmtTick(t, xu)}</text>)}
    <text x={M.l + pw / 2} y={H - 0} textAnchor="middle" fill={c.muted} fontSize="10">{xl} ({UNITS[xu].label})</text><text x={M.l - 6} y={9} textAnchor="end" fill={c.muted} fontSize="10">{yl} ({UNITS[yu].label})</text>
    {fit && <line x1={X(dx[0])} x2={X(dx[1])} y1={Y(fit.intercept + fit.slope * dx[0], dy)} y2={Y(fit.intercept + fit.slope * dx[1], dy)} stroke={c.muted} strokeDasharray="5 4" strokeWidth="1.5" />}
    {xs.map((x, i) => <circle key={i} cx={X(x)} cy={Y(ys[i], dy)} r={hi === i ? 7 : 5} fill={c.s[0]} stroke={c.surface} strokeWidth="2" />)}
    {xs.length > 0 && <text x={X(xs[xs.length - 1]) + 8} y={Y(ys[ys.length - 1], dy) - 8} fill={c.text} fontSize="11">{labels[labels.length - 1]}</text>}
  </svg>{hi != null && <Tip x={X(xs[hi])} y={Y(ys[hi], dy) - 40} w={w}><b>{labels[hi]}</b><div><span>{xl}</span><strong>{fmtValue(xs[hi], xu)}</strong></div><div><span>{yl}</span><strong>{fmtValue(ys[hi], yu)}</strong></div></Tip>}</div>;
}

const hex = (h: string) => { const n = parseInt(h.replace("#", ""), 16); return [n >> 16, (n >> 8) & 255, n & 255]; };
const mix = (a: string, b: string, t: number) => { const x = hex(a), y = hex(b); return `rgb(${x.map((v, i) => Math.round(v + (y[i] - v) * t)).join(",")})`; };
const lum = (rgb: string) => { const v = rgb.match(/\d+/g)!.map(Number); return 0.299 * v[0] + 0.587 * v[1] + 0.114 * v[2]; };

/** Correlation matrix (diverging, neutral at 0) or period x measure grid (one hue, each row scaled on its own). */
export function Heat({ mode, labels, matrix, grid, cols, units, c, w }: { mode: "corr" | "grid"; labels: string[]; matrix?: Matrix; grid?: (number | null)[][]; cols?: string[]; units?: UnitId[]; c: Colors; w: number }) {
  const [hi, setHi] = useState<string | null>(null);
  const n = mode === "corr" ? labels.length : cols!.length, lw = Math.min(130, w * 0.3), cw = Math.max(28, Math.min(70, (w - lw - 8) / n)), rh = 34, top = mode === "grid" ? 26 : 8;
  return <div className="gx-plot"><svg width={Math.max(w, lw + cw * n + 8)} height={labels.length * rh + top + 8} role="img" aria-label={mode === "corr" ? "Correlation matrix: " + labels.join(", ") : "Values by period: " + labels.join(", ")}>
    {mode === "grid" && cols!.map((l, j) => <text key={l} x={lw + j * cw + cw / 2} y={16} textAnchor="middle" fill={c.muted} fontSize="10">{l.length > 8 ? l.slice(0, 8) : l}</text>)}
    {labels.map((l, i) => <g key={l + i}><text x={lw - 8} y={top + i * rh + 21} textAnchor="end" fill={c.text} fontSize="11">{l.length > 20 ? l.slice(0, 19) + "…" : l}</text>
      {Array.from({ length: n }, (_, j) => {
        let v: number | null, fill: string, txt: string, tip: string;
        if (mode === "corr") { v = matrix!.r[i][j]; fill = v == null ? c.grid : v >= 0 ? mix(c.mid, c.pos, v) : mix(c.mid, c.neg, -v); txt = v == null ? "n/a" : v.toFixed(2).replace("-", MINUS); tip = `${labels[i]} vs ${labels[j]}: ${v == null ? "not enough overlapping dates" : `r = ${txt} (${strength(v)}), ${matrix!.n[i][j]} dates`}`; }
        else { v = grid![i][j]; const row = grid![i].filter((x): x is number => x != null), lo = Math.min(...row), hh = Math.max(...row); fill = v == null ? c.grid : mix(c.mid, c.pos, hh === lo ? 0.5 : 0.1 + 0.8 * ((v - lo) / (hh - lo))); txt = v == null ? "—" : fmtTick(v, units![i]); tip = `${labels[i]}, ${cols![j]}: ${v == null ? "no value" : fmtValue(v, units![i])}`; }
        return <g key={j} tabIndex={0} onPointerEnter={() => setHi(tip)} onPointerLeave={() => setHi(null)} onFocus={() => setHi(tip)} onBlur={() => setHi(null)}><title>{tip}</title><rect x={lw + j * cw + 1} y={top + i * rh + 1} width={cw - 2} height={rh - 2} rx="3" fill={fill} /><text x={lw + j * cw + cw / 2} y={top + i * rh + 21} textAnchor="middle" fontSize="11" fill={lum(fill.startsWith("#") ? mix(fill, fill, 0) : fill) > 140 ? "#111" : "#fff"}>{txt}</text></g>;
      })}</g>)}
  </svg><p className="gx-hov" aria-live="polite">{hi ?? "Hover or focus a cell for details."}</p></div>;
}

export function Candles({ pts, c, w }: { pts: Pt[]; c: Colors; w: number }) {
  const [hi, setHi] = useState<number | null>(null);
  const d = pts.filter((p) => p.o != null && p.h != null && p.lo != null && p.v != null), dm = domain(d.flatMap((p) => [p.h as number, p.lo as number]), false), pw = w - M.l - 16, step = pw / d.length, cw = Math.max(1, Math.min(14, step * 0.6));
  const X = (i: number) => M.l + step * (i + 0.5);
  return <div className="gx-plot" onPointerLeave={() => setHi(null)}><svg width={w} height={H} tabIndex={0} role="img" aria-label={`Candlestick chart, ${d.length} trading days`} onPointerMove={(e) => setHi(Math.max(0, Math.min(d.length - 1, Math.floor((e.clientX - e.currentTarget.getBoundingClientRect().left - M.l) / step))))}
    onKeyDown={(e) => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); setHi((h) => Math.max(0, Math.min(d.length - 1, (h ?? d.length - 1) + (e.key === "ArrowRight" ? 1 : -1)))); } }}>
    {ticks(dm[0], dm[1]).map((t) => <g key={t}><line x1={M.l} x2={w - 16} y1={Y(t, dm)} y2={Y(t, dm)} stroke={c.grid} /><text x={M.l - 6} y={Y(t, dm) + 4} textAnchor="end" fill={c.muted} fontSize="11">{fmtTick(t, "inr")}</text></g>)}
    {d.filter((_, i) => i % Math.ceil(d.length / 5) === 0).map((p) => <text key={p.t} x={X(d.indexOf(p))} y={H - 10} textAnchor="middle" fill={c.muted} fontSize="11">{dlabel(p.t).replace(/ \d{4}$/, "")}</text>)}
    {d.map((p, i) => { const up = (p.v as number) >= (p.o as number), col = up ? c.gain : c.loss; return <g key={p.t}><line x1={X(i)} x2={X(i)} y1={Y(p.h as number, dm)} y2={Y(p.lo as number, dm)} stroke={col} strokeWidth="1.5" /><rect x={X(i) - cw / 2} y={Y(Math.max(p.o as number, p.v as number), dm)} width={cw} height={Math.max(1.5, Math.abs(Y(p.o as number, dm) - Y(p.v as number, dm)))} fill={up ? c.surface : col} stroke={col} strokeWidth="1.5" /></g>; })}
  </svg>{hi != null && d[hi] && <Tip x={X(hi)} y={M.t} w={w}><b>{dlabel(d[hi].t)}</b>{([["Open", d[hi].o], ["High", d[hi].h], ["Low", d[hi].lo], ["Close", d[hi].v]] as const).map(([k, v]) => <div key={k}><span>{k}</span><strong>{fmtValue(v, "inr")}</strong></div>)}</Tip>}
    <p className="gx-hov">Hollow candle: closed above its open. Filled: closed below.</p></div>;
}
