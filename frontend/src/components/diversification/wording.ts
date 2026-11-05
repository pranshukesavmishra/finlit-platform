// Every sentence of the Diversification card is built here, so one test can scan them all. The card DESCRIBES how a list of stocks has moved; it never
// advises and never refers to anyone's money. Every weighted figure carries its basis ("if equal amounts" or "if sized by company value").
import type { AsOf, Diversification, Excluded, Horizon, Pair, TiltPart } from "./types";

export const MINUS = "−";
export const ARROW = "→";
export const BASIS_EQUAL = "if equal amounts";
export const BASIS_MCAP = "if sized by company value";
export const NOT_SAFETY = "It measures how spread out the list is, not how safe it is.";
export const SCORE_FORMULA = "Score = 60% co-movement + 40% sector spread.";
export const NEEDS_THREE = "The score needs at least 3 stocks with a year of prices";
export const NEEDS_THREE_NOTE = "Co-movement needs at least 3 stocks with a year of prices, so only the spread by count is shown.";
export const SCORE_ALWAYS_WEEKLY = "The score always uses weekly returns.";
export const HORIZONS: { id: Horizon; label: string }[] = [{ id: "weekly", label: "Weekly · 3 years" }, { id: "monthly", label: "Monthly · 5 years" }, { id: "yearly", label: "Yearly · indicative" }];
export const BANDS = [{ from: 0, to: 39, label: "Concentrated" }, { from: 40, to: 59, label: "Somewhat concentrated" }, { from: 60, to: 79, label: "Fairly spread" }, { from: 80, to: 100, label: "Widely spread" }];
export const SIDE_NOTE = "Based only on the names in your list. FinLit does not ask for amounts, so figures that need amounts show two neutral cases: equal amounts, or amounts sized by company value.";

