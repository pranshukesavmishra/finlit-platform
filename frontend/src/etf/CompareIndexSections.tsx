// The six sections of the ETF vs index fund dashboard. Each one reads a block of the API answer (finlit/etf_vs_index.py) and shows it with its dates and reasons.
// No section names a winner or tells anyone what to do: the summary says which product was ahead on a measure, and "level" when the gap is inside the stated tolerance.
import { useMemo, type ReactNode } from "react";
import { Link } from "react-router";
import { Info } from "../components/Info";
import { nf } from "../lib/format";
import {
  RANGE_KEYS, RETURN_ROWS, dragSentence, growthOf100, inr, kindLabel, lumpSentence, pc, periodLabel, pp, rtLabel, rtShort, day, sgn,
  type Compare, type PageState, type Product, type RangeKey, type RiskRow,
} from "../lib/etfVsIndex";
import { Icon } from "../lib/icons";
import { Blank, Tone } from "./common";
import { EtfChart } from "./EtfChart";

export const COLORS = ["var(--k1)", "var(--k2)", "var(--k3)", "var(--k7)"];
export const DASHES = [undefined, "7 4", "2 3", "10 3 2 3"];
const note = (g: { key: string; label: string; what: string; read?: string; formula?: string; note?: string }) => <Info g={g} />;

/** A figure, or a dash with the reason it is missing. */
export function Fig({ v, text, why, tone }: { v: number | string | null | undefined; text?: string; why?: string | null; tone?: boolean }) {
  if (v == null) return <Blank why={why || "Not available"} />;
  return tone && typeof v === "number" ? <Tone v={v}>{text ?? String(v)}</Tone> : <>{text ?? String(v)}</>;
}

function ProductHead({ p, i }: { p: Product; i: number }) {
  const to = p.kind === "etf" ? `/etfs/${encodeURIComponent(p.id)}` : `/funds/${p.id}`;
  return (
    <th scope="col" className="num evi-ph">
      <svg width="26" height="8" aria-hidden="true"><line x1="1" x2="25" y1="4" y2="4" stroke={COLORS[i]} strokeWidth="3" strokeDasharray={DASHES[i]} /></svg>
      <Link to={to}>{p.label}</Link>
      <small>{kindLabel(p)}{p.house ? ` · ${p.house}` : ""}</small>
      <small title={p.benchmark ?? undefined}>{p.benchmark ? `Benchmark: ${p.benchmark}` : "Benchmark not stored"} ({rtShort(p.returnType)})</small>
    </th>
  );
}

