// "Prism score over time" on the stock page, under the pros and cons: the score and its four parts (0 to 100), or the two technical views (−100 to +100), one
// point per day a figure was worked out. Gold, like the report; the server sends nothing below Gold. It describes how the score moved; it never forecasts.
import { useContext, useMemo, useState } from "react";
import { Icon } from "../lib/icons";
import { dateIN, MINUS } from "../lib/format";
import { useGold } from "../lib/premium";
import { OpenAccess } from "../components/Gate";
import { changeOver, emptyReason, modelChanges, toWeekly, usePrismHistory, valueOf, withValue, type HistPoint, type Series } from "../lib/prismHistory";
import { PRISM_PARTS } from "./prismWords";

const W = 640, H = 230, L = 40, R = 14, T = 12, B = 28;
type View = "score" | "technical";
const LINES: Record<View, { s: Series; name: string; color: string; w: number; on: boolean }[]> = {
  score: [{ s: "final", name: "Prism score", color: "var(--text)", w: 2.4, on: true }, ...PRISM_PARTS.map(([k, name, , v]) => ({ s: k as Series, name, color: `var(${v})`, w: 1.5, on: false }))],
  technical: [{ s: "shortTerm", name: "Short term", color: "var(--gold)", w: 2.2, on: true }, { s: "longTerm", name: "Long term", color: "var(--text)", w: 2.2, on: true }],
};
const fmt = (v: number | null, signed = false) => (v == null ? MINUS : (signed && v > 0 ? "+" : "") + String(Math.round(v * 10) / 10).replace("-", MINUS));

