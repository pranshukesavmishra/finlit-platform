import { describe, expect, it } from "vitest";
import type { Row } from "./screener";
import { CATEGORIES, gainers, indexFor, largest, losers, lastN, moveColour, sectorBoard, stocksFor, treemap, weightedMove } from "./markets";
import type { IndexRow } from "./indices";

const row = (symbol: string, sector: string, price: number | null, change_pct: number | null, market_cap: number | null): Row => ({ symbol, name: symbol, sector, price, change_pct, market_cap } as Row);
const rows = [row("HDFCBANK", "Private Banks", 1500, -1.8, 1200000), row("ICICIBANK", "Private Banks", 1100, 1.0, 800000), row("SBIN", "Public Sector Banks", 800, 0.7, 700000),
  row("KOTAKBANK", "Private Banks", 1800, -0.2, 380000), row("AXISBANK", "Private Banks", 1200, 0.5, 350000), row("TCS", "IT Services", 3500, 0.4, 1300000),
  row("DEAD", "Private Banks", null, -100, 500), row("NOPE", "Private Banks", 10, null, 900)];

describe("treemap", () => {
  it("fills the box exactly with areas proportional to value and no overlap", () => {
    const items = [6, 6, 4, 3, 2, 2, 1];
    const t = treemap(items, (v) => v, 400, 300);
    expect(t).toHaveLength(7);
    expect(t.reduce((s, x) => s + x.w * x.h, 0)).toBeCloseTo(400 * 300, 6);
    for (const x of t) { expect(x.w * x.h).toBeCloseTo((x.item / 24) * 120000, 4); expect(x.x).toBeGreaterThanOrEqual(-1e-9); expect(x.y).toBeGreaterThanOrEqual(-1e-9); expect(x.x + x.w).toBeLessThanOrEqual(400 + 1e-6); expect(x.y + x.h).toBeLessThanOrEqual(300 + 1e-6); }
    for (let i = 0; i < t.length; i++) for (let j = i + 1; j < t.length; j++) {
      const a = t[i], b = t[j], ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x), oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      expect(ox > 1e-6 && oy > 1e-6).toBe(false);
    }
    expect(Math.max(...t.map((x) => Math.max(x.w / x.h, x.h / x.w)))).toBeLessThan(4);          // squarified: no thin slivers
  });
  it("drops zero, negative and non-finite values and handles empty input", () => {
    expect(treemap([0, -1, NaN, 5], (v) => v, 10, 10)).toHaveLength(1);
    expect(treemap([], (v: number) => v, 10, 10)).toEqual([]);
    expect(treemap([1], (v) => v, 0, 10)).toEqual([]);
    expect(treemap([3], (v) => v, 10, 4)[0]).toMatchObject({ x: 0, y: 0, w: 10, h: 4 });
  });
});

describe("what the pills show", () => {
  it("uses the exchange list when it is loaded (only traded stocks), else FinLit's sector text, and says which", () => {
    const bank = CATEGORIES[0].pills[0];
    const a = stocksFor(bank, rows, { NIFTYBANK: ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "DEAD", "MISSING"] });
    expect(a.basis).toBe("exchange list"); expect(a.stocks.map((r) => r.symbol)).toEqual(["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"]);
    const b = stocksFor(bank, rows, undefined);
    expect(b.basis).toBe("FinLit sector"); expect(b.stocks.map((r) => r.symbol).sort()).toEqual(["AXISBANK", "HDFCBANK", "ICICIBANK", "KOTAKBANK", "SBIN"]);
    expect(stocksFor(bank, rows, { NIFTYBANK: ["HDFCBANK"] }).basis).toBe("FinLit sector");        // a list of fewer than five is not trusted
    const psu = CATEGORIES[0].pills[2];
    expect(stocksFor(psu, rows, undefined).stocks.map((r) => r.symbol)).toEqual(["SBIN"]);
  });
  it("finds the provider's index for a pill by name, whatever the spacing and case", () => {
    const items = [{ code: "NIFBAN", name: "Nifty Bank" }, { code: "X", name: "NIFTY PSU BANK" }, { code: "Y", name: "Nifty Financial Services 25/50" }, { code: "Z", name: "Nifty Fin Service" }] as IndexRow[];
    expect(indexFor(items, CATEGORIES[0].pills[0])?.code).toBe("NIFBAN");
    expect(indexFor(items, CATEGORIES[0].pills[2])?.code).toBe("X");
    expect(indexFor(items, CATEGORIES[0].pills[1])?.code).toBe("Z");          // the 25/50 variant is a different index
    expect(indexFor(items, CATEGORIES[1].pills[0])).toBeNull();
    expect(indexFor(undefined, CATEGORIES[0].pills[0])).toBeNull();
  });
  it("every pill and category has a unique id", () => {
    const ids = CATEGORIES.flatMap((c) => c.pills.map((p) => p.id));
    expect(new Set(ids).size).toBe(ids.length); expect(new Set(CATEGORIES.map((c) => c.id)).size).toBe(CATEGORIES.length);
  });
});

