import { WHY } from "../content/site";
import { Icon } from "../lib/icons";
import { CountUp, Reveal } from "../components/Reveal";
import { useDocTitle } from "../lib/title";

export function Why() {
  useDocTitle("Why we exist", "Most Indian investors are scattered, stuck at zero or unstructured. FinLit exists to give them goals, structure and a plan.");
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><div className="eyebrow">Why we exist</div><h1>Millions invest. Few have a plan.</h1><p>India has a huge, financially literate audience that is still investing without structure. We built FinLit for them.</p></div></section>
      <section className="sec" style={{ paddingTop: 16 }}><div className="wrap">
        <Reveal><div className="stats-row">{WHY.kpis.map((k) => <div key={k.label}><div className={"v" + (k.gold ? " gold" : "")}><CountUp to={k.value} decimals={k.value % 1 ? 1 : 0} prefix={k.prefix} suffix={k.suffix} /></div><div className="l">{k.label}</div><div className="s">{k.source}</div></div>)}</div></Reveal>
      </div></section>
      <section className="sec alt"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">Who we help</div><h2>Three kinds of <em>investor</em></h2></Reveal>
        <div className="cards3">{WHY.people.map((p, i) => <Reveal key={p.title} delay={i * 70}><div className="feat" style={{ "--ac": `var(--c${i + 1})` } as React.CSSProperties}><span className="num">{p.n}</span><div className="fi"><Icon name={p.icon} /></div><h3>{p.title}</h3><p>{p.text}</p></div></Reveal>)}</div>
      </div></section>
      <section className="sec"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">The service suite</div><h2>What we offer</h2></Reveal>
        <div className="cards4">{WHY.suite.map((p, i) => <Reveal key={p.title} delay={i * 60}><div className="feat" style={{ "--ac": `var(--c${i + 1})` }as React.CSSProperties}><span className="num">{p.n}</span><h3>{p.title}</h3><p>{p.text}</p></div></Reveal>)}</div>
      </div></section>
      <section className="sec alt"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">The growth loop</div><h2>An investor's <em>journey</em></h2></Reveal>
        <div className="steps six">{WHY.loop.map((l, i) => <Reveal key={l} delay={i * 60} className="step"><div className="dot" style={{ fontFamily: "var(--serif)", fontSize: 20 }}>{i + 1}</div><div><b>{l}</b></div></Reveal>)}</div>
        <div className="cards3" style={{ marginTop: 40 }}>{WHY.principles.map((p, i) => <Reveal key={p.title} delay={i * 70}><div className="feat" style={{ "--ac": "var(--gold)" } as React.CSSProperties}><h3>{p.title}</h3><p>{p.text}</p></div></Reveal>)}</div>
      </div></section>
    </>
  );
}
