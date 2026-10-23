import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SearchRow } from "./api";
import { allSections, amcKey, amcLogo, flat, highlight, moversToday, quoteMap, searchStocks, stockItem, todayIST, type Quotes } from "./globalSearch";
import { visits } from "./recentVisits";

const store = new Map<string, string>();
const fake = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k), clear: () => store.clear(), key: () => null, length: 0 };
(globalThis as unknown as { localStorage: Storage }).localStorage = fake as Storage;

const rows: SearchRow[] = [
  ["RELIANCE", "Reliance Industries Ltd", "500325", 1], ["HDFCBANK", "HDFC Bank Ltd", "500180", 0], ["TCS", "Tata Consultancy Services Ltd", "532540", 0],
  ["HDFCAMC", "HDFC Asset Management Company Ltd", "541729", 0], ["HDFCLIFE", "HDFC Life Insurance Company Ltd", "540777", 0],
  ["IDFCFIRSTB", "IDFC First Bank Ltd", "539437", 0], ["^NIFTY50", "Nifty 50", null, 0], ["M&M", "Mahindra & Mahindra Ltd", "500520", 0, "M&M"],
];
const quotes: Quotes = {
  fields: [], level: "silver", builtAt: 0, amcLogos: { sbi: "/api/logos/aaaaaaaaaaaaaaaa.png", nipponindia: "/api/logos/bbbbbbbbbbbbbbbb.png", tata: "/api/logos/cccccccccccccccc.png" },
  rows: [["RELIANCE", 1184, -1.21, "2026-10-23", 51, "mixed", "/api/logos/1111111111111111.png"], ["HDFCBANK", 950.5, 2.4, "2026-10-23", null, "locked", null],
    ["TCS", 3100, 0.8, "2026-10-22", 70, "healthy", null], ["HDFCAMC", 4000, -3.1, "2026-10-23", null, null, null]],
};

describe("stock search", () => {
  it("puts the larger company first among symbol prefixes, and finds BSE codes and typos", () => {
    expect(searchStocks(rows, "hdfc", 5).map((h) => h.row[0])).toEqual(["HDFCBANK", "HDFCAMC", "HDFCLIFE", "IDFCFIRSTB"]);
    expect(searchStocks(rows, "500325", 3)[0].row[0]).toBe("RELIANCE");
    expect(searchStocks(rows, "relaince", 3)[0].row[0]).toBe("RELIANCE");
    expect(searchStocks(rows, "tata consult", 3)[0].row[0]).toBe("TCS");
    expect(searchStocks(rows, "nifty", 5)).toEqual([]);                          // index rows are not companies
    expect(searchStocks(rows, "  ", 5)).toEqual([]);
  });
  it("lifts a followed company among equal matches", () => {
    expect(searchStocks(rows, "hdfc", 5, new Set(["HDFCLIFE"]))[0].row[0]).toBe("HDFCLIFE");
  });
  it("joins prices, scores and logos by symbol; a missing quote is just empty", () => {
    const q = quoteMap(quotes);
    const rel = stockItem(rows[0], q), idfc = stockItem(rows[5], q);
    expect(rel).toMatchObject({ price: 1184, chg: -1.21, score: 51, band: "mixed", logo: "/api/logos/1111111111111111.png", ready: true, href: "/stocks/RELIANCE" });
    expect(idfc).toMatchObject({ price: null, chg: null, score: null, band: null, logo: null });
    expect(stockItem(rows[1], q).band).toBe("locked");
    expect(stockItem(rows[7], q).href).toBe("/stocks/M%26M");
  });
});

describe("moving today", () => {
  it("uses today's moves only, biggest up first then biggest down", () => {
    const got = moversToday(rows, quoteMap(quotes), "2026-10-23", 4).map((r) => r[0]);
    expect(got).toEqual(["HDFCBANK", "HDFCAMC", "RELIANCE"]);                     // TCS last traded on an earlier day: left out
  });
});

