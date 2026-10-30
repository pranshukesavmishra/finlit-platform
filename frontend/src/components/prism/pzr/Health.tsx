// Peer and benchmark panel, data completeness and freshness, review notes, warnings, and "how this is calculated".
import { useState, type ReactNode } from "react";
import { Icon } from "../../../lib/icons";
import { dateIN, nf } from "../../../lib/format";
import { completenessNote, isRated, notRatedReason, pctWhole, statementWord, type BenchmarkDetail, type Completeness, type PrismReport } from "../../../lib/prism";
import { ageWords, daysBefore, howRules, peerRows, type PeerRow } from "../../../lib/prismReport";
import { ChartTable, ShowTable } from "../PrismCharts";

/** A section that opens and closes; its content stays in the page so a printout always includes it. */
export function Collapse({ title, count, children, defaultOpen = false, id }: { title: string; count?: number; children: ReactNode; defaultOpen?: boolean; id: string }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={"pzr-col" + (open ? " open" : "")}>
      <h3><button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}><span>{title}{count != null && <small> ({count})</small>}</span><i className="pzr-chev" aria-hidden="true" /></button></h3>
      <div id={id} className="pzr-col-b" hidden={!open}>{children}</div>
    </div>
  );
}

/* ---- benchmark words (scope and provider disclosed) */
const RATIO: Record<string, string> = { pe: "P/E", pb: "P/B", ev_ebitda: "EV/EBITDA" };
export function benchmarkLine(key: string, b: BenchmarkDetail) {
  const ratio = RATIO[key.replace(/^(industry_median_|own_5y_median_)/, "")] || key;
  const scope = b.scope === "sector" ? "Sector" : b.scope === "own history" ? "Own five-year" : "Industry";
  const what = `${scope} ${ratio} ${b.method === "reported benchmark" ? "benchmark" : "median"}`;
  const value = b.value == null ? "not available" : `${nf(b.value, 2)}×`;
  const cover = b.positiveCount != null && b.universeCount != null ? ` From ${b.positiveCount} positive multiples; ${b.observedCount ?? "—"} of ${b.universeCount} peer records available${b.partial ? " (partial coverage, not a complete-industry median)" : ""}.` : "";
  const extra = b.scope === "sector" ? " The provider does not specify its statement basis, valuation date or aggregation method." : "";
  return { what, value, src: `${b.provider}${b.method ? `, ${b.method}` : ""}${b.asOf ? `, as of ${dateIN(b.asOf)}` : ""}.`, more: cover + extra };
}

function PeerBlock({ row }: { row: PeerRow }) {
  const max = Math.max(row.company ?? 0, row.benchmark ?? 0, row.own ?? 0) * 1.12 || 1;
  const pos = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  const diff = row.company != null && row.benchmark ? ((row.company - row.benchmark) / row.benchmark) * 100 : null;
  const l = row.detail ? benchmarkLine(`industry_median_${row.key}`, row.detail) : null;
  const sentence = row.company != null && row.benchmark != null
    ? `${row.label}: the company is at ${nf(row.company, 2)}× against a benchmark of ${nf(row.benchmark, 2)}×, ${nf(Math.abs(diff ?? 0), 0)}% ${diff != null && diff < 0 ? "below" : "above"} it.`
    : `${row.label}: ${row.company != null ? `the company is at ${nf(row.company, 2)}×; no benchmark is available.` : `benchmark ${nf(row.benchmark!, 2)}×; no company multiple is available.`}`;
  return (
    <li className="pzr-peer">
      <div className="pzr-peer-h"><b>{row.label}</b><span>{diff == null ? "" : `${nf(Math.abs(diff), 0)}% ${diff < 0 ? "below" : "above"} the benchmark`}</span></div>
      <div className="pzr-peer-bars" role="img" aria-label={sentence} style={{ "--bm": row.benchmark == null ? 0 : Math.min(1, row.benchmark / max) } as React.CSSProperties}>
        {([["Company", row.company, "co"], ["Benchmark", row.benchmark, "bm"], ["Own 5-year median", row.own, "own"]] as const).filter(([, v]) => v != null).map(([n, v, c]) => (
          <div key={n} className={"pzr-peer-r " + c}><span>{n}</span><i><b style={{ width: pos(v!) }} /></i><em>{nf(v!, 2)}×</em></div>
        ))}
        {row.benchmark != null && <u aria-hidden="true" />}
      </div>
      {l ? <p className="pzr-small"><b>{l.what} {l.value}.</b> Source: {l.src}{l.more}</p> : <p className="pzr-small">No verified benchmark for this multiple; the model uses a group estimate where it needs one.</p>}
    </li>
  );
}

