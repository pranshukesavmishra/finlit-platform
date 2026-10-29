import { describe, expect, it } from "vitest";
import type { Segments } from "./api";
import real from "./__fixtures__/segments-reliance-fixture.json";
import large from "./__fixtures__/segments-large-fixture.json";
import { axisCr, chartModel, mixStatus, niceTicks, pp, REMAINING, segmentColors, segmentNames, sortRows, stackTop, tableRows } from "./segmentMix";

const REAL = real as unknown as Segments, LARGE = large as unknown as Segments;
const mk = (periods: string[], rows: Record<string, (number | null)[]>, extra: Partial<Segments> = {}): Segments => ({
  meta: { symbol: "X", statement: "consolidated", generatedAt: "", version: 1, scoreModel: "" }, unit: "Cr", periods,
  segments: Object.fromEntries(Object.entries(rows).map(([k, v]) => [k, { revenue: v, ebit: v.map(() => null) }])), latest: [], ...extra,
});

describe("segment colours", () => {
  it("gives each named segment its own token and Others a neutral one, in a stable order", () => {
    const names = segmentNames(REAL), { color, grouped } = segmentColors(names);
    expect(grouped).toEqual([]);
    expect(names.slice(0, 3)).toEqual(["Oil to Chemicals (O2C)", "Oil and Gas", "Others"]);
    expect(color["Oil to Chemicals (O2C)"]).toBe("var(--k1)");
    expect(color.Others).toBe("var(--faint)");
    const used = Object.values(color).filter((c) => c !== "var(--faint)");
    expect(new Set(used).size).toBe(used.length);
  });
  it("puts segments no longer reported after the active ones", () => {
    const n = segmentNames(REAL);
    expect(n.indexOf("Petrochemicals")).toBeGreaterThan(n.indexOf("Retail"));
    expect(n.indexOf("Financial Services")).toBeGreaterThan(n.indexOf("Retail"));
  });
  it("groups everything past eight named segments into one neutral series", () => {
    const rows: Record<string, number[]> = {};
    for (let i = 0; i < 11; i++) rows["S" + i] = [100 - i, 100 - i, 100 - i];
    const m = chartModel(mk(["FY24", "FY25", "FY26"], rows));
    expect(m.series).toHaveLength(9);
    const rest = m.series[8];
    expect(rest.label).toBe(REMAINING);
    expect(rest.members).toHaveLength(3);
    expect(rest.values[0]).toBe(92 + 91 + 90);
  });
});

describe("chart model", () => {
  it("keeps every year, nulls stay null, and shares add to 100 over the sum of segment revenues", () => {
    const m = chartModel(REAL);
    expect(m.years).toHaveLength(8);
    const pet = m.series.find((s) => s.label === "Petrochemicals")!;
    expect(pet.values[0]).toBeGreaterThan(0);
    expect(pet.values[7]).toBeNull();
    for (let i = 0; i < 8; i++) expect(m.series.reduce((a, s) => a + (s.shares[i] ?? 0), 0)).toBeCloseTo(100, 6);
    expect(stackTop(m, 0, "share")).toBeCloseTo(100, 6);
    expect(stackTop(m, 7, "revenue")).toBeCloseTo(m.totals[7], 6);
  });
  it("matches the server's latest-year shares", () => {
    const m = chartModel(LARGE);
    const o2c = m.series.find((s) => s.label === "Oil to Chemicals (O2C)")!;
    const tile = LARGE.latest.find((s) => s.name === "Oil to Chemicals (O2C)")!;
    expect(o2c.shares[7]).toBeCloseTo(tile.sharePct as number, 1);
  });
  it("ignores a negative revenue in the stack but keeps it in the data", () => {
    const m = chartModel(mk(["FY25", "FY26"], { A: [100, 100], Elim: [-20, -20] }));
    expect(stackTop(m, 1, "revenue")).toBe(100);
    expect(m.series.find((s) => s.label === "Elim")!.values[1]).toBe(-20);
  });
  it("handles missing data", () => {
    expect(chartModel(undefined).series).toEqual([]);
    expect(chartModel(mk([], {})).years).toEqual([]);
  });
});

describe("axis", () => {
  it("makes round ticks that cover the maximum", () => {
    expect(niceTicks(547000)).toEqual([0, 200000, 400000, 600000]);
    for (const max of [3, 87, 547000, 1234567, 100]) { const t = niceTicks(max); expect(t[0]).toBe(0); expect(t[t.length - 1]).toBeGreaterThanOrEqual(max); expect(t.length).toBeLessThanOrEqual(7); }
    expect(niceTicks(0)).toEqual([0, 1]);
  });
  it("writes lakh crore for big numbers", () => {
    expect(axisCr(0)).toBe("0");
    expect(axisCr(25000)).toBe("25,000");
    expect(axisCr(100000)).toBe("1 L");
    expect(axisCr(250000)).toBe("2.5 L");
    expect(axisCr(662000)).toBe("6.62 L");
    expect(pp(3.84)).toBe("▲ +3.8 pp");
    expect(pp(-0.44)).toBe("▼ −0.4 pp");
    expect(pp(null)).toBe("—");
  });
});

describe("table rows", () => {
  it("uses the server's numbers and keeps not-reported segments last", () => {
    const rows = tableRows(REAL);
    expect(rows.length).toBe(Object.keys(REAL.segments).length);
    const og = rows.find((r) => r.name === "Oil and Gas")!;
    expect(og.trend).toBe("growing");
    expect(og.cagrPct).toBeGreaterThan(30);
    expect(rows.slice(-2).every((r) => r.notReported)).toBe(true);
    expect(rows.find((r) => r.name === "Others")!.flag).toMatch(/FY24/);
  });
  it("sorts by share or growth with missing values last and gone rows at the bottom", () => {
    const byShare = sortRows(tableRows(LARGE), "share").filter((r) => !r.notReported).map((r) => r.sharePct as number);
    expect([...byShare].sort((a, b) => b - a)).toEqual(byShare);
    const g = sortRows(tableRows(LARGE), "growth");
    expect(g.slice(-2).every((r) => r.notReported)).toBe(true);
    expect(sortRows(tableRows(LARGE), "default")).toEqual(tableRows(LARGE));
  });
  it("still produces plain rows for a report stored before insights existed", () => {
    const old = { ...REAL, insights: undefined } as Segments;
    const rows = tableRows(old);
    const o2c = rows.find((r) => r.name === "Oil to Chemicals (O2C)")!;
    expect(o2c.sharePct).toBeGreaterThan(90);
    expect(o2c.trend).toBeNull();
    expect(o2c.yoyPct).toBeCloseTo((505114 / 512829 - 1) * 100, 1);
    expect(o2c.marginPct).toBeCloseTo(6.91, 1);
  });
});

describe("empty states", () => {
  it("none, single, short and ok", () => {
    expect(mixStatus(undefined).status).toBe("none");
    expect(mixStatus(mk([], {}, { insights: undefined })).text).toBe("Segment history is not available for this company.");
    expect(mixStatus(mk(["FY24", "FY25", "FY26"], { A: [1, 2, 3] })).text).toBe("This company reports a single business segment.");
    expect(mixStatus(mk(["FY25", "FY26"], { A: [1, 2], B: [1, 1] })).status).toBe("short");
    expect(mixStatus(REAL).status).toBe("ok");
  });
  it("takes the server's status when it is there", () => {
    const s = mk(["FY26"], { A: [1] }, { insights: { status: "single", statusText: "", latestPeriod: "FY26", basis: "", rows: [], sentences: [], cautions: [] } });
    expect(mixStatus(s).text).toBe("This company reports a single business segment.");
  });
});
