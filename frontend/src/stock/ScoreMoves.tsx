// "How the scores have moved" on the stock page: the four Prism scores (0 to 100) and the two technical views (−100 to +100) in one place.
// Choose what to plot (all six, the business scores only, the technical views only, or any single line from the key), one point per day or per week,
// and the period. The four business scores move in steps, only when Prism re-rates the company (marked); the technical views update every trading evening.
// Gold, like the report. It describes how the scores moved; it never forecasts and is not a recommendation.
import { useContext, useMemo, useState } from "react";
import { Icon } from "../lib/icons";
import { dateIN, MINUS } from "../lib/format";
import { useGold } from "../lib/premium";
import { OpenAccess } from "../components/Gate";
import { toWeekly, usePrismHistory, valueOf, withValue, type HistPoint, type Series } from "../lib/prismHistory";
import { BUSINESS, NAME, PERIODS, TECHNICAL, inPeriod, moveSentence, movesOf, readingNow, reRated, seriesFor, type Period, type Show } from "../lib/scoreMoves";
import "../styles/scoremoves.css";

const COLOR: Record<Series, string> = { final: "var(--text)", ["fundamental"]: "var(--p-growth)", valuation: "var(--p-quality)", quality: "var(--p-profit)", risk: "var(--p-balance)", shortTerm: "var(--gold)", longTerm: "var(--info)" };
const W = 720, L = 42, R = 16;
const fmt = (v: number | null, signed = false) => (v == null ? MINUS : (signed && v > 0 ? "+" : "") + String(Math.round(v * 10) / 10).replace("-", MINUS));

function Panel({ points, series, lo, hi, ticks, h, marks, label, signed }: { points: HistPoint[]; series: Series[]; lo: number; hi: number; ticks: number[]; h: number; marks: string[]; label: string; signed: boolean }) {
  const T = 10, B = 22, days = points.map((p) => Date.parse(p.day)), t0 = days[0], t1 = days[days.length - 1];
  const x = (d: string) => L + (t1 === t0 ? (W - L - R) / 2 : ((Date.parse(d) - t0) / (t1 - t0)) * (W - L - R));
  const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (h - T - B);
  const [hover, setHover] = useState<number | null>(null);
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    let best = 0, bd = Infinity; points.forEach((p, i) => { const d = Math.abs(x(p.day) - px); if (d < bd) { bd = d; best = i; } }); setHover(best);
  };
  const axis = points.length > 1 ? [points[0], points[points.length - 1]] : points, hp = hover == null ? null : points[hover];
  return (
    <div className="scm-panel">
      <svg viewBox={`0 0 ${W} ${h}`} role="img" aria-label={`${label}, ${points.length} days recorded`} onPointerMove={move} onPointerLeave={() => setHover(null)}>
        {ticks.map((g) => <g key={g}><line x1={L} x2={W - R} y1={y(g)} y2={y(g)} stroke="var(--border)" strokeWidth={g === 0 && signed ? 1.2 : 0.6} /><text x={L - 6} y={y(g) + 3} textAnchor="end" className="scm-ax">{fmt(g)}</text></g>)}
        {signed && <rect x={L} width={W - L - R} y={y(20)} height={y(-20) - y(20)} fill="var(--gold)" opacity=".07" />}
        {marks.map((d) => <g key={d}><line x1={x(d)} x2={x(d)} y1={T} y2={h - B} stroke="var(--gold)" strokeDasharray="2 3" /><path d={`M${x(d) - 4},${h - B + 8} l4,-7 l4,7z`} fill="var(--gold-deep, var(--gold))"><title>{`Prism re-rated on ${dateIN(d)}`}</title></path></g>)}
        {series.map((s) => { const v = withValue(points, s); if (!v.length) return null;
          return <g key={s}><path d={v.map((p, i) => `${i ? "L" : "M"}${x(p.day).toFixed(1)},${y(valueOf(p, s)!).toFixed(1)}`).join("")} fill="none" stroke={COLOR[s]} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
            <circle cx={x(v[v.length - 1].day)} cy={y(valueOf(v[v.length - 1], s)!)} r="3" fill="var(--bg)" stroke={COLOR[s]} strokeWidth="1.8" /></g>; })}
        {axis.map((p, i) => <text key={p.day} x={x(p.day)} y={h - 5} textAnchor={axis.length > 1 && i === 0 ? "start" : axis.length > 1 ? "end" : "middle"} className="scm-ax">{dateIN(p.day, { day: "numeric", month: "short" })}</text>)}
        {hp && <line x1={x(hp.day)} x2={x(hp.day)} y1={T} y2={h - B} stroke="var(--border-strong)" strokeDasharray="3 3" />}
      </svg>
      {hp && <div className="scm-tip" role="status"><b>{dateIN(hp.day)}</b>{series.map((s) => <span key={s}><i style={{ background: COLOR[s] }} />{NAME[s]} {fmt(valueOf(hp, s), signed)}</span>)}</div>}
    </div>);
}

