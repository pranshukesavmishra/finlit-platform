import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  COLUMNS, COL_BY, DEFAULT_COLS, DEFAULT_STATE, FILTERS, GLOSSARY_NAMES, CATEGORY_TERM, activeFilters, apiQuery, axisDate, dateTicks, fallReading, frameOf, linePath, move, nearest, nextSort, niceTicks,
  parseState, parseSymbols, pct, premiumReading, px, py, rangePosition, rangeReading, rebase, rupee, summaryOfSeries, toParams, traded, typicalDay, volReading, whyBlank,
  type EtfItem, type Point,
} from "./etf";
import { dateIN } from "./format";
import { TERMS, norm } from "./glossary";

const item = (over: Partial<EtfItem> = {}): EtfItem => ({
  symbol: "X", name: "X ETF", isin: "INF000", fundHouse: null, category: null, categoryLabel: null, assetClass: null, price: 100, previousClose: 99, changePct: 1, priceDate: "2026-10-21",
  volume: 1, avgTurnover: 5e7, ret1m: 1, ret6m: 2, ret1y: 3, ret3y: 4, ret5y: 5, cagr3y: 6, cagr5y: 7, vol1y: 8, mdd1y: -9, mdd3y: -10, mdd5y: -11, high52: 120, low52: 80, from52: -16.67,
  rangeFrom: "2025-10-21", firstDate: "2016-10-24", points: 2000, breakDate: null, nav: null, navDate: null, premium: null, premiumWide: false, why: {}, rank: 1, hot: true, ...over,
});

describe("formatting", () => {
  it("writes percentages with a true minus and no negative zero", () => {
    expect(pct(-3.0587)).toBe("−3.06%");
    expect(pct(0)).toBe("0.00%");
    expect(pct(null)).toBe("—");
    expect(pct(12.3456, 1)).toBe("12.3%");
  });
  it("moves carry an arrow and a sign, so colour is never the only cue", () => {
    expect(move(-0.62)).toBe("▼ −0.62%");
    expect(move(1)).toBe("▲ +1.00%");
    expect(move(0)).toBe("0.00%");
    expect(move(null)).toBe("—");
  });
  it("rupees and traded value in Indian units", () => {
    expect(rupee(259.57)).toBe("₹259.57");
    expect(rupee(1234567.5, 0)).toBe("₹12,34,568");
    expect(traded(5.6e9)).toBe("₹560 Cr");
    expect(traded(2.25e8)).toBe("₹22.5 Cr");
    expect(traded(8.2e5)).toBe("₹8.2 lakh");
    expect(traded(9000)).toBe("₹9,000");
    expect(traded(null)).toBe("—");
  });
});

