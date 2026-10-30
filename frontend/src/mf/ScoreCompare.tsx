// Score and the four parts of two or more funds side by side (Fund Compare). Gold; below that the rows show a lock and no value.
import { Link } from "react-router";
import { useUI } from "../lib/ui";
import { Icon } from "../lib/icons";
import { MF_METHOD_URL, MF_SCORE_COMPLIANCE, MF_SCORE_NAME, bandOf, scoreText, useScores, type ScoreItem } from "../lib/mfScore";

const PARTS = [["performance", "Performance"], ["risk", "Risk"], ["cost", "Cost"], ["quality", "Quality"]] as const;
const cellOf = (_it: ScoreItem | undefined, locked: boolean, v: number | null | undefined, why?: string | null) =>
  locked ? <span className="mf-na" title="Part of the Gold plan"><Icon name="lock" /><span className="sr-only">Locked: Gold plan</span></span>
    : v == null ? <span className="mf-na" title={why || "No score"}>—</span> : <b className={"mfs-pv b-" + bandOf(v)}>{scoreText(v)}</b>;

export function ScoreCompare({ codes, names }: { codes: number[]; names?: string[] }) {
  const { has } = useUI();
  const q = useScores(codes);
  const locked = !has("gold") || !!q.data?.locked;
  const by = new Map((q.data?.items || []).map((i) => [i.code, i]));
  return (
    <section className="card mf-card mfs-cmpcard" aria-label={`${MF_SCORE_NAME}, side by side`}>
      <div className="card-h"><h3><span className="ci"><Icon name="quality" /></span>{MF_SCORE_NAME}</h3><Link className="mf-linkbtn" to={MF_METHOD_URL}>How it works</Link></div>
      <div className="tw"><table className="mf-cmp"><caption className="sr-only">Score and its four parts</caption>
        <thead><tr><th scope="col"><span className="sr-only">Measure</span></th>{codes.map((c, i) => <th scope="col" key={c}><Link to={`/funds/${c}`}>{names?.[i] || c}</Link></th>)}</tr></thead>
        <tbody>
          <tr><th scope="row">Score (0 to 100)</th>{codes.map((c) => { const it = by.get(c); return <td key={c}>{cellOf(it, locked, it?.final, it?.reason)}{!locked && it?.label && <small className="muted"> {it.label}{it.status === "PROVISIONAL" ? ", provisional" : ""}</small>}</td>; })}</tr>
          {PARTS.map(([k, label]) => <tr key={k}><th scope="row">{label}</th>{codes.map((c) => { const it = by.get(c); return <td key={c}>{cellOf(it, locked, it?.pillars?.[k], it?.reason)}</td>; })}</tr>)}
          <tr><th scope="row">Rank in its category</th>{codes.map((c) => { const it = by.get(c); return <td key={c}>{locked ? <Icon name="lock" /> : it?.rank ? `${it.rank} of ${it.rankOf}` : "—"}</td>; })}</tr>
        </tbody></table></div>
      <p className="faint mf-fine">{MF_SCORE_COMPLIANCE} Compare funds of the same category and plan: a score is measured against funds of the same kind.</p>
    </section>
  );
}
