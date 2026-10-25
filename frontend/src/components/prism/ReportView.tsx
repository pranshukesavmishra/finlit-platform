// One FinLit Prism report, in the same order and words as its PDF (site-api/backend/premium_pdf.py): headline, the four parts,
// input completeness, data dates and basis, financial history, what supports and holds back each part, every factor with its
// points, reader notes, benchmarks and the data checks. NOT RATED never shows category scores.
import { HScroll } from "../HScroll";
import { Icon } from "../../lib/icons";
import { dateIN, MINUS, nf } from "../../lib/format";
import {
  PRISM_NAME, PRISM_NOTE, STANDING_WORD, STATE_WORD, STATUS_TEXT, STATUS_WORD, factorDetail, factorValue, incomeWord,
  isRated, labelTone, partInfo, partShare, partsOf, pctWhole, pdfOpen, prismReview, reviewItem, score1, standing, statementWord,
  type BenchmarkDetail, type Completeness, type PartKey, type PrismHistory, type PrismMetric, type PrismReport, type PrismReview, type ReviewItem, type ReviewPart,
} from "../../lib/prism";
import { GrowthView, PrismPartBars as PartBars, PrismScoreRing as ScoreRing, TrendCharts } from "./PrismCharts";

export const istTime = (iso: string | null | undefined, withDate = true) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", ...(withDate ? { day: "numeric", month: "short", year: "numeric" } : {}), hour: "numeric", minute: "2-digit" }) + " IST";
};

export type ReportActions = {
  onRecalculate?: () => void; recalculating?: boolean;
  onDownload?: () => void; downloading?: boolean;
  /** Set once the server said the PDF window has passed (410). */
  pdfExpired?: boolean;
};

export function StatusChip({ status }: { status: PrismReport["rating"]["status"] }) {
  return <span className={"pz-st " + status.replace(" ", "-").toLowerCase()}><i aria-hidden="true" />{STATUS_WORD[status]}</span>;
}
export function LabelChip({ label }: { label: PrismReport["rating"]["label"] }) {
  const t = labelTone(label);
  return <span className={"pz-lab " + t.tone}><i aria-hidden="true" />{t.word}</span>;
}

/* ---- 1. headline */
function Headline({ report, actions }: { report: PrismReport; actions: ReportActions }) {
  const { rating, company } = report;
  const open = pdfOpen(report) && !actions.pdfExpired;
  return (
    <section className="pz-hero" aria-label={`${PRISM_NAME} rating for ${company.name}`}>
      <div className="pz-hero-top">
        <div className="pz-co">
          <p className="pz-kick">{PRISM_NAME} · Financial health</p>
          <h2>{company.name}</h2>
          <p className="pz-meta">{company.symbol}{company.industry ? ` · ${company.industry}` : company.sector ? ` · ${company.sector}` : " · Industry unavailable"} · {statementWord(report.statementType)} statements</p>
        </div>
        <div className="pz-acts">
          {open
            ? <button type="button" className="btn primary" onClick={actions.onDownload} disabled={actions.downloading}><Icon name="download" />{actions.downloading ? "Preparing PDF…" : "Download PDF"}</button>
            : <button type="button" className="btn" disabled title="The PDF window for this calculation has passed"><Icon name="download" />PDF window passed</button>}
          <button type="button" className={"btn" + (open ? "" : " primary")} onClick={actions.onRecalculate} disabled={actions.recalculating}><Icon name="refresh" />{actions.recalculating ? "Recalculating…" : "Recalculate"}</button>
        </div>
      </div>
      <div className="pz-hero-main">
        <ScoreRing rating={rating} />
        <div className="pz-verdict">
          <div className="pz-chips"><LabelChip label={rating.label} /><StatusChip status={rating.status} /></div>
          <p className="pz-lede">Financial health assessment across business performance, valuation, financial quality and market risk.</p>
          <p className="pz-stx">{STATUS_TEXT[rating.status]}</p>
          <p className="pz-cov"><Icon name="quality" /><b>{pctWhole(rating.confidence)} data coverage</b> · {rating.judgedQuarters} of 10 comparable quarters</p>
          <p className="pz-sm">Data coverage shows how much of the required information is available. It is not a probability and does not predict returns.</p>
        </div>
      </div>
      <div className="pz-hero-foot">
        <span>Calculated {istTime(report.createdAt)}{report.cached ? " · stored report" : ""}</span>
        <span>{open ? `PDF of this calculation available until ${istTime(report.pdfAvailableUntil, false)}` : "The PDF window for this calculation has passed: recalculate to download a PDF."}</span>
      </div>
      <p className="pz-note-line">{PRISM_NOTE}</p>
    </section>
  );
}

