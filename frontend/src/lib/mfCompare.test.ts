import { describe, expect, it } from "vitest";
import {
  CARDS, DEFAULT_PERIOD, cardTeaser, pickCategory, consistencyLine, costsLine, h2hPath, h2hToParams, isMultiCompare, parseH2H, pct, periodBlock, returnsLine, riskLine, rupees, share,
  shortName, signedPct, type HeadToHead,
} from "./mfCompare";

const names = { a: "Parag Parikh Flexi Cap Fund", b: "HDFC Flexi Cap Fund" };

/** The parts of an answer the lines read, with every figure given (a test changes what it needs). */
function answer(over: Partial<{ ra: number | null; rb: number | null; kind: "cagr" | "absolute"; da: number | null; db: number | null; va: number | null; vb: number | null }> = {}): HeadToHead {
  const o = { ra: 18.4, rb: 16.3, kind: "cagr" as const, da: -24.6, db: -22.1, va: 13.2, vb: 14.9, ...over };
  const risk = (vol: number | null, dd: number | null) => ({
    volatility: { value: vol, why: vol == null ? "Too few NAVs." : null }, downside: { value: null, why: null }, sharpe: { value: null, why: null },
    maxDrawdown: { value: dd, why: null, peak: null, trough: null, recovered: null }, worstMonth: { value: null, why: null, month: null }, bestMonth: { value: null, why: null, month: null },
  });
  const ret = (v: number | null) => ({ value: v, from: null, to: null, growth: null, why: v == null ? "NAV history on file starts on 1 Mar 2024." : null });
  return {
    period: "5Y", returns: { kind: o.kind, funds: { a: ret(o.ra), b: ret(o.rb), cat: ret(15) } }, risk: { funds: { a: risk(o.va, o.da), b: risk(o.vb, o.db), cat: risk(12, -20) }, riskFree: 6, note: "" },
    consistency: {
      window: { months: 12, label: "1 year" }, rolling: { a: 788, b: 442, ties: 0, n: 1230, why: null }, months: { a: 33, b: 26, ties: 0, n: 59, why: null },
      years: { a: 3, b: 1, ties: 0, n: 4, why: null, rows: [] }, vsCategory: { a: { beat: 900, n: 1230, pct: 73.2, why: null }, b: { beat: 500, n: 1230, pct: 40.7, why: null } },
    },
    costs: {
      funds: { a: { terPct: 0.63 }, b: { terPct: 0.77 } }, alpha: { a: { value: 3.4, why: null }, b: { value: 1.3, why: null } }, alphaBasis: "category average", alphaNote: "",
    },
  } as unknown as HeadToHead;
}

describe("URL state", () => {
  it("reads and writes the page state, keeping only what differs from the defaults", () => {
    const s = parseH2H(new URLSearchParams("category=Equity+Scheme+-+Flexi+Cap+Fund&a=122639&b=118955&period=10Y&card=risk&plan=Regular"));
    expect(s).toEqual({ category: "Equity Scheme - Flexi Cap Fund", plan: "Regular", a: 122639, b: 118955, period: "10Y", card: "risk" });
    expect(h2hToParams(s).toString()).toBe("category=Equity+Scheme+-+Flexi+Cap+Fund&plan=Regular&a=122639&b=118955&period=10Y&card=risk");
    const d = parseH2H(new URLSearchParams("a=x&b=-3&period=2Y&card=fees&plan=both"));
    expect(d).toEqual({ category: "", plan: "Direct", a: 0, b: 0, period: DEFAULT_PERIOD, card: "returns" });
    expect(h2hToParams(d).toString()).toBe("");
    expect(parseH2H(new URLSearchParams("a=5&b=5")).b).toBe(0);   // one fund cannot be compared with itself
    expect(h2hPath(1, 2, "3Y")).toBe("/api/mf-compare?a=1&b=2&period=3Y");
  });
  it("the 2 to 4 scheme compare is the view with ids in the address, even empty", () => {
    expect(isMultiCompare(new URLSearchParams("ids=1,2"))).toBe(true);
    expect(isMultiCompare(new URLSearchParams("ids="))).toBe(true);
    expect(isMultiCompare(new URLSearchParams("a=1&b=2"))).toBe(false);
    expect(isMultiCompare(new URLSearchParams(""))).toBe(false);
  });
  it("offers the four cards of the sketch", () => {
    expect(CARDS.map((c) => c.title)).toEqual(["Returns", "Risk", "Consistency", "Costs & benchmark"]);
  });
});

