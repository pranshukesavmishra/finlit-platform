import { useState, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { Reveal } from "./Reveal";
import { TIER } from "../lib/ui";
import { PLATFORM_CARDS, PLAN_LINK, PLAN_TIER, TIER_FILTERS, filterByTier, type PlatformPreview, type TierFilter } from "../lib/platformCards";
import { TierEmblem } from "./TierEmblem";
import "../styles/platform-grid.css";

/** Miniature, decorative sketches of each tool. Sample numbers only: they stand for no real company, price or result. */
const Tabs = ({ items }: { items: string[] }) => <div className="pg-tabs">{items.map((t, i) => <span key={t} className={i === 0 ? "on" : ""}>{t}</span>)}</div>;
const Row = ({ cells, head }: { cells: ReactNode[]; head?: boolean }) => <div className={"pg-row" + (head ? " h" : "")} style={{ "--n": cells.length } as CSSProperties}>{cells.map((c, i) => <span key={i}>{c}</span>)}</div>;

const PREVIEWS: Record<PlatformPreview, () => ReactNode> = {
  screener: () => <><Tabs items={["Pre-built", "Custom filter", "Model Score"]} /><Row head cells={["Company", "P/E", "ROE", "Score"]} />{[["Company A", "14.2", "18%", "78"], ["Company B", "17.8", "21%", "72"], ["Company C", "11.5", "16%", "69"]].map((r) => <Row key={r[0]} cells={r} />)}</>,
  chart: () => <svg className="pg-svg" viewBox="0 0 200 92">
    {[10, 24, 38, 52].map((y) => <line key={y} x1="0" x2="200" y1={y} y2={y} className="gl" />)}
    {[[14, 30, 18, 40, 1], [34, 34, 22, 36, 0], [54, 24, 12, 30, 1], [74, 28, 16, 22, 1], [94, 20, 10, 26, 0], [114, 18, 8, 14, 1], [134, 22, 12, 20, 0], [154, 12, 6, 16, 1], [174, 14, 8, 10, 1]].map(([x, hi, lo, , up], i) => <g key={i} className={up ? "up" : "dn"}><line x1={x} x2={x} y1={hi - 6} y2={lo + 22} /><rect x={x - 5} width="10" y={Math.min(hi, lo + 12)} height="12" rx="1.5" /></g>)}
    <polyline className="ln" points="0,52 30,46 60,38 90,40 120,30 150,26 200,16" fill="none" strokeWidth="1.6" />
    <polyline className="rsi" points="0,84 25,78 50,86 75,76 100,80 125,72 150,78 175,74 200,70" fill="none" strokeWidth="1.5" /><line x1="0" x2="200" y1="76" y2="76" className="gl dash" /></svg>,
  compare: () => <><Row head cells={["", "Co. A", "Co. B", "Co. C"]} />{[["P/E", "14.2", "17.8", "11.5"], ["ROE", "18%", "21%", "16%"], ["Score", "78", "72", "69"]].map((r) => <Row key={r[0]} cells={r} />)}
    <svg className="pg-svg short" viewBox="0 0 200 40"><polyline className="l1" points="0,30 40,24 80,26 120,16 160,12 200,8" fill="none" strokeWidth="1.8" /><polyline className="l2" points="0,32 40,30 80,22 120,24 160,18 200,18" fill="none" strokeWidth="1.8" /><polyline className="l3" points="0,26 40,28 80,32 120,28 160,26 200,24" fill="none" strokeWidth="1.8" /></svg></>,
  watchlist: () => <><div className="pg-hd"><b>My list</b><span>Long term</span></div>{[["Company A", "1,240.50", "+1.2%", "up"], ["Company B", "385.10", "-0.6%", "dn"], ["Company C", "2,910.00", "+0.4%", "up"]].map((r) => <div key={r[0]} className="pg-li"><span>{r[0]}</span><i>{r[1]}</i><em className={r[3]}>{r[2]}</em></div>)}<p className="pg-note">Note: review after results</p></>,
  portfolio: () => <div className="pg-two"><svg className="pg-donut" viewBox="0 0 64 64"><circle cx="32" cy="32" r="22" fill="none" strokeWidth="10" className="d0" /><circle cx="32" cy="32" r="22" fill="none" strokeWidth="10" className="d1" strokeDasharray="60 138" transform="rotate(-90 32 32)" /><circle cx="32" cy="32" r="22" fill="none" strokeWidth="10" className="d2" strokeDasharray="38 138" strokeDashoffset="-60" transform="rotate(-90 32 32)" /><circle cx="32" cy="32" r="22" fill="none" strokeWidth="10" className="d3" strokeDasharray="24 138" strokeDashoffset="-98" transform="rotate(-90 32 32)" /></svg>
    <div className="pg-bars">{[["Banks", 80], ["IT", 56], ["Energy", 40], ["Other", 28]].map(([l, w]) => <div key={l as string}><span>{l}</span><i><b style={{ width: `${w}%` }} /></i></div>)}</div></div>,
  alerts: () => <div className="pg-form"><label>Alert when<span className="pg-in">Price crosses above</span></label><label>Level<span className="pg-in">1,500.00</span></label><label>Notify me<span className="pg-in">In the app</span></label><span className="pg-btn">Create alert</span></div>,
  news: () => <><Tabs items={["All", "Filings", "My watchlist"]} />{[["Company A reports quarterly results", "Filing · 2h"], ["Company B announces a board meeting date", "Announcement · 5h"], ["Sector update: input costs ease", "Market · 1d"]].map((r) => <div key={r[0]} className="pg-news"><b>{r[0]}</b><small>{r[1]}</small></div>)}</>,
  forum: () => <>{[["Q", "How do investors read a rising debt-to-equity ratio?", "3 replies"], ["A", "It depends on the sector. Compare it with peers first.", "2 likes"]].map((r, i) => <div key={i} className={"pg-post" + (i ? " alt" : "")}><span className="pg-av">{r[0]}</span><div><p>{r[1]}</p><small>{r[2]}</small></div></div>)}</>,
  etf: () => <><Row head cells={["ETF", "1Y", "Risk", "Type"]} />{[["Index ETF A", "+9.4%", "Mid", "Broad"], ["Sector ETF B", "+12.1%", "High", "Sector"], ["Theme ETF C", "+6.8%", "Mid", "Theme"]].map((r) => <Row key={r[0]} cells={r} />)}</>,
  funds: () => <><Tabs items={["Equity", "Debt", "Hybrid"]} /><Row head cells={["Fund", "3Y", "TER", "Size"]} />{[["Fund A", "14.2%", "0.8%", "₹12k cr"], ["Fund B", "11.6%", "1.1%", "₹4k cr"], ["Fund C", "12.9%", "0.9%", "₹7k cr"]].map((r) => <Row key={r[0]} cells={r} />)}</>,
  fundnav: () => <><div className="pg-hd"><b>NAV, rebased to 100</b><span>5 years</span></div><svg className="pg-svg" viewBox="0 0 200 70"><line x1="0" x2="200" y1="18" y2="18" className="gl" /><line x1="0" x2="200" y1="36" y2="36" className="gl" /><line x1="0" x2="200" y1="54" y2="54" className="gl" />
    <polyline className="l2" points="0,58 25,54 50,56 75,46 100,48 125,38 150,34 175,26 200,22" fill="none" strokeWidth="1.8" /><polyline className="l1" points="0,58 25,56 50,52 75,50 100,42 125,40 150,30 175,28 200,14" fill="none" strokeWidth="1.8" /></svg>
    <div className="pg-leg"><span><i className="k1" />Fund A</span><span><i className="k2" />Category average</span></div></>,
  forecast: () => <><div className="pg-hd"><b>Profit, yearly</b><span>Sample</span></div><svg className="pg-svg" viewBox="0 0 200 76"><line x1="0" x2="200" y1="20" y2="20" className="gl" /><line x1="0" x2="200" y1="40" y2="40" className="gl" /><line x1="0" x2="200" y1="60" y2="60" className="gl" />
    <polygon className="band" points="120,34 160,26 200,14 200,44 160,40 120,34" /><polyline className="ln" points="0,60 20,56 40,58 60,48 80,50 100,40 120,34" fill="none" strokeWidth="1.8" /><polyline className="ln fc" points="120,34 160,33 200,29" fill="none" strokeWidth="1.8" />
    <line x1="120" x2="120" y1="6" y2="70" className="gl dash" /></svg><div className="pg-leg"><span><i className="k5" />Reported</span><span><i className="k5 dot" />Indicative range</span></div></>,
  calc: () => <div className="pg-two"><div className="pg-form tight"><label>Growth<span className="pg-in">12%</span></label><label>Discount<span className="pg-in">10%</span></label><label>Years<span className="pg-in">10</span></label></div><div className="pg-result"><small>Sample result</small><b>₹ 1,180</b><small>per share</small></div></div>,
};

const BANNERS = [
  { k: "silver", name: "Silver", tag: "Score and full screener", points: ["FinLit score and five pillars on every stock", "Full screener: 160+ filters and CSV download", "Watchlists with notes: 3 lists, 30 stocks", "Portfolio scorecard and downloads"] },
  { k: "gold", name: "Gold", tag: "Most depth", points: ["FinLit Prism, an advanced financial-health rating", "FinLit model filters in the screener", "Profit and revenue outlook", "Compare up to 4 companies, up to 50 watchlists"] },
] as const;

export function PlatformGrid() {
  const [tier, setTier] = useState<TierFilter>("all");
  const cards = filterByTier(PLATFORM_CARDS, tier);
  return (
    <section className="sec hh-sec" id="platform" aria-labelledby="pg-title"><div className="wrap">
      <Reveal className="hh-head"><div className="hh-kicker">Explore our platform</div><h2 id="pg-title">Everything you need to invest smarter</h2><p>Free, Silver and Gold plans. From finding the right stocks to analysing, tracking and discussing ideas, all in one place.</p></Reveal>
      <div className="pg-plans">
        {BANNERS.map((b) => (
          <div key={b.k} className={"pg-plan " + b.k} style={{ "--tc": `var(${TIER[b.k].tc})` } as CSSProperties}>
            <TierEmblem tier={b.k} />
            <div className="pg-plan-b">
              <div className="pg-plan-t"><h3><Link to={PLAN_LINK[b.k]} className="pg-plan-link">{b.name} plan</Link></h3><span className="pg-plan-tag">{b.tag}</span></div>
              <ul>{b.points.map((p) => <li key={p}><Icon name="check" />{p}</li>)}</ul>
              <span className="pg-plan-cta">See the {b.name} plan <Icon name="arrow" /></span>
            </div>
          </div>
        ))}
      </div>
      <div className="pg-filter" role="group" aria-label="Show features by plan">
        {TIER_FILTERS.map((f) => <button key={f.k} type="button" className={"pg-chip" + (tier === f.k ? " on" : "")} aria-pressed={tier === f.k} onClick={() => setTier(f.k)}>{f.label}</button>)}
        <span className="pg-count" role="status">{cards.length} of {PLATFORM_CARDS.length} features</span>
      </div>
      <ul className="pg" aria-label="Platform features">
        {cards.map((c) => { const t = PLAN_TIER[c.plan]; return (
          <li key={c.n} className="pg-card" style={{ "--ac": c.accent } as CSSProperties}>
            <div className="pg-top"><span className="pg-n">{c.n}</span>
              {t === "basic" ? <span className="pg-badge free"><Icon name={TIER.basic.ic} />{c.plan}</span>
                : <Link to={PLAN_LINK[t]} className={"pg-badge " + t} aria-label={`${TIER[t].n} plan: see it on the Plans page`}><Icon name={TIER[t].ic} />{c.plan}</Link>}</div>
            <h3><Link to={c.to} className="pg-link">{c.title} <Icon name="arrow" /></Link></h3>
            <p className="pg-d">{c.desc}</p>
            <div className="pg-prev" aria-hidden="true">{PREVIEWS[c.preview]()}</div>
            <ul className="pg-ticks">{c.bullets.map((b) => <li key={b}><Icon name="check" />{b}</li>)}</ul>
            <Link to={c.to} className="pg-cta">{c.cta} <Icon name="arrow" /></Link>
          </li>); })}
      </ul>
      <p className="hh-fine">Sample figures in the previews are for illustration only. Information only, not investment advice.</p>
    </div></section>
  );
}
