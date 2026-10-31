import { useEffect, useId, useMemo, useState } from "react";
import { HScroll } from "../components/HScroll";
import { RoeLines } from "../charts/RoeLines";
import { Waterfall } from "../charts/Waterfall";
import { Icon } from "../lib/icons";
import type { Table } from "../lib/api";
import { DUPONT_LIMITS as LIM } from "../lib/dupontRules";
import {
  anomalies, averages, completeness, decodeCsv, deepYears, driver, evaluateInsights, explain, gapList, insightContext, move, qualityScore, requiredMargin, simRoe, simStart, tableRows, thresholdNotes, waterfall,
  type Basis, type TableRow, type View, type Why,
} from "../lib/dupontDeep";
import { MINUS, nf } from "../lib/format";
import { saveFile } from "./derive";

const sg = (v: number, d: number) => (v < 0 ? MINUS : "") + nf(v, d);
const DIGITS: Record<string, number> = { margin: 2, turnover: 2, multiplier: 2, roa: 1, roe: 1, normRoe: 1, oneOff: 0 };
const GOAL_DEFAULT = 25, NONE: string[] = [];

/** A blank cell: a dash, the short reason beside it, and the full reason on hover or keyboard focus (read out below the table and by screen readers). */
function Blank({ why, onHint }: { why: Why | null; onHint: (t: string | null) => void }) {
  if (!why) return <span className="dp-na">–</span>;
  return (
    <span className="dp-na" tabIndex={0} role="note" title={why.long} aria-label={`Not available: ${why.long}`} onMouseEnter={() => onHint(why.long)} onFocus={() => onHint(why.long)} onMouseLeave={() => onHint(null)} onBlur={() => onHint(null)}>
      –<small>{why.short}</small>
    </span>
  );
}

/** The Decoding ROE sub-section inside the DuPont block: normalized ROE, ROA, data gaps, anomaly checks, rule-based insight cards, the five-factor waterfall and a what-if calculator.
 *  All numbers come from lib/dupontDeep.ts; this component only lays them out. */
