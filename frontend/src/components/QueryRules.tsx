import { Link } from "react-router";
import { RULES } from "../lib/queryRules";

/** "Rules for writing a query": golden rules, a syntax table, do and don't, and ten examples that go into the editor with one click. */
export function QueryRules({ onInsert, onClose }: { onInsert: (query: string) => void; onClose: () => void }) {
  return (
    <section id="qb-rules" className="card qr" aria-labelledby="qr-h">
      <div className="qr-head">
        <h2 id="qr-h">Rules for writing a query</h2>
        <button className="btn" onClick={onClose}>Hide the rules</button>
      </div>

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
    </section>
  );
}
