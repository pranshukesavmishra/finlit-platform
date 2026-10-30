// "Filter companies by growth" on the Latest results page: a grid of thresholds (Revenue, Operating profit, Net profit by QoQ and YoY), the all / any choice,
// quick presets, and the three donut charts. The controls only edit a GrowthState (kept in the page address); the SERVER filters and counts, so everything
// shown here is what it sends back.
import { useEffect, useId, useRef, useState } from "react";
import { nf } from "../lib/format";
import {
  CELL_OF, GROWTH_METRICS, GROWTH_OPS, GROWTH_PERIODS, GROWTH_PRESETS, activePreset, applyPreset, cellKeyOf, cleanValue, growthIsDefault, metricLabel, onCells, opWords, pctOf, periodLabel, valueProblem,
  DEFAULT_GROWTH, type CellKey, type GrowthCond, type GrowthCondSummary, type GrowthOp, type GrowthState, type GrowthSummary, type QDistribution,
} from "../lib/qresults";

export const LENDER_NOTE = "Banks and lenders do not report operating profit growth, so they never match an operating-profit filter.";
const DEBOUNCE = 600;
const SHOWN_MISSING = 3;

function Cell({ k, cond, onCommit }: { k: CellKey; cond: GrowthCond; onCommit: (c: GrowthCond) => void }) {
  const id = useId();
  const [metric, per] = CELL_OF[k];
  const name = `${metricLabel(metric)} ${periodLabel(per)}`;
  const [draft, setDraft] = useState(cond.value);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => { setDraft(cond.value); }, [cond.value]);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const bad = valueProblem(draft);
  const keep = cleanValue(draft) && !bad ? cleanValue(draft) : cond.value;
  const commitDraft = () => { window.clearTimeout(timer.current); if (!valueProblem(draft) && cleanValue(draft) !== cleanValue(cond.value)) onCommit({ ...cond, value: cleanValue(draft) }); };
  const typed = (v: string) => {
    setDraft(v);
    window.clearTimeout(timer.current);
    if (!valueProblem(v)) timer.current = window.setTimeout(() => onCommit({ ...cond, value: cleanValue(v) }), DEBOUNCE);
  };
  return (
    <div className="qg-cell">
      <span className="qg-cl" aria-hidden="true">{periodLabel(per)}</span>
      <select aria-label={`${name} operator`} value={cond.op} onChange={(e) => { window.clearTimeout(timer.current); onCommit({ op: e.target.value as GrowthOp, value: keep }); }}>
        {GROWTH_OPS.map((o) => <option key={o} value={o}>{o} ({opWords(o)})</option>)}</select>
      <span className="qg-vw"><input type="text" inputMode="decimal" autoComplete="off" aria-label={`${name} value in per cent`} value={draft} placeholder="off" aria-invalid={bad ? true : undefined} aria-describedby={bad ? `${id}-err` : undefined}
        onChange={(e) => typed(e.target.value)} onBlur={commitDraft} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commitDraft(); } }} /><i aria-hidden="true">%</i></span>
      {bad && <p id={`${id}-err`} className="qg-err" role="alert">{bad}</p>}
    </div>
  );
}

/** "<n> companies have no QoQ revenue growth figure and cannot match it." for one condition. */
export const missingLine = (c: GrowthCondSummary) => `${nf(c.missing, 0)} ${c.missing === 1 ? "company has" : "companies have"} no ${periodLabel(c.period)} ${metricLabel(c.metric).toLowerCase()} growth figure and cannot match it.`;

