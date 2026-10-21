import { describe, expect, it } from "vitest";
import { arcPath, assetRows, classifyChanges, groupHoldings, sectorRows, sliceFractions, sliceList, sortHoldings, sumPct, topNPct } from "./logic";
import type { Holding } from "./types";

const h = (name: string, pct: number | null, extra: Partial<Holding> = {}): Holding => ({ name, isin: null, sector: null, assetClass: "equity", pct, qty: null, valueLakh: null, stockSymbol: null, prevPct: null, change: null, ...extra });

describe("groupHoldings", () => {
  const rows = [h("A", 9.5), h("B", 1), h("C", 0.99), h("D", 0.5), h("E", null), h("F", 4)];
  it("splits at the threshold (1% is major, 0.99% is small), largest first", () => {
    const g = groupHoldings(rows);
    expect(g.major.map((x) => x.name)).toEqual(["A", "F", "B"]);
    expect(g.small.map((x) => x.name)).toEqual(["C", "D", "E"]);
    expect(g.otherCount).toBe(3);
  });
  it("sums without float noise and keeps every holding", () => {
    const g = groupHoldings(rows);
    expect(g.otherPct).toBe(1.49);
    expect(g.totalPct).toBe(15.99);
    expect(g.major.length + g.small.length).toBe(rows.length);
  });
  it("slices: majors then one other slice with the small total", () => {
    const s = sliceList(groupHoldings(rows));
    expect(s.map((x) => x.pct)).toEqual([9.5, 4, 1, 1.49]);
    expect(s[3].other).toBe(true);
    expect(sliceList(groupHoldings([h("A", 50)])).some((x) => x.other)).toBe(false);
  });
});

describe("sums", () => {
  it("sumPct ignores missing", () => expect(sumPct([0.1, 0.2, null, undefined])).toBe(0.3));
  it("topNPct", () => { expect(topNPct([h("a", 1), h("b", 5), h("c", 3)], 2)).toBe(8); expect(topNPct([])).toBeNull(); });
  it("fractions fill the circle", () => { const f = sliceFractions([50, 25, 25]); expect(f[0]).toEqual([0, 0.5]); expect(f[2][1]).toBe(1); expect(sliceFractions([30, 30])[1][1]).toBe(1); });
  it("arcPath is a closed path, and a single full slice does not collapse", () => {
    expect(arcPath(50, 50, 40, 20, 0, 0.25)).toMatch(/^M.*Z$/);
    expect(arcPath(50, 50, 40, 20, 0, 1)).toContain("A40,40 0 1 1");
  });
});

describe("classifyChanges", () => {
  const p = {
    previousAsOf: "2026-08-31",
    holdings: [h("New Co", 2, { prevPct: null }), h("Up Co", 5.5, { prevPct: 5 }), h("Down Co", 3, { prevPct: 3.25 }), h("Same Co", 4, { prevPct: 4.001 })],
    exited: [{ name: "Gone Co", prevPct: 1.5 }],
  };
  it("labels new, increased, decreased, unchanged and exited with exact pp", () => {
    const r = classifyChanges(p)!;
    const by = Object.fromEntries(r.map((x) => [x.name, x]));
    expect(by["New Co"]).toMatchObject({ kind: "new", change: 2 });
    expect(by["Up Co"]).toMatchObject({ kind: "increased", change: 0.5 });
    expect(by["Down Co"]).toMatchObject({ kind: "decreased", change: -0.25 });
    expect(by["Same Co"].kind).toBe("unchanged");
    expect(by["Gone Co"]).toMatchObject({ kind: "exited", pct: 0, change: -1.5 });
    expect(r.map((x) => x.kind)).toEqual(["new", "exited", "increased", "decreased", "unchanged"]);
  });
  it("is null without a previous month", () => expect(classifyChanges({ ...p, previousAsOf: null })).toBeNull());
});

describe("sorting and splits", () => {
  it("sorts with missing values last in both directions", () => {
    const rows = [h("a", 2), h("b", null), h("c", 5)];
    expect(sortHoldings(rows, "pct", "desc").map((x) => x.name)).toEqual(["c", "a", "b"]);
    expect(sortHoldings(rows, "pct", "asc").map((x) => x.name)).toEqual(["a", "c", "b"]);
    expect(sortHoldings(rows, "name", "desc").map((x) => x.name)).toEqual(["c", "b", "a"]);
  });
  it("assetRows keeps a missing class missing", () => expect(assetRows({ equity: 97.1, debt: null, cash: 2.9, other: null }).map((r) => r.pct)).toEqual([97.1, null, 2.9, null]));
  it("sectorRows prefers the published summary, else sums holdings", () => {
    const hs = [h("a", 2, { sector: "Banks" }), h("b", 3, { sector: "Banks" }), h("c", 1, { sector: "IT" })];
    expect(sectorRows({ holdings: hs, summary: { count: 3, top10Pct: null, assetSplit: { equity: null, debt: null, cash: null, other: null }, sectors: [] } })).toEqual([{ sector: "Banks", pct: 5 }, { sector: "IT", pct: 1 }]);
    expect(sectorRows({ holdings: hs, summary: { count: 3, top10Pct: null, assetSplit: { equity: null, debt: null, cash: null, other: null }, sectors: [{ sector: "X", pct: 1 }, { sector: "Y", pct: 9 }] } })[0].sector).toBe("Y");
  });
});
