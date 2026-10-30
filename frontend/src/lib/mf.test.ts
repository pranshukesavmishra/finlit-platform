import { describe, expect, it } from "vitest";
import {
  CHECKS, COLUMNS, DEFAULT_COLS, EMPTY_QUERY, FACT_LABELS, PAGE_DEFAULTS, RETURN_LABELS, factKeys, factValueText, retTiles, activeFilterCount, aumText, buildLines, catCount, catNames,
  categoryShort, checklistLines, cleanCats, cleanNum, compareUrl, effectiveQuery, listPath, navText, nearestIndex, niceTicks, noReturnsText, pageWindow,
  parseIds, parseQuery, pctText, queryToParams, readCols, rowSortValue, searchOptions, subCats, terText, toggleAll, toggleCat, tone, trayToggle,
  type FilterCategory, type FundRow,
} from "./mf";
import { CARDS, TABS, classify, keyLabel, selectionTitle, tabLabel, type TabKey } from "./mfCategories";

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
  it("an empty address is the page's default view: every Equity category, Direct plan, Growth option", () => {
    expect(parseQuery(new URLSearchParams(""))).toEqual(PAGE_DEFAULTS);
    expect(PAGE_DEFAULTS).toMatchObject({ tab: "equity", cats: null, plan: "Direct", option: "" });
    expect(queryToParams(PAGE_DEFAULTS).toString()).toBe("");
  });
  it("round-trips every field", () => {
    const q = { ...PAGE_DEFAULTS, q: "hdfc mid", amc: "HDFC Mutual Fund", plan: "Regular", option: "Growth", stopped: true, sort: "sip5y" as const,
      dir: "desc" as const, page: 3, size: 25, min1y: "5", max1y: "40.5", min5y: "10", max5y: "30", view: "ready" as const, tab: "debt" as const, cats: ["corporate-bond", "money-market"] };
    expect(parseQuery(queryToParams(q))).toEqual(q);
    for (const extra of [{ plan: "" }, { tab: "all" as const, cats: null }, { cats: [] as string[] }, { sort: "checklist" as const }]) {
      const r = { ...q, ...extra };
      expect(parseQuery(queryToParams(r))).toEqual(r);
    }
  });
  it("keeps the address short and readable", () => {
    expect(queryToParams({ ...PAGE_DEFAULTS, cats: ["mid-cap", "large-cap"] }).toString()).toBe("cats=large-cap%2Cmid-cap");
    expect(queryToParams({ ...PAGE_DEFAULTS, plan: "" }).toString()).toBe("plan=All");
    expect(queryToParams({ ...PAGE_DEFAULTS, tab: "all", cats: ["x"] }).toString()).toBe("tab=all");   // "all" has no sub-categories
    expect(queryToParams({ ...PAGE_DEFAULTS, cats: [] }).toString()).toBe("cats=");                   // none ticked is a state of its own
  });
  it("junk in the address falls back to safe values", () => {
    const q = parseQuery(new URLSearchParams("plan=Gold&option=x&sort=drop&dir=sideways&page=-4&size=9999&min1y=abc&max1y=1e9&stopped=yes&tab=bonds"));
    expect(q).toEqual(PAGE_DEFAULTS);
    expect(parseQuery(new URLSearchParams("page=2.5")).page).toBe(1);
    expect(parseQuery(new URLSearchParams("q=" + "x".repeat(200))).q).toHaveLength(80);
    expect(parseQuery(new URLSearchParams("cats=Mid Cap,small-cap,small-cap,<script>,a," + "b".repeat(50))).cats).toEqual(["a", "small-cap"]);
    expect(cleanCats("z,y,x")).toEqual(["x", "y", "z"]);
  });
  it("an older link to one exact AMFI category opens its tab with its sub-category ticked", () => {
    expect(parseQuery(new URLSearchParams("category=Equity Scheme - Mid Cap Fund"))).toMatchObject({ tab: "equity", cats: ["mid-cap"] });
    expect(parseQuery(new URLSearchParams("category=Income/Debt Oriented Schemes - Money Market Fund"))).toMatchObject({ tab: "debt", cats: ["money-market"] });
    expect(parseQuery(new URLSearchParams("category=Equity Scheme - Mid Cap Fund&tab=debt"))).toMatchObject({ tab: "debt", cats: null });   // the new address wins
  });
  it("only chosen sorts keep a direction", () => {
    expect(queryToParams({ ...PAGE_DEFAULTS, dir: "desc" }).toString()).toBe("");
    expect(queryToParams({ ...PAGE_DEFAULTS, sort: "name", dir: "desc" }).toString()).toBe("sort=name&dir=desc");
  });
  it("API address: a whole tab as group, ticked sub-categories as their AMFI names, page and size always", () => {
    expect(listPath(EMPTY_QUERY)).toBe("/api/mf?page=1&size=50");
    expect(listPath(PAGE_DEFAULTS)).toBe("/api/mf?group=equity&plan=Direct&page=1&size=50");
    expect(listPath({ ...EMPTY_QUERY, q: "axis liquid", plan: "Direct", stopped: true, sort: "r1y", dir: "desc", min1y: "0" })).toBe("/api/mf?q=axis+liquid&plan=Direct&min1y=0&stopped=true&sort=r1y&dir=desc&page=1&size=50");
    const p = new URL(listPath({ ...PAGE_DEFAULTS, cats: ["large-cap"] }, ["Equity Schemes - Large Cap Fund", "Equity Scheme - Large Cap Fund"]), "http://x").searchParams;
    expect(p.getAll("categories")).toEqual(["Equity Scheme - Large Cap Fund", "Equity Schemes - Large Cap Fund"]) ; expect(p.get("group")).toBeNull();
  });
  it("orders by fund size when no order is chosen, by match while searching", () => {
    expect(effectiveQuery(PAGE_DEFAULTS)).toMatchObject({ sort: "aum", dir: "desc" });
    expect(effectiveQuery({ ...PAGE_DEFAULTS, q: "hdfc" }).sort).toBe("");
    expect(effectiveQuery({ ...PAGE_DEFAULTS, sort: "r1y", dir: "asc" })).toMatchObject({ sort: "r1y", dir: "asc" });
  });
  it("range boxes accept numbers only", () => {
    expect(cleanNum(" 12.5 ")).toBe("12.5"); expect(cleanNum("-3")).toBe("-3"); expect(cleanNum("1,000")).toBe("1000");
    for (const bad of ["", "abc", "1e9", "NaN", "Infinity", "--1"]) expect(cleanNum(bad)).toBe("");
  });
  it("counts filters beyond the categories and the defaults, not search or sort", () => {
    expect(activeFilterCount(PAGE_DEFAULTS)).toBe(0);
    expect(activeFilterCount({ ...PAGE_DEFAULTS, q: "x", sort: "r1y", amc: "A", min1y: "1", stopped: true, cats: ["elss"] })).toBe(3);
    expect(activeFilterCount({ ...PAGE_DEFAULTS, plan: "" })).toBe(1);
  });
  it("the table offers the owner's columns: returns over 1, 3 and 5 years, SIP over 3 and 5, fund size, expense ratio, health score, checklist", () => {
    const ids = COLUMNS.map((c) => c.id);
    expect(ids).toEqual(["amc", "category", "plan", "option", "nav", "navDate", "change", "r1y", "r3y", "r5y", "sip3y", "sip5y", "aum", "ter", "score", "checklist"]);
    expect(COLUMNS.filter((c) => c.group === "ret").map((c) => c.id)).toEqual(["change", "r1y", "r3y", "r5y"]);
    expect(COLUMNS.filter((c) => c.group === "sip").map((c) => c.id)).toEqual(["sip3y", "sip5y"]);
    expect(COLUMNS.every((c) => c.sort !== null || ["plan", "option"].includes(c.id))).toBe(true);
    expect(COLUMNS.find((c) => c.id === "r1y")!.label).toBe("1 year");
    expect(COLUMNS.find((c) => c.id === "r5y")!.hint).toMatch(/CAGR/);
  });
  it("the default columns are the dashboard's", () => {
    expect(DEFAULT_COLS).toEqual(["category", "nav", "r1y", "r3y", "r5y", "sip3y", "sip5y", "aum", "ter", "score", "checklist"]); expect(readCols()).toEqual(DEFAULT_COLS);
  });
  it("fund size and expense ratio text", () => {
    expect(aumText(147064.25)).toBe("₹1,47,064 Cr"); expect(aumText(45.3)).toBe("₹45.30 Cr"); expect(aumText(null)).toBe("—");
    expect(terText(0.4)).toBe("0.40%"); expect(terText(undefined)).toBe("—");
  });
});

