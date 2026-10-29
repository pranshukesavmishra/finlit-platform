import { useState } from "react";
import { MINUS, nf } from "../lib/format";
import { niceTicks, useWidth } from "./RoeLines";

export type WfBar = { key: string; label: [string, string]; narrow?: [string, string]; value: number; kind: "total" | "delta" };

/** Waterfall in plain SVG: the first ROE, one floating bar per factor (up or down, with the sign printed so colour is never the only signal), and the last ROE. */
export function Waterfall({ bars, ariaLabel, height = 250 }: { bars: WfBar[]; ariaLabel: string; height?: number }) {
  const [wrap, W] = useWidth();
  const [hv, setHv] = useState<number | null>(null);
  const n = bars.length, H = height, pl = 42, pr = 8, pt = 22, pb = 40;
  let run = 0;
  const geo = bars.map((b) => { const from = b.kind === "total" ? 0 : run, to = b.kind === "total" ? b.value : run + b.value; run = to; return { from, to }; });
  const all = geo.flatMap((g) => [g.from, g.to]), lo = Math.min(0, ...all), hi = Math.max(...all, 1), ticks = niceTicks(lo, hi), top = ticks[ticks.length - 1], bot = Math.min(lo, ticks[0]);
  const Y = (v: number) => pt + (1 - (v - bot) / (top - bot || 1)) * (H - pt - pb), step = (W - pl - pr) / n, X = (i: number) => pl + (i + 0.5) * step, bw = Math.min(46, step * 0.62);
  const tight = step < 72;   // narrow screens: shorter labels so neighbours never overlap
  const text = (b: WfBar) => (tight && b.kind === "delta" ? `${b.value > 0 ? "▲" : b.value < 0 ? "▼" : ""}${nf(b.value, 1)}` : b.kind === "total" ? `${b.value < 0 ? MINUS : ""}${nf(b.value, 1)}%` : `${b.value > 0 ? "▲ +" : b.value < 0 ? `▼ ${MINUS}` : ""}${nf(b.value, 1)} pp`);
  return (
    <div className="mb dp-chart" ref={wrap} onMouseLeave={() => setHv(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={ariaLabel}>
        {ticks.map((t) => <g key={t}><line x1={pl} x2={W - pr} y1={Y(t)} y2={Y(t)} stroke="var(--border)" strokeWidth={t === 0 ? 1.4 : 1} /><text x={pl - 6} y={Y(t) + 3.5} textAnchor="end" fontSize="10" fill="var(--faint)" fontFamily="IBM Plex Mono, monospace">{(t < 0 ? MINUS : "") + nf(t, 0)}</text></g>)}
        {bars.map((b, i) => {
          const g = geo[i], y1 = Y(Math.max(g.from, g.to)), y2 = Y(Math.min(g.from, g.to)), fill = b.kind === "total" ? "var(--info)" : b.value >= 0 ? "var(--gain)" : "var(--loss)";
          return (
            <g key={b.key} opacity={hv == null || hv === i ? 1 : 0.5}>
              {i > 0 && <line x1={X(i - 1) + bw / 2} x2={X(i) - bw / 2} y1={Y(geo[i - 1].to)} y2={Y(geo[i - 1].to)} stroke="var(--border-strong)" strokeDasharray="2 3" />}
              <rect x={X(i) - bw / 2} y={y1} width={bw} height={Math.max(2, y2 - y1)} rx={3} fill={fill} />
              <text x={X(i)} y={Math.max(11, y1 - 5)} textAnchor="middle" fontSize="10.5" fontWeight={600} fill="var(--text)" fontFamily="IBM Plex Mono, monospace">{text(b)}</text>
              <text x={X(i)} y={H - 22} textAnchor="middle" fontSize="10" fill="var(--muted)">{(tight && b.narrow ? b.narrow : b.label)[0]}</text>
              <text x={X(i)} y={H - 10} textAnchor="middle" fontSize="10" fill="var(--muted)">{(tight && b.narrow ? b.narrow : b.label)[1]}</text>
              <rect x={X(i) - step / 2} y={pt - 14} width={step} height={H - pt + 14} fill="transparent" tabIndex={0} style={{ outline: "none" }} onMouseEnter={() => setHv(i)} onFocus={() => setHv(i)} onBlur={() => setHv(null)} aria-label={`${b.label.join(" ")}: ${b.kind === "total" ? text(b) : `${b.value > 0 ? "up " : b.value < 0 ? "down " : ""}${nf(b.value, 1)} percentage points`}`} />
            </g>
          );
        })}
      </svg>
    </div>
  );
}