export const num = (v: number, d = 2) => v.toFixed(d).replace("-", MINUS);
export const pct = (v: number, d = 1) => `${num(v, d)}%`;
export const signedPct = (v: number, d = 1) => `${v > 0 ? "+" : ""}${pct(v, d)}`;
export function ordinal(n: number): string {
  const r = n % 100;
  if (r >= 11 && r <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] || "th"}`;
}
export const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
/** 'Financial services' reads as 'financial services' inside a sentence; acronyms (FMCG) stay as they are. */
export const inSentence = (sector: string) => (/^[A-Z]{2,}/.test(sector) ? sector : sector.charAt(0).toLowerCase() + sector.slice(1));
export const nameOf = (d: Diversification, s: string) => d.names?.[s] || s;
export const listNames = (xs: string[]) => (xs.length < 2 ? xs.join("") : xs.length === 2 ? `${xs[0]} and ${xs[1]}` : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
export const corr = (v: number) => num(v, 2);

export const windowText = (a?: AsOf, h: Horizon = "weekly") => (a ? (h === "weekly" ? `weekly prices, ${a.label}` : h === "monthly" ? `month-end prices, ${a.label}` : `12-month returns at month-ends, ${a.label}`) : "");
/** The method line, verbatim from the addendum for the weekly view. */
export function methodLine(a?: AsOf, h: Horizon = "weekly"): string {
  const head = h === "weekly" ? `Weekly prices, ${a?.label ?? ""}` : h === "monthly" ? `Month-end prices, ${a?.label ?? ""}` : `Rolling 12-month returns at month-ends, ${a?.label ?? ""}`;
  return `${head}. Describes how these stocks have moved together in the past; it is information, not a recommendation, and these relationships can change.`;
}
export const yearsText = (h: Horizon) => (h === "weekly" ? "weekly returns over 3 years" : h === "monthly" ? "monthly returns over 5 years" : "yearly returns");

export function headlineSentence(d: Diversification): string {
  const h = d.headline; if (!h) return "";
  const top = d.spread.largestSector;
  const tail = top && top.count >= 2 ? `, and ${top.count} of them are in ${inSentence(top.name)}` : "";
  return `These ${d.included} stocks have moved like about ${h.effectiveStocksRounded} independent ones over the last 3 years${tail}.`;
}
export function horizonSentence(d: Diversification, h: Horizon): string {
  const e = d.headline; if (!e) return "";
  if (h === "yearly") return `Indicative: about ${Math.round(d.asOf?.effectiveObservations ?? 7)} years of data. On yearly returns these stocks have moved like about ${e.effectiveStocksRounded} independent ones.`;
  return `On ${yearsText(h)}, these stocks have moved like about ${e.effectiveStocksRounded} independent ones.`;
}
export const partCoNote = (d: Diversification) => `Moves like about ${d.headline!.effectiveStocksRounded} independent stocks out of ${d.included}.`;
export function coMoveCluster(d: Diversification): string {
  const c = d.clusters?.[0]; if (!c || c.symbols.length < 2) return "";
  const ns = c.symbols.map((s) => nameOf(d, s));
  return `${listNames(ns)} move ${c.avgCorrelation >= 0.75 ? "almost as one" : "closely together"}.`;
}
export const partCoText = (d: Diversification) => `${partCoNote(d)} ${coMoveCluster(d)}`.trim();
export function partSectorText(d: Diversification): string {
  const s = d.score!, top = d.spread.largestSector;
  const base = `About ${num(s.effectiveSectors, 1)} effective sectors out of 8 that score in full.`;
  return top && top.count >= 2 ? `${base} ${top.count} of the ${d.included} stocks are in ${inSentence(top.name)}.` : base;
}
export function spreadSentence(d: Diversification): string {
  const total = d.spread.stocks.length, [a, b] = d.spread.sectors;
  if (!a) return "";
  if (a.count === 1) return `Each of the ${total} stocks is in a different sector.`;
  return `${a.count} of the ${total} stocks are in ${inSentence(a.name)}${b && b.count >= 2 ? `, and ${b.count} in ${inSentence(b.name)}` : ""}.`;
}
export function sizeLine(d: Diversification): string {
  const z = d.spread.size;
  const base = `Size: ${z.Large} large ${z.Large === 1 ? "cap" : "caps"} · ${z.Mid} mid · ${z.Small} small`;
  return d.spread.sizeUnknown.length ? `${base} · ${d.spread.sizeUnknown.length} not ranked yet` : base;
}
export function groupLine(d: Diversification): string {
  const g = d.spread.groups;
  if (!g.length) return "Business groups: none of these stocks is in a tagged group.";
  return "Business groups: " + g.map((x) => `${x.name} ${x.symbols.length} (${x.symbols.map((s) => nameOf(d, s)).join(", ")})`).join(" · ");
}
export const unclassifiedNote = (d: Diversification) => (d.spread.unclassified.length ? `${plural(d.spread.unclassified.length, "stock has", "stocks have")} no sector label yet (${d.spread.unclassified.join(", ")}); they are counted together as one group named "Not classified".` : "");
export const clusterIntro = "Stocks whose weekly returns have an average correlation of 0.5 or more with each other.";
export const clusterIntroFor = (h: Horizon) => (h === "monthly" ? "Stocks whose monthly returns have an average correlation of 0.5 or more with each other." : clusterIntro);
export function otherStocks(d: Diversification): string {
  const inGroup = new Set((d.clusters || []).flatMap((c) => c.symbols)); const n = d.included - inGroup.size;
  if (!(d.clusters || []).length) return "No stocks move together closely enough to form a group: each moves more on its own.";
  return n <= 0 ? "Every stock is in a group." : `The other ${n} ${n === 1 ? "stock is" : "stocks are"} not in any group: each moves more on its own.`;
}
const rounded = (x: number) => Math.round(x);
export function recentSentence(d: Diversification): string {
  const r = d.recentVsLongRun; if (!r) return "";
  const a = rounded(r.recent.effectiveStocks), b = rounded(r.longRun.effectiveStocks);
  const first = a === b ? `Over the last year these stocks have moved like about ${a} independent ones, the same as over 3 years.` : `Over the last year these stocks have moved like about ${a} independent ones, against about ${b} over 3 years.`;
  const f = r.flagged;
  return `${first} ${f.length ? `${plural(f.length, "pair")} moved by 0.30 or more: ${f.map((p) => pairText(d, p)).join("; ")}.` : "No pair's correlation has changed by 0.30 or more."}`;
}
export const pairNames = (d: Diversification, p: [string, string]) => `${nameOf(d, p[0])} & ${nameOf(d, p[1])}`;
export const pairText = (d: Diversification, p: Pair) => `${pairNames(d, p.pair)} ${p.direction === "more" ? "moving together more than before" : "moving together less than before"} (${corr(p.longRun)} ${ARROW} ${corr(p.recent)})`;
export const recentFoot = (d: Diversification) => `3-year value ${ARROW} last-year value. A pair is flagged only when it moves by 0.30 or more and one of the two values is 0.50 or higher; ${d.recentVsLongRun?.flagged.length ? `${d.recentVsLongRun.flagged.length} ${d.recentVsLongRun.flagged.length === 1 ? "is" : "are"} flagged` : "none is"}.`;

export function riskSentence(d: Diversification, view: "equal" | "mcap", by: "sector" | "stock"): string {
  const rs = view === "equal" ? d.riskShare?.equal : d.riskShare?.mcap; if (!rs) return "";
  const lead = view === "equal" ? "If equal amounts were held" : "If sized by company value";
  if (by === "stock") { const t = rs.stocks[0]; return t ? `${lead}, ${nameOf(d, t.symbol)} would be ${pct(t.weightPct)} of the amount and ${pct(t.pct)} of the risk, the largest share of risk.` : ""; }
  const t = [...rs.sectors].sort((a, b) => b.pct - b.amountPct - (a.pct - a.amountPct))[0];
  if (!t || t.pct - t.amountPct < 1) return `${lead}, no sector's share of the risk would differ from its share of the amount by 1 point or more.`;
  return `${lead}, ${t.name} would be ${pct(t.amountPct)} of the amount but ${pct(t.pct)} of the risk.`;
}
export const basketLine = (label: string, vol: number, dd: number) => `${label}: swings of ${pct(vol)} a year, worst fall ${pct(dd)}`;
export const eachStockFoot = (d: Diversification) => `"Moves with the rest" is each stock's average correlation with the other ${Math.max(0, d.included - 1)}. "Fell more than NIFTY 50" counts NIFTY 50's ${d.stress?.worstWeeks ?? 10} worst weeks since ${d.asOf?.label.split(" – ")[0] ?? ""}.`;
export const fellText = (n: number, of: number) => `${n} of ${of} weeks`;

