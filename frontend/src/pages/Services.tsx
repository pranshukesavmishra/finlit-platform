import { Link } from "react-router";
import { useEnquiry } from "../components/Enquiry";
import { Reveal } from "../components/Reveal";
import { SERVICES } from "../content/site";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";

export function Services() {
  useDocTitle("Financial planning and portfolio conversations", "Explore FinLit investing education, wealth and family planning, global investing and portfolio review services.");
  const enquire = useEnquiry();
  return <div className="service-page">
    <header className="wrap service-hero"><p className="landing-eyebrow">Our services</p><h1>Let's talk about<br />the bigger picture.</h1><p>Where you are now. What your money is for. What you want to understand next.</p><a className="landing-text-link" href="#conversations">Find your conversation <Icon name="arrow" /></a></header>
    <section className="wrap service-conversations" id="conversations" aria-labelledby="conversations-title"><h2 id="conversations-title">Five ways to start.</h2>
      {SERVICES.map((s) => <Reveal key={s.n}><details className="service-detail"><summary><span className="landing-index">{s.n}</span><span><strong>{s.name}</strong><small>{s.proposition}</small></span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M5 12h14M12 5v14" /></svg></summary><div className="service-detail-body"><p>{s.desc}</p><button className="btn primary" onClick={() => enquire(s.name)}>Enquire about this service <Icon name="arrow" /></button></div></details></Reveal>)}
    </section>
    <Reveal className="service-contact"><div className="wrap"><p className="landing-eyebrow">A place to begin</p><h2>Not sure which one fits?</h2><p>Tell us what you want to understand. We can discuss the kind of conversation that would help.</p><button className="btn primary" onClick={() => enquire()}>Talk to the team <Icon name="arrow" /></button><p className="landing-caption">Session prices have not been announced. Send an enquiry for details.</p></div></Reveal>
    <section className="wrap service-scope" aria-labelledby="service-scope"><div><h2 id="service-scope">What to expect</h2><p>Education and a second perspective. You remain in control of your decisions.</p></div><ul><li>We do not give buy or sell calls, manage your money or place trades.</li><li>We are not registered with SEBI or AMFI. These conversations are educational, not investment advice.</li><li>We do not promise returns. Investments are subject to market risk.</li></ul><p>Looking for company research, scores and screeners? <Link to="/platform">Explore our products</Link>. Website plans are separate from these services.</p></section>
  </div>;
}
