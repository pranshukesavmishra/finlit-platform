// The Mutual Fund Screener's vocabulary: every filter's name, unit, preset chips and wording, in one place (docs/MF-FILTERS.md lists what is built).
// The SERVER owns what a filter means (backend/finlit/mfscreen/spec.py: field expressions, whitelists, histogram edges); this file only names things.
// Wording rule: describe, never advise. No buy / sell / hold / avoid / target / "best" anywhere in this file.
import { nf } from "./format";
import { aumText } from "./mf";

export type Unit = "%" | "₹ Cr" | "years" | "pp" | "x" | "";
export type Preset = { label: string; lo?: number; hi?: number };
export type NumDef = { key: string; label: string; unit: Unit; dec: number; presets: Preset[]; hint?: string; sign?: boolean };

const P = (label: string, lo?: number, hi?: number): Preset => ({ label, lo, hi });
const BANDS_1Y = [P("Negative", undefined, 0), P("0 to 8%", 0, 8), P("8 to 15%", 8, 15), P("Above 15%", 15)];
const BANDS_LONG = [P("Below 8%", undefined, 8), P("8 to 12%", 8, 12), P("12 to 15%", 12, 15), P("Above 15%", 15)];
const EXCESS = [P("Behind", undefined, 0), P("Ahead", 0), P("Ahead by 2+", 2), P("Ahead by 5+", 5)];

