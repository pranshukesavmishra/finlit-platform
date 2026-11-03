// The top of a Prism report: the same two cards the company page shows ("Financial health analysis" with the four weighted parts, and "Technical analysis"
// with the short- and long-term views), drawn by the same components (stock/PrismCardView) so the two pages can never drift apart. Above them, the company's name and its status words.
import { Link } from "react-router";
import { Icon } from "../../../lib/icons";
import { PRISM_NAME, inputsLine, notRatedLede, statementWord, type PrismReport } from "../../../lib/prism";
import { parseTechnical } from "../../../lib/prismTechnical";
import { FundamentalSection, TechnicalSection } from "../../../stock/PrismCardView";
import { partsOf } from "../../../stock/PrismCompare";
import { STATUS, prismSummary, type PrismLatest } from "../../../stock/PrismCard";
import { LabelChip, StatusChip, istTime, type ReportActions } from "./Hero";
import "../../../styles/prism-compare.css";
import "../../../styles/prism-card.css";

const STATUS_NOTE: Record<PrismReport["rating"]["status"], string> = {
  RATED: "Enough of the data was available for a full rating.",
  PROVISIONAL: "Some data is missing or the record is short, so this is a first view and is shown at most as Healthy.",
  "NOT RATED": "The overall rating is withheld.",
};

export function CardTop({ report, actions }: { report: PrismReport; actions: ReportActions }) {
  const r = report.rating, rep = report as unknown as PrismLatest;
  const { parts } = partsOf(r as unknown as PrismLatest["rating"]);
  const inp = inputsLine(r);
  return (
    <section className="pzr-cardtop" aria-label={`${PRISM_NAME} rating of ${report.company.name}`}>
      <header className="pzr-ct-h">
        <div>
          <h2>{report.company.name}</h2>
          <p className="pzr-ct-sub"><b>{report.company.symbol}</b> · {statementWord(report.statementType)} statements · Model {r.modelVersion} · Calculated {istTime(report.completedAt || report.createdAt)}</p>
        </div>
        <div className="pzr-ct-chips"><StatusChip status={r.status} />{r.status !== "NOT RATED" && <LabelChip label={r.label} />}
          {actions.onRecalculate && <button type="button" className="btn" onClick={actions.onRecalculate} disabled={actions.recalculating}><Icon name="refresh" />{actions.recalculating ? "Recalculating…" : "Recalculate"}</button>}</div>
      </header>
      <div className="pcx-body" role="group" aria-label={prismSummary(r as unknown as PrismLatest["rating"])}>
        <FundamentalSection r={r as unknown as PrismLatest["rating"]} parts={parts}>
          <div className="dk-words">
            <div className="dk-chips"><span className={"pz-status " + r.status.toLowerCase().replace(" ", "-")}>{STATUS[r.status as PrismLatest["rating"]["status"]]}</span></div>
            {r.status !== "RATED" && <p className={"dk-note" + (r.status === "NOT RATED" ? " why" : "")}>{r.status === "NOT RATED" ? notRatedLede(r) : STATUS_NOTE[r.status]}</p>}
            <p className={"dk-cov" + (inp.ok ? "" : " held")}><Icon name={inp.ok ? "check" : "info"} />{inp.text}{inp.note ? <span className="dk-cov-n"> · {inp.note}</span> : null} · <Link to="/glossary#coverage-prism">what this means</Link></p>
          </div>
        </FundamentalSection>
        <TechnicalSection a={parseTechnical(report.technicalAssessment)} report={rep} onRecalculate={actions.onRecalculate} busy={actions.recalculating} />
      </div>
    </section>
  );
}
