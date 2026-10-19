import { Icon } from "../lib/icons";
import { Link } from "react-router";
import { RANK, TIER, useUI, type Plan } from "../lib/ui";
import { useAuth } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { useDocTitle } from "../lib/title";

const PLANS: { k: Plan; tag: string; desc: string; price: string; per: string; cta: string; inc: string; feat?: boolean; f: [string, string][] }[] = [
  { k: "basic", tag: "Free", desc: "Start your investing journey with essential data and powerful screeners.", price: "Free", per: "forever", cta: "Get started", inc: "Key features",
    f: [["Starter stock screener", "14 core filters: size, returns, P/E, ROE, margin, growth, debt, sector and index. First 25 matches"], ["Company comparison", "Two companies side by side with charts, spider view and valuation"], ["Glossary of finance terms", "95 terms in plain words, with formulas"], ["Latest quarter results & trends", "Newest quarter against last quarter and last year, with trend charts"], ["Company overview & key information", "Business summary, products, market data"], ["Financial statements (historical)", "P&L, balance sheet and cash flow, 5–10 years"], ["Key financial ratios and their history", "Margins and returns over the years, plus valuation, efficiency and leverage"], ["Shareholding pattern", "Promoters, institutions and public, quarter by quarter"], ["Peer comparison", "Compare with industry peers"], ["Basic charts & technical data", "Price chart, volume, moving averages"]] },
  { k: "silver", tag: "Popular to get started", desc: "Structured insights with a stock score from FinLit's proprietary model.", price: "Soon", per: "pricing at launch", cta: "Upgrade to Silver", inc: "Everything in Basic, plus",
    f: [["Full stock screener: 160+ filters", "Valuation, profitability, growth, quarterly results, financial health, ownership, red flags, trend and more. Every match, ready-made screens, saved screens and download"], ["Basic stock scoring model", "Overall score on key parameters"], ["Scorecard on each stock page", "Clear, easy-to-read visual scorecard"], ["Detailed parameter view", "How each parameter contributes to the score"], ["Watchlist with lists, notes and targets", "Up to 3 lists and 30 stocks, bucketed by industry and size"], ["Model-based comparison", "Quality & risk, growth and technical views, and build-your-own"], ["Export data", "Download financial data, scorecards and PDF notes"], ["Results, IPO and news calendars", "Result dates, open and upcoming IPOs, and company filings (free for everyone)"], ["Portfolio tracker with import", "Holdings, profit and loss, allocation and a health read; paste or upload a broker file"]] },
  { k: "gold", tag: "Most popular", desc: "Deep insights with advanced scoring, in-depth analysis, technical intelligence and stock bucketing.", price: "Soon", per: "pricing at launch", cta: "Upgrade to Gold", inc: "Everything in Silver, plus", feat: true,
    f: [["Advanced stock scoring model (Soon)", "In-depth analysis with more parameters and weightage"], ["Detailed ratio analysis", "Every ratio with its multi-year history"], ["Technical analysis", "Multiple indicators, trend, momentum"], ["FinLit model screener filters", "On top of Silver's 160+ filters: FinLit score, band, each of the five pillars and score movement, plus Gold screens"], ["Compare up to 4 companies", "Pillar spider chart and full side-by-side view"], ["Smart watchlist", "Unlimited lists, bucket by FinLit band and style, and see what needs a second look"], ["Stock bucketing & triggers", "Size, style, income and momentum scales with key triggers"], ["Revenue insights & segmentation", "By reported segment, with growth"], ["Advanced charts & peer insights", "Sector benchmarking, valuation comparison, key triggers"], ["Equity research report (Later)", "A written, in-depth report on a company"], ["Priority access to new features", "Early access to new tools and models"]] },
];
const fIcon = (t: string) => /screener|filter/i.test(t) ? "table" : /overview|company/i.test(t) ? "building" : /statement/i.test(t) ? "notes" : /ratio/i.test(t) ? "gauge" : /peer/i.test(t) ? "layers" : /chart|technical|momentum/i.test(t) ? "line" : /scor|scorecard/i.test(t) ? "quality" : /parameter|trend/i.test(t) ? "growth" : /watchlist|portfolio/i.test(t) ? "wallet" : /export|download/i.test(t) ? "table" : /bucket/i.test(t) ? "layers" : /revenue|segment/i.test(t) ? "pie" : /priority|access/i.test(t) ? "crown" : "check";
function PlanArt({ k }: { k: Plan }) {
  return (
    <svg className="pl-art" viewBox="0 0 300 96" aria-hidden="true" role="presentation">
      <defs><linearGradient id={`pa${k}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--tc)" stopOpacity=".5" /><stop offset="1" stopColor="var(--tc)" stopOpacity="0" /></linearGradient></defs>
      {k === "basic" && <g>{[0, 1, 2, 3].map((i) => <g key={i}><rect x="14" y={12 + i * 21} width="272" height="15" rx="5" fill="var(--tc)" opacity={0.1 + (i % 2) * 0.08} /><rect x="22" y={16 + i * 21} width={60 + i * 14} height="7" rx="3" fill="var(--tc)" opacity=".7" /><rect x="190" y={16 + i * 21} width="30" height="7" rx="3" fill="var(--tc)" opacity=".4" /><rect x="238" y={16 + i * 21} width={28 - i * 4} height="7" rx="3" fill="var(--gain)" opacity=".8" /></g>)}</g>}
      {k === "silver" && <g><circle cx="52" cy="48" r="32" fill="none" stroke="var(--s3)" strokeWidth="9" /><circle className="ring-in" cx="52" cy="48" r="32" fill="none" stroke="var(--tc)" strokeWidth="9" strokeLinecap="round" strokeDasharray="120 300" transform="rotate(-90 52 48)" /><text x="52" y="54" textAnchor="middle" fontSize="20" fontFamily="Newsreader, serif" fill="var(--text)">51</text>{[["--p-quality", 56], ["--p-growth", 44], ["--p-profit", 51], ["--p-balance", 75], ["--p-tech", 31]].map(([c, w], i) => <g key={c as string}><rect x="110" y={14 + i * 16} width="170" height="8" rx="4" fill="var(--s3)" /><rect className="bar-in" style={{ animationDelay: `${i * 100}ms` }} x="110" y={14 + i * 16} width={(w as number) * 1.7} height="8" rx="4" fill={`var(${c})`} /></g>)}</g>}
      {k === "gold" && <g><path d="M10 80 50 62 90 68 130 38 170 46 210 22 250 30 290 10V96H10z" fill={`url(#pa${k})`} /><path className="draw" d="M10 80 50 62 90 68 130 38 170 46 210 22 250 30 290 10" fill="none" stroke="var(--tc)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /><path d="M214 84a24 24 0 0 1 48 0" fill="none" stroke="var(--s3)" strokeWidth="6" strokeLinecap="round" /><path d="M214 84a24 24 0 0 1 20-23.7" fill="none" stroke="var(--info)" strokeWidth="6" strokeLinecap="round" /></g>}
    </svg>
  );
}
const CMP: [string, string | null, number?][] = [
  ["Free for everyone (Basic)", null], ["Financial statements", "Profit and loss, balance sheet, cash flow", 0], ["Key ratios, peers and shareholding", "Valuation, returns, margins, debt and who owns the company", 0], ["Starter screener", "14 core filters, sector, size and index. First 25 matches", 0],
  ["Compare two companies", "Overview, fundamentals, spider chart and valuation", 0], ["Glossary of finance terms", "95 terms with formulas", 0], ["Results, IPO and news calendars", "Dates, open issues and company filings", 0], ["Price chart, volume and moving averages", "", 0], ["Alerts on price and volume", "", 0],
  ["Silver: scores and tools", null], ["Full screener: 160+ filters", "Valuation, quarterly results, ownership, red flags, trend and more. Every match, ready-made and saved screens, download", 1],
  ["FinLit model score across five pillars", "Quality, Growth, Profitability, Balance sheet, Technical", 1], ["Fundamental and technical scores, kept separate", "Read the business and the price trend on their own", 1], ["Parameter view and historical trends", "How each number moves the score", 1],
  ["Watchlists with notes and targets", "3 lists and 30 stocks", 1], ["Portfolio tracker with CSV import", "Value, profit and loss, allocation and a health read", 1], ["Download: PDF note, offline copy, CSV", "", 1],
  ["Gold: deeper analysis", null], ["FinLit model screener filters", "Filter by score, band, the five pillars and score movement", 2], ["Advanced scoring model", "More parameters, higher-weight factors", 2], ["Technical analysis and momentum", "RSI, moving averages, trend signals", 2], ["Compare up to four companies", "", 2],
  ["Gold dashboards", "Stock fundamentals, market events and index dashboard, premium report", 2], ["Smart watchlist: up to 1,000 stocks", "Bucket by band and style, second-look flags", 2], ["Priority access to new features", "", 2],
  ["Planned", null], ["Equity research report (coming soon)", "Subject to the required licence and approvals", 9],
];

export function PlansBand({ id, h1 = false, compact = false }: { id?: string; h1?: boolean; compact?: boolean }) {
  const H = h1 ? "h1" : "h2";
  const { plan, upgrade } = useUI();
  const { user } = useAuth();
  const cta = (k: Plan, label: string) => DEMO ? (plan === k ? "Previewing " + TIER[k].n : label) : plan === k && (user || k === "basic") ? (user ? "Your plan" : "Included for everyone") : k === "basic" ? "Create a free account" : user ? `Request ${TIER[k].n}` : label;
  const go = (k: Plan) => { if (!DEMO && k === "basic") return; upgrade(k); if (DEMO) window.scrollTo({ top: 0, behavior: "smooth" }); };
  return (
    <section className="band plans" id={id} aria-labelledby="plansTitle">
      <div className="wrap">
        <div className="plans-h">
          <div className="eyebrow" style={{ marginBottom: 12 }}>FinLit plans</div>
          <H id="plansTitle">Invest smarter with <em>the right plan</em></H>
          <p>From essential stock data to advanced intelligence, powered by FinLit's proprietary scoring model.</p>
        </div>
        {!compact && <>
        <div className="trust">{[["bars", "Data-driven insights"], ["spark", "Proprietary scoring model"], ["quality", "Reliable & transparent"], ["users", "Built for every investor"]].map(([i, t]) => <span key={t}><Icon name={i} />{t}</span>)}</div>
        <div className="who">{([["sprout", "I'm just starting out", "Free data on every listed stock, plus a powerful screener.", "basic"], ["quality", "I want the score and the story", "The five-pillar scorecard, trends and a watchlist.", "silver"], ["crown", "I invest seriously", "Advanced scoring, full ratio history and technical signals.", "gold"]] as const).map(([ic, t, d, k]) => (
          <button key={k} className="who-c" style={{ "--tc": `var(${TIER[k].tc})` } as React.CSSProperties} onClick={() => { if (DEMO) upgrade(k); else document.getElementById(`plan-${k}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); }}>
            <span className="who-i"><Icon name={ic} /></span><b>{t}</b><span>{d}</span><em>{TIER[k].n} plan <Icon name="arrow" /></em>
          </button>))}</div>
        </>}
        {!compact && (
        <div className="pgrid">
          {PLANS.map((p) => (
            <div key={p.k} id={`plan-${p.k}`} data-cur={DEMO ? "Previewing" : "Your plan"} className={`plan ${p.feat ? "feat" : ""} ${plan === p.k && (DEMO || user || p.k === "basic") ? "current" : ""}`} style={{ "--tc": `var(${TIER[p.k].tc})` } as React.CSSProperties}>
              <PlanArt k={p.k} />
              <div className="plan-top"><div className="plan-name"><span className="pi"><Icon name={TIER[p.k].ic} /></span>{TIER[p.k].n}</div><span className="ribbon">{p.tag}</span></div>
              <p className="plan-desc">{p.desc}</p>
              <div className="price"><b>{p.price}</b><span>{p.per}</span></div>
              {!DEMO && p.k === "basic" && !user ? <Link className="btn" to="/login?mode=signup">{cta(p.k, p.cta)} <Icon name="arrow" /></Link>
                : <button className="btn" disabled={!DEMO && plan === p.k && (!!user || p.k === "basic")} onClick={() => go(p.k)}>{cta(p.k, p.cta)} <Icon name="arrow" /></button>}
              <div className="inc">{p.inc}<span className="inc-n">{p.f.length} features</span></div>
              <ul>{p.f.map(([a, b]) => <li key={a}><span className="ck"><Icon name={fIcon(a)} /></span><span><b>{a}</b><span className="d">{b}</span></span></li>)}</ul>
            </div>
          ))}
        </div>
        )}
        {<>
        <div className="cmp-h"><h3>{compact ? "What each plan includes" : "Compare every feature"}</h3><p>{DEMO ? "Pick a plan to preview it on a stock page." : "Pricing is announced at launch. Until then, request a plan and we will switch it on for your account."}</p></div>
        <div className="cmp"><div className="cmp-scroll"><table>
          <thead><tr><th>Feature</th>{PLANS.map((p) => <th key={p.k} className={"th-" + p.k + (plan === p.k ? " cur" : "")} style={{ "--tc": `var(${TIER[p.k].tc})` } as React.CSSProperties}><span className="th-i"><Icon name={TIER[p.k].ic} /></span><b>{TIER[p.k].n}</b><small>{p.k === "basic" ? "Free" : "Pricing soon"}</small></th>)}</tr></thead>
          <tbody>{CMP.map(([n, d, need]) => d === null ? <tr className="grp" key={n}><td colSpan={4}>{n}</td></tr> :
            <tr key={n}><td><span className="cf"><span className="cf-i"><Icon name={fIcon(n)} /></span><span><b>{n.replace(" (coming soon)", "")}{n.endsWith("(coming soon)") && <span className="soon-tag">Coming soon</span>}</b>{d ? <small>{d}</small> : null}</span></span></td>{PLANS.map((p) => RANK[p.k] >= (need ?? 0) ? <td key={p.k} className={"c-" + p.k}><span className="yes ck" role="img" aria-label="Included"><Icon name="check" /></span></td> : <td key={p.k} className={"c-" + p.k}><span className="x-no" role="img" aria-label="Not included">✕</span></td>)}</tr>)}</tbody>
          <tfoot><tr><td>Features included</td>{PLANS.map((p) => <td key={p.k} className={"c-" + p.k}><b className="cnt" style={{ "--tc": `var(${TIER[p.k].tc})` } as React.CSSProperties}>{CMP.filter(([, d, need]) => d !== null && RANK[p.k] >= (need ?? 0)).length}</b></td>)}</tr>
            {compact && <tr className="cta-r"><td />{PLANS.map((p) => <td key={p.k} className={"c-" + p.k}>{!DEMO && p.k === "basic" && !user ? <Link className="btn" to="/login?mode=signup">{cta(p.k, p.cta)}</Link> : <button className={"btn" + (p.feat ? " primary" : "")} disabled={!DEMO && plan === p.k && (!!user || p.k === "basic")} onClick={() => go(p.k)}>{cta(p.k, p.cta)}</button>}</td>)}</tr>}</tfoot>
        </table></div></div>
        <p className="plans-note">Plans and features are subject to change. Pricing will be announced at launch. {DEMO ? "Use “Preview” to see a stock page as each plan." : "Request a plan from your account and we will confirm it by email."}</p>
        </>}
      </div>
    </section>
  );
}

export function PlansPage() {
  useDocTitle("Plans", "FinLit plans: Basic (free), Silver and Gold, from essential stock data to advanced scoring and technical intelligence.");
  return <PlansBand h1 />;
}
