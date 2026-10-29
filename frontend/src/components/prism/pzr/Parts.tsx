// The part cards (one per part in the data, and a quiet note that the technical view is separate) and the "what moved the score" chart.
import { useState } from "react";
import { nf } from "../../../lib/format";
import {
  factorValue, isRated, labelTone, partInfo, partShare, partsOf, partsSentence, pctWhole, score1, scoreTone,
  type PartKey, type PrismMetric, type PrismReport, type PrismReview, type ReviewPart,
} from "../../../lib/prism";
import { THRESHOLDS, bandLabel, capNotes, contributionTotal, contributions, partVar, topFactors } from "../../../lib/prismReport";
import { partHint } from "../../../lib/scoreBands";
import { parseTechnical } from "../../../lib/prismTechnical";
import { ChartTable, ShowTable } from "../PrismCharts";

const reduced = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
/** Scroll to a part's factor section and move focus there for keyboard and screen-reader users. */
export function goToPart(key: PartKey) {
  const el = document.getElementById(`pzr-part-${key}`);
  if (!el) return;
  el.scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "start" });
  el.focus({ preventScroll: true });
}

function MiniRing({ score, color }: { score: number | null; color: string }) {
  const r = 26, c = 2 * Math.PI * r, f = score == null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  return (
    <svg className="pzr-mini" width="68" height="68" viewBox="0 0 68 68" aria-hidden="true" style={{ "--c": color } as React.CSSProperties}>
      <circle cx="34" cy="34" r={r} className="pzr-mini-t" />
      {f > 0 && <circle cx="34" cy="34" r={r} className="pzr-mini-f" strokeDasharray={`${(c * f).toFixed(1)} ${c.toFixed(1)}`} transform="rotate(-90 34 34)" />}
      <text x="34" y="39" textAnchor="middle" className="pzr-mini-n">{score == null ? "—" : nf(score, 0)}</text>
    </svg>
  );
}

export function ThresholdBar({ value, color, ticks = THRESHOLDS }: { value: number | null; color: string; ticks?: number[] }) {
  return (
    <span className="pzr-tb" aria-hidden="true" style={{ "--c": color } as React.CSSProperties}>
      <i style={{ width: `${value == null ? 0 : Math.max(0, Math.min(100, value))}%` }} />
      {ticks.map((t) => <u key={t} style={{ left: `${t}%` }} />)}
    </span>
  );
}

function PartCard({ k, index, report, review, rows }: { k: PartKey; index: number; report: PrismReport; review: PrismReview; rows: PrismMetric[] }) {
  const { rating } = report, rated = isRated(rating);
  const part: ReviewPart | undefined = review.parts.find((p) => p.key === k);
  const score = rated ? (part?.score ?? rating.parts[k] ?? null) : null;
  const tone = scoreTone(score), word = score == null ? "Not rated" : labelTone(bandLabel(score)).word;
  const { strength, drag } = rated ? topFactors(rows) : { strength: null, drag: null };
  const color = partVar(k, index);
  const missing = rows.filter((r) => r.status === "F" || r.status === "L").length;
  const lines = [partInfo(k).what, rated && part?.notes?.[0] ? part.notes[0] : null].filter(Boolean) as string[];
  return (
    <button type="button" className="pzr-part" onClick={() => goToPart(k)} style={{ "--c": color } as React.CSSProperties}
      aria-label={`${partInfo(k).name}: ${score == null ? "not rated" : `${score1(score)} out of 100, ${word}`}. Counts for ${partShare(rating.partWeights, k)} percent of the score. Go to its factors.`}>
      <span className="pzr-part-h"><MiniRing score={score} color={color} />
        <span className="pzr-part-t"><b>{partInfo(k).name}</b><small>{partShare(rating.partWeights, k)}% of the overall score</small>{partHint(k) && <small className="pzr-hint" title={partHint(k)!.long}>{partHint(k)!.short}{k === "risk" ? ": higher means lower risk" : ""}</small>}</span>
        <span className={"pzr-part-w " + tone}><i aria-hidden="true" />{word}</span>
      </span>
      <ThresholdBar value={score} color={color} />
      <span className="pzr-part-ln">
        {lines.map((l, i) => <span key={i}>{l}</span>)}
        <span>{pctWhole(rating.coverage[k])} of its inputs available{missing ? `; ${missing} estimated or missing` : ""}.</span>
      </span>
      {rated && (strength || drag) && <span className="pzr-part-tf">
        {strength && <span className="pos"><em>Top strength</em>{strength.label} <small>{factorValue(strength)}</small></span>}
        {drag && <span className="neg"><em>Biggest drag</em>{drag.label} <small>{factorValue(drag)}</small></span>}
      </span>}
      <span className="pzr-part-go" aria-hidden="true">See the factors →</span>
    </button>
  );
}

