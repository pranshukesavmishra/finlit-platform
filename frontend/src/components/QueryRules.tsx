import { Link } from "react-router";
import { RULES } from "../lib/queryRules";
import { Icon } from "../lib/icons";

/** "Rules for writing a query": golden rules, a syntax table, do and don't, and ten examples that go into the editor with one click. */
export function QueryRules({ open, onToggle, onInsert }: { open: boolean; onToggle: () => void; onInsert: (query: string) => void }) {
  return (
    <section id="qb-rules" className={"qr-box" + (open ? " is-open" : "")} aria-labelledby="qr-h">
      <h2 id="qr-h" className="qr-bar">
        <button type="button" aria-expanded={open} aria-controls="qr-body" onClick={onToggle}>
          <span className="qr-ico" aria-hidden="true"><Icon name="clipboard" /></span>
          <span className="qr-title">Rules for writing a query</span>
          <svg className="qr-chev" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 15 6-6 6 6" /></svg>
        </button>
      </h2>
      {open && <div id="qr-body" className="card qr">

      <h3>The golden rules</h3>
      <ol className="qr-gold">{RULES.golden.map((g) => <li key={g}>{g}</li>)}</ol>

      <h3>Syntax</h3>
      <div className="qr-tw" role="region" aria-label="Syntax table" tabIndex={0}>
        <table className="qr-t">
          <thead><tr><th scope="col">Write</th><th scope="col">Meaning</th><th scope="col">Example</th></tr></thead>
          <tbody>{RULES.syntax.map((r) => (
            <tr key={r.op}><th scope="row"><code>{r.op}</code></th><td>{r.meaning}</td><td><code className="qr-ex">{r.example}</code></td></tr>))}</tbody>
        </table>
      </div>
      <p className="qb-sub">Not part of the language:</p>
      <ul className="qr-no">{RULES.notSupported.map((n) => <li key={n}>{n}</li>)}</ul>

      <h3>What the results contain</h3>
      <ul className="qr-no">{RULES.results.map((n) => <li key={n}>{n}</li>)}</ul>

      <h3>Do and don't</h3>
      <ul className="qr-dd">{RULES.dos.map((d) => (
        <li key={d.dont}>
          <div><span className="qr-tag ok">Reads correctly</span><code>{d.do}</code></div>
          <div><span className="qr-tag no">Gives a message</span><code>{d.dont}</code></div>
          <p>{d.why}</p>
        </li>))}
      </ul>

      <h3>Ten examples</h3>
      <p className="qb-sub">Each one goes into the editor as it is, and runs for every plan.</p>
      <ul className="qr-exs">{RULES.examples.map((e) => (
        <li key={e.id}>
          <div><b>{e.title}</b><pre>{e.query}</pre></div>
          <button className="btn" onClick={() => onInsert(e.query)} aria-label={`Put “${e.title}” in the editor`}>Insert</button>
        </li>))}
      </ul>

      <p className="qr-foot">When a query has a problem, the message under the editor names the rule that was broken and how to fix it. More answers are in the <Link to="/faq#faq-query-builder-1" className="alx-link">questions for this page</Link>.</p>
      </div>}
    </section>
  );
}
