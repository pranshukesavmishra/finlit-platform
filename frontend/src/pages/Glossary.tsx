import { useMemo, useState } from "react";
import { PageArt } from "../components/PageArt";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import terms from "../content/glossary.json";

type Term = { t: string; l: string; d: string; c: string; formula?: string };
const ALL = terms as Term[];
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
const CATS = [...new Set(ALL.map((x) => x.c))].sort();
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

export function GlossaryPage() {
  useDocTitle("Glossary", "FinLit Glossary: 95 plain-language finance terms from A to Z, with formulas wherever there is a standard calculation.");
  const [q, setQ] = useState(""), [letter, setLetter] = useState("A"), [cat, setCat] = useState(""), [picked, setPicked] = useState(true);
  const counts = useMemo(() => Object.fromEntries(LETTERS.map((l) => [l, ALL.filter((x) => x.l === l && (!cat || x.c === cat)).length])), [cat]);
  const searching = q.trim().length > 0, s = q.trim().toLowerCase(), byLetter = !searching && (!cat || picked);
  const list = useMemo(() => ALL.filter((x) => (!cat || x.c === cat) && (searching ? x.t.toLowerCase().includes(s) || x.d.toLowerCase().includes(s) : !byLetter || x.l === letter)).sort((a, b) => a.t.localeCompare(b.t)), [cat, letter, s, searching, byLetter]);
  const pickLetter = (l: string) => { setQ(""); setLetter(l); setPicked(true); };
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="blog" />
        <div className="eyebrow">Learn</div><h1>The language of investing, in plain words.</h1>
        <p>{ALL.length} finance terms from A to Z, each with a short definition and the formula wherever there is a standard calculation. Free on every plan.</p></div></section>
      <div className="wrap gloss">
        <label className="gl-s"><Icon name="table" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search terms, e.g. P/E, ROE, CAGR…" aria-label="Search the glossary" /></label>
        <div className="gl-bar">
          <div><div className="label">Browse alphabetically</div>
            <div className="gl-az" role="group" aria-label="Letters">{LETTERS.map((l) => <button key={l} className={byLetter && l === letter ? "on" : ""} disabled={!counts[l]} aria-pressed={byLetter && l === letter} onClick={() => pickLetter(l)}>{l}<small>{counts[l] || ""}</small></button>)}</div></div>
          <label className="gl-c"><span className="label">Category</span><select value={cat} onChange={(e) => { setCat(e.target.value); setPicked(false); }} aria-label="Filter by category"><option value="">All categories</option>{CATS.map((c) => <option key={c}>{c}</option>)}</select></label>
        </div>
        <div className="gl-h"><h2>{searching ? `Results for “${q.trim()}”` : byLetter ? `Terms under ${letter}` : `${cat}: all terms`}</h2><span>{list.length} term{list.length === 1 ? "" : "s"}</span></div>
        <div className="gl-list">{list.map((x) => (
          <article className="gl-card" key={x.t} id={slug(x.t)}>
            <header><h3>{x.t}</h3><span className="chip gold">{x.c}</span></header>
            <p>{x.d}</p>
            {x.formula && <div className="gl-f"><span className="label">Formula / measurement</span><code>{x.formula}</code></div>}
          </article>))}
          {!list.length && <div className="state"><h2>No matching terms</h2><p>Try a different word, or clear the category filter.</p></div>}
        </div>
        <p className="faint gl-foot">Definitions are general explanations for learning, not advice. Tax rules and thresholds change; check current rules before acting.</p>
      </div>
    </>
  );
}
