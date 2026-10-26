import { Icon } from "../lib/icons";
import { Link } from "react-router";
import { RANK, TIER, useUI, type Plan } from "../lib/ui";
import { useAuth } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { useDocTitle } from "../lib/title";

const PLANS: { k: Plan; tag: string; desc: string; price: string; per: string; cta: string; inc: string; feat?: boolean; f: [string, string][] }[] = [
  { k: "basic", tag: "Free", desc: "Look up any listed company and run a simple screen. No card needed.", price: "Free", per: "no card needed", cta: "Create a free account", inc: "What you get",
    f: [["Starter stock screener", "14 filters: size, returns, P/E, ROE, margin, growth, debt, sector and index. Shows the first 25 matches. 3 saved screens"], ["Compare two companies", "Side by side, with charts, a spider view and valuation"], ["Glossary", "300+ finance terms in plain words, with formulas"], ["Latest quarter and trends", "The newest quarter against the last quarter and last year"], ["Company overview", "What the business does, its products and market data"], ["Financial statements", "Profit and loss, balance sheet and cash flow, 5 to 10 years"], ["Key ratios and their history", "Margins and returns over the years, plus valuation, efficiency and debt"], ["Shareholding pattern", "Promoters, institutions and public, quarter by quarter"], ["Peer comparison", "How a company stacks up against others in its industry"], ["Price chart", "Price, volume and the 50-day average"], ["Alerts", "3 alerts on price, volume and a few technical triggers"], ["Results, IPO and news calendars", "Result dates, open and upcoming IPOs, and company filings"]] },
  { k: "silver", tag: "Score + full screener", desc: "Adds the FinLit score for every company and the full screener.", price: "Soon", per: "payments not live yet", cta: "Get Silver", inc: "Everything in Basic, plus",
    f: [["Full screener: 160+ filters", "Valuation, profitability, growth, quarterly results, financial health, ownership, red flags, trend and more. Every match, ready-made screens, 20 saved screens and CSV download"], ["FinLit score and five pillars", "An overall score from 0 to 100 on each stock page, built from Quality, Growth, Profitability, Balance sheet and Technical"], ["How the score is built", "Which numbers went into each pillar, and how they were read"], ["Watchlists", "3 lists and 30 stocks in total, with notes and target prices. Group by industry and size"], ["Score-based comparison", "Quality and risk, growth and technical tabs, plus build your own"], ["Downloads", "PDF research note, an offline HTML copy, and CSV of data and screener results"], ["Portfolio scorecard", "Add up to 30 shares by name (typed, pasted or from a broker Excel/CSV). See each share's score, your average score and sector mix. It does not use quantities or prices, so there is no profit and loss"], ["More alerts", "30 alerts, including P/E, ROE and FinLit score triggers"]] },
  { k: "gold", tag: "Most depth", desc: "More depth for people who check companies often: model filters, full ratio history and technical signals.", price: "Soon", per: "payments not live yet", cta: "Get Gold", inc: "Everything in Silver, plus", feat: true,
    f: [["FinLit model filters in the screener", "On top of the 160+ filters: score, band, each of the five pillars and score movement, plus Gold screens"], ["Full ratio history", "Every ratio with its multi-year history, and valuation history"], ["Technical analysis", "Indicators such as RSI and the 200-day average, with trend and momentum"], ["Compare up to 4 companies", "Pillar spider chart and a full side-by-side view"], ["Bigger watchlists", "Up to 50 lists and 1,000 stocks, grouped by FinLit band and style, with a list of what needs a second look"], ["Revenue by segment", "Reported business segments, with growth"], ["Gold dashboards", "Markets, fundamentals and a printable Premium Report for any company"], ["DCF calculator", "Intrinsic value per share with margin of safety, any listed company's cash flow and debt loaded for you, sensitivity grids, reverse DCF and saved scenarios"], ["Bigger limits", "Up to 300 alerts, 100 saved screens and 500 shares in the portfolio scorecard"], ["Advanced scoring model (not built yet)", "A deeper model with more inputs. We will tell you when it is ready"], ["Equity research report (planned, later)", "A written report on a company. Only after the licence and approvals it needs are in place"]] },
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
  ["Free for everyone (Basic)", null], ["Financial statements", "Profit and loss, balance sheet, cash flow", 0], ["Key ratios, peers and shareholding", "Valuation, returns, margins, debt and who owns the company", 0], ["Starter screener", "14 filters, sector, size and index. First 25 matches, 3 saved screens", 0],
  ["Compare two companies", "Overview, fundamentals, spider chart and valuation", 0], ["Glossary of finance terms", "313 terms with formulas", 0], ["Results, IPO and news calendars", "Dates, open issues and company filings", 0], ["Price chart, volume and 50-day average", "", 0], ["Alerts", "Basic 3, Silver 30, Gold 300. Some triggers start at Silver", 0],
  ["Silver: scores and tools", null], ["Full screener: 160+ filters", "Valuation, quarterly results, ownership, red flags, trend and more. Every match, 20 saved screens, download", 1],
  ["FinLit score across five pillars", "Quality, Growth, Profitability, Balance sheet, Technical", 1], ["Fundamental and technical scores side by side", "Read the business and the price trend on their own", 1], ["How the score is built", "Which numbers move each pillar", 1],
  ["Watchlists with notes and targets", "Silver: 3 lists, 30 stocks", 1], ["Portfolio scorecard", "Add shares by name. Score, band mix and sector spread. No profit and loss", 1], ["Downloads: PDF note, offline copy, CSV", "", 1],
  ["Gold: more depth", null], ["FinLit model filters in the screener", "Filter by score, band, the five pillars and score movement", 2], ["Full ratio history", "Every ratio over several years, and valuation history", 2], ["Technical analysis and momentum", "RSI, 200-day average, trend", 2], ["Compare up to four companies", "", 2],
  ["Gold dashboards", "Markets, fundamentals, Premium Report", 2], ["DCF calculator", "Intrinsic value, sensitivity, reverse DCF", 2], ["Bigger watchlists", "Up to 50 lists and 1,000 stocks, grouped by band and style", 2], ["Bigger limits", "100 saved screens, 500 shares in the scorecard", 2],
  ["Planned, not built yet", null], ["Advanced scoring model, not built yet", "More inputs and weights. Planned for Gold", 9], ["Equity research report (coming soon)", "Subject to the required licence and approvals", 9],
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
          <H id="plansTitle">Start free. Add more <em>when you need it</em></H>
          <p>Basic costs nothing and needs no card. Silver and Gold add the FinLit score, the full screener and more tools. Payments are not live yet, so for now we switch Silver and Gold on by hand when you ask.</p>
        </div>
        {!compact && <>
        <div className="trust">{[["check", "Basic is free, no card"], ["spark", "A score helps you compare. It is not advice"], ["quality", "Every report shows when it was last updated"], ["users", "Plans are switched on by our team for now"]].map(([i, t]) => <span key={t}><Icon name={i} />{t}</span>)}</div>
        <div className="who">{([["sprout", "I am new to this", "Statements, ratios and a starter screener for any listed company. Free.", "basic"], ["quality", "I want the score", "The full screener, the five-pillar FinLit score and watchlists.", "silver"], ["crown", "I check companies often", "Model filters, full ratio history, technical signals and bigger limits.", "gold"]] as const).map(([ic, t, d, k]) => (
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
        <div className="cmp-h"><h3>{compact ? "What each plan includes" : "Every feature, plan by plan"}</h3><p>{DEMO ? "Pick a plan to preview it on a stock page." : "Prices are not set yet. Until payments go live, ask for a plan from your account and we will switch it on."}</p></div>
        <div className="cmp"><div className="cmp-scroll"><table>
          <thead><tr><th>Feature</th>{PLANS.map((p) => <th key={p.k} className={"th-" + p.k + (plan === p.k ? " cur" : "")} style={{ "--tc": `var(${TIER[p.k].tc})` } as React.CSSProperties}><span className="th-i"><Icon name={TIER[p.k].ic} /></span><b>{TIER[p.k].n}</b><small>{p.k === "basic" ? "Free" : "Price to come"}</small></th>)}</tr></thead>
          <tbody>{CMP.map(([n, d, need]) => d === null ? <tr className="grp" key={n}><td colSpan={4}>{n}</td></tr> :
            <tr key={n}><td><span className="cf"><span className="cf-i"><Icon name={fIcon(n)} /></span><span><b>{n.replace(" (coming soon)", "")}{n.endsWith("(coming soon)") && <span className="soon-tag">Coming soon</span>}</b>{d ? <small>{d}</small> : null}</span></span></td>{PLANS.map((p) => RANK[p.k] >= (need ?? 0) ? <td key={p.k} className={"c-" + p.k}><span className="yes ck" role="img" aria-label="Included"><Icon name="check" /></span></td> : <td key={p.k} className={"c-" + p.k}><span className="x-no" role="img" aria-label="Not included">✕</span></td>)}</tr>)}</tbody>
          <tfoot><tr><td>Features included</td>{PLANS.map((p) => <td key={p.k} className={"c-" + p.k}><b className="cnt" style={{ "--tc": `var(${TIER[p.k].tc})` } as React.CSSProperties}>{CMP.filter(([, d, need]) => d !== null && RANK[p.k] >= (need ?? 0)).length}</b></td>)}</tr>
            {compact && <tr className="cta-r"><td />{PLANS.map((p) => <td key={p.k} className={"c-" + p.k}>{!DEMO && p.k === "basic" && !user ? <Link className="btn" to="/login?mode=signup">{cta(p.k, p.cta)}</Link> : <button className={"btn" + (p.feat ? " primary" : "")} disabled={!DEMO && plan === p.k && (!!user || p.k === "basic")} onClick={() => go(p.k)}>{cta(p.k, p.cta)}</button>}</td>)}</tr>}</tfoot>
        </table></div></div>
        <p className="plans-note">Features and limits can change. {DEMO ? "Use “Preview” to see a stock page as each plan." : "Ask for a plan from your account and we will confirm it by email."} Scores and tools here are for information only and are not investment advice.</p>
        </>}
      </div>
    </section>
  );
}

export function PlansPage() {
  useDocTitle("Plans", "FinLit plans: Basic is free. Silver adds the FinLit score and the full screener. Gold adds model filters, full ratio history and technical signals. Payments are not live yet.");
  return <PlansBand h1 />;
}
