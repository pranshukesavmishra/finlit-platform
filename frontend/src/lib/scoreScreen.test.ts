import { describe, expect, it } from "vitest";
import { PRESETS, applyFilters, activePreset, chipsFor, concentration, emptyFilters, facetCounts, inBands, inRange, median, pageList, pageOf, parseState, removeChip, serializeState, sortRows,
  summarize, toCsv, validate, withPreset, withScores, nextSort, DEFAULT_SORT, type Item } from "./scoreScreen";
import type { Row } from "./screener";

const row = (symbol: string, o: Partial<Row> = {}): Row => ({
  symbol, name: symbol + " Ltd", sector: "Banks", overall: 60, band: "healthy", pillar_quality: 60, pillar_growth: 60, pillar_profitability: 60, pillar_balance: 60, pillar_technical: 60,
  price: 100, market_cap: 1000, pe: null, pb: null, roe: null, roce: null, dividend_yield: null, debt_to_equity: null, sales_cagr: null, profit_cagr: null,
  operating_margin: null, change_pct: null, return_1m: null, return_1y: null, ...o,
});
/** An item whose Fundamental is exactly `f` (all four pillars equal) and Technical `t`. */
const it1 = (symbol: string, f: number | null, t: number | null, o: Partial<Row> = {}): Item =>
  withScores([row(symbol, { pillar_quality: f, pillar_growth: f, pillar_profitability: f, pillar_balance: f, pillar_technical: t, ...o })])[0];
const syms = (r: Item[]) => r.map((x) => x.symbol);

describe("scores per company", () => {
  it("Fundamental is the rounded average of the four pillars and needs three of them", () => {
    const [a, b, c] = withScores([
      row("A", { pillar_quality: 80, pillar_growth: 70, pillar_profitability: 60, pillar_balance: 50 }),
      row("B", { pillar_quality: 80, pillar_growth: 70, pillar_profitability: 61, pillar_balance: null }),
      row("C", { pillar_quality: 80, pillar_growth: 70, pillar_profitability: null, pillar_balance: null }),
    ]);
    expect(a.f).toBe(65);
    expect(b.f).toBe(70);        // (80+70+61)/3 = 70.33
    expect(c.f).toBeNull();      // two pillars are not enough: a dash, not zero
  });
  it("Technical is the technical pillar untouched and Overall is the stored overall", () => {
    const [a] = withScores([row("A", { pillar_technical: 37, overall: 51 })]);
    expect([a.t, a.overall]).toEqual([37, 51]);
  });
  it("size buckets: 100 Large, next 150 Mid, rest Small; no price or market cap means no bucket", () => {
    const rows = Array.from({ length: 260 }, (_, i) => row("S" + i, { market_cap: 100000 - i }));
    rows.push(row("NOCAP", { market_cap: null }), row("NOPRICE", { price: null, market_cap: 5e6 }));
    const by = Object.fromEntries(withScores(rows).map((r) => [r.symbol, r.cap]));
    expect([by.S0, by.S99, by.S100, by.S249, by.S250, by.S259]).toEqual(["Large", "Large", "Mid", "Mid", "Small", "Small"]);
    expect([by.NOCAP, by.NOPRICE]).toEqual([null, null]);
  });
});

describe("bands and ranges", () => {
  it("band edges: 44 is Under 45, 45 is Mixed/Healthy, 77 is 45 to 77, 78 is Strong", () => {
    expect([44, 45].map((v) => inBands(v, ["low"]))).toEqual([true, false]);
    expect([44, 45].map((v) => inBands(v, ["mid"]))).toEqual([false, true]);
    expect([77, 78].map((v) => inBands(v, ["mid"]))).toEqual([true, false]);
    expect([77, 78].map((v) => inBands(v, ["high"]))).toEqual([false, true]);
    expect([0, 100].map((v) => inBands(v, ["low", "high"]))).toEqual([true, true]);
  });
  it("a missing score never passes a band or a range, and no filter keeps everything", () => {
    expect(inBands(null, ["low", "mid", "high"])).toBe(false);
    expect(inRange(null, { min: 0, max: 100 })).toBe(false);
    expect(inRange(null, { min: null, max: 40 })).toBe(false);
    expect(inBands(null, [])).toBe(true);
    expect(inRange(null, { min: null, max: null })).toBe(true);
  });
  it("min-max is inclusive, either end may be open", () => {
    const r = { min: 45, max: 77 };
    expect([44, 45, 77, 78].map((v) => inRange(v, r))).toEqual([false, true, true, false]);
    expect([10, 90].map((v) => inRange(v, { min: 50, max: null }))).toEqual([false, true]);
    expect([10, 90].map((v) => inRange(v, { min: null, max: 50 }))).toEqual([true, false]);
  });
});

