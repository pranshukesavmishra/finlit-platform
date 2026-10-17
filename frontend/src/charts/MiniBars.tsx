import { useState } from "react";

export type BarSeries = { key: string; label: string; values: (number | null)[]; color: string };

/** Compact bar chart in plain SVG: single, grouped or stacked series; negatives drop below the baseline; hover or focus a column to read it.
 *  Colours come from the caller (theme tokens) so every chart on the page shares one palette. */
export function MiniBars({ labels, series, mode = "single", fmt, height = 150, highlight, dim = true, w = 300 }: {
  labels: string[]; series: BarSeries[]; mode?: "single" | "group" | "stack"; fmt: (v: number) => string; height?: number; highlight?: number; dim?: boolean; w?: number;
}) {
  const [hv, setHv] = useState<number | null>(null);
  const n = labels.length, W = w, H = height, pl = 46, pr = 6, pt = 12, pb = 24;
  const sums = labels.map((_, i) => series.map((s) => s.values[i] ?? 0));
  const pos = (i: number) => (mode === "stack" ? sums[i].filter((v) => v > 0).reduce((a, b) => a + b, 0) : Math.max(0, ...sums[i]));
  const neg = (i: number) => (mode === "stack" ? sums[i].filter((v) => v < 0).reduce((a, b) => a + b, 0) : Math.min(0, ...sums[i]));
  const hi = Math.max(...labels.map((_, i) => pos(i)), 1e-9), lo = Math.min(...labels.map((_, i) => neg(i)), 0);
  const span = hi - lo || 1, X = (i: number) => pl + (i + 0.5) * ((W - pl - pr) / n), Y = (v: number) => pt + (1 - (v - lo) / span) * (H - pt - pb);
  const bw = Math.min(26, ((W - pl - pr) / n) * 0.66), y0 = Y(0), k = series.length;
  const ticks = lo < 0 ? [lo, 0, hi] : [0, hi / 2, hi];
  const every = Math.ceil(n / Math.max(3, Math.floor((W - pl) / 38)));
  return (
    <div className="mb" onMouseLeave={() => setHv(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${series.map((s) => s.label).join(", ")} by period`}>
        {ticks.map((t, i) => <g key={i}><line x1={pl} x2={W - pr} y1={Y(t)} y2={Y(t)} stroke="var(--border)" strokeDasharray={t === 0 ? "" : "3 5"} /><text x={pl - 6} y={Y(t) + 3.5} textAnchor="end" fontSize="9.5" fill="var(--faint)" fontFamily="IBM Plex Mono, monospace">{fmt(t)}</text></g>)}
        {labels.map((l, i) => {
          const on = hv === i || (hv == null && (highlight == null || highlight === i)) || !dim, op = on ? 1 : 0.38;
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
                return <rect key={s.key} x={x} y={top} width={Math.max(1, w - (mode === "group" ? 1 : 0))} height={Math.max(1.5, bot - top)} rx={mode === "stack" ? 0 : 2.5} fill={fill} />;
              })}
              <rect x={X(i) - (W - pl - pr) / n / 2} y={pt} width={(W - pl - pr) / n} height={H - pt - pb} fill="transparent" tabIndex={0} onMouseEnter={() => setHv(i)} onFocus={() => setHv(i)} onBlur={() => setHv(null)} aria-label={`${l}: ${series.map((s) => `${s.label} ${s.values[i] == null ? "n/a" : fmt(s.values[i] as number)}`).join(", ")}`} style={{ outline: "none" }} />
            </g>
          );
        })}
        {labels.map((l, i) => ((n - 1 - i) % every === 0) && <text key={"l" + i} x={X(i)} y={H - 7} textAnchor="middle" fontSize="9.5" fill="var(--faint)">{l.replace(/^(\w{3}) (\d{2})(\d{2})$/, "$1 '$3")}</text>)}
      </svg>
      {hv != null && (
        <div className="mb-tip" style={{ left: `${Math.min(86, Math.max(14, (X(hv) / W) * 100))}%` }}>
          <b>{labels[hv]}</b>{series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}<em>{s.values[hv] == null ? "—" : fmt(s.values[hv] as number)}</em></span>)}
        </div>)}
    </div>
  );
}
