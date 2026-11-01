import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { profitReality } from "./profitReality";
import { earningsIntel, isLenderSector, isSoftSector } from "./earningsIntel";
import { EarningsIntel } from "../stock/EarningsIntel";

const t = (periods: string[], rows: Record<string, (number | null)[]>) => ({ unit: "Cr", period: "yearly", periods, periodEnds: periods, rows });
const P = ["FY21", "FY22", "FY23", "FY24", "FY25", "FY26"];
// The owner's example: OCF negative in FY22, FY23 and FY26; profit +80.6% in FY26; receivables +89% against revenue +57.9%.
const pl = t(P, { revenue: [700, 800, 900, 950, 1000, 1579], net_profit: [300, 398, 304, 101.5, 551.5, 996], profit_before_tax: [400, 530, 405, 135, 735, 1330], tax: [100, 132, 101, 34, 184, 334] });
const cf = t(P, { operating: [200, -44, -2377, 1437, 1386, -1012], free_cash_flow: [100, -150, -2500, 300, 200, -1100] });
const bs = t(P, { receivables: [100, 120, 140, 160, 200, 378], inventories: [90, 95, 100, 100, 100, 180] });
const run = (lender = false, sector?: string, ind?: string) => { const r = profitReality(pl, bs, cf, lender); return { r, x: earningsIntel(r, sector, ind)! }; };
const mod = (x: ReturnType<typeof earningsIntel>, k: string) => x!.modules.find((m) => m.key === k)!;

describe("sign and rounding of operating cash flow / profit", () => {
  it("keeps the sign and rounds correctly", () => {
    const { r } = run();
    const by = Object.fromEntries(r.years.map((y) => [y.period, Math.round(y.cfoToProfit! * 100)]));
    expect(by.FY22).toBe(-11); expect(by.FY23).toBe(-782); expect(by.FY26).toBe(-102);
  });
  it("five-year total is negative and worded for a negative total", () => {
    const { r } = run();
    expect(r.cumulative).toMatchObject({ cfo: -610, profit: 2351 });
    expect(Math.round(r.cumulative!.ratio! * 100)).toBe(-26);
    const f = r.findings.join(" ");
    expect(f).toContain("Operating cash flow was negative over the 5 years: −₹610 crore against ₹2,351 crore of profit (−26% of profit)");
    expect(f).not.toMatch(/turned -26%/);
  });
  it("the row, the gap count and the tile use the corrected values", async () => {
    vi.resetModules();
    vi.doMock("../components/ChartHelp", () => ({ ChartHelp: () => null }));
    vi.doMock("../lib/api", async (orig) => ({ ...(await orig<object>()), useSection: () => ({ data: { yearly: { pl, bs, cf } } }) }));
    const { ProfitReality } = await import("../stock/ProfitReality");
    const html = renderToStaticMarkup(<ProfitReality symbol="X" lender={false} sector="Capital Goods" industry="Engineering" />);
    expect(html).toContain("−11%"); expect(html).toContain("−782%"); expect(html).toContain("−102%");
    expect(html).not.toMatch(/>782%|>102%|>11%</);
    expect(html).toContain("Operating cash flow was negative over the 5 years (−26% of profit)");
    expect(html).toContain("Reported profit against normalized profit");   // data part still there
    expect(html.indexOf("Earnings Quality Intelligence")).toBeLessThan(html.indexOf("Reported profit against normalized profit"));
    vi.doUnmock("../lib/api"); vi.doUnmock("../components/ChartHelp");
  });
});

