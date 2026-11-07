// The collapsible "What does the chart say?" under a chart: the heading is the same everywhere, the subtitle names the kind of analysis the chart shows
// (Task #23). The words inside are each chart's own reading, worked out from its figures by fixed rules (lib/chartInference, chartReading, corrInsight,
// and dupontSays below); nothing here is written by hand per company.
export const CHART_SAYS_HEADING = "What does the chart say?";

export type ChartSaysTopic = "dupont" | "correlation" | "relationship" | "trend" | "comparison" | "breakdown" | "price" | "matrix" | "general";

const SUBTITLE: Record<ChartSaysTopic, string> = {
  dupont: "Get the key takeaways from this Extended DuPont analysis.",
  correlation: "Get the key takeaways from this correlation analysis.",
  relationship: "Get the key takeaways from this relationship between two measures.",
  trend: "Get the key takeaways from this financial trend.",
  comparison: "Get the key takeaways from this comparison of the figures.",
  breakdown: "Get the key takeaways from this breakdown by part.",
  price: "Get the key takeaways from this price chart.",
  matrix: "Get the key takeaways from this correlation matrix.",
  general: "Get the key takeaways from this chart.",
};
export const chartSaysSubtitle = (topic: ChartSaysTopic): string => SUBTITLE[topic] ?? SUBTITLE.general;

/** The topic of a Chart builder chart, from its type. */
export function topicOfChart(chart: string, opts: { matrix?: boolean } = {}): ChartSaysTopic {
  switch (chart) {
    case "scatter": return "relationship";
    case "heatmap": return opts.matrix ? "matrix" : "correlation";
    case "pie": return "breakdown";
    case "candlestick": return "price";
    case "bar": return "comparison";
    case "line": case "area": case "combo": case "stacked": return "trend";
    default: return "general";
  }
}

type Step = { label: string; pp: number };
/** The Extended DuPont reading: what ROE did between the two dates, which factor lifted it most and which weighed on it most. Percentage points, one decimal, as on the chart. */
export function dupontSays(wf: { from: string; to: string; start: number; end: number; steps: Step[] }): string[] {
  const d = wf.end - wf.start, one = (x: number) => (Math.round(Math.abs(x) * 10) / 10).toFixed(1), pp = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${one(x)} pp`;
  const out = [`Return on equity ${Math.abs(d) < 0.05 ? "was about the same" : d > 0 ? "rose" : "fell"} from ${one(wf.start)}% in ${wf.from} to ${one(wf.end)}% in ${wf.to}${Math.abs(d) < 0.05 ? "" : ` (${pp(d)})`}.`];
  const up = [...wf.steps].filter((s) => s.pp >= 0.05).sort((a, b) => b.pp - a.pp)[0], down = [...wf.steps].filter((s) => s.pp <= -0.05).sort((a, b) => a.pp - b.pp)[0];
  if (up) out.push(`${up.label} added the most (${pp(up.pp)}).`);
  if (down) out.push(`${down.label} took away the most (${pp(down.pp)}).`);
  if (!up && !down) out.push("None of the five factors moved ROE by 0.1 percentage points or more.");
  out.push("The five factors multiply to ROE, so the contributions add up to the change (to within rounding). This describes what happened in the reported figures only.");
  return out;
}
