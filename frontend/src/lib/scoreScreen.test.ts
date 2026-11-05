import { describe, expect, it } from "vitest";
import { TOP_N, applyTop, rankTop, topPool, withScores as scoresOf } from "./scoreScreen";
import { PRISM_PRESETS, SORT_KEYS, activePrismPreset, hasPrismParams, techBandOf, trendWord, withPrismPreset, withoutPrismPreset } from "./scoreScreen";
import { applyFilters, chipsFor, concentration, emptyFilters, facetCounts, inBands, inRange, median, pageList, pageOf, parseState, removeChip, serializeState, sortRows,
  summarize, validate, withScores, nextSort, DEFAULT_SORT, type Item } from "./scoreScreen";
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
    expect(ch.map((c) => c.label)).toEqual(["Market cap: Large, Mid", "IT", "Auto", "Growth & Profitability: 45–77, 78+", "Total FinLit IQ: 50 or more"]);
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



// ---------- FinLit Prism
const pr = (symbol: string, final: number | null, label: string | null, o: Partial<Row> = {}) =>
  it1(symbol, 60, 60, { prism_state: label ? "stored" : "none", prism_final: final, prism_label: label, prism_status: final == null ? (label ? "NOT RATED" : null) : "RATED", prism_fundamental: final, prism_valuation: final, prism_quality: final, prism_risk: final, prism_st_score: final == null ? null : final - 50, prism_lt_score: final == null ? null : 50 - final, ...o });
const PZ = [pr("S", 85, "STRONG"), pr("H", 66, "HEALTHY"), pr("A", 55, "AVERAGE"), pr("W", 40, "WEAK"), pr("P", 20, "POOR"), pr("N", null, "NOT RATED"), pr("X", null, null)];

describe("Prism filters", () => {
  it("rated-only keeps companies with a Prism score and drops both 'not rated' kinds", () => {
    const f = emptyFilters(); f.rated = true;
    expect(syms(applyFilters(PZ, f))).toEqual(["S", "H", "A", "W", "P"]);
  });
  it("label chips are OR within the group and never match a company without a stored rating", () => {
    const f = emptyFilters(); f.labels = ["STRONG", "NOT RATED"];
    expect(syms(applyFilters(PZ, f))).toEqual(["S", "N"]);
  });
  it("the Prism range is inclusive and a missing score never passes it or counts as zero", () => {
    const f = emptyFilters(); f.ranges.z = { min: 55, max: 85 };
    expect(syms(applyFilters(PZ, f))).toEqual(["S", "H", "A"]);
    f.ranges.z = { min: null, max: 30 };
    expect(syms(applyFilters(PZ, f))).toEqual(["P"]);       // N and X have no score: not 'under 30'
  });
  it("each part has its own range", () => {
    const x = [pr("A", 70, "HEALTHY", { prism_quality: 90, prism_valuation: 10 }), pr("B", 70, "HEALTHY", { prism_quality: 90, prism_valuation: 60 })];
    const f = emptyFilters(); f.ranges.zq = { min: 80, max: null }; f.ranges.zv = { min: 50, max: null };
    expect(syms(applyFilters(x, f))).toEqual(["B"]);
  });
  it("rows from a plan or a server without Prism fields simply have no rating", () => {
    const bare = it1("Z", 60, 60);
    const f = emptyFilters(); f.rated = true;
    expect(applyFilters([bare], f)).toEqual([]);
    expect(applyFilters([bare], emptyFilters())).toHaveLength(1);
  });
  it("validation covers the Prism ranges", () => {
    const f = emptyFilters(); f.ranges.z = { min: 90, max: 10 }; f.ranges.zq = { min: -5, max: null };
    expect(Object.keys(validate(f))).toEqual(["z", "zq"]);
  });
});

describe("Prism sorting", () => {
  it("every score column sorts both ways with missing last", () => {
    for (const key of ["prism_final", "prism_fundamental", "prism_valuation", "prism_quality", "prism_risk", "prism_st_score", "prism_lt_score"] as const) {
      expect(SORT_KEYS).toContain(key);
      const down = sortRows(PZ, { key, dir: -1 }), up = sortRows(PZ, { key, dir: 1 });
      expect(syms(down).slice(-2)).toEqual(["N", "X"]); expect(syms(up).slice(-2)).toEqual(["N", "X"]);
    }
    expect(syms(sortRows(PZ, { key: "prism_final", dir: -1 })).slice(0, 5)).toEqual(["S", "H", "A", "W", "P"]);
    expect(syms(sortRows(PZ, { key: "prism_lt_score", dir: -1 })).slice(0, 2)).toEqual(["P", "W"]);
    expect(nextSort(DEFAULT_SORT, "prism_final")).toEqual({ key: "prism_final", dir: -1 });
  });
});