describe("fund-house logos", () => {
  it("matches AMFI and exchange spellings to the longest known key", () => {
    expect(amcKey("Nippon India Mutual Fund")).toBe("nipponindia");
    expect(amcLogo("Nippon India Mutual Fund", quotes.amcLogos)).toBe("/api/logos/bbbbbbbbbbbbbbbb.png");
    expect(amcLogo("SBI Funds Management Ltd", quotes.amcLogos)).toBe("/api/logos/aaaaaaaaaaaaaaaa.png");
    expect(amcLogo("Tata Asset Management", quotes.amcLogos)).toBe("/api/logos/cccccccccccccccc.png");
    expect(amcLogo("Unknown House", quotes.amcLogos)).toBeNull();
    expect(amcLogo(null, quotes.amcLogos)).toBeNull();
  });
});

describe("highlight", () => {
  const marked = (t: string, q: string) => highlight(t, q).filter((p) => p.hit).map((p) => p.t);
  it("marks each word at a word start when it can", () => {
    expect(marked("HDFC Bank Ltd", "hdfc")).toEqual(["HDFC"]);
    expect(marked("Tata Consultancy Services", "con serv")).toEqual(["Con", "Serv"]);
    expect(marked("Bandhan Bank", "an")).toEqual(["an"]);                         // no word starts with it: the first place inside a word
    expect(highlight("Infosys", "")).toEqual([{ t: "Infosys", hit: false }]);
    expect(highlight("A+B (C)", "(c")).toEqual([{ t: "A+B ", hit: false }, { t: "(C", hit: true }, { t: ")", hit: false }]);   // no regex: symbols are safe
  });
});

describe("sections", () => {
  it("shows a best match once, caps each kind and keeps one keyboard order", () => {
    const q = quoteMap(quotes);
    const stocks = rows.slice(0, 6).map((r) => stockItem(r, q));
    const fund = { kind: "mf" as const, key: "mf:1", title: "F", sub: "", href: "/funds/1" };
    const secs = allSections(stocks, stocks[0], [fund, fund, fund, fund], [], []);
    expect(secs.map((s) => s.id)).toEqual(["best", "stocks", "mf"]);
    expect(secs[1].items.map((i) => i.sub)).not.toContain("RELIANCE");
    expect(secs[1].items).toHaveLength(5);
    expect(secs[2].items).toHaveLength(3);
    expect(flat(secs)[0].sub).toBe("RELIANCE");
  });
  it("knows today's date in India", () => {
    expect(todayIST(new Date("2026-10-23T20:00:00Z"))).toBe("2026-10-24");     // 01:30 the next morning in India
    expect(todayIST(new Date("2026-10-23T10:00:00Z"))).toBe("2026-10-23");
  });
});

describe("recent visits", () => {
  beforeEach(() => { localStorage.clear(); });
  it("keeps the newest first, once each, and survives broken or blocked storage", () => {
    visits.add({ k: "stock", id: "TCS", name: "Tata Consultancy Services Ltd" });
    visits.add({ k: "mf", id: "122639", name: "Parag Parikh Flexi Cap Fund", sub: "PPFAS Mutual Fund" });
    visits.add({ k: "stock", id: "TCS", name: "Tata Consultancy Services Ltd" });
    expect(visits.get().map((v) => v.id)).toEqual(["TCS", "122639"]);
    visits.add({ k: "etf", id: "", name: "nothing" });
    expect(visits.get()).toHaveLength(2);
    localStorage.setItem("finlit.recent-visits", "{not json");
    expect(visits.get()).toEqual([]);
    localStorage.setItem("finlit.recents", JSON.stringify(["INFY"]));             // the older stock-only list fills in
    expect(visits.get()).toEqual([{ k: "stock", id: "INFY", name: "", at: 0 }]);
    const spy = vi.spyOn(fake, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => visits.add({ k: "stock", id: "X", name: "X" })).not.toThrow();
    spy.mockRestore();
    visits.clear();
    expect(visits.get()).toEqual([]);
  });
});
