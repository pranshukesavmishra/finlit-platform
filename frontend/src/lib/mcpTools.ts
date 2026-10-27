// The tools the public MCP server offers, kept in step with the server by a backend test (backend/tests/test_mcp_page.py reads this file
// and compares it with the server's own tools/list), so the page never lists a tool that does not exist or hides one that does.

export type McpTool = { name: string; what: string; group: "Stocks" | "Markets" | "Funds" | "System" };

export const MCP_TOOLS: McpTool[] = [
  { name: "search_stocks", what: "Find a company by name or symbol", group: "Stocks" },
  { name: "get_stock_quote", what: "Price, day change, day and 52-week range, volume, market cap", group: "Stocks" },
  { name: "get_batch_quotes", what: "Prices for up to 20 companies at once", group: "Stocks" },
  { name: "get_company_profile", what: "Sector, industry, website, employees, business description", group: "Stocks" },
  { name: "get_financials", what: "Profit and loss, balance sheet and cash flow, quarterly or annual", group: "Stocks" },
  { name: "get_ratios", what: "Margins, returns and the other ratios the site shows, with history", group: "Stocks" },
  { name: "get_shareholding", what: "Promoter, FII, DII, government and public holding by quarter", group: "Stocks" },
  { name: "get_price_history", what: "Daily or weekly prices, up to five years", group: "Stocks" },
  { name: "get_finlit_score", what: "The FinLit score where the free site shows it, otherwise says it is a Silver feature", group: "Stocks" },
  { name: "get_quarter_results", what: "Who announced results for a quarter or a date", group: "Stocks" },
  { name: "get_results_calendar", what: "Who is due to announce results in the next days", group: "Stocks" },
  { name: "screen_stocks", what: "Filter companies on the free screener metrics", group: "Stocks" },
  { name: "get_market_overview", what: "Index levels and India economy headline figures", group: "Markets" },
  { name: "get_fii_dii_flows", what: "Daily FII and DII cash-market flows", group: "Markets" },
  { name: "get_ipo_calendar", what: "Upcoming, open, closed and listed issues", group: "Markets" },
  { name: "search_funds", what: "Find mutual fund schemes by name", group: "Funds" },
  { name: "get_fund_details", what: "One scheme: NAV, returns, fees, size", group: "Funds" },
  { name: "list_etfs", what: "Exchange-traded funds with price, NAV and returns", group: "Funds" },
  { name: "get_etf", what: "One ETF in full", group: "Funds" },
  { name: "get_data_freshness", what: "How recent each dataset is", group: "System" },
];

// Defaults of the server (MCP_RATE_PER_MINUTE, MCP_DAILY_CAP); a backend test keeps these equal to the server's.
export const MCP_LIMITS = { perMinute: 60, perDay: 1000 };

export const MCP_DISCLAIMER = "Describes the company's financial health from its filings and prices; not a recommendation. FinLit Ventures is a technology company and is not registered with SEBI or AMFI.";

export const MCP_TEST_PROMPT = "Using the FinLit tools, give me Reliance Industries' latest price with its date, and its revenue and net profit for the last four quarters. Say where any figure is missing.";

export const mcpEndpoint = (origin: string) => `${origin.replace(/\/$/, "")}/mcp`;
export const cursorConfig = (url: string) => JSON.stringify({ mcpServers: { finlit: { url } } }, null, 2);
export const claudeCodeCommand = (url: string) => `claude mcp add --transport http finlit ${url}`;
