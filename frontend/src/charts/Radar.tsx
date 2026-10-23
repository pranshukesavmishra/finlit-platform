import { useId } from "react";
import { With3D } from "./With3D";

export type RadarSeries = { key: string; label: string; values: (number | null)[]; cls: string };

/** Spider chart on a fixed 0–100 scale. Series are drawn as translucent polygons with distinct markers, so colour is never the only cue. */
export function Radar({ axes, series, size = 360 }: { axes: string[]; series: RadarSeries[]; size?: number }) {
  const id = useId().replace(/:/g, "");
  const C = size / 2, R = size / 2 - 58, n = axes.length;
  const pt = (i: number, v: number): [number, number] => { const a = (i / n) * Math.PI * 2 - Math.PI / 2; return [C + (R * v) / 100 * Math.cos(a), C + (R * v) / 100 * Math.sin(a)]; };
  const ring = (v: number) => axes.map((_, i) => pt(i, v).join(",")).join(" ");
  const mark = (cls: string, x: number, y: number) => {
    const k = cls.replace("k", "");
    return k === "0" ? <circle cx={x} cy={y} r="4.5" /> : k === "1" ? <rect x={x - 4} y={y - 4} width="8" height="8" /> : k === "2" ? <path d={`M${x} ${y - 5.5}L${x + 5.5} ${y}L${x} ${y + 5.5}L${x - 5.5} ${y}Z`} /> : <path d={`M${x} ${y - 5.5}L${x + 5} ${y + 4}L${x - 5} ${y + 4}Z`} />;
  };
  const flat = (
    <svg className="radar" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Radar chart of ${axes.join(", ")} for ${series.map((s) => s.label).join(" and ")}`}>
      <defs><radialGradient id={`rg${id}`}><stop offset="0" stopColor="var(--gold)" stopOpacity=".16" /><stop offset="1" stopColor="var(--gold)" stopOpacity="0" /></radialGradient></defs>
      <circle cx={C} cy={C} r={R + 10} fill={`url(#rg${id})`} />
      {[25, 50, 75, 100].map((v) => <polygon key={v} points={ring(v)} fill="none" stroke="var(--border-strong)" strokeDasharray={v === 100 ? "" : "2 5"} opacity={v === 100 ? 0.9 : 0.6} />)}
      {axes.map((a, i) => { const [x, y] = pt(i, 100), [lx, ly] = pt(i, 118), anchor = Math.abs(lx - C) < 6 ? "middle" : lx > C ? "start" : "end"; return (
        <g key={a}><line x1={C} y1={C} x2={x} y2={y} stroke="var(--border)" /><text x={lx} y={ly + 4} textAnchor={anchor} fontSize="11.5" fontWeight="600" fill="var(--muted)" fontFamily="IBM Plex Sans, sans-serif">{a}</text></g>); })}
      {[50, 100].map((v) => <text key={v} x={C + 4} y={C - (R * v) / 100 + 11} fontSize="9" fill="var(--faint)" fontFamily="IBM Plex Mono, monospace">{v}</text>)}
      {series.map((s) => (
        <g key={s.key} className={"rs " + s.cls}>
          <polygon className="rs-p" points={s.values.map((v, i) => pt(i, v ?? 0).join(",")).join(" ")} />
          {s.values.map((v, i) => v != null && <g key={i} className="rs-m">{mark(s.cls, ...pt(i, v))}<title>{`${s.label}, ${axes[i]}: ${v}`}</title></g>)}
        </g>))}
    </svg>
  );
  return <With3D flat={flat} label={`Radar chart of ${axes.join(", ")} in 3D`}
    hint="How to read it: each spoke is one measure from 0 at the centre to 100 at the outer ring. A bigger shape means higher scores. Move the pointer over a dot to read it."
    spec={{ kind: "radar", axes, series: series.map((s) => ({ label: s.label, values: s.values })) }} />;
}