describe("Prism presets (advanced screener: Prism parts only)", () => {
  const items = [
    pr("A", 85, "STRONG", { prism_fundamental: 80, prism_valuation: 55, prism_risk: 70, prism_st_score: 30, prism_lt_score: 25 }),
    pr("B", 85, "STRONG", { prism_fundamental: 80, prism_valuation: 40, prism_risk: 50, prism_st_score: 30, prism_lt_score: 10 }),
    pr("C", 60, "AVERAGE", { prism_fundamental: 66, prism_valuation: 60, prism_risk: 90, prism_st_score: 5, prism_lt_score: 45 }),
    pr("D", null, null, {})];
  const run = (id: string) => syms(applyFilters(items, withPrismPreset(emptyFilters(), PRISM_PRESETS.find((p) => p.id === id)!)));
  it("has the four views, none of them using the FinLit IQ", () => {
    expect(PRISM_PRESETS.map((p) => p.label)).toEqual(["Prism strong and lower risk", "Strong Growth & Profitability at a fair valuation", "Uptrend on both technical views", "Growth & Profitability strong but valuation weak"]);
    PRISM_PRESETS.forEach((p) => expect(Object.keys(p.ranges).every((k) => ["z", "zf", "zv", "zq", "zr"].includes(k))).toBe(true));
  });
  it("Prism strong and lower risk: Prism 80+ and Risk 65+", () => expect(run("strongsafe")).toEqual(["A"]));
  it("Strong Growth & Profitability at a fair valuation: Growth & Profitability 65+ and Valuation 50+", () => expect(run("fairvalue")).toEqual(["A", "C"]));
  it("Uptrend on both technical views: both scores at +20 or more", () => expect(run("bothtech")).toEqual(["A"]));   // B long term +10 is Neutral; C short term +5 is Neutral
  it("Growth & Profitability strong but valuation weak: Growth & Profitability 65+ and Valuation below 50", () => expect(run("weakvalue")).toEqual(["B"]));
  it("a preset owns the Prism filters (sets exactly its own), keeps the others, and is recognised and removable", () => {
    const f = emptyFilters(); f.sectors = ["IT"]; f.ranges.z = { min: 10, max: 20 }; f.labels = ["POOR"]; f.tech.st = ["neg"]; f.ranges.o = { min: 50, max: null };
    const n = withPrismPreset(f, PRISM_PRESETS[1]);
    expect(n.sectors).toEqual(["IT"]); expect(n.ranges.z).toEqual({ min: null, max: null }); expect(n.labels).toEqual([]); expect(n.tech).toEqual({ st: [], lt: [] });
    expect(n.ranges.o).toEqual({ min: 50, max: null });
    expect(activePrismPreset(n)).toBe("fairvalue"); expect(activePrismPreset(emptyFilters())).toBeNull();
    const t = withPrismPreset(emptyFilters(), PRISM_PRESETS[2]);
    expect(t.tech).toEqual({ st: ["pos"], lt: ["pos"] }); expect(activePrismPreset(t)).toBe("bothtech");
    const off = withoutPrismPreset(n);
    expect(activePrismPreset(off)).toBeNull(); expect(chipsFor(off).map((c) => c.id)).toEqual(["sector:IT", "range:o"]);
  });
  it("uses no advice wording", () => {
    const text = PRISM_PRESETS.map((p) => p.label + " " + p.say).join(" ").toLowerCase();
    expect(text).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate|target)\b/);
  });
});

