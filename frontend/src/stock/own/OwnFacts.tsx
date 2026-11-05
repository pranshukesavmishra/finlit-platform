import { factItems, pc2, type OwnFacts as Facts, type OwnInsights } from "../../lib/ownView";

const GROUP_WORD: Record<string, string> = { dii: "Domestic", fii: "Foreign", public: "Retail & others", government: "Government", promoters: "Promoter" };

/** "Also from the filing" (shareholders, pledge, share count, lock-in) and "Largest institutional holders". Each blank says why. */
export function OwnFacts({ ins }: { ins?: OwnInsights }) {
  const f: Facts | undefined = ins?.facts, prem = ins?.premium;
  const why = prem && prem.state !== "ok" ? prem.reason : null;
  const items = factItems(f, why);
  const holders = f?.top_holders ?? [];
  return (
    <div className="ow-row">
      <section className="ow-card" aria-labelledby="ow-facts">
        <h3 id="ow-facts" className="ow-h3">Also from the filing</h3>
        {why && <p className="ow-note ow-why" role="status">{why}</p>}
        <div className="ow-facts">
          {items.map((it) => <div className="ow-fact" key={it.label}><span className="ow-small ow-muted">{it.label}</span><b>{it.value}</b><span className="ow-small ow-body">{it.note}</span></div>)}
        </div>
      </section>
      <section className="ow-card" aria-labelledby="ow-named">
        <div className="ow-sec-h"><h3 id="ow-named" className="ow-h3">Largest institutional holders</h3><span className="ow-small ow-muted">1% or more · a year ago → now</span></div>
        {holders.length ? holders.map((h) => (
          <div className="ow-holder" key={h.name}><span title={GROUP_WORD[h.group] ? `${GROUP_WORD[h.group]} institution` : undefined}>{h.name}</span><span className="ow-muted">{h.year_ago == null ? "–" : pc2(h.year_ago)} →</span><b>{pc2(h.now)}</b></div>
        )) : <p className="ow-note">{why ?? (prem?.has.holders === false && prem ? "The data provider lists no holder of 1% or more for this company." : "No named holder of 1% or more is listed for this company.")}</p>}
      </section>
    </div>
  );
}