describe("earnings intelligence rules", () => {
  it("header stats show honest signs", () => {
    const { x } = run();
    expect(x.stats[0]).toMatchObject({ label: "Profit growth", value: "+80.6%", sub: "Mar 2026 YoY" });
    expect(x.stats[1].value).toBe("−₹1,012 Cr");
  });
  it("owner example: weak cash backing, receivables and inventory investigate, text generated from data", () => {
    const { x } = run();
    expect(x.pill.label).toBe("Weak cash backing");
    expect(mod(x, "cash").badge).toBe("Red flag");
    expect(mod(x, "receivables").badge).toBe("Investigate");
    expect(mod(x, "receivables").facts[0]).toBe("Receivables grew 89.0% vs revenue 57.9% in Mar 2026.");
    expect(mod(x, "inventory").badge).toBe("Investigate");
    expect(mod(x, "fcf").badge).toBe("Weak");
    expect(x.happening).toContain("Profit is growing, but cash generation has weakened significantly");
    expect(x.happening).toContain("Receivables and inventory are also growing faster than revenue.");
    expect(x.questions.length).toBeGreaterThanOrEqual(3);
  });
  it("a single bad year alone is Watch, not Red flag", () => {
    const c = t(P, { operating: [300, 600, 500, 300, 1500, -1012], free_cash_flow: [100, 300, 200, 80, 400, -1100] });
    const x = earningsIntel(profitReality(pl, bs, c, false))!;
    expect(mod(x, "cash").badge).toBe("Watch"); expect(x.pill.label).toBe("Cash backing to watch");
  });
  it("steady when cash follows profit", () => {
    const c = t(P, { operating: [300, 400, 320, 110, 560, 1000], free_cash_flow: [250, 350, 280, 90, 500, 900] });
    const x = earningsIntel(profitReality(pl, bs, c, false))!;
    expect(mod(x, "cash").badge).toBe("Steady"); expect(x.pill.label).toBe("Cash backing steady"); expect(mod(x, "fcf").badge).toBe("Strong");
  });
  it("FCF adequate between 20% and 60%", () => {
    const c = t(P, { operating: [300, 400, 320, 110, 560, 1000], free_cash_flow: [100, 150, 100, 30, 200, 300] });
    expect(mod(earningsIntel(profitReality(pl, bs, c, false))!, "fcf").badge).toBe("Adequate");
  });
  it("missing inputs give Not enough data and never a guess", () => {
    const x = earningsIntel(profitReality(pl, undefined, undefined, false))!;
    expect(mod(x, "cash").badge).toBe("Not enough data"); expect(mod(x, "receivables").badge).toBe("Not enough data");
    expect(mod(x, "inventory").badge).toBe("Not enough data"); expect(mod(x, "fcf").badge).toBe("Not enough data");
    expect(x.pill.label).toBe("Not enough data"); expect(x.stats[1].value).toBe("Not available");
  });
  it("normalized earnings: unstable at 30% gap, stable when close", () => {
    const stable = earningsIntel(profitReality(pl, bs, cf, false))!;
    expect(mod(stable, "normalized").badge).toBe("Relatively stable");
    const p2 = t(P, { revenue: [1, 1, 1, 1, 1, 1], net_profit: [100, 100, 100, 100, 100, 300], profit_before_tax: [130, 130, 130, 130, 130, 200], tax: [30, 30, 30, 30, 30, 100], exceptional_items: [0, 0, 0, 0, 0, 200] });
    expect(mod(earningsIntel(profitReality(p2, undefined, undefined, false))!, "normalized").badge).toBe("Unstable");
  });
  it("lenders: no cash-based modules, message shown", () => {
    const x = earningsIntel(profitReality(pl, bs, cf, true))!;
    expect(x.lender).toBe(true); expect(x.pill.label).toBe("Cash-flow analysis not comparable");
    expect(x.modules.map((m) => m.key)).toEqual(["normalized", "sustain"]);
    expect(x.stats[1].sub).toBe("Cash-flow analysis is not comparable for lenders");
    const html = renderToStaticMarkup(<EarningsIntel pr={profitReality(pl, bs, cf, true)} />);
    expect(html).toContain("Cash-flow analysis is not comparable for lenders");
    expect(html).not.toContain("Profit vs Cash Flow");
    expect(earningsIntel(profitReality(pl, bs, cf, false), "Financial Services", "Private Sector Bank")!.lender).toBe(true);
  });
  it("sector softening: red flag becomes watch in project-based industries, caveat always present", () => {
    const { x } = run(false, "Capital Goods", "Construction & Engineering");
    expect(x.softened).toBe(true); expect(mod(x, "cash").badge).toBe("Watch");
    expect(x.caveats[0]).toBe("Some businesses have seasonal or project-based cash cycles.");
    expect(isSoftSector("Services", "IT Services")).toBe(false); expect(isLenderSector("Financial Services", "NBFC")).toBe(true);
  });
  it("sustainability reviews repeated one-offs", () => {
    const p3 = t(P, { net_profit: [100, 100, 100, 100, 100, 100], profit_before_tax: [130, 130, 130, 130, 130, 130], tax: [30, 30, 30, 30, 30, 30], exceptional_items: [0, 0, 0, 0, 30, 30] });
    expect(mod(earningsIntel(profitReality(p3, undefined, undefined, false))!, "sustain").badge).toBe("Review");
  });
  it("no advice words, no accusation, and peer comparison stated unavailable", () => {
    const { x } = run();
    const html = renderToStaticMarkup(<EarningsIntel pr={profitReality(pl, bs, cf, false)} />);
    const all = JSON.stringify(x) + html;
    expect(all).not.toMatch(/\b(buy|sell|hold|avoid|target|fraud\w*|manipulat\w*)\b/i);
    expect(html).toContain("Peer comparison: not available");
    expect(html).toContain("not a recommendation. Information only, not investment advice.");
    expect(html).toContain("Some businesses have seasonal or project-based cash cycles.");
    for (const h of ["What is happening?", "What should you investigate?", "Intelligence modules", "How this is decided"]) expect(html).toContain(h);
    expect(html).toContain("−₹1,012 Cr");
  });
});
