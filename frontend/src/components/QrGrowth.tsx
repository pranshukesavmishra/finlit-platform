// "Filter companies by growth" on the Latest results page: the two filter cards (QoQ, YoY), the AND / OR choice, and the three donut charts.
// The controls only edit a GrowthState (kept in the page address); the SERVER filters and counts, so everything shown here is what it sends back.
import { useEffect, useId, useRef, useState } from "react";
import { nf } from "../lib/format";
import {
  GROWTH_METRICS, GROWTH_OPS, condOn, cleanValue, growthIsDefault, metricLabel, opWords, pctOf, valueProblem,
  DEFAULT_GROWTH, type GrowthCond, type GrowthMetric, type GrowthOp, type GrowthState, type GrowthSummary, type QDistribution,
} from "../lib/qresults";

export const LENDER_NOTE = "Banks and lenders do not report operating profit growth, so they never match an operating-profit filter.";
const DEBOUNCE = 600;

function CondCard({ kind, cond, onCommit, disabledNote }: { kind: "qoq" | "yoy"; cond: GrowthCond; onCommit: (c: GrowthCond) => void; disabledNote?: string }) {
  const id = useId();
  const [draft, setDraft] = useState(cond.value);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => { setDraft(cond.value); }, [cond.value]);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const bad = valueProblem(draft);
  const title = kind === "qoq" ? "Quarter-on-quarter (QoQ) growth" : "Year-on-year (YoY) growth";
  const against = kind === "qoq" ? "against the quarter before" : "against the same quarter a year earlier";
  const push = (next: GrowthCond) => { window.clearTimeout(timer.current); onCommit(next); };
  const commitDraft = () => { window.clearTimeout(timer.current); if (!valueProblem(draft) && cleanValue(draft) !== cleanValue(cond.value)) onCommit({ ...cond, value: cleanValue(draft) }); };
  const typed = (v: string) => {
    setDraft(v);
    window.clearTimeout(timer.current);
    if (!valueProblem(v)) timer.current = window.setTimeout(() => onCommit({ ...cond, value: cleanValue(v) }), DEBOUNCE);
  };
  const ex = `e.g. ${metricLabel(cond.metric)} ${kind === "qoq" ? "QoQ" : "YoY"} ${cond.op} ${kind === "qoq" ? "1" : "10"}%`;
  return (
    <fieldset className={"qg-card " + kind}>
      <legend><b>{title}</b></legend>
      <p className="qg-sub">{against}</p>
      <div className="qg-fields">
        <label className="wl-sel"><span>Metric</span>
          <select value={cond.metric} onChange={(e) => push({ ...cond, metric: e.target.value as GrowthMetric, value: cleanValue(draft) && !bad ? cleanValue(draft) : cond.value })}>
            {GROWTH_METRICS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label className="wl-sel"><span>Operator</span>
          <select value={cond.op} onChange={(e) => push({ ...cond, op: e.target.value as GrowthOp, value: cleanValue(draft) && !bad ? cleanValue(draft) : cond.value })}>
            {GROWTH_OPS.map((o) => <option key={o} value={o}>{o} ({opWords(o)})</option>)}</select></label>
        <label className="wl-sel qg-val"><span>Value %</span>
          <input type="text" inputMode="decimal" autoComplete="off" value={draft} placeholder="e.g. 1" aria-invalid={bad ? true : undefined} aria-describedby={`${id}-hint ${bad ? id + "-err" : ""}`}
            onChange={(e) => typed(e.target.value)} onBlur={commitDraft} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commitDraft(); } }} /></label>
      </div>
      <p id={`${id}-hint`} className="qg-hint">{ex}</p>
      {bad && <p id={`${id}-err`} className="qg-err" role="alert">{bad}</p>}
      {disabledNote && <p className="qg-note">{disabledNote}</p>}
    </fieldset>
  );
}

