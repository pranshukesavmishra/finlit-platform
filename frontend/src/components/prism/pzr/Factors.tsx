// Factor explorer: every factor of every part with value, points, a bar with threshold ticks, an input-state badge in words and the
// comparison behind it. Filter chips and a points sort apply to all parts; on a phone each row becomes a stacked card.
import { useMemo, useState } from "react";
import { nf } from "../../../lib/format";
import {
  STANDING_WORD, factorDetail, factorValue, isRated, partInfo, partShare, partsOf, reviewItem, score1, standing,
  type PartKey, type PrismMetric, type PrismReport, type PrismReview, type ReviewPart,
} from "../../../lib/prism";
import { BADGE_WORD, FILTER_WORD, POINT_TICKS, filterFactors, partVar, sortFactors, valueBar, type FactorFilter, type FactorSort } from "../../../lib/prismReport";

const FILTERS: FactorFilter[] = ["all", "strengths", "concerns", "estimated"];
const SORTS: [FactorSort, string][] = [["model", "Model order"], ["high", "Points: high to low"], ["low", "Points: low to high"]];

function PointsBar({ row }: { row: PrismMetric }) {
  const st = standing(row), vb = valueBar(row);
  return (
    <span className={"pzr-pb " + st} aria-hidden="true">
      <span className="pzr-pb-t"><i style={{ width: `${row.points == null ? 0 : Math.max(0, Math.min(100, row.points))}%` }} />{POINT_TICKS.map((t) => <u key={t} style={{ left: `${t}%` }} />)}</span>
      {vb && <span className="pzr-vb" title="Where the value sits between its 0-point and 100-point values; ticks are the red and green boundaries">
        <i className="r" style={{ width: `${(vb.red ?? 0) * 100}%` }} /><i className="g" style={{ left: `${(vb.green ?? 1) * 100}%` }} />
        {vb.red != null && <u style={{ left: `${vb.red * 100}%` }} />}{vb.green != null && <u style={{ left: `${vb.green * 100}%` }} />}
        <b style={{ left: `${vb.pos * 100}%` }} />
      </span>}
    </span>
  );
}

function Row({ row, review, part, group }: { row: PrismMetric; review: PrismReview; part: PartKey; group: string }) {
  const item = reviewItem(review, part, row.metric), st = standing(row), detail = factorDetail(row, group);
  const hasVb = valueBar(row) != null;
  const lines = [item?.summary, detail, item?.comparisonText].filter((t): t is string => !!t).reduce<string[]>((acc, t) => (acc.some((a) => a.includes(t.replace(/\.$/, ""))) ? acc : [...acc.filter((a) => !t.includes(a.replace(/\.$/, ""))), t]), []);
  return (
    <li className={"pzr-fr " + st} id={`pzr-f-${row.metric}`}>
      <span className="pzr-fr-n"><b>{item?.label || row.label}</b>
        {lines.map((t) => <small key={t}>{t}</small>)}</span>
      <span className="pzr-fr-v" data-l="Value">{row.value == null && item ? item.valueText : factorValue(row)}</span>
      <span className="pzr-fr-b" data-l={hasVb ? "Points and range" : "Points"}><PointsBar row={row} /></span>
      <span className="pzr-fr-p" data-l="Points">{row.points == null ? "—" : <>{nf(row.points, 0)}<small> / 100</small></>}</span>
      <span className="pzr-fr-s" data-l="Status">
        <span className={"pzr-badge s" + row.status}><i aria-hidden="true" />{BADGE_WORD[row.status]}</span>
        <span className={"pzr-sw " + st}><i aria-hidden="true" />{STANDING_WORD[st]}</span>
      </span>
    </li>
  );
}

function PartSection({ part, index, report, review, filter, sort }: { part: ReviewPart; index: number; report: PrismReport; review: PrismReview; filter: FactorFilter; sort: FactorSort }) {
  const { rating } = report, rated = isRated(rating);
  const all = rating.metrics.filter((m) => m.part === part.key);
  const rows = useMemo(() => sortFactors(filterFactors(all, filter), sort), [all, filter, sort]);
  const score = rated ? part.score ?? rating.parts[part.key] ?? null : null;
  return (
    <section id={`pzr-part-${part.key}`} tabIndex={-1} className="pzr-fp" aria-labelledby={`pzr-fh-${part.key}`} style={{ "--c": partVar(part.key, index) } as React.CSSProperties}>
      <header className="pzr-fp-h">
        <span className="pzr-fp-sw" aria-hidden="true" />
        <div><h4 id={`pzr-fh-${part.key}`}>{partInfo(part.key).name}</h4><p>{partInfo(part.key).what} Counts for {partShare(rating.partWeights, part.key)}% of the overall score.</p></div>
        <p className="pzr-fp-s">{score == null ? <small>Not rated</small> : <>{score1(score)}<small> / 100</small></>}</p>
      </header>
      {rated && part.notes?.map((n, i) => <p key={i} className="pzr-fnote">{n}</p>)}
      {rows.length ? (
        <>
          <div className="pzr-fr-head" aria-hidden="true"><span>Factor</span><span>Value</span><span>Position</span><span>Points</span><span>Status</span></div>
          <ul className="pzr-fl" aria-label={`${partInfo(part.key).name} factors`}>{rows.map((r) => <Row key={r.metric} row={r} review={review} part={part.key} group={rating.group} />)}</ul>
        </>
      ) : <p className="pzr-empty">{all.length ? `No ${FILTER_WORD[filter].toLowerCase()} in this part.` : "No factors are listed for this part."}</p>}
    </section>
  );
}

export function FactorExplorer({ report, review }: { report: PrismReport; review: PrismReview }) {
  const [filter, setFilter] = useState<FactorFilter>("all"), [sort, setSort] = useState<FactorSort>("model");
  const metrics = report.rating.metrics;
  const order = partsOf(report.rating);
  const parts = order.map((k) => review.parts.find((p) => p.key === k) ?? { key: k, name: partInfo(k).name, score: report.rating.parts[k] ?? null, notes: [], pros: [], cons: [], mixed: [], unavailable: [] });
  const count = (f: FactorFilter) => filterFactors(metrics, f).length;
  return (
    <section className="pzr-sec" aria-labelledby="pzr-h-fx">
      <header className="pzr-sh"><h3 id="pzr-h-fx">Every factor</h3>
        <p>Points run from 0 to 100. A factor supports the score at 70 or more and holds it back below 40. Estimated factors are never counted as strengths or concerns. A higher Risk score means lower risk.</p></header>
      <div className="pzr-tools pzr-noprint">
        <div className="pzr-chipsrow" role="group" aria-label="Filter factors">
          {FILTERS.map((f) => <button key={f} type="button" className={"pzr-chip" + (filter === f ? " on" : "")} aria-pressed={filter === f} onClick={() => setFilter(f)}>{FILTER_WORD[f]} <small>{count(f)}</small></button>)}
        </div>
        <label className="pzr-sortl">Sort by<select value={sort} onChange={(e) => setSort(e.target.value as FactorSort)}>{SORTS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>
      </div>
      <div className="pzr-fps">{parts.map((p, i) => <PartSection key={p.key} part={p} index={i} report={report} review={review} filter={filter} sort={sort} />)}</div>
    </section>
  );
}