// ------------------------------------------------------------------------------------------------ categories

const REAL: [string, TabKey, string][] = [   // AMFI's names as stored from NAVAll.txt, both generations; the server's tests use the same list
  ["Equity Scheme - Large Cap Fund", "equity", "large-cap"], ["Equity Schemes - Large Cap Fund", "equity", "large-cap"],
  ["Equity Scheme - Large & Mid Cap Fund", "equity", "large-mid-cap"], ["Equity Schemes - Large & Mid Cap Fund", "equity", "large-mid-cap"],
  ["Equity Scheme - ELSS", "equity", "elss"], ["Equity Schemes - ELSS- Tax Saver Fund", "equity", "elss"], ["ELSS", "equity", "elss"],
  ["Equity Scheme - Sectoral/ Thematic", "equity", "sectoral-thematic"], ["Equity Schemes - Sectoral Fund", "equity", "sectoral-thematic"],
  ["Equity Schemes - Thematic Fund", "equity", "sectoral-thematic"], ["Equity Scheme - Flexi Cap Fund", "equity", "flexi-cap"],
  ["Equity Scheme - Small Cap Fund", "equity", "small-cap"], ["Equity Scheme - Mid Cap Fund", "equity", "mid-cap"], ["Equity Scheme - Multi Cap Fund", "equity", "multi-cap"],
  ["Equity Scheme - Contra Fund", "equity", "contra"], ["Equity Scheme - Dividend Yield Fund", "equity", "dividend-yield"], ["Equity Scheme - Value Fund", "equity", "value"],
  ["Equity Scheme - Focused Fund", "equity", "focused"], ["Growth", "equity", "equity-other"],
  ["Debt Scheme - Money Market Fund", "debt", "money-market"], ["Income/Debt Oriented Schemes - Money Market Fund", "debt", "money-market"],
  ["Debt Scheme - Corporate Bond Fund", "debt", "corporate-bond"], ["Income/Debt Oriented Schemes - Corporate Bond Fund", "debt", "corporate-bond"],
  ["Debt Scheme - Low Duration Fund", "debt", "low-duration"], ["Income/Debt Oriented Schemes - Ultra Short to Short Term Fund", "debt", "low-duration"],
  ["Debt Scheme - Ultra Short Duration Fund", "debt", "ultra-short"], ["Income/Debt Oriented Schemes - Ultra Short Term Fund", "debt", "ultra-short"],
  ["Debt Scheme - Medium to Long Duration Fund", "debt", "medium-long-duration"], ["Income/Debt Oriented Schemes - Medium Term Fund", "debt", "medium-duration"],
  ["Income/Debt Oriented Schemes - Long Term Fund", "debt", "long-duration"], ["Debt Scheme - Short Duration Fund", "debt", "short-duration"],
  ["Income/Debt Oriented Schemes - 10-year Constant Maturity Gilt Fund", "debt", "gilt-10y"], ["Debt Scheme - Gilt Fund", "debt", "gilt"],
  ["Income/Debt Oriented Schemes - Dynamic Term Fund", "debt", "dynamic-bond"], ["Income/Debt Oriented Schemes - Floating Interest Rates Fund", "debt", "floater"],
  ["Income/Debt Oriented Schemes - Banking and PSU Debt Fund", "debt", "banking-psu"], ["Debt Scheme - Banking and PSU Fund", "debt", "banking-psu"],
  ["Income/Debt Oriented Schemes - Fixed Term Plan", "debt", "fixed-term"], ["Income", "debt", "fixed-term"], ["Debt Scheme - Overnight Fund", "debt", "overnight"],
  ["Income/Debt Oriented Schemes - Liquid Fund", "debt", "liquid"], ["Income/Debt Oriented Schemes - Other Debt Scheme", "debt", "debt-other"],
  ["Hybrid Scheme - Dynamic Asset Allocation or Balanced Advantage", "hybrid", "balanced-advantage"],
  ["Hybrid Schemes - Balanced Advantage Fund/ Dynamic Asset Allocation", "hybrid", "balanced-advantage"], ["Hybrid Schemes - Balanced Hybrid Fund", "hybrid", "balanced-hybrid"],
  ["Hybrid Scheme - Aggressive Hybrid Fund", "hybrid", "aggressive-hybrid"], ["Hybrid Schemes - Equity Savings Fund", "hybrid", "equity-savings"],
  ["Hybrid Scheme - Arbitrage Fund", "hybrid", "arbitrage"], ["Hybrid Schemes - Multi Asset Allocation Fund", "hybrid", "multi-asset"],
  ["Hybrid Scheme - Conservative Hybrid Fund", "hybrid", "conservative-hybrid"],
  ["Solution Oriented Scheme - Retirement Fund", "solution", "retirement"], ["Solution Oriented Schemes ** - Retirement Fund", "solution", "retirement"],
  ["Solution Oriented Scheme - Children’s Fund", "solution", "childrens"], ["Children’s Fund - Childrens' Fund", "solution", "childrens"],
  ["Life Cycle Funds - Life Cycle Fund with Maturity of 10 Years", "solution", "life-cycle"],
  ["Other Scheme - Index Funds", "other", "index-funds"], ["Index Funds - Equity Funds", "other", "index-funds"], ["Index Funds - Debt Funds", "other", "index-debt"],
  ["Other Scheme - Gold ETF", "other", "gold-etf"], ["Exchange Traded Funds (ETFs) - Gold ETF", "other", "gold-etf"], ["Exchange Traded Funds (ETFs) - Silver ETF", "other", "silver-etf"],
  ["Exchange Traded Funds (ETFs) - Debt ETF", "other", "etf-debt"], ["Other Scheme - Other ETFs", "other", "etf"], ["Exchange Traded Funds (ETFs) - Equity ETF", "other", "etf"],
  ["Other Scheme - FoF Overseas", "other", "fof-overseas"], ["Overseas Fund of Funds - Fund of Funds investing overseas", "other", "fof-overseas"],
  ["Other Scheme - FoF Domestic", "other", "fof-domestic"], ["Fund of Funds Scheme (Domestic) - Fund of Funds Scheme (Domestic)", "other", "fof-domestic"],
  ["Something New - Never Seen", "other", "other"],
];
const cat = (name: string, n: Partial<FilterCategory> = {}): FilterCategory => ({ name, group: "", type: "Open Ended", active: 10, total: 12, ...n });

