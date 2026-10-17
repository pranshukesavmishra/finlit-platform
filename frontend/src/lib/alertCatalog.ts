// Everything an alert can watch. Mirrors backend/finlit/alertengine.py (a test keeps the metric keys identical).
export type Op = "above" | "below" | "event";
export type Group = "Price & momentum" | "Technical signals" | "Valuation" | "Quality & growth" | "FinLit score" | "Results & ownership" | "News & filings";
export type Metric = { label: string; unit: string; group: Group; live: boolean; tier: "basic" | "silver"; ops: Op[]; hint: string; sample: number; text?: string };

export const METRICS: Record<string, Metric> = {
  price: { label: "Price", unit: "₹", group: "Price & momentum", live: true, tier: "basic", ops: ["above", "below"], hint: "The last traded price. Checked every few minutes while the market is open.", sample: 0 },
  change_pct: { label: "Day change", unit: "%", group: "Price & momentum", live: true, tier: "basic", ops: ["above", "below"], hint: "Today's move against yesterday's close. Use a negative number for a fall.", sample: 3 },
  move_abs: { label: "Move in a day (either way)", unit: "%", group: "Price & momentum", live: true, tier: "basic", ops: ["above"], hint: "Tell me when it moves this much in a day, up or down.", sample: 5 },
  volume_x: { label: "Volume vs 20-day average", unit: "×", group: "Price & momentum", live: false, tier: "basic", ops: ["above"], hint: "A volume spike: today's traded volume as a multiple of the 20-day average.", sample: 3 },
  from_high52: { label: "Below 52-week high", unit: "%", group: "Price & momentum", live: false, tier: "basic", ops: ["below"], hint: "How far the price sits under its 52-week high. 0 means a fresh high.", sample: 2 },
  from_low52: { label: "Above 52-week low", unit: "%", group: "Price & momentum", live: false, tier: "basic", ops: ["below"], hint: "How far the price sits above its 52-week low. 0 means a fresh low.", sample: 3 },
  return_1m: { label: "1-month return", unit: "%", group: "Price & momentum", live: false, tier: "silver", ops: ["above", "below"], hint: "Price change over the last month.", sample: 10 },
  return_1y: { label: "1-year return", unit: "%", group: "Price & momentum", live: false, tier: "silver", ops: ["above", "below"], hint: "Price change over the last year.", sample: 30 },
  rsi14: { label: "RSI (14)", unit: "", group: "Technical signals", live: false, tier: "basic", ops: ["above", "below"], hint: "Relative strength index. Below 30 is often read as oversold, above 70 as overbought.", sample: 30 },
  ema50_gap: { label: "Price vs 50-day average", unit: "%", group: "Technical signals", live: false, tier: "silver", ops: ["above", "below"], hint: "How far the price is from its 50-day moving average. 0 means it crosses the average.", sample: 0 },
  ema200_gap: { label: "Price vs 200-day average", unit: "%", group: "Technical signals", live: false, tier: "silver", ops: ["above", "below"], hint: "How far the price is from its 200-day moving average. 0 means it crosses the average.", sample: 0 },
  pe: { label: "P/E", unit: "×", group: "Valuation", live: false, tier: "silver", ops: ["above", "below"], hint: "Price relative to earnings.", sample: 20 },
  pb: { label: "P/B", unit: "×", group: "Valuation", live: false, tier: "silver", ops: ["above", "below"], hint: "Price relative to book value.", sample: 3 },
  dividend_yield: { label: "Dividend yield", unit: "%", group: "Valuation", live: false, tier: "silver", ops: ["above", "below"], hint: "Yearly dividend as a share of the price.", sample: 2 },
  market_cap: { label: "Market cap", unit: "Cr", group: "Valuation", live: false, tier: "silver", ops: ["above", "below"], hint: "Total company value in crore rupees.", sample: 10000 },
  roe: { label: "ROE", unit: "%", group: "Quality & growth", live: false, tier: "silver", ops: ["above", "below"], hint: "Return on equity.", sample: 15 },
  roce: { label: "ROCE", unit: "%", group: "Quality & growth", live: false, tier: "silver", ops: ["above", "below"], hint: "Return on capital employed.", sample: 15 },
  operating_margin: { label: "Operating margin", unit: "%", group: "Quality & growth", live: false, tier: "silver", ops: ["above", "below"], hint: "Operating profit as a share of sales.", sample: 15 },
  debt_to_equity: { label: "Debt to equity", unit: "×", group: "Quality & growth", live: false, tier: "silver", ops: ["above", "below"], hint: "Borrowings relative to shareholders' money.", sample: 1 },
  overall: { label: "FinLit score", unit: "", group: "FinLit score", live: false, tier: "silver", ops: ["above", "below"], hint: "The overall 0–100 FinLit score.", sample: 70 },
  pillar_quality: { label: "Quality score", unit: "", group: "FinLit score", live: false, tier: "silver", ops: ["above", "below"], hint: "The Quality pillar, 0–100.", sample: 70 },
  pillar_growth: { label: "Growth score", unit: "", group: "FinLit score", live: false, tier: "silver", ops: ["above", "below"], hint: "The Growth pillar, 0–100.", sample: 70 },
  pillar_profitability: { label: "Profitability score", unit: "", group: "FinLit score", live: false, tier: "silver", ops: ["above", "below"], hint: "The Profitability pillar, 0–100.", sample: 70 },
  pillar_balance: { label: "Balance-sheet score", unit: "", group: "FinLit score", live: false, tier: "silver", ops: ["above", "below"], hint: "The Balance-sheet pillar, 0–100.", sample: 70 },
  pillar_technical: { label: "Technical score", unit: "", group: "FinLit score", live: false, tier: "silver", ops: ["above", "below"], hint: "The Technical pillar, 0–100.", sample: 60 },
  q_net_profit: { label: "Net profit (latest quarter)", unit: "Cr", group: "Results & ownership", live: false, tier: "silver", ops: ["above", "below"], hint: "Net profit of the newest reported quarter, in crore rupees. Checked when new results are loaded.", sample: 1000 },
  q_revenue: { label: "Revenue (latest quarter)", unit: "Cr", group: "Results & ownership", live: false, tier: "silver", ops: ["above", "below"], hint: "Revenue of the newest reported quarter, in crore rupees.", sample: 10000 },
  promoter_chg: { label: "Promoter holding change", unit: "pp", group: "Results & ownership", live: false, tier: "silver", ops: ["above", "below"], hint: "Change in promoter holding against the previous quarter, in percentage points. Use a negative number for a fall.", sample: 1 },
  fii_chg: { label: "FII holding change", unit: "pp", group: "Results & ownership", live: false, tier: "silver", ops: ["above", "below"], hint: "Change in foreign institutional holding against the previous quarter, in percentage points.", sample: 1 },
  result_soon: { label: "Results due within (days)", unit: "days", group: "Results & ownership", live: false, tier: "basic", ops: ["event"], hint: "Tell me when a results date or board meeting for the company is announced inside this many days.", sample: 7 },
  news_keyword: { label: "News or filing mentions", unit: "", group: "News & filings", live: false, tier: "basic", ops: ["event"], hint: "Tell me when a new headline or filing for the company contains this word or phrase.", sample: 0, text: "e.g. dividend, buyback, acquisition" },
  new_filing: { label: "Any new filing", unit: "", group: "News & filings", live: false, tier: "silver", ops: ["event"], hint: "Tell me about every new exchange filing or document for the company.", sample: 0 },
};
export const GROUPS: Group[] = ["Price & momentum", "Technical signals", "Valuation", "Quality & growth", "FinLit score", "Results & ownership", "News & filings"];
export const isEvent = (k: string) => METRICS[k]?.ops[0] === "event";
export const LIMITS: Record<string, number> = { basic: 3, silver: 30, gold: 300 };

