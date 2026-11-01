import { Icon } from "../lib/icons";
import type { ProfitReality } from "../lib/profitReality";
import { earningsIntel, type Tone } from "../lib/earningsIntel";
import "../styles/earningsintel.css";

const MARK: Record<Tone, string> = { ok: "✓", watch: "!", alert: "⚑", na: "–" };

/** Shape plus text, never colour alone. */
export function Pill({ tone, children }: { tone: Tone; children: string }) {
  return <span className={"ei-pill " + tone}><span className="m" aria-hidden="true">{MARK[tone]}</span>{children}</span>;
}

/** Level 1, quick insights for the Profit Reality Check. Everything comes from the numbers the section already loaded. */
export function EarningsIntel({ pr, sector, industry }: { pr: ProfitReality; sector?: string | null; industry?: string | null }) {
  const x = earningsIntel(pr, sector, industry);
  if (!x) return null;
  return (
    <section className="ei" aria-label="Earnings Quality Intelligence">
      <div className="ei-h">
        <h4><span className="ci"><Icon name="spark" /></span>Earnings Quality Intelligence</h4>
        <Pill tone={x.pill.tone}>{x.pill.label}</Pill>
      </div>
      <p className="ei-sub">Quick insights, worked out from the numbers below</p>

      <div className="ei-stats" role="list">
        {x.stats.map((s) => <div className="ei-stat" role="listitem" key={s.label}><span className="k">{s.label}</span><b>{s.value}</b><small>{s.sub}</small></div>)}
      </div>

      <div className="ei-cols">
        <div className="ei-col">
          <h5>What is happening?</h5>
          <p>{x.happening}</p>
          {x.questions.length > 0 && (<>
            <h5>What should you investigate?</h5>
            <ul className="ei-q">{x.questions.map((t, i) => <li key={i}>{t}</li>)}</ul>
          </>)}
        </div>
        <div className="ei-col">
          <h5>Intelligence modules</h5>
          <ul className="ei-mods">
            {x.modules.map((m) => (
              <li key={m.key}>
                <details>
                  <summary><span className="ci"><Icon name={m.icon} /></span><span className="nm">{m.name}</span><Pill tone={m.tone}>{m.badge}</Pill></summary>
                  <ul className="ei-facts">{m.facts.map((t, i) => <li key={i}>{t}</li>)}</ul>
                </details>
              </li>))}
          </ul>
          {x.lender && <p className="ei-na">Cash-flow analysis is not comparable for lenders. The modules that apply are shown.</p>}
          <p className="ei-na">{x.peer}</p>
        </div>
      </div>

      <details className="ei-l3">
        <summary>Investor interpretation</summary>
        <dl>
          <dt>Why it matters</dt><dd>{x.meaning.why}</dd>
          {x.meaning.risks.length > 0 && (<><dt>Possible risks</dt><dd><ul>{x.meaning.risks.map((t, i) => <li key={i}>{t}</li>)}</ul></dd></>)}
          <dt>What to investigate next</dt><dd>{x.meaning.where}</dd>
        </dl>
      </details>

      <details className="ei-how">
        <summary>How this is decided</summary>
        <ul>{x.modules.map((m) => <li key={m.key}><b>{m.name}.</b> {m.rule}</li>)}</ul>
        {x.lender ? <p>Cash-flow based labels are not shown for lenders. Missing inputs give "Not enough data"; nothing is estimated.</p>
          : <p>The top label follows the Profit vs Cash Flow status: Red flag gives "Weak cash backing", Watch gives "Cash backing to watch", Steady gives "Cash backing steady". A single weak year alone is Watch. Missing inputs give "Not enough data"; nothing is estimated.</p>}
      </details>

      {x.caveats.map((t, i) => <p className="ei-cav" key={i}><Icon name="info" />{t}</p>)}
      <p className="ei-disc">Describes the company's earnings quality from its filings; not a recommendation. Information only, not investment advice.</p>
    </section>
  );
}
