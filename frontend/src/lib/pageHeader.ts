// What the page header (components/PageHeader.tsx) needs from the site map: a quick link is only ever an address the site really has,
// and it takes its name from lib/nav.ts, so a renamed page is renamed everywhere. Pages that are not in the menus are listed once in EXTRA.
import { MORE, PRICING, SECTIONS, type NavItem } from "./nav";

/** Short names for the buttons ("Basic Screener", not "Basic score screener"). Anything not listed uses its menu name. */
const SHORT: Record<string, string> = {
  "/screener": "Stock Screener", "/score-screener": "Basic Screener", "/advanced-score-screener": "Advanced Screener", "/query-builder": "Query Builder",
  "/fund-score-screener": "Fund Screener", "/research": "Company Report", "/compare": "Compare", "/prism": "FinLit Prism", "/outlook": "Outlook",
  "/premium/report": "Premium Reports", "/eps-calculator": "EPS Calculator", "/dcf": "DCF Calculator", "/sip-calculator": "SIP Calculator",
  "/graphs": "Chart Builder", "/graphs/advanced": "Correlation Charts", "/fii-dii": "FII & DII", "/macro": "India Economy", "/commodities": "Commodities",
  "/results": "Results Calendar", "/results/quarter": "Latest Results", "/ipo": "IPO Calendar", "/news": "News & Filings",
  "/funds/screener": "MF Screener", "/funds": "Mutual Funds", "/etfs": "ETFs", "/holdings": "Equity Portfolio", "/mf-portfolio": "MF Portfolio", "/watchlist": "Watchlists",
};
/** Pages that exist but are not in the menus. */
const EXTRA: Record<string, string> = {
  "/fund-score-screener": "Fund score screener", "/funds/compare": "Fund Compare", "/funds/insights": "Fund Trends", "/etfs/compare": "Compare ETFs",
  "/etfs/compare-index-funds": "ETF vs Index Fund", "/baskets": "My Baskets", "/plans": "Plans", "/faq": "FAQs", "/methodology/mf-score": "How the score works",
  "/premium": "Gold Dashboards", "/account": "Account", "/portfolio": "Portfolio Report", "/leadership-label": "Leadership Label",
};

const ALL: NavItem[] = [...SECTIONS, MORE].flatMap((s) => s.groups.flatMap((g) => g.items)).concat(PRICING);
const base = (to: string) => to.split(/[?#]/)[0].replace(/(.)\/+$/, "$1");

export type PhLink = string | { to: string; label?: string; primary?: boolean };
export type ResolvedLink = { to: string; label: string; primary: boolean };

/** The button for an address, or null when the site has no such page (it is then left out, never shown broken). */
export function resolveLink(l: PhLink): ResolvedLink | null {
  const o = typeof l === "string" ? { to: l } : l;
  const b = base(o.to);
  const it = ALL.find((x) => x.to === b);
  const label = ("label" in o && o.label) || SHORT[b] || it?.label || EXTRA[b];
  const dyn = /^\/(stocks|funds|etfs|outlook|prism)\/[^/]+$/.test(b);   // a company / fund page: needs a label from the caller
  if (!label || (!it && !(b in EXTRA) && !(dyn && ("label" in o && o.label)))) return null;
  return { to: o.to, label, primary: !!(typeof l !== "string" && l.primary) };
}
export const resolveLinks = (ls: PhLink[] = [], max = 4): ResolvedLink[] => ls.map(resolveLink).filter((x): x is ResolvedLink => !!x).slice(0, max);

/** A stat tile is shown only for a real value: not missing, not empty, not NaN, not a placeholder dash. */
export function realValue(v: unknown): boolean {
  if (v === null || v === undefined) return false;
  if (typeof v === "number") return Number.isFinite(v);
  if (typeof v === "string") { const t = v.trim(); return t !== "" && !/^[-–—?]+$/.test(t) && !/^(nan|null|undefined|n\/a)$/i.test(t); }
  return true;
}
