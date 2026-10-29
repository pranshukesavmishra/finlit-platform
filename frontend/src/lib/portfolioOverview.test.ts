import { describe, expect, it } from "vitest";
import fx from "./__fixtures__/portfolioOverview.json";
import {
  BAND_CHIPS, MODEL_BANNER, TABS, blankWhy, bandCounts, columnsFor, csvName, isReady, modelFor, monthYear, nextTab, parsePeriod, parseTab, scoreOf, scoreWhy, sortLines, summarize,
  toCsv, visibleLines, withTab, type Line, type Overview,
} from "./portfolioOverview";

const silver = fx.silver as unknown as Overview, gold = fx.gold as unknown as Overview;
const lines = (o: Overview): Line[] => o.holdings.map((h) => ({ symbol: h.symbol, name: isReady(h) ? h.name : null, ov: h }));
const S = lines(silver), G = lines(gold);

describe("plan and model", () => {
  it("Silver sees the basic FinLit score, Gold only FinLit Prism, Basic none", () => {
    expect(modelFor("silver")).toBe("finlit"); expect(modelFor("gold")).toBe("prism"); expect(modelFor("basic")).toBeNull(); expect(modelFor("basic", true)).toBe("prism");
  });
  it("the banners are the founder's words", () => {
    expect(MODEL_BANNER.prism).toBe("Scores on this page use FinLit Prism, our advanced model: four fundamental parts (Fundamentals, Valuation, Quality, Risk) and two technical views (short and long term). Higher is better for the four parts; a high Risk score means lower risk.");
    expect(MODEL_BANNER.finlit).toBe("Scores on this page use the FinLit score (our basic model). Gold shows FinLit Prism, the advanced model.");
  });
});

describe("tab state in the address", () => {
  it("reads and writes ?tab= and ?period= and keeps other parameters", () => {
    expect(parseTab(null)).toBe("overview"); expect(parseTab("ratios")).toBe("ratios"); expect(parseTab("nonsense")).toBe("overview");
    expect(parsePeriod("quarter")).toBe("quarter"); expect(parsePeriod("x")).toBe("year");
    expect(withTab("", "overview", "year")).toBe("");
    expect(withTab("", "ratios", "year")).toBe("?tab=ratios");
    expect(withTab("?tab=ratios&x=1", "financials", "quarter")).toBe("?tab=financials&x=1&period=quarter");
    expect(withTab("?tab=financials&period=quarter", "ratios", "quarter")).toBe("?tab=ratios");      // the period belongs to Financials only
  });
  it("keyboard moves between the three tabs", () => {
    expect(TABS.map((t) => t.label)).toEqual(["Overview", "Ratios", "Financials"]);
    expect(nextTab("overview", "ArrowRight")).toBe("ratios"); expect(nextTab("financials", "ArrowRight")).toBe("overview"); expect(nextTab("overview", "ArrowLeft")).toBe("financials");
    expect(nextTab("ratios", "End")).toBe("financials"); expect(nextTab("ratios", "Home")).toBe("overview"); expect(nextTab("ratios", "a")).toBeNull();
  });
});

describe("columns per tab and plan", () => {
  it("Overview Silver: score and the five FinLit pillars; Gold: Prism score, four parts and two technical views, no pillars", () => {
    expect(columnsFor("overview", "finlit").map((c) => c.label)).toEqual(["Share", "Latest price", "Today (%)", "Market cap", "FinLit score", "Quality", "Growth", "Profit.", "Balance", "Technical"]);
    expect(columnsFor("overview", "prism").map((c) => c.label)).toEqual(["Share", "Latest price", "Today (%)", "Market cap", "Prism score", "Fundamentals", "Valuation", "Quality", "Risk", "Short term", "Long term"]);
    expect(columnsFor("overview", "prism").map((c) => c.label)).not.toContain("Growth");
  });
  it("Ratios and Financials columns follow the reference", () => {
    expect(columnsFor("ratios", "finlit").map((c) => c.label)).toEqual(["Share", "FinLit score", "Latest price", "Today (%)", "Market cap", "Dividend yield (%)", "P/E", "ROE (%)", "Debt to equity (x)", "P/BV (x)"]);
    expect(columnsFor("financials", "prism").map((c) => c.label)).toEqual(["Share", "Prism score", "Latest price", "Today (%)", "Year end", "Statement", "Net sales / revenue (₹ Cr)", "Other income (₹ Cr)", "Operating profit (₹ Cr)", "Interest paid (₹ Cr)", "Tax ratio (%)", "Net profit (₹ Cr)", "EPS (₹)"]);
    expect(columnsFor("financials", "prism", "quarter")[4].label).toBe("Quarter end");
  });
});

