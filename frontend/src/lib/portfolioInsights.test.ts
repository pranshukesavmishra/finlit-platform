import { describe, expect, it } from "vitest";
import { portfolioInsights, bandOf, type InsightLine } from "./portfolioInsights";
import type { Row } from "./screener";

const row = (o: Partial<Row> & { symbol: string }): Row => ({
  name: o.symbol, sector: "IT", overall: 70, band: "healthy", pillar_quality: 70, pillar_growth: 70, pillar_profitability: 70, pillar_balance: 70, pillar_technical: 70,
  price: 100, market_cap: 200000, pe: null, pb: null, roe: null, roce: null, dividend_yield: null, debt_to_equity: null, sales_cagr: null, profit_cagr: null,
  operating_margin: null, change_pct: null, return_1m: null, return_1y: null, ...o,
});
const L = (o: Partial<Row> & { symbol: string }): InsightLine => ({ symbol: o.symbol, name: o.symbol + " Ltd", row: row(o) });
const noBad = (x: unknown) => expect(JSON.stringify(x)).not.toMatch(/NaN|undefined|Infinity/);

describe("portfolioInsights", () => {
  it("bands", () => { expect([bandOf(78), bandOf(62), bandOf(45), bandOf(44.9)]).toEqual(["strong", "healthy", "mixed", "watch"]); });

  it("handles empty", () => {
    const m = portfolioInsights([]);
    expect(m.empty).toBe(true); expect(m.health).toBeNull(); expect(m.priorities).toEqual([]); noBad(m);
  });

  it("excludes rows still loading and says so", () => {
    const m = portfolioInsights([L({ symbol: "A", overall: 80 }), { symbol: "B", name: "B" }, L({ symbol: "C", overall: null })]);
    expect(m.total).toBe(3); expect(m.scored).toBe(1); expect(m.preparing).toBe(2);
    expect(m.note).toMatch(/2 holdings are still being prepared/); noBad(m);
  });

  it("all loading gives no health but a note", () => {
    const m = portfolioInsights([{ symbol: "B", name: "B" }]);
    expect(m.health).toBeNull(); expect(m.note).toMatch(/1 holding is still being prepared/); noBad(m);
  });

  it("single holding: no weakest list, no spread flags", () => {
    const m = portfolioInsights([L({ symbol: "A", overall: 80 })]);
    expect(m.health?.score).toBe(80); expect(m.health?.band).toBe("strong");
    expect(m.strongest).toHaveLength(1); expect(m.weakest).toHaveLength(0); expect(m.enough).toBe(false);
    expect(m.diversification?.flags).toEqual([]); noBad(m);
  });

  it("flags sector > 40% and fewer than 5 sectors", () => {
    const m = portfolioInsights([L({ symbol: "A" }), L({ symbol: "B" }), L({ symbol: "C", sector: "Banks" })]);
    const d = m.diversification!;
    expect(d.top?.sector).toBe("IT"); expect(Math.round(d.top!.share)).toBe(67);
    expect(d.flags.some((f) => /more than 40%/.test(f))).toBe(true);
    expect(d.flags.some((f) => /fewer than 5/.test(f))).toBe(true);
    expect(d.label).toBe("Concentrated"); expect(d.hhi).toBe(5556);
  });

  it("well spread across 5+ sectors has no flags", () => {
    const m = portfolioInsights(["a", "b", "c", "d", "e", "f", "g", "h"].map((s) => L({ symbol: s, sector: s })));
    expect(m.diversification!.flags).toEqual([]); expect(m.diversification!.label).toBe("Well spread");
    expect(m.diversification!.hhi).toBe(1250);
  });

  it("market-cap mix and missing values", () => {
    const m = portfolioInsights([L({ symbol: "A", market_cap: 150000 }), L({ symbol: "B", market_cap: 40000 }), L({ symbol: "C", market_cap: 900 }), L({ symbol: "D", market_cap: null, sector: null })]);
    const c = m.diversification!.caps;
    expect([c.large, c.mid, c.small, c.unknown]).toEqual([1, 1, 1, 1]);
    expect(m.diversification!.unknownSector).toBe(1); expect(m.diversification!.sectorCount).toBe(1); noBad(m);
  });

  it("strongest/weakest with leading and dragging pillar", () => {
    const m = portfolioInsights([
      L({ symbol: "TOP", overall: 90, pillar_growth: 99 }),
      L({ symbol: "MID", overall: 60 }),
      L({ symbol: "LOW", overall: 30, pillar_balance: 10 }),
    ]);
    expect(m.strongest[0].symbol).toBe("TOP"); expect(m.strongest[0].pillarLabel).toBe("Growth");
    expect(m.weakest[0].symbol).toBe("LOW"); expect(m.weakest[0].pillarLabel).toBe("Balance sheet");
    expect(m.strongest.map((s) => s.symbol)).not.toContain("LOW");
  });

  it("pillar strength and weakest link", () => {
    const m = portfolioInsights([L({ symbol: "A", pillar_quality: 90, pillar_balance: 20 }), L({ symbol: "B", pillar_quality: 80, pillar_balance: 30 })]);
    expect(m.strengthPillar?.key).toBe("pillar_quality"); expect(m.weakPillar?.key).toBe("pillar_balance");
    expect(m.pillarSentence).toMatch(/Quality is the portfolio's strength/);
  });

  it("even pillars give a neutral sentence; null pillars are skipped", () => {
    const m = portfolioInsights([L({ symbol: "A", pillar_growth: null, pillar_technical: null })]);
    expect(m.pillarSentence).toMatch(/fairly even/); expect(m.pillars.filter((p) => p.avg == null)).toHaveLength(2); noBad(m);
  });

  it("risk shares and priorities link to stocks", () => {
    const m = portfolioInsights([
      L({ symbol: "W", overall: 30, pillar_balance: 20, pillar_technical: 20 }),
      L({ symbol: "X", overall: 70, pillar_balance: 30 }),
      L({ symbol: "Y", overall: 80 }), L({ symbol: "Z", overall: 75 }),
    ]);
    expect(m.risk!.watchCount).toBe(1); expect(m.risk!.watchShare).toBe(25);
    expect(m.risk!.weakBalanceCount).toBe(2); expect(m.risk!.momentumPositive).toBe(3);
    expect(m.priorities[0].symbol).toBe("W"); expect(m.priorities.length).toBeLessThanOrEqual(4);
    expect(new Set(m.priorities.map((p) => p.symbol)).size).toBe(m.priorities.length); noBad(m);
  });

  it("dedupes symbols, ignores non-finite scores, never advises", () => {
    const m = portfolioInsights([L({ symbol: "A" }), L({ symbol: "A" }), L({ symbol: "B", overall: NaN })]);
    expect(m.total).toBe(2); expect(m.scored).toBe(1);
    expect(JSON.stringify(m)).not.toMatch(/\b(should buy|should sell|buy now|sell now)\b/i); noBad(m);
  });
});
