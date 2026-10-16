import { PRICING, SERVICES } from "../content/site";
import { Icon } from "../lib/icons";
import { Reveal } from "../components/Reveal";
import { useEnquiry } from "../components/Enquiry";
import { useDocTitle } from "../lib/title";

export function Services() {
  useDocTitle("Services & pricing", "Investing, wealth planning, family financial planning, global investing and portfolio review from FinLit. First sessions from ₹99.");
  const enquire = useEnquiry();
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><div className="eyebrow">Services</div><h1>Structured help for every stage.</h1><p>Pick a service, or start with a first session and we will work out the rest together.</p></div></section>
      <section className="sec" style={{ paddingTop: 16 }}><div className="wrap">
        <div className="cards3">{SERVICES.map((s, i) => <Reveal key={s.name} delay={i * 60}><div className="feat" style={{ "--ac": `var(--c${(i % 4) + 1})`, height: "100%" } as React.CSSProperties}><span className="num">{s.n}</span><div className="fi"><Icon name={s.icon} /></div><h3>{s.name}</h3><p className="prop">{s.proposition}</p><p>{s.desc}</p><button className="btn" onClick={() => enquire(s.name)}>Enquire <Icon name="arrow" /></button></div></Reveal>)}</div>
      </div></section>
      <section className="sec alt"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">Pricing</div><h2>Simple, <em>per service</em></h2><p>Prices are per service. Start with a single session.</p></Reveal>
        <div className="prices">{PRICING.map((p, i) => <Reveal key={p.plan} delay={i * 60}><div className={"price-c" + (i === PRICING.length - 1 ? " best" : "")}>{p.note === "Best value" && <span className="chip gold tag-b">Best value</span>}<div className="n">{p.plan}</div><div className="p">{p.price}</div><button className="btn" style={{ width: "100%" }} onClick={() => enquire()}>Choose</button></div></Reveal>)}</div>
      </div></section>
    </>
  );
}
