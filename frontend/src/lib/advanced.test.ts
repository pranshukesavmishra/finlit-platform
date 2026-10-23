import { describe, expect, it } from "vitest";
import {
  bandPath, b64urlDecode, b64urlEncode, decodeState, decodeUniverse, DEFAULT_STATE, edgeOf, encodeState, encodeUniverse, EMPTY_UNIVERSE,
  fmtP, fmtR, logTicks, nearest, quantile7, sectionBySlug, SECTIONS, shapePath, SHAPES, sig3, viewRange, type AdvState,
} from "./advanced";

describe("sections", () => {
  it("has the ten route slugs of the plan, in order", () => {
    expect(SECTIONS.map((s) => s.slug)).toEqual(["valuation", "profitability", "growth", "leverage", "cash-flow", "liquidity", "dividends", "market", "warnings", "sector"]);
    expect(sectionBySlug("cash-flow")?.n).toBe(5);
    expect(sectionBySlug("nope")).toBeUndefined();
  });
});

describe("URL state", () => {
  const full: AdvState = {
    ...DEFAULT_STATE, pair: "1.9", mode: "history", companies: ["RELIANCE", "M&M", "TCS"],
    universe: { sector: ["Banks", "Paper, Forest & Jute Products"], industry: ["Private Sector Bank"], index: ["NIFTY 50"], cap: ["Large", "Mid"], mcapMin: 500, mcapMax: 250000, lenders: "only", sameFy: true },
    sx: "log", sy: "lin", trim: true, all: true, h: 20, indices: ["NIFTY50", "NIFTYIT"], variant: "forward",
  };
  it("round-trips every field", () => {
    const back = decodeState(new URLSearchParams(encodeState(full).toString()));
    expect(back).toEqual(full);
  });
  it("round-trips a custom pair", () => {
    const s = { ...DEFAULT_STATE, pair: "custom", x: "roe", y: "g_eps" };
    expect(decodeState(new URLSearchParams(encodeState(s).toString()))).toEqual(s);
  });
  it("leaves defaults out of the address", () => {
    expect(encodeState(DEFAULT_STATE).toString()).toBe("");
    expect(encodeUniverse(EMPTY_UNIVERSE)).toBe("");
  });
  it("ignores malformed values instead of throwing", () => {
    const s = decodeState(new URLSearchParams("pair=<script>&mode=evil&c=reliance,,bad sym,TCS&sx=cubic&h=7&u=%%%&v=<b>&trim=yes"));
    expect(s.pair).toBeNull(); expect(s.mode).toBe("cross"); expect(s.companies).toEqual(["RELIANCE", "TCS"]);
    expect(s.sx).toBeNull(); expect(s.h).toBeNull(); expect(s.universe).toEqual(EMPTY_UNIVERSE); expect(s.variant).toBeNull(); expect(s.trim).toBe(false);
    expect(decodeUniverse(b64urlEncode("[1,2]"))).toEqual(EMPTY_UNIVERSE);
    expect(decodeUniverse(b64urlEncode('{"c":["Huge","Large"],"mn":-5}')).cap).toEqual(["Large"]);
  });
  it("caps the companies at the plan limit and drops duplicates", () => {
    expect(decodeState(new URLSearchParams("c=A,B,A,C,D"), 3).companies).toEqual(["A", "B", "C"]);
  });
  it("base64url handles non-ASCII text", () => {
    expect(b64urlDecode(b64urlEncode("Sector – ₹ & ü"))).toBe("Sector – ₹ & ü");
    expect(b64urlDecode("@@@")).toBeNull();
  });
});

describe("display rounding", () => {
  it("r and rho to 2 decimals with a true minus, never -0.00", () => {
    expect(fmtR(0.816421)).toBe("0.82"); expect(fmtR(-0.4567)).toBe("−0.46"); expect(fmtR(-0.004)).toBe("0.00"); expect(fmtR(1)).toBe("1.00");
    expect(fmtR(null)).toBe("—"); expect(fmtR(NaN)).toBe("—");
  });
  it("p to 3 significant figures, or < 0.001", () => {
    expect(fmtP(0.0021696)).toBe("0.00217"); expect(fmtP(0.073388)).toBe("0.0734"); expect(fmtP(0.363217)).toBe("0.363");
    expect(fmtP(0.0009999)).toBe("< 0.001"); expect(fmtP(0)).toBe("< 0.001"); expect(fmtP(0.001)).toBe("0.00100"); expect(fmtP(1)).toBe("1.00"); expect(fmtP(undefined)).toBe("—");
  });
  it("slopes to 3 significant figures in plain notation", () => {
    expect(sig3(0.500091)).toBe("0.500"); expect(sig3(0.0912345)).toBe("0.0912"); expect(sig3(-4.5)).toBe("−4.50"); expect(sig3(123456)).toBe("1,23,000");
    expect(sig3(1.23e-7)).toBe("0.000000123"); expect(sig3(0)).toBe("0"); expect(sig3(null)).toBe("—");
  });
});