describe("applying filters", () => {
  const items = [
    it1("A", 90, 90, { sector: "Banks", market_cap: 900 }), it1("B", 90, 30, { sector: "IT", market_cap: 800 }), it1("C", 50, 90, { sector: "IT", market_cap: 700 }),
    it1("D", null, 80, { sector: "Auto", market_cap: 600 }), it1("E", 44, 45, { sector: null, market_cap: 500 }), it1("F", 78, null, { sector: "Banks", market_cap: 400 }),
  ];
  it("empty filters keep every company, including ones with no scores", () => { expect(applyFilters(items, emptyFilters())).toHaveLength(6); });
  it("multi-select sectors is OR within the group", () => {
    const f = emptyFilters(); f.sectors = ["IT", "Auto"];
    expect(syms(applyFilters(items, f))).toEqual(["B", "C", "D"]);
  });
  it("a company with no sector never matches a sector filter", () => {
    const f = emptyFilters(); f.sectors = ["Banks"];
    expect(syms(applyFilters(items, f))).not.toContain("E");
  });
  it("Fundamental 78 band keeps 78 and drops a missing Fundamental", () => {
    const f = emptyFilters(); f.bands.f = ["high"];
    expect(syms(applyFilters(items, f))).toEqual(["A", "B", "F"]);
  });
  it("band and min-max on the same score are both required (AND)", () => {
    const f = emptyFilters(); f.bands.f = ["high"]; f.ranges.f = { min: 85, max: null };
    expect(syms(applyFilters(items, f))).toEqual(["A", "B"]);
  });
  it("Overall min-max uses the stored overall", () => {
    const x = [it1("P", 60, 60, { overall: 70 }), it1("Q", 60, 60, { overall: 40 }), it1("R", 60, 60, { overall: null })];
    const f = emptyFilters(); f.ranges.o = { min: 50, max: 100 };
    expect(syms(applyFilters(x, f))).toEqual(["P"]);
  });
  it("pillar bands filter on that pillar only", () => {
    const x = withScores([row("G", { pillar_quality: 90, pillar_growth: 20, pillar_profitability: 50, pillar_balance: 50 }), row("H", { pillar_quality: 20, pillar_growth: 90, pillar_profitability: 50, pillar_balance: 50 })]);
    const f = emptyFilters(); f.bands.q = ["high"];
    expect(syms(applyFilters(x, f))).toEqual(["G"]);
  });
  it("size filter is multi-select", () => {
    const x = withScores([row("L", { market_cap: 5 }), row("M", { market_cap: 4 })]);
    const f = emptyFilters(); f.caps = ["Large", "Mid"];
    expect(applyFilters(x, f)).toHaveLength(2);
  });
  it("counts beside options follow the other filters but not their own group", () => {
    const f = emptyFilters(); f.sectors = ["IT"]; f.bands.f = ["high"];
    const c = facetCounts(items, f);
    expect(Object.fromEntries(c.sectors)).toEqual({ Banks: 2, IT: 1, Auto: 0 });   // sector counts ignore the sector choice itself
    expect(c.caps.Large).toBe(1);                                                    // B only: IT, Fundamental 78+
  });
});

describe("presets", () => {
  const items = [it1("A", 90, 90), it1("B", 90, 30), it1("C", 50, 90), it1("D", 70, 90), it1("E", 90, 44), it1("F", 90, null)];
  const run = (id: string) => syms(applyFilters(items, withPreset(emptyFilters(), PRESETS.find((p) => p.id === id)!)));
  it("Strong on both", () => expect(run("both")).toEqual(["A"]));
  it("Strong fundamentals, weak trend (Technical under 45)", () => expect(run("fund")).toEqual(["B", "E"]));   // E is Technical 44, still under 45; F has no Technical and is left out
  it("Strong trend, weaker fundamentals (Fundamental under 78)", () => expect(run("trend")).toEqual(["C", "D"]));
  it("keeps other filters and clears the Fundamental and Technical boxes; is recognised as active", () => {
    const f = emptyFilters(); f.sectors = ["IT"]; f.ranges.f = { min: 10, max: 20 };
    const n = withPreset(f, PRESETS[0]);
    expect(n.sectors).toEqual(["IT"]); expect(n.ranges.f).toEqual({ min: null, max: null });
    expect(activePreset(n)).toBe("both"); expect(activePreset(emptyFilters())).toBeNull();
  });
  it("uses no advice wording", () => {
    const text = PRESETS.map((p) => p.label + " " + p.say).join(" ").toLowerCase();
    expect(text).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate|target)\b/);
  });
});

