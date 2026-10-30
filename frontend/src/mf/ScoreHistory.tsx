// "Score over time": the final score as a line over band-coloured zones (35, 50, 65, 80), optional lines for the four parts, a hover tooltip and the
// "what changed since last month" sentence, all from the weekly rows the server stored. Gold; the server sends nothing below Gold.
import { useMemo, useState } from "react";
import { PILLARS, ZONES, useScoreHistory, type HistPoint, type PillarKey } from "../lib/mfScoreUp";
import { scoreText } from "../lib/mfScore";
import { dateIN } from "../lib/format";
import "../styles/mfup.css";

const W = 640, H = 240, L = 34, Rr = 12, T = 12, B = 26;
const PCOL: Record<PillarKey, string> = { performance: "var(--k1)", risk: "var(--k2)", cost: "var(--k3)", quality: "var(--k7)" };
const ZCOL = ["var(--band-lo)", "var(--band-lo)", "var(--band-mid)", "var(--band-hi)", "var(--band-hi)"];
const ZOP = [0.2, 0.1, 0.12, 0.1, 0.2];

export function HistoryChart({ points }: { points: HistPoint[] }) {
  const [on, setOn] = useState<Record<PillarKey, boolean>>({ performance: false, risk: false, cost: false, quality: false });
  const [hover, setHover] = useState<number | null>(null);
  const pts = useMemo(() => points.filter((p) => p.final != null), [points]);
  const t0 = pts.length ? Date.parse(pts[0].date) : 0, t1 = pts.length ? Date.parse(pts[pts.length - 1].date) : 1;
  const x = (d: string) => L + (t1 === t0 ? (W - L - Rr) / 2 : ((Date.parse(d) - t0) / (t1 - t0)) * (W - L - Rr));
  const y = (v: number) => T + (1 - v / 100) * (H - T - B);
  const line = (get: (p: HistPoint) => number | null) => pts.filter((p) => get(p) != null).map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(get(p)!).toFixed(1)}`).join("");
  const h = hover == null ? null : pts[hover];
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    let best = 0, bd = Infinity;
    pts.forEach((p, i) => { const d = Math.abs(x(p.date) - px); if (d < bd) { bd = d; best = i; } });
    setHover(best);
  };
  const ticks = pts.length > 1 ? [pts[0], pts[Math.floor(pts.length / 2)], pts[pts.length - 1]] : pts;
  return (
    <div className="mfu-hist">
      <div className="mfu-tog" role="group" aria-label="Lines to show">
        <span className="mfu-key"><i style={{ background: "var(--text)" }} aria-hidden="true" />Score</span>
        {PILLARS.map(([k, n]) => <label key={k} className={on[k] ? "on" : ""}><input type="checkbox" checked={on[k]} onChange={() => setOn({ ...on, [k]: !on[k] })} /><i style={{ background: PCOL[k] }} aria-hidden="true" />{n}</label>)}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Score over time, ${pts.length} weekly points, latest ${scoreText(pts[pts.length - 1]?.final)}`} onPointerMove={move} onPointerLeave={() => setHover(null)}>
        {ZONES.map(([n, a, b], i) => <g key={n}><rect x={L} y={y(b)} width={W - L - Rr} height={y(a) - y(b)} fill={ZCOL[i]} opacity={ZOP[i]} /><text x={W - Rr - 4} y={y(b) + 12} textAnchor="end" className="mfu-zl">{n}</text></g>)}
        {[0, 35, 50, 65, 80, 100].map((g) => <g key={g}><line x1={L} x2={W - Rr} y1={y(g)} y2={y(g)} stroke="var(--border)" strokeWidth="0.6" /><text x={L - 5} y={y(g) + 3} textAnchor="end" className="mfu-ax">{g}</text></g>)}
        {PILLARS.map(([k]) => on[k] && <path key={k} d={line((p) => p.pillars[k])} fill="none" stroke={PCOL[k]} strokeWidth="1.5" strokeDasharray="4 3" />)}
        <path d={line((p) => p.final)} fill="none" stroke="var(--text)" strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round" />
        {pts.map((p, i) => <circle key={p.week} cx={x(p.date)} cy={y(p.final!)} r={i === hover ? 5 : pts.length > 40 ? 0 : 3} fill="var(--bg)" stroke="var(--text)" strokeWidth="2" />)}
        {ticks.map((p) => <text key={p.week} x={x(p.date)} y={H - 7} textAnchor="middle" className="mfu-ax">{dateIN(p.date, { day: "numeric", month: "short", year: "2-digit" })}</text>)}
        {h && <line x1={x(h.date)} x2={x(h.date)} y1={T} y2={H - B} stroke="var(--border-strong)" strokeDasharray="3 3" />}
      </svg>
      {h && (
        <div className="mfu-tip" role="status" style={{ left: `${Math.min(78, Math.max(2, (x(h.date) / W) * 100 - 8))}%` }}>
          <b>{dateIN(h.date)}</b> Score {scoreText(h.final)} · {h.label}{h.status === "PROVISIONAL" ? " (provisional)" : ""}
          <small>{PILLARS.map(([k, n]) => `${n} ${scoreText(h.pillars[k])}`).join(" · ")}{h.rank ? ` · place ${h.rank} of ${h.rankOf}` : ""}</small>
        </div>)}
    </div>
  );
}

export function ScoreHistoryCard({ code = 0, kind = "mf", symbol = "" }: { code?: number; kind?: "mf" | "etf"; symbol?: string }) {
  const q = useScoreHistory(code, kind, symbol);
  const d = q.data;
  if (q.isLoading) return <section className="card mf-card mfu" aria-busy="true"><div className="skeleton" style={{ height: 200 }} /></section>;
  if (q.isError || !d || d.locked) return null;     // the score card above already carries the upgrade prompt
  const enough = d.points.filter((p) => p.final != null).length >= 2;
  return (
    <section className="card mf-card mfu" aria-label="Score over time">
      <div className="card-h"><h3>Score over time</h3><span className="s">Stored weekly · describes the past</span></div>
      {d.changes && <p className="mfu-change" data-testid="score-change"><b>What changed since last month.</b> {d.changes.text}</p>}
      {enough ? <HistoryChart points={d.points} /> : <p className="mfu-empty" role="status">{d.note || "Not enough history yet: the score is stored weekly."}</p>}
      {enough && !d.changes && <p className="faint mf-fine">A one-month comparison needs two stored rows at least three weeks apart.</p>}
    </section>
  );
}