describe("axis geometry", () => {
  it("log ticks use 1-2-5 per decade and thin out over many decades", () => {
    expect(logTicks(1, 100)).toEqual([1, 2, 5, 10, 20, 50, 100]);
    expect(logTicks(3, 40)).toEqual([5, 10, 20]);
    expect(logTicks(10, 1e8)).toEqual([10, 1000, 1e5, 1e7]);
    expect(logTicks(-1, 10)).toEqual([]);
    expect(logTicks(100, 1)).toEqual([1, 2, 5, 10, 20, 50, 100]);
  });
  it("type-7 quantiles match numpy's default", () => {
    const v = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    expect(quantile7(v, 0)).toBe(1); expect(quantile7(v, 1)).toBe(10); expect(quantile7(v, 0.5)).toBe(5.5); expect(quantile7(v, 0.01)).toBeCloseTo(1.09, 12);
  });
  it("view range: percentile window, every point with all=true, highlights always inside", () => {
    const v = Array.from({ length: 100 }, (_, i) => i + 1).concat([10000]);
    const [lo, hi] = viewRange(v, false); expect(hi).toBeLessThan(200); expect(lo).toBeLessThan(2);
    expect(viewRange(v, true)[1]).toBeGreaterThan(10000);
    expect(viewRange(v, false, [10000])[1]).toBeGreaterThan(10000);
    expect(viewRange([5, 5], false)).toEqual([2.5, 7.5]);
  });
  it("edge markers clamp a point to the window and say which side it left by", () => {
    expect(edgeOf(15, 5, [0, 10], [0, 10])).toMatchObject({ inside: false, right: true, x: 10, y: 5 });
    expect(edgeOf(5, 5, [0, 10], [0, 10]).inside).toBe(true);
  });
  it("band path goes along the upper edge and back along the lower edge, closed", () => {
    const id = (v: number) => v;
    expect(bandPath([{ x: 0, lo: -1, hi: 1 }, { x: 10, lo: 8, hi: 12 }], id, id)).toBe("M0.0,1.0L10.0,12.0L10.0,8.0L0.0,-1.0Z");
    expect(bandPath([{ x: 0, lo: 0, hi: 0 }], id, id)).toBe("");
    expect(bandPath([{ x: 0, lo: 0, hi: 1 }, { x: NaN, lo: 0, hi: 1 }, { x: 2, lo: 1, hi: 2 }], id, id)).toBe("M0.0,1.0L2.0,2.0L2.0,1.0L0.0,0.0Z");
  });
  it("every highlight shape gives a closed path; nearest finds the closest point", () => {
    for (const s of SHAPES) expect(shapePath(s, 10, 10, 5)).toMatch(/^M.*Z$/);
    expect(nearest([{ sx: 0, sy: 0 }, { sx: 10, sy: 10 }], 8, 9)).toBe(1);
    expect(nearest([], 1, 1)).toBe(-1);
  });
});

// ------------------------------------------------------------------ sentence, typesetting, CSV, rules
import { advSentence, ariaSummary, cfoWarning, crossBody, crossCsv, disp, roundHalfEven, rounded, type CrossResp, type Stats, type DecisionRule } from "./advanced";

