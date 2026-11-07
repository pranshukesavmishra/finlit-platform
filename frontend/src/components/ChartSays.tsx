import { useId, type ReactNode } from "react";
import { Icon } from "../lib/icons";
import { CHART_SAYS_HEADING, chartSaysSubtitle, type ChartSaysTopic } from "../lib/chartSays";

/** The collapsible reading under a chart. The heading never changes; the subtitle names the kind of analysis; the body is the chart's own reading.
 *  Closed until opened (a native <details>, so it works with the keyboard and without scripts). Colours come from the site's tokens. */
export function ChartSays({ topic, children, open = false, id }: { topic: ChartSaysTopic; children: ReactNode; open?: boolean; id?: string }) {
  const uid = useId(), hid = (id ?? uid) + "-h";
  return (
    <details className="csay" open={open} data-topic={topic}>
      <summary aria-labelledby={hid}>
        <span className="csay-ic" aria-hidden="true"><Icon name="bars" /></span>
        <span className="csay-t"><b id={hid}>{CHART_SAYS_HEADING}</b><small>{chartSaysSubtitle(topic)}</small></span>
        <svg className="csay-chev" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
      </summary>
      <div className="csay-body">{children}</div>
    </details>
  );
}
