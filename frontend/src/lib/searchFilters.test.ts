import { describe, expect, it } from "vitest";
import type { SearchIndex } from "./api";
import { NO_FILTER, bandOf, facetsOf, filterNoun, filterPhrase, filterStocks, filteredRows, hasFilterData, indexFacets, passes, passesValues } from "./searchFilters";

// 10 rows in index order; sector codes point into `sectors`; mc is rupees crore (0 = unknown), -1 = unknown sector.
const idx: SearchIndex = {
  fields: ["symbol", "name", "bse", "ready", "nse"],
  rows: [
    ["AAA", "Alpha Infotech Ltd", "1", 0], ["BBB", "Beta Bank Ltd", "2", 0], ["CCC", "Gamma Infosys Ltd", "3", 0], ["DDD", "Delta Soft Ltd", "4", 0], ["EEE", "Epsilon Bank Ltd", "5", 0],
    ["FFF", "Zeta Mystery Ltd", "6", 0], ["GGG", "Eta Infotech Ltd", "7", 0], ["HHH", "Theta Soft Ltd", "8", 0], ["^NSEI", "Nifty 50", null, 0], ["III", "Iota Infotech Ltd", "9", 0],
  ],
  sectors: ["Information Technology", "Financial Services"],
  sec: [0, 1, 0, 0, 1, -1, 0, 0, -1, 0],
  mc: [250000, 90000, 200000, 2000, 500, 300000, 0, 50001, 0, 12000],
};

describe("size bands", () => {
  it("uses the portfolio checker's bands, edges going to the band whose range ends there", () => {
    expect(bandOf(200001)?.id).toBe("mega"); expect(bandOf(200000)?.id).toBe("large"); expect(bandOf(50001)?.id).toBe("large"); expect(bandOf(50000)?.id).toBe("mid");
    expect(bandOf(10000)?.id).toBe("small"); expect(bandOf(2000)?.id).toBe("micro"); expect(bandOf(500)?.id).toBe("nano"); expect(bandOf(1)?.id).toBe("nano");
  });
  it("has no band for an unknown value (0, null, undefined), so it is never shown under a wrong one", () => {
    expect(bandOf(0)).toBeNull(); expect(bandOf(null)).toBeNull(); expect(bandOf(undefined)).toBeNull();
  });
});

describe("facets come from the data", () => {
  const f = indexFacets(idx);
  it("lists only sectors that occur, with counts, most companies first; index entries are not companies", () => {
    expect(f.sectors).toEqual([{ name: "Information Technology", n: 6 }, { name: "Financial Services", n: 2 }]);
    expect(f.total).toBe(9);
  });
  it("counts every band and the companies left out when a filter is on", () => {
    expect(Object.fromEntries(f.caps.map((c) => [c.id, c.n]))).toEqual({ mega: 2, large: 3, mid: 1, small: 0, micro: 1, nano: 1 });
    expect(f.unknown).toEqual({ sector: 1, cap: 1 });
  });
  it("is cached per index and works on plain rows (screener rows)", () => {
    expect(indexFacets(idx)).toBe(f);
    expect(facetsOf([{ sector: "Power", cap: 300 }, { sector: null, cap: null }]).sectors).toEqual([{ name: "Power", n: 1 }]);
  });
  it("reports whether the index carries filter data at all", () => {
    expect(hasFilterData(idx)).toBe(true); expect(hasFilterData({ fields: [], rows: [["A", "A", null, 0]] })).toBe(false); expect(hasFilterData(undefined)).toBe(false);
  });
});

describe("filtering", () => {
  it("passes a company only if every chosen filter matches; unknowns fail only the filter that needs them", () => {
    expect(passesValues(null, null, NO_FILTER)).toBe(true);
    expect(passesValues(null, 500000, { sector: null, cap: "mega" })).toBe(true);
    expect(passesValues(null, 500000, { sector: "Power", cap: null })).toBe(false);
    expect(passesValues("Power", 0, { sector: null, cap: "nano" })).toBe(false);
    expect(passes(idx, 0, { sector: "Information Technology", cap: "mega" })).toBe(true);
    expect(passes(idx, 2, { sector: "Information Technology", cap: "mega" })).toBe(false);   // 2,00,000 is Large-cap
  });
  it("sector only: that sector's companies, largest market value first", () => {
    const r = filterStocks(idx, "", { sector: "Information Technology", cap: null }, 40);
    expect(r.rows.map((x) => x[0])).toEqual(["AAA", "CCC", "HHH", "III", "DDD", "GGG"]); expect(r.total).toBe(6);   // GGG: sector known, value unknown, so last
  });
  it("band only", () => {
    expect(filterStocks(idx, "", { sector: null, cap: "mega" }, 40).rows.map((x) => x[0])).toEqual(["FFF", "AAA"]);
    expect(filterStocks(idx, "", { sector: null, cap: "nano" }, 40).rows.map((x) => x[0])).toEqual(["EEE"]);
  });
  it("sector and band together", () => {
    const r = filterStocks(idx, "", { sector: "Information Technology", cap: "large" }, 40);
    expect(r.rows.map((x) => x[0])).toEqual(["CCC", "HHH"]);
  });
  it("never lists a company with unknown sector or size under a chosen sector or band", () => {
    const all = (f: Parameters<typeof filterStocks>[2]) => filterStocks(idx, "", f, 40).rows.map((x) => x[0]);
    expect(all({ sector: "Information Technology", cap: null })).not.toContain("FFF");     // sector unknown
    expect(all({ sector: null, cap: "mega" })).not.toContain("GGG");                        // market value unknown
    expect(all({ sector: null, cap: null })).toContain("GGG");                              // but both appear with no filter
  });
  it("with a query: best match first, still inside the filter", () => {
    const r = filterStocks(idx, "infotech", { sector: "Information Technology", cap: null }, 40);
    expect(r.rows.map((x) => x[0])).toEqual(["AAA", "GGG", "III"]);   // GGG has no market value but its sector is known, so a sector filter keeps it
  });
  it("a query that matches nothing inside the filter gives an honest zero", () => {
    expect(filterStocks(idx, "bank", { sector: "Information Technology", cap: null }, 40)).toEqual({ rows: [], total: 0 });
  });
  it("limits the rows but reports the full total", () => {
    const r = filterStocks(idx, "", { sector: "Information Technology", cap: null }, 2);
    expect(r.rows).toHaveLength(2); expect(r.total).toBe(6);
  });
  it("returns the index rows untouched when no filter is on, and never lists index entries", () => {
    expect(filteredRows(idx, NO_FILTER)).toBe(idx.rows);
    expect(filteredRows(idx, { sector: null, cap: "nano" }).some((r) => r[0].startsWith("^"))).toBe(false);
  });
});

describe("wording", () => {
  it("names the filter", () => {
    expect(filterPhrase({ sector: "Information Technology", cap: "mega" })).toBe("Mega-cap Information Technology");
    expect(filterNoun({ sector: "Information Technology", cap: "mega" })).toBe("Mega-cap Information Technology companies");
    expect(filterNoun({ sector: null, cap: "small" }, 1)).toBe("Small-cap company");
    expect(filterNoun(NO_FILTER)).toBe("companies");
  });
});