describe("technical view bands", () => {
  it("use the Prism card's edges: +20 and above Positive (strong uptrend included), above -20 Neutral, -20 and below Negative", () => {
    expect([100, 50, 20, 19.9, 0, -19.9, -20, -50, -100].map(techBandOf)).toEqual(["pos", "pos", "pos", "neutral", "neutral", "neutral", "neg", "neg", "neg"]);
    expect(techBandOf(null)).toBeNull(); expect(techBandOf(undefined)).toBeNull();
  });
  it("filter by band on either view; a missing score never passes; bands are OR within a view and AND across the two", () => {
    const x = [pr("A", 80, "STRONG", { prism_st_score: 30, prism_lt_score: -30 }), pr("B", 80, "STRONG", { prism_st_score: 0, prism_lt_score: 0 }), pr("C", 80, "STRONG", { prism_st_score: null, prism_lt_score: null }), pr("D", null, null)];
    const f = emptyFilters(); f.tech.st = ["pos", "neutral"];
    expect(syms(applyFilters(x, f))).toEqual(["A", "B"]);
    f.tech.lt = ["neg"]; expect(syms(applyFilters(x, f))).toEqual(["A"]);
  });
  it("words come from the score (the site's descriptive words), whatever the model said", () => {
    expect(trendWord(22.5)).toBe("Uptrend"); expect(trendWord(-60)).toBe("Strong downtrend"); expect(trendWord(null)).toBeNull();
  });
  it("chips, address and removal", () => {
    const f = emptyFilters(); f.tech.st = ["neg", "pos"]; f.tech.lt = ["neutral"];
    expect(chipsFor(f).map((c) => c.label)).toEqual(["Short-term technical: Uptrend, Downtrend", "Long-term technical: Sideways"]);
    const qs = serializeState({ filters: f, sort: DEFAULT_SORT, size: 10, page: 0 }).toString();
    expect(qs).toBe("st=pos%2Cneg&lt=neutral");
    expect(parseState(new URLSearchParams(qs)).filters.tech).toEqual({ st: ["pos", "neg"], lt: ["neutral"] });
    expect(parseState(new URLSearchParams("st=bogus&lt=")).filters.tech).toEqual({ st: [], lt: [] });
    expect(removeChip(f, "tech:st").tech).toEqual({ st: [], lt: ["neutral"] });
  });
});

describe("one address, two pages", () => {
  const qs = "cap=Large&f=high&t=mid&omin=70&zmin=60&zrmin=50&pl=strong&rated=1&st=pos&lt=neg&sort=prism_final";
  it("the basic page reads only the FinLit IQ and ignores Prism parts and a Prism sort", () => {
    const b = parseState(new URLSearchParams(qs), "basic");
    expect(b.filters.bands.f).toEqual(["high"]); expect(b.filters.ranges.o.min).toBe(70); expect(b.filters.caps).toEqual(["Large"]);
    expect(b.filters.ranges.z).toEqual({ min: null, max: null }); expect(b.filters.labels).toEqual([]); expect(b.filters.rated).toBe(false); expect(b.filters.tech).toEqual({ st: [], lt: [] });
    expect(b.sort).toEqual(DEFAULT_SORT);
  });
  it("the advanced page reads only the Prism filters and ignores FinLit bands, ranges and sorts", () => {
    const a = parseState(new URLSearchParams(qs), "advanced");
    expect(a.filters.bands.f).toEqual([]); expect(a.filters.ranges.o).toEqual({ min: null, max: null }); expect(a.filters.caps).toEqual(["Large"]);
    expect(a.filters.ranges.z.min).toBe(60); expect(a.filters.labels).toEqual(["STRONG"]); expect(a.filters.rated).toBe(true); expect(a.filters.tech).toEqual({ st: ["pos"], lt: ["neg"] });
    expect(a.sort.key).toBe("prism_final");
    expect(parseState(new URLSearchParams("sort=overall"), "advanced").sort).toEqual(DEFAULT_SORT);
  });
  it("tells an old shared link that carries Prism filters (or a Prism sort) from a FinLit-only one", () => {
    for (const q of ["zmin=60", "zfmax=80", "pl=strong", "rated=1", "st=pos", "lt=neg", "sort=prism_risk", "f=high&zvmin=5"]) expect(hasPrismParams(new URLSearchParams(q)), q).toBe(true);
    for (const q of ["", "f=high&t=mid&omin=70", "cap=Large&sector=IT&sort=overall&dir=desc&size=20&page=2"]) expect(hasPrismParams(new URLSearchParams(q)), q).toBe(false);
  });
});

