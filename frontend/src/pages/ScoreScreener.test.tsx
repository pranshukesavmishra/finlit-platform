// @vitest-environment jsdom
// The Basic score screener (FinLit score only, Silver) in a DOM: draft vs applied filters, chips, selection, bulk actions, address (URL) state, CSV and plan gating.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Row } from "../lib/screener";

const st = vi.hoisted(() => ({ plan: "gold" as "basic" | "silver" | "gold", rows: [] as unknown[], cover: null as unknown, upgrade: vi.fn(), toast: vi.fn() }));
vi.mock("../lib/screener", async (orig) => ({ ...(await orig<typeof import("../lib/screener")>()), useUniverse: () => ({ data: { rows: st.rows, sample: true, asOf: "2026-10-26", prism: st.cover }, isLoading: false, isError: false }) }));
vi.mock("../lib/ui", () => ({
  useUI: () => ({ has: (t: string) => ({ basic: 0, silver: 1, gold: 2 })[st.plan] >= ({ basic: 0, silver: 1, gold: 2 } as Record<string, number>)[t], upgrade: st.upgrade, toast: st.toast }),
  TIER: { gold: { n: "Gold" }, silver: { n: "Silver" } },
}));
import { ScoreScreener } from "./ScoreScreener";
import { watch } from "../lib/watchlist";

const mk = (symbol: string, sector: string | null, f: number | null, t: number | null, cap: number | null, o: Partial<Row> = {}): Row => ({
  symbol, name: symbol + " Limited", sector, overall: f == null ? null : f, band: null, pillar_quality: f, pillar_growth: f, pillar_profitability: f, pillar_balance: f, pillar_technical: t,
  price: cap == null ? null : 100, market_cap: cap, pe: null, pb: null, roe: null, roce: null, dividend_yield: null, debt_to_equity: null, sales_cagr: null, profit_cagr: null,
  operating_margin: null, change_pct: null, return_1m: null, return_1y: null, scored: true, ...o,
});
const DATA = [
  mk("AAA", "Banks", 90, 90, 9000), mk("BBB", "Banks", 80, 30, 8000), mk("CCC", "IT", 50, 85, 7000), mk("DDD", "IT", 44, 45, 6000), mk("EEE", "Auto", 77, 78, 5000),
  mk("FFF", null, 60, null, 4000), mk("GGG", "Auto", null, 60, null, { scored: false }), mk("HHH", "Pharma", 78, 77, 3000),
  ...Array.from({ length: 14 }, (_, i) => mk("ZZ" + String(i).padStart(2, "0"), "Metals", 55, 55, 2000 - i * 10)),
];
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
const Where = () => { const l = useLocation(); return <output data-testid="loc">{l.pathname + l.search}</output>; };
const open = (qs = "") => render(<MemoryRouter initialEntries={["/score-screener" + qs]}><Routes><Route path="/score-screener" element={<ScoreScreener />} /><Route path="/advanced-score-screener" element={<div data-testid="adv">advanced page</div>} /><Route path="*" element={<div>elsewhere</div>} /></Routes><Where /></MemoryRouter>);
const loc = () => screen.getByTestId("loc").textContent || "";
const symbols = () => within(screen.getByRole("table")).getAllByRole("row").slice(1).map((r) => within(r).queryAllByRole("cell")[2]?.querySelector("b")?.textContent).filter(Boolean);
const hint = () => document.querySelector(".sx-hint")!;
const sector = (name: string) => screen.getByRole("checkbox", { name: new RegExp("^" + name) });

beforeEach(() => { st.plan = "gold"; st.rows = DATA; st.cover = null; localStorage.clear(); watch.reset(); st.upgrade.mockReset(); st.toast.mockReset(); });
afterEach(cleanup);

