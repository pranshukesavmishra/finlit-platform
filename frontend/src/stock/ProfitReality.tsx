import { useMemo } from "react";
import { HScroll } from "../components/HScroll";
import { ChartHelp } from "../components/ChartHelp";
import { Icon } from "../lib/icons";
import { useSection, type Financials } from "../lib/api";
import { MINUS, nf } from "../lib/format";
import { fyLabel, profitReality, type Status } from "../lib/profitReality";
import "../styles/profitreality.css";

const sn = (v: number | null, d = 0, suffix = "") => (v == null ? MINUS : (v < 0 ? MINUS : "") + nf(v, d) + suffix);
const sg = (v: number | null, suffix = "%") => (v == null ? MINUS : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(v, 1) + suffix);
const mark: Record<Status, string> = { ok: "✓", warn: "!", flag: "⚑", na: "–" };
const word: Record<Status, string> = { ok: "Passed", warn: "Watch", flag: "Flagged", na: "Not tested" };
const tone = { Strong: "good", Mixed: "mid", "Needs a closer look": "bad" } as const;

/** Profit Reality Check: reported profit against normalized profit, cash conversion, one-off items and working capital, from the company's own statements. */
export function ProfitReality({ symbol, lender }: { symbol: string; lender: boolean }) {
  const f = useSection<Financials>(symbol, "financials", !!symbol);
  const r = useMemo(() => profitReality(f.data?.yearly.pl, f.data?.yearly.bs, f.data?.yearly.cf, lender), [f.data, lender]);
  const ys = r.years;
  if (!ys.length) return null;
  // Bar heights: scaled by the largest absolute value, clamped to 3..100 per cent so a bad number can never zero or overflow a bar.
  const max = Math.max(...ys.flatMap((y) => [Math.abs(y.netProfit ?? 0), Math.abs(y.normalized ?? 0)]));
  const h = (v: number | null) => (v == null || !Number.isFinite(v) || !(max > 0) ? 0 : Math.min(100, Math.max(3, (Math.abs(v) / max) * 100)));
  const anyNeg = ys.some((y) => (y.netProfit ?? 0) < 0 || (y.normalized ?? 0) < 0);
  const bar = (v: number | null, cls: string, label: string) => v == null ? <i className="pr-bar none" /> : (
    <i className={"pr-bar " + cls + (v < 0 ? " neg" : "")} style={{ height: `${h(v)}%` }} title={`${label}: ${sn(v)} crore`} />);
  const hasOneOff = ys.some((y) => y.exceptional != null || y.discontinued != null);
  const hasOi = ys.some((y) => y.otherIncomeShare != null);
  const hasWc = !lender && ys.some((y) => y.receivablesGrowth != null || y.inventoryGrowth != null);
  const hasCash = !lender && ys.some((y) => y.cfoToProfit != null);
  return (
    <div className="card pr-card" aria-label="Profit Reality Check">
      <div className="card-h"><h3><span className="ci"><Icon name="shield" /></span>Profit Reality Check<ChartHelp id="profit-reality" /></h3><span className="s">Is the profit real, repeatable and backed by cash? · ₹ crore</span></div>

      <div className={"pr-verdict " + (r.verdict ? tone[r.verdict] : "none")} role="status">
        <span className="k">Earnings quality</span>
        <b>{r.verdict ?? "Not enough data to judge"}</b>
        {r.findings.length > 0 && <ul>{r.findings.map((t, i) => <li key={i}>{t}</li>)}</ul>}
        {r.verdict === "Strong" && !r.findings.length && <p>Profit is backed by cash, one-off items are small and receivables and inventory are keeping pace with sales.</p>}
      </div>
      <details className="pr-rules"><summary>How this is decided</summary>
        <ul>{r.rules.map((x) => <li key={x.key} className={x.status}><span className="m" aria-hidden="true">{mark[x.status]}</span><span><b>{word[x.status]}.</b> {x.text}. <small>{x.detail}</small></span></li>)}</ul>
        <p className="faint">Two or more flagged rules, or "profit rose but cash did not", gives "Needs a closer look". One flagged rule or two watch rules gives "Mixed". Otherwise "Strong". At least three tests (one for lenders) need data first.</p>
      </details>
      {r.notes.map((t, i) => <p className="faint pr-note" key={i}>{t}</p>)}

      <h4 className="pr-h">Reported profit against normalized profit</h4>
      <p className="pr-say">Normalized profit takes out discontinued operations, exceptional items after tax, and other income above {20}% of pre-tax profit. It is a cleaner guide to what the core business earns, not a forecast.</p>
      <div className={"pr-chart" + (anyNeg ? " neg" : "")} role="img" aria-label={"Reported and normalized net profit by year: " + ys.map((y) => `${fyLabel(y.period)} reported ${sn(y.netProfit)}, normalized ${sn(y.normalized)}`).join("; ")}>
        {ys.map((y) => (
          <div className="pr-col" key={y.period}>
            <div className="pr-bars">{bar(y.netProfit, "rep", "Reported")}{bar(y.normalized, "nrm", "Normalized")}</div>
            <span className="pr-x">{y.period}</span>
          </div>))}
      </div>
      <p className="pr-legend"><i className="rep" />Reported<i className="nrm" />Normalized</p>
      <HScroll className="" label="reported and normalized profit">
        <table className="pr-t"><thead><tr><th>Item</th>{ys.map((y) => <th key={y.period}>{fyLabel(y.period)}</th>)}</tr></thead>
          <tbody>
            <tr><td>Reported net profit</td>{ys.map((y) => <td key={y.period}>{sn(y.netProfit)}</td>)}</tr>
            {hasOneOff && <tr className="sub"><td>less discontinued operations</td>{ys.map((y) => <td key={y.period}>{y.discontinued ? sn(y.discontinued) : MINUS}</td>)}</tr>}
            {hasOneOff && <tr className="sub"><td>less exceptional items (after tax)</td>{ys.map((y) => <td key={y.period}>{y.exceptionalAfterTax ? sn(y.exceptionalAfterTax) : MINUS}</td>)}</tr>}
            {hasOi && <tr className="sub"><td>less other income above threshold (after tax)</td>{ys.map((y) => <td key={y.period}>{y.otherIncomeAdjustment ? sn(y.otherIncomeAdjustment) : MINUS}</td>)}</tr>}
            <tr className="tot"><td>Normalized profit</td>{ys.map((y) => <td key={y.period}>{sn(y.normalized)}</td>)}</tr>
            {hasOi && <tr className="sub"><td>Other income share of pre-tax profit</td>{ys.map((y) => <td key={y.period} className={y.otherIncomeAdjustment ? "warn" : ""}>{y.otherIncomeShare == null ? MINUS : nf(y.otherIncomeShare, 0) + "%"}</td>)}</tr>}
          </tbody></table>
      </HScroll>
      <p className="faint pr-note">Exceptional items are taxed at the company's effective tax rate for that year (not below 0%, not above 40%; 25% when it cannot be worked out). A dash means nothing to remove or no data.</p>

      {lender ? null : hasCash ? (<>
        <h4 className="pr-h">Cash conversion</h4>
        <HScroll className="" label="cash conversion">
          <table className="pr-t"><thead><tr><th>Item</th>{ys.map((y) => <th key={y.period}>{fyLabel(y.period)}</th>)}</tr></thead>
            <tbody>
              <tr><td>Net profit</td>{ys.map((y) => <td key={y.period}>{sn(y.netProfit)}</td>)}</tr>
              <tr><td>Operating cash flow</td>{ys.map((y) => <td key={y.period}>{sn(y.cfo)}</td>)}</tr>
              <tr className="tot"><td>Operating cash flow / profit</td>{ys.map((y) => <td key={y.period} className={y.cashGap ? "warn" : ""}>{y.cfoToProfit == null ? MINUS : nf(y.cfoToProfit * 100, 0) + "%"}{y.cashGap && <sup className="pr-flag" title="Below 80% of profit">⚑</sup>}</td>)}</tr>
              <tr className="sub"><td>Free cash flow / profit</td>{ys.map((y) => <td key={y.period}>{y.fcfToProfit == null ? MINUS : sn(y.fcfToProfit * 100, 0, "%")}</td>)}</tr>
            </tbody></table>
        </HScroll>
        <div className="pr-tiles" role="list">
          {r.cumulative && <div className={"pr-tile " + (r.cumulative.ratio != null && r.cumulative.ratio < 0.8 ? "warn" : "")} role="listitem"><span className="k">{r.cumulative.years}-year total</span><b>{sn(r.cumulative.cfo)} cash vs {sn(r.cumulative.profit)} profit</b><small>{r.cumulative.ratio == null ? "Profit total is not positive" : `Cash is ${nf(r.cumulative.ratio * 100, 0)}% of profit`}</small></div>}
          <div className={"pr-tile " + (r.gapYears >= 2 ? "warn" : "")} role="listitem"><span className="k">Years below 80% cash conversion</span><b>{r.gapYears} of {r.gapEvaluated}</b><small>{r.gapYears >= 2 ? "The gap repeats" : "Not a repeated pattern"}</small></div>
        </div>
      </>) : <p className="faint pr-note">Operating cash flow was not reported for these years, so cash conversion cannot be shown.</p>}

      {hasOneOff && (<>
        <h4 className="pr-h">One-off gains and losses</h4>
        <HScroll className="" label="one-off items">
          <table className="pr-t"><thead><tr><th>Item</th>{ys.map((y) => <th key={y.period}>{fyLabel(y.period)}</th>)}</tr></thead>
            <tbody>
              <tr><td>Exceptional items (before tax)</td>{ys.map((y) => <td key={y.period}>{y.exceptional == null ? MINUS : sn(y.exceptional)}</td>)}</tr>
              <tr className="sub"><td>… % of pre-tax profit</td>{ys.map((y) => <td key={y.period}>{y.exceptionalPctPretax == null ? MINUS : nf(y.exceptionalPctPretax, 0) + "%"}</td>)}</tr>
              <tr><td>Discontinued operations (after tax)</td>{ys.map((y) => <td key={y.period}>{y.discontinued == null ? MINUS : sn(y.discontinued)}</td>)}</tr>
              <tr className="sub"><td>… % of net profit</td>{ys.map((y) => <td key={y.period}>{y.discontinuedPctNet == null ? MINUS : nf(y.discontinuedPctNet, 0) + "%"}</td>)}</tr>
              <tr className="tot"><td>15% or more of profit?</td>{ys.map((y) => <td key={y.period} className={y.oneOffFlag ? "warn" : ""}>{y.oneOffFlag ? "⚑ Yes" : "No"}</td>)}</tr>
            </tbody></table>
        </HScroll>
      </>)}

      {lender ? null : hasWc ? (<>
        <h4 className="pr-h">Receivables and inventory against sales</h4>
        <HScroll className="" label="working capital growth">
          <table className="pr-t"><thead><tr><th>Yearly growth</th>{ys.map((y) => <th key={y.period}>{fyLabel(y.period)}</th>)}</tr></thead>
            <tbody>
              <tr><td>Revenue</td>{ys.map((y) => <td key={y.period}>{sg(y.revenueGrowth)}</td>)}</tr>
              <tr><td>Receivables</td>{ys.map((y) => <td key={y.period} className={y.receivablesFlag ? "warn" : ""}>{sg(y.receivablesGrowth)}{y.receivablesFlag && <sup className="pr-flag" title="10 or more points faster than revenue">⚑</sup>}</td>)}</tr>
              <tr><td>Inventory</td>{ys.map((y) => <td key={y.period} className={y.inventoryFlag ? "warn" : ""}>{sg(y.inventoryGrowth)}{y.inventoryFlag && <sup className="pr-flag" title="10 or more points faster than revenue">⚑</sup>}</td>)}</tr>
            </tbody></table>
        </HScroll>
        <p className="faint pr-note">Flagged when receivables or inventory grew 10 or more points faster than revenue in the latest year, or two years running. Growth is not worked out when the earlier year is zero or missing.</p>
      </>) : <p className="faint pr-note">Receivables and inventory are not reported, so the working-capital test cannot be shown.</p>}

      <p className="faint pr-note">Worked out from the company's own yearly statements. These are warning signs to investigate, not proof of anything, and not investment advice.</p>
    </div>
  );
}
