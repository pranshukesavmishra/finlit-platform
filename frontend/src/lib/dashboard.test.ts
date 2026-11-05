import { beforeEach, describe, expect, it } from "vitest";
import { TILE_COLOURS, contrast, dedupeFilings, filingLine, filingTag, firstName, greetingWord, moveBlock, readTab, resultLines, shortDay, shorten, tileColour, tileLabel, titleCase, writeTab, yoyOf } from "./dashboard";
import { WIDGETS, normaliseLayout } from "./prefs";
import type { FeedItem } from "./feed";

const item = (o: Partial<FeedItem>): FeedItem => ({ id: 1, kind: "result", title: "", symbol: "LUPIN", company: "Lupin Ltd", source: "Exchange filing", link: null, date: "2026-11-04", category: null, period: null, summary: null, auto: true, ...o } as FeedItem);

describe("greeting", () => {
  it("capitalises the first name", () => { expect(firstName("pranjal kumar")).toBe("Pranjal"); expect(firstName("  ")).toBe(""); expect(firstName("", "anita.rao@x.in")).toBe("Anita"); });
  it("says the time of day", () => { expect([greetingWord(9), greetingWord(12), greetingWord(16), greetingWord(17), greetingWord(23)]).toEqual(["Good morning", "Good afternoon", "Good afternoon", "Good evening", "Good evening"]); });
});

describe("heat-map tile colours", () => {
  it("maps the seven bands", () => {
    expect([-3, -2, -1, -0.75, -0.3, 0, 0.1, 0.5, 0.75, 1.9, 2, 5].map(tileColour)).toEqual([TILE_COLOURS[0], TILE_COLOURS[0], TILE_COLOURS[1], TILE_COLOURS[2], TILE_COLOURS[2], TILE_COLOURS[3], TILE_COLOURS[3], TILE_COLOURS[4], TILE_COLOURS[5], TILE_COLOURS[5], TILE_COLOURS[6], TILE_COLOURS[6]]);
    expect(tileColour(null)).toBe(TILE_COLOURS[3]);
  });
  it("keeps white text at 4.5:1 or better on every tile", () => { for (const c of TILE_COLOURS) expect(contrast("#FFFFFF", c)).toBeGreaterThanOrEqual(4.5); });
  it("labels by size and never below 11px", () => {
    expect(tileLabel("RELIANCE", 300, 200)).toEqual({ size: 16, pct: true });
    expect(tileLabel("TCS", 80, 50)?.size).toBe(13);
    expect(tileLabel("ADANIPORTS", 80, 50)).toBeNull();                 // 13px does not fit; 11px does not either at 80px
    expect(tileLabel("BEL", 38, 40)?.size).toBe(11);
    expect(tileLabel("RELIANCE", 30, 40)).toBeNull();
    expect(tileLabel("TCS", 80, 20)).toEqual({ size: 11, pct: false });
  });
});

describe("year on year", () => {
  const ends = ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"];
  it("compares with the same quarter a year earlier", () => { expect(yoyOf([100, 1, 1, 1, 135], ends).pct).toBeCloseTo(35); });
  it("says why when it cannot", () => {
    expect(yoyOf([1, 2], ["a", "b"]).reason).toMatch(/Fewer than five/);
    expect(yoyOf([100, 1, 1, 1, 135], ["2025-03-31", ...ends.slice(1)]).reason).toMatch(/missing/);
    expect(yoyOf([-5, 1, 1, 1, 10], ends)).toEqual({ pct: null, reason: expect.stringMatching(/loss/) });
    expect(yoyOf([100, 1, 1, 1, null], ends).reason).toBe("Not reported");
  });
});

describe("results today", () => {
  it("keeps results dates, financial results and outcome-of-meeting results; drops other press releases", () => {
    const lines = resultLines([
      item({ id: 1, symbol: "TENNIND", title: "TENNIND: board meeting for results", category: "Results date", source: "FinEdge results calendar" }),
      item({ id: 2, symbol: "LUPIN", title: "Unaudited financial results for Q2 FY27", category: "Financial Results", period: "Q2 FY27" }),
      item({ id: 3, symbol: "ABC", title: "Outcome of Board Meeting: appointment of CFO", category: "Outcome of Board Meeting" }),
      item({ id: 4, symbol: "XYZ", title: "Press release on new plant", category: "Press Release / Media Release" }),
    ]);
    expect(lines.map((l) => [l.symbol, l.text])).toEqual([["TENNIND", "Board meets on results"], ["LUPIN", "Q2 FY27 results filed"]]);
  });
  it("shows one line per company per day", () => {
    const lines = resultLines([
      item({ id: 1, symbol: "HEGAM", title: "Board meeting for results", category: "Results date" }),
      item({ id: 2, symbol: "HEGAM", title: "Intimation: board meeting to consider results", category: "Results date" }),
    ]);
    expect(lines).toHaveLength(1);
  });
  it("describes a result and its press release together, and a press release about results alone", () => {
    const both = resultLines([item({ symbol: "LUPIN", title: "Financial results Q2 FY27", category: "Financial Results" }), item({ id: 2, symbol: "LUPIN", title: "Press release on Q2 FY27 results", category: "Press Release / Media Release" })]);
    expect(both).toHaveLength(1); expect(both[0].text).toBe("Q2 FY27 results and press release");
    const only = resultLines([item({ symbol: "FRACTAL", title: "Press release on Q2 FY27 results", category: "Results date" })]);
    expect(only[0].text).toBe("Q2 FY27 results and press release");
  });
});