describe("Prism chips, address and summary", () => {
  it("one removable chip each for the labels, the rated switch and each Prism range", () => {
    const f = emptyFilters(); f.labels = ["HEALTHY", "STRONG"]; f.rated = true; f.ranges.z = { min: 60, max: null }; f.ranges.zr = { min: null, max: 40 };
    expect(chipsFor(f).map((c) => c.label)).toEqual(["Total Fundamental Score: 60 or more", "Prism Risk: 40 or less", "Prism rating: Strong, Healthy", "Only companies rated by Prism"]);
    expect(chipsFor(removeChip(removeChip(f, "labels"), "rated")).map((c) => c.id)).toEqual(["range:z", "range:zr"]);
  });
  it("round-trips through the address and ignores junk", () => {
    const f = emptyFilters(); f.labels = ["STRONG", "NOT RATED"]; f.rated = true; f.ranges.z = { min: 40, max: 90 }; f.ranges.zv = { min: 55, max: null };
    const s = { filters: f, sort: { key: "prism_quality" as const, dir: 1 as const }, size: 20, page: 1 };
    const qs = serializeState(s).toString();
    expect(qs).toContain("pl=strong%2Cnotrated"); expect(qs).toContain("rated=1");
    expect(parseState(new URLSearchParams(qs))).toEqual(s);
    const bad = parseState(new URLSearchParams("pl=bogus,Strong&rated=yes&zmin=abc&zmax=500&sort=prism_evil"));
    expect(bad.filters.labels).toEqual([]); expect(bad.filters.rated).toBe(false); expect(bad.filters.ranges.z).toEqual({ min: null, max: 100 }); expect(bad.sort).toEqual(DEFAULT_SORT);
  });
  it("summary counts and medians the Prism scores that exist", () => {
    expect(summarize(PZ)).toMatchObject({ nZ: 5, medZ: 55 });
    expect(summarize([])).toMatchObject({ nZ: 0, medZ: null });
  });
});


describe("colour rule", () => {
  it("scores are coloured by the site's one rule (70 / 50), while the model's word labels keep their own bands", async () => {
    const { level, bandName } = await import("./scoreScreen");
    expect([level(70), level(69), level(50), level(49), level(null)]).toEqual(["hi", "mid", "mid", "lo", "na"]);
    expect([bandName(78), bandName(62), bandName(45), bandName(44)]).toEqual(["Strong", "Healthy", "Mixed", "Watch"]);
  });
});