describe("Basic score screener page", () => {
  it("lists the universe sorted by market cap, with 10 rows a page and the stat tiles over the whole set", () => {
    open();
    expect(symbols()).toEqual(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "HHH", "ZZ00", "ZZ01", "ZZ02"]);
    const tiles = screen.getByLabelText("Summary");
    expect(within(tiles).getByText("Companies found").previousSibling?.textContent).toBe("22");
    expect(within(tiles).getByText("Sectors").previousSibling?.textContent).toBe("5");           // no-sector company is not a sector
    expect(within(tiles).getByText("Active filters").previousSibling?.textContent).toBe("0");
    expect(screen.getByText("1–10 of 22")).toBeTruthy();
  });

  it("sidebar edits wait for Apply; Apply updates the table, chips and address", () => {
    open();
    fireEvent.click(sector("IT")); fireEvent.click(sector("Auto"));
    expect(symbols()).toHaveLength(10);                                       // draft only: table unchanged
    expect(hint().textContent).toMatch(/Unsaved changes/);
    expect(loc()).toBe("/score-screener");
    fireEvent.submit(screen.getByRole("button", { name: "Apply filters" }).closest("form")!);   // Enter in a field submits the form
    expect(symbols()).toEqual(["CCC", "DDD", "EEE", "GGG"]);
    expect(loc()).toBe("/score-screener?sector=IT&sector=Auto");
    expect(hint().textContent).toBe("");
    expect(screen.getByRole("button", { name: "Remove filter IT" })).toBeTruthy();
    expect(within(screen.getByLabelText("Summary")).getByText("Active filters").previousSibling?.textContent).toBe("2");
  });

  it("score bands and min-max are exact, and missing scores never pass", () => {
    open();
    const fund = screen.getByRole("group", { name: "Fundamental score" }), tech = screen.getByRole("group", { name: "Technical score" });
    fireEvent.click(within(fund).getByRole("button", { name: "78 and above (Strong)" }));
    fireEvent.submit(fund.closest("form")!);
    expect(symbols()).toEqual(["AAA", "BBB", "HHH"]);                        // 78 is in, 77 (EEE) is out, GGG has no Fundamental
    fireEvent.click(within(tech).getByRole("button", { name: "45 to 77 (Mixed, Healthy)" }));
    fireEvent.submit(fund.closest("form")!);
    expect(symbols()).toEqual(["HHH"]);                                      // Technical 77 is in, 78 is out
    fireEvent.click(within(screen.getByRole("group", { name: "Technical score, exact range" })).getByRole("checkbox", { name: "Technical score" }));   // ticking enables Min and Max
    fireEvent.change(within(screen.getByRole("group", { name: "Technical score, exact range" })).getByLabelText("Min"), { target: { value: "78" } });
    expect(screen.getByRole("button", { name: "Apply filters" }).hasAttribute("disabled")).toBe(false);
    fireEvent.change(within(screen.getByRole("group", { name: "Technical score, exact range" })).getByLabelText("Max"), { target: { value: "50" } });
    expect(screen.getByRole("alert").textContent).toMatch(/minimum is above the maximum/);
    expect(screen.getByRole("button", { name: "Apply filters" }).hasAttribute("disabled")).toBe(true);
    fireEvent.submit(fund.closest("form")!);
    expect(loc()).toBe("/score-screener?f=high&t=mid");                      // an invalid range is not applied
  });

  it("a removed chip, and Clear all, update the table and address at once", () => {
    open("?sector=IT&sector=Auto&f=mid");
    expect(symbols()).toEqual(["CCC", "EEE"]);                                // IT or Auto, Fundamental 45 to 77: 50 and 77 (DDD is 44)
    fireEvent.click(screen.getByRole("button", { name: "Remove filter Fundamental: 45–77" }));
    expect(symbols()).toEqual(["CCC", "DDD", "EEE", "GGG"]);
    expect(loc()).toBe("/score-screener?sector=IT&sector=Auto");
    fireEvent.click(screen.getByRole("button", { name: "Remove filter IT" }));
    expect(symbols()).toEqual(["EEE", "GGG"]);                                // Auto only
    fireEvent.click(within(screen.getByLabelText("Active filters")).getByRole("button", { name: "Clear all" }));
    expect(loc()).toBe("/score-screener");
    expect(symbols()).toHaveLength(10);
  });

  it("opens a shared link with its filters, sort and page", () => {
    open("?cap=Large&sector=Metals&sort=name&dir=asc&size=5&page=2");
    expect((sector("Metals") as HTMLInputElement).checked).toBe(true);
    expect(screen.getByRole("button", { name: "Sort by Stock" }).closest("th")!.getAttribute("aria-sort")).toBe("ascending");
    expect(screen.getByRole("button", { name: "Sort by Fundamental" }).closest("th")!.getAttribute("aria-sort")).toBe("none");
    expect((screen.getByLabelText("Rows per page") as HTMLSelectElement).value).toBe("5");
    expect(screen.getByRole("button", { name: "Page 2" }).getAttribute("aria-current")).toBe("page");
  });

  it("sorting by a heading flips the direction, keeps missing scores last and writes the address", () => {
    open("?size=50");
    fireEvent.click(screen.getByRole("button", { name: "Sort by Fundamental" }));
    expect(loc()).toBe("/score-screener?sort=f&dir=desc&size=50");
    expect(symbols().slice(0, 3)).toEqual(["AAA", "BBB", "HHH"]);
    expect(symbols().at(-1)).toBe("GGG");
    fireEvent.click(screen.getByRole("button", { name: "Sort by Fundamental" }));
    expect(symbols().at(-1)).toBe("GGG");                                     // still last when ascending
    expect(symbols()[0]).toBe("DDD");
  });

  it("selects rows, compares 2 and keeps the selection across pages", () => {
    open("?size=5");
    const box = (s: string) => screen.getByRole("checkbox", { name: `Select ${s}` });
    fireEvent.click(box("AAA"));
    expect((screen.getByRole("button", { name: "Compare" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(box("BBB"));
    expect(screen.getByText("2 selected")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("2 selected")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Compare 2" }));
    expect(loc()).toBe("/compare?c=AAA,BBB");
  });

  it("the header box selects the page and shows a partial state", () => {
    open("?size=5");
    const head = screen.getByRole("checkbox", { name: "Select all companies on this page" }) as HTMLInputElement;
    fireEvent.click(head);
    expect(screen.getByText("5 selected")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select AAA" }));
    expect(head.indeterminate).toBe(true);
    fireEvent.click(head);
    expect(screen.getByText("5 selected")).toBeTruthy();
    fireEvent.click(head);
    expect(screen.queryByText(/^\d+ selected$/)).toBeNull();
  });

  it("adds the selected companies to the watchlist; Basic and Silver follow the plan rules", () => {
    open();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select AAA" })); fireEvent.click(screen.getByRole("checkbox", { name: "Select CCC" }));
    fireEvent.click(screen.getByRole("button", { name: "Add to watchlist" }));
    expect(watch.has("AAA") && watch.has("CCC") && !watch.has("BBB")).toBe(true);
    cleanup(); st.plan = "basic"; watch.reset(); open();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select AAA" }));
    fireEvent.click(screen.getByRole("button", { name: "Add to watchlist" }));
    expect(st.upgrade).toHaveBeenCalledWith("silver", expect.any(String));
    expect(watch.has("AAA")).toBe(false);
  });

  it("Silver compares 2 at most; Gold up to 4", () => {
    st.plan = "silver"; open();
    ["AAA", "BBB", "CCC"].forEach((s) => fireEvent.click(screen.getByRole("checkbox", { name: `Select ${s}` })));
    expect((screen.getByRole("button", { name: "Compare" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/compares up to 2/)).toBeTruthy();
  });

  it("exports the selected rows to CSV with the filters in the header and blanks for missing data", async () => {
    open("?sector=Banks&sector=IT&sector=Auto&sort=f&dir=desc");
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    let blob: Blob | null = null;
    URL.createObjectURL = vi.fn((b: Blob) => { blob = b; return "blob:x"; }); URL.revokeObjectURL = vi.fn();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select GGG" }));
    fireEvent.click(screen.getByRole("button", { name: "Export selected" }));
    const text = await new Promise<string>((res) => { const fr = new FileReader(); fr.onload = () => res(String(fr.result)); fr.readAsText(blob!); });
    expect(text).toMatch(/Scores computed on: 2026-10-26/);
    expect(text).toMatch(/# Filters: Banks\r\n#          IT\r\n#          Auto/);
    expect(text).toMatch(/Rows: 1 \(selected rows only; 6 companies match the filters\)/);
    expect(text).toContain("\r\n" + ["GGG", "GGG Limited", "Auto", "", "", "", "", "", "", "", "", "60", ""].join(",") + "\r\n");   // blanks, never zeros
    fireEvent.click(screen.getByRole("button", { name: /Export all 6/ }));
    const all = await new Promise<string>((res) => { const fr = new FileReader(); fr.onload = () => res(String(fr.result)); fr.readAsText(blob!); });
    expect(all.match(/\r\n[A-Z]{3},/g)).toHaveLength(6);
  });

  it("shows a dash with its reason, never a zero, for missing data", () => {
    open("?sector=Auto");
    const row = screen.getByRole("checkbox", { name: "Select GGG" }).closest("tr")!;
    expect(row.textContent).toMatch(/Not available: Not scored yet/);
    expect(row.textContent).not.toMatch(/\b0\b/);
    expect(within(row).getAllByTitle(/Not scored yet/).length).toBeGreaterThan(0);
  });

  it("Basic members see locks and the upgrade card instead of score filters; presets ask for Silver", () => {
    st.plan = "basic"; st.rows = DATA.map((r) => ({ ...r, overall: null, pillar_quality: null, pillar_growth: null, pillar_profitability: null, pillar_balance: null, pillar_technical: null }));
    open();
    expect(screen.getByText(/Score filters are part of Silver/)).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Fundamental score, exact range" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Strong on both/ }));
    expect(st.upgrade).toHaveBeenCalled();
    expect(loc()).toBe("/score-screener");
  });

  it("a quick view applies straight away and can be switched off", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: /Strong on both/ }));
    expect(symbols()).toEqual(["AAA"]);
    expect(loc()).toBe("/score-screener?f=high&t=high");
    fireEvent.click(screen.getByRole("button", { name: /Strong on both/ }));
    expect(loc()).toBe("/score-screener");
  });

  it("opens and closes the How scores work dialog with the exact definitions", () => {
    open();
    fireEvent.click(screen.getAllByRole("button", { name: /How scores work/ })[0]);
    const d = screen.getByRole("dialog", { name: "How scores work" });
    expect(d.textContent).toMatch(/Strong 78 and above, Healthy 62 to 77, Mixed 45 to 61, Watch under 45/);
    expect(d.textContent).toMatch(/100 largest are Large cap, the next 150 Mid cap/);
    expect(d.textContent).toMatch(/26 Oct 2026/);
    expect(d.textContent?.toLowerCase()).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate|target)\b/);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows the sector mix of the whole result", () => {
    open();
    const mix = screen.getByLabelText("Sector mix of the result");
    expect(mix.textContent).toMatch(/Metals 14/);
    expect(mix.textContent).toMatch(/Sector not listed 1/);
  });
});


// ---- two pages: the basic one has no trace of Prism, and old links with Prism filters move to the advanced page
describe("Basic score screener: no Prism", () => {
  const PR = (o: Partial<Row> = {}) => ({ prism_state: "stored", prism_final: 85, prism_label: "STRONG", prism_status: "RATED", prism_fundamental: 80, prism_valuation: 55, prism_quality: 70, prism_risk: 60, prism_st: "Positive", prism_lt: "Neutral", prism_st_score: 22, prism_lt_score: -4, ...o });
  it("is titled Basic score screener and has no Prism column, filter, view, tile or coverage line even when the rows carry Prism values", () => {
    st.rows = DATA.map((r) => ({ ...r, ...PR() })); st.cover = { rated: 3, provisional: 1, not_rated: 1, stored: 5, total: 6, as_of: "2026-10-27", per_night: 30 };
    open();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Basic score screener");
    const page = document.body.textContent || "";
    expect(page).not.toMatch(/Rated by Prism|Median Prism|Prism filters|Prism has rated|Short term|Long term|Valuation|Only companies rated/);
    expect(within(screen.getByRole("table")).queryByRole("columnheader", { name: /Prism|Risk|Valuation/ })).toBeNull();
    expect(document.querySelector(".pzs-cover")).toBeNull();
    // the only mention is the link to the advanced page
    expect([...(page.match(/Prism/g) || [])].length).toBeLessThanOrEqual(4);
    expect(within(screen.getByLabelText("Summary")).queryByText(/Prism/)).toBeNull();
  });
  it("has the FinLit columns only, in order", () => {
    open();
    const heads = within(screen.getByRole("table")).getAllByRole("columnheader").map((h) => h.textContent?.replace(/[▲▼▾]/g, "").trim());
    expect(heads.map((h) => h?.replace(/ \?$/, ""))).toEqual(expect.arrayContaining(["Fundamental", "Quality", "Growth", "Profit.", "Balance", "Technical", "Overall"]));
    expect(screen.getAllByRole("button", { name: /^(Strong on both|Strong fundamentals, weak trend|Strong trend, weaker fundamentals)/ })).toHaveLength(3);
  });
  it("links to the Advanced score screener (Gold) with a Gold chip", () => {
    open();
    const a = screen.getByRole("link", { name: /Advanced score screener/ });
    expect(a.getAttribute("href")).toBe("/advanced-score-screener");
    expect(a.textContent).toMatch(/Advanced score screener \(Gold\): FinLit Prism, 4 fundamental parts and 2 technical views/);
    expect(a.textContent).toMatch(/Gold/);
  });
  it("Silver sees the scores, Basic sees the locked state as before", () => {
    st.plan = "silver"; open();
    expect(screen.queryByText(/Score filters are part of Silver/)).toBeNull();
    expect(screen.getByRole("group", { name: "Fundamental score" })).toBeTruthy();
  });
  it("moves an old link that carries Prism filters to the advanced page with the same parameters", () => {
    open("?zmin=60&pl=strong&rated=1&sector=IT");
    expect(screen.getByTestId("adv")).toBeTruthy();
    expect(loc()).toBe("/advanced-score-screener?zmin=60&pl=strong&rated=1&sector=IT");
    cleanup(); open("?sort=prism_final&dir=desc");
    expect(loc()).toBe("/advanced-score-screener?sort=prism_final&dir=desc");
    cleanup(); open("?f=high&t=mid&sector=IT");
    expect(screen.queryByTestId("adv")).toBeNull();                       // a FinLit-only link stays
    expect(loc()).toBe("/score-screener?f=high&t=mid&sector=IT");
  });
  it("the page text uses no advice wording", () => {
    open();
    expect(document.body.textContent?.toLowerCase()).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate)\b/);
  });

  it("filter groups are buttons that collapse and expand, with aria-expanded and aria-controls", () => {
    open();
    const head = within(screen.getByLabelText("Score screener filters")).getByRole("button", { name: /^Market cap/ });
    expect(head.getAttribute("aria-expanded")).toBe("true");
    const body = document.getElementById(head.getAttribute("aria-controls")!)!;
    expect(body.hidden).toBe(false);
    fireEvent.click(head);
    expect(head.getAttribute("aria-expanded")).toBe("false");
    expect(body.hidden).toBe(true);
    fireEvent.click(head);
    expect(body.hidden).toBe(false);
  });

  it("a group header shows 'n active' for its filters and counts beside options are real", () => {
    open("?sector=IT&sector=Auto&cap=Large");
    expect(screen.getByRole("button", { name: /^Industry \/ Sector.*2 active/ })).toBeTruthy();
    expect(within(screen.getByLabelText("Score screener filters")).getByRole("button", { name: /^Market cap.*1 active/ })).toBeTruthy();
    // 22 companies: the draft counts follow the other filters (Large cap + sector are skipped for their own group)
    const large = screen.getByRole("checkbox", { name: /^Large cap/ }).closest("label")!;
    expect(large.querySelector("small")!.textContent).toMatch(/^\d+$/);
    const banks = sector("Banks").closest("label")!;
    expect(banks.querySelector("small")!.textContent).toBe("2");
  });

  it("a Min - Max row is disabled until its box is ticked, unticking clears it, and the value reaches the address", () => {
    open();
    const g = screen.getByRole("group", { name: "Overall score, exact range" });
    const min = within(g).getByLabelText("Min") as HTMLInputElement;
    expect(min.disabled).toBe(true);
    fireEvent.click(within(g).getByRole("checkbox", { name: "Overall score" }));
    expect(min.disabled).toBe(false);
    fireEvent.change(min, { target: { value: "70" } });
    fireEvent.submit(g.closest("form")!);
    expect(loc()).toBe("/score-screener?omin=70");
    fireEvent.click(within(g).getByRole("checkbox", { name: "Overall score" }));
    expect(min.value).toBe("");
    expect(min.disabled).toBe(true);
  });

  it("the toolbar search narrows the table by name or sector without touching the address", () => {
    open("?size=50");
    fireEvent.change(screen.getByLabelText("Search company name, sector or keyword"), { target: { value: "pharma" } });
    expect(symbols()).toEqual(["HHH"]);
    expect(loc()).toBe("/score-screener?size=50");
  });

  it("the sort select writes the same address as a column heading", () => {
    open();
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "f:-1" } });
    expect(loc()).toContain("sort=f&dir=desc");
    expect(symbols().slice(0, 3)).toEqual(["AAA", "BBB", "HHH"]);
  });

  it("the not-scored donut is computed from the loaded companies", () => {
    open();
    expect(screen.getByText("1 of 22 companies are not scored yet.")).toBeTruthy();
    expect(screen.getByText(/Scored 21 \(95%\)/)).toBeTruthy();
  });
});
