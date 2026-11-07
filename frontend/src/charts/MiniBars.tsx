import { useEffect, useRef, useState } from "react";
import { labelEvery, niceTicks } from "../lib/chartAxis";
import { ChartZoom } from "../components/ChartZoom";

export type BarSeries = { key: string; label: string; values: (number | null)[]; color: string };

/** Compact bar chart in plain SVG: single, grouped or stacked series; negatives drop below the baseline; hover or focus a column to read it.
 *  Colours come from the caller (theme tokens) so every chart on the page shares one palette. */
export function MiniBars({ labels, series, mode = "single", fmt, height = 150, highlight, dim = true, w = 300, fit = false, tag = false, summary, zoomLabel }: {
  labels: string[]; series: BarSeries[]; mode?: "single" | "group" | "stack"; fmt: (v: number) => string; height?: number; highlight?: number; dim?: boolean; w?: number;
  /** Fill the parent box at real pixel size (readable text, wide bars) instead of scaling a fixed 300 x 150 drawing. */
  fit?: boolean;
  /** Fit mode, one series: a value tag above the highlighted bar. */
  tag?: boolean;
  /** Text alternative that carries the numbers. */
  summary?: string;
  /** Gives the chart the shared enlarge arrow. Left off for small tiles inside other cards. */
  zoomLabel?: string;
}) {
  const [hv, setHv] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  useEffect(() => {
    const el = box.current;
    if (!fit || !el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => { const r = el.getBoundingClientRect(); if (r.width > 0 && r.height > 0) setSize((o) => (o && Math.abs(o.w - r.width) < 1 && Math.abs(o.h - r.height) < 1 ? o : { w: Math.round(r.width), h: Math.round(r.height) })); });
    ro.observe(el); return () => ro.disconnect();
  }, [fit]);
  const n = labels.length, W = fit && size ? size.w : w, H = fit && size ? size.h : height;
  const fs = 11, pr = fit ? 4 : 6, pt = fit && tag ? 26 : fit ? 14 : 12, pb = fit ? 26 : 24;
  const sums = labels.map((_, i) => series.map((s) => s.values[i] ?? 0));
  const pos = (i: number) => (mode === "stack" ? sums[i].filter((v) => v > 0).reduce((a, b) => a + b, 0) : Math.max(0, ...sums[i]));
  const neg = (i: number) => (mode === "stack" ? sums[i].filter((v) => v < 0).reduce((a, b) => a + b, 0) : Math.min(0, ...sums[i]));
  let hi = Math.max(...labels.map((_, i) => pos(i)), 1e-9), lo = Math.min(...labels.map((_, i) => neg(i)), 0);
  const nice = fit ? niceTicks(lo, hi, H < 190 ? 3 : 4) : null;
  if (nice) { lo = nice[0]; hi = nice[nice.length - 1]; }
  const pl = fit ? Math.max(30, Math.max(...(nice as number[]).map((t) => fmt(t).length)) * 6.6 + 10) : 46;
  const span = hi - lo || 1, X = (i: number) => pl + (i + 0.5) * ((W - pl - pr) / n), Y = (v: number) => pt + (1 - (v - lo) / span) * (H - pt - pb);
  const bw = Math.min(fit ? 24 : 15, ((W - pl - pr) / n) * (fit ? 0.62 : 0.5)), y0 = Y(0), k = series.length;
  const ticks = nice ?? (lo < 0 ? [lo, 0, hi] : [0, hi / 2, hi]);
  const every = labelEvery(n, W - pl - pr, Math.max(...labels.map((l) => l.replace(/^(\w{3}) (\d{2})(\d{2})$/, "$1 '$3").length), 1), 6.8, fit ? 12 : 10);
  const chart = (
    <div className={"mb" + (fit ? " fit" : "")} ref={box} onMouseLeave={() => setHv(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary ?? `${series.map((s) => s.label).join(", ")} by period`}>
        {ticks.map((t, i) => <g key={i}><line x1={pl} x2={W - pr} y1={Y(t)} y2={Y(t)} stroke="var(--border)" strokeWidth={t === 0 ? 1.2 : 1} /><text x={pl - 6} y={Y(t) + 3.5} textAnchor="end" fontSize={fs} fill="var(--faint)" fontFamily="IBM Plex Mono, monospace">{fmt(t)}</text></g>)}
        {labels.map((l, i) => {
          const on = hv === i || (hv == null && (highlight == null || highlight === i)) || !dim, op = on ? 1 : fit ? 0.62 : 0.38;
          let acc = 0, accN = 0;
          return (
            <g key={l + i} opacity={op} style={{ transition: "opacity .15s" }}>
              {series.map((s, j) => {
                const v = s.values[i]; if (v == null) return null;
                let x = X(i) - bw / 2, w = bw, top: number, bot: number;
                if (mode === "group") { w = bw / k; x = X(i) - bw / 2 + j * w; top = v >= 0 ? Y(v) : y0; bot = v >= 0 ? y0 : Y(v); }
                else if (mode === "stack") { if (v >= 0) { bot = Y(acc); acc += v; top = Y(acc); } else { top = Y(accN); accN += v; bot = Y(accN); } }
                else { top = v >= 0 ? Y(v) : y0; bot = v >= 0 ? y0 : Y(v); }
                const fill = mode === "single" && v < 0 ? "var(--loss)" : s.color;
                return <rect key={s.key} x={x} y={top} width={Math.max(1, w - (mode === "group" ? 1 : 0))} height={Math.max(1.5, bot - top - (mode === "stack" ? 1.5 : 0))} rx={mode === "stack" ? 1 : 3.5} fill={fill} />;
              })}
              <rect x={X(i) - (W - pl - pr) / n / 2} y={pt} width={(W - pl - pr) / n} height={H - pt - pb} fill="transparent" tabIndex={0} onMouseEnter={() => setHv(i)} onFocus={() => setHv(i)} onBlur={() => setHv(null)} aria-label={`${l}: ${series.map((s) => `${s.label} ${s.values[i] == null ? "n/a" : fmt(s.values[i] as number)}`).join(", ")}`} style={{ outline: "none" }} />
            </g>
          );
        })}
        {labels.map((l, i) => ((n - 1 - i) % every === 0) && <text key={"l" + i} x={fit && X(i) + (l.length > 6 ? 17 : 11) > W ? W - 1 : X(i)} y={H - (fit ? 8 : 7)} textAnchor={fit && X(i) + (l.length > 6 ? 17 : 11) > W ? "end" : "middle"} fontSize={fs} fill="var(--faint)">{l.replace(/^(\w{3}) (\d{2})(\d{2})$/, "$1 '$3")}</text>)}
        {fit && tag && mode === "single" && highlight != null && series[0]?.values[highlight] != null && hv == null && (() => {
          const v = series[0].values[highlight] as number, t = fmt(v), tw = t.length * 6.8 + 14, cx = Math.min(W - 2 - tw / 2, Math.max(pl + tw / 2, X(highlight))), ty = (v >= 0 ? Y(v) : y0) - 21;
          return <g pointerEvents="none"><rect x={cx - tw / 2} y={Math.max(1, ty)} width={tw} height={18} rx={6} fill={`color-mix(in srgb, ${series[0].color} 24%, var(--bg-surface))`} stroke={series[0].color} strokeWidth={1} /><text x={cx} y={Math.max(1, ty) + 12.5} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--text-primary)" fontFamily="IBM Plex Mono, monospace">{t}</text></g>;
        })()}
      </svg>
      {hv != null && (
        <div className="mb-tip" style={{ left: `${Math.min(86, Math.max(14, (X(hv) / W) * 100))}%` }}>
          <b>{labels[hv]}</b>{series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}<em>{s.values[hv] == null ? "—" : fmt(s.values[hv] as number)}</em></span>)}
        </div>)}
    </div>
  );
  return zoomLabel ? <ChartZoom label={zoomLabel}>{chart}</ChartZoom> : chart;
}
