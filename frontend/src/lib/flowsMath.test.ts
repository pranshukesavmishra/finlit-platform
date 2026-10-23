import { describe, expect, it } from "vitest";
import sample from "./fixtures/flows.sample.json";
import type { FlowDay, Flows } from "./flows";
import { absorption, ageLabel, calendar, combined, corrWords, cumulative, diiState, filterDays, grp, indexCorrelation, inr, level, monthGrid, movingAverage, percentileOf, rangeRows, runs, sinceMonths, sortDays, splitOf, summarize, toCsv, topRuns, totalSince } from "./flowsMath";

const F = sample as unknown as Flows;
const noDii: Flows = { ...F, days: F.days.map((d) => ({ ...d, dii: null })), latest: { ...F.latest!, dii: null, combinedNet: null }, streaks: { fii: F.streaks.fii, dii: null }, last30: { ...F.last30, dii: null }, coverage: { ...F.coverage, diiSessions: 0 }, monthly: F.monthly.map((m) => ({ ...m, dii: null })), yearly: F.yearly.map((y) => ({ ...y, dii: null })) };
const mk = (d: string, f: number | null, i?: number | null): FlowDay => ({ d, fii: { buy: null, sell: null, net: f }, dii: i === undefined ? null : { buy: null, sell: null, net: i } });