describe("Top 10 large / mid / small caps by FinLit IQ", () => {
  // 320 companies: market caps 3200 down to 10 (so ranks 1-100 are Large, 101-250 Mid, 251+ Small), each with an IQ; a few are given none.
  const row = (i: number, o: Partial<Row> = {}): Row => ({
    symbol: "S" + String(i).padStart(3, "0"), name: "S" + i, sector: "X", overall: 50 + (i % 41), band: null, pillar_quality: 40 + (i % 7), pillar_growth: 50, pillar_profitability: 50, pillar_balance: 50, pillar_technical: 50,
    price: 100, market_cap: (321 - i) * 10, pe: null, pb: null, roe: null, roce: null, dividend_yield: null, debt_to_equity: null, sales_cagr: null, profit_cagr: null,
    operating_margin: null, change_pct: null, return_1m: null, return_1y: null, scored: true, ...o,
  } as Row);
  const rows: Row[] = Array.from({ length: 320 }, (_, i) => row(i + 1)).map((r, i) => (i % 53 === 0 ? { ...r, overall: null, scored: false } : r));
  const items = scoresOf(rows);
  type Cap3 = "Large" | "Mid" | "Small";
  const topOf = (cap: Cap3) => ({ ...emptyFilters(), caps: [cap], top: TOP_N });   // what an old shared link (?top=10&cap=...) sets
  const TOP_PRESETS = (["Large", "Mid", "Small"] as Cap3[]).map((cap) => ({ cap }));

  it("each shows exactly ten companies of its own size class, highest FinLit IQ first, none without an IQ", () => {
    for (const p of TOP_PRESETS) {
      const f = topOf(p.cap);
      const out = applyTop(items, f, { key: "overall", dir: -1 });
      expect(out).toHaveLength(TOP_N);
      expect(out.every((r) => r.cap === p.cap && r.overall != null)).toBe(true);
      expect(out.map((r) => r.overall)).toEqual([...out.map((r) => r.overall as number)].sort((a, b) => b - a));
      // the ten really are the ten highest of that class (recomputed by hand)
      const pool = items.filter((r) => r.cap === p.cap && r.overall != null).map((r) => r.overall as number).sort((a, b) => b - a);
      expect(out.map((r) => r.overall)).toEqual(pool.slice(0, TOP_N));
    }
  });
  it("ties go to the higher Quality score, then the larger market cap, then the symbol, and the result never depends on the input order", () => {
    const a = items.filter((r) => r.cap === "Large" && r.overall != null);
    const forward = rankTop(a, 10).map((r) => r.symbol), backward = rankTop([...a].reverse(), 10).map((r) => r.symbol);
    expect(backward).toEqual(forward);
    const tied = scoresOf([row(1, { overall: 80, pillar_quality: 60 }), row(2, { overall: 80, pillar_quality: 70 }), row(3, { overall: 80, pillar_quality: 70, market_cap: 1 }), row(4, { overall: 79 })]);
    expect(rankTop(tied, 3).map((r) => r.symbol)).toEqual(["S002", "S003", "S001"]);       // 70 q (larger cap first), then 60 q
  });
  it("the pool says how many were ranked, and fewer than ten qualifying shows fewer, never padding", () => {
    const f = topOf("Large");
    expect(topPool(items, f)).toBe(items.filter((r) => r.cap === "Large" && r.overall != null).length);
    expect(topPool(items, emptyFilters())).toBeNull();
    const few = scoresOf(rows.slice(0, 6));
    expect(applyTop(few, topOf("Large"), { key: "overall", dir: -1 })).toHaveLength(5);   // six companies, one without an IQ: five are shown, not ten
    expect(topPool(few, topOf("Large"))).toBe(5);
  });
  it("the user can still re-sort the ten, other filters narrow the pool first, and choosing another view or removing the chip switches it off", () => {
    const f = topOf("Large");
    const byName = applyTop(items, f, { key: "name", dir: 1 });
    expect(byName).toHaveLength(10);
    expect(byName.map((r) => r.name)).toEqual([...byName.map((r) => r.name)].sort());
    const g = { ...f, sectors: ["Nothing"] };
    expect(applyTop(items, g, { key: "overall", dir: -1 })).toHaveLength(0);
    expect(chipsFor(f).map((c) => c.label)).toEqual(["Market cap: Large", "Top 10 by FinLit IQ"]);
    expect(removeChip(f, "top").top).toBeNull();
  });
  it("the address keeps the screen (top=10 with the size class) and a shared link opens it", () => {
    const f = topOf("Mid");
    const qs = serializeState({ filters: f, sort: { key: "overall", dir: -1 }, size: 10, page: 0 });
    expect(qs.get("top")).toBe("10"); expect(qs.get("cap")).toBe("Mid");
    const back = parseState(new URLSearchParams(qs.toString()), "basic");
    expect(back.filters.top).toBe(10);
    expect(parseState(new URLSearchParams("top=7"), "basic").filters.top).toBeNull();          // only the ten the screen defines
    expect(parseState(new URLSearchParams("top=10"), "advanced").filters.top).toBeNull();      // the advanced screener does not use it
  });
});

describe("the two valuation views split at 50 (issue 30.b)", () => {
  const vals: [string, number | null][] = [["GLAXO", 49.75], ["ICICILIFE", 49.7], ["OFSS", 49.69], ["EDGE", 49.99], ["AT50", 50], ["JUST", 50.01], ["ZERO", 0], ["TOP", 100], ["BLANK", null]];
  const items = vals.map(([s, v]) => pr(s, 80, "STRONG", { prism_fundamental: 70, prism_valuation: v as number, prism_risk: 60, prism_st_score: 0, prism_lt_score: 0 }));
  const run = (id: string) => syms(applyFilters(items, withPrismPreset(emptyFilters(), PRISM_PRESETS.find((p) => p.id === id)!)));
  it("Valuation below 50 is weak (GLAXO 49.75, ICICILIFE 49.70, OFSS 49.69), 50 and above is fair, and 50.0 is on the fair side", () => {
    expect(run("weakvalue")).toEqual(["GLAXO", "ICICILIFE", "OFSS", "EDGE", "ZERO"]);
    expect(run("fairvalue")).toEqual(["AT50", "JUST", "TOP"]);
  });
  it("no stock with a Valuation score falls into neither view, or into both", () => {
    const weak = run("weakvalue"), fair = run("fairvalue");
    items.filter((r) => r.prism_valuation != null).forEach((r) => expect([weak.includes(r.symbol), fair.includes(r.symbol)].filter(Boolean)).toHaveLength(1));
  });
  it("the weak view is recognised again from its address and says 'below 50'", () => {
    const f = withPrismPreset(emptyFilters(), PRISM_PRESETS.find((p) => p.id === "weakvalue")!);
    expect(activePrismPreset(f)).toBe("weakvalue");
    const qs = serializeState({ filters: f, sort: DEFAULT_SORT, size: 10, page: 0 }).toString();
    expect(qs).toContain("zvlt=50"); expect(qs).not.toContain("zvmax");
    const back = parseState(new URLSearchParams(qs), "advanced").filters;
    expect(activePrismPreset(back)).toBe("weakvalue"); expect(back.ranges.zv).toEqual({ min: null, max: 50, maxExcl: true });
    expect(chipsFor(f).map((c) => c.label).find((l) => /below 50/.test(l))).toMatch(/Valuation.*: below 50/);
    expect(inRange(49.99, back.ranges.zv)).toBe(true); expect(inRange(50, back.ranges.zv)).toBe(false);
  });
  it("an exact maximum typed in the boxes stays inclusive", () => expect(inRange(50, { min: null, max: 50 })).toBe(true));
  it("the score bands leave no gap for a fractional score", () => {
    for (const v of [44, 44.5, 44.99, 45, 77, 77.4, 77.99, 78, 100]) expect(["low", "mid", "high"].filter((b) => inBands(v, [b as "low" | "mid" | "high"]))).toHaveLength(1);
  });
});

