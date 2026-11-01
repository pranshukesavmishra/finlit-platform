import { Link, useLocation } from "react-router";
import { COMPANY } from "../content/site";
import { versionLine } from "../lib/version";

export function SiteFooter() {
  const { pathname } = useLocation();
  return <footer className="site-footer"><div className="wrap">
    <div className="site-footer-main"><div><Link className="logo" to="/" aria-label="FinLit home"><span className="lg-mark" role="img" aria-label="FinLit" /></Link><p>Company research, with the figures in view.</p><a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a></div>
      <nav aria-label="Research links"><b>Research</b><Link to="/research">Company reports</Link><Link to="/screener">Stock screener</Link><Link to="/prism">FinLit Prism</Link><Link to="/platform">All tools</Link></nav>
      <nav aria-label="Company links"><b>FinLit</b><Link to="/about">About the team</Link><Link to="/services">Services</Link><Link to="/plans">Plans</Link><Link to="/contact">Contact</Link></nav>
      <nav aria-label="Help and information"><b>Help</b><button onClick={() => dispatchEvent(new Event("finlit:help"))}>Ask the FinLit assistant</button>{pathname === "/" && <button onClick={() => dispatchEvent(new Event("finlit:replay-introduction"))}>Replay introduction</button>}<Link to="/faq">FAQs</Link><Link to="/glossary">Financial glossary</Link><a href={COMPANY.linkedin} target="_blank" rel="noopener noreferrer">LinkedIn</a></nav>
    </div>
    <div className="site-footer-bottom"><p>{COMPANY.disclaimer} Market data may be delayed. Past performance does not indicate future results.</p><div><span>© {new Date().getFullYear()} {COMPANY.name}</span><Link to="/legal/terms">Terms</Link><Link to="/legal/privacy">Privacy</Link><Link to="/legal/disclosures">Disclosures</Link><small title="Quote this when you contact support">{versionLine()}</small></div></div>
  </div></footer>;
}