export function DecodeRoe({ symbol, pl, bs, lender, said = NONE }: { symbol: string; pl: Table | undefined; bs: Table | undefined; lender: boolean; said?: string[] }) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const [view, setView] = useState<View>("reported");
  const [basis, setBasis] = useState<Basis>("year-end");
  const [hint, setHint] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState<string | null>(null);
  const [goal, setGoal] = useState(String(GOAL_DEFAULT));
  const [canLink, setCanLink] = useState(false);
  useEffect(() => { setCanLink(!!document.getElementById("financials")); }, []);

  const years = useMemo(() => deepYears(pl, bs, lender, basis), [pl, bs, lender, basis]);
  const rows = useMemo(() => tableRows(years, view, lender), [years, view, lender]);
  const comp = useMemo(() => completeness(years), [years]);
  const gaps = useMemo(() => gapList(years), [years]);
  const flags = useMemo(() => anomalies(years), [years]);
  const mv = useMemo(() => move(years), [years]);
  const drv = useMemo(() => driver(mv), [mv]);
  const score = useMemo(() => qualityScore(years, lender), [years, lender]);
  const ins = useMemo(() => evaluateInsights(insightContext(years), lender, { skip: said }), [years, lender, said]);
  const avgs = useMemo(() => LIM.averageWindows.map((n) => averages(years, n)), [years]);
  const wf = useMemo(() => waterfall(years, lender), [years, lender]);
  const start = useMemo(() => simStart(years), [years]);

  // what-if state starts at the latest year's values, and restarts when the year (or the balance basis) behind them changes
  const [sim, setSim] = useState<{ key: string; m: number; t: number; e: number } | null>(null);
  const simKey = start ? `${start.year.period}|${basis}` : "";
  const cur = start && sim?.key === simKey ? sim : start ? { key: simKey, m: start.margin, t: start.turnover, e: start.multiplier } : null;
  const chosen = years.find((y) => y.period === pick) ?? start?.year ?? years[years.length - 1];

  if (!years.length) return null;
  const fmtCell = (row: TableRow, v: number | string | null, i: number) => {
    const y = years[i];
    if (v == null) return <Blank why={row.whys[i]} onHint={setHint} />;
    if (row.key === "oneOff" && y.oneOffShare != null && y.oneOffShare > LIM.implausibleOneOffShare)
      return <span className="dp-na dp-caution" tabIndex={0} role="note" title="Implausible ratio: likely a tiny pre-tax profit or a data issue." aria-label={`Implausible ratio of ${nf(y.oneOffShare * 100, 0)} per cent of pre-tax profit: likely a tiny pre-tax profit or a data issue`} onMouseEnter={() => setHint("Implausible ratio: likely a tiny pre-tax profit or a data issue.")} onFocus={() => setHint("Implausible ratio: likely a tiny pre-tax profit or a data issue.")} onMouseLeave={() => setHint(null)} onBlur={() => setHint(null)}>⚠ implausible<small>{nf(y.oneOffShare * 100, 0)}%</small></span>;
    if (typeof v === "string") return <span className={v === "Low quality" ? "dp-lq" : ""}>{v === "Low quality" ? "⚑ " : ""}{v}</span>;
    return <>{sg(v, DIGITS[row.key] ?? 1)}{row.kind === "x" ? "×" : "%"}</>;
  };
  const labels = years.map((y) => y.label);
  const roeSeries = [
    { key: "rep", label: "ROE, reported", values: years.map((y) => y.roe), color: "var(--c1)", marker: "circle" as const, dotted: view === "normalized" },
    { key: "norm", label: "ROE, normalized", values: years.map((y) => y.normRoe), color: "var(--c2)", marker: "square" as const, dotted: view === "reported" },
  ];
  const rowOrder = view === "reported" ? roeSeries : [roeSeries[1], roeSeries[0]];   // the chosen view draws solid on top
  const goNum = Number(goal), goalOk = goal.trim() !== "" && Number.isFinite(goNum) && goNum > 0;
  const need = goalOk && cur ? requiredMargin(goNum, cur.t, cur.e) : null;
  const goStatements = (e: React.MouseEvent) => { const el = document.getElementById("financials"); if (el) { e.preventDefault(); el.scrollIntoView({ behavior: "smooth", block: "start" }); } };
  const lines = chosen ? explain(chosen, basis, lender) : [];
  const csv = () => saveFile(`FinLit-${symbol || "stock"}-decoding-roe.csv`, "﻿" + decodeCsv({ symbol, years, view, basis, lender, day: new Date().toISOString().slice(0, 10) }), "text/csv;charset=utf-8");
  const driverWhy = !mv ? "Needs two years with margin, turnover and multiplier." : "Return on equity barely moved, or a loss year makes the log shares undefined.";

  return (
    <section className="dp-deep" id="decoding-roe" aria-labelledby={uid + "-h"}>
      <div className="dp-head"><h4 id={uid + "-h"}><span className="ci"><Icon name="layers" /></span>Decoding ROE</h4><p className="faint">Return on equity can look high or low for reasons that have little to do with how well the business runs. Here it is cleaned of one-off items, split into its causes and checked for gaps and odd jumps.</p></div>

      <div className="dp-bar">
        <div className="seg" role="group" aria-label="Show reported or normalized figures">{(["reported", "normalized"] as View[]).map((v) => <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>{v === "reported" ? "Reported" : "Normalized"}</button>)}</div>
        <div className="seg" role="group" aria-label="Balance sheet figures used">{(["year-end", "average"] as Basis[]).map((b) => <button key={b} type="button" aria-pressed={basis === b} onClick={() => setBasis(b)}>{b === "year-end" ? "Year-end balances" : "Average balances"}</button>)}</div>
        <span className="chip ghost dp-comp" title={comp.missing.length ? `Incomplete: ${comp.missing.join(", ")}` : "Every year has margin, turnover, multiplier and ROE"}>{comp.complete} of {comp.total} years complete</span>
        <button type="button" className="alx-link dp-csv" onClick={csv}><Icon name="download" />Download table (CSV)</button>
      </div>
      {basis === "average" && <p className="faint dp-note">Average balances use the mean of this year's and the previous year's closing total assets and equity. The first year, or a year after a missing balance sheet, falls back to its year-end figure (marked †). The DuPont card above always uses year-end balances.</p>}

      <div className="dp-sum">
        <div className="dp-stat">
          <span className="k">ROE driven by</span>
          {drv ? <b className="dp-badge">{drv.name}</b> : <b className="dp-badge off">Not clear</b>}
          <small>{drv && mv ? `${nf(Math.abs(drv.share), 0)}% of the ROE move from ${mv.first.label} to ${mv.last.label}, the largest of the three (log method)` : driverWhy}</small>
        </div>
        <div className="dp-stat">
          <span className="k">ROE quality score</span>
          <b className="dp-badge">{score.total == null ? "Not scored" : `${score.total} / 100`}</b>
          <small>{score.total == null ? score.reason : "A description of how clean and steady the ROE is, not a rating of the company."}</small>
          <ul className="dp-parts" aria-label="How the score was made">{score.parts.map((p) => <li key={p.key} title={p.how}><span>{p.label}</span><b>{p.points == null ? "–" : `${nf(p.points, 1)} of ${p.max}`}</b><small>{p.detail}</small></li>)}</ul>
          {score.scaled && score.total != null && <small>Scored on the two parts that apply and scaled to 100.</small>}
        </div>
      </div>

      <div className="card dp-card">
        <div className="card-h"><h3><span className="ci"><Icon name="growth" /></span>ROE by year, reported and normalized</h3><span className="s">{view === "reported" ? "Dotted line: normalized" : "Dotted line: reported"} · ⚑ ring marks low-quality earnings</span></div>
        <RoeLines labels={labels} series={rowOrder} flags={years.map((y) => y.lowQuality)} notes={years.map((y) => y.why.roe?.short ?? null)} fmt={(v) => `${sg(v, 1)}%`} ariaLabel={`Return on equity by year, reported and normalized. ${years.map((y) => `${y.label}: reported ${y.roe == null ? "not available" : nf(y.roe, 1) + " per cent"}, normalized ${y.normRoe == null ? "not available" : nf(y.normRoe, 1) + " per cent"}`).join("; ")}`} />
        <ul className="dp-legend" aria-hidden="true"><li><i className="ln" style={{ background: "var(--c1)" }} />ROE, reported (circle)</li><li><i className="ln dot" style={{ color: "var(--c2)" }} />ROE, normalized (square)</li></ul>
        <p className="faint dp-note">Normalized ROE removes exceptional items (after tax at the year's own tax rate) and profit from discontinued operations: normalized profit = net profit − exceptional items × (1 − tax rate) − discontinued profit.{years.some((y) => y.taxRateFallback && (y.exceptional ?? 0) !== 0) ? ` Where tax and pre-tax profit could not give a rate (${years.filter((y) => y.taxRateFallback && (y.exceptional ?? 0) !== 0).map((y) => y.label).join(", ")}), a ${nf(LIM.fallbackTaxRate * 100, 0)}% rate was assumed.` : ""}</p>
      </div>

      <div className="card dp-card">
        <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>ROE and ROA by year</h3><span className="s">{basis === "average" ? "Average balances" : "Year-end balances"} · {view} figures</span></div>
        <HScroll className="" label="ROE and ROA table">
          <table className="dp-t">
            <caption className="sr-only">Net margin, asset turnover, equity multiplier, ROA, reported and normalized ROE and one-off share, by year</caption>
            <thead><tr><th scope="col">Measure</th>{years.map((y) => <th scope="col" key={y.period}>{y.label}{y.fellBack ? <sup title="Average balances are not possible for this year, so its year-end figures are used">†</sup> : ""}</th>)}</tr></thead>
            <tbody>{rows.map((row) => (
              <tr key={row.key} className={(row.emphasis ? "tot " : "") + (row.sub ? "sub" : "")}>
                <th scope="row">{row.label}</th>{row.values.map((v, i) => <td key={years[i].period}>{fmtCell(row, v, i)}</td>)}
              </tr>))}</tbody>
          </table>
        </HScroll>
        <p className="dp-hint faint" aria-live="polite">{hint ?? (gaps.length ? "Hover or tab to a dash to read why the figure is missing." : "")}</p>
        {gaps.length > 0 && <ul className="dp-gaps" aria-label="Why some cells are blank">{gaps.map((g) => <li key={g.reason.long}><b>{g.labels.join(", ")}:</b> {g.reason.long}</li>)}</ul>}
        <div className="dp-avgs">
          <HScroll className="" label="average ROE table"><table className="dp-t dp-at">
            <caption>Average ROE over the last years shown (low-quality years left out)</caption>
            <thead><tr><th scope="col">Window</th><th scope="col">Reported</th><th scope="col">Normalized</th><th scope="col">Years used</th><th scope="col">Left out</th></tr></thead>
            <tbody>{avgs.map((a) => (
              <tr key={a.window}><th scope="row">{a.window}-year average</th>
                <td>{a.reported == null ? <span className="dp-na">–<small>no usable year</small></span> : sg(a.reported, 1) + "%"}</td>
                <td>{a.normalized == null ? <span className="dp-na">–<small>no usable year</small></span> : sg(a.normalized, 1) + "%"}</td>
                <td>{a.used.length} of {a.years}</td>
                <td className="left">{a.lowQuality.length || a.noData.length ? <>{a.lowQuality.length > 0 && <>{a.lowQuality.join(", ")} (low-quality earnings)</>}{a.lowQuality.length > 0 && a.noData.length > 0 && "; "}{a.noData.length > 0 && <>{a.noData.join(", ")} (no meaningful ROE)</>}</> : "none"}</td></tr>))}</tbody>
          </table></HScroll>
          <p className="faint dp-note">A year is low-quality earnings when one-off items (exceptional items and discontinued-operations profit) are above {nf(LIM.lowQualityShare * 100, 0)}% of its pre-tax profit. It is shown in the table and chart but not averaged. The average is a simple mean of the yearly ROE.</p>
        </div>
      </div>

      {flags.length > 0 && (
        <div className="card dp-card">
          <div className="card-h"><h3><span className="ci"><Icon name="alert" /></span>Checks on the numbers</h3><span className="s">{flags.length} to look at</span></div>
          <ul className="dp-flags">{flags.map((a, i) => (
            <li className="dp-find" key={a.period + a.kind + i}><Icon name="alert" /><span><b>{a.label}:</b> {a.text}{canLink && <> <a className="alx-link" href="#financials" onClick={goStatements}>See the financial statements</a></>}</span></li>))}</ul>
        </div>
      )}

      <div className="card dp-card">
        <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>What the numbers say</h3><span className="s">Descriptive only · reported figures</span></div>
        {ins.cards.length ? <div className="dp-ins" role="list">{ins.cards.map((c) => (
          <div className="dp-insc" role="listitem" key={c.id}><p><b>{c.text}</b></p><ul>{c.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul></div>))}</div>
          : <p className="faint">{mv ? "None of the observation rules applies to this range." : "Needs at least two years with margin, turnover, multiplier and a meaningful ROE."}</p>}
        {ins.fired > ins.cards.length && <p className="faint dp-note">Showing the {ins.cards.length} most important of {ins.fired} observations.</p>}
      </div>

      <div className="card dp-card">
        <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>Extended DuPont: tax, interest or operations?</h3><span className="s">{wf.ok ? `${wf.from} to ${wf.to} · reported figures` : "Five factors"}</span></div>
        {wf.ok ? (<>
          <p className="dp-eq"><b>ROE</b> = <span>Tax burden</span> × <span>Interest burden</span> × <span>EBIT margin</span> × <span>Asset turnover</span> × <span>Equity multiplier</span></p>
          <Waterfall ariaLabel={`ROE bridge from ${wf.from} to ${wf.to}: ${nf(wf.start, 1)} per cent to ${nf(wf.end, 1)} per cent. ${wf.steps.map((s) => `${s.label} ${s.pp >= 0 ? "adds" : "takes away"} ${nf(Math.abs(s.pp), 1)} percentage points`).join(", ")}`}
            bars={[{ key: "s", label: [wf.from.replace("Mar ", "Mar "), "ROE"], value: wf.start, kind: "total" },
              ...wf.steps.map((s) => ({ key: s.key, label: SHORT[s.key][0], narrow: SHORT[s.key][1], value: s.pp, kind: "delta" as const })),
              { key: "e", label: [wf.to, "ROE"], value: wf.end, kind: "total" }]} />
          <HScroll className="" label="ROE bridge table">
            <table className="dp-t">
              <caption className="sr-only">Contribution of each factor to the change in ROE from {wf.from} to {wf.to}</caption>
              <thead><tr><th scope="col">Factor</th><th scope="col">{wf.from}</th><th scope="col">{wf.to}</th><th scope="col">Adds to ROE</th></tr></thead>
              <tbody>{wf.steps.map((s) => <tr key={s.key}><th scope="row">{s.label}</th><td>{s.key === "ebitMargin" ? nf(s.first * 100, 2) + "%" : nf(s.first, 2) + (s.key === "turnover" || s.key === "multiplier" ? "×" : "")}</td><td>{s.key === "ebitMargin" ? nf(s.last * 100, 2) + "%" : nf(s.last, 2) + (s.key === "turnover" || s.key === "multiplier" ? "×" : "")}</td><td className={"ch " + (s.pp > 0 ? "up" : s.pp < 0 ? "down" : "")}>{s.pp > 0 ? "▲ +" : s.pp < 0 ? "▼ " + MINUS : ""}{nf(Math.abs(s.pp), 1)} pp</td></tr>)}
                <tr className="tot"><th scope="row">Change in ROE</th><td>{sg(wf.start, 1)}%</td><td>{sg(wf.end, 1)}%</td><td>{wf.end - wf.start > 0 ? "+" : wf.end - wf.start < 0 ? MINUS : ""}{nf(Math.abs(wf.end - wf.start), 1)} pp</td></tr></tbody>
            </table>
          </HScroll>
          <p className="faint dp-note">{wf.note} Pre-tax profit includes exceptional items. Contributions are rounded to one decimal, so they can differ from the total by 0.1.</p>
        </>) : <p className="faint">{wf.reason}</p>}
      </div>

      <div className="card dp-card">
        <div className="card-h"><h3><span className="ci"><Icon name="gauge" /></span>What-if calculator</h3><span className="s">{start ? `Starts at ${start.year.label} · ${basis === "average" ? "average" : "year-end"} balances` : "Needs a year with all three factors"}</span></div>
        {cur && start ? (<>
          <div className="dp-sliders">
            <Slider id={uid + "-m"} label="Net margin" value={cur.m} min={0} max={Math.ceil(Math.max(40, cur.m * 2, start.margin * 1.5))} step={0.1} fmt={(v) => `${nf(v, 1)}%`} onChange={(v) => setSim({ ...cur, m: v })} />
            <Slider id={uid + "-t"} label="Asset turnover" value={cur.t} min={0} max={Math.ceil(Math.max(3, start.turnover * 2.5) * 2) / 2} step={0.01} fmt={(v) => `${nf(v, 2)}×`} onChange={(v) => setSim({ ...cur, t: v })} />
            <Slider id={uid + "-e"} label="Equity multiplier" value={cur.e} min={1} max={Math.ceil(Math.max(6, start.multiplier * 1.6))} step={0.01} fmt={(v) => `${nf(v, 2)}×`} onChange={(v) => setSim({ ...cur, e: v })} />
          </div>
          <p className="dp-simout" aria-live="polite" role="status"><b>{nf(simRoe(cur.m, cur.t, cur.e), 1)}%</b> ROE = {nf(cur.m, 2)}% × {nf(cur.t, 2)} × {nf(cur.e, 2)}
            {start.year.roe != null && <small> ({(() => { const d = simRoe(cur.m, cur.t, cur.e) - (start.year.roe as number); return Math.abs(d) < 0.05 ? "same as" : `${d > 0 ? "▲ +" : "▼ " + MINUS}${nf(Math.abs(d), 1)} pp against`; })()} {nf(start.year.roe, 1)}% in {start.year.label})</small>}</p>
          <button type="button" className="alx-link" onClick={() => setSim(null)}>Reset to {start.year.label}</button>
          {start.year.lowQuality && <p className="faint dp-note">{start.year.label} includes one-off items above {nf(LIM.lowQualityShare * 100, 0)}% of pre-tax profit, so its margin is not a usual level.</p>}
          <div className="dp-need">
            <label htmlFor={uid + "-g"}>What net margin would give an ROE of <input id={uid + "-g"} className="dp-goal" type="number" inputMode="decimal" min={0} step={1} value={goal} onChange={(e) => setGoal(e.target.value)} aria-describedby={uid + "-need"} />% at the current asset turnover and leverage?</label>
            <p id={uid + "-need"} aria-live="polite" role="status" className="dp-simout">{!goalOk ? "Enter a positive ROE." : need == null ? "Not defined: asset turnover × equity multiplier must be above zero." : <><b>{nf(need, 1)}%</b> net margin = {nf(goNum, 1)}% ÷ ({nf(cur.t, 2)} × {nf(cur.e, 2)}){(() => { const d = need - cur.m; return <small> ({Math.abs(d) < 0.05 ? "the same as" : `${d > 0 ? "▲ " : "▼ "}${nf(Math.abs(d), 1)} pp ${d > 0 ? "above" : "below"}`} the {nf(cur.m, 1)}% now set)</small>; })()}</>}</p>
          </div>
          <p className="faint dp-note">required margin = ROE ÷ (asset turnover × equity multiplier). This is arithmetic on the ratios set above, not a forecast of what the company will earn.</p>
        </>) : <p className="faint">No year has margin, asset turnover and equity multiplier together, so there is nothing to start from.</p>}
      </div>

      <div className="card dp-card">
        <button type="button" className="dp-how" aria-expanded={open} aria-controls={uid + "-how"} onClick={() => setOpen(!open)}><Icon name="info" />How is this calculated?<span aria-hidden="true">{open ? "−" : "+"}</span></button>
        {open && (
          <div id={uid + "-how"} className="dp-howbody">
            <label className="dp-pick">Year <select value={chosen.period} onChange={(e) => setPick(e.target.value)}>{years.map((y) => <option key={y.period} value={y.period}>{y.label}</option>)}</select></label>
            <HScroll className="" label="calculation steps">
              <table className="dp-t dp-how-t">
                <caption className="sr-only">Formulas for {chosen.label} with the actual numbers, in ₹ crore</caption>
                <thead><tr><th scope="col">Step</th><th scope="col">Formula</th><th scope="col">With the numbers (₹ crore)</th><th scope="col">Result</th></tr></thead>
                <tbody>{lines.map((l) => <tr key={l.label}><th scope="row">{l.label}</th><td>{l.formula}</td><td>{l.working}</td><td>{l.result}</td></tr>)}</tbody>
              </table>
            </HScroll>
            <ul className="dp-notes faint">
              <li>Year-end balances use the closing balance sheet, which is what the DuPont card above uses. When equity or assets change sharply in a year, year-end figures can overstate or understate the return; the average option uses the mean of the opening and closing balance.</li>
              <li>Each factor's share of an ROE move uses logs: ln(ROE last ÷ ROE first) = ln(margin ratio) + ln(turnover ratio) + ln(multiplier ratio), so the shares add up to 100%. A log is undefined for zero or negative values, so those years show no share.</li>
              {thresholdNotes().map((t) => <li key={t}>{t}</li>)}
              <li>Observation sentences come from a rule list with thresholds that can be tuned; each card shows the numbers behind its sentence.</li>
            </ul>
          </div>)}
      </div>
      <p className="faint dp-note">Worked out from the company's own statements. Net profit is the part that belongs to the company's shareholders. Information only, not investment advice.</p>
    </section>
  );
}

const SHORT: Record<string, [[string, string], [string, string]]> = { taxBurden: [["Tax", "burden"], ["Tax", "burden"]], interestBurden: [["Interest", "burden"], ["Interest", "burden"]], ebitMargin: [["EBIT", "margin"], ["EBIT", "margin"]], turnover: [["Asset", "turnover"], ["Asset", "turn."]], multiplier: [["Equity", "multiplier"], ["Equity", "mult."]] };

/** A keyboard slider (arrow keys, Home, End are native) with its value printed beside it. */
function Slider({ id, label, value, min, max, step, fmt, onChange }: { id: string; label: string; value: number; min: number; max: number; step: number; fmt: (v: number) => string; onChange: (v: number) => void }) {
  return (
    <div className="dp-sl"><label htmlFor={id}>{label}</label><output htmlFor={id} aria-live="off">{fmt(value)}</output>
      <input id={id} type="range" min={min} max={Math.max(max, value)} step={step} value={value} aria-valuetext={fmt(value)} onChange={(e) => onChange(Number(e.target.value))} /></div>
  );
}
