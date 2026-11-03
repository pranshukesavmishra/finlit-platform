import { describe, expect, it } from "vitest";
import { commitItems, initialDecisions, reviewCounts, rupees, pct1, shares, sizeOf, typeOf, sortHoldings, toCsv, type Fund, type Holding, type ReviewRow } from "./mfPortfolio";

const F = (code: number): Fund => ({ code, name: `Fund ${code}`, amc: "A", plan: "Direct", option: "Growth", active: true, navDate: "2026-10-29" });
const H = (id: string, o: Partial<Holding> = {}, score: number | null = null): Holding => ({
  id, code: 1, folio: "", units: 10, lots: [], name: `Fund ${id}`, amc: "A", plan: "Direct", option: "Growth", category: "c", categoryLabel: "Large Cap", active: true,
  nav: 10, navDate: "2026-10-29", navStale: false, navNote: null, invested: 80, investedWhy: null, current: 100, currentWhy: null, gain: 20, gainPct: 25, gainWhy: null, xirr: null, xirrWhy: "Add the purchase date",
  xirrKind: "cagr", returns: { r1y: 5, r3y: null, r5y: null, asOf: null, why: null }, ter: 0.5, terDate: null, terWhy: null, aum: 100, aumAsOf: null, aumWhy: null, weight: 50, weightWhy: null,
  score: { locked: score == null, final: score, label: score == null ? null : "Healthy", status: null, reason: null, runDate: null, parts: score == null ? null : { performance: score, risk: 50, cost: 60, quality: 70 }, inherited: null }, ...o,
});
const R = (i: number, status: ReviewRow["status"], o: Partial<ReviewRow> = {}): ReviewRow => ({ i, row: i + 2, name: "n", isin: "", status, reason: "", warnings: [], fund: null, candidates: [], units: 10, invested: 100, ...o });

describe("import review decisions", () => {
  const rows = [R(0, "matched", { fund: F(1) }), R(1, "choose", { candidates: [F(2), F(3)] }), R(2, "not_found"), R(3, "ignored"), R(4, "invalid"), R(5, "duplicate"), R(6, "matched", { fund: F(4), existing: true })];
  it("only matched rows start with a fund; nothing else is chosen for the member", () => {
    const d = initialDecisions(rows);
    expect(Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v.code]))).toEqual({ 0: 1, 1: null, 2: null, 3: null, 4: null, 5: null, 6: 4 });
    expect(commitItems(rows, d).map((x) => x.code)).toEqual([1, 4]);
  });
  it("a choice makes a row importable; skipped, ignored, invalid and repeated rows never are", () => {
    const d = initialDecisions(rows);
    d[1] = { code: 3, fund: F(3) };
    d[3] = { code: 9, fund: F(9) };                       // even a tampered decision on an ignored row is not imported
    expect(commitItems(rows, d).map((x) => x.code)).toEqual([1, 3, 4]);
    expect(commitItems(rows, d, new Set([0])).map((x) => x.code)).toEqual([3, 4]);
    expect(commitItems(rows, d)[0]).toEqual({ code: 1, folio: "", units: 10, invested: 100, boughtOn: null });
  });
  it("counts what is ready, what still needs a choice and what is already held", () => {
    expect(reviewCounts(rows, initialDecisions(rows))).toEqual({ ready: 2, needChoice: 2, existing: 1 });
  });
});

