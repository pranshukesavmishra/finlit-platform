import { lazy, Suspense, useEffect, useState } from "react";
import { Link } from "react-router";
import { COMPANY, PHILOSOPHY, PRICING, SERVICES, TESTIMONIAL } from "../content/site";
import { FAQ_GROUPS } from "../content/faq";
import { NotifyForm } from "../components/NotifyForm";
import { Icon } from "../lib/icons";
import { Reveal, CountUp } from "../components/Reveal";
import { useEnquiry } from "../components/Enquiry";
import { useSummary } from "../lib/api";
import { useDocTitle } from "../lib/title";
import { nf } from "../lib/format";
const HeroCanvas = lazy(() => import("../components/HeroCanvas").then((m) => ({ default: m.HeroCanvas })));
function LateCanvas() { const [on, setOn] = useState(false); useEffect(() => { const id = (window as unknown as { requestIdleCallback?: (f: () => void) => number }).requestIdleCallback; const t = id ? id(() => setOn(true)) : window.setTimeout(() => setOn(true), 600); return () => { if (!id) clearTimeout(t); }; }, []); return on ? <Suspense fallback={null}><HeroCanvas /></Suspense> : null; }
import { ServiceArt, SERVICE_ART } from "../components/Art";
import { PlansBand } from "./Plans";
import { useAuth } from "../lib/auth";

function LiveTerminal() {
  const { data: s } = useSummary("RELIANCE");
  if (!s) return <div className="term"><div className="skeleton" style={{ height: 240 }} /></div>;
  const colors: Record<string, string> = { quality: "--p-quality", growth: "--p-growth", profitability: "--p-profit", balance: "--p-balance", technical: "--p-tech" };
  const c = s.sparkline.c, mn = Math.min(...c), mx = Math.max(...c);
  const d = c.map((p, i) => `${i ? "L" : "M"}${(i / (c.length - 1)) * 300},${60 - ((p - mn) / (mx - mn || 1)) * 54}`).join("");
    return (
    <Link to="/stocks/RELIANCE" className="term" style={{ display: "block", textDecoration: "none", color: "inherit" }} aria-label="Open the live example report">
      <span className="float-chip a"><Icon name="check" />Checked before publishing</span>
      <span className="float-chip b"><Icon name="spark" />Updated daily</span>
      <div className="term-h"><div><b>{s.profile.name}</b> <span className="tk">{s.profile.nse}</span></div><span className={"chip " + ((s.quote.changePct ?? 0) >= 0 ? "up" : "down")}>₹{nf(s.quote.price ?? 0)}</span></div>
      <div className="term-score">
        <div className="term-dial"><svg viewBox="0 0 140 140" aria-hidden="true">
          <defs><linearGradient id="tg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="var(--gold-2)" /><stop offset="1" stopColor="var(--gold-deep)" /></linearGradient><radialGradient id="tdisc" cx=".5" cy=".35" r=".8"><stop offset="0" stopColor="var(--gold)" stopOpacity=".22" /><stop offset="1" stopColor="var(--s1)" stopOpacity="0" /></radialGradient></defs>
          <circle cx="70" cy="70" r="52" fill="url(#tdisc)" />
          {Array.from({ length: 60 }, (_, i) => { const a = (i / 60) * Math.PI * 2 - Math.PI / 2, lit = i < Math.round(((s.score.overall ?? 0) / 100) * 60), r1 = 63, r2 = i % 5 === 0 ? 57 : 59.5; return <line key={i} x1={70 + r1 * Math.cos(a)} y1={70 + r1 * Math.sin(a)} x2={70 + r2 * Math.cos(a)} y2={70 + r2 * Math.sin(a)} stroke={lit ? "var(--gold)" : "var(--border-strong)"} strokeWidth={i % 5 === 0 ? 1.6 : 1} opacity={lit ? 0.95 : 0.7} />; })}
          <circle cx="70" cy="70" r="49" fill="none" stroke="var(--s3)" strokeWidth="7" />
          <circle cx="70" cy="70" r="49" fill="none" stroke="var(--gold)" strokeWidth="12" opacity=".18" strokeLinecap="round" strokeDasharray={`${(2 * Math.PI * 49 * (s.score.overall ?? 0)) / 100} 400`} transform="rotate(-90 70 70)" />
          <circle className="ring-in" cx="70" cy="70" r="49" fill="none" stroke="url(#tg)" strokeWidth="7" strokeLinecap="round" strokeDasharray={`${(2 * Math.PI * 49 * (s.score.overall ?? 0)) / 100} 400`} transform="rotate(-90 70 70)" />
          <text x="70" y="70" dy=".36em" textAnchor="middle" fontFamily="Newsreader Variable, Newsreader, Georgia, serif" fontWeight="300" fontSize="40" fill="var(--text)">{s.score.overall}</text>
          <text x="70" y="97" textAnchor="middle" fontSize="7.5" letterSpacing="1.6" fill="var(--faint)" fontFamily="IBM Plex Sans, sans-serif">OUT OF 100</text>
        </svg></div>
        <div className="term-bars">{s.score.pillars.map((p) => <div key={p.key} style={{ "--pc": `var(${colors[p.key]})` } as React.CSSProperties}><span>{p.label}</span><i><b style={{ width: `${p.score ?? 0}%` }} /></i><span>{p.score}</span></div>)}</div>
      </div>
      <div className="term-spark"><svg viewBox="0 0 300 64" preserveAspectRatio="none"><path d={d} fill="none" stroke="var(--gold)" strokeWidth="2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" /></svg></div>
      <p className="faint" style={{ margin: "10px 0 0", fontSize: 12 }}>Live example · opens the full report →</p>
    </Link>
  );
}