describe("flowsMath", () => {
  it("fixture is clearly a sample and sizeable", () => { expect((F as unknown as { _sample: boolean })._sample).toBe(true); expect(F.days.length).toBeGreaterThan(1200); });
  it("cumulative adds in order and skips missing", () => {
    const d = [mk("2026-01-01", 10, 1), mk("2026-01-02", -4, null as never), mk("2026-01-05", 6, 3)];
    expect(cumulative(d, "fii").map((p) => p[1])).toEqual([10, 6, 12]);
    expect(cumulative([mk("a", 1, 2), mk("b", 1, null as never), mk("c", 5, 5)], "dii").map((p) => p[1])).toEqual([2, 7]);
    expect(cumulative([mk("a", 1, 2), mk("b", 1, null as never), mk("c", 5, 5)], "all").map((p) => p[1])).toEqual([3, 13]);
  });
  it("cumulative of the sample ends at the sum of its nets", () => {
    const t = F.days.reduce((a, d) => a + (d.fii.net ?? 0), 0);
    expect(cumulative(F.days, "fii").at(-1)![1]).toBeCloseTo(t, 1);
  });
  it("moving average needs a full window", () => {
    expect(movingAverage([1, 2, 3, 4], 2)).toEqual([null, 1.5, 2.5, 3.5]);
    expect(movingAverage([1, null, 3, 4, 5], 2)).toEqual([null, null, null, 3.5, 4.5]);
    expect(movingAverage([1, 2], 5)).toEqual([null, null]);
  });
  it("percentile of a selling day counts days with less selling", () => {
    const d = [-100, -50, 20, 30, -10, 40].map((v, i) => mk(`2026-01-0${i + 1}`, v));
    expect(percentileOf(d, "fii", -100)).toEqual({ pct: 83.3, n: 6 });
    expect(percentileOf(d, "fii", 40)).toEqual({ pct: 83.3, n: 6 });
    expect(percentileOf(d, "fii", 0)).toBeNull();
    expect(percentileOf(d, "dii", -1)).toBeNull();
  });
  it("runs and top runs", () => {
    const d = [5, 3, -1, -2, -3, -4, 0, 2, 1, 9].map((v, i) => mk(`2026-02-${String(i + 1).padStart(2, "0")}`, v));
    const r = runs(d, "fii");
    expect(r.map((x) => [x.side, x.days])).toEqual([["buying", 2], ["selling", 4], ["buying", 3]]);
    expect(r[0].touchesStart).toBe(true); expect(r[2].current).toBe(true); expect(r[1].sum).toBe(-10);
    expect(topRuns(d, "fii", "selling")[0]).toMatchObject({ days: 4, from: "2026-02-03", to: "2026-02-06" });
  });
  it("the streak in the fixture payload matches the runs", () => {
    const r = runs(F.days, "fii").at(-1)!; expect(r.days).toBe(F.streaks.fii!.days); expect(r.side).toBe(F.streaks.fii!.side);
    const rd = runs(F.days, "dii").at(-1)!; expect(rd.days).toBe(F.streaks.dii!.days);
  });
  it("absorption", () => {
    const d = [mk("1", -100, 60), mk("2", 50, -10), mk("3", -50, -20), mk("4", -50, 70)];
    expect(absorption(d, 10)).toEqual({ sessions: 4, sellDays: 3, fiiSold: 200, diiNetOnThoseDays: 110, ratio: 0.55, diiBoughtDays: 2 });
    expect(absorption([mk("1", -1), mk("2", -3)], 5)).toBeNull();
    expect(absorption(F.days, 90)!.sessions).toBe(90);
    expect(absorption(noDii.days, 90)).toBeNull();
  });
  it("calendar puts weekdays in Monday-first columns and ignores weekends", () => {
    const d = [mk("2026-10-19", 5), mk("2026-10-20", -5), mk("2026-10-23", 1), mk("2026-10-24", 9)];
    const c = calendar(d, "fii", 4);
    expect(c.cells.map((x) => [x.d, x.col, x.row])).toEqual([["2026-10-19", 3, 0], ["2026-10-20", 3, 1], ["2026-10-23", 3, 4]]);
    const big = calendar(F.days, "fii");
    expect(Math.max(...big.cells.map((x) => x.col))).toBeLessThanOrEqual(52); expect(big.months.length).toBeGreaterThan(8);
  });
  it("level scales by sign and size", () => {
    expect(level(null, 10)).toBe(0); expect(level(0, 10)).toBe(0); expect(level(2, 10)).toBe(1); expect(level(-10, 10)).toBe(-4); expect(level(100, 10)).toBe(4); expect(level(6, 10)).toBe(3);
  });
  it("ranges are calendar months back from the last session", () => {
    expect(sinceMonths(F.days, 1)[0].d > "2026-09-22").toBe(true);
    expect(rangeRows(F.days, "MAX")).toBe(F.days);
    const y = rangeRows(F.days, "1Y"); expect(y.length).toBeGreaterThan(230); expect(y.length).toBeLessThan(262);
  });
  it("totals since", () => {
    const d = [mk("2025-09-01", 100), mk("2026-01-01", 10), mk("2026-10-01", 5)];
    expect(totalSince(d, "fii", 12)).toBe(15); expect(totalSince(d, "dii", 12)).toBeNull();
  });
  it("month grid from payload and from days", () => {
    const g = monthGrid(F, "fii"); expect(g.years[0]).toBe("2026"); expect(g.cell("2026", 9)).not.toBeNull(); expect(g.cell("2026", 11)).toBeNull();
    const only = monthGrid({ monthly: [], yearly: [], days: [mk("2026-01-02", 3), mk("2026-01-05", 4), mk("2026-02-02", -1)] }, "fii");
    expect(only.cell("2026", 0)).toBe(7); expect(only.total("2026")).toBe(6);
    const nd = monthGrid(noDii, "dii"); expect(nd.cell("2026", 9)).toBeNull(); expect(nd.total("2026")).toBeNull();
  });
  it("split bar wording", () => {
    const s = splitOf({ ...F.latest!, fii: { buy: 1, sell: 2, net: -540 }, dii: { buy: 1, sell: 1, net: 460 } })!;
    expect(s.left).toMatchObject({ label: "FII selling", pct: 54 }); expect(s.right).toMatchObject({ label: "DII support", pct: 46 });
    expect(splitOf(noDii.latest)).toBeNull();
    expect(splitOf({ ...F.latest!, fii: { buy: 1, sell: 2, net: 300 }, dii: { buy: 1, sell: 1, net: -100 } })!.right.label).toBe("DII selling");
  });
  it("labels and words", () => {
    expect(ageLabel("2026-10-22", "2026-10-23")).toBe("yesterday"); expect(ageLabel("2026-10-23", "2026-10-23")).toBe("today"); expect(ageLabel("2026-10-18", "2026-10-23")).toBe("5 days ago");
    expect(corrWords(0.05)).toBe("almost no relationship"); expect(corrWords(-0.35)).toBe("a moderate negative relationship"); expect(corrWords(null)).toBe("not enough data");
  });
  it("formats rupees crore with Indian grouping and a true minus", () => {
    expect(grp(509032)).toBe("5,09,032"); expect(inr(-509032)).toBe("−₹5,09,032 Cr"); expect(inr(1200.5, { sign: true, d: 1 })).toBe("+₹1,200.5 Cr"); expect(inr(null)).toBe("—");
  });
  it("diiState covers full, partial and none", () => {
    expect(diiState(F)).toBe("full"); expect(diiState(noDii)).toBe("none");
    expect(diiState({ ...F, days: [mk("a", 1, 1), mk("b", 1)] })).toBe("partial");
  });
  it("index correlation uses same-day index moves", () => {
    const idx = [100, 101, 99, 103, 104, 102, 105, 108, 107, 110, 109, 111].map((c, i) => ({ d: `2026-03-${String(i + 1).padStart(2, "0")}`, close: c }));
    const d = idx.map((p, i) => mk(p.d, i === 0 ? 0 : (p.close - idx[i - 1].close) * 10));
    expect(indexCorrelation(d, idx, "fii")!).toBeGreaterThan(0.9);
    expect(indexCorrelation(d, null, "fii")).toBeNull();
    expect(indexCorrelation(d, idx, "dii")).toBeNull();
  });
  it("table filter and sort", () => {
    expect(filterDays(F.days, "2026-10").every((d) => d.d.startsWith("2026-10"))).toBe(true);
    expect(filterDays(F.days, "oct 2025").every((d) => d.d.startsWith("2025-10"))).toBe(true);
    expect(filterDays(F.days, "zzz")).toEqual([]);
    const s = sortDays(F.days, "fii", true); expect(s[0].fii.net!).toBeLessThanOrEqual(s[1].fii.net!);
    const n = sortDays([mk("1", 1, null as never), mk("2", 2, 5), mk("3", 3, 1)], "dii", false); expect(n.map((x) => x.d)).toEqual(["2", "3", "1"]);
  });
  it("csv has every session, blanks for missing, and a header", () => {
    const c = toCsv(F.days).trim().split("\n"); expect(c.length).toBe(F.days.length + 1); expect(c[0]).toMatch(/^Date,FII buy/);
    expect(toCsv([mk("2026-01-01", 5)])).toBe(toCsv([mk("2026-01-01", 5)])); expect(toCsv([mk("2026-01-01", 5)]).split("\n")[1]).toBe("2026-01-01,,,5,,,,");
    expect(combined(mk("a", 1, 2))).toBe(3); expect(combined(mk("a", 1))).toBeNull();
  });
  it("summary is descriptive, covers both shapes, and never advises", () => {
    const a = summarize(F).join(" "), b = summarize(noDii).join(" ");
    expect(a).toMatch(/offset|opposite/); expect(a).toMatch(/bigger than \d+% of the/); expect(a).toMatch(/Over the last 30 sessions/);
    expect(b).not.toMatch(/DIIs were net/); expect(b).toMatch(/DII figures are not available/);
    for (const t of [a, b]) expect(t).not.toMatch(/\b(should|will rise|will fall|buy now|recommend|expect)\b/i);
  });
});