const LEAN: Record<string, [string, string]> = {
  "Growth & Profitability": ["leans towards faster growth", "leans towards slower growth"], Valuation: ["leans towards cheaper stocks", "leans towards more expensive stocks"],
  Quality: ["leans towards higher quality", "leans towards lower quality"], Risk: ["leans towards lower risk", "leans towards higher risk"],
  "Short-term technical view": ["leans towards uptrends", "leans towards downtrends"], "Long-term technical view": ["leans towards uptrends", "leans towards downtrends"],
};
export const tiltRead = (p: TiltPart) => (p.avgPercentile == null ? "no rated stock in the list" : p.lean === "typical" ? "close to typical" : (LEAN[p.part] || ["leans high", "leans low"])[p.lean === "high" ? 0 : 1]);
export const tiltPercentile = (p: TiltPart) => (p.avgPercentile == null ? "" : `${ordinal(p.avgPercentile)} percentile`);
export const tiltFoot = (universe: number) => `Each stock's percentile among the ${universe} companies Prism rates, averaged across the list. The shaded band (35th to 65th) reads as typical. Valuation: higher means cheaper. Risk: higher means lower risk.`;
export const notRatedNote = (xs: string[]) => (xs.length ? `${plural(xs.length, "stock is", "stocks are")} not rated by Prism yet (${xs.join(", ")}), so ${xs.length === 1 ? "it is" : "they are"} left out of the style tilt only.` : "");

export function excludedNotes(d: Diversification): string[] {
  return d.excluded.map((e: Excluded) => {
    const n = nameOf(d, e.symbol);
    if (e.reason === "history") return `${n}: Listed recently: needs 1 year of prices${e.weeks != null ? ` (${plural(e.weeks, "week")} on file)` : e.months != null ? ` (${plural(e.months, "month")} on file)` : ""}. It is counted in the spread by count and left out of the co-movement figures.`;
    if (e.reason === "noPrices") return `${n}: no price history on file yet. It is counted in the spread by count and left out of the co-movement figures.`;
    if (e.reason === "unknown") return `${e.symbol}: not in FinLit's company list, so it has no sector or prices here.`;
    return `${n}: its prices overlap the others for too few weeks to compare.`;
  });
}

/** A plain-text summary a reader can copy. Built only from the sentences above. */
export function summaryText(d: Diversification, h: Horizon): string {
  if (!d.score || !d.headline) return `${NEEDS_THREE_NOTE}\n${spreadSentence(d)}`;
  const lines = [`Diversification score ${d.score.value} · ${d.score.band}. Co-movement ${d.score.coMovement} · Sector spread ${d.score.sectorSpread}.`, NOT_SAFETY, headlineSentence(d), `Average correlation between pairs: ${corr(d.headline.avgCorrelation)}.`];
  if (d.market) lines.push(`Market sensitivity (beta to NIFTY 50): ${num(d.market.betaEqual)} (${BASIS_EQUAL}).`);
  lines.push(spreadSentence(d), ...(d.clusters || []).map((c) => `${listNames(c.symbols.map((s) => nameOf(d, s)))} tend to move together (average correlation ${corr(c.avgCorrelation)}).`), methodLine(d.asOf, h));
  return lines.filter(Boolean).join("\n");
}