export const NUM: NumDef[] = [
  { key: "aum", label: "Fund size (AUM)", unit: "₹ Cr", dec: 0, presets: [P("Under 100", undefined, 100), P("100 to 500", 100, 500), P("500 to 2,000", 500, 2000), P("2,000 to 10,000", 2000, 10000), P("10,000 to 50,000", 10000, 50000), P("Above 50,000", 50000)],
    hint: "Average assets over the latest quarter (AMFI), all plans of the scheme together; the fund house's month-end net assets where AMFI lists none. Size says how big a fund is, not how good it is." },
  { key: "age", label: "Age", unit: "years", dec: 1, presets: [P("Under 1 year", undefined, 1), P("1 to 3", 1, 3), P("3 to 5", 3, 5), P("5 to 10", 5, 10), P("Over 10", 10)], hint: "Years from the launch date AMFI gives to the latest NAV." },
  { key: "aum_share", label: "Share of its category's size", unit: "%", dec: 2, presets: [], hint: "The fund's size as a share of its whole category's net assets in AMFI's monthly report." },
  { key: "na_chg", label: "Net assets, change over the stored months", unit: "%", dec: 1, sign: true, presets: [P("Growing", 5), P("Steady", -5, 5), P("Shrinking", undefined, -5)],
    hint: "Month-end net assets in the fund house's portfolio files (the latest three are kept): latest against the oldest of them." },
  { key: "r1d", label: "1 day change", unit: "%", dec: 2, sign: true, presets: [P("Down", undefined, 0), P("Up", 0)] },
  { key: "r1m", label: "1 month return", unit: "%", dec: 1, sign: true, presets: [], hint: "Stored for the largest funds only; the count under the slider says how many funds have it." },
  { key: "r6m", label: "6 month return", unit: "%", dec: 1, sign: true, presets: [], hint: "Stored for the largest funds only; the count under the slider says how many funds have it." },
  { key: "r1y", label: "1 year return", unit: "%", dec: 1, sign: true, presets: BANDS_1Y, hint: "Total change in NAV over one year." },
  { key: "r3y", label: "3 year return, per year", unit: "%", dec: 1, sign: true, presets: BANDS_LONG, hint: "Yearly rate (CAGR) over three years." },
  { key: "r5y", label: "5 year return, per year", unit: "%", dec: 1, sign: true, presets: BANDS_LONG, hint: "Yearly rate (CAGR) over five years." },
  { key: "sip3y", label: "SIP return, 3 years", unit: "%", dec: 1, sign: true, presets: BANDS_LONG, hint: "Yearly rate (XIRR) of the same amount put in every month for three years." },
  { key: "sip5y", label: "SIP return, 5 years", unit: "%", dec: 1, sign: true, presets: BANDS_LONG, hint: "Yearly rate (XIRR) of the same amount put in every month for five years." },
  { key: "ex1y", label: "1 year, against category median", unit: "pp", dec: 1, sign: true, presets: EXCESS, hint: "The fund's return minus the median of the same category and plan (percentage points). Needs three funds with a figure." },
  { key: "ex3y", label: "3 years, against category median", unit: "pp", dec: 1, sign: true, presets: EXCESS, hint: "The fund's yearly return minus the median of the same category and plan." },
  { key: "ex5y", label: "5 years, against category median", unit: "pp", dec: 1, sign: true, presets: EXCESS, hint: "The fund's yearly return minus the median of the same category and plan." },
  { key: "consist", label: "Months ahead of peers (last 36)", unit: "%", dec: 0, presets: [P("Under 45%", undefined, 45), P("45 to 55%", 45, 55), P("Above 55%", 55)], hint: "Share of the last 36 months in which the fund's return was above the peer median for that month." },
  { key: "cy1", label: "Calendar-year return, last full year", unit: "%", dec: 1, sign: true, presets: BANDS_1Y, hint: "Change in NAV from one December month-end to the next, for the last full calendar year." },
  { key: "cy2", label: "Calendar-year return, the year before", unit: "%", dec: 1, sign: true, presets: BANDS_1Y, hint: "Change in NAV from one December month-end to the next, two calendar years back." },
  { key: "cy3", label: "Calendar-year return, three years back", unit: "%", dec: 1, sign: true, presets: BANDS_1Y, hint: "Change in NAV from one December month-end to the next, three calendar years back." },
  { key: "up_m", label: "Biggest monthly gain (last 36)", unit: "%", dec: 1, sign: true, presets: [P("Up to 2%", undefined, 2), P("2 to 6%", 2, 6), P("6 to 10%", 6, 10), P("Over 10%", 10)], hint: "The largest single-month rise in NAV in the last 36 months. A big monthly gain also says the fund can swing a lot." },
  { key: "ter", label: "Expense ratio (TER)", unit: "%", dec: 2, presets: [P("Up to 0.5%", undefined, 0.5), P("0.5 to 1%", 0.5, 1), P("1 to 1.5%", 1, 1.5), P("Above 1.5%", 1.5)], hint: "Total expense ratio of the plan, percent a year (AMFI). The Direct plan has its own, lower figure." },
  { key: "ter_rel", label: "TER against category median", unit: "x", dec: 2, presets: [P("Below 0.7×", undefined, 0.7), P("0.7 to 1×", 0.7, 1), P("1 to 1.3×", 1, 1.3), P("Above 1.3×", 1.3)], hint: "The plan's TER divided by the median TER of the same category and plan. Needs three funds with a figure." },
  { key: "ter_gap", label: "Regular minus Direct TER", unit: "pp", dec: 2, presets: [P("Under 0.5", undefined, 0.5), P("0.5 to 1", 0.5, 1), P("Above 1", 1)], hint: "How much more the Regular plan of the same scheme charges a year." },
  { key: "fee_share", label: "Fee share of return", unit: "%", dec: 0, presets: [P("Under 10%", undefined, 10), P("10 to 25%", 10, 25), P("Above 25%", 25)], hint: "TER ÷ (3-year return + TER). Most useful for debt funds, where a fee can be a large part of what the fund earned." },
  { key: "exit_pct", label: "Exit load, highest percentage", unit: "%", dec: 2, presets: [], hint: "Read from the exit-load wording of the fund house (0 when it says nil)." },
  { key: "vol1", label: "Volatility, 1 year", unit: "%", dec: 1, presets: [P("Under 5%", undefined, 5), P("5 to 12%", 5, 12), P("12 to 20%", 12, 20), P("Above 20%", 20)], hint: "Annualised: standard deviation of the last 12 month-end returns × √12." },
  { key: "vol3", label: "Volatility, 3 years", unit: "%", dec: 1, presets: [P("Under 5%", undefined, 5), P("5 to 12%", 5, 12), P("12 to 20%", 12, 20), P("Above 20%", 20)], hint: "Annualised: standard deviation of the last 36 month-end returns × √12." },
  { key: "vol_rel", label: "Volatility against category median", unit: "x", dec: 2, presets: [P("Below 0.9×", undefined, 0.9), P("0.9 to 1.1×", 0.9, 1.1), P("Above 1.1×", 1.1)], hint: "The fund's 3-year volatility divided by the median of the same category and plan. Below 1 means it moved less than most peers. Needs three funds with a figure." },
  { key: "down_dev", label: "Downside deviation, 3 years", unit: "%", dec: 1, presets: [P("Under 2%", undefined, 2), P("2 to 6%", 2, 6), P("6 to 10%", 6, 10), P("Above 10%", 10)], hint: "Like volatility, but only the months that fell count: root mean square of the falls in the last 36 months × √12. 0 when no month fell." },
  { key: "fall", label: "Biggest fall, 36 months", unit: "%", dec: 1, presets: [P("Under 5%", undefined, 5), P("5 to 15%", 5, 15), P("15 to 30%", 15, 30), P("Over 30%", 30)], hint: "The largest drop from a month-end NAV to a later month-end NAV in the last 36 months." },
  { key: "worst_m", label: "Worst month (loss)", unit: "%", dec: 2, presets: [P("No falling month", undefined, 0), P("Up to 0.5%", undefined, 0.5), P("0.5 to 2%", 0.5, 2), P("2 to 5%", 2, 5), P("Over 5%", 5)], hint: "The worst single month in the last 36 as a loss; 0 when no month fell." },
  { key: "worst_12m", label: "Worst 12 months (loss)", unit: "%", dec: 1, presets: [P("Up to 1%", undefined, 1), P("1 to 5%", 1, 5), P("5 to 15%", 5, 15), P("Over 15%", 15)], hint: "The worst rolling year in the last 4 years as a loss; 0 when no year fell." },
  { key: "neg_share", label: "Months with a fall", unit: "%", dec: 0, presets: [P("None", undefined, 0), P("Up to 10%", undefined, 10), P("10 to 25%", 10, 25), P("Over 25%", 25)], hint: "Share of the last 36 months in which the fund's NAV fell." },
  { key: "below_high", label: "Time below previous high", unit: "%", dec: 0, presets: [P("Under 25%", undefined, 25), P("25 to 50%", 25, 50), P("Over 50%", 50)], hint: "Share of the last 36 month-ends that closed below an earlier month-end high." },
  { key: "down_cap", label: "Downside capture", unit: "", dec: 0, presets: [P("Under 90", undefined, 90), P("90 to 100", 90, 100), P("Above 100", 100)], hint: "The fund's average return in the months its peers fell, as a percentage of the peers' average then. Below 100 means it fell less than peers." },
  { key: "sharpe", label: "Sharpe ratio", unit: "", dec: 2, sign: true, presets: [P("Below 0.5", undefined, 0.5), P("0.5 to 1", 0.5, 1), P("Above 1", 1)], hint: "(3-year return − 6%) ÷ 3-year volatility. The 6% is an assumed risk-free rate, the same one the head-to-head page uses." },
  { key: "eq_pct", label: "Equity share of net assets", unit: "%", dec: 0, presets: [P("Under 10%", undefined, 10), P("10 to 25%", 10, 25), P("25 to 40%", 25, 40), P("40 to 65%", 40, 65), P("65 to 80%", 65, 80), P("Above 80%", 80)] },
  { key: "debt_pct", label: "Debt share of net assets", unit: "%", dec: 0, presets: [] },
  { key: "cash_pct", label: "Cash share of net assets", unit: "%", dec: 1, presets: [] },
  { key: "other_pct", label: "Other share of net assets", unit: "%", dec: 1, presets: [] },
  { key: "n_hold", label: "Number of holdings", unit: "", dec: 0, presets: [P("Under 25", undefined, 25), P("25 to 50", 25, 50), P("50 to 100", 50, 100), P("Over 100", 100)] },
  { key: "top10", label: "Top-10 concentration", unit: "%", dec: 0, presets: [P("Under 30%", undefined, 30), P("30 to 50%", 30, 50), P("50 to 70%", 50, 70), P("Above 70%", 70)], hint: "Share of net assets in the ten largest holdings (cash left out)." },
  { key: "max_hold", label: "Largest single holding", unit: "%", dec: 1, presets: [P("Under 5%", undefined, 5), P("5 to 10%", 5, 10), P("Above 10%", 10)] },
  { key: "cf_aum_mom", label: "Category net assets, month on month", unit: "%", dec: 1, sign: true, presets: [], hint: "Change in the whole category's net assets against the month before (AMFI's monthly report)." },
  { key: "cf_aum_yoy", label: "Category net assets, year on year", unit: "%", dec: 1, sign: true, presets: [] },
  { key: "cf_folio_mom", label: "Category folios, month on month", unit: "%", dec: 1, sign: true, presets: [] },
  { key: "cf_share", label: "Category's share of the industry", unit: "%", dec: 1, presets: [P("Under 1%", undefined, 1), P("1 to 5%", 1, 5), P("Above 5%", 5)] },
];
export const NUM_BY: Record<string, NumDef> = Object.fromEntries(NUM.map((n) => [n.key, n]));