function Missing({ conds }: { conds: GrowthCondSummary[] }) {
  const [open, setOpen] = useState(false);
  const lacking = conds.filter((c) => c.missing > 0).sort((a, b) => b.missing - a.missing);
  const head = lacking.slice(0, SHOWN_MISSING), rest = lacking.slice(SHOWN_MISSING);
  if (!lacking.length) return null;
  return (
    <>
      <ul className="qg-miss">{head.map((c) => <li key={c.metric + c.period}>{missingLine(c)}</li>)}
        {open && rest.map((c) => <li key={c.metric + c.period}>{missingLine(c)}</li>)}</ul>
      {rest.length > 0 && <button type="button" className="alx-link qg-more" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide details" : `and ${rest.length} more ${rest.length === 1 ? "condition" : "conditions"} (details)`}</button>}
    </>
  );
}

export function GrowthPanel({ state, onChange, summary, loading }: { state: GrowthState; onChange: (g: GrowthState) => void; summary?: GrowthSummary | null; loading?: boolean }) {
  const on = onCells(state), k = on.length;
  const opUsed = on.some((c) => CELL_OF[c][0] === "operatingProfit");
  const preset = activePreset(state);
  const setCell = (key: CellKey, c: GrowthCond) => onChange({ ...state, cells: { ...state.cells, [key]: c } });
  const modes = [["and", "Match all", "Every filled condition must hold"], ["or", "Match any", "At least one filled condition must hold"]] as const;
  return (
    <section className="card qg" aria-labelledby="qg-h">
      <div className="card-h"><h3 id="qg-h">Filter companies by growth</h3>
        <button type="button" className="btn qg-reset" disabled={growthIsDefault(state)} onClick={() => onChange(DEFAULT_GROWTH)}>Reset filters</button></div>
      <p className="muted qg-lead">Type a percentage threshold for the growth of revenue, operating profit or net profit, on the quarter before (QoQ) and on the same quarter a year earlier (YoY). Leave a cell empty to switch it off; any one cell works alone.</p>
      <div className="qg-presets" role="group" aria-label="Quick fills">
        <span className="qg-pl">Quick fills</span>
        {GROWTH_PRESETS.map((p) => <button key={p.id} type="button" className={preset === p.id ? "on" : ""} aria-pressed={preset === p.id} title={p.hint} onClick={() => onChange(applyPreset(p))}>{p.label}</button>)}
      </div>
      <fieldset className="qg-set">
        <legend className="sr-only">Growth thresholds, by metric and period</legend>
        <div className="qg-gh" aria-hidden="true"><span /><span><b>Quarter-on-quarter (QoQ)</b><small>against the quarter before</small></span><span><b>Year-on-year (YoY)</b><small>against the same quarter a year earlier</small></span></div>
        {GROWTH_METRICS.map(([m, label]) => (
          <div key={m} className="qg-row" role="group" aria-label={`${label} growth`}>
            <span className="qg-rl">{label}</span>
            {GROWTH_PERIODS.map(([per]) => { const key = cellKeyOf(m, per); return <Cell key={key} k={key} cond={state.cells[key]} onCommit={(c) => setCell(key, c)} />; })}
          </div>
        ))}
      </fieldset>
      <div className="qg-modewrap">
        <div className="qg-join" role="group" aria-label="How the filled conditions combine">
          {modes.map(([j, l, t]) => <button key={j} type="button" className={state.join === j ? "on" : ""} aria-pressed={state.join === j} title={t} onClick={() => onChange({ ...state, join: j })}>{l}</button>)}
        </div>
        <span className="qg-modehint">{state.join === "and" ? "Every filled condition must be met." : "At least one filled condition must be met."}{k < 2 ? " It makes no difference while fewer than two cells are filled." : ""}</span>
      </div>
      {opUsed && <p className="qg-note" id="qg-lender">{LENDER_NOTE}</p>}
      <div className="qg-state" role="status" aria-live="polite">
        {summary ? <>
          <p><b>{nf(summary.matching, 0)}</b> of {nf(summary.withFigures, 0)} companies with figures match {summary.k === 1 ? "the condition" : summary.join === "and" ? `all ${summary.k} conditions` : `any of the ${summary.k} conditions`}.</p>
          <Missing conds={summary.conditions} />
        </> : <p>{loading && k > 0 ? "Applying the filter…" : "No growth filter is on, so every company in the table is shown."}</p>}
      </div>
      <p className="qg-note">Growth is not defined when the earlier quarter was zero or a loss, or is not in our statements; such a company shows a dash, has no figure for that cell and cannot match it. Information only, not advice.</p>
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
  if (g.k === 1) return [{ label: "Meets the condition", n: g.metAll, color: "var(--gold)" }, { label: "Does not meet it", n: g.metNone, color: "var(--qr-none)" }];
  return [{ label: `Meet all ${g.k}`, n: g.metAll, color: "var(--gold)" }, { label: "Meet some, not all", n: g.metSome, color: "var(--qr-qoq)" }, { label: "Meet none", n: g.metNone, color: "var(--qr-none)" }];
}

export function GrowthCharts({ summary, dist, locked }: { summary?: GrowthSummary | null; dist?: QDistribution; locked: boolean }) {
  return (
    <section className="qg-charts" aria-label="Charts for the companies in the table">
      {summary
        ? <QrDonut title="Companies meeting the growth conditions" parts={growthParts(summary)} centerLabel="with figures" empty="No company has figures for this quarter." />
        : <figure className="card qg-chart"><figcaption><h3>Companies meeting the growth conditions</h3></figcaption>
          <p className="muted qg-none">{locked ? "Growth filters and their counts are part of the Silver plan." : "Fill one or more cells of the growth filter above to see how many companies meet them."}</p></figure>}
      <QrDonut title="Sector-wise distribution" parts={(dist?.sectors || []).map((s, i) => ({ label: s.name, n: s.n, color: s.name === "Others" ? "var(--qr-c8)" : SECTOR_COLORS[i % 7] }))} centerLabel="companies" empty="No companies in this view." />
      <QrDonut title="Market cap distribution" parts={(dist?.caps || []).map((c) => ({ label: c.name, n: c.n, color: CAP_COLORS[c.name] || "var(--qr-c8)" }))} centerLabel="companies" empty="No companies in this view." />
      <p className="muted qg-foot">Counts cover every matching company, not just the page shown. Market cap groups are the site's own Large, Mid and Small bands; companies without a band are shown as Not classified. Informational only, not a recommendation.</p>
    </section>
  );
}
