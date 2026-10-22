import { describe, expect, it } from "vitest";
import {
  COLUMNS, DEFAULT_COLS, EMPTY_QUERY, FACT_LABELS, RETURN_LABELS, factKeys, factValueText, retTiles, activeFilterCount, buildLines, categoryShort, cleanNum, compareUrl, listPath, navText, nearestIndex, niceTicks, noReturnsText, pageWindow,
  parseIds, parseQuery, pctText, queryToParams, readCols, searchOptions, tone, trayToggle,
} from "./mf";

describe("number text", () => {
  it("NAV keeps at least 2 and at most 4 decimals, Indian grouping", () => {
    expect(navText(66.74)).toBe("₹66.74");
    expect(navText(29.1407)).toBe("₹29.1407");
    expect(navText(10.0087785)).toBe("₹10.0088");
    expect(navText(1000)).toBe("₹1,000.00");
    expect(navText(2540201.9508)).toBe("₹25,40,201.9508");
    expect(navText(null)).toBe("—");
  });
  it("percent has a true minus, an explicit plus and a dash for no figure", () => {
    expect(pctText(-6.9566)).toBe("−6.96%");
    expect(pctText(7.9655)).toBe("+7.97%");
    expect(pctText(0)).toBe("0.00%");
    expect(pctText(4.1, 1, false)).toBe("4.1%");
    expect(pctText(null)).toBe("—");
    expect(pctText(undefined)).toBe("—");
  });
  it("tone colours only real moves", () => { expect(tone(1)).toBe("pos"); expect(tone(-0.1)).toBe("neg"); expect(tone(0)).toBe(""); expect(tone(null)).toBe(""); });
  it("every reason code has words, and no code means no text", () => {
    for (const c of ["stopped", "idcw", "unstated", "no_history", "short"] as const) expect(noReturnsText(c).length).toBeGreaterThan(20);
    expect(noReturnsText(null)).toBe("");
    expect(noReturnsText("idcw")).toMatch(/IDCW/);
  });
  it("category short form drops the group", () => {
    expect(categoryShort("Equity Scheme - Mid Cap Fund")).toBe("Mid Cap Fund");
    expect(categoryShort("ELSS")).toBe("ELSS");
  });
});

describe("list address", () => {
  it("an empty address is the default list", () => {
    expect(parseQuery(new URLSearchParams(""))).toEqual(EMPTY_QUERY);
    expect(queryToParams(EMPTY_QUERY).toString()).toBe("");
  });
  it("round-trips every field", () => {
    const q = { ...EMPTY_QUERY, q: "hdfc mid", category: "Equity Scheme - Mid Cap Fund", amc: "HDFC Mutual Fund", plan: "Direct", option: "Growth", stopped: true, sort: "r5y" as const,
      dir: "desc" as const, page: 3, size: 25, min1y: "5", max1y: "40.5", min5y: "10", max5y: "30", view: "ready" as const };
    expect(parseQuery(queryToParams(q))).toEqual(q);
  });
  it("junk in the address falls back to safe values", () => {
    const q = parseQuery(new URLSearchParams("plan=Gold&option=x&sort=drop&dir=sideways&page=-4&size=9999&min1y=abc&max1y=1e9&stopped=yes"));
    expect(q).toEqual(EMPTY_QUERY);
    expect(parseQuery(new URLSearchParams("page=2.5")).page).toBe(1);
    expect(parseQuery(new URLSearchParams("q=" + "x".repeat(200))).q).toHaveLength(80);
  });
  it("only chosen sorts keep a direction", () => {
    expect(queryToParams({ ...EMPTY_QUERY, dir: "desc" }).toString()).toBe("");
    expect(queryToParams({ ...EMPTY_QUERY, sort: "name", dir: "desc" }).toString()).toBe("sort=name&dir=desc");
  });
  it("API address always carries page and size, and sort with its direction", () => {
    expect(listPath(EMPTY_QUERY)).toBe("/api/mf?page=1&size=50");
    expect(listPath({ ...EMPTY_QUERY, q: "axis liquid", plan: "Direct", stopped: true, sort: "r1y", dir: "desc", min1y: "0" })).toBe("/api/mf?q=axis+liquid&plan=Direct&min1y=0&stopped=true&sort=r1y&dir=desc&page=1&size=50");
  });
  it("range boxes accept numbers only", () => {
    expect(cleanNum(" 12.5 ")).toBe("12.5"); expect(cleanNum("-3")).toBe("-3"); expect(cleanNum("1,000")).toBe("1000");
    for (const bad of ["", "abc", "1e9", "NaN", "Infinity", "--1"]) expect(cleanNum(bad)).toBe("");
  });
  it("counts active filters, not search or sort", () => {
    expect(activeFilterCount(EMPTY_QUERY)).toBe(0);
    expect(activeFilterCount({ ...EMPTY_QUERY, q: "x", sort: "r1y", amc: "A", min1y: "1", stopped: true })).toBe(3);
  });
  it("the list offers exactly three return columns: 1 day, 1 year, 5 year per year", () => {
    const ret = COLUMNS.filter((c) => ["change", "r1y", "r5y"].includes(c.id));
    expect(ret.map((c) => c.label)).toEqual(["1 day", "1 year", "5 year, per year (CAGR)"]);
    expect(COLUMNS.map((c) => c.id).sort()).toEqual(["amc", "category", "change", "nav", "navDate", "option", "plan", "r1y", "r5y"]);
    expect(COLUMNS.every((c) => c.sort !== null || ["plan", "option"].includes(c.id))).toBe(true);
  });
  it("the default columns are the ones the founder asked for", () => { expect(DEFAULT_COLS).toEqual(["amc", "category", "nav", "change", "r1y", "r5y"]); expect(readCols()).toEqual(DEFAULT_COLS); });
});

