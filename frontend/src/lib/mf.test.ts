import { describe, expect, it } from "vitest";
import {
  DEFAULT_COLS, EMPTY_QUERY, activeFilterCount, buildLines, categoryShort, cleanNum, compareUrl, listPath, navText, nearestIndex, niceTicks, noReturnsText, pageWindow,
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
    const q = { ...EMPTY_QUERY, q: "hdfc mid", category: "Equity Scheme - Mid Cap Fund", amc: "HDFC Mutual Fund", plan: "Direct", option: "Growth", stopped: true, sort: "r3y" as const,
      dir: "desc" as const, page: 3, size: 25, min1y: "5", max1y: "40.5", min3y: "-2", max3y: "", min5y: "10", max5y: "30" };
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
  it("the default columns are the ones the founder asked for", () => { expect(DEFAULT_COLS).toEqual(["amc", "category", "nav", "r1y", "r3y", "r5y"]); expect(readCols()).toEqual(DEFAULT_COLS); });
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