describe("list state in the address", () => {
  it("the plain list has a plain address", () => {
    expect(toParams(DEFAULT_STATE).toString()).toBe("");
    expect(parseState(new URLSearchParams(""))).toEqual(DEFAULT_STATE);
  });
  it("round-trips everything that was chosen", () => {
    const s = { ...DEFAULT_STATE, q: "nifty bank", category: ["bank", "it"], asset: ["equity"], sort: "ret1y", order: "asc" as const, bounds: { ret1y: [5, null], ret5y: [null, 20] } as never, offset: 40 };
    const back = parseState(new URLSearchParams(toParams(s).toString()));
    expect(back).toEqual(s);
    expect(activeFilters(s)).toBe(5);
  });
  it("ignores what it does not know and unusable numbers", () => {
    const s = parseState(new URLSearchParams("sort=drop%20table&order=sideways&ret1yMin=abc&ret1yMax=NaN&ret5yMin=1e9&offset=-5&q=" + "x".repeat(200)));
    expect(s.sort).toBe("turnover"); expect(s.order).toBe("desc"); expect(s.bounds).toEqual({}); expect(s.offset).toBe(0); expect(s.q.length).toBe(60);
    expect(parseState(new URLSearchParams("offset=99999")).offset).toBe(5000);
    expect(parseState(new URLSearchParams("ret1yMin=0")).bounds.ret1y).toEqual([0, null]);   // zero is a value, not "empty"
  });
  it("the API query always names sort, order and a page size", () => {
    const q = new URLSearchParams(apiQuery({ ...DEFAULT_STATE, q: "gold" }));
    expect(q.get("sort")).toBe("turnover"); expect(q.get("order")).toBe("desc"); expect(q.get("limit")).toBe("40"); expect(q.get("q")).toBe("gold");
  });
  it("clicking a column starts at its natural order, clicking again flips it", () => {
    const a = nextSort(DEFAULT_STATE, "ret1y");
    expect([a.sort, a.order]).toEqual(["ret1y", "desc"]);
    expect(nextSort(a, "ret1y").order).toBe("asc");
    expect(nextSort(a, "name")).toMatchObject({ sort: "name", order: "asc", offset: 0 });
    expect(nextSort({ ...a, offset: 80 }, "ret5y").offset).toBe(0);
  });
  it("the compare tray keeps 2 to 4 clean, distinct symbols", () => {
    expect(parseSymbols("niftybees, GOLDBEES,niftybees,bad symbol,A,B,C")).toEqual(["NIFTYBEES", "GOLDBEES", "A", "B"]);
    expect(parseSymbols(null)).toEqual([]);
  });
});

describe("columns match the server", () => {
  const py = readFileSync(new URL("../../../backend/finlit/etf.py", import.meta.url), "utf8");
  const block = (name: string) => py.match(new RegExp(`${name} = \\{([^}]*)\\}`, "s"))![1];
  it("every sortable column is a sort key the API accepts", () => {
    const keys = [...block("LIST_FIELDS").matchAll(/"(\w+)":/g)].map((m) => m[1]);
    for (const c of COLUMNS) if (c.sort) expect(keys, c.key).toContain(c.sort);
    expect(keys).toContain("name");
  });
  it("every filter is one the API accepts", () => {
    const m = py.match(/FILTER_KEYS = \{k: v for k, v in LIST_FIELDS.items\(\) if k not in \(([^)]*)\)\}/)![1];
    const banned = [...m.matchAll(/"(\w+)"/g)].map((x) => x[1]);
    for (const f of FILTERS) expect(banned).not.toContain(f.key);
  });
  it("the default columns are the ones meant to show", () => {
    expect(DEFAULT_COLS).toEqual(["category", "price", "change", "ret1y", "ret5y"]);
    expect(COLUMNS.filter((c) => /^(change|ret)/.test(c.key)).map((c) => c.key)).toEqual(["change", "ret1y", "ret5y"]);       // exactly three return columns
    expect(COL_BY.ret5y.label).toMatch(/total/);                                                                              // 5Y is the total change, and says so
    expect(new Set(COLUMNS.map((c) => c.key)).size).toBe(COLUMNS.length);
  });
  it("the disclaimer text equals the server's", () => {
    expect(py).toContain('DISCLAIMER = "Information only. Not investment advice. Past returns do not guarantee future returns."');
  });
  it("a blank always has a reason", () => {
    const blank = item({ ret5y: null, why: { ret_5y: "Listed less than 5 years", change: "Price jumped on 21 Oct 2026" }, ret1y: null, changePct: null });
    expect(whyBlank(blank, COL_BY.ret5y)).toBe("Listed less than 5 years");
    expect(whyBlank(blank, COL_BY.change)).toBe("Price jumped on 21 Oct 2026");
    expect(whyBlank(blank, COL_BY.ret1y)).toBe("Not enough price history");
    expect(whyBlank(item({ nav: null }), COL_BY.premium)).toMatch(/AMFI/);
    expect(whyBlank(item(), COL_BY.category)).toMatch(/name/);
  });
});

