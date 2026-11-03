import type { Reading } from "../lib/chartReading";

/** The plain-words "Inference" block under every Chart builder chart other than the scatter (which has its own, ChartInference). Same look, same words:
 *  what the figures did, never a forecast. `null` renders nothing (too little data to say anything honest). */
export function ChartReading({ reading, id }: { reading: Reading | null; id: string }) {
  if (!reading) return null;
  return <section className="cinf" role="note" aria-live="polite" aria-labelledby={id + "-h"} data-testid="chart-reading">
    <h4 className="cinf-h" id={id + "-h"}>Inference <span className="cinf-sub">a plain-words reading of this chart</span></h4>
    <p className="cinf-head">{reading.headline}</p>
    {reading.lines.length > 0 && <ul className="cinf-list">{reading.lines.map((l, i) => <li key={i} className={l.warn ? "warn" : undefined}>{l.warn && <b className="cinf-w">Note: </b>}{l.text}</li>)}</ul>}
    <p className="cinf-close">{reading.closing}</p>
  </section>;
}
