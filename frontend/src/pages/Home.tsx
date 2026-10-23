import { useEffect, useMemo } from "react";
import { Link } from "react-router";
import { COMPANY, SERVICES } from "../content/site";
import { FAQ_GROUPS } from "../content/faq";
import { NotifyForm } from "../components/NotifyForm";
import { Icon } from "../lib/icons";
import { Reveal } from "../components/Reveal";
import { useEnquiry } from "../components/Enquiry";
import { useSummary, useSearchIndex, type Summary } from "../lib/api";
import { useDocTitle } from "../lib/title";
import { nf } from "../lib/format";
import { PlansBand } from "./Plans";
import { useAuth } from "../lib/auth";
import "../styles/human-home.css";

const SAMPLE = "RELIANCE";
const PILLAR_VAR: Record<string, string> = { quality: "--p-quality", growth: "--p-growth", profitability: "--p-profit", balance: "--p-balance", technical: "--p-tech" };
const inr = (n: number) => n.toLocaleString("en-IN");

/** A real score card for a real stock, read from the same API the report page uses. */
function ScoreCard({ s }: { s?: Summary }) {
  if (!s) return <div className="hh-card" aria-busy="true"><div className="skeleton" style={{ height: 300 }} /></div>;
  const o = s.score.overall ?? 0, circ = 2 * Math.PI * 46, up = (s.quote.changePct ?? 0) >= 0;
  return (
    <Link to={`/stocks/${SAMPLE}`} className="hh-card" aria-label={`Open the full ${s.profile.name} report`}>
      <div className="hh-card-top"><span className="hh-stamp">A real report</span><span className="hh-tk">{s.profile.nse ?? SAMPLE}</span></div>
      <div className="hh-card-name"><b>{s.profile.name}</b><span className={up ? "up" : "down"}>₹{nf(s.quote.price ?? 0)}{s.quote.changePct != null && <> · {up ? "+" : ""}{s.quote.changePct.toFixed(2)}%</>}</span></div>
      <div className="hh-card-score">
        <svg viewBox="0 0 110 110" role="img" aria-label={`FinLit score ${o} out of 100`}>
          <circle cx="55" cy="55" r="46" fill="none" stroke="var(--s3)" strokeWidth="8" />
          <circle cx="55" cy="55" r="46" fill="none" stroke="var(--gold)" strokeWidth="8" strokeLinecap="butt" strokeDasharray={`${(circ * o) / 100} ${circ}`} transform="rotate(-90 55 55)" />
          <text x="55" y="58" textAnchor="middle" className="hh-dial-n">{o}</text>
          <text x="55" y="76" textAnchor="middle" className="hh-dial-s">out of 100</text>
        </svg>
        <ul className="hh-bars">{s.score.pillars.map((p) => <li key={p.key} style={{ "--pc": `var(${PILLAR_VAR[p.key] ?? "--gold"})` } as React.CSSProperties}><span>{p.label}</span><i><b style={{ width: `${p.score ?? 0}%` }} /></i><em>{p.score ?? "–"}</em></li>)}</ul>
      </div>
      <p className="hh-card-foot">Taken live from the same data as the full report. Open it →</p>
    </Link>
  );
}

const STEPS: [string, string][] = [
  ["Search a company", "Type a name or an NSE/BSE symbol. Every listed company has a page."],
  ["Read the score", "One number out of 100, split into five pillars so you can see what is pulling it up or down."],
  ["Check the working", "Statements, ratios, peers, ownership and filings are on the same page. Each ratio explains itself."],
  ["Keep an eye on it", "Add it to a watchlist or set an alert on price, RSI, score, a ratio or a new filing."],
];

const PLATFORM: { to: string; t: string; d: string; tier: "Free" | "Silver" | "Gold"; math?: boolean }[] = [
  { to: "/research", t: "Stock research", d: "A report for every listed company: statements, ratios, peers, ownership, price and filings.", tier: "Free" },
  { to: "/screener", t: "Screener", d: "Write the company you want as a few rules. You get every company that passes all of them. 160+ filters.", tier: "Free", math: true },
  { to: "/compare", t: "Compare", d: "Two to four companies side by side, with charts and the five-pillar view.", tier: "Free" },
  { to: "/watchlist", t: "Watchlists", d: "Named lists with notes and price targets, grouped by industry, size or FinLit band.", tier: "Silver" },
  { to: "/holdings", t: "Portfolio tracker", d: "Value, profit and loss, allocation and a health read of what you own. Import from CSV.", tier: "Silver" },
  { to: "/alerts", t: "Alerts", d: "Told when a price, RSI, score, ratio, result or filing crosses the line you set.", tier: "Free" },
  { to: "/news", t: "News", d: "Market news and company updates: filings, announcements and results. Filter by company, category or your watchlist.", tier: "Free" },
  { to: "/forum", t: "Discussion forums", d: "Talk about listed companies with other investors. Information and opinion only, moderated, never tips.", tier: "Free" },
  { to: "/etfs", t: "ETFs", d: "Every exchange-traded fund: price, returns over 1 month to 5 years, volatility and worst fall, with a chart and plain-words terms.", tier: "Free" },
  { to: "/funds", t: "Mutual funds", d: "Every scheme from AMFI: NAV, returns, risk, category and plan, with a chart and side-by-side compare. Information only.", tier: "Free" },
  { to: "/graphs", t: "Graph Studio", d: "Put several graphs side by side: pick companies and measures, choose a chart type for each, and see patterns and correlation.", tier: "Free" },
  { to: "/dcf", t: "DCF calculator", d: "Work out what a business is worth from its future free cash flow: load a company's figures, set growth and discount rates, and see the value per share, the price after your margin of safety, and what today's price already assumes.", tier: "Gold" },
];

