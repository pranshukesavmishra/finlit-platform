import { PageArt } from "../components/PageArt";
import { WHY } from "../content/site";
import { Icon } from "../lib/icons";
import { Reveal } from "../components/Reveal";
import { useDocTitle } from "../lib/title";

export function Why() {
  useDocTitle("Why we exist", "Many Indian investors have SIPs and stocks but no plan. Here is why we started FinLit and what we are trying to fix.");
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="why" /><div className="eyebrow">Why we exist</div><h1>Many people invest. Few have a plan.</h1><p>Here is why we started FinLit, in a few short paragraphs.</p></div></section>
      <section className="sec" style={{ paddingTop: 16 }}><div className="wrap">
        <Reveal><div className="hp-story">{WHY.story.map((t) => <p key={t}>{t}</p>)}</div></Reveal>
      </div></section>
      <section className="sec alt"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">Who we meet</div><h2>Three kinds of investor</h2></Reveal>
        <div className="cards3">{WHY.people.map((p, i) => <Reveal key={p.title} delay={i * 70}><div className="feat" style={{ "--ac": `var(--c${i + 1})` } as React.CSSProperties}><span className="num">{p.n}</span><div className="fi"><Icon name={p.icon} /></div><h3>{p.title}</h3><p>{p.text}</p></div></Reveal>)}</div>
      </div></section>
      <section className="sec"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">What we offer</div><h2>Four things we do</h2></Reveal>
        <div className="cards4">{WHY.suite.map((p, i) => <Reveal key={p.title} delay={i * 60}><div className="feat" style={{ "--ac": `var(--c${i + 1})` }as React.CSSProperties}><span className="num">{p.n}</span><h3>{p.title}</h3><p>{p.text}</p></div></Reveal>)}</div>
      </div></section>
      <section className="sec alt"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">How it usually goes</div><h2>Six steps, repeated</h2></Reveal>
        <div className="steps six">{WHY.loop.map((l, i) => <Reveal key={l} delay={i * 60} className="step"><div className="dot" style={{ fontFamily: "var(--serif)", fontSize: 20 }}>{i + 1}</div><div><b>{l}</b></div></Reveal>)}</div>
        <div className="cards3" style={{ marginTop: 40 }}>{WHY.principles.map((p, i) => <Reveal key={p.title} delay={i * 70}><div className="feat" style={{ "--ac": "var(--gold)" } as React.CSSProperties}><h3>{p.title}</h3><p>{p.text}</p></div></Reveal>)}</div>
      </div></section>
    </>
  );
}
