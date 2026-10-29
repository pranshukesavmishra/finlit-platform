// The technical view on the stock page, compact: a short-term and a long-term mini scale (-100..+100) with the score and the trend word, in
// the Prism card under the four parts. It is an independent view (report.technicalAssessment), not a fifth part of the score. A stored report
// from before the technical view gets one quiet line; nothing is invented. Words and shapes carry the meaning, colour only decorates.
import { Icon } from "../lib/icons";
import type { PrismLatest } from "./PrismCard";
import { fmtScore, parseTechnical, ratingWord, scalePos, trendAlignment, type TechHorizon, type TrendTone, type VerdictTone } from "../lib/prismTechnical";
import "../styles/prism-technical.css";

const SHAPE: Record<TrendTone, string> = { strongpos: "▲▲", pos: "▲", neutral: "◆", neg: "▼", strongneg: "▼▼", na: "–" };
const VSHAPE: Record<VerdictTone, string> = { pos: "▲", mixed: "◆", neg: "▼", na: "–" };

function Mini({ label, h }: { label: string; h: TechHorizon }) {
  const w = ratingWord(h.rating, h.score), has = h.score != null;
  return (
    <div className={"pzt-rm " + w.tone}>
      <span className="pzt-rn"><small>Technical</small>{label}</span>
      <span className="pzt-rv"><b>{has ? fmtScore(h.score) : "Not available"}</b>{has && <span className="pzt-rw"><i aria-hidden="true">{SHAPE[w.tone]}</i>{w.word}</span>}</span>
      <span className="pzt-rs" aria-hidden="true"><u />{has && <i style={{ left: `${scalePos(h.score)}%` }} />}</span>
    </div>
  );
}

/** What a screen reader hears for the row. */
export function techRowSummary(h: { shortTerm: TechHorizon; longTerm: TechHorizon }): string {
  const one = (n: string, x: TechHorizon) => x.score == null ? `${n} not available` : `${n} ${fmtScore(x.score)} on a scale from minus 100 to plus 100, ${ratingWord(x.rating, x.score).word.toLowerCase()}`;
  const al = trendAlignment(h.shortTerm.score, h.longTerm.score);
  return `Technical view, separate from the Prism score: ${one("short term", h.shortTerm)}; ${one("long term", h.longTerm)}.${al ? ` Trend alignment: ${al.label}.` : ""}`;
}

export function PrismTechRow({ report, onRecalculate, busy }: { report: PrismLatest; onRecalculate?: () => void; busy?: boolean }) {
  const a = parseTechnical(report.technicalAssessment);
  if (!a) {
    return (
      <p className="pzt-row quiet" role="note"><Icon name="activity" /><span>Technical view: {onRecalculate ? <button type="button" disabled={busy} onClick={onRecalculate}>recalculate to add</button> : "recalculate to add"}</span></p>
    );
  }
  const al = trendAlignment(a.shortTerm.score, a.longTerm.score);
  return (
    <div className="pzt-row" role="group" aria-label={techRowSummary(a)} title="Technical view: describes recent price and trend behaviour from past prices; it does not predict prices.">
      <Mini label="Short term" h={a.shortTerm} />
      <Mini label="Long term" h={a.longTerm} />
      {al && <p className={"pzt-ra " + al.tone}><small>Trend alignment</small><span><i aria-hidden="true">{VSHAPE[al.tone]}</i>{al.label}</span></p>}
    </div>
  );
}