describe("filings", () => {
  it.each([
    ["Unaudited financial results", "Results"], ["Resignation of independent director", "Board"], ["Second reminder for call money on partly paid-up shares", "Capital"],
    ["Record date for dividend", "Dividend"], ["Receipt of order from NHAI", "Order"], ["Amended MOA and AOA", "Corporate"], ["Analyst meet intimation", "Other"],
  ])("tags %s as %s", (title, tag) => { expect(filingTag({ title, category: null })).toBe(tag); });
  it("strips the exchange boilerplate", () => {
    expect(shorten("Lupin Limited has informed the Exchange regarding Change in directors")).toBe("Change in directors");
    expect(shorten("Sanduma Ltd. has submitted to the Exchange that independent director resigns")).toBe("Independent director resigns");
    expect(shorten("Resignation: independent director Latha Pillai")).toBe("Independent director Latha Pillai");
    expect(shorten("Sanduma Textiles ( Company ) intimates a meeting")).toBe("Intimates a meeting");
  });
  it("cuts at a word boundary, never mid-word", () => {
    const long = "Intimation of the board's decision to raise funds through qualified institutional placement of equity shares of the company subject to approvals";
    const s = shorten(long);
    expect(s.length).toBeLessThanOrEqual(112); expect(s.endsWith("…")).toBe(true);
    expect(long.startsWith(s.slice(0, -1).replace(/^./, "I"))).toBe(true);
    expect(long.charAt(s.length - 1)).toBe(" ");
  });
  it("uses the feed's summary when it is filled", () => { expect(filingLine({ title: "x", summary: "the plain summary" })).toBe("The plain summary"); });
  it("shows the same company, day and filing type once", () => {
    const a = { symbol: "SANDUMA", company: null, date: "2026-11-03", category: "Change in Directors", title: "Independent director resigns" };
    expect(dedupeFilings([a, { ...a, title: "Resignation of independent director" }, { ...a, date: "2026-11-04" }, { ...a, category: "Updates" }])).toHaveLength(3);
  });
  it("short day labels", () => { expect([shortDay("2026-11-04", "2026-11-04"), shortDay("2026-11-03", "2026-11-04"), shortDay("2026-11-05", "2026-11-04"), shortDay("2026-10-20", "2026-11-04")]).toEqual(["Today", "Yesterday", "Tomorrow", "20 Oct"]); });
  it("title-cases IPO names in capitals only", () => { expect(titleCase("ANTALA INDUSTRIES LTD")).toBe("Antala Industries Ltd"); expect(titleCase("Vedant Poly Fabs")).toBe("Vedant Poly Fabs"); });
});

describe("phone tab memory", () => {
  const mem = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }; };
  let s: ReturnType<typeof mem>;
  beforeEach(() => { s = mem(); });
  it("remembers the last tab per member", () => {
    expect(readTab("u1", s)).toBe("stocks");
    writeTab("u1", "news", s); writeTab("u2", "market", s);
    expect([readTab("u1", s), readTab("u2", s)]).toEqual(["news", "market"]);
  });
  it("ignores a stored value that is not a tab and a store that throws", () => {
    s.setItem("finlit-dash-tab:u1", "bogus"); expect(readTab("u1", s)).toBe("stocks");
    const bad = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(readTab("u1", bad)).toBe("stocks"); expect(() => writeTab("u1", "news", bad)).not.toThrow();
  });
});

describe("customise layout", () => {
  it("starts with the new default order, the three optional old blocks off, and no Gold & silver or DCF", () => {
    const d = normaliseLayout(null);
    expect(d.slice(0, 3).map((w) => w.id)).toEqual(["mystocks", "market", "snapshot"]);
    const off = d.filter((w) => !w.on).map((w) => w.id);
    expect(off).toEqual(expect.arrayContaining(["commodities", "dcf", "results"]));
    expect(d.filter((w) => w.on).map((w) => w.id)).not.toContain("commodities");
    expect(d).toHaveLength(WIDGETS.length);
  });
  it("replaces a layout saved before the refresh", () => { expect(normaliseLayout([{ id: "movers", on: true, size: "half" }, { id: "learn", on: false, size: "full" }])[0].id).toBe("mystocks"); });
  it("keeps a member's own order, hidden blocks and widths, drops unknown blocks and adds new ones", () => {
    const mine = normaliseLayout([{ id: "filings", on: true, size: "full" }, { id: "mystocks", on: false, size: "half" }, { id: "nope", on: true, size: "half" }, { id: "filings", on: false, size: "half" }]);
    expect(mine.slice(0, 2)).toEqual([{ id: "filings", on: true, size: "full" }, { id: "mystocks", on: false, size: "half" }]);
    expect(mine.map((w) => w.id)).not.toContain("nope");
    expect(new Set(mine.map((w) => w.id)).size).toBe(WIDGETS.length);
  });
  it("moves a block up, down or to a dragged place", () => {
    const l = normaliseLayout(null).slice(0, 4);
    expect(moveBlock(l, 1, 0).map((w) => w.id).slice(0, 2)).toEqual(["market", "mystocks"]);
    expect(moveBlock(l, 0, 3).map((w) => w.id)).toEqual(["market", "snapshot", "sectors", "mystocks"]);
    expect(moveBlock(l, 0, 0)).toEqual(l); expect(moveBlock(l, 0, -1)).toEqual(l); expect(moveBlock(l, 9, 0)).toEqual(l);
  });
  it("gives every block a phone tab", () => { expect(new Set(WIDGETS.map((w) => w.tab))).toEqual(new Set(["stocks", "market", "news"])); });
});