describe("validation", () => {
  it("flags out of range and min above max", () => {
    const f = emptyFilters(); f.ranges.f = { min: -1, max: 50 }; f.ranges.t = { min: 70, max: 60 }; f.ranges.o = { min: 0, max: 100 };
    expect(Object.keys(validate(f))).toEqual(["f", "t"]);
  });
});

describe("chips", () => {
  it("one chip per active filter, each removable", () => {
    const f = emptyFilters(); f.caps = ["Mid", "Large"]; f.sectors = ["IT", "Auto"]; f.bands.f = ["high", "mid"]; f.ranges.o = { min: 50, max: null };
    const ch = chipsFor(f);
    expect(ch.map((c) => c.label)).toEqual(["Market cap: Large, Mid", "IT", "Auto", "Fundamental: 45–77, 78+", "Overall: 50 or more"]);
    expect(chipsFor(removeChip(f, "sector:IT")).map((c) => c.id)).toEqual(["caps", "sector:Auto", "band:f", "range:o"]);
    expect(chipsFor(removeChip(removeChip(removeChip(f, "caps"), "band:f"), "range:o")).map((c) => c.id)).toEqual(["sector:IT", "sector:Auto"]);
    expect(chipsFor(emptyFilters())).toEqual([]);
  });
});

describe("sorting and paging", () => {
  const items = [it1("A", 50, 10), it1("B", null, 20), it1("C", 70, null), it1("D", 50, 30), it1("E", 90, 40)];
  it("sorts numbers both ways with missing values always last", () => {
    expect(syms(sortRows(items, { key: "f", dir: -1 }))).toEqual(["E", "C", "A", "D", "B"]);
    expect(syms(sortRows(items, { key: "f", dir: 1 }))).toEqual(["A", "D", "C", "E", "B"]);
    expect(syms(sortRows(items, { key: "t", dir: 1 }))).toEqual(["A", "B", "D", "E", "C"]);
  });
  it("is stable: ties keep their order in both directions", () => {
    expect(syms(sortRows(items, { key: "f", dir: -1 })).filter((s) => s === "A" || s === "D")).toEqual(["A", "D"]);
    expect(syms(sortRows(items, { key: "f", dir: 1 })).filter((s) => s === "A" || s === "D")).toEqual(["A", "D"]);
  });
  it("sorts text A to Z, missing sector last, and does not change the input", () => {
    const x = [it1("Z", 1, 1, { sector: "IT" }), it1("Y", 1, 1, { sector: null }), it1("X", 1, 1, { sector: "Auto" })];
    expect(syms(sortRows(x, { key: "sector", dir: 1 }))).toEqual(["X", "Z", "Y"]);
    expect(syms(sortRows(x, { key: "sector", dir: -1 }))).toEqual(["Z", "X", "Y"]);
    expect(syms(x)).toEqual(["Z", "Y", "X"]);
  });
  it("heading clicks: new column starts high to low (text A to Z), same column flips", () => {
    expect(nextSort(DEFAULT_SORT, "f")).toEqual({ key: "f", dir: -1 });
    expect(nextSort({ key: "f", dir: -1 }, "f")).toEqual({ key: "f", dir: 1 });
    expect(nextSort(DEFAULT_SORT, "name")).toEqual({ key: "name", dir: 1 });
  });
  it("paging clamps the page and reports the range", () => {
    const rows = Array.from({ length: 23 }, (_, i) => i);
    expect(pageOf(rows, 2, 10)).toMatchObject({ page: 2, pages: 3, from: 21, to: 23, view: [20, 21, 22] });
    expect(pageOf(rows, 9, 10).page).toBe(2);
    expect(pageOf(rows, -3, 10).page).toBe(0);
    expect(pageOf([], 0, 10)).toMatchObject({ pages: 1, from: 0, to: 0, view: [] });
  });
  it("page numbers leave gaps", () => {
    expect(pageList(0, 3)).toEqual([0, 1, 2]);
    expect(pageList(5, 12)).toEqual([0, null, 3, 4, 5, 6, 7, null, 11]);
  });
});

