// Full measure-by-measure breakdown of a score (Gold): pillars with every measure (your value, the category median, points, weight, state and what it means,
// a coloured bar), the radar of the four parts against the category median, and a "Data gaps" box. Rendered inside the score card when the score is rated.
import { useState } from "react";
import { Radar } from "./Radar";
import { Icon } from "../lib/icons";
import { PEER_KIND_WORD, PILLARS, STATE_WORD, dataGaps, groupMetrics, stateLine, type CategoryMedian } from "../lib/mfScoreUp";
import { bandOf, scoreText, type FundScore } from "../lib/mfScore";
import { bandVar } from "../lib/scoreBands";
import "../styles/mfup.css";

const num = (v: number | null | undefined) => (v == null ? "—" : Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2).replace(/\.?0+$/, ""));
type S = FundScore & { categoryMedian?: CategoryMedian };

export function ScoreBreakdown({ s }: { s: S }) {
  const [open, setOpen] = useState(false);
  if (s.final == null || !s.metrics?.length) return null;
  const groups = groupMetrics(s), gaps = dataGaps(s), med = s.categoryMedian;
  const own = PILLARS.map(([k]) => s.pillars.find((p) => p.key === k)?.score ?? null);
  return (
    <div className="mfu-bd" data-testid="score-breakdown">
      <h3 className="mf-h4">Score breakdown</h3>
      <div className="mfu-bdtop">
        <Radar label="The four parts against the category median" series={[{ name: "This fund", values: own, color: "var(--gold)" }, ...(med ? [{ name: `Category median${med.n ? ` (${med.n} funds)` : ""}`, values: PILLARS.map(([k]) => med[k]), color: "var(--k1)", dashed: true }] : [])]} />
        <div className="mfu-facts">
          <dl>
            <dt>NAV history used</dt><dd>{s.months ? `${s.months} months (${(s.months / 12).toFixed(1)} years)` : "—"}</dd>
            <dt>Compared with</dt><dd>{s.peers?.n ? `${s.peers.n} funds · ${PEER_KIND_WORD[s.peers.kind || ""] || s.peers.text || "similar funds"}` : "—"}</dd>
            {med && <><dt>Category median score</dt><dd>{scoreText(med.final)} ({med.categoryLabel}, {med.plan} plan)</dd></>}
          </dl>
          <div className={"mfu-gaps" + (gaps.length ? " has" : "")} aria-label="Data gaps">
            <h4><Icon name={gaps.length ? "alert" : "check"} /> Data gaps</h4>
            {gaps.length === 0 ? <p>Every measure used the fund's own figures.</p> : (
              <><p>{gaps.filter((g) => g.state === "F").length} measure(s) used the group value because data was missing; {gaps.filter((g) => g.state === "S").length} used a stand-in figure.</p>
                <ul>{gaps.map((g) => <li key={g.id}><b>{g.label}</b> <em>{STATE_WORD[g.state]}</em>{g.whyText ? `: ${g.whyText}` : ""}</li>)}</ul></>)}
          </div>
        </div>
      </div>
      <button type="button" className="mf-linkbtn" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide the measure-by-measure table" : "Show the measure-by-measure table"}</button>
      {open && (
        <div className="tw"><table className="mf-cmp mfu-tbl"><caption className="sr-only">Every measure behind the score, by part</caption>
          <thead><tr><th scope="col">Measure</th><th scope="col" className="num">This fund</th><th scope="col" className="num">Peer median</th><th scope="col" className="num">Points</th><th scope="col" className="num">Weight</th><th scope="col">State</th></tr></thead>
          {groups.map((g) => (
            <tbody key={g.key}>
              <tr className="mfu-ph"><th scope="colgroup" colSpan={6}>{PILLARS.find(([k]) => k === g.key)![1]} <b className={"b-" + bandOf(g.score)}>{scoreText(g.score)}</b></th></tr>
              {g.metrics.map((m) => (
                <tr key={m.id}>
                  <th scope="row">{m.label}</th><td className="num">{num(m.own ?? m.value)}</td><td className="num">{num(m.peer)}</td>
                  <td className="num"><span className="mfu-pbar" aria-hidden="true"><i style={{ width: `${m.points ?? 0}%`, background: bandVar(bandOf(m.points)) }} /></span><span>{m.points == null ? "—" : m.points.toFixed(0)}</span></td>
                  <td className="num">{m.weight == null || m.state === "N" ? "—" : m.weight.toFixed(1) + "%"}</td>
                  <td><span className={"mfu-st st-" + m.state}>{STATE_WORD[m.state]}</span><small>{stateLine(m)}</small></td>
                </tr>))}
            </tbody>))}
        </table></div>)}
    </div>
  );
}
