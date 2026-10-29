// The stock page's sections, for the sticky section bar and its "All sections" panel: id, name, icon and a one-line hint of what the section holds,
// plus the pure keyboard rule of the panel's grid. Leadership is listed only when the report says it is shown.
export type NavItem = [id: string, label: string, icon: string, hint: string];

export const NAV: NavItem[] = [
  ["business", "Company", "building", "What the company does and how it earns"],
  ["notes", "Scorecard", "notes", "The FinLit score and what lifts or weighs on it"],
  ["price", "Price", "line", "Price chart, returns and technical levels"],
  ["quarter", "Quarter", "notes", "The latest quarter against a year ago"],
  ["financials", "Financials", "bars", "Profit and loss, balance sheet and cash flow"],
  ["trends", "Trends", "line", "How sales, profit and margins have moved"],
  ["ratios", "Ratios", "gauge", "Valuation, returns and balance sheet ratios"],
  ["ownership", "Ownership", "pie", "Promoters, institutions and the public"],
  ["peers", "Peers", "layers", "Similar companies side by side"],
  ["insights", "Insights", "crown", "Gold insights worked out from the numbers"],
  ["dividends", "Dividends", "coins", "Dividends, splits, bonuses and events"],
  ["method", "Pros & cons", "info", "Strengths, weaknesses and data notes"],
  ["leadership", "Leadership", "medal", "Directors and key management"],
  ["plans", "Plans", "medal", "Compare Basic, Silver and Gold"],
];

/** The sections to list: Leadership only when the report shows it. */
export const navFor = (leadershipShown: boolean): NavItem[] => NAV.filter(([id]) => id !== "leadership" || leadershipShown);

/** Where arrow keys move inside the panel's grid of `n` items laid out in `cols` columns: Left/Right step one (wrapping), Up/Down step a row (staying put at the
 *  top and bottom edge), Home/End jump to the ends. Any other key returns the same index. */
export function moveIndex(i: number, key: string, n: number, cols: number): number {
  if (n <= 0) return -1;
  const c = Math.max(1, cols), last = n - 1;
  switch (key) {
    case "ArrowRight": return i >= last ? 0 : i + 1;
    case "ArrowLeft": return i <= 0 ? last : i - 1;
    case "ArrowDown": return i + c <= last ? i + c : i;
    case "ArrowUp": return i - c >= 0 ? i - c : i;
    case "Home": return 0;
    case "End": return last;
    default: return i;
  }
}

/** The number of columns a CSS grid is drawing, read from its computed template (falls back to 1). */
export const columnsOf = (template: string): number => Math.max(1, template.split(" ").filter(Boolean).length);