const PLATFORM: { to: string; icon: string; t: string; d: string; tier: "Free" | "Silver" | "Gold"; math?: React.ReactNode }[] = [
  { to: "/research", icon: "search", t: "Stock research", d: "A report for every listed company: statements, ratios, peers, ownership, price and filings.", tier: "Free" },
  { to: "/screener", icon: "table", t: "Screener", d: "Describe the company you want as a few rules, and we return every one that satisfies all of them. 160+ filters, live in milliseconds.", tier: "Free",
    math: <>{"{"} P/E <i>&lt;</i> 20 {"}"} <i>AND</i> {"{"} ROE <i>&gt;</i> 15% {"}"} <i>AND</i> {"{"} D/E <i>&lt;</i> 0.5 {"}"}<br /><i>→</i> <b>matches</b> out of 2,800+ companies</> },
  { to: "/compare", icon: "compare", t: "Compare", d: "Put two to four companies side by side, with charts and the five-pillar view.", tier: "Free" },
  { to: "/watchlist", icon: "wallet", t: "Watchlists", d: "Named lists with notes and price targets, bucketed by industry, size or FinLit band.", tier: "Silver" },
  { to: "/holdings", icon: "pie", t: "Portfolio tracker", d: "Value, profit and loss, allocation and a health read of what you own. Import from CSV.", tier: "Silver" },
  { to: "/alerts", icon: "bell", t: "Alerts", d: "Be told when a price, RSI, score, ratio, result or filing crosses the line you set.", tier: "Free" },
  { to: "/news", icon: "notes", t: "News", d: "Market news and company-specific updates: filings, announcements and results, filtered by company, category or your watchlist.", tier: "Free" },
];
function Faq() {
  return (
    <section className="sec" id="faq"><div className="wrap faq-w">
      <Reveal className="sec-h"><div className="eyebrow">Questions</div><h2>Good things to <em>know first</em></h2><p>Tap a question to read the answer.</p></Reveal>
      {FAQ_GROUPS.map((g) => <div key={g.title}><h3 className="faq-g">{g.title}</h3><div className="faq">{g.items.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}</div></div>)}
    </div></section>
  );
}
function Platform() {
  return (
    <section className="sec alt" id="platform"><div className="wrap">
      <Reveal className="sec-h"><div className="eyebrow">The platform</div><h2>Seven tools for <em>your research</em></h2><p>Everything you need to find, follow and track companies, in one place.</p></Reveal>
      <div className="plat">{PLATFORM.map((x, i) => <Reveal key={x.t} delay={i * 50}><Link to={x.to} className="plat-t"><span className="plat-i"><Icon name={x.icon} /></span><span className={"tier-tag " + x.tier.toLowerCase()}>{x.tier === "Free" ? "Free account" : x.tier}</span><h3>{x.t}</h3><p>{x.d}</p>{x.math && <div className="plat-math" aria-label="Example screen">{x.math}</div>}<span className="plat-m">Open <Icon name="arrow" /></span></Link></Reveal>)}</div>
          <Reveal><div className="split" role="note" aria-label="Fundamental and technical analysis">
        <div><h3><span className="mark" style={{ background: "var(--p-quality)" }} />Fundamental</h3><p>The business itself: quality, growth, profitability and balance sheet, from the company's statements.</p></div>
        <div><h3><span className="mark" style={{ background: "var(--p-tech)" }} />Technical</h3><p>The share price only: trend, momentum and moving averages, from the price chart.</p></div>
        <p className="split-note"><b>Two different lenses, never blended.</b> Fundamental and technical scores are shown separately, so you can read each on its own.</p>
      </div></Reveal>
    </div></section>
  );
}