describe("category map", () => {
  it("files every AMFI category name (both generations) in one tab and one sub-category", () => {
    for (const [name, tab, key] of REAL) expect([name, classify(name).tab, classify(name).key]).toEqual([name, tab, key]);
  });
  it("tabs are the owner's five, in his order, and every sub-category key has a friendly name", () => {
    expect(TABS.map((t) => t.label)).toEqual(["Equity", "Hybrid", "Debt", "Solution Oriented", "Others"]);
    for (const [name] of REAL) expect(keyLabel(classify(name).key)).toBe(classify(name).label);
    expect(keyLabel("large-mid-cap")).toBe("Large & Mid Cap"); expect(keyLabel("nope")).toBe("nope");
  });
  it("the six cards: categories, tabs and the owner's descriptor lines", () => {
    expect(CARDS.map((c) => [c.key, c.tab])).toEqual([["elss", "equity"], ["large-cap", "equity"], ["flexi-cap", "equity"], ["small-cap", "equity"], ["money-market", "debt"], ["corporate-bond", "debt"]]);
    const elss = CARDS[0];
    expect(elss.lines).toEqual(["Lock-in for three years", "Tax savings of up to Rs. 46,800 under 80C"]);
    expect(elss.note).toMatch(/old tax regime/);
    expect(Math.round(150000 * 0.3 * 1.04)).toBe(46800);   // ₹1.5 lakh at the 30% slab plus 4% cess
    expect(CARDS.find((c) => c.key === "corporate-bond")!.lines).toEqual(["Higher risk & return than FD", "Medium-term (1–5 years) investments"]);
    for (const c of CARDS) expect(REAL.some(([, tab, key]) => tab === c.tab && key === c.key)).toBe(true);   // a card always matches real AMFI names
  });
  it("the heading names the chosen categories", () => {
    expect(selectionTitle("equity", [], true)).toBe("Equity");
    expect(selectionTitle("equity", ["Large Cap", "Multi Cap"], false)).toBe("Large Cap & Multi Cap");
    expect(selectionTitle("equity", ["Contra", "Large Cap", "Mid Cap", "Small Cap", "Value"], false)).toBe("Contra, Large Cap & 3 more equity");
    expect(selectionTitle("all", ["x"], false)).toBe("All"); expect(tabLabel("solution")).toBe("Solution Oriented");
  });
  it("sub-categories merge both spellings, count for the plan chosen, and hide empty ones unless ticked", () => {
    const cats = [cat("Equity Scheme - Large Cap Fund", { direct: 30, regular: 31, growth: 61 }), cat("Equity Schemes - Large Cap Fund", { direct: 20, regular: 21, growth: 41 }),
      cat("Equity Scheme - Contra Fund", { direct: 0, regular: 0, growth: 0, active: 0 }), cat("Debt Scheme - Gilt Fund"), cat("ELSS", { active: 5 })];
    const base = { plan: "Direct", option: "", stopped: false, cats: null };
    const subs = subCats(cats, "equity", base);
    expect(subs.map((s) => [s.key, s.count])).toEqual([["elss", 5], ["large-cap", 50]]);   // A to Z by name; contra has none
    expect(subs[1].names).toEqual(["Equity Scheme - Large Cap Fund", "Equity Schemes - Large Cap Fund"]);
    expect(subCats(cats, "equity", { ...base, plan: "" }).find((s) => s.key === "large-cap")!.count).toBe(102);
    expect(subCats(cats, "equity", { ...base, plan: "Regular" }).find((s) => s.key === "large-cap")!.count).toBe(52);
    expect(subCats(cats, "equity", { ...base, option: "IDCW" }).find((s) => s.key === "large-cap")!.count).toBe(20);   // only `active` is known for IDCW
    expect(subCats(cats, "equity", { ...base, stopped: true }).find((s) => s.key === "large-cap")!.count).toBe(24);
    expect(subCats(cats, "equity", { ...base, cats: ["contra"] }).map((s) => s.key)).toContain("contra");
    expect(catNames(cats, "equity", ["large-cap", "elss"])).toEqual(["ELSS", "Equity Scheme - Large Cap Fund", "Equity Schemes - Large Cap Fund"]);
    expect(catNames(cats, "debt", ["large-cap"])).toEqual([]);
    expect(catCount(cat("X"), { plan: "Direct", option: "", stopped: false })).toBe(10);   // an older answer without per-plan counts
  });
  it("ticking and Select All", () => {
    const all = ["contra", "elss", "large-cap"];
    expect(toggleCat(null, "elss", all)).toEqual(["contra", "large-cap"]);
    expect(toggleCat(["contra", "large-cap"], "elss", all)).toBeNull();   // all ticked again: one address for "all"
    expect(toggleCat([], "elss", all)).toEqual(["elss"]);
    expect(toggleCat(["elss"], "elss", all)).toEqual([]);
    expect(toggleAll(null)).toEqual([]); expect(toggleAll(["elss"])).toBeNull(); expect(toggleAll([])).toBeNull();
  });
});