describe("scores and reasons", () => {
  const by = (o: Overview, sym: string) => o.holdings.find((h) => h.symbol === sym)!;
  it("the plan's score, its word and the shared colour band", () => {
    expect(scoreOf(by(silver, "SAMPLEIT"), "finlit")).toEqual({ value: 83, word: "Strong", band: "hi" });
    expect(scoreOf(by(silver, "RELIANCE"), "finlit").band).toBe("mid"); expect(scoreOf(by(silver, "SAMPLETEXT"), "finlit").band).toBe("lo");
    expect(scoreOf(by(gold, "RELIANCE"), "prism")).toEqual({ value: 71.4, word: "Healthy", band: "hi" });
    expect(scoreOf(by(gold, "SAMPLETEXT"), "prism").value).toBeNull();
  });
  it("Gold with no rating says so and a NOT RATED company shows the report's own reason", () => {
    expect(scoreWhy(by(gold, "SAMPLEPHARMA"), "prism")).toMatch(/^Not rated yet/);
    expect(scoreWhy(by(gold, "SAMPLETEXT"), "prism")).toBe("Only 3 years of reported history: Prism needs at least 5 years to rate a company.");
    expect(scoreWhy(by(gold, "SAMPLENEW"), "prism")).toMatch(/being prepared/); expect(scoreWhy(by(gold, "NOSUCHCO"), "prism")).toMatch(/does not list/);
    expect(scoreWhy(by(gold, "RELIANCE"), "prism")).toBeNull(); expect(scoreWhy(undefined, "prism")).toBe("Scores are loading.");
  });
  it("Silver rows carry no Prism field and Gold rows no FinLit block", () => {
    silver.holdings.filter(isReady).forEach((h) => expect(h.prism).toBeUndefined());
    gold.holdings.filter(isReady).forEach((h) => expect(h.finlit).toBeUndefined());
  });
  it("blank figures give their reason", () => {
    const bank = by(silver, "SAMPLEBANK"), loss = by(silver, "SAMPLETEXT");
    if (!isReady(bank) || !isReady(loss)) throw new Error("fixture");
    expect(blankWhy(bank, "debt_to_equity", "year")).toMatch(/^Not applicable to banks/);
    expect(blankWhy(bank, "operating_profit", "year")).toMatch(/banks/);
    expect(blankWhy(loss, "pe", "year")).toMatch(/^Loss-making/);
    expect(blankWhy(loss, "tax_ratio", "year")).toMatch(/not meaningful/);
    expect(blankWhy(bank, "pe", "year")).toBeNull();
  });
});

describe("the figures are the stock page's (Reliance, from the recorded fixtures)", () => {
  it("ratios and the latest full year", () => {
    const r = silver.holdings[0];
    if (!isReady(r)) throw new Error("fixture");
    expect(r.ratios.pe).toMatchObject({ value: 41.36, period: "As of 28 Sep 2026" }); expect(r.ratios.roe.value).toBe(6.93); expect(r.ratios.debt_to_equity.value).toBe(0.41);
    expect(r.ratios.dividend_yield.note).toMatch(/worked out by FinLit/);
    expect(r.financials.year).toMatchObject({ period: "FY26", periodEnd: "2026-03-31", revenue: { value: 524105 }, net_profit: { value: 43851 }, eps: { value: 32.4 }, finance_costs: { value: 6904 } });
    expect(r.financials.year.tax_ratio?.value).toBeCloseTo((10225 / 54076) * 100, 1);
    expect(r.financials.quarter.period).toBe("Jun 2026");
    expect(monthYear("2026-03-31")).toBe("Mar-26"); expect(monthYear(null)).toBeNull();
  });
});

