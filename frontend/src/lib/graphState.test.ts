import { describe, expect, it } from "vitest";
import { alignSeries, asOf, changes, corrMatrix, csvCell, domain, pearson, rebase, windowPts } from "./graphData";
import { extract, fmtTick, fmtValue, fyEnd, monthEnd, BY_ID } from "./graphMetrics";
import { chartCheck, decodeView, defaultView, encodeView, sanitize } from "./graphState";

const pt = (t: string, v: number | null) => ({ t, v });
describe("correlation", () => {
  it("matches a hand-computed Pearson r", () => {
    expect(pearson([1, 2, 3, 4, 5], [2, 4, 5, 4, 5]).r).toBeCloseTo(0.7746, 4);
    expect(pearson([1, 2, 3], [3, 2, 1]).r).toBeCloseTo(-1, 10);
  });
  it("uses only pairs where both exist and refuses tiny or flat samples", () => {
    const c = pearson([1, null, 3, 4, 5], [2, 9, 6, 8, 10]);
    expect(c.n).toBe(4); expect(c.r).toBeCloseTo(1, 10);
    expect(pearson([1, 2], [1, 2]).r).toBeNull();
    expect(pearson([1, 1, 1], [1, 2, 3]).r).toBeNull();
  });
  it("builds a symmetric matrix with a unit diagonal", () => {
    const m = corrMatrix([[1, 2, 3, 4], [2, 4, 6, 9], [4, 3, 2, 1]]);
    expect(m.r[0][0]).toBe(1); expect(m.r[0][1]).toBe(m.r[1][0]); expect(m.r[0][2]).toBeCloseTo(-1, 10);
  });
});
describe("transforms", () => {
  it("percent change for amounts, difference for ratios, none from a non-positive base", () => {
    expect(changes([100, 110, 99], "amount")).toEqual([null, 10, -10]);
    expect(changes([10, 12.5], "ratio")).toEqual([null, 2.5]);
    expect(changes([-5, 5], "amount")).toEqual([null, null]);
  });
  it("rebases to 100 only from a positive start", () => {
    expect(rebase([pt("a", 50), pt("b", 75)])!.map((p) => p.v)).toEqual([100, 150]);
    expect(rebase([pt("a", -1), pt("b", 2)])).toBeNull();
  });
  it("windows each series back from its own latest date", () => {
    const pts = [pt("2023-03-31", 1), pt("2024-03-31", 2), pt("2025-03-31", 3), pt("2026-03-31", 4)];
    expect(windowPts(pts, "1Y").length).toBe(2); expect(windowPts(pts, "MAX").length).toBe(4);
  });
  it("aligns price to period ends without forward-filling statements onto dates", () => {
    const prices = Array.from({ length: 800 }, (_, i) => pt(new Date(Date.UTC(2024, 0, 1) + i * 86400000).toISOString().slice(0, 10), 100 + i));
    const fin = [pt("2024-03-31", 10), pt("2025-03-31", 20)];
    const a = alignSeries([{ pts: fin, grain: "periodic" }, { pts: prices, grain: "price" }], "annual");
    expect(a.dates).toEqual(["2024-03-31", "2025-03-31"]); expect(a.cols[0]).toEqual([10, 20]); expect(a.cols[1]).toEqual([190, 555]);
    expect(asOf(prices, "2023-01-01", 7)).toBeNull();
  });
  it("domain includes zero for bars", () => { expect(domain([5, 9], true)[0]).toBe(0); expect(domain([5, 9], false)[0]).toBeLessThan(5); });
  it("neutralises spreadsheet formulas in CSV", () => { expect(csvCell("=1+1")).toBe("'=1+1"); expect(csvCell('a,"b"')).toBe('"a,""b"""'); expect(csvCell(-3)).toBe("-3"); });
});
describe("metrics", () => {
  it("reads period ends and labels", () => { expect(monthEnd("Sep 2023")).toBe("2023-09-30"); expect(fyEnd("FY26")).toBe("2026-03-31"); });
  it("formats Indian units", () => { expect(fmtValue(964693, "cr")).toBe("₹9,64,693 Cr"); expect(fmtValue(-7.5, "pct")).toBe("−7.50%"); expect(fmtTick(250000, "cr")).toBe("2.5L"); });
  it("says locked for a plan-trimmed ratio and noperiod for annual-only data on quarters", () => {
    const b = { ratios: { history: { periods: ["FY25"], rows: {} }, valuationHistory: { periods: [], rows: {} } } } as never;
    expect(extract(BY_ID.pe, b, "annual", "basic", true).status).toBe("locked");
    expect(extract(BY_ID.pe, b, "annual", "gold", true).status).toBe("nodata");
    expect(extract(BY_ID.cash, {}, "quarterly", "gold", true).status).toBe("noperiod");
  });
});
describe("view state", () => {
  it("round-trips through the URL and clamps to the plan", () => {
    const v = defaultView(); expect(decodeView(encodeView(v), "gold")).toEqual(sanitize(v, "gold"));
    const big = { layout: "3x3", cells: [{ chart: "heatmap", series: ["A", "B", "C"].map((s) => ({ s, m: "price" })) }] };
    const s = sanitize(big, "basic"); expect(s.layout).toBe("2x2"); expect(s.cells[0].chart).toBe("line"); expect(s.cells[0].series.length).toBe(2);
    expect(decodeView("%%%not-base64", "gold")).toBeNull();
    expect(sanitize({ cells: [{ chart: "line", series: [{ s: "../x", m: "price" }, { s: "TCS", m: "nope" }] }] }, "gold").cells[0].series).toEqual([]);
  });
  it("explains invalid chart choices instead of drawing them", () => {
    const f = { n: 2, comp: false, mixedComp: false, units: ["cr", "pct"], ratioUnits: true, maxPts: 8, ohlc: false, priceOnly1: false, companies: 1 };
    expect(chartCheck("bar", f, "gold").ok).toBe(false); expect(chartCheck("pie", f, "gold").ok).toBe(false);
    expect(chartCheck("candlestick", { ...f, n: 1, priceOnly1: true }, "gold").why).toMatch(/daily/);
    expect(chartCheck("heatmap", f, "silver").why).toMatch(/plan/);
    expect(chartCheck("pie", { ...f, comp: true, n: 1 }, "gold").ok).toBe(true);
  });
});

