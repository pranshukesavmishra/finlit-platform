// Why a listed company may be missing from a picker, one test per cause: a filter hides it (and says so), it is found only by its BSE/NSE code or ISIN,
// it has no sector on file (so no sector chip lists it), it has no stored rating (it is still in the list).
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { SearchIndex } from "./api";
import { rankCompanies } from "./companySearch";
import { searchStocks } from "./globalSearch";
import { NO_FILTER, filterParts, filterStocks, hiddenMatches, hiddenRowMatches, indexFacets, isinMap, passes, relaxed, sectorAt } from "./searchFilters";
import { ActiveFilters, FilterNote } from "../components/SearchFilters";

const IDX: SearchIndex = {
  fields: ["symbol", "name", "bse", "ready", "nse"],
  rows: [["TCS", "Tata Consultancy Services Ltd", "532540", 1], ["HDFCBANK", "HDFC Bank Ltd", "500180", 1], ["TATAMOTORS", "Tata Motors Ltd", "500570", 0, "TMCV"], ["SMALLCO", "Small Co Ltd", null, 0], ["NOSEC", "Nameless Sector Ltd", "999999", 0]],
  sectors: ["Information Technology", "Financial Services", "Auto"], sec: [0, 1, 2, 0, -1], mc: [1400000, 1200000, 300000, 900, 0],
  isin: ["INE467B01029", "INE040A01034", "INE155A01022", "", ""],
};
const text = (h: string) => h.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("a filter that hides the company the reader typed", () => {
  const f = { sector: "Financial Services", cap: null };
  it("lists the matching company as hidden, with the reason, instead of silently dropping it", () => {
    expect(filterStocks(IDX, "tata", f, 8).rows).toHaveLength(0);
    const h = hiddenMatches(IDX, "tata", f);
    expect(h.map((x) => x.symbol).sort()).toEqual(["TATAMOTORS", "TCS"]);
    expect(h.find((x) => x.symbol === "TCS")!.why).toBe("Hidden by your filter: Sector Financial Services (this one is in Information Technology)");
    expect(h[0].keys).toEqual(["sector"]);
  });
  it("names the market-cap part and companies with no value on file", () => {
    const h = hiddenMatches(IDX, "nameless", { sector: null, cap: "mega" });
    expect(h[0].why).toContain("Market cap Mega-cap (this one has no market value on file)");
  });
  it("shows nothing hidden while no filter is on, and never lists a company that passes", () => {
    expect(hiddenMatches(IDX, "tata", NO_FILTER)).toEqual([]);
    expect(hiddenMatches(IDX, "hdfc", f)).toEqual([]);
  });
  it("Show it removes only the part that hides the company", () => {
    const both = { sector: "Financial Services", cap: "mega" as const };
    const h = hiddenMatches(IDX, "tcs", both)[0];
    expect(h.keys).toEqual(["sector"]);   // TCS is mega-cap: only the sector hides it
    expect(relaxed(both, h.keys)).toEqual({ sector: null, cap: "mega" });
  });
  it("works for screener rows (compare page, watchlist)", () => {
    const rows = [{ symbol: "TCS", name: "Tata Consultancy", sector: "Information Technology", market_cap: 1400000 }];
    const h = hiddenRowMatches(rows, (r) => ({ sector: r.sector, cap: r.market_cap }), "tcs", { sector: "Auto", cap: null });
    expect(h[0].why).toContain("Hidden by your filter: Sector Auto");
  });
});

describe("the funnel says exactly what is on", () => {
  it("names each active filter and offers Clear filters", () => {
    expect(filterParts({ sector: "Auto", cap: "large" })).toEqual(["Sector: Auto", "Market cap: Large-cap"]);
    const h = text(renderToStaticMarkup(<ActiveFilters filter={{ sector: "Auto", cap: "large" }} onChange={() => undefined} />));
    expect(h).toContain("2 filters on: Sector: Auto · Market cap: Large-cap");
    expect(h).toContain("Clear filters");
  });
  it("renders nothing when no filter is on (the default)", () => {
    expect(renderToStaticMarkup(<ActiveFilters filter={NO_FILTER} onChange={() => undefined} />)).toBe("");
  });
  it("the empty note offers relaxations and shows the greyed hidden row with Show it", () => {
    const f = { sector: "Financial Services", cap: "mega" as const };
    const h = text(renderToStaticMarkup(<FilterNote filter={f} q="tata" onChange={() => undefined} hidden={hiddenMatches(IDX, "tata", f)} />));
    expect(h).toContain("Hidden by your filter");
    expect(h).toContain("Show it");
    expect(h).toContain("Any sector");
    expect(h).toContain("Any size");
    expect(h).toContain("Clear filters");
  });
});

describe("every listed company is reachable by name, symbol, exchange code or ISIN", () => {
  const names = (q: string) => rankCompanies(IDX.rows, q, 8, [], isinMap(IDX)).map((h) => h.symbol);
  it("finds a company by its BSE code (the picker used to rank only symbol and name)", () => expect(names("532540")).toEqual(["TCS"]));
  it("finds a company by a different NSE code", () => expect(names("TMCV")).toEqual(["TATAMOTORS"]));
  it("finds a company by ISIN, whole or its first characters", () => {
    expect(names("INE040A01034")).toEqual(["HDFCBANK"]);
    expect(searchStocks(IDX.rows, "INE155A0", 5, new Set(), undefined, IDX.isin).map((h) => h.row[0])).toEqual(["TATAMOTORS"]);
  });
  it("finds a name in the middle of the words and a company that has no rating, no sector and no size", () => {
    expect(names("consultancy")).toEqual(["TCS"]);
    expect(names("nameless")).toEqual(["NOSEC"]);
  });
  it("an ISIN-shaped query does not match by accident", () => expect(names("INE999")).toEqual([]));
});

describe("sector browsing lists every company", () => {
  it("counts the companies with no sector on file so a chip can list them", () => {
    const f = indexFacets(IDX);
    expect(f.unknown.sector).toBe(1);
    expect(f.sectors.reduce((n, s) => n + s.n, 0) + f.unknown.sector).toBe(5);
    expect(sectorAt(IDX, 4)).toBeNull();
  });
  it("a company with no sector fails only the sector filter", () => {
    expect(passes(IDX, 4, { sector: "Auto", cap: null })).toBe(false);
    expect(passes(IDX, 4, NO_FILTER)).toBe(true);
  });
});
