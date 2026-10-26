// One FinLit Prism report: hero with the prism ring, the parts, what moved the score, every factor, financial history, valuation against
// the benchmark, and completeness and freshness. NOT RATED never shows category scores. Layout lives in styles/prism-report.css (pzr-*).
import { Icon } from "../../lib/icons";
import { PRISM_NAME, PRISM_NOTE, incomeWord, prismReview } from "../../lib/prism";
import { Hero, istTime, LabelChip, StatusChip, type ReportActions } from "./pzr/Hero";
import { FactorExplorer } from "./pzr/Factors";
import { Health, Peers } from "./pzr/Health";
import { HistoryCharts, HistoryTables } from "./pzr/History";
import { PartCards, Waterfall } from "./pzr/Parts";
import type { PrismReport } from "../../lib/prism";

export { istTime, LabelChip, StatusChip };
export type { ReportActions };

/** Placeholder with the report's own proportions, shown while the stored report loads. */
export function ReportSkeleton() {
  return (
    <div className="pzr-rep pzr-skel" aria-busy="true" aria-label="Loading the stored rating">
      <div className="skeleton pzr-sk-hero" /><div className="pzr-sk-parts">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" />)}</div><div className="skeleton pzr-sk-wf" /><div className="skeleton pzr-sk-fx" />
    </div>
  );
}

export function PrismReportView({ report, actions = {}, example = false }: { report: PrismReport; actions?: ReportActions; example?: boolean }) {
  const review = prismReview(report), legacy = "legacy" in review && review.legacy;
  const income = incomeWord(report.rating.group);
  return (
    <article className={"pzr-rep" + (example ? " pzr-example" : "")} aria-label={`${PRISM_NAME} report for ${report.company.name}`}>
      {example && <p className="pzr-example-b" role="note"><b>Example</b> A fictional company, to show the layout. Not a real rating.</p>}
      <Hero report={report} actions={actions} />
      {report.rating.dataIntegrityStatus === "REVIEW REQUIRED" && (
        <div className="pzr-caution" role="note"><Icon name="alert" /><span><b>Data check: review required.</b> Some inputs could not be fully verified (see the review notes below). The caution does not change the score; read the result with it in mind.</span></div>
      )}
      {legacy && (
        <div className="pzr-caution" role="note"><Icon name="info" /><span>This stored report predates the reader commentary. <button type="button" className="pzr-link pzr-noprint" onClick={actions.onRecalculate}>Recalculate</button> for the full review.</span></div>
      )}
      <PartCards report={report} review={review} />
      <Waterfall report={report} />
      <FactorExplorer report={report} review={review} />
      <section className="pzr-sec" aria-labelledby="pzr-h-hist">
        <header className="pzr-sh"><h3 id="pzr-h-hist">Financial history</h3><p>From the company's filings, on the same statement basis as the score.</p></header>
        <HistoryCharts report={report} />
        {report.financialHistory && <HistoryTables history={report.financialHistory} income={income} />}
      </section>
      <Peers report={report} />
      <Health report={report} completeness={review.completeness} onRecalculate={actions.onRecalculate} notes={review.notes} />
      <footer className="pzr-foot">
        <p>This report assesses financial health using available financial and market information, with estimates where information is missing. It is not an investment recommendation or a prediction of future returns. The PDF of a calculation can be downloaded for 30 minutes; after that, recalculate to download a fresh one.</p>
        <p className="pzr-note">{PRISM_NOTE}</p>
      </footer>
    </article>
  );
}
