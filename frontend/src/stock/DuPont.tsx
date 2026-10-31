import { useMemo, useState } from "react";
import { HScroll } from "../components/HScroll";
import { ChartHelp } from "../components/ChartHelp";
import { Icon } from "../lib/icons";
import { useSection, type Financials } from "../lib/api";
import { dupont, dupontSummary, shareText } from "../lib/dupont";
import { MINUS, nf } from "../lib/format";
import { DecodeRoe } from "./DecodeRoe";
import "../styles/dupont.css";

const fy = (p: string) => (/^FY\d{2}$/.test(p) ? `Mar 20${p.slice(2)}` : p);
const arrow = (v: "up" | "down" | "flat") => (v === "up" ? "▲" : v === "down" ? "▼" : "▬");

const NAME = { netMargin: "Net profit margin", turnover: "Asset turnover", multiplier: "Equity multiplier" } as const;
const WHY: Record<string, string> = { m: "Needs net profit and revenue", t: "Needs revenue and total assets", e: "Needs total assets and positive equity", roe: "Needs net profit and positive equity" };
/** A missing figure: an en dash with the reason on hover, keyboard focus and for screen readers. Nothing is estimated. */
function Dash({ why }: { why: string }) { return <span className="dp-dash" tabIndex={0} role="note" title={why} aria-label={`Not available: ${why}`}>–</span>; }

