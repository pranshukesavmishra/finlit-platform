import { useEffect, useMemo, useState } from "react";
import { PageArt } from "../components/PageArt";
import { Icon } from "../lib/icons";
import { LETTERS, TERMS, TOPICS, search } from "../lib/glossary";
import { useDocTitle } from "../lib/title";
import "../styles/glossary.css";

export function GlossaryPage() {
  useDocTitle("Glossary", `FinLit Glossary: ${TERMS.length} investing terms in plain English, from A to Z, with formulas and how FinLit measures them.`);
  const [q, setQ] = useState(""), [letter, setLetter] = useState(""), [topic, setTopic] = useState("");
  const pool = useMemo(() => TERMS.filter((t) => (!topic || t.topic === topic) && (!letter || t.letter === letter)), [topic, letter]);
  const list = useMemo(() => (q.trim() ? search(q, pool) : pool), [q, pool]);
  const counts = useMemo(() => Object.fromEntries(LETTERS.map((l) => [l, TERMS.filter((t) => t.letter === l && (!topic || t.topic === topic)).length])), [topic]);
  useEffect(() => {  // deep link #term-id: show everything, then scroll to the card
    const id = decodeURIComponent(location.hash.slice(1));
    if (id) setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: "start" }), 50);
  }, []);
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="blog" />
        <div className="eyebrow">Learn</div><h1>The language of investing, in plain words.</h1>
        <p>{TERMS.length} terms from A to Z. Each says what it means, why it matters and how to use it, with the formula where there is a standard one, and how FinLit measures it. For education only; not investment, tax or legal advice.</p></div></section>
      <div className="wrap gx">
        <label className="gx-s"><Icon name="table" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search terms, e.g. P/E, ROE, EV/CFO…" aria-label="Search the glossary" /></label>
        <div className="gx-bar">
          <div className="gx-az" role="group" aria-label="Letters">
            <button className={!letter ? "on" : ""} aria-pressed={!letter} onClick={() => setLetter("")}>All</button>
            {LETTERS.map((l) => <button key={l} className={letter === l ? "on" : ""} disabled={!counts[l]} aria-pressed={letter === l} onClick={() => setLetter(l)}>{l}</button>)}
          </div>
          <label className="gx-c"><span className="label">Topic</span><select value={topic} onChange={(e) => setTopic(e.target.value)} aria-label="Filter by topic"><option value="">All topics</option>{TOPICS.map((c) => <option key={c}>{c}</option>)}</select></label>
        </div>
        <div className="gx-h"><span>{list.length} term{list.length === 1 ? "" : "s"}</span></div>
        <div className="gx-list">{list.map((x) => (
          <article className="gx-card" key={x.id} id={x.id}>
            <header><h3><a href={"#" + x.id}>{x.term}</a></h3><span className="chip gold">{x.topic}</span></header>
            <dl>
              <dt>Meaning</dt><dd>{x.meaning}</dd>
              <dt>Why it matters</dt><dd>{x.why}</dd>
              <dt>How to use it</dt><dd>{x.how}</dd>
            </dl>
            {x.formula && <div className="gx-f"><span className="label">Formula</span><code>{x.formula}</code></div>}
            {x.finlit && <div className="gx-n"><span className="label">How FinLit measures it</span><p>{x.finlit}</p></div>}
          </article>))}
          {!list.length && <div className="state"><h2>No matching terms</h2><p>Try a different word, or clear the letter and topic filters.</p></div>}
        </div>
        <p className="faint gx-foot">Rules and limits quoted (tax rates, IPO quotas) can change; check the latest SEBI and tax rules. Definitions are for learning, not advice.</p>
      </div>
    </>
  );
}
