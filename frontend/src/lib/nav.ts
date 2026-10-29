// The site's map, in one place. The header menus, the phone menu, the left rail of the product pages and the footer are all built from this list,
// so a page is named, grouped and ordered the same way everywhere. Each entry is [path, label, one line about it, icon].
// `gold` marks tools that need the Gold plan (shown as a small tag, never hidden: locked tools stay visible behind an unlock card).

export type NavItem = { to: string; label: string; sub: string; icon: string; gold?: boolean; end?: boolean };
export type NavGroup = { title?: string; items: NavItem[] };
export type NavSection = { id: string; label: string; wide?: boolean; groups: NavGroup[] };

const i = (to: string, label: string, sub: string, icon: string, o: { gold?: boolean; end?: boolean } = {}): NavItem => ({ to, label, sub, icon, ...o });

/** The five main headings, in the order people use them. */
export const SECTIONS: NavSection[] = [
  { id: "myfinlit", label: "Workspace", groups: [{ items: [
    i("/dashboard", "Dashboard", "Your stocks, alerts and scores in one place", "table"),
    i("/watchlist", "Watchlists", "Follow stocks in named lists", "wallet"),
    i("/holdings", "My portfolio", "Score and mix of the shares you hold", "pie"),
    i("/alerts", "Alerts", "Price, signals, scores and filings", "bell"),
  ] }] },
  { id: "research", label: "Research", wide: true, groups: [
    { title: "Find stocks", items: [
      i("/screener", "Stock screener", "Filter every listed company by size, valuation, growth and debt", "table"),
      i("/score-screener", "Advanced score screener", "Every listed company with its FinLit score and FinLit Prism rating, filtered by size, sector and both scores", "quality"),
      i("/query-builder", "Query builder", "Type a rule like P/E < 15, get the companies; save baskets", "notes"),
    ] },
    { title: "Analyse a company", items: [
      i("/research", "Company report", "A report for every listed company: score, financials, ratios", "search"),
      i("/compare", "Compare companies", "Two to four companies side by side, in charts", "compare"),
      i("/prism", "FinLit Prism", "A company's financial health rated in four parts, with a PDF", "layers", { gold: true }),
      i("/premium/report", "Premium reports", "The full written report on a company", "notes", { gold: true }),
    ] },
    { title: "Investment calculators", items: [
      i("/eps-calculator", "EPS & P/E calculator", "Estimate earnings per share and explore valuation multiples.", "gauge"),
      i("/dcf", "DCF valuation calculator", "Estimate intrinsic value using projected future cash flows.", "rupee", { gold: true }),
      i("/sip-calculator", "SIP calculator", "Project potential wealth creation through monthly investments.", "spark"),
    ] },
    { title: "Charts", items: [
      i("/graphs", "Chart builder", "Combine metrics in side-by-side charts", "bars", { end: true }),
      i("/graphs/advanced", "Correlation charts", "How two measures move together, with tested trend lines", "spark"),
    ] },
  ] },
  { id: "markets", label: "Markets", groups: [{ items: [
    i("/fii-dii", "FII & DII flows", "Institutional buying and selling, streaks and history", "bars"),
    i("/macro", "India economy", "Inflation, growth, interest rates and reserves", "activity"),
    i("/commodities", "Commodity prices", "Gold, silver, crude and metals: MCX, global and import parity", "activity"),
  ] }] },
  { id: "news", label: "News & events", groups: [{ items: [
    i("/results", "Results calendar", "Who reports quarterly results, and when", "calendar", { end: true }),
    i("/results/quarter", "Latest results", "Every company's newest quarter, newest first", "notes"),
    i("/ipo", "IPO calendar", "Issues open now, upcoming and listed", "activity"),
    i("/news", "News & filings", "Exchange filings and headlines", "notes"),
  ] }] },
  { id: "funds", label: "Funds", groups: [{ items: [
    i("/funds", "Mutual funds", "NAV, returns, fund size and risk for every scheme", "pie"),
    i("/etfs", "ETFs", "Exchange-traded funds: price, returns and risk", "bars"),
    i("/funds/insights", "Fund industry trends", "Industry assets, net flows and folios, month by month", "line"),
  ] }] },
];

/** Everything else, kept reachable under "More" in the header: the Gold dashboards, learning and community, and the company. */
export const MORE: NavSection = { id: "more", label: "More", groups: [
  { title: "Gold dashboards", items: [
    i("/premium/fundamentals", "Stock fundamentals", "Financials of any company, in tables and charts", "table", { gold: true }),
    i("/premium/markets", "Market events & index", "Index moves and the events behind them", "activity", { gold: true }),
    i("/premium/options", "Option chain", "Open interest, put-call ratio and max pain", "layers", { gold: true }),
  ] },
  { title: "Learn and community", items: [
    i("/forum", "Discussion forums", "Information and opinion only, moderated", "users"),
    i("/blog", "Insights & blog", "Research notes and explainers", "spark"),
    i("/glossary", "Glossary", "Terms in plain words, with formulas", "book"),
    i("/documents", "Documents", "Annual reports and presentations", "layers"),
    i("/mcp", "Connect AI assistants", "Free, read-only data for Claude, ChatGPT and Cursor", "spark"),
  ] },
  { title: "Company", items: [
    i("/services", "Services", "Portfolio reviews and financial planning", "wallet"),
    i("/about", "About FinLit", "Who we are and how we work", "users"),
    i("/why-we-exist", "Why we exist", "The problem we set out to fix", "quality"),
    i("/contact", "Contact", "Talk to the team", "notes"),
  ] },
] };
MORE.wide = true;

/** Pricing sits in the header on its own. */
export const PRICING: NavItem = i("/plans", "Pricing", "Free, Silver and Gold", "crown");

/** Does this address belong to the item (itself or a page under it)? `end` items match only themselves. */
export const isHere = (path: string, it: NavItem) => path === it.to || (!it.end && path.startsWith(it.to + "/"));
export const sectionHere = (path: string, s: NavSection) => s.groups.some((g) => g.items.some((it) => isHere(path, it)));