describe("categories", () => {
  const cats = [
    { name: "Equity Scheme - Large Cap Fund", short: "Large Cap Fund", group: "Equity Scheme", direct: 40, regular: 40 },
    { name: "Equity Scheme - Flexi Cap Fund", short: "Flexi Cap Fund", group: "Equity Scheme", direct: 39, regular: 39, variants: ["Equity Scheme - Flexi Cap Fund", "Equity Schemes - Flexi Cap Fund"] },
  ];
  it("finds a category by either of AMFI's wordings, and starts on Flexi Cap", () => {
    expect(pickCategory(cats, "Equity Schemes - Flexi Cap Fund")?.name).toBe("Equity Scheme - Flexi Cap Fund");
    expect(pickCategory(cats, "Equity Scheme - Large Cap Fund")?.short).toBe("Large Cap Fund");
    expect(pickCategory(cats, "")?.short).toBe("Flexi Cap Fund");
    expect(pickCategory(cats, "Nonsense")).toBeUndefined();
    expect(pickCategory(undefined, "")).toBeUndefined();
  });
});

describe("names and periods", () => {
  it("drops the plan and option words shared by both funds", () => {
    expect(shortName("Parag Parikh Flexi Cap Fund - Direct Plan - Growth")).toBe("Parag Parikh Flexi Cap Fund");
    expect(shortName("HDFC Flexi Cap Fund - Growth Option - Direct Plan")).toBe("HDFC Flexi Cap Fund");
    expect(shortName("Axis Large Cap Fund - Direct Plan - Growth Option")).toBe("Axis Large Cap Fund");
    expect(shortName("Quant Flexi Cap Fund-Growth Option-Direct Plan")).toBe("Quant Flexi Cap Fund");
    expect(shortName("HDFC Retirement Savings Fund - Equity Plan - Direct Plan - Growth")).toBe("HDFC Retirement Savings Fund - Equity Plan");
    expect(shortName("HSBC Large-Cap Fund - Regular Growth")).toBe("HSBC Large-Cap Fund");
    expect(shortName("Kotak Flexicap Fund Direct Growth")).toBe("Kotak Flexicap Fund");
    expect(shortName("Growth")).toBe("Growth");
    expect(shortName("ICICI Prudential Growth Fund - Series 3 - Direct Plan")).toBe("ICICI Prudential Growth Fund - Series 3");
  });
  it("holds back a period longer than the younger fund has existed, and says why", () => {
    const old = { name: "Old Fund - Direct Plan - Growth", launch: "2008-01-01" }, young = { name: "Young Fund - Direct Plan - Growth", launch: "2019-03-03" };
    expect(periodBlock("5Y", [old, young], "2026-10-19")).toBeNull();
    expect(periodBlock("10Y", [old, young], "2026-10-19")).toBe(`Young Fund was launched on 3 Mar 2019, less than 10 years before 19 Oct 2026.`);
    expect(periodBlock("10Y", [old, { name: "X", launch: null }], "2026-10-19")).toBeNull();   // launch not loaded: the server answers
    expect(periodBlock("10Y", [old, young], null)).toBeNull();
    expect(periodBlock("1Y", [{ name: "New", launch: "2026-02-28" }, undefined], "2026-02-28")).toContain("less than 1 year");
    expect(periodBlock("3Y", [{ name: "Leap", launch: "2023-03-01" }], "2026-02-28")).toContain("less than 3 years");    // 3 years before 28 Feb 2026 is 28 Feb 2023
  });
});

describe("number text", () => {
  it("uses a real minus sign, an explicit plus and Indian grouping", () => {
    expect(pct(-24.63)).toBe("−24.6%");
    expect(signedPct(2.05, 2)).toBe("+2.05%");
    expect(signedPct(null)).toBe("—");
    expect(rupees(254321.4)).toBe("₹2,54,321");
    expect(share(788, 1230)).toBe("64% (788 of 1,230)");
    expect(share(0, 0)).toBe("—");
  });
});