export function Peers({ report }: { report: PrismReport }) {
  const rows = peerRows(report), [table, setTable] = useState(false);
  const extra = Object.entries(report.benchmark?.metrics || {}).filter(([k]) => !rows.some((r) => k === `industry_median_${r.key}`));
  return (
    <section className="pzr-sec" aria-labelledby="pzr-h-peer">
      <header className="pzr-sh"><h3 id="pzr-h-peer">Valuation against the benchmark</h3><p>Price multiples of the company next to the benchmark used in the Valuation part. The line marks the benchmark.</p></header>
      {rows.length ? <ul className="pzr-peers">{rows.map((r) => <PeerBlock key={r.key} row={r} />)}</ul>
        : <p className="pzr-empty">No verified industry or sector valuation benchmarks were available; the valuation factors that need one use group estimates.</p>}
      {extra.length > 0 && <ul className="pzr-bm">{extra.map(([k, b]) => { const l = benchmarkLine(k, b); return <li key={k}><b>{l.what} {l.value}</b><span className="pzr-small">Source: {l.src}{l.more}</span></li>; })}</ul>}
      {report.benchmark?.note && <p className="pzr-small">{report.benchmark.note}</p>}
      <p className="pzr-small">Own-history comparisons use the company's own multiples over up to five years; the comparison behind each valuation factor is listed with the factor.</p>
      {rows.length > 0 && <><div className="pzr-cfoot"><span /><ShowTable on={table} set={setTable} /></div>
        {table && <ChartTable caption="Company multiple, benchmark and own five-year median" head={["Multiple", "Company", "Benchmark", "Own 5-year median"]} rows={rows.map((r) => [r.label, r.company == null ? "—" : `${nf(r.company, 2)}×`, r.benchmark == null ? "—" : `${nf(r.benchmark, 2)}×`, r.own == null ? "—" : `${nf(r.own, 2)}×`])} />}</>}
    </section>
  );
}

/* ---- completeness and freshness */
const DATES: [keyof PrismReport["inputMeta"], string][] = [["quarterlyAsOf", "Quarterly results"], ["annualAsOf", "Annual results"], ["balanceAsOf", "Balance sheet"], ["ownershipAsOf", "Ownership"], ["priceAsOf", "Market price"]];

function Freshness({ report }: { report: PrismReport }) {
  const m = report.inputMeta, requested = m.requestedStatementType, used = report.statementType;
  return (
    <div className="pzr-fresh">
      <h4>Data freshness</h4>
      <ol className="pzr-tl">{DATES.map(([k, label]) => {
        const v = m[k] as string | null | undefined, d = daysBefore(v, report.createdAt);
        return <li key={k} className={v ? "ok" : "na"}><i aria-hidden="true" /><span><b>{label}</b><em>{v ? dateIN(v) : "Not available"}</em><small>{v ? ageWords(d) : "No date was supplied for this input."}</small></span><strong>{v ? "Available" : "Not available"}</strong></li>;
      })}</ol>
      <p className="pzr-small"><b>{statementWord(used)} statements</b> are used throughout this report.
        {requested && requested !== used ? ` ${statementWord(requested)} statements were requested but unavailable, so the whole report uses ${used} statements instead.` : ""}
        {m.assetQualityStatementType && m.assetQualityStatementType !== used ? ` Asset-quality ratios use the ${m.assetQualityStatementType} disclosure.` : ""}</p>
    </div>
  );
}