describe("page numbers", () => {
  it("shows ends and the neighbours with gaps marked", () => {
    expect(pageWindow(1, 1)).toEqual([1]);
    expect(pageWindow(1, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(pageWindow(6, 40)).toEqual([1, "…", 4, 5, 6, 7, 8, "…", 40]);
    expect(pageWindow(40, 40)).toEqual([1, "…", 38, 39, 40]);
  });
});

const funds = [
  { n: "HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth" }, { n: "Axis Large Cap Fund" }, { n: "ICICI Prudential Bluechip Fund" }, { n: "Nippon India Small Cap Fund" },
  { n: "Kotak Mahindra Mutual Fund" }, { n: "UTI Nifty 50 Index Fund" }, { n: "Aditya Birla Sun Life Mutual Fund" },
];
const top = (q: string) => searchOptions(funds, q, (f) => f.n)[0]?.n;
describe("menu search", () => {
  it("is tolerant of spaces, hyphens and case", () => {
    for (const q of ["hdfc mid cap", "HDFC MID-CAP", "hdfc midcap", "mid cap opportunities"]) expect(top(q)).toBe(funds[0].n);
  });
  it("is tolerant of typos", () => {
    expect(top("axis lage cap")).toBe("Axis Large Cap Fund");
    expect(top("icici prudentail")).toBe("ICICI Prudential Bluechip Fund");
    expect(top("nipon small")).toBe("Nippon India Small Cap Fund");
    expect(top("kotek")).toBe("Kotak Mahindra Mutual Fund");
  });
  it("finds a fund house by the start of its name", () => { expect(top("aditya")).toBe("Aditya Birla Sun Life Mutual Fund"); expect(top("ABSL")).toBeUndefined(); });
  it("returns everything for an empty query and nothing for nonsense", () => {
    expect(searchOptions(funds, "  ", (f) => f.n)).toHaveLength(funds.length);
    expect(searchOptions(funds, "zzzzqq", (f) => f.n)).toEqual([]);
  });
});

describe("compare tray", () => {
  it("adds up to four and removes on a second click", () => {
    let l: number[] = [];
    for (const c of [1, 2, 3, 4]) l = trayToggle(l, c).list;
    expect(l).toEqual([1, 2, 3, 4]);
    expect(trayToggle(l, 5)).toEqual({ list: [1, 2, 3, 4], full: true });
    expect(trayToggle(l, 2)).toEqual({ list: [1, 3, 4], full: false });
  });
  it("addresses carry distinct valid codes only, at most four", () => {
    expect(parseIds("120465, 120389,120465,abc,-4,1.5,0,99999999,5,6,7")).toEqual([120465, 120389, 5, 6]);
    expect(parseIds(null)).toEqual([]);
    expect(compareUrl([1, 2])).toBe("/funds/compare?ids=1,2");
  });
});

describe("chart geometry", () => {
  it("nice ticks are round and cover the range", () => {
    expect(niceTicks(0, 100, 5)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(niceTicks(66.1, 72.4, 4)).toEqual([68, 70, 72]);
    expect(niceTicks(5, 5)).toEqual([5]);
  });
  it("places points by date, not by position, so funds with different starts line up", () => {
    const g = buildLines([{ key: "a", label: "A", t: ["2026-01-01", "2026-01-11"], v: [100, 110] }, { key: "b", label: "B", t: ["2026-01-06", "2026-01-11"], v: [100, 105] }], 500, 200, { l: 0, r: 0, t: 0, b: 0 })!;
    expect(g.lines[0].xy[0][0]).toBe(0);
    expect(g.lines[0].xy[1][0]).toBe(500);
    expect(g.lines[1].xy[0][0]).toBe(250);   // 5 of the 10 days
    expect(g.lines[0].xy[1][1]).toBeLessThan(g.lines[0].xy[0][1]);   // higher value, smaller y
    expect(g.xTicks).toHaveLength(5);
    expect(g.lo).toBeLessThan(100); expect(g.hi).toBeGreaterThan(110);   // padded, nothing touches the frame
  });
  it("needs two points to draw", () => { expect(buildLines([{ key: "a", label: "A", t: ["2026-01-01"], v: [100] }], 100, 100)).toBeNull(); });
  it("finds the nearest point for the hover read-out", () => {
    const xs = [0, 10, 30, 31, 100];
    expect(nearestIndex(xs, -5)).toBe(0); expect(nearestIndex(xs, 4)).toBe(0); expect(nearestIndex(xs, 6)).toBe(1); expect(nearestIndex(xs, 30.4)).toBe(2);
    expect(nearestIndex(xs, 30.6)).toBe(3); expect(nearestIndex(xs, 500)).toBe(4);
  });
});

describe("the three return tiles", () => {
  const ret = (value: number | null, from: string | null, kind: "absolute" | "cagr", why: string | null = null) => ({ value, kind, from, why });
  const base = {
    change: { abs: -0.82, pct: -1.21, since: "2026-10-16" }, navDate: "2026-10-19", retDate: "2026-10-19", returnsNote: null, optionClass: "Growth" as const, active: true,
    returns: { "1m": ret(1, "2026-09-18", "absolute"), "6m": ret(2, "2026-04-17", "absolute"), "1y": ret(-6.96, "2025-10-17", "absolute"), "3y": ret(7.97, "2023-10-19", "cagr"), "5y": ret(4.33, "2021-10-19", "cagr") },
  };
  it("shows 1 day, 1 year, 5 year per year, with the dates behind each figure", () => {
    const t = retTiles(base);
    expect(t.map((x) => x.label)).toEqual([RETURN_LABELS.d1, RETURN_LABELS.y1, RETURN_LABELS.y5]);
    expect(t.map((x) => x.value)).toEqual([-1.21, -6.96, 4.33]);
    expect(t[0].note).toMatch(/16 Oct 2026/); expect(t[1].note).toMatch(/17 Oct 2025/);
    expect(t[2].how).toMatch(/CAGR/); expect(t[1].how).toMatch(/Not a yearly rate/);
  });
  it("says why a figure is missing instead of showing a number", () => {
    const t = retTiles({ ...base, change: null, returns: { ...base.returns, "5y": ret(null, null, "cagr", "Younger than 5 years: the first NAV on file is dated 3 Mar 2023.") } });
    expect(t[0].value).toBeNull(); expect(t[0].note).toMatch(/previous NAV/);
    expect(t[2].value).toBeNull(); expect(t[2].note).toMatch(/Younger than 5 years/);
  });
  it("a figure without a start date says it was worked out from AMFI history, as of a date", () => {
    expect(retTiles({ ...base, returns: { ...base.returns, "1y": ret(-6.96, null, "absolute") } })[1].note).toBe("Worked out from AMFI history, as of 19 Oct 2026");
  });
});

describe("fund facts text", () => {
  it("values, dates, lists and numbers", () => {
    expect(factValueText({ value: "Nifty 50 TRI", asOf: "2026-09-30", source: "x" })).toBe("Nifty 50 TRI");
    expect(factValueText({ value: ["A B", "C D"] })).toBe("A B, C D");
    expect(factValueText({ value: 12345.6, unit: "₹ crore" })).toBe("12,346 ₹ crore");
    expect(factValueText({ value: 6070.8205, unit: "crore" })).toBe("₹6,071 Cr");          // what finlit.disclosure sends
    expect(factValueText({ value: 2, unit: "percent" })).toBe("2.00%");
    expect(factValueText({ value: 5000, unit: "rupees" })).toBe("₹5,000");
    expect(factValueText({ value: "2013-01-01" })).toBe("1 Jan 2013");
    expect(factValueText({ unavailable: "why" })).toBe(""); expect(factValueText({ value: null })).toBe(""); expect(factValueText({ value: [] })).toBe("");
  });
  it("orders keys as the server says and every known key has a label", () => {
    const f = { code: 1, order: ["aum", "amc"], facts: { amc: { value: "X" }, aum: { unavailable: "u" }, extra: { unavailable: "u" } } };
    expect(factKeys(f)).toEqual(["aum", "amc", "extra"]);
    for (const k of ["aum", "terRegular", "terDirect", "exitLoad", "benchmark", "managers", "riskometer", "launchDate", "minInvestment", "category", "amc"]) expect(FACT_LABELS[k]).toBeTruthy();
  });
});
