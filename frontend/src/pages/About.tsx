import { PageArt } from "../components/PageArt";
import { Link } from "react-router";
import { FOUNDER, PILLARS, PRINCIPLES } from "../content/site";
import { Icon } from "../lib/icons";
import { Reveal } from "../components/Reveal";
import { useDocTitle } from "../lib/title";

export function About() {
  useDocTitle("About", "FinLit Ventures: independent investment research, portfolio reviews and planning, led by Nishant Jain (IIT Kanpur, CFA Level I, NISM RA).");
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="about" /><div className="eyebrow">About FinLit</div><h1>Independent thinking, plainly explained.</h1><p>Investment research, portfolio reviews and financial planning with one rule: reasoning you can follow.</p></div></section>
      <section className="sec" style={{ paddingTop: 16 }}><div className="wrap founder">
        <Reveal><img src={FOUNDER.photo} alt={`Portrait of ${FOUNDER.name}`} width="560" height="700" /></Reveal>
        <Reveal delay={100}><div className="eyebrow">Investment lead</div><div className="sec-h" style={{ margin: "8px 0 0" }}><h2>{FOUNDER.name}</h2><p>{FOUNDER.role}</p></div><div className="cred">{FOUNDER.credentials.map((c) => <span className="chip gold" key={c}>{c}</span>)}</div><p className="muted">{FOUNDER.bio}</p><a className="btn" href={FOUNDER.linkedin} target="_blank" rel="noopener noreferrer">LinkedIn</a></Reveal>
      </div></section>
      <section className="sec alt"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">What we do</div><h2>Four pillars</h2></Reveal>
        <div className="cards4">{PILLARS.map((p, i) => <Reveal key={p.title} delay={i * 60}><div className="feat" style={{ "--ac": `var(--c${i + 1})`, height: "100%" } as React.CSSProperties}><div className="fi"><Icon name={p.icon} /></div><h3>{p.title}</h3><p>{p.text}</p></div></Reveal>)}</div>
      </div></section>
      <section className="sec"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">Our principles</div><h2>How we <em>think</em></h2></Reveal>
        <div className="cards3">{PRINCIPLES.map((p, i) => <Reveal key={p.title} delay={i * 70}><div className="feat" style={{ "--ac": "var(--gold)" } as React.CSSProperties}><span className="num">0{i + 1}</span><h3>{p.title}</h3><p>{p.text}</p></div></Reveal>)}</div>
        <div style={{ marginTop: 32, textAlign: "center" }}><Link className="btn primary lg" to="/why-we-exist">Why FinLit exists <Icon name="arrow" /></Link></div>
      </div></section>
    </>
  );
}