/** Text of a number in the unit of its field: "₹2,000 Cr", "+3.5%", "1.2 years". */
export function unitText(def: NumDef, v: number): string {
  const body = def.unit === "₹ Cr" ? aumText(v).replace(/^₹/, "").replace(" Cr", "") : nf(Math.abs(v), def.dec);
  const signed = def.sign && v > 0 ? "+" : v < 0 ? "−" : "";
  const num = def.unit === "₹ Cr" ? body : signed + body;
  return def.unit === "%" ? num + "%" : def.unit === "₹ Cr" ? "₹" + num + " Cr" : def.unit === "years" ? num + " yr" : def.unit === "pp" ? num + " pp" : def.unit === "x" ? num + "×" : num;
}
/** "3 to 12%", "above 12%", "up to 3%": the range as words, for chips. */
export function rangeText(def: NumDef, lo: number | null, hi: number | null): string {
  if (lo != null && hi != null) return `${unitText(def, lo)} to ${unitText(def, hi)}`;
  if (lo != null) return `${unitText(def, lo)} or more`;
  if (hi != null) return `up to ${unitText(def, hi)}`;
  return "any";
}

// ------------------------------------------------------------------------------------------------ option lists

export type Opt = { v: string; label: string; hint?: string };
export const TYPE_OPTS: Opt[] = [{ v: "equity", label: "Equity" }, { v: "debt", label: "Debt" }, { v: "hybrid", label: "Hybrid" }, { v: "solution", label: "Solution oriented" }, { v: "other", label: "Others" }];
export const CAP_OPTS: Opt[] = [{ v: "large", label: "Large" }, { v: "largemid", label: "Large & Mid" }, { v: "mid", label: "Mid" }, { v: "small", label: "Small" }, { v: "multiflexi", label: "Multi / Flexi" }];
export const STYLE_OPTS: Opt[] = [{ v: "active", label: "Active" }, { v: "passive", label: "Passive", hint: "Index funds and ETFs" }];
export const STRUCT_OPTS: Opt[] = [{ v: "open", label: "Open ended" }, { v: "close", label: "Close ended" }, { v: "interval", label: "Interval" }];
export const MAT_OPTS: Opt[] = [
  { v: "d1", label: "Up to 1 day" }, { v: "d91", label: "Up to 91 days" }, { v: "m3_6", label: "3 to 6 months" }, { v: "m6_12", label: "6 to 12 months" },
  { v: "y1_3", label: "1 to 3 years" }, { v: "y3_4", label: "3 to 4 years" }, { v: "y4_7", label: "4 to 7 years" }, { v: "y7p", label: "Over 7 years" },
];
export const HOUSE_OPTS: Opt[] = [{ v: "h1", label: "Under ₹1,000 Cr" }, { v: "h2", label: "₹1,000 to 25,000 Cr" }, { v: "h3", label: "₹25,000 to 1,00,000 Cr" }, { v: "h4", label: "Above ₹1,00,000 Cr" }];
export const PLAN_OPTS: Opt[] = [{ v: "Direct", label: "Direct" }, { v: "Regular", label: "Regular" }, { v: "Unspecified", label: "Unspecified" }];
export const OPTION_OPTS: Opt[] = [{ v: "Growth", label: "Growth" }, { v: "IDCW", label: "IDCW (payout, reinvestment)" }, { v: "Other", label: "Other" }];
export const INST_OPTS: Opt[] = [{ v: "fund", label: "Mutual fund" }, { v: "etf", label: "ETF" }];
export const STATUS_OPTS: Opt[] = [{ v: "active", label: "Still publishing" }, { v: "stopped", label: "Stopped publishing" }];
export const FRESH_OPTS: Opt[] = [{ v: "today", label: "NAV updated today" }, { v: "week", label: "Within 7 days" }];
export const BASIS_OPTS: Opt[] = [{ v: "q", label: "Quarterly average" }, { v: "m", label: "Month-end net assets", hint: "The fund house's portfolio file, used where AMFI lists no quarterly figure" }];
export const AUMRANK_OPTS: Opt[] = [{ v: "top5", label: "Top 5" }, { v: "top10", label: "Top 10" }, { v: "top25", label: "Top 25%" }, { v: "bottom25", label: "Bottom 25%" }];
export const RK_BANDS: Opt[] = [{ v: "top10", label: "Top 10" }, { v: "q1", label: "Q1 (top quarter)" }, { v: "q2", label: "Q2" }, { v: "q3", label: "Q3" }, { v: "q4", label: "Q4 (bottom quarter)" }];
export const EXIT_OPTS: Opt[] = [{ v: "none", label: "None" }, { v: "d7", label: "Up to 7 days" }, { v: "d30", label: "8 to 30 days" }, { v: "y1", label: "31 days to 1 year" }, { v: "y1p", label: "Above 1 year" }, { v: "unread", label: "Wording not readable" }];
export const PFDATE_OPTS: Opt[] = [{ v: "latest", label: "Latest month-end" }, { v: "prev", label: "One month older" }, { v: "older", label: "Older" }];
export const CFLOW_OPTS: Opt[] = [{ v: "pos", label: "Positive" }, { v: "neg", label: "Negative" }];
export const CSTREAK_OPTS: Opt[] = [{ v: "up", label: "Inflow 3 months in a row" }, { v: "down", label: "Outflow 3 months in a row" }];
export const CSIZE_OPTS: Opt[] = [{ v: "lt1", label: "Under 1% of industry" }, { v: "1to5", label: "1 to 5%" }, { v: "gt5", label: "Above 5%" }];
export const CHK_EACH: Opt[] = [
  { v: "ret", label: "Return above category median" }, { v: "ter", label: "Expense ratio below category median" }, { v: "fall", label: "Smaller fall than category median" },
  { v: "size", label: "Fund size at least ₹500 Cr" }, { v: "age", label: "At least 5 years old" },
];
export const TICK_FALL: Opt[] = [
  { v: "noneg36", label: "No falling month in 3 years", hint: "Every one of the last 36 month-ends was above the one before." },
  { v: "fallless", label: "Fell less than its category", hint: "Biggest fall in 36 months smaller than the category median." },
  { v: "worstless", label: "Worst year smaller than its category's", hint: "Worst rolling 12 months smaller than the category median." },
  { v: "fall10", label: "Biggest fall under 10%" },
];
export const TICK_DATA: Opt[] = [
  { v: "has_ter", label: "Has an expense ratio" }, { v: "has_exit", label: "Has a readable exit load" }, { v: "has_port", label: "Has a portfolio" },
  { v: "has_hist3", label: "Has a 3-year record" }, { v: "has_hist5", label: "Has a 5-year record" }, { v: "has_aum", label: "Has a fund size" },
];
export const TICK_LISTS: Opt[] = [{ v: "hot", label: "Hot funds", hint: "The 100 largest funds by size (the site's ready list)" }, { v: "opened", label: "Most opened on this site", hint: "The site's own open counter" }];