/* ---- 2. the four parts */
function Parts({ report, review }: { report: PrismReport; review: PrismReview }) {
  const { rating } = report;
  const rated = isRated(rating);
  return (
    <section className="pz-sec" aria-label="Score components">
      <h3 className="pz-h">The four parts</h3>
      <p className="pz-sub">The overall score combines four parts. A part's share is fixed by the model; its coverage shows how much of its information was available.</p>
      <div className="pz-parts-w">
        <div className="card pz-card"><PartBars rating={rating} /></div>
        <div className="pz-parts">
          {partsOf(rating).map((k) => {
            const part = review.parts.find((p) => p.key === k);
            const v = rated ? (part?.score ?? rating.parts[k]) : null;
            return (
              <div className="pz-part" key={k}>
                <div className="pz-part-h"><b>{partInfo(k).name}</b><span>{rated ? <>{score1(v)}<small> / 100</small></> : <small>Not rated</small>}</span></div>
                <p>{partInfo(k).what}</p>
                <p className="pz-part-f">Counts for {partShare(rating.partWeights, k)}% of the overall score · {pctWhole(rating.coverage[k])} data coverage</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ---- 3. input completeness (port of upstream PremiumInputCompleteness) */
export function InputCompleteness({ completeness, onRecalculate }: { completeness?: Completeness; onRecalculate?: () => void }) {
  let body;
  if (!completeness) {
    body = <p className="pz-legacy">Recalculate this report to see the latest missing-input and history checks.{onRecalculate && <> <button type="button" className="pz-link" onClick={onRecalculate}>Recalculate</button></>}</p>;
  } else if (completeness.complete) {
    body = <p className="pz-ok"><Icon name="check" />All applicable scoring factors have usable inputs and the required comparison history.</p>;
  } else {
    body = <>
      <p className="pz-gap">Unavailable factors: <b>{completeness.missingFactorCount}</b> · Limited histories: <b>{completeness.limitedHistoryCount}</b></p>
      <p className="pz-sm">These limitations remain visible even where an input is excluded from the coverage percentage.</p>
      <ul className="pz-items">{completeness.items.map((item) => (
        <li key={`${item.category}-${item.metric}`}>
          <p className="pz-it-h"><span className={"pz-kind " + item.kind}>{item.kind === "missing" ? "Unavailable" : "Limited history"}</span>{item.category} · {item.label}</p>
          <p className="pz-it-r">{item.reason}</p>
          <p className="pz-sm">{item.treatment}</p>
        </li>))}</ul>
    </>;
  }
  return <section className="card pz-card pz-sec" aria-label="Input completeness"><h3 className="pz-h">Input completeness</h3>{body}</section>;
}

/* ---- 4. data dates and the statement basis actually used */
const DATES: [keyof PrismReport["inputMeta"], string][] = [["quarterlyAsOf", "Quarterly results"], ["annualAsOf", "Annual results"], ["balanceAsOf", "Balance sheet"], ["ownershipAsOf", "Ownership"], ["priceAsOf", "Market price"]];
function DataDates({ report }: { report: PrismReport }) {
  const m = report.inputMeta;
  const requested = m.requestedStatementType, used = report.statementType;
  return (
    <section className="card pz-card pz-sec" aria-label="Data dates and statement basis">
      <h3 className="pz-h">Data dates and statement basis</h3>
      <dl className="pz-dates">{DATES.map(([k, label]) => { const v = m[k] as string | null | undefined; return <div key={k}><dt>{label}</dt><dd>{v ? dateIN(v) : "Unavailable"}</dd></div>; })}</dl>
      <p className="pz-basis"><b>{statementWord(used)} statements</b> are used throughout this report.
        {requested && requested !== used ? ` ${statementWord(requested)} statements were requested but unavailable, so the whole report uses ${used} statements instead.` : ""}
        {m.assetQualityStatementType && m.assetQualityStatementType !== used ? ` Asset-quality ratios use the ${m.assetQualityStatementType} disclosure.` : ""}</p>
    </section>
  );
}

/* ---- 5. financial history */
function History({ report }: { report: PrismReport }) {
  const income = incomeWord(report.rating.group);
  return (
    <section className="card pz-card pz-sec" aria-label="Financial history">
      <h3 className="pz-h">Financial history</h3>
      <p className="pz-sub">Annual {income.toLowerCase()} and net profit in ₹ crore; EPS in ₹ per share. {statementWord(report.statementType)} statements.</p>
      {report.trends.length ? <>
        <TrendCharts trends={report.trends} income={income} />
        <h4 className="pz-h4">Growth against the previous year</h4>
        <GrowthView trends={report.trends} income={income} />
      </> : <p className="pz-empty">No reported annual history is available for this statement basis.</p>}
      {report.financialHistory && <HistoryTables history={report.financialHistory} income={income} />}
    </section>
  );
}

const cellNum = (v: number | null | undefined) => (v == null ? "—" : (v < 0 ? MINUS : "") + nf(v, 2));
/** The snapshot's quarterly and annual tables and key ratios (upstream PremiumFinancialHistory); only when the API sends them. */
function HistoryTables({ history, income }: { history: PrismHistory; income: string }) {
  const table = (title: string, rows: { period: string; [k: string]: number | string | null }[], fields: [string, string][]) => (
    <div className="pz-htab"><h4 className="pz-h4">{title}</h4>
      {rows.length ? <HScroll label={title}><table className="pz-t"><thead><tr><th scope="col">Measure</th>{rows.map((r) => <th scope="col" key={r.period} className="n">{r.period}</th>)}</tr></thead>
        <tbody>{fields.map(([k, label]) => <tr key={k}><th scope="row">{label}</th>{rows.map((r) => <td key={r.period} className="n">{cellNum(r[k] as number | null)}</td>)}</tr>)}</tbody></table></HScroll>
        : <p className="pz-empty">No reported history available for this statement basis.</p>}</div>
  );
  const q = history.quarterly.map((r) => ({ period: r.period, revenue: r.sales, profit: r.profit, eps: r.eps }));
  return (
    <>
      {q.filter((r) => r.revenue != null || r.profit != null).length >= 2 && <><h4 className="pz-h4">Quarterly trend</h4><TrendCharts trends={q} income={income} unit="quarter" /></>}
      <p className="pz-sm">Oldest to newest · amounts in ₹ crore · EPS in ₹ per share · missing values shown as —.</p>
      {table("Quarterly results", history.quarterly, [["sales", income === "Revenue" ? "Sales" : income], ["profit", "Owner-attributable net profit"], ["ebitda", "EBITDA"], ["eps", "EPS (₹)"]])}
      {table("Annual results", history.annual, [["sales", income === "Revenue" ? "Sales" : income], ["profit", "Owner-attributable net profit"], ["cashFlow", "Operating cash flow"], ["netWorth", "Book equity"]])}
      <h4 className="pz-h4">Key financial ratios</h4>
      <dl className="pz-ratios">{history.latest.map((r) => <div key={r.key}><dt>{r.key === "shares" ? "Shares outstanding" : r.label}</dt><dd>{r.value == null ? "—" : `${cellNum(r.value)} ${r.unit}`}</dd></div>)}</dl>
    </>
  );
}

/* ---- 6. what supports and what holds back each part (upstream CategoryReview), then every factor with its points */
function FactorList({ title, rows, cls, empty }: { title: string; rows: ReviewItem[]; cls: string; empty?: string }) {
  return (
    <div className={"pz-fl " + cls}>
      <h5><i aria-hidden="true" />{title}</h5>
      {rows.length ? <ul>{rows.map((r) => <li key={r.metric}><p className="pz-fl-h">{r.label} <span>· {r.valueText}</span></p>{r.summary && <p className="pz-fl-s">{r.summary}</p>}{r.comparisonText && <p className="pz-fl-c">{r.comparisonText}</p>}</li>)}</ul>
        : <p className="pz-empty">{empty}</p>}
    </div>
  );
}

function FactorTable({ rows, review, part, group }: { rows: PrismMetric[]; review: PrismReview; part: PartKey; group: string }) {
  return (
    <table className="pz-ft">
      <caption className="sr-only">Every {partInfo(part).name} factor with its value, its points out of 100 and its status in words.</caption>
      <thead><tr><th scope="col">Factor</th><th scope="col" className="n">Value</th><th scope="col" className="n">Points</th><th scope="col">Status</th></tr></thead>
      <tbody>{rows.map((row) => {
        const item = reviewItem(review, part, row.metric), st = standing(row), detail = factorDetail(row, group);
        return (
          <tr key={row.metric} className={st}>
            <th scope="row"><b>{item?.label || row.label}</b>{detail && <small>{detail}</small>}{item?.comparisonText && <small>{item.comparisonText}</small>}</th>
            <td className="n" data-l="Value">{row.value == null && item ? item.valueText : factorValue(row)}</td>
            <td className="n" data-l="Points">{row.points == null ? "—" : <><span className={"pz-fb " + st} aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(100, row.points))}%` }} /></span>{nf(row.points, 0)}<small> / 100</small></>}</td>
            <td data-l="Status"><span className={"pz-sw " + st}><i aria-hidden="true" />{STANDING_WORD[st]}</span><small>{STATE_WORD[row.status]}</small></td>
          </tr>
        );
      })}</tbody>
    </table>
  );
}

function CategoryReview({ part, report, review }: { part: ReviewPart; report: PrismReport; review: PrismReview }) {
  const rated = isRated(report.rating);
  const rows = report.rating.metrics.filter((m) => m.part === part.key);
  return (
    <section className="card pz-card pz-cat" aria-label={`${part.key} factors`}>
      <div className="pz-cat-h"><h4>{partInfo(part.key).name}</h4><p>{rated && part.score != null ? <>{score1(part.score)}<small> / 100</small></> : <small>Not rated</small>}</p></div>
      {part.notes?.map((n, i) => <p key={i} className="pz-cnote">{n}</p>)}
      <div className="pz-pc"><FactorList title="Pros" rows={part.pros} cls="pros" empty="No clear strengths identified." /><FactorList title="Cons" rows={part.cons} cls="cons" empty="No major concerns identified." /></div>
      {part.mixed.length > 0 && <FactorList title="Mixed factors" rows={part.mixed} cls="mixed" />}
      {part.unavailable.length > 0 && <FactorList title="Estimated or unavailable information" rows={part.unavailable} cls="unavailable" />}
      {(part.notApplicable?.length ?? 0) > 0 && <FactorList title="Not applicable to this company" rows={part.notApplicable!} cls="na" />}
      {rows.length > 0 && <details className="pz-all"><summary>Every factor with its points ({rows.length})</summary><FactorTable rows={rows} review={review} part={part.key} group={report.rating.group} /></details>}
    </section>
  );
}

/* ---- 7. benchmarks: which comparison, from whom, how wide */
const RATIO: Record<string, string> = { pe: "P/E", pb: "P/B", ev_ebitda: "EV/EBITDA" };
function benchmarkLine(key: string, b: BenchmarkDetail) {
  const ratio = RATIO[key.replace(/^(industry_median_|own_5y_median_)/, "")] || key;
  const scope = b.scope === "sector" ? "Sector" : b.scope === "own history" ? "Own five-year" : "Industry";
  const what = `${scope} ${ratio} ${b.method === "reported benchmark" ? "benchmark" : "median"}`;
  const value = b.value == null ? "not available" : `${nf(b.value, 2)}×`;
  const cover = b.positiveCount != null && b.universeCount != null ? ` From ${b.positiveCount} positive multiples; ${b.observedCount ?? "—"} of ${b.universeCount} peer records available${b.partial ? " (partial coverage, not a complete-industry median)" : ""}.` : "";
  const extra = b.scope === "sector" ? " The provider does not specify its statement basis, valuation date or aggregation method." : "";
  return { what, value, src: `${b.provider}${b.method ? `, ${b.method}` : ""}${b.asOf ? `, as of ${dateIN(b.asOf)}` : ""}.`, more: cover + extra };
}
function Benchmarks({ report }: { report: PrismReport }) {
  const metrics = Object.entries(report.benchmark?.metrics || {});
  return (
    <section className="card pz-card pz-sec" aria-label="Benchmarks">
      <h3 className="pz-h">Valuation benchmarks</h3>
      {metrics.length ? <ul className="pz-bm">{metrics.map(([k, b]) => { const l = benchmarkLine(k, b); return <li key={k}><p><b>{l.what}</b> <span className="pz-bm-v">{l.value}</span></p><p className="pz-sm">Source: {l.src}{l.more}</p></li>; })}</ul>
        : <p className="pz-empty">No verified industry or sector valuation benchmarks were available; the valuation factors that need one use group estimates.</p>}
      {report.benchmark?.note && <p className="pz-sm">{report.benchmark.note}</p>}
      <p className="pz-sm">Own-history comparisons use the company's own valuation multiples over up to five years; the comparison behind each valuation factor is listed with the factor.</p>
    </section>
  );
}

/* ---- the report */
export function PrismReportView({ report, actions = {} }: { report: PrismReport; actions?: ReportActions }) {
  const review = prismReview(report);
  return (
    <article className="pz-rep" aria-label={`${PRISM_NAME} report for ${report.company.name}`}>
      <Headline report={report} actions={actions} />
      {report.rating.dataIntegrityStatus === "REVIEW REQUIRED" && (
        <div className="pz-caution" role="note"><Icon name="alert" /><span><b>Data check: review required.</b> Some inputs could not be fully verified (see the review notes below). The caution does not change the score; read the result with it in mind.</span></div>
      )}
      {"legacy" in review && review.legacy && (
        <div className="pz-caution" role="note"><Icon name="info" /><span>This stored report predates the reader commentary. <button type="button" className="pz-link" onClick={actions.onRecalculate}>Recalculate</button> for the full review.</span></div>
      )}
      <Parts report={report} review={review} />
      <InputCompleteness completeness={review.completeness} onRecalculate={actions.onRecalculate} />
      <DataDates report={report} />
      <History report={report} />
      <section className="pz-sec" aria-label="Category pros and cons">
        <h3 className="pz-h">What supports the assessment and what needs attention</h3>
        <p className="pz-sub">Pros and cons reflect the company's assessment for its industry. Mixed results and unavailable information are shown separately; estimates are never presented as company strengths or weaknesses. A higher Risk score indicates lower assessed risk.</p>
        <div className="pz-cats">{review.parts.map((p) => <CategoryReview key={p.key} part={p} report={report} review={review} />)}</div>
      </section>
      <section className="card pz-card pz-sec" aria-label="Review notes">
        <h3 className="pz-h">Review notes</h3>
        {review.notes.length ? <ul className="pz-notes">{review.notes.map((n, i) => <li key={i}>{n}</li>)}</ul> : <p className="pz-empty">No material data limitations identified for this assessment.</p>}
      </section>
      <Benchmarks report={report} />
      {report.warnings.length > 0 && (
        <details className="card pz-card pz-sec pz-warn"><summary><h3 className="pz-h">Data checks ({report.warnings.length})</h3></summary>
          <p className="pz-sm">What the data loader recorded while preparing this calculation, as recorded.</p>
          <ul className="pz-notes">{report.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></details>
      )}
      <footer className="pz-foot">
        <p>This report assesses financial health using available financial and market information, with estimates where information is missing. It is not an investment recommendation or a prediction of future returns. The PDF of a calculation can be downloaded for 30 minutes; after that, recalculate to download a fresh one.</p>
        <p className="pz-note-line">{PRISM_NOTE}</p>
      </footer>
    </article>
  );
}
