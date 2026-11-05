// The single registry of the 22 platform tools: id, name, one-line tagline, lowest plan, real route and icon. The Tools & Research Hub on the Home page and every tile that stands for one of these tools read from here.
export type ToolTier = "free" | "silver" | "gold";
export type ToolId =
  | "stock-radar" | "score-screener" | "etf-explorer" | "fund-finder" | "fund-health-check"
  | "chart-studio" | "peer-compare" | "company-health-score" | "company-financials" | "deep-dive-report"
  | "fair-value-calculator" | "forecast-builder" | "finance-calculators" | "option-chain"
  | "watchlists" | "portfolio-check-up" | "alerts" | "compare-funds"
  | "theme-tracker" | "market-dashboard" | "newsroom" | "investor-circle";
export interface ToolMeta { id: ToolId; name: string; tagline: string; tier: ToolTier; route: string }

export const TOOL_ICONS: Record<ToolId, ToolMeta> = {
  "stock-radar": { id: "stock-radar", name: "Stock Radar", tagline: "Scan every listed stock", tier: "free", route: "/screener" },
  "score-screener": { id: "score-screener", name: "Score Screener", tagline: "Hunt by health score", tier: "gold", route: "/advanced-score-screener" },
  "etf-explorer": { id: "etf-explorer", name: "ETF Explorer", tagline: "Map ETFs by return and risk", tier: "free", route: "/etfs" },
  "fund-finder": { id: "fund-finder", name: "Fund Finder", tagline: "Shortlist mutual funds", tier: "free", route: "/funds" },
  "fund-health-check": { id: "fund-health-check", name: "Fund Health Check", tagline: "A 0–100 score for every fund", tier: "gold", route: "/fund-score-screener" },
  "chart-studio": { id: "chart-studio", name: "Chart Studio", tagline: "Price and financials together", tier: "free", route: "/graphs" },
  "peer-compare": { id: "peer-compare", name: "Peer Compare", tagline: "Spider chart strengths", tier: "free", route: "/compare" },
  "company-health-score": { id: "company-health-score", name: "Company Health Score", tagline: "Health out of 100", tier: "gold", route: "/prism" },
  "company-financials": { id: "company-financials", name: "Company Financials", tagline: "Every statement in one place", tier: "gold", route: "/premium/fundamentals" },
  "deep-dive-report": { id: "deep-dive-report", name: "Deep-Dive Report", tagline: "A printable one-pager", tier: "gold", route: "/premium/report" },
  "fair-value-calculator": { id: "fair-value-calculator", name: "Fair Value Calculator", tagline: "Step-by-step DCF, reverse DCF", tier: "gold", route: "/dcf" },
  "forecast-builder": { id: "forecast-builder", name: "Forecast Builder", tagline: "Where revenue could head", tier: "gold", route: "/outlook" },
  "finance-calculators": { id: "finance-calculators", name: "Finance Calculators", tagline: "Change one assumption", tier: "free", route: "/eps-calculator" },
  "option-chain": { id: "option-chain", name: "Option Chain", tagline: "OI, max pain, PCR", tier: "gold", route: "/premium/options" },
  "watchlists": { id: "watchlists", name: "Watchlists", tagline: "Keep every stock in sight", tier: "silver", route: "/watchlist" },
  "portfolio-check-up": { id: "portfolio-check-up", name: "Portfolio Check-Up", tagline: "How healthy are your holdings", tier: "silver", route: "/holdings" },
  "alerts": { id: "alerts", name: "Alerts", tagline: "Pinged when a level is hit", tier: "free", route: "/alerts" },
  "compare-funds": { id: "compare-funds", name: "Compare Funds", tagline: "Settle which fund wins", tier: "free", route: "/funds/compare" },
  "theme-tracker": { id: "theme-tracker", name: "Theme Tracker", tagline: "Spot themes the market backs", tier: "gold", route: "/sectors" },
  "market-dashboard": { id: "market-dashboard", name: "Market Dashboard", tagline: "Weekly bearings", tier: "gold", route: "/premium/markets" },
  "newsroom": { id: "newsroom", name: "Newsroom", tagline: "News and filings as they land", tier: "free", route: "/news" },
  "investor-circle": { id: "investor-circle", name: "Investor Circle", tagline: "Learn from other investors", tier: "free", route: "/forum" },
};
export const TOOL_IDS = Object.keys(TOOL_ICONS) as ToolId[];
export const TIER_LABEL: Record<ToolTier, string> = { free: "Free", silver: "Silver", gold: "Gold" };