import { IQ_LABELS, filtersKey, bandsToRange, iqLabelOf, rangeToBands, toggleRangeBand } from "./scoreScreen";
describe("Basic FinLit IQ rating chips, Technical and Total rows", () => {
  const rows = withScores([
    { symbol: "A", overall: 90, pillar_technical: 80 }, { symbol: "B", overall: 78, pillar_technical: 77 }, { symbol: "C", overall: 77.9, pillar_technical: 45 }, { symbol: "D", overall: 62, pillar_technical: 44.9 },
    { symbol: "E", overall: 61, pillar_technical: 20 }, { symbol: "F", overall: 45, pillar_technical: null }, { symbol: "G", overall: 44, pillar_technical: 10 }, { symbol: "H", overall: 35, pillar_technical: 10 },
    { symbol: "I", overall: 34, pillar_technical: 10 }, { symbol: "J", overall: null, pillar_technical: 50 },
  ] as never[]);
  const syms = (f: ReturnType<typeof emptyFilters>) => applyFilters(rows, f).map((r) => r.symbol).join("");
  it("rating labels have half-open edges, no gaps, and Not rated is a missing score", () => {
    expect(rows.map((r) => iqLabelOf(r.overall))).toEqual(["strong", "strong", "healthy", "healthy", "average", "average", "weak", "weak", "poor", "notrated"]);
    for (const [l, want] of [["strong", "AB"], ["healthy", "CD"], ["average", "EF"], ["weak", "GH"], ["poor", "I"], ["notrated", "J"]] as const) { const f = emptyFilters(); f.iqLabels = [l]; expect(syms(f)).toBe(want); }
    const all = emptyFilters(); all.iqLabels = [...IQ_LABELS]; expect(syms(all)).toBe("ABCDEFGHIJ");
    const two = emptyFilters(); two.iqLabels = ["strong", "notrated"]; expect(syms(two)).toBe("ABJ");
  });
  it("Technical band chips and the Total band use the same stored numbers; a missing score never passes", () => {
    const t = emptyFilters(); t.bands.t = ["low"]; expect(syms(t)).toBe("DEGHI");             // F has no Technical: out
    t.bands.t = ["mid"]; expect(syms(t)).toBe("BCJ"); t.bands.t = ["high"]; expect(syms(t)).toBe("A");
    const o = emptyFilters(); o.bands.o = ["high"]; expect(syms(o)).toBe("AB");
    const r = emptyFilters(); r.ranges.o = { min: 45, max: 77 }; expect(syms(r)).toBe("DEF");  // C is 77.9: above 77
    const tr = emptyFilters(); tr.ranges.t = { min: 50, max: null }; expect(syms(tr)).toBe("ABJ");
  });
  it("the filter reads the very numbers the table shows (overall and the Technical pillar)", () => {
    for (const r of rows) { expect(r.t).toBe((r as never as { pillar_technical: number | null }).pillar_technical); }
    const f = emptyFilters(); f.ranges.t = { min: 0, max: 100 }; f.ranges.o = { min: 0, max: 100 };
    expect(applyFilters(rows, f).every((r) => r.overall != null && r.t != null)).toBe(true);
  });
  it("URL round trip: ?iql=, ?ovr=, ?omin= and the Technical keys; Prism links are not touched", () => {
    const f = emptyFilters(); f.iqLabels = ["weak", "strong"]; f.bands.o = ["high", "low"]; f.bands.t = ["mid"]; f.ranges.o = { min: 40, max: 90 }; f.ranges.t = { min: 10, max: null };
    const p = serializeState({ filters: f, sort: DEFAULT_SORT, size: 10, page: 0 });
    expect(p.get("iql")).toBe("strong,weak"); expect(p.get("ovr")).toBe("low,high"); expect(p.get("t")).toBe("mid"); expect(p.get("omin")).toBe("40"); expect(p.get("tmin")).toBe("10");
    const back = parseState(new URLSearchParams(p.toString()), "basic").filters;
    expect(back.iqLabels).toEqual(["strong", "weak"]); expect(back.bands.o).toEqual(["low", "high"]); expect(back.ranges.o).toEqual({ min: 40, max: 90 }); expect(filtersKey(back)).toBe(filtersKey(f));
    expect(parseState(new URLSearchParams("iql=strong"), "advanced").filters.iqLabels).toEqual([]);
    expect(parseState(new URLSearchParams("iql=bogus,poor"), "basic").filters.iqLabels).toEqual(["poor"]);
  });
  it("chips are readable and removable", () => {
    const f = emptyFilters(); f.iqLabels = ["strong", "notrated"]; f.bands.t = ["high"]; f.bands.o = ["mid"];
    const c = chipsFor(f).map((x) => x.label);
    expect(c).toEqual(["Technical: 78+", "Total FinLit IQ: 45–77", "FinLit IQ rating: Strong, Not rated"]);
    expect(removeChip(f, "iqlabels").iqLabels).toEqual([]); expect(removeChip(f, "band:o").bands.o).toEqual([]);
  });
});