describe("glossary", () => {
  const pending = JSON.parse(readFileSync(new URL("../../../backend/tests/fixtures/etf/new_glossary_terms.json", import.meta.url), "utf8")) as { term: string; id: string; meaning: string; why: string; how: string; aliases: string[]; topic: string; letter: string }[];
  it("every term the pages explain exists in the glossary or in the list waiting to be merged", () => {
    const have = new Set([...TERMS.map((t) => norm(t.term)), ...pending.map((t) => norm(t.term))]);
    for (const n of GLOSSARY_NAMES) expect(have.has(norm(n)), n).toBe(true);
    for (const n of Object.values(CATEGORY_TERM)) expect(GLOSSARY_NAMES).toContain(n);
    for (const c of COLUMNS) if (c.term) expect(GLOSSARY_NAMES).toContain(c.term);
  });
  it("the new terms are complete, unique and carry no advice", () => {
    const ids = new Set(TERMS.map((t) => t.id));
    for (const t of pending) {
      expect(t.meaning && t.why && t.how && t.topic && t.letter && t.id).toBeTruthy();
      expect(t.letter).toBe(t.term[0].toUpperCase());
    }
    expect(new Set(pending.map((t) => t.id)).size).toBe(pending.length);
    // before the merge none of the ids exist; after it they are the glossary's own, so only the first case is checked for clashes with other terms
    for (const t of pending) if (ids.has(t.id)) expect(norm(TERMS.find((x) => x.id === t.id)!.term)).toBe(norm(t.term));
    const text = pending.map((t) => `${t.meaning} ${t.why} ${t.how}`).join(" ").toLowerCase();
    for (const bad of ["you should buy", "you should sell", "guaranteed", "will rise", "best etf"]) expect(text).not.toContain(bad);
  });
});

describe("chart maths", () => {
  it("nice ticks frame the data with round numbers", () => {
    expect(niceTicks(251.7, 302.25, 5)).toEqual([240, 260, 280, 300, 320]);
    const t = niceTicks(0, 100, 5);
    expect(t[0]).toBe(0); expect(t[t.length - 1]).toBe(100);
    expect(niceTicks(100, 100, 5).length).toBeGreaterThan(1);                       // a flat line still gets an axis
    expect(niceTicks(NaN, 1)).toEqual([]);
  });
  const pts: Point[] = [["2026-01-01", 100], ["2026-01-11", 110], ["2026-01-21", 90], ["2026-02-10", 120]];
  it("places points by date and value inside the frame", () => {
    const f = frameOf([pts], 400, 200)!;
    expect(px(f, "2026-01-01")).toBe(f.x0); expect(px(f, "2026-02-10")).toBe(f.x1);
    expect(px(f, "2026-01-11")).toBeCloseTo(f.x0 + ((f.x1 - f.x0) * 10) / 40, 5);   // 10 of 40 days
    expect(py(f, f.vMin)).toBe(f.y0); expect(py(f, f.vMax)).toBe(f.y1);
    expect(f.vMin).toBeLessThanOrEqual(90); expect(f.vMax).toBeGreaterThanOrEqual(120);
    expect(py(f, 120)).toBeLessThan(py(f, 90));                                     // higher value, higher on the screen (smaller y)
    expect(linePath(f, pts).startsWith("M")).toBe(true);
    expect(linePath(f, pts).match(/L/g)!.length).toBe(3);
    expect(frameOf([[pts[0]]], 400, 200)).toBeNull();
  });
  it("finds the nearest point to the pointer", () => {
    const f = frameOf([pts], 400, 200)!;
    expect(nearest(f, pts, px(f, "2026-01-12"))).toBe(1);
    expect(nearest(f, pts, 0)).toBe(0); expect(nearest(f, pts, 9999)).toBe(3);
    expect(nearest(f, pts, px(f, "2026-02-01"))).toBe(3);                          // closer to 10 Feb than to 21 Jan
  });
  it("date ticks span the range and never crowd", () => {
    const f = frameOf([pts], 400, 200)!;
    const d = dateTicks(f, 6);
    expect(d[0]).toBe("2026-01-01"); expect(d[d.length - 1]).toBe("2026-02-10"); expect(d.length).toBeLessThanOrEqual(5);
    expect(axisDate("2026-01-01", 40)).toMatch(/1 Jan/); expect(axisDate("2026-01-01", 900)).toMatch(/Jan 26/);
  });
  it("rebases every series to 100 on the same day", () => {
    const r = rebase({ A: [["2026-01-01", 50], ["2026-01-05", 55], ["2026-01-09", 60]], B: [["2026-01-02", 200], ["2026-01-05", 190], ["2026-01-09", 220]] }, "2026-01-05");
    expect(r.A[0]).toEqual(["2026-01-05", 100]); expect(r.A[1][1]).toBeCloseTo((60 / 55) * 100, 2);
    expect(r.B[0]).toEqual(["2026-01-05", 100]); expect(r.B[1][1]).toBeCloseTo((220 / 190) * 100, 2);
  });
});