// ------------------------------------------------------------------------------------------------ checklist

describe("checklist", () => {
  const row = (over: Partial<FundRow>): FundRow => ({
    code: 1, name: "A Small Cap Fund", amc: "A Mutual Fund", category: "Equity Scheme - Small Cap Fund", plan: "Direct", option: "Growth", optionClass: "Growth", nav: 10, navDate: "2026-10-19",
    change: null, active: true, r1y: 5, r3y: 20, r5y: 25, noReturns: null, sip3y: 18, sip5y: 21, fall3y: -10, aum: 750, ter: 0.4, ...over,
  });
  const peers = { "small-cap|Direct": { r5y: 20, n5: 4, r3y: 18, n3: 5, ter: 0.7, nTer: 4, fall: -20, nFall: 5, n: 6 } };
  it("five checks in the server's order, each with the figure and the category median", () => {
    expect(CHECKS.map((c) => c.key)).toEqual(["ret", "ter", "fall", "size", "age"]);
    const l = checklistLines(row({ checklist: { pass: 5, of: 5, bits: 63, mask: 31, peer: "small-cap|Direct" } }), peers);
    expect(l.map((x) => x.state)).toEqual(["pass", "pass", "pass", "pass", "pass"]);
    expect(l[0].text).toBe("Long-term return: 5-year return 25.00% a year; category median 20.00% (4 schemes).");
    expect(l[1].text).toBe("Costs: Expense ratio 0.40%; category median 0.70%.");
    expect(l[2].text).toMatch(/−10.00%; category median −20.00%/);
    expect(l[3].text).toMatch(/₹750 Cr; the floor is ₹500 Cr/);
  });
  it("a check that could not be worked out says why and is not a fail", () => {
    const l = checklistLines(row({ r5y: null, ter: null, aum: null, checklist: { pass: 1, of: 3, bits: 1, mask: 1 | 4 | 16, peer: "small-cap|Direct" } }), peers);
    expect(l.map((x) => x.state)).toEqual(["pass", "unknown", "fail", "unknown", "fail"]);
    expect(l[0].text).toMatch(/3-year return 20.00% a year; category median 18.00% \(5 schemes\). No 5-year figure yet./);
    expect(l[1].text).toMatch(/not in AMFI's latest TER file/); expect(l[3].text).toMatch(/not in the AMFI or fund-house files/);
    expect(l[4].text).toMatch(/less than 5 years/);
    expect(checklistLines(row({ checklist: null }))).toEqual([]);
  });
  it("sorts rows already in the browser by checklist, then by how many checks were known", () => {
    const a = row({ checklist: { pass: 3, of: 5, bits: 0, mask: 0, peer: "" } }), b = row({ checklist: { pass: 3, of: 4, bits: 0, mask: 0, peer: "" } });
    expect((rowSortValue(a, "checklist") as number) > (rowSortValue(b, "checklist") as number)).toBe(true);
    expect(rowSortValue(row({ checklist: null }), "checklist")).toBeNull(); expect(rowSortValue(row({}), "aum")).toBe(750);
  });
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

describe("aumBucket", () => {
  it("names a fund's size from rupees crore, on the published bands", async () => {
    const { aumBucket } = await import("./mf");
    expect(aumBucket(null)).toBeNull(); expect(aumBucket(-1)).toBeNull(); expect(aumBucket(NaN)).toBeNull();
    expect(aumBucket(99.99)?.label).toBe("Very small"); expect(aumBucket(100)?.label).toBe("Small"); expect(aumBucket(499)?.label).toBe("Small");
    expect(aumBucket(500)?.label).toBe("Medium"); expect(aumBucket(1999)?.label).toBe("Medium"); expect(aumBucket(2000)?.label).toBe("Large");
    expect(aumBucket(9999)?.label).toBe("Large"); expect(aumBucket(10000)?.label).toBe("Very large"); expect(aumBucket(147064)?.step).toBe(5);
  });
});

describe("return and cost bands", () => {
  it("puts a return in the published band, on both edges", async () => {
    const { returnBand } = await import("./mf");
    expect(returnBand("r1y", null)).toBeNull();
    expect(returnBand("r1y", -0.1)?.label).toBe("Negative"); expect(returnBand("r1y", 0)?.label).toBe("0–8%"); expect(returnBand("r1y", 8)?.label).toBe("8–15%"); expect(returnBand("r1y", 15)?.label).toBe("Above 15%");
    expect(returnBand("r3y", 7.99)?.label).toBe("Below 8%"); expect(returnBand("r5y", 8)?.label).toBe("8–12%"); expect(returnBand("r5y", 12)?.label).toBe("12–15%"); expect(returnBand("r5y", 15)?.label).toBe("Above 15%");
  });
  it("judges an expense ratio against its own category median", async () => {
    const { costLevel } = await import("./mf");
    expect(costLevel(0.5, null)).toBeNull(); expect(costLevel(null, 1)).toBeNull(); expect(costLevel(1, 0)).toBeNull();
    expect(costLevel(0.8, 1)?.label).toBe("Low"); expect(costLevel(1, 1)?.label).toBe("Moderate"); expect(costLevel(1.2, 1)?.label).toBe("High");
  });
});
