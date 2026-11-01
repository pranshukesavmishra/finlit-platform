// Report summary: one financial score, separate technical scores, completeness and validation.
import { Icon } from "../../../lib/icons";
import { dateIN } from "../../../lib/format";
import {
  PRISM_NAME, PRISM_NOTE, completenessNote, notRatedReason, STATUS_TEXT, STATUS_WORD, isRated, labelTone, pctWhole, score1, statementWord,
  type PrismRating, type PrismReport,
} from "../../../lib/prism";
import { fmtScore, parseTechnical, ratingWord } from "../../../lib/prismTechnical";
import { horizonCaption } from "../../../stock/prismCardLogic";

export const istTime = (iso: string | null | undefined, withDate = true) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", ...(withDate ? { day: "numeric", month: "short", year: "numeric" } : {}), hour: "numeric", minute: "2-digit" }) + " IST";
};

export type ReportActions = {
  onRecalculate?: () => void; recalculating?: boolean;
};

export function StatusChip({ status }: { status: PrismReport["rating"]["status"] }) {
  return <span className={"pzr-st " + status.replace(" ", "-").toLowerCase()}><i aria-hidden="true" />{STATUS_WORD[status]}</span>;
}
export function LabelChip({ label }: { label: PrismReport["rating"]["label"] }) {
  const t = labelTone(label);
  return <span className={"pzr-lab " + t.tone}><i aria-hidden="true" />{t.word}</span>;
}

export function miniFundLabel(rating: Pick<PrismRating, "status" | "final" | "label">): string {
  return isRated(rating) && rating.final != null ? `Fundamental score ${score1(rating.final)} out of 100: ${labelTone(rating.label).word}` : "Fundamental score: not rated";
}

export function Hero({ report, actions }: { report: PrismReport; actions: ReportActions }) {
  const { rating, company } = report, rated = isRated(rating) && rating.final != null;
  const tech = parseTechnical(report.technicalAssessment);
  return <section className="pzr-hero pzr-summary" aria-label={`${PRISM_NAME} rating for ${company.name}`}>
    <div className="pzr-summary-heading"><div><p className="pzr-kick">{PRISM_NAME} · Financial health · four components</p><h2>{company.name}</h2><p className="pzr-meta"><span>{company.symbol}</span><span>{company.industry || company.sector || "Industry unavailable"}</span><span>{statementWord(report.statementType)} statements</span></p></div>
      <div className="pzr-main-score" role="img" aria-label={miniFundLabel(rating)}><b>{rated ? score1(rating.final) : "Not rated"}</b>{rated && <span>out of 100</span>}<LabelChip label={rating.label} /></div></div>
    <div className="pzr-summary-status"><StatusChip status={rating.status} /><p>{notRatedReason(rating) ?? (rating.dataIntegrityStatus === "REVIEW REQUIRED" ? "Calculated from available inputs. Validation checks need a closer look." : STATUS_TEXT[rating.status])}</p></div>
    <div className="pzr-summary-facts"><div><span>Input completeness</span><b>{pctWhole(rating.confidence)}</b><small>Completeness is not accuracy or a forecast.</small></div><div><span>Comparable quarters</span><b>{rating.judgedQuarters} of 10</b><small>{completenessNote(rating) || "History available for the growth comparisons."}</small></div><div><span>Validation</span><b>{rating.dataIntegrityStatus === "PASS" ? "Checks passed" : rating.dataIntegrityStatus === "REVIEW REQUIRED" ? "Review required" : "Not checked"}</b><a href="#pzr-h-health">Inspect data checks</a></div></div>
    {tech && <div className="pzr-summary-tech"><span>Separate technical view</span><span aria-label={`Technical short term ${fmtScore(tech.shortTerm.score)}: ${ratingWord(tech.shortTerm.rating, tech.shortTerm.score).word}, ${horizonCaption(tech.shortTerm)}`}>Short term <b>{fmtScore(tech.shortTerm.score)}</b> · {ratingWord(tech.shortTerm.rating, tech.shortTerm.score).word}<small>{horizonCaption(tech.shortTerm)}</small></span><span aria-label={`Technical long term ${fmtScore(tech.longTerm.score)}: ${ratingWord(tech.longTerm.rating, tech.longTerm.score).word}, ${horizonCaption(tech.longTerm)}`}>Long term <b>{fmtScore(tech.longTerm.score)}</b> · {ratingWord(tech.longTerm.rating, tech.longTerm.score).word}<small>{horizonCaption(tech.longTerm)}</small></span><a href="#pzr-technical">See technical details</a></div>}
    <div className="pzr-summary-bottom"><span>Calculated {istTime(report.createdAt)}{report.technical?.asOf && <span data-testid="tech-asof"> · Technical view as of {dateIN(report.technical.asOf)}</span>}</span><button type="button" className="btn pzr-noprint" onClick={actions.onRecalculate} disabled={actions.recalculating}><Icon name="refresh" />{actions.recalculating ? "Recalculating…" : "Recalculate"}</button></div>
    <p className="pzr-note">{PRISM_NOTE}</p>
  </section>;
}
