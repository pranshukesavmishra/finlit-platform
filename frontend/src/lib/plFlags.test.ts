import { describe, expect, it } from "vitest";
import cases from "./fixtures/plFlags.cases.json";
import { CASES, divergenceRun, highlightMap, move, plFlags, plInsights, priorIndex, T, type PlInput } from "./plFlags";
import type { Table } from "./api";

const tbl = (t: unknown): Table | undefined => t ? ({ unit: "Cr", period: "yearly", ...(t as object) } as Table) : undefined;

describe("plFlags shared cases (also run by the backend tests)", () => {
  for (const c of cases.cases) {
    it(c.name, () => {
      const got = plFlags({ annual: tbl((c as { annual?: unknown }).annual), quarterly: tbl((c as { quarterly?: unknown }).quarterly) }).map((f) => f.key).sort();
      expect(got).toEqual(c.expect);
    });
  }
  it("covers all eight cases", () => {
    const seen = new Set(cases.cases.flatMap((c) => c.expect.map((k) => k.split(":")[0])));
    expect([...seen].sort()).toEqual(["1", "2", "3", "4", "5", "6", "7", "8"]);
  });
});

const A = (rev: (number | null)[], np: (number | null)[], op?: (number | null)[]): PlInput => ({ annual: tbl({ periods: ["FY25", "FY26"], periodEnds: ["2025-03-31", "2026-03-31"], rows: { revenue: rev, net_profit: np, ...(op ? { operating_profit: op } : {}) } }) });

describe("plFlags details", () => {
  it("never flags on missing input, nulls, NaN or Infinity", () => {
    expect(plFlags(null)).toEqual([]);
    expect(plFlags(undefined)).toEqual([]);
    expect(plFlags({})).toEqual([]);
    expect(plFlags(A([100, NaN], [10, 15]))).toEqual([]);
    expect(plFlags(A([100, 110], [10, Infinity]))).toEqual([]);
    expect(plFlags({ annual: tbl({ periods: [], periodEnds: [], rows: {} }) })).toEqual([]);
    expect(plFlags({ annual: tbl({ periods: ["FY26"], periodEnds: [], rows: { revenue: [1], net_profit: [1] } }) })).toEqual([]);
  });
  it("describes a case 3 flag in plain words with figures, period and rows", () => {
    const [f] = plFlags(A([100, 110], [10, 9]));
    expect(f).toMatchObject({ case: 3, id: "revenue_up_profit_down", severity: "caution", scope: "annual", period: "FY26", against: "FY25", revenueGrowth: 10, profitGrowth: -10, key: "3:annual:FY26" });
    expect(f.text).toBe("Revenue grew 10.0% while net profit fell 10.0%. Compared with FY25.");
    expect(f.rows).toEqual(["revenue", "net_profit"]);
    expect(f.periods).toEqual(["FY26", "FY25"]);
    expect(f.why.length).toBeGreaterThan(10);
  });
  it("uses words, not a percentage, for a swing from loss to profit", () => {
    const [f] = plFlags(A([100, 101], [-5, 4]));
    expect(f.case).toBe(5);
    expect(f.profitGrowth).toBeNull();
    expect(f.text).toContain("turned from a loss of ₹5 crore to a profit of ₹4 crore");
  });
  it("case 7 highlights net and operating profit", () => {
    const [f] = plFlags(A([100, 110], [10, 12], [20, 18]));
    expect(f.rows).toEqual(["net_profit", "operating_profit"]);
    expect(f.operatingGrowth).toBe(-10);
  });
  it("only highlights rows that exist in the table", () => {
    const [f] = plFlags({ annual: tbl({ periods: ["FY25", "FY26"], periodEnds: ["2025-03-31", "2026-03-31"], rows: { net_profit: [10, 12], operating_profit: [20, 18] } }) });
    expect(f.case).toBe(7); expect(f.rows).toEqual(["net_profit", "operating_profit"]);
  });
  it("every case has plain, non-advisory wording", () => {
    for (const c of Object.values(CASES)) expect(`${c.title} ${c.why}`).not.toMatch(/\b(buy|sell|avoid|invest|recommend)\b/i);
  });
  it("sorts by case number and has unique keys", () => {
    const fl = plFlags({ ...A([100, 125], [10, 10.1]), quarterly: tbl({ periods: ["Dec 2024", "Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026"], periodEnds: ["2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"], rows: { revenue: [100, 100, 100, 100, 110, 112], net_profit: [10, 10, 10, 10, 8, 7] } }) });
    expect(fl.map((f) => f.case)).toEqual([4, 8]);
    expect(new Set(fl.map((f) => f.key)).size).toBe(fl.length);
    const run = fl.find((f) => f.case === 8)!;
    expect(run.periods).toEqual(expect.arrayContaining(["Mar 2026", "Dec 2025", "Mar 2025", "Dec 2024"]));
    expect(run.text).toContain("2 quarters in a row, from Dec 2025 to Mar 2026");
  });
});

