import { PageArt } from "../components/PageArt";
import { PRICING, SERVICES } from "../content/site";
import { Icon } from "../lib/icons";
import { Reveal } from "../components/Reveal";
import { useEnquiry } from "../components/Enquiry";
import { useDocTitle } from "../lib/title";
import { Link } from "react-router";

const perMonth = (price: string, months: number) => {
  const n = Number(price.replace(/[^\d]/g, ""));
  if (!n) return "Price to be announced";   // no price set yet (PRICE_TBA)
  return months > 1 ? "about ₹" + Math.round(n / months) + " a month" : months === 1 ? "a month" : "one time";
};

export function Services() {
  useDocTitle("Services & pricing", "Talk to the FinLit team about starting to invest, planning, global investing or reviewing your portfolio. Session prices will be announced soon.");
  const enquire = useEnquiry();
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="services" /><div className="eyebrow">Services</div><h1>Talk to someone about your money.</h1><p>Five kinds of conversation, from your first investment to a review of what you already hold. Not sure which one fits? Book a first session and we will work it out together.</p></div></section>
      <section className="sec hp-services" style={{ paddingTop: 16 }}><div className="wrap">
        <div className="cards3">{SERVICES.map((s, i) => <Reveal key={s.name} delay={i * 60}><div className="feat" style={{ "--ac": `var(--c${(i % 4) + 1})`, height: "100%" } as React.CSSProperties}><span className="num">{s.n}</span><div className="fi"><Icon name={s.icon} /></div><h3>{s.name}</h3><p className="prop">{s.proposition}</p><p>{s.desc}</p><button className="btn" onClick={() => enquire(s.name)}>Enquire <Icon name="arrow" /></button></div></Reveal>)}</div>
      </div></section>
      <section className="sec alt hp-prices"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">Pricing</div><h2>What a session costs</h2><p>These options are for talking to us: a first session, then monthly, quarterly, half-yearly or yearly plans for one service. Prices will be announced soon; send an enquiry and we will share the details.</p></Reveal>
        <div className="prices">{PRICING.map((p, i) => <Reveal key={p.plan} delay={i * 60}><div className={"price-c" + (i === PRICING.length - 1 ? " best" : "")}>{p.note === "Lowest per month" && <span className="chip gold tag-b">Lowest per month</span>}<div className="n">{p.plan}</div><div className="p">{p.price}</div><div className="hp-per">{perMonth(p.price, p.months)}</div><button className="btn" style={{ width: "100%" }} onClick={() => enquire()}>Enquire</button></div></Reveal>)}</div>
        <p className="hp-note">Looking for the website tools (screener, scores, watchlists)? Those are separate and are on the <Link to="/plans">Plans page</Link>. Basic is free.</p>
      </div></section>
      <section className="sec hp-dcf"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">Gold tool</div><h2>DCF calculator</h2>
          <p>Work out what a company is worth from the cash it will generate, the way analysts and banks do it, without building an Excel model. Load any listed company's free cash flow, debt and shares, set growth and the discount rate, and see the intrinsic value per share, the buy price after your margin of safety, and whether today's price is above or below it.</p></Reveal>
        <ul className="hp-list">
          <li>Every step of the working shown: projected cash flows, present values, terminal value, enterprise and equity value.</li>
          <li>Checks that stop impossible assumptions, and warnings when the answer rests mostly on the terminal value.</li>
          <li>Sensitivity grids, reverse DCF (the growth today's price assumes), bear, base and bull cases, and a discount-rate builder.</li>
          <li>Save scenarios, share a link, or download to Excel.</li>
        </ul>
        <p className="hp-note"><Link className="btn primary" to="/dcf">Open the DCF calculator</Link> Part of the <Link to="/plans">Gold plan</Link>. A calculation tool for education, not investment advice.</p>
      </div></section>
      <section className="sec hp-limits"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">Please read</div><h2>What we do not do</h2></Reveal>
        <ul className="hp-list">
          <li>We do not tell you which stock to buy or sell, and we do not promise returns.</li>
          <li>We do not manage your money or place trades for you.</li>
          <li>We are not registered with SEBI or AMFI. A conversation with us is education, not investment advice.</li>
          <li>Investments in securities markets are subject to market risks. You can lose money.</li>
        </ul>
      </div></section>
    </>
  );
}
