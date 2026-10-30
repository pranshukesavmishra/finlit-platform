// Score and the four parts of two to four funds side by side (Fund Compare): score rings, a radar overlay, the measure table with ahead / level / behind
// per part (level means within LEVEL_TOLERANCE points), and the score lines over time. Gold; below that the rows show a lock and no value is requested.
import { Link } from "react-router";
import { useUI } from "../lib/ui";
import { Icon } from "../lib/icons";
import { MF_METHOD_URL, MF_SCORE_COMPLIANCE, MF_SCORE_NAME, bandOf, scoreText, useScores, type ScoreItem } from "../lib/mfScore";
import { LEVEL_TOLERANCE, PILLARS, compareTo, useManyHistory } from "../lib/mfScoreUp";
import { Radar } from "./Radar";
import { ScoreRing } from "./ScoreCard";
import { dateIN } from "../lib/format";
import "../styles/mfup.css";

const COLORS = ["var(--gold)", "var(--k1)", "var(--k2)", "var(--k3)"];
const WORD = { ahead: "ahead", level: "level", behind: "behind", na: "" } as const;
const cellOf = (locked: boolean, v: number | null | undefined, why?: string | null) =>
  locked ? <span className="mf-na" title="Part of the Gold plan"><Icon name="lock" /><span className="sr-only">Locked: Gold plan</span></span>
    : v == null ? <span className="mf-na" title={why || "No score"}>—</span> : <b className={"mfs-pv b-" + bandOf(v)}>{scoreText(v)}</b>;

function Lines({ codes, names }: { codes: number[]; names: string[] }) {
  const h = useManyHistory(codes);
  const series = codes.map((c) => (h.data?.series?.[`mf:${c}`] || []).filter((p) => p.final != null));
  const all = series.flat();
  if (!h.data || all.length < 2 || series.every((s) => s.length < 2)) return <p className="mfu-empty" role="status">Score history: not enough history yet. The score is stored weekly{all.length ? ` from ${dateIN(all[0].date)}` : ""}.</p>;
  const t = all.map((p) => Date.parse(p.date)), t0 = Math.min(...t), t1 = Math.max(...t);
  const lo = Math.max(0, Math.floor(Math.min(...all.map((p) => p.final!)) / 10) * 10 - 5), hi = Math.min(100, Math.ceil(Math.max(...all.map((p) => p.final!)) / 10) * 10 + 5);
  const X = (d: string) => 30 + (t1 === t0 ? 280 : ((Date.parse(d) - t0) / (t1 - t0)) * 560), Y = (v: number) => 10 + (1 - (v - lo) / (hi - lo)) * 140;
  return (
    <figure className="mfu-lines">
      <svg viewBox="0 0 600 170" role="img" aria-label={`Score over time. ${codes.map((_, i) => `${names[i]}: ${scoreText(series[i][series[i].length - 1]?.final)}`).join("; ")}`}>
        {[lo, (lo + hi) / 2, hi].map((g) => <g key={g}><line x1="30" x2="590" y1={Y(g)} y2={Y(g)} stroke="var(--border)" strokeWidth="0.6" /><text x="25" y={Y(g) + 3} textAnchor="end" className="mfu-ax">{Math.round(g)}</text></g>)}
        {series.map((s, i) => <path key={codes[i]} d={s.map((p, k) => `${k ? "L" : "M"}${X(p.date).toFixed(1)},${Y(p.final!).toFixed(1)}`).join("")} fill="none" stroke={COLORS[i]} strokeWidth="2.2" strokeLinejoin="round" />)}
      </svg>
      <figcaption className="mfu-leg">{codes.map((c, i) => <span key={c}><i style={{ background: COLORS[i] }} aria-hidden="true" />{names[i]}</span>)}</figcaption>
    </figure>
  );
}

export function ScoreCompare({ codes, names = [] }: { codes: number[]; names?: string[] }) {
  const { has } = useUI();
  const q = useScores(codes);
  const locked = !has("gold") || !!q.data?.locked;
  const by = new Map((q.data?.items || []).map((i) => [i.code, i]));
  const nm = codes.map((c, i) => names[i] || String(c));
  const its = codes.map((c) => by.get(c));
  const ref = its[0];
  const passive = !locked && its.some((i) => i?.group === "OT-PASSIVE");
  return (
    <section className="card mf-card mfs-cmpcard mfu" aria-label={`${MF_SCORE_NAME}, side by side`}>
      <div className="card-h"><h3><span className="ci"><Icon name="quality" /></span>{MF_SCORE_NAME}</h3><Link className="mf-linkbtn" to={MF_METHOD_URL}>How it works</Link></div>
      {!locked && its.some((i) => i?.final != null) && (
        <div className="mfu-cmptop">
          <div className="mfu-rings">{codes.map((c, i) => <div key={c}><ScoreRing score={its[i]?.final ?? null} label={its[i]?.label ?? null} size={92} /><small style={{ color: COLORS[i] }}>{nm[i]}</small></div>)}</div>
          <Radar label="The four parts of each fund" series={codes.map((_, i) => ({ name: nm[i], values: PILLARS.map(([k]) => its[i]?.pillars?.[k] ?? null), color: COLORS[i], dashed: i > 0 && false }))} />
        </div>)}
      <div className="tw"><table className="mf-cmp"><caption className="sr-only">Score and its four parts</caption>
        <thead><tr><th scope="col"><span className="sr-only">Measure</span></th>{codes.map((c, i) => <th scope="col" key={c}><Link to={`/funds/${c}`}>{nm[i]}</Link></th>)}</tr></thead>
        <tbody>
          <tr><th scope="row">Score (0 to 100)</th>{codes.map((c, i) => { const it = its[i]; return <td key={c}>{cellOf(locked, it?.final, it?.reason)}{!locked && it?.label && <small className="muted"> {it.label}{it.status === "PROVISIONAL" ? ", provisional" : ""}</small>}{!locked && i > 0 && compareTo(it?.final, ref?.final) !== "na" && <em className={"mfu-ahead " + compareTo(it?.final, ref?.final)}>{WORD[compareTo(it?.final, ref?.final)]}</em>}</td>; })}</tr>
          {PILLARS.map(([k, label]) => <tr key={k}><th scope="row">{label}</th>{codes.map((c, i) => { const it: ScoreItem | undefined = its[i], a = compareTo(it?.pillars?.[k], ref?.pillars?.[k]); return <td key={c}>{cellOf(locked, it?.pillars?.[k], it?.reason)}{!locked && i > 0 && a !== "na" && <em className={"mfu-ahead " + a}>{WORD[a]}</em>}</td>; })}</tr>)}
          <tr><th scope="row">Rank in its category</th>{codes.map((c, i) => { const it = its[i]; return <td key={c}>{locked ? <Icon name="lock" /> : it?.rank ? `${it.rank} of ${it.rankOf}` : "—"}</td>; })}</tr>
        </tbody></table></div>
      {!locked && <p className="faint mf-fine">Ahead, level or behind compares each fund with the first one, part by part. Level means within {LEVEL_TOLERANCE} points. These are gaps on a 0 to 100 score, not a verdict.</p>}
      {!locked && <Lines codes={codes} names={nm} />}
      {passive && <p className="mf-fine"><Link to="/etfs/compare-index-funds">ETF vs index fund</Link>: see an ETF and an index fund on the same index side by side.</p>}
      <p className="faint mf-fine">{MF_SCORE_COMPLIANCE} Compare funds of the same category and plan: a score is measured against funds of the same kind.</p>
    </section>
  );
}