describe("indices in a view", () => {
  const ix = (m: string, s = "IDX:NIF50") => ({ s, m });
  it("round-trips an index symbol through the share link", () => {
    const v = sanitize({ cells: [{ chart: "line", series: [ix("price"), { s: "TCS", m: "price" }] }] }, "gold");
    expect(decodeView(encodeView(v), "gold")!.cells[0].series.map((s) => s.s)).toEqual(["IDX:NIF50", "TCS"]);
  });
  it("keeps only measures an index has, and index valuation only on indices", () => {
    const v = sanitize({ cells: [{ chart: "line", series: [ix("price"), ix("revenue"), ix("ix_pe"), { s: "TCS", m: "ix_pe" }] }] }, "gold");
    expect(v.cells[0].series.map((s) => s.s + "/" + s.m)).toEqual(["IDX:NIF50/price", "IDX:NIF50/ix_pe"]);
  });
  it("counts indices toward the series limit but not the company limit", () => {
    const v = sanitize({ cells: [{ chart: "line", series: [{ s: "TCS", m: "price" }, { s: "INFY", m: "price" }, { s: "WIPRO", m: "price" }, ix("price")] }] }, "basic");
    expect(v.cells[0].series.map((s) => s.s)).toEqual(["TCS", "INFY", "IDX:NIF50"]);
    expect(sanitize({ cells: [{ chart: "line", series: [{ s: "idx:bad!", m: "price" }] }] }, "gold").cells[0].series).toEqual([]);
  });
  it("reads index levels in points and valuation as daily points", () => {
    const b = { ixl: { rows: [{ d: "2026-10-16", c: 100 }, { d: "2026-10-19", c: 110 }] }, ixv: { rows: [{ d: "2026-10-19", pe: 19.7, pb: 2.8, dy: 1.49 }] } };
    expect(extract(BY_ID.price, b, "annual", "basic", true).pts.map((p) => p.v)).toEqual([100, 110]);
    expect(extract(BY_ID.ix_dy, b, "annual", "gold", true).pts).toEqual([{ t: "2026-10-19", v: 1.49 }]);
  });
});