function Platform({ total }: { total: number | null }) {
  return (
    <section className="sec hh-sec" id="platform"><div className="wrap">
      <Reveal className="hh-head"><div className="hh-kicker">The tools</div><h2>Twelve tools, one login</h2><p>Use them in any order. Most people start with a report and end up in the screener.</p></Reveal>
      <div className="plat">{PLATFORM.map((x, i) => (
        <Link key={x.t} to={x.to} className="plat-t">
          <span className="plat-n">{String(i + 1).padStart(2, "0")}</span><span className={"tier-tag " + x.tier.toLowerCase()}>{x.tier === "Free" ? "Free account" : x.tier}</span>
          <h3>{x.t}</h3><p>{x.d}</p>
          {x.math && <div className="plat-math" aria-label="Example screen">{"{"} P/E <i>&lt;</i> 20 {"}"} <i>AND</i> {"{"} ROE <i>&gt;</i> 15% {"}"} <i>AND</i> {"{"} D/E <i>&lt;</i> 0.5 {"}"}<br /><i>→</i> <b>matches</b> out of {total ? <>{inr(total)} companies</> : "every listed company"}</div>}
          <span className="plat-m">Open <Icon name="arrow" /></span>
        </Link>))}
      </div>
      <div className="split" role="note" aria-label="Fundamental and technical analysis">
        <div><h3><span className="mark" style={{ background: "var(--p-quality)" }} />Fundamental</h3><p>The business itself: quality, growth, profitability and balance sheet, read from the company's statements.</p></div>
        <div><h3><span className="mark" style={{ background: "var(--p-tech)" }} />Technical</h3><p>The share price only: trend, momentum and moving averages, read from the price chart.</p></div>
        <p className="split-note"><b>These are two different lenses and we do not blend them.</b> Each gets its own score so you can read it on its own.</p>
      </div>
    </div></section>
  );
}

function Method({ s }: { s?: Summary }) {
  const strength = s?.strengths?.[0], watch = s?.watchouts?.[0];
  return (
    <section className="sec hh-sec" id="method"><div className="wrap">
      <Reveal className="hh-head"><div className="hh-kicker">How the score is made</div><h2>The number, and what is behind it</h2><p>A score is only useful if you can check it. So we show the working.</p></Reveal>
      <div className="hh-method">
        <ol className="hh-notes">
          <li><b>Five pillars.</b> Quality, growth, profitability, balance sheet, and price trend. Each is scored from 0 to 100.</li>
          <li><b>Fixed yardsticks.</b> Inside a pillar, each ratio is compared with set thresholds, the same for every company in the model. Nobody adjusts them for a stock we like.</li>
          <li><b>Missing data stays missing.</b> If a pillar cannot be scored from the filings we have, the report says so. It does not fill the gap with a guess.</li>
          <li><b>The score is a summary, not a verdict.</b> It does not tell you to buy or sell anything. {COMPANY.name} is not registered with SEBI or AMFI.</li>
        </ol>
        <figure className="hh-excerpt">
          <figcaption>From the {s ? s.profile.name : "sample"} report{s?.meta?.generatedAt ? `, generated ${new Date(s.meta.generatedAt).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}` : ""}</figcaption>
          {s ? <>
            {s.thesis && <blockquote>{s.thesis}</blockquote>}
            {strength && <p><span className="hh-tag good">Strength</span> <b>{strength.title}.</b> {strength.text}</p>}
            {watch && <p><span className="hh-tag warn">Watch-out</span> <b>{watch.title}.</b> {watch.text}</p>}
            {!s.thesis && !strength && !watch && <p>Open the report to read the notes.</p>}
          </> : <div className="skeleton" style={{ height: 160 }} />}
          <Link to={`/stocks/${SAMPLE}`} className="hh-link">Read the full report <Icon name="arrow" /></Link>
        </figure>
      </div>
    </div></section>
  );
}

function Faq() {
  return (
    <section className="sec hh-sec" id="faq"><div className="wrap faq-w">
      <Reveal className="hh-head"><div className="hh-kicker">Questions</div><h2>Questions people ask first</h2><p>Tap a question to open the answer.</p></Reveal>
      {FAQ_GROUPS.map((g) => <div key={g.title}><h3 className="faq-g">{g.title}</h3><div className="faq">{g.items.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}</div></div>)}
    </div></section>
  );
}