export function GrowthPanel({ state, onChange, summary, loading }: { state: GrowthState; onChange: (g: GrowthState) => void; summary?: GrowthSummary | null; loading?: boolean }) {
  const both = condOn(state.qoq) && condOn(state.yoy);
  const opUsed = state.qoq.metric === "operatingProfit" || state.yoy.metric === "operatingProfit";
  const set = (patch: Partial<GrowthState>) => onChange({ ...state, ...patch });
  const miss = (n: number, label: string, m: GrowthMetric) => (n > 0 ? `${nf(n, 0)} ${n === 1 ? "company has" : "companies have"} no ${label} ${metricLabel(m).toLowerCase()} growth figure and cannot match it.` : "");
  return (
    <section className="card qg" aria-labelledby="qg-h">
      <div className="card-h"><h3 id="qg-h">Filter companies by growth</h3>
        <button type="button" className="btn qg-reset" disabled={growthIsDefault(state)} onClick={() => onChange(DEFAULT_GROWTH)}>Reset filters</button></div>
      <p className="muted qg-lead">Type a percentage threshold for the growth of revenue, operating profit or net profit. Leave a filter empty to switch it off; one filter works alone.</p>
      <div className="qg-grid">
        <CondCard kind="qoq" cond={state.qoq} onCommit={(c) => set({ qoq: c })} />
        <div className="qg-join" role="group" aria-label="How the two filters combine">
          {(["and", "or"] as const).map((j) => <button key={j} type="button" className={state.join === j ? "on" : ""} aria-pressed={state.join === j} onClick={() => set({ join: j })}>{j.toUpperCase()}</button>)}
        </div>
        <CondCard kind="yoy" cond={state.yoy} onCommit={(c) => set({ yoy: c })} />
      </div>
      {opUsed && <p className="qg-note" id="qg-lender">{LENDER_NOTE}</p>}
      <p className="qg-state" role="status" aria-live="polite">
        {summary ? <>
          <b>{nf(summary.matching, 0)}</b> of {nf(summary.withFigures, 0)} companies with figures match{both ? ` ${summary.join === "and" ? "both filters" : "either filter"}` : ""}.{" "}
          {summary.qoq && miss(summary.qoqMissing, "QoQ", state.qoq.metric)} {summary.yoy && miss(summary.yoyMissing, "YoY", state.yoy.metric)}
        </> : loading && (condOn(state.qoq) || condOn(state.yoy)) ? "Applying the filter…" : "No growth filter is on, so every company in the table is shown."}
      </p>
    </section>
  );
}

// ---------------------------------------------------------------- donuts
export type Part = { label: string; n: number; color: string };
const R = 70, r = 46, C = 90;
const pt = (rad: number, a: number) => `${(C + rad * Math.cos(a)).toFixed(2)},${(C + rad * Math.sin(a)).toFixed(2)}`;

