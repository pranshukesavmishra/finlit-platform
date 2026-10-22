// Fund facts (size, costs, exit load, benchmark, managers, risk-o-meter, launch date, minimum investment, category, fund house).
// Each shows its value with the date and source, or a dash with the reason it is missing. Nothing is estimated.
import { Icon } from "../lib/icons";
import { dateIN } from "../lib/format";
import { FACT_LABELS, factKeys, factValueText, type FundFacts } from "../lib/mf";

export function FactsCard({ facts, loading, failed }: { facts?: FundFacts; loading: boolean; failed: boolean }) {
  return (
    <section className="card mf-card" aria-labelledby="mf-facts-h">
      <div className="card-h"><h3 id="mf-facts-h"><span className="ci"><Icon name="notes" /></span>Fund facts</h3></div>
      {loading && !facts ? <div className="skeleton" style={{ height: 180 }} aria-busy="true" /> : failed && !facts ? <p className="muted">The fund facts could not be loaded right now. Please try again in a moment.</p> : facts && (
        <dl className="mf-factlist">
          {factKeys(facts).map((k) => {
            const f = facts.facts[k];
            const text = factValueText(f);
            const why = "unavailable" in f ? f.unavailable : text ? "" : "The source gives no value.";
            return (
              <div key={k}>
                <dt>{FACT_LABELS[k] || k}</dt>
                <dd>
                  {text ? <b>{text}</b> : <span className="mf-bigna" aria-label={`No figure. ${why}`}>—</span>}
                  <small className={text ? "faint" : "mf-why"}>
                    {text && !("unavailable" in f) ? [f.asOf ? `As of ${dateIN(f.asOf)}` : "", f.source || ""].filter(Boolean).join(" · ") : why}
                  </small>
                  {text && !("unavailable" in f) && f.note ? <small className="faint">{f.note}</small> : null}
                </dd>
              </div>);
          })}
        </dl>)}
    </section>
  );
}