describe("the plain-English lines", () => {
  it("returns: who returned more, by how much a year, and how the worst falls compare", () => {
    expect(returnsLine(answer(), names)).toBe("Over 5 years, Parag Parikh Flexi Cap Fund returned 2.1 points a year more than HDFC Flexi Cap Fund (18.4% against 16.3% a year), with a slightly deeper worst fall (−24.6% against −22.1%).");
    expect(returnsLine(answer({ ra: 12, rb: 15, da: -30, db: -20 }), names)).toBe("Over 5 years, HDFC Flexi Cap Fund returned 3.0 points a year more than Parag Parikh Flexi Cap Fund (15.0% against 12.0% a year), with a shallower worst fall (−20.0% against −30.0%).");
    expect(returnsLine(answer({ da: -22.2, db: -22.1 }), names)).toContain("with about the same worst fall");
    expect(returnsLine(answer({ ra: 15, rb: 15.01 }), names)).toBe("Over 5 years, both funds returned the same a year (15.0%).");
    expect(returnsLine(answer({ rb: null }), names)).toBe("Over 5 years, the two funds cannot be compared: HDFC Flexi Cap Fund has no figure for the whole period.");
    const one = { ...answer({ kind: "absolute", da: null }), period: "1Y" as const };
    expect(returnsLine(one, names)).toBe("Over 1 year, Parag Parikh Flexi Cap Fund returned 2.1 points more than HDFC Flexi Cap Fund (18.4% against 16.3%).");
    expect(returnsLine(answer({ ra: 16.3, rb: 15.3 }), names)).toContain("returned 1.0 point a year more");
  });
  it("risk: which NAV swung less and which fell deeper; never which is safer", () => {
    expect(riskLine(answer(), names)).toBe("Over 5 years, Parag Parikh Flexi Cap Fund's NAV swung less than HDFC Flexi Cap Fund's (volatility 13.2% against 14.9% a year); Parag Parikh Flexi Cap Fund had the slightly deeper worst fall (−24.6% against −22.1%).");
    expect(riskLine(answer({ va: 14, vb: 14.1, da: -20, db: -20.1 }), names)).toBe("Over 5 years, the NAVs of both funds swung about as much (volatility 14.0% and 14.1% a year), and their worst falls were about as deep (−20.0% and −20.1%).");
    expect(riskLine(answer({ va: null }), names)).toContain("cannot be compared");
    expect(riskLine(answer(), names)).not.toMatch(/safer|better|should|recommend/i);
  });
  it("consistency: share of windows ahead, then calendar years (or months when there is no whole year)", () => {
    expect(consistencyLine(answer(), names)).toBe("Over 5 years, Parag Parikh Flexi Cap Fund was ahead in 64% (788 of 1,230) of the 1 year windows and in 3 of 4 calendar years.");
    const d = answer();
    d.consistency.years = { ...d.consistency.years, n: 0, a: 0, b: 0 };
    d.consistency.rolling = { a: 10, b: 30, ties: 0, n: 40, why: null };
    expect(consistencyLine(d, names)).toBe("Over 5 years, HDFC Flexi Cap Fund was ahead in 75% (30 of 40) of the 1 year windows and in 26 of 59 calendar months.");
    d.consistency.rolling = { a: 0, b: 0, ties: 0, n: 0, why: "short" };
    expect(consistencyLine(d, names)).toContain("no whole 1 year window");
  });
  it("costs: the expense ratio gap and each fund against the category average", () => {
    expect(costsLine(answer(), names)).toBe("Parag Parikh Flexi Cap Fund charges 0.14 percentage points a year less in expenses (0.63% against 0.77%). Over 5 years, Parag Parikh Flexi Cap Fund returned 3.4 points more than the category average a year, HDFC Flexi Cap Fund 1.3 points more than it.");
    const d = answer();
    d.costs.funds.b.terPct = null;
    d.costs.alpha.b = { value: null, why: "short" };
    d.costs.alpha.a = { value: -0.6, why: null };
    expect(costsLine(d, names)).toBe("Over 5 years, Parag Parikh Flexi Cap Fund returned 0.6 points less than the category average a year.");
    d.costs.alpha.a = { value: null, why: "x" };
    expect(costsLine(d, names)).toContain("not available");
  });
  it("teasers on the four cards are figures only", () => {
    const d = answer();
    expect(cardTeaser("returns", d)).toBe("18.4% vs 16.3% a year");
    expect(cardTeaser("risk", d)).toBe("Worst fall −24.6% vs −22.1%");
    expect(cardTeaser("consistency", d)).toBe("A ahead in 64% of windows");
    expect(cardTeaser("costs", d)).toBe("TER 0.63% vs 0.77%");
    expect(cardTeaser("returns", answer({ rb: null }))).toBeNull();
  });
});