const TEXT: Record<DecisionRule, string> = {
  few: "Too few points for a reliable line (n = 7).", no_spread: "No line: the values do not vary.", not_significant: "No reliable linear relationship (p = 0.312).",
  weak: "Statistically detectable but too weak to be useful (explains under 9%).", one_company: "No line: the line depends on one company (XYZ Ltd).",
  curved: "No straight line: the relationship is curved.", pulled: "Extreme values pull the straight line: both the straight line and a robust (Theil-Sen) line are drawn.",
  ok: "A straight line is drawn with its 95% band.",
};
const mk = (rule: DecisionRule, o: Partial<Stats> = {}): Stats => ({
  n: 812, space: { x: "lin", y: "lin" },
  pearson: { r: 0.4612, r2: 0.2127, p: 1.2e-43, ci: [0.405, 0.514] }, spearman: { rho: 0.5201, p: 3.3e-58 },
  ols: { slope: 0.0912, intercept: 0.84, ci: [0.079, 0.103] }, theilSen: { slope: 0.0871, intercept: 0.86 },
  decision: { line: rule === "ok" ? "ols" : rule === "pulled" ? "ols_ts" : "none", rule, text: TEXT[rule] },
  line: rule === "ok" || rule === "pulled" ? { x0: 1, y0: 2, x1: 3, y1: 4 } : null, band: null,
  rounded: { r: "0.46", rho: "0.52", p: "< 0.001", slope: "0.0912", r2pct: "21%" }, ...o,
});
const ctx = { kind: "cross" as const, who: "companies", x: { short: "ROE", unit: "%" as const }, y: { short: "P/B", unit: "x" as const }, left: 61, total: 873, fy: [{ fy: "FY26", n: 790 }, { fy: "FY25", n: 22 }], builtAt: "2026-10-22T10:15:00Z" };

describe("advSentence", () => {
  it("words a drawn line from the API's own rounded strings", () => {
    const s = advSentence(mk("ok"), ctx);
    expect(s).toContain("Across 812 companies, higher ROE tends to go with higher P/B (Pearson r = 0.46, moderate; Spearman rho = 0.52; p < 0.001).");
    expect(s).toContain("The line explains 21% of the variation; on average, +1 percentage point of ROE goes with +0.0912× of P/B.");
    expect(s).toContain("61 of the 873 companies in the filters are left out");
    expect(s).toContain("Results FY26 (790) / FY25 (22).");
    expect(s).toContain("22 Oct 2026");
    expect(s.endsWith("Correlation is not causation. Information only, not advice.")).toBe(true);
  });
  it("says 'lower' for a negative relationship", () => {
    const s = advSentence(mk("ok", { pearson: { r: -0.5, r2: 0.25, p: 0.0001 }, rounded: { r: "-0.50", rho: "-0.48", p: "< 0.001", slope: "-0.120", r2pct: "25%" } }), ctx);
    expect(s).toContain("higher ROE tends to go with lower P/B (Pearson r = −0.50, moderate; Spearman rho = −0.48");
    expect(s).toContain("goes with −0.120× of P/B");
  });
  it("puts the sign before the rupee sign for amounts", () => {
    const c2 = { ...ctx, y: { short: "Revenue", unit: "Cr" as const } };
    const pos = advSentence(mk("ok", { rounded: { r: "0.46", rho: "0.52", p: "< 0.001", slope: "0.338", r2pct: "21%" } }), c2);
    expect(pos).toContain("goes with +₹0.338 Cr of Revenue");
    const neg = advSentence(mk("ok", { rounded: { r: "0.46", rho: "0.52", p: "< 0.001", slope: "-0.338", r2pct: "21%" } }), c2);
    expect(neg).toContain("goes with −₹0.338 Cr of Revenue");
  });
  it("words a log-scale slope as a log slope, never as a linear one", () => {
    const s = advSentence(mk("ok", { space: { x: "log", y: "log" }, rounded: { r: "0.46", rho: "0.52", p: "< 0.001", slope: "0.338", r2pct: "21%" } }), ctx);
    expect(s).toContain("the slope is +0.338 on the log scale");
    expect(s).not.toContain("+1 percentage point");
  });
  it("adds the pulled-line explanation", () => {
    expect(advSentence(mk("pulled"), ctx)).toContain(TEXT.pulled);
  });
  for (const rule of ["few", "no_spread", "not_significant", "weak", "one_company", "curved"] as DecisionRule[]) {
    it(`states the reason when no line is drawn: ${rule}`, () => {
      const s = advSentence(mk(rule), ctx);
      expect(s).toContain(`No line is drawn. ${TEXT[rule]}`);
      expect(s).not.toContain("tends to go with");
      expect(s).toContain("Correlation is not causation.");
    });
  }
  it("'no reliable linear relationship' keeps the API's p in the text", () => {
    expect(advSentence(mk("not_significant", { pearson: { r: 0.0401, r2: 0.0016, p: 0.312 }, rounded: { r: "0.04", rho: "0.05", p: "0.312", slope: "0.00100", r2pct: "0%" } }), ctx)).toContain("Pearson r = 0.04 (very weak); Spearman rho = 0.05; p = 0.312. No line is drawn. No reliable linear relationship (p = 0.312).");
  });
  it("handles no statistics and missing r", () => {
    expect(advSentence(null, ctx)).toMatch(/^No company has both figures/);
    expect(advSentence(mk("no_spread", { pearson: null, spearman: null, rounded: null }), ctx)).toContain("Pearson r cannot be computed");
  });
  it("uses log wording when the statistics are on a log scale", () => {
    expect(advSentence(mk("ok", { space: { x: "log", y: "log" } }), ctx)).toContain("the slope is +0.0912 on the log scale");
  });
  it("aria summary names the line decision", () => {
    expect(ariaSummary(mk("ok"), "ROE", "P/B", 812, "companies")).toBe("Scatter of P/B against ROE, 812 companies. Pearson r 0.46, p < 0.001; straight line drawn with its 95% band.");
    expect(ariaSummary(mk("curved"), "ROE", "P/B", 812, "companies")).toContain("no line drawn: No straight line");
  });
});