describe("helpers", () => {
  it("move handles zero and negative bases", () => {
    expect(move(null, 5)).toBeNull();
    expect(move(5, null)).toBeNull();
    expect(move(5, 0)).toMatchObject({ pct: null, dir: 1 });
    expect(move(0, 0)).toMatchObject({ pct: null, dir: 0 });
    expect(move(-5, 0)).toMatchObject({ dir: -1 });
    expect(move(-8, -10)).toMatchObject({ pct: 20, dir: 1 });
    expect(move(-12, -10)).toMatchObject({ pct: -20, dir: -1 });
    expect(move(100.2, 100)!.dir).toBe(0);
    expect(T.deadBand).toBeGreaterThan(0);
  });
  it("finds the period a year before by end date, not by position", () => {
    const t = tbl({ periods: ["a", "b", "c"], periodEnds: ["2024-12-31", "2025-09-30", "2025-12-31"], rows: {} })!;
    expect(priorIndex(t, 2, "year")).toBe(0);
    expect(priorIndex(t, 2, "quarter")).toBe(1);
    expect(priorIndex(t, 1, "year")).toBeNull();
    const fy = tbl({ periods: ["FY24", "FY25", "FY27"], periodEnds: [], rows: {} })!;
    expect(priorIndex(fy, 1, "year")).toBe(0);
    expect(priorIndex(fy, 2, "year")).toBeNull();
    expect(priorIndex(fy, 1, "quarter")).toBeNull();
  });
  it("divergenceRun is null with no divergence", () => {
    const t = tbl({ periods: ["a", "b"], periodEnds: ["2025-03-31", "2026-03-31"], rows: { revenue: [100, 110], net_profit: [10, 12] } })!;
    expect(divergenceRun(t)).toBeNull();
  });
  it("highlightMap groups rows and periods per scope and can be switched off", () => {
    const fl = plFlags(A([100, 110], [10, 12], [20, 18]));
    const on = highlightMap(fl);
    expect([...on.annual.net_profit].sort()).toEqual(["FY25", "FY26"]);
    expect(Object.keys(on.quarterly)).toEqual([]);
    expect(highlightMap(fl, false)).toEqual({ annual: {}, quarterly: {} });
  });
});

