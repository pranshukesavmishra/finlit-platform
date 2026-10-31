import { BANDS_TIP, type Inference } from "../lib/chartInference";

/**
 * The plain-words "Inference" block under a scatter chart. Pure view of a `chartInference()` result.
 * `inference === null` shows a skeleton (the chart is still loading). The region is polite-live, so a screen reader
 * hears the new reading when filters, companies or the window change.
 */
export function ChartInference({ inference, id = "inf" }: { inference: Inference | null; id?: string }) {
  if (!inference) return <section className="cinf cinf-skel" aria-busy="true" aria-label="Inference" data-testid="inference-skeleton"><span className="cinf-bar w1" /><span className="cinf-bar w2" /><span className="cinf-bar w3" /></section>;
  const ok = inference.state === "ok";
  return <section className="cinf" role="note" aria-live="polite" aria-labelledby={id + "-h"} data-testid="inference">
    <h4 className="cinf-h" id={id + "-h"}>Inference <span className="cinf-sub">a plain-words reading of this chart</span>
      <button type="button" className="cinf-tip" title={BANDS_TIP} aria-label={BANDS_TIP}>?</button></h4>
    <p className={"cinf-head" + (ok ? "" : " cinf-none")}>{inference.headline}</p>
    {ok && inference.lines.length > 0 && <ul className="cinf-list">{inference.lines.map((l) => <li key={l.id} className={l.warn ? "warn" : undefined}>{l.warn && <b className="cinf-w">Note: </b>}{l.text}</li>)}</ul>}
    {ok && inference.placements.length > 0 && <ul className="cinf-list cinf-place" aria-label="Where the companies you added sit">{inference.placements.map((p) => <li key={p.name}>{p.text}</li>)}</ul>}
    <details className="cinf-how"><summary>How to read this</summary>
      <ul>{inference.howTo.map((t) => <li key={t}>{t}</li>)}</ul></details>
    <p className="cinf-close">{inference.closing}</p>
  </section>;
}
