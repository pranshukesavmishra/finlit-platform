import { useId, useState } from "react";
import { labelEvery } from "../lib/chartAxis";

export type LSeries = { key: string; label: string; color: string; values: (number | null)[] };

/** Smooth multi-line chart with grid, end labels, optional area and average line, and a hover read-out.
 *  Plain React SVG on a fixed viewBox that scales with its container. */
export function LineChart({ periods, series, fmt, height = 260, area = false, avg, avgLabel = "Average", domain }: {
  periods: string[]; series: LSeries[]; fmt: (v: number) => string; height?: number; area?: boolean; avg?: number | null; avgLabel?: string; domain?: [number, number];
}) {
  const id = useId().replace(/:/g, "");
  const [hover, setHover] = useState<number | null>(null);
  const W = 720, H = height, pl = 44, pr = series.length > 1 ? 92 : 28, pt = 18, pb = 30, n = periods.length;
  const all = series.flatMap((s) => s.values).filter((v): v is number => v != null);
  if (n < 2 || !all.length) return null;
  let lo = domain ? domain[0] : Math.min(...all), hi = domain ? domain[1] : Math.max(...all);
  if (avg != null) { lo = Math.min(lo, avg); hi = Math.max(hi, avg); }
  if (!domain) { const padv = (hi - lo || 1) * 0.15; lo = Math.max(0, lo - padv); hi = hi + padv; }
  const every = labelEvery(n, W - pl - pr, Math.max(...periods.map((p) => p.length), 1));
  const step = (hi - lo) / 4, X = (i: number) => pl + (i * (W - pl - pr)) / (n - 1), Y = (v: number) => pt + (1 - (v - lo) / (hi - lo || 1)) * (H - pt - pb);
  const path = (vals: (number | null)[]) => {
    const pts = vals.map((v, i) => (v == null ? null : ([X(i), Y(v)] as const)));
    let d = "", prev: readonly [number, number] | null = null;
    pts.forEach((p, i) => {
      if (!p) { prev = null; return; }
      if (!prev) d += `M${p[0]},${p[1]}`;
      else { const p0 = pts[i - 2] || prev, p3 = pts[i + 1] || p, c1x = prev[0] + (p[0] - p0[0]) / 6, c1y = prev[1] + (p[1] - p0[1]) / 6, c2x = p[0] - (p3[0] - prev[0]) / 6, c2y = p[1] - (p3[1] - prev[1]) / 6; d += `C${c1x},${c1y} ${c2x},${c2y} ${p[0]},${p[1]}`; }
      prev = p;
    });
    return d;
  };
  const ends = series.map((s) => { const li = s.values.map((v) => v != null).lastIndexOf(true); return { s, y: li < 0 ? 0 : Y(s.values[li] as number), v: li < 0 ? null : (s.values[li] as number) }; }).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 15) ends[i].y = ends[i - 1].y + 15;
  const onMove = (e: React.PointerEvent<SVGRectElement>) => { const r = e.currentTarget.getBoundingClientRect(); const x = ((e.clientX - r.left) / r.width) * (W - pl - pr); setHover(Math.max(0, Math.min(n - 1, Math.round((x / (W - pl - pr)) * (n - 1))))); };
  return (
    <div className="lc">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={series.map((s) => s.label).join(", ") + " over time"}>
        <defs>{series.map((s) => <linearGradient key={s.key} id={`${id}-${s.key}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={s.color} stopOpacity=".38" /><stop offset="1" stopColor={s.color} stopOpacity="0" /></linearGradient>)}</defs>
        {[0, 1, 2, 3, 4].map((k) => { const v = lo + step * k; return <g key={k}><line x1={pl} x2={W - pr} y1={Y(v)} y2={Y(v)} stroke="var(--border)" strokeDasharray={k ? "3 5" : ""} /><text x={pl - 8} y={Y(v) + 4} textAnchor="end" fontSize="10.5" fill="var(--faint)" fontFamily="IBM Plex Mono, monospace">{fmt(v)}</text></g>; })}
        {periods.map((p, i) => ((n - 1 - i) % every === 0) && <text key={p} x={X(i)} y={H - 8} textAnchor="middle" fontSize="10.5" fill="var(--faint)">{p}</text>)}
        {avg != null && <g><line x1={pl} x2={W - pr} y1={Y(avg)} y2={Y(avg)} stroke="var(--c2)" strokeDasharray="6 5" strokeWidth="1.6" /><text x={W - pr} y={Y(avg) - 6} textAnchor="end" fontSize="10.5" fontWeight="600" fill="var(--c2)">{avgLabel.toUpperCase()} {fmt(avg)}</text></g>}
        {series.map((s) => <g key={s.key}>
          {area && <path d={`${path(s.values)}L${X(n - 1)},${H - pb}L${X(0)},${H - pb}Z`} fill={`url(#${id}-${s.key})`} />}
          <path className="lc-line" pathLength={1} d={path(s.values)} fill="none" stroke={s.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ filter: `drop-shadow(0 4px 8px color-mix(in srgb, ${s.color} 45%, transparent))` }} />
          {s.values.map((v, i) => v != null && (n <= 14 || i === n - 1) && <circle key={i} cx={X(i)} cy={Y(v)} r={i === hover ? 6 : 3.6} fill="var(--s1)" stroke={s.color} strokeWidth="2.4" />)}
        </g>)}
        {series.length > 1 && ends.map(({ s, y, v }) => v != null && <text key={s.key} x={W - pr + 10} y={y + 4} fontSize="11.5" fontWeight="600" fill={s.color}>{s.label.split(" ")[0]} {fmt(v)}</text>)}
        {hover != null && <line x1={X(hover)} x2={X(hover)} y1={pt} y2={H - pb} stroke="var(--border-strong)" />}
        <rect x={pl} y={pt} width={W - pl - pr} height={H - pt - pb} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
      </svg>
      {hover != null && <div className="lc-tip" style={{ left: `${Math.min(88, Math.max(12, (X(hover) / W) * 100))}%` }}><b>{periods[hover]}</b>{series.map((s) => s.values[hover] != null && <span key={s.key}><i style={{ background: s.color }} />{s.label}<em>{fmt(s.values[hover] as number)}</em></span>)}</div>}
    </div>
  );
}