describe("plInsights: latest quarter and latest year together", () => {
  const Q = (rev: number[], np: number[], extra: Record<string, number[]> = {}) => tbl({ period: "quarterly", periods: ["Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"], periodEnds: ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"], rows: { revenue: rev, net_profit: np, ...extra } });
  const Y = (rev: number[], np: number[], extra: Record<string, number[]> = {}) => tbl({ periods: ["FY25", "FY26"], periodEnds: ["2025-03-31", "2026-03-31"], rows: { revenue: rev, net_profit: np, ...extra } });
  it("a quarter-only flag is labelled as the quarter and names the periods exactly", () => {
    const [x] = plInsights({ annual: Y([100, 105], [10, 10.5]), quarterly: Q([100, 100, 100, 100, 110], [10, 10, 10, 10, 8]) });
    expect(x.case).toBe(3); expect(x.headline).toBe("quarterly");
    expect(x.title).toBe("Revenue rose while profit fell in the latest quarter");
    expect(x.views.quarterly).toMatchObject({ label: "Latest quarter", period: "Sep 2026", against: "Sep 2025", periodEnd: "2026-09-30", againstEnd: "2025-09-30", triggered: true });
    expect(x.views.annual).toMatchObject({ period: "FY26", against: "FY25", triggered: false });   // the year still shows its own figures
    expect(x.views.annual!.growth).toMatchObject({ revenue: 5, profit: 5 });
    expect(x.key).toBe("3:quarterly:Sep 2026");
  });
  it("when the year and the quarter both trigger there is one insight with two views; the fresher quarter is the headline", () => {
    const list = plInsights({ annual: Y([100, 106.3], [10, 8.72]), quarterly: Q([100, 100, 100, 100, 110], [10, 10, 10, 10, 8]) });
    expect(list).toHaveLength(1);
    const x = list[0];
    expect(Object.keys(x.views).sort()).toEqual(["annual", "quarterly"]);
    expect(x.views.annual).toMatchObject({ triggered: true, growth: { revenue: 6.3, profit: -12.8 } });
    expect(x.headline).toBe("quarterly");
    expect(x.views.quarterly!.qoq).toMatchObject({ period: "Sep 2026", against: "Jun 2026" });
    expect(x.views.quarterly!.qoq!.growth.revenue).toBe(10);
  });
  it("a year-only flag keeps the annual headline and a quarter without flag still shows", () => {
    const [x] = plInsights({ annual: Y([100, 110], [10, 8]), quarterly: Q([100, 100, 100, 100, 101], [10, 10, 10, 10, 10.2]) });
    expect(x.headline).toBe("annual"); expect(x.title).toBe("Revenue rose while profit fell");
    expect(x.views.quarterly!.triggered).toBe(false); expect(x.views.annual!.triggered).toBe(true);
  });
  it("the year is the headline when the quarter and the year end on the same day", () => {
    const q = tbl({ period: "quarterly", periods: ["Mar 2025", "Mar 2026"], periodEnds: ["2025-03-31", "2026-03-31"], rows: { revenue: [100, 110], net_profit: [10, 8] } });
    const [x] = plInsights({ annual: Y([100, 110], [10, 8]), quarterly: q });
    expect(x.headline).toBe("annual");
  });
  it("a missing quarter never shifts a comparison", () => {
    const q = tbl({ period: "quarterly", periods: ["Sep 2025", "Mar 2026", "Sep 2026"], periodEnds: ["2025-09-30", "2026-03-31", "2026-09-30"], rows: { revenue: [100, 100, 110], net_profit: [10, 10, 8] } });
    const [x] = plInsights({ quarterly: q });
    expect(x.views.quarterly).toMatchObject({ against: "Sep 2025", period: "Sep 2026" });
    expect(x.views.quarterly!.qoq).toBeNull();   // no quarter ended about 91 days earlier
    const gap = plInsights({ quarterly: tbl({ period: "quarterly", periods: ["Dec 2025", "Mar 2026", "Sep 2026"], periodEnds: ["2025-12-31", "2026-03-31", "2026-09-30"], rows: { revenue: [100, 100, 110], net_profit: [10, 10, 8] } }) });
    expect(gap).toEqual([]);   // nothing a year before Sep 2026, so no comparison at all
  });
  it("all eight cases can be reached on the quarterly series alone", () => {
    const seen = new Set<number>();
    for (const c of cases.cases) { const qq = (c as { quarterly?: unknown }).quarterly; if (qq) plInsights({ quarterly: tbl(qq) }).forEach((x) => seen.add(x.case)); }
    expect(seen.has(8)).toBe(true);
  });
  it("lenders: revenue is total income and operating profit is never used", () => {
    const rows = { revenue: [100, 110], total_income: [200, 200], net_profit: [20, 22], operating_profit: [50, 40] };
    expect(plInsights({ annual: Y(rows.revenue, rows.net_profit, { operating_profit: rows.operating_profit }) }).map((x) => x.case)).toEqual([7]);
    const lend = plInsights({ lender: true, annual: Y(rows.revenue, rows.net_profit, { total_income: rows.total_income, operating_profit: rows.operating_profit }) });
    expect(lend).toEqual([]);   // total income flat, profit flat: no case, and case 7 cannot fire without operating profit
    const k = plInsights({ lender: true, annual: Y([100, 110], [10, 9], { total_income: [200, 230], operating_profit: [5, 4] }) })[0];
    expect(k.views.annual!.growth).toEqual({ revenue: 15, profit: -10, operating: null });
    expect(k.lender).toBe(true);
  });
  it("the quarterly series is read from the same table, so a new quarter changes the headline without a code change", () => {
    const before = plInsights({ quarterly: Q([100, 100, 100, 100, 110], [10, 10, 10, 10, 8]) })[0];
    const next = tbl({ period: "quarterly", periods: ["Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026", "Dec 2026"], periodEnds: ["2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31"], rows: { revenue: [100, 100, 100, 110, 90], net_profit: [10, 10, 10, 8, 9] } });
    const after = plInsights({ quarterly: next })[0];
    expect(before.views.quarterly!.period).toBe("Sep 2026"); expect(after.views.quarterly!.period).toBe("Dec 2026");
    expect(after.case).toBe(6);
  });
});