describe("band chips as a Min - Max range (Advanced rows)", () => {
  it("each chip maps to a half-open range with no gaps", () => {
    expect(bandsToRange(["low"])).toEqual({ min: null, max: 45, maxExcl: true });
    expect(bandsToRange(["mid"])).toEqual({ min: 45, max: 78, maxExcl: true });
    expect(bandsToRange(["high"])).toEqual({ min: 78, max: null });
    expect(bandsToRange(["low", "mid"])).toEqual({ min: null, max: 78, maxExcl: true });
    expect(bandsToRange(["mid", "high"])).toEqual({ min: 45, max: null });
    for (const v of [44.99, 45, 77.99, 78]) { const hit = (["low", "mid", "high"] as const).filter((b) => inRange(v, bandsToRange([b]))); expect(hit).toHaveLength(1); }
  });
  it("toggling joins neighbours, restarts otherwise, and a typed range lights no chip", () => {
    const none = { min: null, max: null };
    const a = toggleRangeBand(none, "low"), b = toggleRangeBand(a, "mid"), c = toggleRangeBand(b, "high");
    expect(rangeToBands(a)).toEqual(["low"]); expect(rangeToBands(b)).toEqual(["low", "mid"]); expect(c).toEqual({ min: null, max: null });
    expect(rangeToBands(toggleRangeBand(a, "high"))).toEqual(["high"]);       // not next to it: starts over
    expect(toggleRangeBand(b, "mid")).toEqual(bandsToRange(["low"]));
    expect(toggleRangeBand(a, "low")).toEqual(none);
    expect(rangeToBands({ min: 50, max: 70 })).toEqual([]);
  });
  it("URL round trip of a chip-set range (zvlt / zmin)", () => {
    const f = emptyFilters(); f.ranges.zv = bandsToRange(["low"]); f.ranges.zq = bandsToRange(["mid", "high"]);
    const p = serializeState({ filters: f, sort: DEFAULT_SORT, size: 10, page: 0 });
    expect(p.get("zvlt")).toBe("45"); expect(p.get("zqmin")).toBe("45");
    const back = parseState(p, "advanced").filters;
    expect(rangeToBands(back.ranges.zv)).toEqual(["low"]); expect(rangeToBands(back.ranges.zq)).toEqual(["mid", "high"]);
  });
});