describe("typesetting the API's display strings", () => {
  it("only typesets, never re-rounds", () => {
    expect(disp("-0.46", "x")).toBe("−0.46"); expect(disp("-0.00", "x")).toBe("0.00"); expect(disp("1.2e+06", "x")).toBe("12,00,000");
    expect(disp("1.23e-05", "x")).toBe("0.0000123"); expect(disp("n/a", "x")).toBe("—"); expect(disp(null, "fb")).toBe("fb"); expect(disp("0.0912", "x")).toBe("0.0912");
  });
  it("falls back to the same rounding rules when the API sends no strings", () => {
    expect(rounded(mk("ok", { rounded: null }))).toEqual({ r: "0.46", rho: "0.52", p: "< 0.001", slope: "0.0912", r2pct: "21%" });
  });
  it("rounds whole per cents half to even, as Python does", () => {
    expect(roundHalfEven(20.5)).toBe(20); expect(roundHalfEven(21.5)).toBe(22); expect(roundHalfEven(21.27)).toBe(21); expect(roundHalfEven(0.5)).toBe(0);
  });
});

describe("request body and CSV", () => {
  it("sends the pair id, or x/y for a custom pair, with the universe, scales, trim and highlights", () => {
    const st = { ...DEFAULT_STATE, pair: "1.9", companies: ["TCS"], trim: true, variant: "forward" };
    expect(crossBody(st, { id: "1.9" } as never, { x: "lin", y: "log" })).toEqual({ pair: "1.9", variant: "forward", universe: { ...EMPTY_UNIVERSE }, scale: { x: "lin", y: "log" }, trim: true, highlight: ["TCS"] });
    expect(crossBody({ ...DEFAULT_STATE, pair: "custom", x: "roe", y: "pb" }, null, { x: "lin", y: "lin" })).toMatchObject({ x: "roe", y: "pb" });
  });
  it("guards text cells against spreadsheet formulas, keeps numbers raw", () => {
    const r = { n: 1, universeTotal: 2, excluded: [], points: [{ s: "ABC", name: "=HYPERLINK(\"x\")", sector: "+Sector", x: -1.5, y: 2, fy: "FY26" }],
      highlights: [{ s: "ZZZ", name: "@evil", x: null, y: null, status: "excluded", reason: "no_fy", reasonText: "No figure" }], stats: null, method: "-m", caveats: ["c"], tableBuiltAt: null } as unknown as CrossResp;
    const csv = crossCsv(r, "T");
    expect(csv).toContain(`ABC,"'=HYPERLINK(""x"")",'+Sector,FY26,-1.5,2,yes,,no`);
    expect(csv).toContain("ZZZ,'@evil,,,,,no,no_fy,yes");
    expect(csv).toContain("# method,'-m");
  });
});

describe("revenue and profit up, cash flow down", () => {
  const t = (periods: string[], ends: string[], rows: Record<string, (number | null)[]>) => ({ unit: "Cr", period: "FY", periods, periodEnds: ends, rows });
  const fin = (cfo: number[]) => ({ yearly: { pl: t(["FY25", "FY26"], ["2025-03-31", "2026-03-31"], { revenue: [100, 120], net_profit: [10, 12] }), cf: t(["FY25", "FY26"], ["2025-03-31", "2026-03-31"], { operating: cfo }), bs: t([], [], {}) } }) as never;
  it("flags it with the reported figures", () => {
    const w = cfoWarning(fin([15, 9]));
    expect(w?.period).toBe("FY26"); expect(w?.against).toBe("FY25"); expect(w?.text).toContain("operating cash flow ₹15.00 Cr to ₹9.00 Cr");
  });
  it("stays silent when cash flow rose or a figure is missing", () => {
    expect(cfoWarning(fin([9, 15]))).toBeNull();
    expect(cfoWarning(null)).toBeNull();
  });
});