/** DuPont analysis (what drives return on equity) and the margin story with changes in basis points, from the company's own statements. */
export function DuPont({ symbol, lender }: { symbol: string; lender: boolean }) {
  const f = useSection<Financials>(symbol, "financials", !!symbol);
  const [five, setFive] = useState(false);
  const d = useMemo(() => dupont(f.data?.yearly.pl, f.data?.yearly.bs, lender), [f.data, lender]);
  const years = d.years, flagged = years.filter((y) => y.flag);
  const hasUnderlying = years.some((y) => y.underlyingMargin != null);
  const canFive = !lender && years.some((y) => y.taxBurden != null && y.interestBurden != null && y.ebitMargin != null);
  const now = [...years].reverse().find((y) => y.roe != null) ?? null;
  const summary = dupontSummary(d);
  const cur = (i: number) => (i === years.length - 1 ? "cur" : "");
  return (
    <div className="dp">
      {years.length >= 1 && years.some((y) => y.roe != null) && (
        <div className="card dp-card dp-main" id="dupont">
          <div className="dp-top">
            <div className="dp-title">
              <h3><span className="ci"><Icon name="layers" /></span>DuPont analysis<ChartHelp id="dupont" /></h3>
              <p className="faint">ROE is broken into three components: <b>Net profit margin × Asset turnover × Equity multiplier</b></p>
            </div>
            <aside className="dp-info" aria-label="What drives ROE"><Icon name="info" /><div><b>What drives the return on equity (ROE)?</b><span>ROE shows how efficiently a company turns equity into profits.</span></div></aside>
          </div>
          {now && (
            <div className="dp-strip" role="group" aria-label={`ROE equals ${lender ? "net profit over total income" : "net profit over revenue"} times asset turnover times equity multiplier, ${fy(now.period)}`}>
              {[
                { k: "roe", icon: "gauge", t: "ROE", s: "Return on equity", v: now.roe, f: (v: number) => nf(v, 1) + "%" },
                { k: "m", icon: "percent", t: "Net profit margin", s: lender ? "Net profit / Total income" : "Net profit / Revenue", v: now.netMargin, f: (v: number) => nf(v, 2) + "%" },
                { k: "t", icon: "refresh", t: "Asset turnover", s: lender ? "Total income / Total assets" : "Revenue / Total assets", v: now.turnover, f: (v: number) => nf(v, 2) + "×" },
                { k: "e", icon: "balance", t: "Equity multiplier", s: "Total assets / Total equity", v: now.multiplier, f: (v: number) => nf(v, 2) + "×" },
              ].flatMap((c, i) => [
                i > 0 && <span className="dp-op" aria-hidden="true" key={"o" + i}>{i === 1 ? "=" : "×"}</span>,
                <div className={"dp-sc" + (c.k === "roe" ? " roe" : "")} key={c.k}>
                  <span className="dp-sci"><Icon name={c.icon as never} /></span>
                  <span className="t">{c.t}</span><small>{c.s}</small>
                  <b>{c.v == null ? <Dash why={WHY[c.k]} /> : c.f(c.v)}</b><small>({fy(now.period)})</small>
                </div>,
              ])}
            </div>
          )}
          <HScroll className="dp-scroll" label="DuPont analysis">
            <table className="dp-t dp-main-t"><caption className="sr-only">DuPont components by year; the latest year is highlighted</caption>
              <thead><tr><th scope="col">Component</th>{years.map((y, i) => <th scope="col" key={y.period} className={i === years.length - 1 ? "cur" : ""}>{fy(y.period)}</th>)}</tr></thead>
              <tbody>
                <tr><th scope="row">Net profit margin<small>{lender ? "Net profit / Total income" : "Net profit / Revenue"}</small></th>{years.map((y, i) => <td key={y.period} className={cur(i)}>{y.netMargin == null ? <Dash why={WHY.m} /> : nf(y.netMargin, 2) + "%"}{y.flag && <sup className="dp-flag" title={y.flag}>⚑</sup>}</td>)}</tr>
                {hasUnderlying && <tr className="sub"><th scope="row">… without discontinued operations</th>{years.map((y, i) => <td key={y.period} className={cur(i)}>{y.underlyingMargin == null ? MINUS : nf(y.underlyingMargin, 2) + "%"}</td>)}</tr>}
                {five && canFive && <>
                  <tr className="sub"><th scope="row">… tax burden (profit after tax / before tax)</th>{years.map((y, i) => <td key={y.period} className={cur(i)}>{y.taxBurden == null ? MINUS : nf(y.taxBurden, 2)}</td>)}</tr>
                  <tr className="sub"><th scope="row">… interest burden (pre-tax profit / EBIT)</th>{years.map((y, i) => <td key={y.period} className={cur(i)}>{y.interestBurden == null ? MINUS : nf(y.interestBurden, 2)}</td>)}</tr>
                  <tr className="sub"><th scope="row">… EBIT margin</th>{years.map((y, i) => <td key={y.period} className={cur(i)}>{y.ebitMargin == null ? MINUS : nf(y.ebitMargin, 2) + "%"}</td>)}</tr></>}
                <tr><th scope="row">Asset turnover<small>{lender ? "Total income / Total assets" : "Revenue / Total assets"}</small></th>{years.map((y, i) => <td key={y.period} className={cur(i)}>{y.turnover == null ? <Dash why={WHY.t} /> : nf(y.turnover, 2) + "×"}</td>)}</tr>
                <tr><th scope="row">Equity multiplier<small>Total assets / Total equity</small></th>{years.map((y, i) => <td key={y.period} className={cur(i)}>{y.multiplier == null ? <Dash why={WHY.e} /> : nf(y.multiplier, 2) + "×"}</td>)}</tr>
                <tr className="tot"><th scope="row">Calculated ROE</th>{years.map((y, i) => <td key={y.period} className={cur(i)}>{y.roe == null ? <Dash why={WHY.roe} /> : nf(y.roe, 1) + "%"}</td>)}</tr>
              </tbody></table>
          </HScroll>
          {canFive && <button type="button" className="alx-link dp-more" aria-pressed={five} onClick={() => setFive(!five)}>{five ? "Show the simple three-factor view" : "Split net margin further (tax, interest, operating)"}</button>}
          {d.factors.length > 0 && (
            <div className="dp-tiles" role="list">{d.factors.map((x) => {
              const sh = shareText(x), spark = years.filter((y) => y[x.key] != null).slice(-5), top = Math.max(...spark.map((y) => Math.abs(y[x.key] as number)), 0);
              const dig = x.key === "netMargin" ? 1 : 2, unit = x.key === "netMargin" ? "%" : "×";
              return (
                <div className={"dp-tile " + x.verdict} role="listitem" key={x.key}>
                  <span className="k">{NAME[x.key]}</span><small>{lender && x.key !== "multiplier" ? x.label.replace("revenue", "total income").replace("Revenue", "Total income") : x.label}</small>
                  <b>{nf(x.first ?? 0, dig)}{unit} → {nf(x.last ?? 0, dig)}{unit}</b>
                  <span className={"dp-pill " + x.verdict}>{arrow(x.verdict)} {x.changePct == null ? "" : nf(Math.abs(x.changePct), 1) + "%"}{sh ? ` · ${sh}` : ""}</span>
                  <div className="dp-bars" aria-label={`${NAME[x.key]} by year: ${spark.map((y) => `${fy(y.period)} ${nf(y[x.key] as number, 2)}${unit}`).join(", ")}`} role="img">
                    {spark.map((y, i) => { const v = y[x.key] as number; return (
                      <span className={"dp-bar1" + (i === spark.length - 1 ? " last" : "")} key={y.period}><i style={{ height: top ? `${Math.max(4, (Math.abs(v) / top) * 100)}%` : "4%" }} /><em>{nf(v, dig)}</em><u>{y.period}</u></span>); })}
                  </div>
                </div>);
            })}</div>
          )}
          {summary && <p className="dp-sum1"><span className="dp-bulb"><Icon name="spark" /></span><span>{summary}</span></p>}
          {d.words.slice(2).map((t, i) => <p className="dp-say faint" key={i}>{t}</p>)}
          {flagged.map((y) => <p className="dp-find" key={y.period}><Icon name="alert" /><span><b>Unusual year, {fy(y.period)}:</b> {y.flag}</span></p>)}
          <p className="faint dp-note">Worked out from the company's own statements, using each year-end balance sheet. Net profit is the part that belongs to the company's shareholders. Information only, not investment advice.</p>
          <DecodeRoe symbol={symbol} pl={f.data?.yearly.pl} bs={f.data?.yearly.bs} lender={lender} said={d.words} />
        </div>
      )}
    </div>
  );
}