describe("plain words", () => {
  it("volatility is explained as a typical day", () => {
    expect(typicalDay(15.8745)).toBeCloseTo(1, 3);                                  // 15.87% a year is about 1% a day
    expect(volReading(13.02)).toBe("Over the last year the price swung about 13.0% on a yearly basis. On a typical day that is a move of roughly 0.8% up or down.");
    expect(volReading(0.01)).toMatch(/0\.00%/);
    expect(volReading(null)).toBeNull();
  });
  it("falls and ranges name their dates and prices", () => {
    expect(fallReading({ label: "3 years", value: -15.23, peak: "2024-09-27", trough: "2025-03-04" })).toBe(`The worst fall in the last 3 years was 15.2%, from a high on ${dateIN("2024-09-27")} to a low on ${dateIN("2025-03-04")}.`);
    expect(fallReading({ label: "1 year", value: 0, peak: null, trough: null })).toMatch(/never closed below/);
    expect(fallReading({ label: "1 year", value: null, peak: null, trough: null })).toBeNull();
    expect(rangeReading(259.57, 302.25, 251.7)).toBe("The price is 14.1% below its high of ₹302.25 and 3.1% above its low of ₹251.70.");
    expect(rangePosition(259.57, 302.25, 251.7)).toBeCloseTo(15.6, 1);
    expect(rangePosition(259.57, 100, 100)).toBeNull();
    expect(rangePosition(500, 302.25, 251.7)).toBe(100);
  });
  it("premium and discount are described neutrally", () => {
    const up = premiumReading({ value: 100, date: "2026-10-19", premium: 1.5 })!;
    expect(up).toMatch(/1\.50% above the NAV/); expect(up).toMatch(/buyers paid more/);
    expect(premiumReading({ value: 100, date: "2026-10-19", premium: -0.2 })).toMatch(/0\.20% below/);
    expect(premiumReading({ value: 100, date: "2026-10-19", premium: null })).toBeNull();
    expect(premiumReading(null)).toBeNull();
    for (const text of [up, volReading(30)!, rangeReading(1, 2, 0.5)!]) expect(text.toLowerCase()).not.toMatch(/\b(buy now|should buy|should sell|recommend|guarantee)/);
  });
  it("a chart is described in words for screen readers", () => {
    const s = { range: "1Y" as const, available: true, grain: "daily" as const, points: [["2025-10-21", 291.87], ["2026-03-30", 251.7], ["2026-10-21", 259.57]] as Point[] };
    expect(summaryOfSeries("Nippon India ETF Nifty 50 BeES", s)).toBe(`Nippon India ETF Nifty 50 BeES price from ${dateIN("2025-10-21")} (₹291.87) to ${dateIN("2026-10-21")} (₹259.57). Lowest ₹251.70, highest ₹291.87.`);
    expect(summaryOfSeries("X", { ...s, available: false })).toMatch(/no price chart/);
  });
});
