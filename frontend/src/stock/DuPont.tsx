import { useMemo, useState } from "react";
import { HScroll } from "../components/HScroll";
import { ChartHelp } from "../components/ChartHelp";
import { Icon } from "../lib/icons";
import { useSection, type Financials } from "../lib/api";
import { dupont, marginTrend } from "../lib/dupont";
import { MINUS, nf } from "../lib/format";
import { DecodeRoe } from "./DecodeRoe";
import "../styles/dupont.css";

const fy = (p: string) => (/^FY\d{2}$/.test(p) ? `Mar 20${p.slice(2)}` : p);
const bps = (v: number | null) => (v == null ? MINUS : `${v > 0 ? "+" : v < 0 ? MINUS : ""}${nf(Math.abs(v), 0)} bps`);
const arrow = (v: "up" | "down" | "flat") => (v === "up" ? "▲" : v === "down" ? "▼" : "▬");

/** DuPont analysis (what drives return on equity) and the margin story with changes in basis points, from the company's own statements. */
export function DuPont({ symbol, periods, rows, lender }: { symbol: string; periods: string[]; rows: Record<string, (number | null)[]>; lender: boolean }) {
  const f = useSection<Financials>(symbol, "financials", !!symbol);
  const [five, setFive] = useState(false);
  const d = useMemo(() => dupont(f.data?.yearly.pl, f.data?.yearly.bs, lender), [f.data, lender]);
  const m = useMemo(() => marginTrend(periods, rows, 4), [periods, rows]);
  const years = d.years, flagged = years.filter((y) => y.flag);
  const hasUnderlying = years.some((y) => y.underlyingMargin != null);
  const canFive = !lender && years.some((y) => y.taxBurden != null && y.interestBurden != null && y.ebitMargin != null);
  return (
    <div className="dp">
      {m.rows.length > 0 && (
        <div className="card dp-card">
          <div className="card-h"><h3><span className="ci"><Icon name="growth" /></span>Margin trend<ChartHelp id="margin-trend" /></h3><span className="s">{fy(m.periods[0])} to {fy(m.periods[m.periods.length - 1])} · change in basis points</span></div>
          <HScroll className="" label="margin trend">
            <table className="dp-t"><thead><tr><th>Metric</th>{m.periods.map((p) => <th key={p}>{p}</th>)}<th>Change</th></tr></thead>
              <tbody>{m.rows.map((r) => <tr key={r.key}><td>{r.label}</td>{r.values.map((v, i) => <td key={i}>{v == null ? MINUS : nf(v, 1) + "%"}</td>)}<td className={"ch " + (r.bps == null || r.bps === 0 ? "" : r.bps > 0 ? "up" : "down")}>{bps(r.bps)}</td></tr>)}</tbody></table>
          </HScroll>
          <p className="faint dp-note">One percentage point is 100 basis points (bps). The change runs from the first to the last year shown.</p>
          {m.findings.map((t, i) => <p className="dp-find" key={i}><Icon name="alert" />{t}</p>)}
        </div>
      )}
      {years.length >= 1 && years.some((y) => y.roe != null) && (<>
        <div className="card dp-card">
          <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>DuPont analysis<ChartHelp id="dupont" /></h3><span className="s">What drives the return on equity</span></div>
          <p className="dp-eq"><b>ROE</b> = <span>Net profit margin</span> × <span>Asset turnover</span> × <span>Equity multiplier</span></p>
          <HScroll className="" label="DuPont analysis">
            <table className="dp-t"><thead><tr><th>Component</th>{years.map((y) => <th key={y.period}>{fy(y.period)}</th>)}</tr></thead>
              <tbody>
                <tr><td>Net profit / revenue{lender ? " (total income)" : ""}</td>{years.map((y) => <td key={y.period}>{y.netMargin == null ? MINUS : nf(y.netMargin, 2) + "%"}{y.flag && <sup className="dp-flag" title={y.flag}>⚑</sup>}</td>)}</tr>
                {hasUnderlying && <tr className="sub"><td>… without discontinued operations</td>{years.map((y) => <td key={y.period}>{y.underlyingMargin == null ? MINUS : nf(y.underlyingMargin, 2) + "%"}</td>)}</tr>}
                {five && canFive && <>
                  <tr className="sub"><td>… tax burden (profit after tax / before tax)</td>{years.map((y) => <td key={y.period}>{y.taxBurden == null ? MINUS : nf(y.taxBurden, 2)}</td>)}</tr>
                  <tr className="sub"><td>… interest burden (pre-tax profit / EBIT)</td>{years.map((y) => <td key={y.period}>{y.interestBurden == null ? MINUS : nf(y.interestBurden, 2)}</td>)}</tr>
                  <tr className="sub"><td>… EBIT margin</td>{years.map((y) => <td key={y.period}>{y.ebitMargin == null ? MINUS : nf(y.ebitMargin, 2) + "%"}</td>)}</tr></>}
                <tr><td>Revenue / total assets</td>{years.map((y) => <td key={y.period}>{y.turnover == null ? MINUS : nf(y.turnover, 2) + "×"}</td>)}</tr>
                <tr><td>Total assets / total equity</td>{years.map((y) => <td key={y.period}>{y.multiplier == null ? MINUS : nf(y.multiplier, 2) + "×"}</td>)}</tr>
                <tr className="tot"><td>Calculated ROE</td>{years.map((y) => <td key={y.period}>{y.roe == null ? MINUS : nf(y.roe, 1) + "%"}</td>)}</tr>
              </tbody></table>
          </HScroll>
          {canFive && <button type="button" className="alx-link dp-more" aria-pressed={five} onClick={() => setFive(!five)}>{five ? "Show the simple three-factor view" : "Split net margin further (tax, interest, operating)"}</button>}
          {d.factors.length > 0 && (
            <div className="dp-tiles" role="list">{d.factors.map((x) => (
              <div className={"dp-tile " + x.verdict} role="listitem" key={x.key}>
                <span className="k">{x.label}</span>
                <b>{x.key === "netMargin" ? nf(x.first ?? 0, 1) + "% → " + nf(x.last ?? 0, 1) + "%" : nf(x.first ?? 0, 2) + "× → " + nf(x.last ?? 0, 2) + "×"}</b>
                <small>{arrow(x.verdict)} {x.changePct == null ? "" : (x.changePct > 0 ? "+" : "") + nf(x.changePct, 1) + "%"}{x.shareOfMove != null ? ` · ${x.shareOfMove}% of the ROE move` : ""}</small>
              </div>))}</div>
          )}
          {d.words.map((t, i) => <p className={i === d.words.length - 1 ? "faint dp-note" : "dp-say"} key={i}>{t}</p>)}
          {flagged.map((y) => <p className="dp-find" key={y.period}><Icon name="alert" /><span><b>{fy(y.period)}:</b> {y.flag}</span></p>)}
          <p className="faint dp-note">Worked out from the company's own statements, using each year-end balance sheet. Net profit is the part that belongs to the company's shareholders. Information only, not investment advice.</p>
        </div>
        <DecodeRoe symbol={symbol} pl={f.data?.yearly.pl} bs={f.data?.yearly.bs} lender={lender} said={d.words} />
      </>)}
    </div>
  );
}