/** A plain SVG donut with a visible legend that carries every count and share (the text alternative), and one aria-label that says the same in a sentence. */
export function QrDonut({ title, parts, centerLabel, empty }: { title: string; parts: Part[]; centerLabel: string; empty: string }) {
  const total = parts.reduce((a, p) => a + p.n, 0);
  const sentence = `${title}: ${total === 0 ? empty : parts.map((p) => `${p.label} ${nf(p.n, 0)} (${nf(pctOf(p.n, total), 1)}%)`).join(", ")}`;
  let a0 = -Math.PI / 2;
  const live = parts.filter((p) => p.n > 0);
  const arcs = live.map((p) => {
    const sweep = (p.n / total) * Math.PI * 2, a1 = a0 + sweep - (live.length > 1 ? 0.012 : 0), big = a1 - a0 > Math.PI ? 1 : 0;
    const d = `M${pt(R, a0)}A${R},${R} 0 ${big} 1 ${pt(R, a1)}L${pt(r, a1)}A${r},${r} 0 ${big} 0 ${pt(r, a0)}Z`;
    a0 += sweep;
    return { p, d };
  });
  return (
    <figure className="card qg-chart">
      <figcaption><h3>{title}</h3></figcaption>
      <div className="qg-dn">
        <svg viewBox="0 0 180 180" role="img" aria-label={sentence} className="qg-svg">
          <circle cx={C} cy={C} r={(R + r) / 2} fill="none" stroke="var(--s3)" strokeWidth={R - r} />
          {live.length === 1 ? <circle cx={C} cy={C} r={(R + r) / 2} fill="none" stroke={live[0].color} strokeWidth={R - r} /> : arcs.map(({ p, d }) => <path key={p.label} d={d} fill={p.color} />)}
          <text x="90" y="89" textAnchor="middle" className="qg-c1">{nf(total, 0)}</text>
          <text x="90" y="106" textAnchor="middle" className="qg-c2">{centerLabel}</text>
        </svg>
        {total === 0 ? <p className="muted qg-none">{empty}</p> : (
          <ul className="qg-legend" aria-label={`${title}, counts and shares`}>
            {parts.map((p) => <li key={p.label}><i style={{ background: p.color }} aria-hidden="true" /><span>{p.label}</span><b>{nf(p.n, 0)}</b><small>{nf(pctOf(p.n, total), 1)}%</small></li>)}
          </ul>
        )}
      </div>
    </figure>
  );
}

const SECTOR_COLORS = ["var(--qr-c1)", "var(--qr-c2)", "var(--qr-c3)", "var(--qr-c4)", "var(--qr-c5)", "var(--qr-c6)", "var(--qr-c7)", "var(--qr-c8)"];
const CAP_COLORS: Record<string, string> = { Large: "var(--qr-c1)", Mid: "var(--qr-c2)", Small: "var(--qr-c3)", "Not classified": "var(--qr-c8)" };

export function growthParts(g: GrowthSummary): Part[] {
  if (g.qoq && g.yoy) return [{ label: "Both filters", n: g.both, color: "var(--gold)" }, { label: "Only QoQ", n: g.onlyQoQ, color: "var(--qr-qoq)" }, { label: "Only YoY", n: g.onlyYoY, color: "var(--qr-yoy)" }, { label: "Neither", n: g.neither, color: "var(--qr-none)" }];
  const hit = g.qoq ? g.onlyQoQ : g.onlyYoY;
  return [{ label: `Meets the ${g.qoq ? "QoQ" : "YoY"} filter`, n: hit, color: g.qoq ? "var(--qr-qoq)" : "var(--qr-yoy)" }, { label: "Does not meet it", n: g.neither, color: "var(--qr-none)" }];
}

export function GrowthCharts({ summary, dist, locked }: { summary?: GrowthSummary | null; dist?: QDistribution; locked: boolean }) {
  return (
    <section className="qg-charts" aria-label="Charts for the companies in the table">
      {summary
        ? <QrDonut title="Companies meeting both filters" parts={growthParts(summary)} centerLabel="with figures" empty="No company has figures for this quarter." />
        : <figure className="card qg-chart"><figcaption><h3>Companies meeting both filters</h3></figcaption>
          <p className="muted qg-none">{locked ? "Growth filters and their counts are part of the Silver plan." : "Type a threshold in one or both filters above to see how many companies meet it."}</p></figure>}
      <QrDonut title="Sector-wise distribution" parts={(dist?.sectors || []).map((s, i) => ({ label: s.name, n: s.n, color: s.name === "Others" ? "var(--qr-c8)" : SECTOR_COLORS[i % 7] }))} centerLabel="companies" empty="No companies in this view." />
      <QrDonut title="Market cap distribution" parts={(dist?.caps || []).map((c) => ({ label: c.name, n: c.n, color: CAP_COLORS[c.name] || "var(--qr-c8)" }))} centerLabel="companies" empty="No companies in this view." />
      <p className="muted qg-foot">Counts cover every matching company, not just the page shown. Market cap groups are the site's own Large, Mid and Small bands; companies without a band are shown as Not classified. Informational only, not a recommendation.</p>
    </section>
  );
}
