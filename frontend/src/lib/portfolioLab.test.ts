import { describe, expect, it } from "vitest";
import type { Row } from "./screener";
import { applySwaps, bandOf, buildReportHtml, capTier, findGaps, resilience, statsOf, stressView, suggestSwaps, type Holding } from "./portfolioLab";

const mk = (symbol: string, sector: string | null, overall: number | null, o: Partial<Row> = {}): Row => ({
  symbol, name: symbol + " Ltd", sector, overall, band: bandOf(overall) === "none" ? null : bandOf(overall),
  pillar_quality: 60, pillar_growth: 60, pillar_profitability: 60, pillar_balance: 60, pillar_technical: 60,
  price: 100, market_cap: 50_000, pe: null, pb: null, roe: null, roce: null, dividend_yield: null, debt_to_equity: null,
  sales_cagr: null, profit_cagr: null, operating_margin: null, change_pct: null, return_1m: null, return_1y: null, ...o,
});
const H = (r: Row): Holding => ({ symbol: r.symbol, name: r.name, row: r });

describe("bands and tiers", () => {
  it("uses site thresholds", () => {
    expect([78, 77, 62, 61, 45, 44].map(bandOf)).toEqual(["strong", "healthy", "healthy", "mixed", "mixed", "watch"]);
    expect(bandOf(null)).toBe("none");
    expect(capTier(null)).toBe(-1); expect(capTier(4999)).toBe(0); expect(capTier(5000)).toBe(1); expect(capTier(100000)).toBe(3);
  });
});

describe("statsOf", () => {
  it("rounds half up and ignores unscored in the average", () => {
    const s = statsOf([H(mk("A", "IT", 60)), H(mk("B", "IT", 61)), { symbol: "C" }]);
    expect(s.avg).toBe(60.5); expect(s.score).toBe(61); expect(s.unscored).toBe(1);
    expect(s.band.none).toBeCloseTo(33.33, 1);
    expect(s.sectors.find((x) => x.name === "Not yet loaded")).toBeTruthy();
  });
  it("handles empty", () => {
    const s = statsOf([]);
    expect(s.score).toBeNull(); expect(s.sectors).toEqual([]); expect(Number.isNaN(s.band.strong)).toBe(false);
  });
});

describe("suggestSwaps", () => {
  const mine = [mk("W1", "Banks", 40, { market_cap: 50_000 }), mk("W2", "IT", 50), mk("OK", "Pharma", 80)].map(H);
  const uni = [
    ...mine.map((h) => h.row!),
    mk("B1", "Banks", 60, { pillar_balance: 90, pillar_quality: 90 }),   // best fit
    mk("B2", "Banks", 70, { pillar_balance: 50, pillar_quality: 50 }),   // higher score, weaker balance/quality
    mk("B3", "Banks", 47),                                              // gain 7 < 8
    mk("B4", "Banks", 90, { market_cap: 1_000 }),                       // smaller tier
    mk("B5", "Banks", 85, { market_cap: null }),                        // unknown cap: not similar-or-larger
    mk("I1", "IT", 80),                                                 // other sector for W1
    mk("N1", null, 95),
  ];
  const g = suggestSwaps(mine, uni);
  it("picks the weakest first and stays in sector", () => {
    expect(g.map((x) => x.from.symbol)).toEqual(["W1", "W2", "OK"]);
    expect(g[0].suggestions.every((s) => s.row.sector === "Banks")).toBe(true);
  });
  it("enforces gain, tier and ranks by balance and quality", () => {
    const ids = g[0].suggestions.map((s) => s.row.symbol);
    expect(ids).toEqual(["B1", "B2"]);
    expect(ids).not.toContain("B3"); expect(ids).not.toContain("B4"); expect(ids).not.toContain("B5");
  });
  it("before/after math", () => {
    // before: (40+50+80)/3 = 56.67 -> 57 ; after W1->B1: (60+50+80)/3 = 63.33 -> 63
    const s = g[0].suggestions[0];
    expect(s.before).toBe(57); expect(s.after).toBe(63); expect(s.delta).toBe(6);
    expect(s.gain).toBe(20);
  });
  it("W2 gets same-sector IT only; strong holding gets none", () => {
    expect(g[1].suggestions.map((s) => s.row.symbol)).toEqual(["I1"]);
    expect(g[2].suggestions).toEqual([]);
  });
  it("never suggests a held share and limits to 3", () => {
    const many = Array.from({ length: 6 }, (_, i) => mk("X" + i, "Banks", 70 + i));
    const r = suggestSwaps([H(mk("W", "Banks", 30))], [...many, mk("W", "Banks", 30)]);
    expect(r[0].suggestions).toHaveLength(3);
    expect(r[0].suggestions.some((s) => s.row.symbol === "W")).toBe(false);
  });
  it("edge cases: empty, tiny universe, unscored, no sector", () => {
    expect(suggestSwaps([], [])).toEqual([]);
    expect(suggestSwaps([{ symbol: "Z" }], uni)).toEqual([]);
    expect(suggestSwaps([H(mk("S", null, 20))], uni)[0].suggestions).toEqual([]);
    expect(suggestSwaps(mine, [])[0].suggestions).toEqual([]);
  });
});