export function Grid({ d, caption, head = "Measure", children }: { d: Compare; caption: string; head?: string; children: ReactNode }) {
  return (
    <div className="tw etf-tw evi-tw" tabIndex={0} role="region" aria-label={`${caption}. Scroll sideways for more products.`}>
      <table className="etf-table etf-cmp evi-table">
        <caption className="sr-only">{caption}</caption>
        <thead><tr><th scope="col" className="etf-first">{head}</th>{d.products.map((p, i) => <ProductHead key={p.id} p={p} i={i} />)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
const Row = ({ label, children, help }: { label: ReactNode; children: ReactNode; help?: ReactNode }) => (
  <tr><th scope="row" className="etf-first">{label}{help}</th>{children}</tr>
);
const Why = ({ children }: { children: ReactNode }) => <p className="faint evi-fine">{children}</p>;

// ------------------------------------------------------------------------------------------------ 1 performance
export function Performance({ d, page, setRange }: { d: Compare; page: PageState; setRange: (r: RangeKey) => void }) {
  const ids = d.products.map((p) => p.id);
  const growth = useMemo(() => (d.chart ? growthOf100(d.chart, ids, page.range) : null), [d.chart, page.range]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d.returns || !d.rolling) return <p className="evi-empty">{d.common.why}</p>;
  const lines = growth && growth.start
    ? [...d.products.map((p, i) => ({ key: p.id, label: p.label, points: growth.series[p.id] ?? [], color: COLORS[i], dash: DASHES[i] })).filter((l) => l.points.length > 1),
       ...(growth.index && growth.index.length > 1 ? [{ key: "index", label: `${d.index.label} (price index)`, points: growth.index, color: "var(--muted)", dash: "1 4" }] : [])]
    : [];
  const n = d.products.length, r = d.rolling, ref = d.products.find((p) => p.id === r.ref)!;
  return (
    <>
      <div className="etf-ranges-btns evi-ranges" role="group" aria-label="Chart range">{RANGE_KEYS.map((k) => (
        <button key={k} type="button" className={"chip-b" + (k === page.range ? " on" : "")} aria-pressed={k === page.range} onClick={() => setRange(k)}>{k === "MAX" ? "Max" : k}</button>))}</div>
      {growth && growth.start && lines.length >= 2 ? (
        <>
          <EtfChart mode="index" series={lines} caption={`Growth of 100 in ${lines.map((l) => l.label).join(", ")} from ${day(growth.start)}`}
            summary={`Growth of 100 from ${day(growth.start)}. ` + lines.map((l) => `${l.label} ends at ${nf(l.points[l.points.length - 1][1], 1)}.`).join(" ")} />
          <ul className="etf-legend">{lines.map((l) => { const end = l.points[l.points.length - 1][1]; return (
            <li key={l.key}><svg width="34" height="10" aria-hidden="true"><line x1="1" x2="33" y1="5" y2="5" stroke={l.color} strokeWidth="3" strokeDasharray={l.dash} /></svg><b>{l.label}</b><span className="faint">ends at {nf(end, 1)}</span><Tone v={end - 100}>{sgn(end - 100, 1)}</Tone></li>); })}</ul>
          <p className="faint etf-cap">Every line starts at 100 on {day(growth.start)}, the first date shown, and uses the dates all products have a price for. The index line is the price index: it leaves out dividends, which the products reinvest.
            {growth.indexWhy ? ` Index line not shown: ${growth.indexWhy}` : ""}</p>
        </>
      ) : <div className="etf-state small"><p>{growth && growth.start === null ? growth.why : "Not enough history for a chart."}</p></div>}

      <h3 className="evi-h3">Returns{note({ key: "evi-ret", label: "Point-to-point return and CAGR", what: "How much each product gained between a start date and the last date they share. For 3 and 5 years the yearly rate (CAGR) is shown under the total.", formula: "return = last price ÷ price on the start date − 1; CAGR = (1 + return) ^ (1 ÷ years) − 1" })}</h3>
      <Grid d={d} caption="Returns over the same dates for every product" head="Period">
        {RETURN_ROWS.map((k) => (
          <Row key={k} label={k === "since" ? <>Since {day(d.common.from)}</> : periodLabel(k).replace(" (a year)", "")}>
            {d.products.map((p) => { const x = d.returns![p.id][k]; return (
              <td key={p.id} className="num"><Fig v={x.value} text={sgn(x.value)} why={x.why} tone />{x.value != null && x.cagr != null && <small className="etf-cell-sub">{pc(x.cagr)} a year</small>}
                {x.value != null && <small className="etf-cell-sub">{day(x.from)} to {day(x.to)}</small>}</td>); })}
          </Row>))}
      </Grid>
      <Why>All figures use the {nf(d.common.days, 0)} dates on which every product has a price, from {day(d.common.from)} to {day(d.common.to)}. A return needs a price on or within 10 days before its start date.</Why>

      <h3 className="evi-h3">Rolling 1-year returns{note({ key: "evi-roll", label: "Rolling returns", what: "Every day is the end of a one-year window. Looking at all windows shows how much the one-year result depended on the day it was measured.", read: "A wide gap between best and worst means the result changed a lot with timing." })}</h3>
      <Grid d={d} caption="Rolling one-year returns" head="Over all windows">
        <Row label="Windows (days)">{d.products.map((p) => <td key={p.id} className="num">{nf(r.stats[p.id].count, 0)}</td>)}</Row>
        {(["median", "best", "worst"] as const).map((k) => (
          <Row key={k} label={k === "median" ? "Median" : k === "best" ? "Best window" : "Worst window"}>{d.products.map((p) => <td key={p.id} className="num"><Fig v={r.stats[p.id][k]} text={sgn(r.stats[p.id][k])} why={r.stats[p.id].why} tone /></td>)}</Row>))}
        <Row label="Windows with a gain">{d.products.map((p) => <td key={p.id} className="num"><Fig v={r.stats[p.id].positive} text={pc(r.stats[p.id].positive, 1)} why={r.stats[p.id].why} /></td>)}</Row>
      </Grid>
      {n > 1 && (Object.keys(r.headToHead).length ? (
        <ul className="evi-h2h" aria-label={`One-year windows compared with ${ref.label}`}>
          {d.products.filter((p) => r.headToHead[p.id]).map((p) => { const h = r.headToHead[p.id]; return (
            <li key={p.id}><b>{p.label}</b> against <b>{ref.label}</b>, {nf(h.windows, 0)} one-year windows: higher in <b>{pc(h.ahead, 1)}</b>, level (same to two decimals) in {pc(h.level, 1)}, lower in {pc(h.behind, 1)}.</li>); })}
        </ul>
      ) : <Why>Not enough one-year windows to compare the products window by window.</Why>)}

      <h3 className="evi-h3">Monthly SIP: XIRR{note({ key: "evi-xirr", label: "XIRR", what: "The yearly rate that makes the dated instalments and the final value balance. It is the SIP's own return, counting when each rupee went in.", formula: "solve for r: sum of cash flow ÷ (1 + r) ^ (days since the first instalment ÷ 365) = 0" })}</h3>
      <Grid d={d} caption="XIRR of an equal monthly SIP" head={`SIP of ${inr(d.inputs.sip)} a month`}>
        <Row label={<>Instalments from {day(d.startDay)}</>}>{d.products.map((p) => <td key={p.id} className="num">{d.sip?.[p.id]?.installments ?? <Blank why={d.sip?.[p.id]?.why || "Not available"} />}</td>)}</Row>
        <Row label="XIRR (a year)">{d.products.map((p) => { const s = d.sip?.[p.id]; return <td key={p.id} className="num"><Fig v={s?.xirr} text={pc(s?.xirr)} why={s?.xirrWhy || s?.why} tone /></td>; })}</Row>
      </Grid>
      <Why>Change the amount or the start date in the calculator below.</Why>
    </>
  );
}

// ------------------------------------------------------------------------------------------------ 2 cost
export function Cost({ d }: { d: Compare }) {
  const base = d.inputs.dragBase;
  return (
    <>
      <Grid d={d} caption="Costs written in the fund documents">
        <Row label="Expense ratio (a year)" help={note({ key: "evi-ter", label: "Expense ratio (TER)", what: "The yearly fee a fund takes from its assets, already inside the price or NAV. Direct plans have the lower figure.", note: "Brokerage, taxes and the spread of buying an ETF on the exchange are not part of it." })}>
          {d.products.map((p) => { const c = d.costs[p.id]; return <td key={p.id} className="num"><Fig v={c.terPct} text={c.terPct == null ? undefined : nf(c.terPct, 2) + "%"} why={c.ter.why} />{c.ter.asOf && <small className="etf-cell-sub">as of {day(c.ter.asOf)}</small>}{c.ter.source && c.terPct != null && <small className="etf-cell-sub">{c.ter.source}</small>}</td>; })}
        </Row>
        <Row label={<>Expense ratio on {inr(base)}</>}>
          {d.products.map((p) => { const c = d.costs[p.id], s = dragSentence(c, base); return <td key={p.id} className="num"><Fig v={c.dragPerYear} text={c.dragPerYear == null ? undefined : inr(c.dragPerYear) + " a year"} why={c.ter.why} />{s && <small className="etf-cell-sub">{s}</small>}</td>; })}
        </Row>
        <Row label="Exit load">{d.products.map((p) => { const c = d.costs[p.id].exitLoad; return <td key={p.id} className="num evi-txt"><Fig v={c.value} why={c.why} />{c.source && c.value != null && <small className="etf-cell-sub">{c.source}</small>}</td>; })}</Row>
        <Row label="Minimum to start">{d.products.map((p) => { const c = d.costs[p.id].minimum; return <td key={p.id} className="num evi-txt"><Fig v={c.value} why={c.why} /></td>; })}</Row>
        <Row label="Fund size (AUM)">{d.products.map((p) => { const c = d.costs[p.id].aum; return <td key={p.id} className="num evi-txt"><Fig v={c.value} why={c.why} />{c.asOf && c.value != null && <small className="etf-cell-sub">as of {day(c.asOf)}</small>}</td>; })}</Row>
        {d.products.some((p) => p.kind === "etf") && (
          <Row label="Exchange price against NAV" help={note({ key: "evi-prem", label: "Premium and discount to NAV", what: "How far the ETF's closing price on the exchange was from the NAV of the same day." })}>
            {d.products.map((p) => { const e = d.etfExtra[p.id]; return <td key={p.id} className="num">{p.kind === "etf" ? <Fig v={e?.premium} text={pc(e?.premium)} why="No NAV found in AMFI's file for this ETF" tone />
              : <span className="faint">—<span className="sr-only"> (not an ETF)</span></span>}{p.kind === "etf" && e?.navDate && <small className="etf-cell-sub">NAV of {day(e.navDate)}</small>}</td>; })}
          </Row>)}
      </Grid>
      <p className="evi-callout" role="note"><Icon name="info" /><span>Brokerage, the gap between buying and selling prices (bid-ask spread) and impact cost of trading an ETF on the exchange are <b>not included</b>: we do not have these figures and do not estimate them. The line “on {inr(base)}” is only the expense ratio multiplied by {inr(base)}, nothing else.</span></p>
    </>
  );
}

// ------------------------------------------------------------------------------------------------ 3 tracking
export function TrackingBlock({ d }: { d: Compare }) {
  if (!d.tracking) return <p className="evi-empty">{d.common.why}</p>;
  const t = d.tracking, ref = d.products[0];
  return (
    <>
      <p className="evi-callout" role="note"><Icon name="info" /><span>
        {d.index.why ? <>Index levels are not available: <b>{d.index.why}</b> The comparison of the products with each other below does not need them.</>
          : <>The index here is the <b>{d.index.label} price index</b> from our index data provider, without dividends. The total-return index (TRI) is not stored. The products reinvest dividends, so their gap to this index is mostly the index's dividend yield (positive).
            Read the difference below as “against the price index; total-return index not available”. The tracking error is less affected by dividends.</>}</span></p>
      <h3 className="evi-h3">Difference from the index{note({ key: "evi-td", label: "Tracking difference", what: "The product's return minus the index's return over the same dates. A fund that tracked closely has a small difference.", note: "Here the index is the price index, so dividends make the difference positive. Not a measure of fault." })}</h3>
      <Grid d={d} caption="Tracking difference against the price index" head="Return minus index return">
        {(["1Y", "3Y", "5Y"] as const).map((k) => (
          <Row key={k} label={`${k.replace("Y", "")} year${k === "1Y" ? "" : "s"}`}>
            {d.products.map((p) => { const x = t[p.id].td[k]; return (
              <td key={p.id} className="num"><Fig v={x.value} text={pp(x.value)} why={x.why} />
                {x.value != null && x.annual != null && <small className="etf-cell-sub">{pp(x.annual)} a year</small>}
                {x.value != null && <small className="etf-cell-sub">product {pc(x.product)} · index {pc(x.index)}</small>}</td>); })}
          </Row>))}
      </Grid>
      <h3 className="evi-h3">Tracking error{note({ key: "evi-te", label: "Tracking error", what: "How much the product's daily return differed from the index's daily return, as a yearly standard deviation. Smaller means a steadier match.", formula: "standard deviation of (product daily return − index daily return) × √252", note: "Shown only with at least 240 overlapping daily returns (about one year)." })}</h3>
      <Grid d={d} caption="Tracking error against the price index" head="Daily differences">
        <Row label="Tracking error (a year)">{d.products.map((p) => { const x = t[p.id].te; return <td key={p.id} className="num"><Fig v={x.value} text={x.value == null ? undefined : nf(x.value, 2) + "%"} why={x.why} />{x.value != null && <small className="etf-cell-sub">{nf(x.returns, 0)} daily returns, {day(x.from)} to {day(x.to)}</small>}</td>; })}</Row>
      </Grid>
      {d.products.length > 1 && (
        <>
          <h3 className="evi-h3">Return gap between the products</h3>
          <Grid d={d} caption={`Return minus the return of ${ref.label}`} head={`Return minus ${ref.label}`}>
            {(["1Y", "3Y", "5Y"] as const).map((k) => (
              <Row key={k} label={`${k.replace("Y", "")} year${k === "1Y" ? "" : "s"}`}>
                {d.products.map((p) => p.id === ref.id ? <td key={p.id} className="num faint">reference</td> : <td key={p.id} className="num"><Fig v={t[p.id].gap[k]?.value} text={pp(t[p.id].gap[k]?.value)} why={t[p.id].gap[k]?.why} /></td>)}
              </Row>))}
          </Grid>
          <Why>This compares the products with each other (the first one chosen is the reference), so the index's dividends do not enter.</Why>
        </>)}
    </>
  );
}

// ------------------------------------------------------------------------------------------------ 4 risk
const RISK_LABEL: Record<string, string> = { "1Y": "Last 1 year", "3Y": "Last 3 years", "5Y": "Last 5 years", all: "Whole common period" };
export function RiskBlock({ d, page, setRisk }: { d: Compare; page: PageState; setRisk: (k: string) => void }) {
  if (!d.risk) return <p className="evi-empty">{d.common.why}</p>;
  const keys = ["1Y", "3Y", "5Y", "all"];
  const avail = keys.filter((k) => d.risk![k]?.products);
  const cur = page.risk && avail.includes(page.risk) ? page.risk : "all";
  const w = d.risk[cur];
  const rows: { label: ReactNode; cell: (r: RiskRow) => ReactNode }[] = [
    { label: <>Volatility (a year){note({ key: "evi-vol", label: "Volatility", what: "How much the daily returns varied, as a yearly standard deviation. Bigger means a bumpier ride.", formula: "standard deviation of daily returns × √252" })}</>, cell: (r) => <Fig v={r.volatility} text={r.volatility == null ? undefined : nf(r.volatility, 2) + "%"} why={r.volatilityWhy} /> },
    { label: <>Maximum fall{note({ key: "evi-mdd", label: "Maximum drawdown", what: "The largest fall from a high to a later low in this period.", formula: "lowest of (price ÷ highest earlier price − 1)" })}</>, cell: (r) => <><Fig v={r.maxDrawdown.value} text={pc(r.maxDrawdown.value)} />{r.maxDrawdown.peak && <small className="etf-cell-sub">{day(r.maxDrawdown.peak)} to {day(r.maxDrawdown.trough)}</small>}</> },
    { label: <>Downside deviation (a year){note({ key: "evi-dd", label: "Downside deviation", what: "Like volatility, but only the falling days count; gains count as zero.", formula: "√(average of min(daily return, 0)²) × √252" })}</>, cell: (r) => <Fig v={r.downside} text={r.downside == null ? undefined : nf(r.downside, 2) + "%"} why={r.downsideWhy} /> },
    { label: "Worst 1-year rolling return", cell: (r) => <><Fig v={r.worstRolling?.value} text={pc(r.worstRolling?.value)} why={r.worstRollingWhy} />{r.worstRolling && <small className="etf-cell-sub">year ending {day(r.worstRolling.end)}</small>}</> },
    { label: "Best day", cell: (r) => <><Fig v={r.best?.value} text={sgn(r.best?.value)} />{r.best && <small className="etf-cell-sub">{day(r.best.date)}</small>}</> },
    { label: "Worst day", cell: (r) => <><Fig v={r.worst?.value} text={sgn(r.worst?.value)} />{r.worst && <small className="etf-cell-sub">{day(r.worst.date)}</small>}</> },
  ];
  return (
    <>
      <div className="etf-ranges-btns evi-ranges" role="group" aria-label="Period for the risk figures">{keys.map((k) => (
        <button key={k} type="button" className={"chip-b" + (k === cur ? " on" : "")} aria-pressed={k === cur} disabled={!avail.includes(k)} title={avail.includes(k) ? undefined : d.risk![k]?.why} onClick={() => setRisk(k)}>{RISK_LABEL[k]}</button>))}</div>
      {!avail.includes("5Y") && d.risk["5Y"]?.why && <Why>5 years not shown: {d.risk["5Y"].why}</Why>}
      <Grid d={d} caption={`Risk figures, ${RISK_LABEL[cur].toLowerCase()}`} head={RISK_LABEL[cur]}>
        {rows.map((r, i) => <Row key={i} label={r.label}>{d.products.map((p) => <td key={p.id} className="num">{w?.products?.[p.id] ? r.cell(w.products[p.id]) : <Blank why={w?.why || "Not available"} />}</td>)}</Row>)}
      </Grid>
      <Why>{w?.from ? `Daily returns from ${day(w.from)} to ${day(w.to)}. ` : ""}Volatility and downside deviation use 252 trading days a year.</Why>
    </>
  );
}

// ------------------------------------------------------------------------------------------------ 5 calculator
export function Calculator({ d, draft, setDraft, apply, dirty }: { d: Compare; draft: { sip: string; lump: string; start: string }; setDraft: (x: { sip: string; lump: string; start: string }) => void; apply: () => void; dirty: boolean }) {
  const ref = d.products[0];
  return (
    <>
      <form className="evi-calc" onSubmit={(e) => { e.preventDefault(); apply(); }}>
        <label>Lump sum (₹)<input inputMode="numeric" value={draft.lump} onChange={(e) => setDraft({ ...draft, lump: e.target.value })} aria-describedby="evi-calc-h" /></label>
        <label>Monthly SIP (₹)<input inputMode="numeric" value={draft.sip} onChange={(e) => setDraft({ ...draft, sip: e.target.value })} aria-describedby="evi-calc-h" /></label>
        <label>Start date<input type="date" value={draft.start} min="2000-01-01" onChange={(e) => setDraft({ ...draft, start: e.target.value })} aria-describedby="evi-calc-h" /></label>
        <button className="btn" type="submit" disabled={!dirty}>Recalculate</button>
      </form>
      <p id="evi-calc-h" className="faint evi-fine">Uses the actual prices and NAVs of the dates all products share ({day(d.common.from)} to {day(d.common.to)}). Expense ratios are already inside them; no other assumption is added. Start date empty: five years before the last date, or the first shared date if the history is shorter. Used start: <b>{day(d.startDay)}</b>.</p>
      {!d.lump ? <p className="evi-empty">{d.common.why}</p> : (
        <>
          <h3 className="evi-h3">Lump sum of {inr(d.inputs.lump)}</h3>
          <Grid d={d} caption="Final value of a lump sum" head="Lump sum">
            <Row label="Value on the last date">{d.products.map((p) => <td key={p.id} className="num"><Fig v={d.lump![p.id].value} text={inr(d.lump![p.id].value, 0)} why={d.lump![p.id].why} />{d.lump![p.id].gainPct != null && <small className="etf-cell-sub"><Tone v={d.lump![p.id].gainPct}>{sgn(d.lump![p.id].gainPct)}</Tone> · {d.lump![p.id].cagr != null ? `${pc(d.lump![p.id].cagr)} a year` : "under a year"}</small>}</td>)}</Row>
            <Row label={`Difference from ${ref.label}`}>{d.products.map((p) => { const x = d.lump![p.id].diffVsRef; return <td key={p.id} className="num">{p.id === ref.id ? <span className="faint">reference</span> : x ? <><Tone v={x.rupees}>{x.rupees > 0 ? "+" : x.rupees < 0 ? "−" : ""}{inr(Math.abs(x.rupees), 0)}</Tone><small className="etf-cell-sub">{sgn(x.pct)}</small></> : <Blank why={d.lump![p.id].why || "Not available"} />}</td>; })}</Row>
            <Row label="The arithmetic">{d.products.map((p) => <td key={p.id} className="num evi-txt"><small className="evi-arith">{lumpSentence(d.inputs.lump, d.lump![p.id]) ?? <Blank why={d.lump![p.id].why || "Not available"} />}</small></td>)}</Row>
          </Grid>
          <h3 className="evi-h3">Monthly SIP of {inr(d.inputs.sip)}</h3>
          <Grid d={d} caption="Final value of a monthly SIP" head="Monthly SIP">
            <Row label="Instalments">{d.products.map((p) => { const s = d.sip![p.id]; return <td key={p.id} className="num">{s.installments != null ? <>{s.installments}<small className="etf-cell-sub">{day(s.first)} to {day(s.last)}</small></> : <Blank why={s.why || "Not available"} />}</td>; })}</Row>
            <Row label="Money put in">{d.products.map((p) => <td key={p.id} className="num"><Fig v={d.sip![p.id].invested} text={inr(d.sip![p.id].invested, 0)} why={d.sip![p.id].why} /></td>)}</Row>
            <Row label="Value on the last date">{d.products.map((p) => { const s = d.sip![p.id]; return <td key={p.id} className="num"><Fig v={s.value} text={inr(s.value, 0)} why={s.why} />{s.gainPct != null && <small className="etf-cell-sub"><Tone v={s.gainPct}>{sgn(s.gainPct)}</Tone> on money put in</small>}</td>; })}</Row>
            <Row label={`Difference from ${ref.label}`}>{d.products.map((p) => { const x = d.sip![p.id].diffVsRef; return <td key={p.id} className="num">{p.id === ref.id ? <span className="faint">reference</span> : x ? <><Tone v={x.rupees}>{x.rupees > 0 ? "+" : x.rupees < 0 ? "−" : ""}{inr(Math.abs(x.rupees), 0)}</Tone><small className="etf-cell-sub">{sgn(x.pct)}</small></> : <Blank why={d.sip![p.id].why || "Not available"} />}</td>; })}</Row>
            <Row label="XIRR (a year)">{d.products.map((p) => <td key={p.id} className="num"><Fig v={d.sip![p.id].xirr} text={pc(d.sip![p.id].xirr)} why={d.sip![p.id].xirrWhy || d.sip![p.id].why} tone /></td>)}</Row>
            <Row label="The arithmetic">{d.products.map((p) => { const s = d.sip![p.id]; return <td key={p.id} className="num evi-txt"><small className="evi-arith">{s.units != null || s.value != null ? `Each instalment buys ${inr(d.inputs.sip)} ÷ that day's price in units; ${s.installments} instalments add up to ${s.units != null ? nf(s.units, 4) : "—"} units × ${inr(s.endPrice, 4)} (${day(s.endDate)}) = ${inr(s.value, 2)}` : <Blank why={s.why || "Not available"} />}</small></td>; })}</Row>
          </Grid>
        </>)}
      <Why>A past calculation is not a forecast. Instalments are bought on the same day of each month, or the next day all products have a price.</Why>
    </>
  );
}

// ------------------------------------------------------------------------------------------------ 6 summary
export function Summary({ d }: { d: Compare }) {
  const s = d.summary;
  if (!s) return <p className="evi-empty">{d.common.why || "No summary: there is not enough common history."}</p>;
  const names = Object.fromEntries(d.products.map((p, i) => [p.id, { label: p.label, i }]));
  const cats = ["Returns", "Cost", "Tracking", "Risk"];
  const unitText = (r: (typeof s.rows)[number], v: number | null) => (v == null ? "—" : r.unit.startsWith("%") ? nf(v, 2) + "%" : nf(v, 2));
  return (
    <>
      <p className="evi-sum" aria-label="Summary sentence">{s.sentence}</p>
      <div className="tw etf-tw evi-tw" tabIndex={0} role="region" aria-label="Which product was ahead on each measure. Scroll sideways if needed.">
        <table className="etf-table evi-table evi-sumtable">
          <caption className="sr-only">Which product was ahead on each measure</caption>
          <thead><tr><th scope="col">Category</th><th scope="col">Measure</th><th scope="col">Ahead</th><th scope="col">Values</th></tr></thead>
          <tbody>{cats.flatMap((c) => s.rows.filter((r) => r.category === c).map((r, k) => (
            <tr key={r.measure}>
              {k === 0 && <th scope="rowgroup" rowSpan={s.rows.filter((x) => x.category === c).length}>{c}</th>}
              <td>{r.measure}{r.windowLabel ? <small className="etf-cell-sub">{r.windowLabel === "all" ? "whole common period" : r.windowLabel}</small> : null}</td>
              <td>{r.level ? <span className="evi-tag level">Level (within {nf(r.tol, 2)} pts)</span> : r.leaders.length ? r.leaders.map((id) => <span key={id} className="evi-tag"><svg width="14" height="6" aria-hidden="true"><line x1="0" x2="14" y1="3" y2="3" stroke={COLORS[names[id].i]} strokeWidth="3" strokeDasharray={DASHES[names[id].i]} /></svg>{names[id].label}</span>) : <Blank why="Fewer than two products have this figure" />}</td>
              <td className="evi-vals">{d.products.map((p) => <span key={p.id}>{p.label}: <b>{unitText(r, r.values[p.id])}</b></span>)}<small className="etf-cell-sub">{r.unit}</small></td>
            </tr>)))}</tbody>
        </table>
      </div>
      <Why>“Level” means the gap is smaller than the tolerance: {nf(s.tolerances.return, 2)} points a year for returns, {nf(s.tolerances.cost, 2)} for the expense ratio, {nf(s.tolerances.tracking, 2)} for tracking error, {nf(s.tolerances.fall, 2)} for the maximum fall, {nf(s.tolerances.volatility, 2)} for volatility. The tracking row uses tracking error only, because the price index leaves out dividends. There is no overall score and no weighting.</Why>
      <p className="evi-callout" role="note"><Icon name="info" /><span><b>Differences of this size can reverse in other periods. Information only, not investment advice.</b> “Ahead” describes the past figures above; it says nothing about which product suits anyone.</span></p>
    </>
  );
}

export { rtLabel };