const n = (v: number) => (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-IN") : String(+v.toFixed(2)));
export function fmtValue(metric: string, v: number | null | undefined): string {
  if (v == null || !METRICS[metric]) return "—";
  const u = METRICS[metric].unit, sign = v < 0 ? "−" : metric === "promoter_chg" || metric === "fii_chg" ? (v > 0 ? "+" : "") : "";
  const x = n(Math.abs(v));
  return u === "₹" ? `${sign}₹${x}` : u === "Cr" ? `${sign}₹${x} Cr` : u === "pp" ? `${sign}${x} pp` : u === "days" ? `${x} days` : u ? `${sign}${x}${u}` : `${sign}${x}`;
}
/** "RSI (14) rises above 30" */
export function describe(a: { metric: string; op: Op; value: number | null; keyword?: string | null }): string {
  const m = METRICS[a.metric]; if (!m) return a.metric;
  if (a.metric === "news_keyword") return `News or a filing mentions “${a.keyword}”`;
  if (a.metric === "new_filing") return "A new filing is published";
  if (a.metric === "result_soon") return `Results announced within ${a.value ?? 7} days`;
  if (a.metric === "move_abs") return `Moves ${fmtValue(a.metric, a.value)} or more in a day`;
  if (a.metric === "volume_x") return `Volume reaches ${fmtValue(a.metric, a.value)} its 20-day average`;
  if (a.metric === "from_high52") return `Falls ${fmtValue(a.metric, a.value)} below its 52-week high`;
  if (a.metric === "from_low52") return `Within ${fmtValue(a.metric, a.value)} of its 52-week low`;
  return `${m.label} ${a.op === "above" ? "rises to or above" : "falls to or below"} ${fmtValue(a.metric, a.value)}`;
}
/** How close a threshold alert is to firing, 0–100 (for the progress bar); null when it cannot be told. */
export function closeness(a: { metric: string; op: Op; value: number | null; lastValue: number | null; startValue?: number | null }): number | null {
  if (a.op === "event" || a.value == null || a.lastValue == null) return null;
  const hit = a.op === "above" ? a.lastValue >= a.value : a.lastValue <= a.value;
  if (hit) return 100;
  const gap = Math.abs(a.value - a.lastValue), base = Math.max(Math.abs(a.value), Math.abs(a.lastValue), 1e-9);
  return Math.max(2, Math.min(98, Math.round(100 - Math.min(1, gap / base) * 100)));
}
export const LIVE_NOTE = "Price alerts are checked every few minutes while the market is open. Everything else is checked on weekday evenings, once the day's data is in.";
