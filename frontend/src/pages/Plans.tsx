import { Icon } from "../lib/icons";
import { RANK, TIER, useUI, type Plan } from "../lib/ui";
import { useDocTitle } from "../lib/title";

const PLANS: { k: Plan; tag: string; desc: string; price: string; per: string; cta: string; inc: string; feat?: boolean; f: [string, string][] }[] = [
  { k: "basic", tag: "Free", desc: "Start your investing journey with essential data and powerful screeners.", price: "Free", per: "forever", cta: "Get started", inc: "Key features",
    f: [["Stock screener with advanced filters", "Market cap, sector, industry, P/E, ROE, dividend and more"], ["Company overview & key information", "Business summary, products, market data"], ["Financial statements (historical)", "P&L, balance sheet and cash flow, 5–10 years"], ["Key financial ratios", "Valuation, profitability, efficiency, leverage"], ["Peer comparison", "Compare with industry peers"], ["Basic charts & technical data", "Price chart, volume, moving averages"]] },
  { k: "bronze", tag: "Popular to get started", desc: "Structured insights with a stock score from FinLit's proprietary model.", price: "Soon", per: "pricing at launch", cta: "Upgrade to Bronze", inc: "Everything in Basic, plus",
    f: [["Basic stock scoring model", "Overall score on key parameters"], ["Scorecard on each stock page", "Clear, easy-to-read visual scorecard"], ["Detailed parameter view", "How each parameter contributes to the score"], ["Historical trend for each parameter", "Track improvement or deterioration over time"], ["Watchlist & portfolio tracking", "Follow your favourite stocks"], ["Export data", "Download financial data, scorecards and PDF notes"]] },
  { k: "gold", tag: "Most popular", desc: "Deep insights with advanced scoring, in-depth analysis, technical intelligence and stock bucketing.", price: "Soon", per: "pricing at launch", cta: "Upgrade to Gold", inc: "Everything in Bronze, plus", feat: true,
    f: [["Advanced stock scoring model", "In-depth analysis with more parameters and weightage"], ["Detailed ratio analysis", "Every ratio with its multi-year history"], ["Technical analysis & advanced score", "Multiple indicators, trend, momentum"], ["Stock bucketing & advanced filters", "Size, sector, theme, value/growth, custom filters"], ["Revenue insights & segmentation", "By reported segment, with growth"], ["Advanced charts & peer insights", "Sector benchmarking, valuation comparison, key triggers"], ["Priority access to new features", "Early access to new tools and models"]] },
];
const CMP: [string, string | null, number?][] = [
  ["Research data", null], ["Stock screener & filters", "Market cap, sector, industry, P/E, ROE", 0], ["Company overview", "Business, key facts", 0], ["Financial statements", "P&L, balance sheet, cash flow", 0], ["Key ratios & peer comparison", "", 0], ["Price chart, volume & moving averages", "", 0],
  ["FinLit scoring", null], ["Research score & five-pillar scorecard", "Quality, Growth, Profitability, Balance sheet, Technical", 1], ["Parameter view & historical trends", "", 1], ["Advanced scoring model", "More parameters, higher-weight factors", 2],
  ["Deep analysis", null], ["Detailed ratio analysis", "Every ratio, with history", 2], ["Technical analysis & momentum score", "RSI, EMAs, trend signals", 2], ["Stock bucketing & triggers", "", 2], ["Revenue segmentation", "", 2],
  ["Tools", null], ["Watchlist & portfolio tracking", "", 1], ["Export: PDF note, offline copy, CSV", "", 1], ["Priority access to new features", "", 2],
];

export function PlansBand({ id }: { id?: string }) {
  const { plan, setPlan, toast } = useUI();
  return (
    <section className="band plans" id={id} aria-labelledby="plansTitle">
      <div className="wrap">
        <div className="plans-h">
          <div className="eyebrow" style={{ marginBottom: 12 }}>FinLit plans</div>
          <h2 id="plansTitle">Invest smarter with <em>the right plan</em></h2>
          <p>From essential stock data to advanced intelligence, powered by FinLit's proprietary scoring model.</p>
        </div>
        <div className="trust">{[["bars", "Data-driven insights"], ["spark", "Proprietary scoring model"], ["quality", "Reliable & transparent"], ["users", "Built for every investor"]].map(([i, t]) => <span key={t}><Icon name={i} />{t}</span>)}</div>
        <div className="who">{([["sprout", "I'm just starting out", "Free data on every listed stock, plus a powerful screener.", "basic"], ["quality", "I want the score and the story", "The five-pillar scorecard, trends and a watchlist.", "bronze"], ["crown", "I invest seriously", "Advanced scoring, full ratio history and technical signals.", "gold"]] as const).map(([ic, t, d, k]) => (
          <button key={k} className="who-c" style={{ "--tc": `var(${TIER[k].tc})` } as React.CSSProperties} onClick={() => { setPlan(k); toast(`Previewing the ${TIER[k].n} plan.`); }}>
            <span className="who-i"><Icon name={ic} /></span><b>{t}</b><span>{d}</span><em>{TIER[k].n} plan <Icon name="arrow" /></em>
          </button>))}</div>
        <div className="pgrid">
          {PLANS.map((p) => (
            <div key={p.k} className={`plan ${p.feat ? "feat" : ""} ${plan === p.k ? "current" : ""}`} style={{ "--tc": `var(${TIER[p.k].tc})` } as React.CSSProperties}>
              <div className="plan-top"><div className="plan-name"><span className="pi"><Icon name={TIER[p.k].ic} /></span>{TIER[p.k].n}</div><span className="ribbon">{p.tag}</span></div>
              <p className="plan-desc">{p.desc}</p>
              <div className="price"><b>{p.price}</b><span>{p.per}</span></div>
              <button className="btn" onClick={() => { setPlan(p.k); toast(`Previewing the ${TIER[p.k].n} plan.${p.k === "gold" ? " Everything is unlocked." : " Locked sections show what upgrading adds."}`); window.scrollTo({ top: 0, behavior: "smooth" }); }}>{plan === p.k ? "Previewing " + TIER[p.k].n : p.cta} <Icon name="arrow" /></button>
              <div className="inc">{p.inc}</div>
              <ul>{p.f.map(([a, b]) => <li key={a}><span className="ck"><Icon name="check" /></span><span><b>{a}</b><span className="d">{b}</span></span></li>)}</ul>
            </div>
          ))}
        </div>
        <div className="cmp"><div className="cmp-scroll"><table>
          <thead><tr><th>Feature</th>{PLANS.map((p) => <th key={p.k}><span className={"tier " + p.k}>{TIER[p.k].n}</span></th>)}</tr></thead>
          <tbody>{CMP.map(([n, d, need]) => d === null ? <tr className="grp" key={n}><td colSpan={4}>{n}</td></tr> :
            <tr key={n}><td>{n}{d ? <span>{d}</span> : null}</td>{PLANS.map((p) => RANK[p.k] >= (need ?? 0) ? <td key={p.k}><span className="yes" style={{ "--tc": `var(${TIER[p.k].tc})` } as React.CSSProperties}><Icon name="check" /></span></td> : <td key={p.k}><span className="no">—</span></td>)}</tr>)}</tbody>
        </table></div></div>
        <p className="plans-note">Plans and features are subject to change. Pricing will be announced at launch. Use “Preview” to see a stock page as each plan.</p>
      </div>
    </section>
  );
}

export function PlansPage() {
  useDocTitle("Plans", "FinLit plans: Basic (free), Bronze and Gold, from essential stock data to advanced scoring and technical intelligence.");
  return <PlansBand />;
}