describe("sorting", () => {
  const a = H("a", { current: 300, name: "Beta" }, 80), b = H("b", { current: null, name: "alpha" }, 60), c = H("c", { current: 100, name: "Gamma" }), d = H("d", { current: 200, name: "Delta" }, 90);
  it("blanks are last in both directions; ties keep the member's order", () => {
    expect(sortHoldings([a, b, c, d], "current", "desc").map((h) => h.id)).toEqual(["a", "d", "c", "b"]);
    expect(sortHoldings([a, b, c, d], "current", "asc").map((h) => h.id)).toEqual(["c", "d", "a", "b"]);
    expect(sortHoldings([a, b, c, d], "score", "desc").map((h) => h.id)).toEqual(["d", "a", "b", "c"]);
    expect(sortHoldings([a, b, c, d], "name", "asc").map((h) => h.id)).toEqual(["b", "a", "d", "c"]);
    expect(sortHoldings([a, b], "r1y", "desc").map((h) => h.id)).toEqual(["a", "b"]);
  });
  it("sorts by a part of the score and puts locked rows last", () => {
    expect(sortHoldings([c, a], "performance", "desc").map((h) => h.id)).toEqual(["a", "c"]);
  });
});

describe("CSV export", () => {
  it("writes numbers plainly and explains every blank in Notes; the score columns are absent when locked", () => {
    const csv = toCsv([H("a", { gain: null, gainPct: null, gainWhy: "The amount paid is not known" }, 82)], false).trim().split("\r\n");
    expect(csv[0]).toContain('"Health score"') ; expect(csv[0].endsWith('"Notes"')).toBe(true);
    expect(csv[1]).toContain('"82.0","Healthy","82.0","50.0","60.0","70.0"');
    expect(csv[1]).toContain("Gain: The amount paid is not known");
    expect(csv[1]).toContain("XIRR: Add the purchase date");
    const locked = toCsv([H("a")], true).split("\r\n")[0];
    expect(locked).not.toContain("Health score");
    expect(toCsv([H("x", { name: "=HYPERLINK(1)" })], true)).toContain(`"'=HYPERLINK(1)"`);
  });
});

describe("text", () => {
  it("money has Indian grouping and a true minus", () => {
    expect(rupees(1234567.5)).toBe("₹12,34,568"); expect(rupees(-1500)).toBe("−₹1,500"); expect(rupees(null)).toBe("—"); expect(rupees(12.5, true)).toBe("₹12.50");
    expect(pct1(12.345, true)).toBe("+12.35%"); expect(pct1(-3)).toBe("−3.00%");
  });
});

describe("the size and type pie charts", () => {
  const h = (category: string | null, current: number | null) => ({ category, current } as unknown as Holding);
  it("sizes and types are read from the SEBI category", () => {
    expect(["Equity Scheme - Large Cap Fund", "Equity Scheme - Mid Cap Fund", "Equity Scheme - Small Cap Fund", "Equity Scheme - Large & Mid Cap Fund", "Equity Scheme - Flexi Cap Fund", "Debt Scheme - Liquid Fund"].map(sizeOf))
      .toEqual(["Large cap", "Mid cap", "Small cap", "Large & mid cap", null, null]);
    expect(["Equity Scheme - Flexi Cap Fund", "Debt Scheme - Liquid Fund", "Hybrid Scheme - Balanced Hybrid Fund", "Solution Oriented Scheme - Retirement Fund", "Other Scheme - Index Funds", null].map(typeOf))
      .toEqual(["Equity", "Debt", "Hybrid", "Solution oriented", "Others", "Others"]);
  });
  it("funds with no value count the same; with values every fund is weighted by its value; funds outside the groups are counted apart", () => {
    const f = shares([h("Equity Scheme - Large Cap Fund", null), h("Equity Scheme - Large Cap Fund", null), h("Equity Scheme - Small Cap Fund", null), h("Debt Scheme - Liquid Fund", null)], (x) => sizeOf(x.category));
    expect(f.by).toBe("count"); expect(f.left).toBe(1); expect(f.slices).toEqual([{ label: "Large cap", value: 2, pct: 66.7 }, { label: "Small cap", value: 1, pct: 33.3 }]);
    const v = shares([h("Equity Scheme - Large Cap Fund", 300), h("Equity Scheme - Mid Cap Fund", 100)], (x) => sizeOf(x.category));
    expect(v.by).toBe("value"); expect(v.slices.map((s) => s.pct)).toEqual([75, 25]);
  });
});
