// Profit and revenue outlook: the company picker's quick picks and "last searched" list, and the plain-words key takeaways of a result. Pure, tested.
import { signedPct, type Outlook } from "./outlook";
import { fmtCr } from "./outlookChart";

/** The five companies offered on the landing page, in this order. */
export const QUICK_PICKS: { symbol: string; name: string }[] = [
  { symbol: "RELIANCE", name: "Reliance" }, { symbol: "TCS", name: "TCS" }, { symbol: "HDFCBANK", name: "HDFC Bank" }, { symbol: "INFY", name: "Infosys" }, { symbol: "ICICIBANK", name: "ICICI Bank" },
];
const KEY = "finlit.outlook.recent";
export const RECENT_MAX = 5;
const SYM = /^[A-Z0-9&._-]{1,24}$/;

/** The companies last opened here, newest first. Never throws: a blocked or full store just means an empty list. */
export function readRecent(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && SYM.test(x)).slice(0, RECENT_MAX) : [];
  } catch { return []; }
}
/** Puts a company first in the list (once), keeps the latest five, and returns the new list. */
export function pushRecent(symbol: string): string[] {
  const s = symbol.trim().toUpperCase();
  if (!SYM.test(s)) return readRecent();
  const next = [s, ...readRecent().filter((x) => x !== s)].slice(0, RECENT_MAX);
  try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* a private window: the list lasts for this visit only */ }
  return next;
}

/** "FY27" style label for the last estimated year. */
const lastYear = (d: Outlook) => d.forecast.years[d.forecast.years.length - 1];

/** What the result says, in a few plain lines: the change, the rate it rests on, what drives it, and how it differs from the FinLit model. Empty when there is no estimate. */
export function takeaways(d: Outlook, model: Outlook | null): string[] {
  const f = d.forecast, k = d.kind === "profit" ? "Profit" : "Revenue";
  if (!f.available || !f.base || !f.years.length) return [];
  const end = lastYear(d), n = f.years.length, base = f.base.valueCr;
  const out: string[] = [];
  const change = base > 0 ? ((end.valueCr / base) - 1) * 100 : null;
  out.push(change == null ? `${k} is estimated at ${fmtCr(end.valueCr)} for ${end.period}.`
    : n === 1 ? `${k} is estimated to ${change >= 0 ? "grow" : "fall"} ${signedPct(Math.abs(change), 1).replace("+", "")} in ${end.period}, from ${fmtCr(base)} to ${fmtCr(end.valueCr)}.`
      : `${k} is estimated at ${fmtCr(end.valueCr)} by ${end.period}, ${signedPct(change, 1)} on ${fmtCr(base)} over ${n} years.`);
  if (d.rate.ratePct != null) out.push(`It rests on a weighted growth rate of ${signedPct(d.rate.ratePct, 2).replace("+", "")} a year.`);
  const top = d.rate.rows.filter((r) => r.status === "ok" && r.contributionPts != null).sort((a, b) => Math.abs(b.contributionPts as number) - Math.abs(a.contributionPts as number))[0];
  if (top) out.push(`The biggest input is “${top.label}”, adding ${signedPct(top.contributionPts as number, 2)} points to the rate.`);
  if (d.mode === "custom") {
    const m = model?.forecast.available ? lastYear(model) : null;
    if (m && m.valueCr > 0) {
      const diff = (end.valueCr / m.valueCr - 1) * 100;
      out.push(Math.abs(diff) < 0.05 ? "Your weights give the same estimate as the FinLit model."
        : `Your estimate for ${end.period} is ${Math.abs(diff).toFixed(1)}% ${diff > 0 ? "higher" : "lower"} than the FinLit model's ${fmtCr(m.valueCr)}.`);
    }
  } else out.push("Choose “Set your own model” to see how different weights change this estimate.");
  if (d.rate.unavailable.length) out.push(`Left out for this company: ${d.rate.unavailable.join("; ")}. Their weight was shared across the other inputs.`);
  return out;
}