export function HistoryChart({ points, view }: { points: HistPoint[]; view: View }) {
  const defs = LINES[view];
  const [shown, setShown] = useState<Record<string, boolean>>(() => Object.fromEntries(Object.values(LINES).flat().map((l) => [l.s, l.on])));
  const [hover, setHover] = useState<number | null>(null);
  const [lo, hi] = view === "score" ? [0, 100] : [-100, 100];
  const days = useMemo(() => points.map((p) => Date.parse(p.day)), [points]);
  const t0 = days[0] ?? 0, t1 = days[days.length - 1] ?? 1;
  const x = (d: string) => L + (t1 === t0 ? (W - L - R) / 2 : ((Date.parse(d) - t0) / (t1 - t0)) * (W - L - R));
  const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const path = (s: Series) => withValue(points, s).map((p, i) => `${i ? "L" : "M"}${x(p.day).toFixed(1)},${y(valueOf(p, s)!).toFixed(1)}`).join("");
  const ticks = view === "score" ? [0, 25, 50, 75, 100] : [-100, -50, 0, 50, 100];
  const changes = modelChanges(points);
  const h = hover == null ? null : points[hover];
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    let best = 0, bd = Infinity;
    points.forEach((p, i) => { const d = Math.abs(x(p.day) - px); if (d < bd) { bd = d; best = i; } });
    setHover(best);
  };
  const axis = points.length > 1 ? [points[0], points[Math.floor(points.length / 2)], points[points.length - 1]] : points;
  return (
    <div className="phx">
      <div className="phx-tog" role="group" aria-label="Lines to show">
        {defs.map((l) => (
          <label key={l.s} className={shown[l.s] ? "on" : ""}>
            <input type="checkbox" checked={!!shown[l.s]} disabled={l.s === defs[0].s} onChange={() => setShown({ ...shown, [l.s]: !shown[l.s] })} />
            <i style={{ background: l.color }} aria-hidden="true" />{l.name}
          </label>))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${view === "score" ? "Prism score" : "Technical views"} over time, ${points.length} days recorded`} onPointerMove={move} onPointerLeave={() => setHover(null)}>
        {ticks.map((g) => <g key={g}><line x1={L} x2={W - R} y1={y(g)} y2={y(g)} stroke="var(--border)" strokeWidth={g === 0 && view === "technical" ? 1.1 : 0.6} /><text x={L - 6} y={y(g) + 3} textAnchor="end" className="phx-ax">{fmt(g)}</text></g>)}
        {changes.map((c) => <g key={c.day}><line x1={x(c.day)} x2={x(c.day)} y1={T} y2={H - B} stroke="var(--gold)" strokeDasharray="2 3" /><title>{`Model version changed on ${dateIN(c.day)}: ${c.from} to ${c.to}`}</title></g>)}
        {defs.filter((l) => shown[l.s]).map((l) => <path key={l.s} d={path(l.s)} fill="none" stroke={l.color} strokeWidth={l.w} strokeLinejoin="round" strokeLinecap="round" />)}
        {defs.filter((l) => shown[l.s]).flatMap((l) => withValue(points, l.s).map((p) => <circle key={l.s + p.day} cx={x(p.day)} cy={y(valueOf(p, l.s)!)} r={points.length > 40 ? 0 : 2.6} fill="var(--bg)" stroke={l.color} strokeWidth="1.6" />))}
        {axis.map((p, i) => <text key={p.day} x={x(p.day)} y={H - 8} textAnchor={axis.length > 1 && i === 0 ? "start" : axis.length > 1 && i === axis.length - 1 ? "end" : "middle"} className="phx-ax">{dateIN(p.day, { day: "numeric", month: "short", year: "2-digit" })}</text>)}
        {h && <line x1={x(h.day)} x2={x(h.day)} y1={T} y2={H - B} stroke="var(--border-strong)" strokeDasharray="3 3" />}
      </svg>
      {h && (
        <div className="phx-tip" role="status">
          <b>{dateIN(h.day)}</b>
          {defs.filter((l) => shown[l.s]).map((l) => <span key={l.s}>{l.name} {fmt(valueOf(h, l.s), view === "technical")}</span>)}
          {h.modelVersion && <small>Model {h.modelVersion}</small>}
        </div>)}
      {changes.length > 0 && <p className="phx-note"><Icon name="info" /><span>The dashed gold line marks a day the model version changed ({changes.map((c) => dateIN(c.day, { day: "numeric", month: "short" })).join(", ")}): a jump there can come from the new formula, not from the business.</span></p>}
      <details className="phx-table"><summary>Show as table</summary>
        <div className="tw"><table className="qtt"><thead><tr><th>Day</th>{defs.map((l) => <th key={l.s}>{l.name}</th>)}</tr></thead>
          <tbody>{[...points].reverse().map((p) => <tr key={p.day}><td>{dateIN(p.day)}</td>{defs.map((l) => <td key={l.s} className="num">{fmt(valueOf(p, l.s), view === "technical")}</td>)}</tr>)}</tbody></table></div>
      </details>
    </div>
  );
}

export function PrismHistoryCard({ symbol, statement }: { symbol: string; statement: string }) {
  const gold = useGold(), open = useContext(OpenAccess);
  const q = usePrismHistory(symbol, statement, gold || open);
  const [view, setView] = useState<View>("score");
  const [step, setStep] = useState<"day" | "week">("day");
  if (q.isError || (!q.data && !q.isLoading)) return null;           // the server and this page disagree about the plan: say nothing rather than show a lock to a member
  const all = q.data?.points ?? [];
  const points = step === "week" ? toWeekly(all) : all;      // weekly: the last day recorded in each week, as recorded
  const main: Series = view === "score" ? "final" : "shortTerm";
  const why = emptyReason(points, main);
  const ch = changeOver(points, main);
  return (
    <section className="card acc phx-card" id="prism-history" aria-label="FinLit Prism score over time">
      <div className="card-h"><h3><span className="ci"><Icon name="gauge" /></span>FinLit Prism: score over time</h3>
        <div className="seg" role="group" aria-label="One point for each">{([["day", "Daily"], ["week", "Weekly"]] as const).map(([k, l]) => <button key={k} aria-pressed={step === k} onClick={() => setStep(k)}>{l}</button>)}</div>
        <div className="seg" role="tablist" aria-label="What to plot">{([["score", "Prism score"], ["technical", "Technical views"]] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={view === k} aria-pressed={view === k} onClick={() => setView(k)}>{l}</button>)}</div></div>
      {q.isLoading ? <div className="skeleton" style={{ height: 160 }} /> : why ? <p className="faint phx-empty">{why}</p> : (
        <>
          {ch && <p className="phx-sum">{view === "score" ? "Prism score" : "Short-term view"} moved from {fmt(valueOf(withValue(points, main)[0], main), view === "technical")} on {dateIN(ch.from)} to {fmt(valueOf(withValue(points, main).slice(-1)[0], main), view === "technical")} on {dateIN(ch.to)} ({fmt(ch.delta, true)} points).</p>}
          <HistoryChart points={points} view={view} />
        </>)}
      <p className="faint phx-foot">One point for each day a figure was worked out (Weekly shows the last day recorded in each week); the history starts on the day recording began and earlier days are not estimated. It describes how the score moved; it is not a forecast. Describes the company's financial health from its filings and prices; not a recommendation. Information only, not investment advice.</p>
    </section>
  );
}
