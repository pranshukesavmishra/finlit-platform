// What each plan includes in Graph Studio. The server applies the same numbers when a view is saved (backend/finlit/graphviews.py,
// kept equal by a test); chart data itself is already trimmed by plan on the stock endpoints. Here they only shape the page.
import type { Plan } from "./auth";

export type ChartKind = "line" | "area" | "column" | "bar" | "combo" | "pie" | "candlestick" | "scatter" | "heatmap";
export type GraphLimits = { cells: number; companies: number; series: number; views: number; charts: ChartKind[] };

export const GRAPH_LIMITS: Record<Plan, GraphLimits> = {
  basic: { cells: 4, companies: 2, series: 3, views: 2, charts: ["line", "area", "column", "bar", "combo", "pie"] },
  silver: { cells: 6, companies: 3, series: 4, views: 10, charts: ["line", "area", "column", "bar", "combo", "pie", "candlestick", "scatter"] },
  gold: { cells: 9, companies: 6, series: 6, views: 50, charts: ["line", "area", "column", "bar", "combo", "pie", "candlestick", "scatter", "heatmap"] },
};
export const graphLimits = (plan: Plan): GraphLimits => GRAPH_LIMITS[plan] ?? GRAPH_LIMITS.basic;
/** The cheapest plan that includes a chart type. */
export const chartTier = (c: ChartKind): Plan => (GRAPH_LIMITS.basic.charts.includes(c) ? "basic" : GRAPH_LIMITS.silver.charts.includes(c) ? "silver" : "gold");
