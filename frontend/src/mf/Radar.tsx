// Spider chart of the four parts (0 to 100). One or more outlines; the first is the fund, the others (category median, other funds) are drawn behind it.
import { PILLARS } from "../lib/mfScoreUp";

export type RadarSeries = { name: string; values: (number | null)[]; color: string; dashed?: boolean };
const R = 78, C = 100;
const pt = (i: number, v: number): [number, number] => { const a = -Math.PI / 2 + (i * 2 * Math.PI) / 4; return [C + Math.cos(a) * R * (v / 100), C + Math.sin(a) * R * (v / 100)]; };

export function Radar({ series, label }: { series: RadarSeries[]; label: string }) {
  const desc = series.map((s) => `${s.name}: ${PILLARS.map(([, n], i) => `${n} ${s.values[i] == null ? "none" : Math.round(s.values[i]!)}`).join(", ")}`).join(". ");
  return (
    <figure className="mfu-radar">
      <svg viewBox="-22 0 244 200" role="img" aria-label={`${label}. ${desc}`}>
        {[25, 50, 75, 100].map((g) => <polygon key={g} points={PILLARS.map((_, i) => pt(i, g).join(",")).join(" ")} fill="none" stroke="var(--border)" strokeWidth={g === 100 ? 1.2 : 0.7} />)}
        {PILLARS.map((_, i) => <line key={i} x1={C} y1={C} x2={pt(i, 100)[0]} y2={pt(i, 100)[1]} stroke="var(--border)" strokeWidth="0.7" />)}
        {[...series].reverse().map((s) => s.values.every((v) => v != null) && (
          <polygon key={s.name} points={s.values.map((v, i) => pt(i, v as number).join(",")).join(" ")} fill={s.dashed ? "none" : s.color} fillOpacity={s.dashed ? 0 : 0.14} stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? "5 3" : undefined} strokeLinejoin="round" />))}
        {series.map((s) => s.values.map((v, i) => v != null && <circle key={s.name + i} cx={pt(i, v)[0]} cy={pt(i, v)[1]} r="2.6" fill={s.color} />))}
        {PILLARS.map(([, n], i) => { const [x, y] = pt(i, 118); return <text key={n} x={x} y={y + 3} textAnchor="middle" className="mfu-rl">{n}</text>; })}
      </svg>
      <figcaption className="mfu-leg">{series.map((s) => <span key={s.name}><i style={{ background: s.dashed ? "transparent" : s.color, borderColor: s.color, borderStyle: s.dashed ? "dashed" : "solid" }} aria-hidden="true" />{s.name}</span>)}</figcaption>
    </figure>
  );
}
