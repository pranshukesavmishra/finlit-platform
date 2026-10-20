import { describe, expect, it } from "vitest";
import type { SearchRow } from "./api";
import { makeMatcher, matchNames, namesFrom } from "./holdingsMatch";

const R = (s: string, n: string, b: string | null, nse?: string): SearchRow => [s, n, b, true, nse] as SearchRow;
const INDEX: SearchRow[] = [
  R("RELIANCE", "Reliance Industries Ltd.", "500325"), R("TCS", "Tata Consultancy Services Ltd.", "532540"), R("HDFCBANK", "HDFC Bank Ltd.", "500180"),
  R("HDFCLIFE", "HDFC Life Insurance Company Ltd.", "540777"), R("LT", "Larsen & Toubro Ltd.", "500510"), R("M&M", "Mahindra & Mahindra Ltd.", "500520"),
  R("TATAMOTORS", "Tata Motors Ltd.", "500570"), R("TATASTEEL", "Tata Steel Ltd.", "500470"), R("TATA", "Tata Sons Ltd", null),
  R("ITC", "ITC Ltd.", "500875"), R("INFY", "Infosys Ltd.", "500209"), R("SBIN", "State Bank of India", "500112", "SBIN"),
  R("BAJAJ-AUTO", "Bajaj Auto Ltd.", "532977"), R("BAJFINANCE", "Bajaj Finance Ltd.", "500034"), R("ZOMATO", "Zomato Ltd.", null, "ZOMATO"),
];

describe("makeMatcher", () => {
  it("is undefined for an empty index", () => { expect(makeMatcher([])).toBeUndefined(); });
  const m = makeMatcher(INDEX)!;
  it("matches by ticker, case-insensitive", () => { expect(m("reliance")).toBe(true); expect(m("TCS")).toBe(true); expect(m("M&M")).toBe(true); expect(m("BAJAJ-AUTO")).toBe(true); });
  it("matches by BSE code and NSE code", () => { expect(m("500325")).toBe(true); expect(m("999999")).toBe(false); });
  it("matches full and short names", () => {
    for (const n of ["Reliance Industries Ltd", "Reliance Industries Limited", "RELIANCE INDUSTRIES", "Larsen & Toubro", "Larsen and Toubro Limited", "Mahindra & Mahindra", "State Bank of India", "HDFC Bank"]) expect(m(n), n).toBe(true);
  });
  it("handles broker suffixes", () => { for (const n of ["TCS-EQ", "RELIANCE EQ", "INFY.NS", "NSE:ITC", "SBIN - BE", "ZOMATO-EQ"]) expect(m(n), n).toBe(true); });
  it("rejects funds, ETFs, bonds and junk", () => {
    for (const n of ["Axis Bluechip Fund - Direct Growth", "Nippon India ETF Nifty BeES", "SBI Small Cap Fund", "7.26% GOI 2033", "Tata Digital India Fund", "Total", "", "   "]) expect(m(n), n).toBe(false);
  });
  it("short prefix of a name is not enough (min length 4) but a real prefix is", () => {
    expect(m("Tat")).toBe(false);
    expect(m("Infosys")).toBe(true);
  });
  it("does not confuse HDFC Bank and HDFC Life", () => {
    const r = matchNames(["HDFC Bank", "HDFC Life Insurance"], INDEX);
    expect(r.found.map((f) => f.symbol)).toEqual(["HDFCBANK", "HDFCLIFE"]);
  });
});

describe("matchNames", () => {
  it("splits found and missing, preserving order and input", () => {
    const r = matchNames(["Tata Motors Ltd", "No Such Co", "ITC-EQ"], INDEX);
    expect(r.found).toEqual([{ input: "Tata Motors Ltd", symbol: "TATAMOTORS", name: "Tata Motors Ltd." }, { input: "ITC-EQ", symbol: "ITC", name: "ITC Ltd." }]);
    expect(r.missing).toEqual(["No Such Co"]);
  });
  it("an ambiguous prefix picks the first (largest) company", () => {
    expect(matchNames(["Tata"], INDEX).found[0].symbol).toBe("TATA");
    expect(matchNames(["Bajaj"], INDEX).found[0]?.symbol).toBe("BAJAJ-AUTO");
  });
  it("empty inputs", () => { expect(matchNames([], INDEX)).toEqual({ found: [], missing: [] }); expect(matchNames(["TCS"], [])).toEqual({ found: [], missing: ["TCS"] }); });
});

describe("namesFrom (pasted text)", () => {
  const m = makeMatcher(INDEX);
  it("one per line", () => { expect(namesFrom("Reliance\nTCS\nInfosys")).toEqual(["Reliance", "TCS", "Infosys"]); });
  it("csv with header", () => { expect(namesFrom("Symbol,Qty\nTCS,4\nITC,5", m)).toEqual(["TCS", "ITC"]); });
  it("comma-separated single line is not a table: each ticker kept", () => {
    expect(namesFrom("TCS, INFY, ITC", m).sort()).toEqual(["INFY", "ITC", "TCS"]);
  });
  it("a one-column list with a heading drops the heading", () => { expect(namesFrom("Symbol\nTCS\nINFY", m)).toEqual(["TCS", "INFY"]); });
});