function Checklist({ report, completeness, onRecalculate }: { report: PrismReport; completeness?: Completeness; onRecalculate?: () => void }) {
  const { rating } = report;
  const items: { ok: boolean; text: ReactNode }[] = [
    { ok: rating.confidence >= 0.8, text: <><b>{pctWhole(rating.confidence)} of inputs available.</b> Completeness of the data, not a probability.{completenessNote(rating) ? " The data coverage is not what withheld the rating." : ""}</> },
    { ok: rating.judgedQuarters >= 6, text: <><b>{rating.judgedQuarters} of 10 comparable quarters</b> for the growth streaks.</> },
    { ok: rating.dataIntegrityStatus === "PASS", text: rating.dataIntegrityStatus === "PASS" ? <><b>Data checks passed.</b></> : <><b>Data check: review required.</b> {notRatedReason(rating) ?? "Some inputs could not be fully verified."} The caution does not change the score.</> },
  ];
  if (completeness) {
    items.push({ ok: completeness.missingFactorCount === 0, text: completeness.missingFactorCount ? <><b>{completeness.missingFactorCount} factor{completeness.missingFactorCount === 1 ? "" : "s"} unavailable</b>, estimated or left out.</> : <><b>All applicable factors have usable inputs.</b></> });
    items.push({ ok: completeness.limitedHistoryCount === 0, text: completeness.limitedHistoryCount ? <><b>{completeness.limitedHistoryCount} limited histor{completeness.limitedHistoryCount === 1 ? "y" : "ies"}</b>, with fewer comparisons than the model asks for.</> : <><b>Every history is long enough</b> for its comparison.</> });
  }
  return (
    <div className="pzr-check">
      <h4>Completeness</h4>
      <ul className="pzr-cl">{items.map((it, i) => <li key={i} className={it.ok ? "ok" : "warn"}><Icon name={it.ok ? "check" : "alert"} /><span>{it.text}</span><strong>{it.ok ? "Complete" : "Check"}</strong></li>)}</ul>
      {!completeness && <p className="pzr-small">Recalculate this report to see the latest missing-input and history checks.{onRecalculate && <> <button type="button" className="pzr-link pzr-noprint" onClick={onRecalculate}>Recalculate</button></>}</p>}
      {completeness && completeness.items.length > 0 && (
        <ul className="pzr-miss">{completeness.items.map((item) => (
          <li key={`${item.category}-${item.metric}`}>
            <p><span className={"pzr-kind " + item.kind}>{item.kind === "missing" ? "Unavailable" : "Limited history"}</span>{item.category} · {item.label}</p>
            <p>{item.reason}</p><p className="pzr-small">{item.treatment}</p>
          </li>))}</ul>
      )}
    </div>
  );
}

export function Health({ report, completeness, onRecalculate, notes }: { report: PrismReport; completeness?: Completeness; onRecalculate?: () => void; notes: string[] }) {
  return (
    <section className="pzr-sec" aria-labelledby="pzr-h-health">
      <header className="pzr-sh"><h3 id="pzr-h-health">Data completeness and freshness</h3><p>What the score is built from, how recent each input is, and what is missing.</p></header>
      <div className="pzr-two"><Checklist report={report} completeness={completeness} onRecalculate={onRecalculate} /><Freshness report={report} /></div>
      <div className="pzr-cols">
        {notes.length > 0 && <Collapse id="pzr-notes" title="Review notes" count={notes.length}><ul className="pzr-notes">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul></Collapse>}
        {report.warnings.length > 0 && <Collapse id="pzr-warn" title="Data checks recorded while loading" count={report.warnings.length}><p className="pzr-small">What the data loader recorded while preparing this calculation, as recorded.</p><ul className="pzr-notes">{report.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></Collapse>}
        <Collapse id="pzr-how" title="How this is calculated"><ul className="pzr-notes">{howRules(report.rating).map((r) => <li key={r}>{r}</li>)}</ul>
          {!isRated(report.rating) && <p className="pzr-small">This company is not rated, so the part scores that exist inside the model are not shown.</p>}</Collapse>
      </div>
    </section>
  );
}