// ------------------------------------------------------------------ index reference markers
import { indexMarkers, INDEX_NOTE, MAX_INDICES, type IndexPoint } from "./advanced";

describe("index markers", () => {
  it("round-trips ?ix= and caps it at the API's maximum", () => {
    const st = decodeState(new URLSearchParams("ix=nifty50,NIFTYIT,NIFTYIT,bad code,NIFTYBANK,NIFTY100"));
    expect(st.indices).toEqual(["NIFTY50", "NIFTYIT", "NIFTYBANK"]);
    expect(st.indices.length).toBe(MAX_INDICES);
    expect(encodeState(st).get("ix")).toBe("NIFTY50,NIFTYIT,NIFTYBANK");
    expect(crossBody({ ...DEFAULT_STATE, indices: ["NIFTY50"] }, { id: "1.9" } as never, { x: "lin", y: "lin" }).indices).toEqual(["NIFTY50"]);
    expect("indices" in crossBody(DEFAULT_STATE, { id: "1.9" } as never, { x: "lin", y: "lin" })).toBe(false);
  });
  const base: IndexPoint = { code: "NIFTY50", label: "NIFTY 50", x: 22.4, y: 15.1, membersTotal: 50, membersEligible: 50, membersUsed: 47, mcapCoveragePct: 96.2,
    method: { x: "ratio_of_sums", y: "median" }, formula: { x: "f", y: "g" }, reason: null, reasonText: null, lossMembers: 2 };
  const f = (v: number) => String(v);
  it("maps a point exactly as sent, with method, members and coverage", () => {
    const [m] = indexMarkers([base], ["NIFTY50"], "lin", "lin", f, f, "P/E", "ROE");
    expect(m).toMatchObject({ code: "NIFTY50", label: "NIFTY 50", drawn: true, x: 22.4, y: 15.1, why: null, color: "var(--k7)" });
    expect(m.lines).toEqual(["P/E: 22.4 (aggregate of members (sum over sum, so weighted by size))", "ROE: 15.1 (median of members)",
      "Members used 47 of 50; 96.2% of the index by market cap", "2 loss-making members included in the aggregate", INDEX_NOTE]);
  });
  it("keeps the API's reason when coverage is too low, and does not draw it", () => {
    const low = { ...base, code: "NIFTYIT", label: "NIFTY IT", x: null, y: null, mcapCoveragePct: 61.5, reason: "low_coverage", reasonText: "Only 62% of the index (by market cap) has stored figures for this chart; at least 80% is needed." };
    const ms = indexMarkers([low, base], ["NIFTY50", "NIFTYIT"], "lin", "lin", f, f, "P/E", "ROE");
    expect(ms.map((m) => m.code)).toEqual(["NIFTY50", "NIFTYIT"]);              // in the order the user added them
    expect(ms[1]).toMatchObject({ drawn: false, x: null, y: null, why: low.reasonText, color: "var(--k8)" });
    expect(ms[1].lines[0]).toBe("P/E: — (aggregate of members (sum over sum, so weighted by size))");
    expect(ms[1].lines).toContain(`Not drawn — ${low.reasonText}`);
  });
  it("does not place a zero or negative value on a log axis", () => {
    const [m] = indexMarkers([{ ...base, y: -3 }], [], "lin", "log", f, f, "x", "y");
    expect(m.drawn).toBe(false); expect(m.why).toMatch(/log scale/);
  });
  it("adds index rows to the CSV as reference rows, outside the statistics", () => {
    const r = { n: 0, universeTotal: 0, excluded: [], points: [], highlights: [], stats: null, method: "m", caveats: [], tableBuiltAt: null,
      indices: [base, { ...base, code: "NIFTYIT", label: "NIFTY IT", x: null, y: null, reason: "low_coverage" }] } as unknown as CrossResp;
    const csv = crossCsv(r, "T");
    expect(csv).toContain("index:NIFTY50,NIFTY 50,,,22.4,15.1,no,index_reference,no");
    expect(csv).toContain("index:NIFTYIT,NIFTY IT,,,,,no,index_reference; low_coverage,no");
  });
  it("the sentence says index markers are not part of the line", () => {
    expect(advSentence(mk("ok"), { ...ctx, indices: true })).toContain(INDEX_NOTE);
    expect(advSentence(mk("ok"), ctx)).not.toContain(INDEX_NOTE);
  });
});