export function ScoreMoves({ points: all }: { points: HistPoint[] }) {
  const [show, setShow] = useState<Show>("all"), [step, setStep] = useState<"day" | "week">("day"), [period, setPeriod] = useState<Period>("3M"), [off, setOff] = useState<Series[]>([]);
  const base = useMemo(() => inPeriod(step === "week" ? toWeekly(all) : all, period), [all, step, period]);
  const chosen = seriesFor(show), visible = chosen.filter((s) => !off.includes(s));
  const biz = visible.filter((s) => BUSINESS.includes(s)), tech = visible.filter((s) => TECHNICAL.includes(s));
  const latest = all[all.length - 1], marks = useMemo(() => reRated(base), [base]);
  const moves = movesOf(base, visible);
  const toggle = (s: Series) => setOff((o) => (o.includes(s) ? o.filter((x) => x !== s) : [...o, s]));
  const pick = (k: Show) => { setShow(k); setOff([]); };
  return (
    <div className="scm">
      <div className="scm-ctl">
        <div className="seg" role="group" aria-label="Show">{([["all", "All six"], ["business", "Business only"], ["technical", "Technical only"]] as const).map(([k, l]) => <button key={k} type="button" aria-pressed={show === k} onClick={() => pick(k)}>{l}</button>)}</div>
        <div className="seg" role="group" aria-label="Points">{([["day", "Daily"], ["week", "Weekly"]] as const).map(([k, l]) => <button key={k} type="button" aria-pressed={step === k} onClick={() => setStep(k)}>{l}</button>)}</div>
        <div className="seg" role="group" aria-label="Period">{PERIODS.map((p) => <button key={p.id} type="button" aria-pressed={period === p.id} onClick={() => setPeriod(p.id)}>{p.id}</button>)}</div>
      </div>
      <p className="scm-sum" aria-live="polite">{biz.length && tech.length ? `${moveSentence(base, biz, period)} ${moveSentence(base, tech, period).replace(/^Over the last [^,]+, the/, "The")}` : moveSentence(base, visible, period)}</p>
      <div className="scm-keys">
        {BUSINESS.some((s) => chosen.includes(s)) && <div role="group" aria-label="Business scores, 0 to 100"><small>BUSINESS SCORES · 0 TO 100</small>
          {BUSINESS.filter((s) => chosen.includes(s)).map((s) => <button key={s} type="button" className={"scm-key" + (off.includes(s) ? " off" : "")} aria-pressed={!off.includes(s)} onClick={() => toggle(s)}><i style={{ background: COLOR[s] }} />{NAME[s]} <b>{fmt(latest ? valueOf(latest, s) : null)}</b></button>)}</div>}
        {TECHNICAL.some((s) => chosen.includes(s)) && <div role="group" aria-label="Technical views, −100 to +100"><small>TECHNICAL VIEWS · −100 TO +100</small>
          {TECHNICAL.filter((s) => chosen.includes(s)).map((s) => <button key={s} type="button" className={"scm-key" + (off.includes(s) ? " off" : "")} aria-pressed={!off.includes(s)} onClick={() => toggle(s)}><i style={{ background: COLOR[s] }} />{NAME[s]} <b>{fmt(latest ? valueOf(latest, s) : null, true)}</b></button>)}</div>}
      </div>
      {visible.length === 0 ? <p className="faint scm-empty">No line is selected. Tick a score above to draw it.</p> : base.length < 2 ? <p className="faint scm-empty">Only one recorded day falls in this period, so there is no line to draw yet. Try a longer period.</p> : (
        <>
          {biz.length > 0 && <Panel points={base} series={biz} lo={0} hi={100} ticks={[0, 25, 50, 75, 100]} h={biz.length && tech.length ? 190 : 240} marks={marks} label="Business scores over time" signed={false} />}
          {tech.length > 0 && <Panel points={base} series={tech} lo={-100} hi={100} ticks={[-100, -50, 0, 50, 100]} h={biz.length ? 150 : 230} marks={[]} label="Technical views over time" signed />}
          <p className="scm-note"><Icon name="info" /><span>Business scores change only when Prism re-rates the company (▲), so they move in steps. Technical views update every trading evening: short term reads the last 5 to 20 sessions, long term the last 6 to 18 months. Valuation: higher means cheaper. Risk: higher means lower risk.</span></p>
          {moves.length > 0 && <div className="tw"><table className="qtt scm-t"><caption>Change since {dateIN(moves[0].fromDay)}</caption>
            <thead><tr><th>Score</th><th className="num">Start</th><th className="num">Now</th><th className="num">Change</th><th>Reading now</th></tr></thead>
            <tbody>{moves.map((m) => <tr key={m.s}><td><i style={{ background: COLOR[m.s] }} />{NAME[m.s]}</td><td className="num">{fmt(m.from, m.s === "shortTerm" || m.s === "longTerm")}</td><td className="num">{fmt(m.to, m.s === "shortTerm" || m.s === "longTerm")}</td><td className="num">{fmt(m.delta, true)}</td><td>{readingNow(m.s, m.to)}</td></tr>)}</tbody></table></div>}
        </>)}
    </div>);
}

export function ScoreMovesCard({ symbol, statement }: { symbol: string; statement: string }) {
  const gold = useGold(), open = useContext(OpenAccess);
  const q = usePrismHistory(symbol, statement, gold || open);
  if (q.isError || (!q.data && !q.isLoading)) return null;   // the server and this page disagree about the plan: say nothing rather than show a lock to a member
  const all = q.data?.points ?? [];
  return (
    <section className="card acc scm-card" id="scores-moved" aria-label="How the scores have moved">
      <div className="card-h"><h3><span className="ci"><Icon name="gauge" /></span>How the scores have moved</h3>{all.length > 0 && <span className="s">As of {dateIN(all[all.length - 1].day)}</span>}</div>
      {q.isLoading ? <div className="skeleton" style={{ height: 200 }} /> : all.length < 2 ? <p className="faint scm-empty">{q.data?.note || "The history starts on the day recording began; there are not yet enough days to draw it."}</p> : <ScoreMoves points={all} />}
      <p className="faint scm-foot">One point for each day a figure was worked out (Weekly shows the last day recorded in each week); the history starts on the day recording began and earlier days are not estimated. It describes how the scores moved; it is not a forecast or a recommendation. Information only, not investment advice.</p>
    </section>);
}