describe("applySwaps", () => {
  const a = H(mk("A", "IT", 40)), b = H(mk("B", "IT", 50)), n = mk("N", "IT", 70);
  it("replaces and ignores held or repeated targets", () => {
    expect(applySwaps([a, b], { A: n }).map((h) => h.symbol)).toEqual(["N", "B"]);
    expect(applySwaps([a, b], { A: n, B: n }).map((h) => h.symbol)).toEqual(["N", "B"]);
    expect(applySwaps([a, b], { A: b.row })).toEqual([a, b]);
  });
});

describe("findGaps", () => {
  const mine = [H(mk("A", "Information Technology", 70, { pillar_growth: 30 }))];
  const uni = [mine[0].row!, mk("F1", "Financial Services", 75), mk("F2", "Financial Services", 82), mk("P1", "Healthcare", 70),
    mk("G1", "Capital Goods", 66, { pillar_growth: 95 }), mk("L1", "Capital Goods", 40, { pillar_growth: 99 })];
  const gaps = findGaps(mine, uni);
  it("reports missing sectors with the top scored pick", () => {
    expect(gaps.find((g) => g.id === "financials")?.pick?.symbol).toBe("F2");
    expect(gaps.find((g) => g.id === "defensive")?.pick?.symbol).toBe("P1");
    expect(gaps.find((g) => g.id === "technology")).toBeUndefined();
  });
  it("reports weak pillar with a sound company", () => {
    const g = gaps.find((x) => x.id === "pillar_growth");
    expect(g?.pick?.symbol).toBe("G1"); expect(g?.reason).toContain("30");
  });
  it("is empty without scores", () => { expect(findGaps([], uni)).toEqual([]); expect(findGaps([{ symbol: "Q" }], uni)).toEqual([]); });
});

describe("stress and resilience", () => {
  const rows = [90, 80, 70, 60, 50].map((o, i) => H(mk("S" + i, "IT", o, { pillar_balance: [20, 40, 70, 80, 90][i], pillar_quality: i < 3 ? 70 : 50 })));
  it("removes the weakest quarter by balance sheet (rounded up)", () => {
    const s = stressView(rows);
    expect(s.eligible).toBe(true); expect(s.removedSymbols).toEqual(["S0", "S1"]);
    expect(s.before).toBe(70); expect(s.after).toBe(60); expect(s.delta).toBe(-10);
  });
  it("needs at least 4", () => { const s = stressView(rows.slice(0, 3)); expect(s.eligible).toBe(false); expect(s.after).toBeNull(); });
  it("resilience share", () => {
    const r = resilience(rows);
    expect(r.sound).toBe(1); expect(r.total).toBe(5); expect(r.pct).toBe(20);
    expect(resilience([]).pct).toBeNull();
  });
});

describe("buildReportHtml", () => {
  it("includes disclaimer, escapes, no NaN", () => {
    const html = buildReportHtml([H(mk("A<b>", "IT & Co", 70)), { symbol: "LOAD" }], new Date("2026-01-02T00:00:00Z"));
    expect(html).toContain("Information only, not investment advice");
    expect(html).toContain("A&lt;b&gt;"); expect(html).toContain("IT &amp; Co"); expect(html).toContain("2026-01-02");
    expect(html).not.toMatch(/NaN|undefined|null/);
  });
  it("works when empty", () => { expect(buildReportHtml([])).toContain("No shares added"); });
});