export const TAG_KIND_LABEL: Record<string, string> = { theme: "Sector & theme (India)", tech: "Technology & AI", global: "Global themes", factor: "Factor & strategy", index: "Index tracked (passive funds)" };

export const SORTS: { v: string; dir: "asc" | "desc"; label: string; gold?: boolean }[] = [
  { v: "aum", dir: "desc", label: "Fund size, largest first" }, { v: "r1y", dir: "desc", label: "1 year return, high to low" }, { v: "r3y", dir: "desc", label: "3 year return, high to low" },
  { v: "r5y", dir: "desc", label: "5 year return, high to low" }, { v: "sip3y", dir: "desc", label: "SIP return (3 years), high to low" }, { v: "sip5y", dir: "desc", label: "SIP return (5 years), high to low" },
  { v: "ter", dir: "asc", label: "Expense ratio, low to high" }, { v: "fall", dir: "asc", label: "Biggest fall, smallest first" }, { v: "rank3y", dir: "asc", label: "Rank in category (3 years), top first" },
  { v: "age", dir: "desc", label: "Age, oldest first" }, { v: "name", dir: "asc", label: "Name, A to Z" }, { v: "score", dir: "desc", label: "Health score, high to low (Gold)", gold: true },
];

/** Groups the spec lists that need data we do not hold. Shown, never hidden, never faked: each says why and which free route would fill it (spec section 15). */
export const COMING: { id: string; label: string; why: string; route: string }[] = [
  { id: "riskometer", label: "Risk-o-meter (scheme and benchmark)", why: "AMFI's feed does not answer from the live server and the fund houses publish it on their own pages.", route: "AMFI fund-performance file from a host AMFI accepts (F-A), then each house's monthly page (F-B)." },
  { id: "benchmark", label: "Benchmark", why: "Held for about half of the funds only; no verified list of index names yet.", route: "Fund-house statements, AMFI scheme benchmark files (F-D), NSE and BSE index lists (F-E)." },
  { id: "tracking", label: "Tracking error and difference", why: "Needs index history to compare each fund's NAV with.", route: "Daily fund NAV minus the index's total-return value (niftyindices.com, F-E)." },
  { id: "managers", label: "Fund managers", why: "Held for about 29% of fund families; no group of its own until more houses are read.", route: "Each house's monthly factsheet and scheme page (F-B, F-C)." },
  { id: "credit", label: "Credit rating mix (debt)", why: "The debt holdings' ratings are in the monthly portfolio files but are not read yet.", route: "Rating column of the portfolio file, share of AAA / sovereign (F-B, F-C)." },
  { id: "capmix", label: "Large, mid and small cap share of holdings", why: "Needs the half-yearly AMFI large / mid / small list joined to holdings by ISIN.", route: "AMFI half-yearly cap list (F-D), or Nifty 100 / Midcap 150 / Smallcap 250 constituents (F-E)." },
  { id: "pe", label: "Portfolio P/E, P/B, quality and health", why: "Needs holdings joined to the stock database's ratios by ISIN.", route: "Join disclosure holdings to company ratios (F-E where a stock has none)." },
  { id: "moves", label: "Recent moves in a stock", why: "Needs two stored month-ends of holdings; only the latest is kept per fund today.", route: "Keep every month's holdings from now on (F-G)." },
  { id: "score", label: "Health score, pillar scores and rank inside group", why: "The Mutual Fund Health Score is a Gold feature with its own screener.", route: "Use the Fund score screener (Gold)." },
  { id: "etfpanel", label: "ETF panel: traded value, premium or discount, 52-week range", why: "ETF price data exists but the panel is not built yet.", route: "Already stored in the ETF tables; next build." },
];