describe("filter, sort, summary", () => {
  it("sorts by score with unscored and waiting shares last in either direction", () => {
    const col = columnsFor("overview", "finlit").find((c) => c.id === "score")!;
    expect(sortLines(S, col, -1).map((l) => l.symbol)).toEqual(["SAMPLEIT", "SAMPLEBANK", "RELIANCE", "SAMPLEPHARMA", "SAMPLETEXT", "NOSUCHCO", "SAMPLENEW"]);
    expect(sortLines(S, col, 1).map((l) => l.symbol).slice(-2)).toEqual(["NOSUCHCO", "SAMPLENEW"]);
    const share = columnsFor("overview", "finlit")[0];
    expect(sortLines(S, share, 1)[0].symbol).toBe("NOSUCHCO");
  });
  it("filters by colour chip and by text over name, symbol and sector", () => {
    expect(visibleLines(S, "", "hi", "finlit").map((l) => l.symbol)).toEqual(["SAMPLEBANK", "SAMPLEIT"]);
    expect(visibleLines(S, "", "na", "finlit").map((l) => l.symbol)).toEqual(["SAMPLENEW", "NOSUCHCO"]);
    expect(visibleLines(S, "software", null, "finlit").map((l) => l.symbol)).toEqual(["SAMPLEIT"]);
    expect(visibleLines(S, "banks", null, "finlit").map((l) => l.symbol)).toEqual(["SAMPLEBANK"]);
    expect(BAND_CHIPS.map((b) => b.label)).toEqual(["Green", "Orange", "Red", "Not scored"]);
  });
  it("summary: shares, equal-weighted average, colour mix, sectors", () => {
    const s = summarize(S, "finlit");
    expect(s.shares).toBe(7); expect(s.scored).toBe(5); expect(s.preparing).toBe(1); expect(s.unknown).toBe(1);
    expect(s.average).toBeCloseTo((51 + 74 + 83 + 51 + 38) / 5, 5);
    expect(s.bands).toEqual({ hi: 2, mid: 2, lo: 1, na: 2 }); expect(bandCounts(S, "finlit")).toEqual(s.bands);
    expect(s.sectors.length).toBe(5); expect(s.parts.map((p) => p.label)).toEqual(["Quality", "Growth", "Profit.", "Balance", "Technical"]);
    const g = summarize(G, "prism");
    expect(g.scored).toBe(3); expect(g.average).toBeCloseTo((71.4 + 64.2 + 83.9) / 3, 5); expect(g.parts.map((p) => p.label)).toEqual(["Fundamentals", "Valuation", "Quality", "Risk"]);
  });
});

describe("CSV per tab", () => {
  const rows = (t: string) => t.split("\n");
  it("names the file by tab and period", () => {
    expect(csvName("overview", "year")).toBe("FinLit-portfolio-overview.csv"); expect(csvName("financials", "quarter")).toBe("FinLit-portfolio-financials-latest-quarter.csv");
  });
  it("Overview CSV for Silver has pillars, for Gold the Prism parts and technical scores and no pillars", () => {
    const a = rows(toCsv(S, "overview", "finlit", "year")), b = rows(toCsv(G, "overview", "prism", "year"));
    expect(a[0]).toBe('"Symbol","Company","Sector","Latest price","Today (%)","Market cap","FinLit score","Quality","Growth","Profit.","Balance","Technical","Note"');
    expect(b[0]).toContain('"Prism score","Fundamentals","Valuation","Quality","Risk","Short term","Long term"'); expect(b[0]).not.toContain("Growth");
    expect(a).toHaveLength(8); expect(a[1].startsWith('"RELIANCE","Reliance Industries Ltd","Refineries & Marketing",1184,-1.21,1602252.58,51,')).toBe(true);
    expect(b[1]).toContain(",71.4,68.8,41.2,77.3,73.7,34.2,-22.4,");
  });
  it("Ratios and Financials CSV carry the stock page's numbers, and blanks with a reason in Note", () => {
    const r = rows(toCsv(S, "ratios", "finlit", "year")), f = rows(toCsv(S, "financials", "finlit", "year"));
    expect(r[1]).toContain(",0.51,41.36,6.93,0.41,2.86,"); expect(r[5]).toContain(',,'); // the loss-making company has no P/E
    expect(f[1]).toContain('"Mar-26"'); expect(f[1]).toContain(",524105,"); expect(f[1]).toContain(",43851,32.4,");
    expect(f.at(-2)!).toContain("being prepared"); expect(f.at(-1)!).toContain("does not list");
    const q = rows(toCsv(S, "financials", "finlit", "quarter"));
    expect(q[0]).toContain('"Quarter end"'); expect(q[1]).toContain('"Jun-26"');
  });
  it("a text that starts like a formula is stored as text", () => {
    const evil: Line[] = [{ symbol: "X", name: "=HYPERLINK(1)", ov: undefined }];
    expect(toCsv(evil, "overview", "finlit", "year")).toContain("\"'=HYPERLINK(1)\"");
  });
});

describe("compliance wording", () => {
  it("no buy, sell or hold language anywhere in the labels, banners, notes or CSV", () => {
    const text = JSON.stringify([MODEL_BANNER, TABS, columnsFor("overview", "prism"), columnsFor("ratios", "finlit"), columnsFor("financials", "finlit"), toCsv(G, "overview", "prism", "year"), toCsv(S, "ratios", "finlit", "year"), gold.holdings.filter(isReady).map((h) => [h.prism?.shortTerm?.word, h.prism?.longTerm?.word])]);
    expect(text).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate|target)\b/i);
  });
});