export function Home() {
  useDocTitle("Invest with clarity, not noise", "FinLit Ventures: research-led investing, portfolio reviews and financial planning, with a research report for every listed Indian stock.");
  const enquire = useEnquiry();
  const { user } = useAuth();
  useEffect(() => { if (location.hash === "#faq") setTimeout(() => document.getElementById("faq")?.scrollIntoView({ behavior: "smooth" }), 200); }, []);   // /faq lands here
  return (
    <>
      <section className="hero-home">
        <div className="aurora" /><div className="grid-fade" /><LateCanvas />
        <div className="wrap hero-cols">
          <div>
            <div className="eyebrow">Research · Portfolios · Investing</div>
            <h1>Invest with <em>clarity</em>, not noise.</h1>
            <p className="lede-xl">A research report for every listed Indian stock, honest portfolio reviews and financial planning, from people who put their own capital behind their ideas.</p>
            <div className="cta-row">{user ? <Link className="btn primary lg" to="/dashboard">Open your dashboard <Icon name="arrow" /></Link> : <Link className="btn primary lg" to="/login?mode=signup">Create free account <Icon name="arrow" /></Link>}<Link className="btn lg" to="/research">Explore stock research</Link></div>
            <div className="trustrow"><span><Icon name="quality" />Independent research</span><span><Icon name="check" />Every number checked before publishing</span><span><Icon name="lock" />No passwords stored</span></div>
          </div>
          <LiveTerminal />
        </div>
      </section>

      <div className="marq" aria-hidden="true"><div>{[...PHILOSOPHY, ...PHILOSOPHY].map((p, i) => <span key={i}>{p}</span>)}</div></div>

      <section className="tagline" aria-label="Our promise"><div className="wrap"><Reveal><p><span>Quantify the market</span><span className="x" aria-hidden="true">×</span><span>Research deeper</span><span className="x" aria-hidden="true">×</span><span>Track what matters</span></p></Reveal></div></section>

      <section className="wrap" id="coming-soon" aria-labelledby="soonTitle"><Reveal><div className="soon">
        <div><div className="eyebrow">Coming soon</div><h2 id="soonTitle">Be the first to know</h2>
          <p>We are adding more. Leave your email and we will tell you the day each one goes live. No spam, and you can ask us to stop at any time.</p>
          <ul><li>Equity research reports</li><li>Online payments</li><li>Newsletter</li><li>Meet the team</li></ul></div>
        <div><NotifyForm source="home" /><p className="fine">Equity research reports are subject to the required licence and approvals.</p></div>
      </div></Reveal></section>

      <section className="statstrip"><div className="wrap">
        {[[<CountUp to={5700} suffix="+" />, "listed stocks covered"], [<CountUp to={5} />, "pillars scored on every stock"], [<>&lt;<CountUp to={1} /> s</>, "to open a report"], [<CountUp to={169} />, "filters in the screener"]].map(([v, k], i) => <Reveal key={i} delay={i * 80}><div className="ss"><b>{v}</b><span>{k as string}</span></div></Reveal>)}
      </div></section>
      <Platform />

      <section className="sec"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">What we do</div><h2>Five ways we <em>help you invest</em></h2><p>From your first investment to a global portfolio.</p></Reveal>
        <div className="cards3">
          {SERVICES.map((s, i) => <Reveal key={s.name} delay={i * 70}><div className="feat" style={{ "--ac": `var(--c${(i % 4) + 1})` } as React.CSSProperties}><ServiceArt kind={SERVICE_ART[i]} /><span className="num">{s.n}</span><div className="fi"><Icon name={s.icon} /></div><h3>{s.name}</h3><p className="prop">{s.proposition}</p><p>{s.desc}</p></div></Reveal>)}
          <Reveal delay={350}><div className="feat" style={{ "--ac": "var(--gold)", display: "grid", alignContent: "center" } as React.CSSProperties}><h3>First session</h3><div className="price-c best" style={{ textAlign: "left", border: 0, background: "none", padding: 0 }}><div className="p">{PRICING[0].price}</div><div className="n">{PRICING[0].note}</div></div><button className="btn primary" style={{ marginTop: 14 }} onClick={() => enquire()}>Book now</button></div></Reveal>
        </div>
      </div></section>

      <section className="sec"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">Why it feels different</div><h2>Research you can <em>see</em> and trust</h2><p>Every report is built the same way, checked the same way and explained in plain English.</p></Reveal>
        <div className="bento">
          <Reveal className="bt b1"><div className="spot"><h3>One score, five pillars</h3><p>Quality, growth, profitability, balance sheet and price trend, each scored 0 to 100 and shown in one glance.</p>
            <svg className="bt-art" viewBox="0 0 300 130" aria-hidden="true">{[["Quality", "--p-quality", 56], ["Growth", "--p-growth", 44], ["Profitability", "--p-profit", 51], ["Balance sheet", "--p-balance", 75], ["Technical", "--p-tech", 31]].map(([l, c, v], i) => <g key={c as string}><text x="0" y={i * 25 + 13} fontSize="11" fill="var(--muted)">{l}</text><rect x="92" y={i * 25 + 4} width="200" height="12" rx="6" fill="var(--s3)" /><rect className="bar-in" style={{ animationDelay: `${i * 120}ms` }} x="92" y={i * 25 + 4} width={(v as number) * 2} height="12" rx="6" fill={`var(${c})`} /></g>)}</svg></div></Reveal>
          <Reveal className="bt b2" delay={80}><div className="spot"><h3>Checked before it is published</h3><p>Numbers that fail our checks never reach the page.</p>
            <ul className="ticks">{["Statements reconcile", "Ratios re-priced at today's quote", "Dates and periods aligned", "Sources recorded"].map((t, i) => <li key={t} style={{ animationDelay: `${i * 160}ms` }}><Icon name="check" />{t}</li>)}</ul></div></Reveal>
          <Reveal className="bt b3" delay={140}><div className="spot"><h3>Open in under a second</h3><p>Reports are prepared ahead of time, so nothing makes you wait.</p>
            <div className="speed"><b>&lt; 1</b><span>second to the first summary</span><i><u /></i></div></div></Reveal>
          <Reveal className="bt b4" delay={200}><div className="spot"><h3>Plain English, with the working shown</h3><p>Every ratio has a one-line meaning and a link to how it is calculated.</p>
            <svg className="bt-art" viewBox="0 0 300 110" aria-hidden="true"><path className="draw" d="M0 90 40 74 80 80 120 50 160 58 200 28 240 36 300 8" fill="none" stroke="var(--gold)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /><path d="M0 90 40 74 80 80 120 50 160 58 200 28 240 36 300 8V110H0z" fill="url(#bf)" /><defs><linearGradient id="bf" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--gold)" stopOpacity=".35" /><stop offset="1" stopColor="var(--gold)" stopOpacity="0" /></linearGradient></defs></svg></div></Reveal>
        </div>
      </div></section>

      <PlansBand id="pricing" compact />

      <section className="sec alt"><div className="wrap">
        <Reveal className="quote"><div className="eyebrow">Client experience</div><blockquote>“{TESTIMONIAL.quote}”</blockquote><div className="muted">{TESTIMONIAL.name}</div></Reveal>
      </div></section>

      <Faq />

      <section className="sec"><div className="wrap"><Reveal><div className="cta-band"><h2>Let's talk about your portfolio</h2><p>Tell us where you are. We'll tell you what we'd look at first. {COMPANY.disclaimer}</p><div className="cta-row" style={{ justifyContent: "center" }}><button className="btn primary lg" onClick={() => enquire()}>Get in touch</button><Link className="btn lg" to="/services">View services & pricing</Link></div></div></Reveal></div></section>
    </>
  );
}