describe("moves", () => {
  it("weights an average move by market cap, like an index", () => {
    expect(weightedMove([{ change_pct: 1, market_cap: 300 }, { change_pct: -1, market_cap: 100 }] as Row[])).toBeCloseTo(0.5, 12);
    expect(weightedMove([])).toBeNull(); expect(weightedMove([{ change_pct: 2, market_cap: null }] as Row[])).toBeNull();
  });
  it("ranks sectors by size and leaves out suspended and tiny companies", () => {
    const b = sectorBoard(rows);
    expect(b.map((x) => x.sector)).toEqual(["Banks", "IT & software"]);
    expect(b[0].n).toBe(5); expect(b[0].move).toBeCloseTo((-1.8 * 1200000 + 1.0 * 800000 + 0.7 * 700000 + -0.2 * 380000 + 0.5 * 350000) / (1200000 + 800000 + 700000 + 380000 + 350000), 8);
  });
  it("picks gainers and losers, largest move first, and the largest companies", () => {
    expect(gainers(rows, 2).map((r) => r.symbol)).toEqual(["ICICIBANK", "SBIN"]); expect(losers(rows, 5).map((r) => r.symbol)).toEqual(["DEAD", "HDFCBANK", "KOTAKBANK"]);
    expect(largest(rows, 3).map((r) => r.symbol)).toEqual(["TCS", "HDFCBANK", "ICICIBANK"]);
    expect(lastN([1, 2, 3, 4], 2)).toEqual([3, 4]); expect(lastN([1, 2], 0)).toEqual([1, 2]);
  });
  it("colours by direction and size of move", () => {
    expect(moveColour(1)).toContain("--gain"); expect(moveColour(-1)).toContain("--loss"); expect(moveColour(0)).toBe("var(--s3)"); expect(moveColour(null)).toBe("var(--s3)");
    const pct = (c: number) => +/(\d+)%/.exec(moveColour(c))![1];
    expect(pct(3)).toBeGreaterThan(pct(0.5)); expect(pct(10)).toBe(pct(3));
  });
});

describe("broad sectors", () => {
  it("groups the exchange's fine industries into a short list", async () => {
    const { broadSector } = await import("./markets");
    expect(broadSector("Private Sector Bank")).toBe("Banks");
    expect(broadSector("Computers - Software & Consulting")).toBe("IT & software");
    expect(broadSector("Refineries & Marketing")).toBe("Oil, gas & energy");
    expect(broadSector("Pharmaceuticals")).toBe("Pharma & healthcare");
    expect(broadSector("Auto Components & Equipments")).toBe("Automobiles");
    expect(broadSector("Heavy Electrical Equipment")).toBe("Capital goods & industrials");
    expect(broadSector(null)).toBe("Other");
    expect(broadSector("Something unheard of")).toBe("Other");
  });
  it("leaves out moves no exchange allows (data artefacts)", async () => {
    const { sectorBoard } = await import("./markets");
    const r = (symbol: string, change_pct: number) => ({ symbol, name: symbol, sector: "Pharmaceuticals", price: 10, change_pct, market_cap: 500 }) as never;
    const b = sectorBoard([r("A", 1), r("B", 23800)]);
    expect(b).toHaveLength(1); expect(b[0].n).toBe(1); expect(b[0].move).toBe(1);
  });
});
