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
    sx: "log", sy: "lin", trim: true, all: true, h: 20, variant: "forward",
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
