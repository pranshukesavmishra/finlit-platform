// The stock page's sections, for the sticky section bar and its "All sections" panel: id, name, icon and a one-line hint of what the section holds,
// plus the pure keyboard rule of the panel's grid. Leadership is listed only when the report says it is shown.
export type NavItem = [id: string, label: string, icon: string, hint: string];

export const NAV: NavItem[] = [
  ["prism", "Scores", "gauge", "The FinLit IQ and the FinLit Prism score, side by side"],
  ["business", "Company", "building", "What the company does and how it earns"],
  ["macro", "Macro outlook", "globe", "How the economy is moving for the sector: score, drivers and indicators"],
  ["notes", "Strengths & watch-outs", "notes", "Plain-language findings and what lifts or weighs on the score"],
  ["findings", "Key findings", "notes", "Every red flag, watch item and strength, each linking to its section"],
  ["price", "Price", "line", "Price chart, returns and technical levels"],
  ["quarter", "Quarter", "notes", "The latest quarter against a year ago"],
  ["financials", "Financials", "bars", "Profit and loss, balance sheet and cash flow by year"],
  ["trends", "Trends", "line", "How sales, profit and cash have moved"],
  ["charts", "Charts", "bars", "Price history, statements and ownership in charts"],
  ["ratios", "Ratios", "gauge", "Valuation, returns, margins and debt"],
  ["dupont", "DuPont analysis", "layers", "What drives return on equity"],
  ["earnings", "Earnings & cash", "coins", "Is the profit real, and is it turning into cash?"],
  ["ownership", "Ownership", "pie", "Promoters, institutions and the public"],
  ["peers", "Peers", "layers", "How the company compares with its peers"],
  ["sector", "Sector & peers", "activity", "Where its industry stands, and how the stock ranks inside it"],
  ["insights", "What to watch", "crown", "Triggers to watch and where the company fits"],
  ["segments", "Segments", "pie", "Where the revenue comes from"],
  ["dividends", "Dividends", "coins", "Dividends, splits, bonuses and events"],
  ["announcements", "Announcements", "notes", "Exchange announcements, routine filings hidden"],
  ["method", "Pros & cons", "info", "Pros, cons and how the Prism score has moved"],
  ["leadership", "Leadership", "medal", "Directors and key management"],
];

/** The first section of each reading group: the bar draws a thin separator before it. */
export const GROUP_START = new Set(["price", "quarter", "ratios", "ownership", "insights", "dividends", "method"]);

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