export function PartCards({ report, review }: { report: PrismReport; review: PrismReview }) {
  const keys = partsOf(report.rating);
  return (
    <section className="pzr-sec" aria-labelledby="pzr-h-parts">
      <header className="pzr-sh"><h3 id="pzr-h-parts">The parts of the score</h3><p>Each part has a fixed share of the overall score. Select a card to jump to its factors. Ticks mark 35, 50, 65 and 80, where the labels change. For all four, higher is better: a higher Risk score means lower risk.</p></header>
      {!isRated(report.rating) && <p className="pzr-withheld">{partsSentence(report.rating)}</p>}
      <div className="pzr-parts">
        {keys.map((k, i) => <PartCard key={k} k={k} index={i} report={report} review={review} rows={report.rating.metrics.filter((m) => m.part === k)} />)}
        {!keys.includes("technical") && <div className="pzr-part soon" role="note"><b>Technical view: separate from this score</b><span>{parseTechnical(report.technicalAssessment) ? "Short-term and long-term price trend. It is calculated on its own, is not a part of the score above and never changes it. See the Technical view below." : "Short-term and long-term price trend. It is not a part of the score above. This stored report does not include it; recalculate to add it."}</span></div>}
      </div>
    </section>
  );
}

/* ---- what moved the score */
export function Waterfall({ report }: { report: PrismReport }) {
  const [table, setTable] = useState(false);
  const { rating } = report;
  const rows = contributions(rating), total = contributionTotal(rows), notes = capNotes(rating);
  if (!rows.length) return (
    <section className="pzr-sec" aria-labelledby="pzr-h-wf"><header className="pzr-sh"><h3 id="pzr-h-wf">What moved the score</h3></header><p className="pzr-withheld">There is no overall score to break down because the company is not rated.</p></section>
  );
  const worst = [...rows].sort((a, b) => b.lost - a.lost)[0];
  const concl = `Overall ${score1(rating.final)} is the sum of ${rows.map((r) => `${partInfo(r.key).name} ${score1(r.points)} of ${nf(r.max, 0)}`).join(", ")}. Largest shortfall: ${partInfo(worst.key).name}, ${score1(worst.lost)} points not earned.`;
  let acc = 0;
  return (
    <section className="pzr-sec" aria-labelledby="pzr-h-wf">
      <header className="pzr-sh"><h3 id="pzr-h-wf">What moved the score</h3><p>Each part adds its score times its weight. The solid bar is what it added; the outline is the share it did not earn. The four additions make the overall score.</p></header>
      <div className="pzr-wf" role="img" aria-label={concl}>
        <div className="pzr-wf-axis" aria-hidden="true">{[0, 25, 50, 75, 100].map((t) => <span key={t} style={{ left: `${t}%` }}>{t}</span>)}</div>
        {rows.map((r, i) => {
          const from = acc; acc += r.points;
          return (
            <div className="pzr-wf-row" key={r.key} aria-hidden="true" style={{ "--c": partVar(r.key, i) } as React.CSSProperties}>
              <span className="pzr-wf-n">{partInfo(r.key).name}<small>{r.score == null ? "" : `${score1(r.score)} × ${Math.round(r.weight * 100)}%`}</small></span>
              <span className="pzr-wf-t">
                <i className="pzr-wf-gh" style={{ left: `${from}%`, width: `${r.max}%` }} />
                <i className="pzr-wf-b" style={{ left: `${from}%`, width: `${r.points}%` }} />
                {r.capLost > 0 && <i className="pzr-wf-cap" style={{ left: `${from + r.points}%`, width: `${r.capLost}%` }} />}
                {THRESHOLDS.map((t) => <u key={t} style={{ left: `${t}%` }} />)}
              </span>
              <b>+{score1(r.points)}<small> of {nf(r.max, 0)}</small></b>
            </div>
          );
        })}
        <div className="pzr-wf-row total" aria-hidden="true">
          <span className="pzr-wf-n">Overall score<small>sum of the parts</small></span>
          <span className="pzr-wf-t"><i className="pzr-wf-tot" style={{ left: 0, width: `${total}%` }} />{THRESHOLDS.map((t) => <u key={t} style={{ left: `${t}%` }} />)}</span>
          <b>{score1(total)}<small> of 100</small></b>
        </div>
      </div>
      <ul className="pzr-capnotes">
        {notes.length ? notes.map((n) => <li key={n}>{n}</li>) : <li>No loss or valuation limit was applied to this score.</li>}
        {rows.some((r) => r.capLost > 0) && <li>The hatched part of a bar is the share a limit took away.</li>}
      </ul>
      <div className="pzr-cfoot"><span>Rounding: parts are shown to one decimal, so the sum can differ from the total by 0.1.</span><ShowTable on={table} set={setTable} /></div>
      {table && <ChartTable caption={concl} head={["Part", "Part score", "Weight", "Points added", "Points not earned"]}
        rows={[...rows.map((r) => [partInfo(r.key).name, score1(r.score), `${Math.round(r.weight * 100)}%`, score1(r.points), score1(r.lost)]), ["Overall", "", "100%", score1(total), score1(100 - total)]]} />}
    </section>
  );
}