describe("summary", () => {
  it("median ignores missing values and averages the middle pair", () => {
    expect(median([10, null, 30, 20])).toBe(20);
    expect(median([10, 20, 30, 40])).toBe(25);
    expect(median([null, null])).toBeNull();
    expect(median([])).toBeNull();
  });
  it("summarises the whole filtered set", () => {
    const s = summarize([it1("A", 80, 60, { sector: "IT" }), it1("B", null, 40, { sector: "IT" }), it1("C", 60, null, { sector: null })]);
    expect(s).toMatchObject({ found: 3, sectors: 1, medF: 70, medT: 50, nF: 2, nT: 2 });
  });
  it("sector concentration sums to the whole result", () => {
    const rows = [..."aaaabbbccd"].map((s, i) => it1("S" + i, 1, 1, { sector: s })).concat(it1("N", 1, 1, { sector: null }));
    const c = concentration(rows, 2);
    expect(c.map((x) => [x.label, x.n])).toEqual([["a", 4], ["b", 3], ["Other sectors", 3], ["Sector not listed", 1]]);
    expect(c.reduce((a, x) => a + x.pct, 0)).toBeCloseTo(100);
    expect(concentration([])).toEqual([]);
  });
});

describe("URL state", () => {
  it("round-trips every control", () => {
    const f = emptyFilters(); f.caps = ["Large", "Mid"]; f.sectors = ["IT", "Banks, Private"]; f.bands.f = ["mid", "high"]; f.bands.b = ["low"]; f.ranges.t = { min: 40, max: 90.5 }; f.ranges.o = { min: null, max: 80 };
    const s = { filters: f, sort: { key: "f" as const, dir: 1 as const }, size: 20, page: 2 };
    const qs = serializeState(s).toString();
    expect(parseState(new URLSearchParams(qs))).toEqual(s);
  });
  it("defaults leave the address empty", () => {
    expect(serializeState(parseState(new URLSearchParams())).toString()).toBe("");
  });
  it("still reads links from the earlier page", () => {
    const s = parseState(new URLSearchParams("cap=Mid&sector=IT&f=high&t=low,mid&q=high"));
    expect(s.filters).toMatchObject({ caps: ["Mid"], sectors: ["IT"], bands: { f: ["high"], t: ["low", "mid"], q: ["high"] } });
  });
  it("ignores junk and clamps", () => {
    const s = parseState(new URLSearchParams("cap=Huge&f=bogus&fmin=abc&tmin=-5&tmax=500&omin=80&omax=20&sort=evil&size=7&page=-4"));
    expect(s.filters.caps).toEqual([]); expect(s.filters.bands.f).toEqual([]);
    expect(s.filters.ranges.f).toEqual({ min: null, max: null });
    expect(s.filters.ranges.t).toEqual({ min: 0, max: 100 });
    expect(s.filters.ranges.o).toEqual({ min: 20, max: 80 });
    expect(s.sort).toEqual(DEFAULT_SORT); expect(s.size).toBe(10); expect(s.page).toBe(0);
  });
});

describe("CSV", () => {
  const f = emptyFilters(); f.sectors = ["IT"]; f.bands.t = ["high"];
  const rows = [it1("AAA", 80, 90, { name: 'A "Quoted", Ltd', sector: "IT", price: 12.5, market_cap: 5000, overall: 77 }), it1("BBB", null, null, { name: "=SUM(1)", sector: null, price: null, market_cap: null, overall: null })];
  const csv = toCsv(rows, { filters: f, sort: { key: "f", dir: -1 }, scope: "filtered", total: 2, asOf: "2026-10-26", exportedOn: "2026-10-27" });
  const lines = csv.split("\r\n");
  it("lists the filters, data date and meaning of a blank in the header", () => {
    expect(lines.filter((l) => l.startsWith("#")).join("\n")).toMatch(/Scores computed on: 2026-10-26/);
    expect(csv).toMatch(/# Filters: IT\r\n#          Technical: 78\+/);
    expect(csv).toMatch(/Blank cell = not available/);
    expect(csv).toMatch(/Sorted by: f descending/);
  });
  it("quotes text, neutralises formulas and leaves missing values blank (never 0)", () => {
    const head = lines.findIndex((l) => l.startsWith("Symbol,"));
    expect(lines[head + 1]).toBe('AAA,"A ""Quoted"", Ltd",IT,Large cap,12.5,5000,80,80,80,80,80,90,77');
    expect(lines[head + 2]).toBe("BBB,'=SUM(1),,,,,,,,,,,");
  });
  it("says when it exports only the selected rows", () => {
    expect(toCsv([rows[0]], { filters: emptyFilters(), sort: DEFAULT_SORT, scope: "selected", total: 9, asOf: null, exportedOn: "x" })).toMatch(/Rows: 1 \(selected rows only; 9 companies match the filters\)\r\n# Filters: None/);
  });
});
