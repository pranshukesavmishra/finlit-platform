import { CLOSING, MAX_BLOCKS, type Insight } from "../lib/corrInsight";

/** The rule-based reading under the correlation chart: what the cloud says, where each chosen company sits, how the chosen companies compare, how far to trust it.
 *  A pure view of `generateInsight()`. `null` shows a skeleton while the chart loads. Polite-live, so a screen reader hears the new text when the selection changes. */
export function CorrInsight({ insight, id = "ci" }: { insight: Insight | null; id?: string }) {
  if (!insight) return <section className="cinf cinf-skel" aria-busy="true" aria-label="What this chart says" data-testid="insight-skeleton"><span className="cinf-bar w1" /><span className="cinf-bar w2" /></section>;
  const shown = insight.companies.slice(0, MAX_BLOCKS), more = insight.companies.slice(MAX_BLOCKS);
  return (
    <section className="cinf corrins" role="note" aria-live="polite" aria-labelledby={id + "-h"} data-testid="corr-insight">
      <h4 className="cinf-h" id={id + "-h"}>What this chart says <span className="cinf-sub">worked out from the figures by fixed rules</span></h4>
      <p className="cinf-head">{insight.cloud}{insight.shape ? " " + insight.shape : ""}</p>
      {shown.length > 0 && <div className="ci-co" aria-label="Where the companies you added sit">{shown.map((t, i) => <p key={i}>{t}</p>)}
        {more.length > 0 && <details className="ci-more"><summary>Show {more.length} more compan{more.length === 1 ? "y" : "ies"}</summary>{more.map((t, i) => <p key={i}>{t}</p>)}</details>}</div>}
      {insight.comparison.length > 0 && <div className="ci-cmp" aria-label="How the companies you added compare">{insight.comparison.map((t, i) => <p key={i}>{t}</p>)}</div>}
      {insight.caveats.length > 0 && <ul className="cinf-list ci-cav" aria-label="Reading notes">{insight.caveats.map((t) => <li key={t}>{t}</li>)}</ul>}
      <p className="ci-foot">{insight.footer}</p>
      <p className="cinf-close">{CLOSING}</p>
    </section>);
}