export function Home() {
  useDocTitle("Research on every listed Indian stock", "FinLit Ventures: a research report and a 0 to 100 score for every listed Indian stock, a screener, watchlists and alerts. Information only, not investment advice.");
  const enquire = useEnquiry();
  const { user } = useAuth();
  const { data: s } = useSummary(SAMPLE);
  const { data: idx } = useSearchIndex(true);
  const counts = useMemo(() => idx ? { all: idx.rows.length, ready: idx.rows.filter((r) => r[3]).length } : null, [idx]);
  useEffect(() => { if (location.hash === "#faq") setTimeout(() => document.getElementById("faq")?.scrollIntoView({ behavior: "smooth" }), 200); }, []);   // /faq lands here
  const notify = () => { const el = document.getElementById("coming-soon"); el?.scrollIntoView({ behavior: "smooth", block: "center" }); setTimeout(() => el?.querySelector<HTMLInputElement>("input[type=email]")?.focus({ preventScroll: true }), 500); };
  return (
    <div className="hh">
      <section className="tagline" aria-label="Our promise"><div className="wrap"><p><span>Quantify the market</span><span className="x" aria-hidden="true">×</span><span>Research deeper</span><span className="x" aria-hidden="true">×</span><span>Track what matters</span></p></div></section>

      <section className="hh-hero">
        <div className="wrap hh-hero-cols">
          <div>
            <div className="hh-kicker">Equity research · India</div>
            <h1>A research report for every listed Indian stock.</h1>
            <p className="hh-lede">Each report has a score out of 100, the financial statements, ratios, peers, ownership and filings. You can see how every number was worked out. We also do portfolio reviews and financial planning.</p>
            <div className="cta-row">
              {user ? <Link className="btn primary lg" to="/dashboard">Open your dashboard <Icon name="arrow" /></Link> : <Link className="btn primary lg" to="/login?mode=signup">Create free account <Icon name="arrow" /></Link>}
              <Link className="btn lg" to="/research">Explore stock research</Link>
              <button type="button" className="btn lg" onClick={notify}><Icon name="bell" /> Notify me</button>
            </div>
            <p className="hh-fine">Information only. Not investment advice.</p>
          </div>
          <ScoreCard s={s} />
        </div>
      </section>

      <section className="wrap" id="coming-soon" aria-labelledby="soonTitle"><Reveal><div className="soon">
        <div><div className="hh-kicker">Coming soon</div><h2 id="soonTitle">Be the first to know</h2>
          <p>Leave your email and we will write to you the day each of these goes live. We will not send anything else, and you can ask us to stop at any time.</p>
          <ul><li>Equity research reports</li><li>Online payments</li><li>Newsletter</li><li>Meet the team</li></ul></div>
        <div><NotifyForm source="home" /><p className="fine">Equity research reports are subject to the required licence and approvals.</p></div>
      </div></Reveal></section>

      <section className="sec hh-sec" id="how"><div className="wrap">
        <Reveal className="hh-head"><div className="hh-kicker">How it works</div><h2>Four steps, no setup</h2></Reveal>
        <ol className="hh-steps">{STEPS.map(([t, d], i) => <li key={t}><span className="hh-n">{i + 1}</span><div><h3>{t}</h3><p>{d}</p></div></li>)}</ol>
        <dl className="hh-facts" aria-label="The index today">
          {counts && <><div><dt>Companies in the index</dt><dd>{inr(counts.all)}</dd></div><div><dt>With a full report</dt><dd>{inr(counts.ready)}</dd></div></>}
          <div><dt>Score pillars</dt><dd>5</dd></div><div><dt>Screener filters</dt><dd>160+</dd></div>
        </dl>
      </div></section>

      <Platform total={counts?.all ?? null} />
      <Method s={s} />

      <section className="sec hh-sec"><div className="wrap">
        <Reveal className="hh-head"><div className="hh-kicker">Beyond the website</div><h2>Five things we do with people</h2><p>The software does the digging. The conversation is for your own money and your own goals.</p></Reveal>
        <ol className="hh-svc">
          {SERVICES.map((x) => <li key={x.name}><span className="hh-n">{x.n}</span><div><h3>{x.name}</h3><p className="hh-prop">{x.proposition}</p><p>{x.desc}</p></div></li>)}
          <li className="hh-first"><span className="hh-n">₹</span><div><h3>Plans</h3><p>Basic is free. Silver and Gold open the deeper tools, from watchlists to the DCF calculator.</p><Link className="btn primary" to="/plans">Explore plans</Link></div></li>
        </ol>
      </div></section>

      <PlansBand id="pricing" compact />
      <Faq />

      <section className="sec hh-sec"><div className="wrap"><div className="hh-end"><h2>Want to talk about your portfolio?</h2><p>Tell us where you are. We will tell you what we would look at first.</p><div className="cta-row"><button className="btn primary lg" onClick={() => enquire()}>Get in touch</button><Link className="btn lg" to="/services">Services and pricing</Link></div><p className="hh-fine">{COMPANY.disclaimer}</p></div></div></section>
    </div>
  );
}
