import { Link } from "react-router";
import { useState } from "react";
import { FOUNDER, SERVICES } from "../content/site";
import { CompanySearch } from "../components/CompanySearch";
import { Icon } from "../lib/icons";
import { useSummary } from "../lib/api";
import { useDocTitle } from "../lib/title";
import { dateIN, nf, signed } from "../lib/format";
import { Reveal } from "../components/Reveal";
import { TIER, type Plan } from "../lib/ui";
import { useEnquiry } from "../components/Enquiry";
import "../styles/landing.css";

const SAMPLE = "RELIANCE";
function SampleReport() {
  const { data: report, isError, refetch } = useSummary(SAMPLE);
  const [view, setView] = useState<"snapshot" | "pillars">("snapshot");
  return <section className="landing-preview" aria-labelledby="sample-title">
    <div className="landing-preview-top"><span><i className="showcase-dot" />Inside FinLit</span><span>Sample · {SAMPLE}</span></div>
    <h2 id="sample-title">{report?.profile.name ?? "Reliance Industries Ltd"}</h2>
    {report ? <>
      <div className="landing-quote"><b>{report.quote.price == null ? "Price not available" : `₹${nf(report.quote.price)}`}</b><span className={report.quote.changePct == null || report.quote.changePct === 0 ? "neutral" : report.quote.changePct < 0 ? "down" : "up"}>{signed(report.quote.changePct)}</span></div>
      <div className="showcase-controls" role="group" aria-label="Sample report view">{(["snapshot", "pillars"] as const).map((v) => <button key={v} aria-pressed={view === v} onClick={() => setView(v)}>{v === "snapshot" ? "Company snapshot" : "Five pillars"}</button>)}</div>
      <div className="showcase-body">
        {view === "snapshot" ? <>
          <div className="landing-score"><div><span>FinLit score · five pillars</span><strong>{report.score.overall == null ? "Not rated" : <>{nf(report.score.overall, 0)}<small> / 100</small></>}</strong></div><span className="showcase-score-note">The score is a starting point.<br />The reasoning is inside.</span></div>
          <p className="landing-read">{report.thesis || "Financial statements, ratios and ownership, together in one report."}</p>
          <ul className="landing-findings">
            {report.strengths?.[0] && <li><Icon name="check" /><div><b>{report.strengths[0].title}</b><p>{report.strengths[0].text}</p></div></li>}
            {report.watchouts?.[0] && <li><Icon name="alert" /><div><b>{report.watchouts[0].title}</b><p>{report.watchouts[0].text}</p></div></li>}
          </ul>
        </> : <div className="showcase-pillars"><p>One score. Five different perspectives.</p>{report.score.pillars.map((pillar) => <div className="showcase-pillar" key={pillar.key}><span>{pillar.label}</span><b>{pillar.score == null ? "N/A" : `${nf(pillar.score, 0)} / 100`}</b><span className="showcase-pillar-track" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(100, pillar.score ?? 0))}%` }} /></span></div>)}</div>}
      </div>
      {report.meta.generatedAt && <p className="landing-caption">Report updated {dateIN(report.meta.generatedAt)}.</p>}
    </> : isError ? <div className="landing-unavailable"><p>The sample is unavailable right now. You can still search for a company.</p><button className="btn" onClick={() => refetch()}>Retry sample</button></div> : <div className="landing-skeleton" role="status">Loading the sample report…<div className="skeleton" /></div>}
    <Link className="landing-text-link" to={`/stocks/${SAMPLE}`}>View sample company report <Icon name="arrow" /></Link>
  </section>;
}

const PRODUCTS: { title: string; text: string; to: string; action: string; plan: Plan; icon: string }[] = [
  { title: "Company research", text: "Financial statements, ownership and peer comparisons. The figures behind the business, in one place.", to: "/research", action: "Explore company reports", plan: "basic", icon: "notes" },
  { title: "FinLit Prism", text: "A financial-health assessment with the factors behind each score, alongside separate short- and long-term technical views.", to: "/prism", action: "Explore FinLit Prism", plan: "gold", icon: "layers" },
  { title: "Stock screener", text: "Find companies by sector, valuation, growth and the factors you want to investigate.", to: "/screener", action: "Open the screener", plan: "basic", icon: "search" },
];
export function Home() {
  useDocTitle("Company research and financial planning", "Explore FinLit research products, company reports, screeners and financial planning conversations.");
  const enquire = useEnquiry();
  return <div className="landing landing-minimal landing-product-led">
    <section className="landing-hero wrap" aria-labelledby="landing-title">
      <div className="landing-intro"><p className="landing-eyebrow"><span className="showcase-dot" /> Independent thinking starts here</p><h1 id="landing-title">Know the business.<br /><em>See the bigger picture.</em></h1>
        <p className="landing-lede">Company research that shows its working. Financial planning that starts with you.</p>
        <div className="landing-hero-actions"><Link className="marketing-action marketing-action-primary" to="/platform">Explore products <Icon name="arrow" /></Link><Link className="marketing-action marketing-action-secondary" to="/plans">Compare plans <Icon name="arrow" /></Link></div>
      <p className="hero-service-link">Looking for a conversation? <a href="#services">Explore our services <Icon name="arrow" /></a></p></div><div className="landing-demo showcase-stage"><div className="showcase-orbit" aria-hidden="true" /><div className="showcase-stage-label"><span>THE FINLIT PERSPECTIVE</span><span>01 / COMPANY RESEARCH</span></div><SampleReport /></div>
    </section>
    <section className="product-collection" id="products" aria-labelledby="landing-products"><div className="wrap landing-section"><Reveal className="product-collection-head"><div className="landing-section-head"><p className="landing-eyebrow">A toolkit for your own thinking</p><h2 id="landing-products">Go beyond<br /><em>the headline.</em></h2><p>Meet the business. Understand its financial health. Find what deserves a closer look.</p></div><div className="product-collection-actions"><Link className="marketing-action marketing-action-primary" to="/platform">Explore products <Icon name="arrow" /></Link><Link className="marketing-action marketing-action-secondary" to="/plans">Compare plans <Icon name="arrow" /></Link></div></Reveal>
      <div className="landing-products">{PRODUCTS.map((x, i) => <Reveal key={x.to} delay={i * 70}><Link className="landing-product" data-tier={x.plan} to={x.to}><div className="product-card-top"><span className="landing-index">0{i + 1}</span><span className="membership-badge">{TIER[x.plan].n}</span></div><div className="product-card-mark" aria-hidden="true"><Icon name={x.icon} /></div><h3>{x.title}</h3><p>{x.text}</p><span className="landing-product-action">{x.action} <Icon name="arrow" /></span></Link></Reveal>)}</div>
      <Reveal className="landing-search-row"><div><h3>Have a company in mind?</h3><p>Try a name or symbol. Start with the financials.</p></div><CompanySearch /></Reveal>
    </div></section>
    <section className="landing-services" id="services" aria-labelledby="landing-services"><div className="wrap landing-section"><Reveal className="landing-section-head"><p className="landing-eyebrow">Our services</p><h2 id="landing-services">A person to talk to.<br />Room to work things out.</h2><p>From a first investment to a second look at your portfolio. Choose the conversation that fits where you are.</p></Reveal>
      <div className="landing-service-list">{SERVICES.map((s) => <Reveal key={s.n}><div className="landing-service"><span className="landing-index">{s.n}</span><div><h3>{s.name}</h3><p>{s.proposition}</p></div><button aria-label={`Enquire about ${s.name}`} onClick={() => enquire(s.name)}><Icon name="arrow" /></button></div></Reveal>)}</div>
      <Link className="marketing-action marketing-action-primary" to="/services">Find your conversation <Icon name="arrow" /></Link><p className="landing-caption">Educational conversations. We do not give buy or sell calls or promise returns.</p>
    </div></section>
    <Reveal className="landing-section wrap landing-team"><img src={FOUNDER.photo} alt="Nishant Jain, founder of FinLit Ventures" loading="lazy" /><div><p className="landing-eyebrow">The people behind FinLit</p><h2>A small team.<br />A thoughtful approach.</h2><p>Led by {FOUNDER.name}, FinLit brings company research and financial planning into a place where you can examine the reasoning for yourself.</p><Link className="landing-text-link" to="/about">Meet the team <Icon name="arrow" /></Link></div></Reveal>
  </div>;
}
