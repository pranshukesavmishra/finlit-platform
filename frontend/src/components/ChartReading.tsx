import type { Reading } from "../lib/chartReading";
import { ChartSays } from "./ChartSays";
import type { ChartSaysTopic } from "../lib/chartSays";

/** The plain-words "Inference" block under every Chart builder chart other than the scatter (which has its own, ChartInference). Same look, same words:
 *  what the figures did, never a forecast. `null` renders nothing (too little data to say anything honest). */
export function ChartReading({ reading, id, topic = "general" }: { reading: Reading | null; id: string; topic?: ChartSaysTopic }) {
  if (!reading) return null;
  return <ChartSays topic={topic} id={id}><section className="cinf" role="note" aria-live="polite" aria-label="What the chart says" data-testid="chart-reading">
    <p className="cinf-head">{reading.headline}</p>
    {reading.lines.length > 0 && <ul className="cinf-list">{reading.lines.map((l, i) => <li key={i} className={l.warn ? "warn" : undefined}>{l.warn && <b className="cinf-w">Note: </b>}{l.text}</li>)}</ul>}
    <p className="cinf-close">{reading.closing}</p>
  </section></ChartSays>;
}
