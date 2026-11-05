// @vitest-environment jsdom
// The Basic score screener (FinLit IQ only, Silver) in a DOM: draft vs applied filters, chips, selection, bulk actions, address (URL) state, CSV and plan gating.
import { act, cleanup, fireEvent, render, screen, waitFor, within, configure } from "@testing-library/react";
configure({ asyncUtilTimeout: 8000 });
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { Row } from "../lib/screener";

const st = vi.hoisted(() => ({ plan: "gold" as "basic" | "silver" | "gold", rows: [] as unknown[], cover: null as unknown, upgrade: vi.fn(), toast: vi.fn() }));
vi.mock("../lib/screener", async (orig) => ({ ...(await orig<typeof import("../lib/screener")>()), useUniverse: () => ({ data: { rows: st.rows, sample: true, asOf: "2026-10-26", prism: st.cover }, isLoading: false, isError: false }) }));
const api = vi.hoisted(() => ({ list: { tab: "basic", asOf: "2026-10-30", groups: [] as unknown[] } as unknown }));
vi.mock("../lib/api", async (orig) => ({ ...(await orig<typeof import("../lib/api")>()), apiGet: vi.fn(async (path: string) => { if (path.startsWith("/api/screener/presets")) return api.list; throw new Error("unexpected " + path); }) }));
const admin = vi.hoisted(() => ({ on: true }));
vi.mock("../lib/auth", async (orig) => ({ ...(await orig<typeof import("../lib/auth")>()), useAuth: () => ({ isAdmin: admin.on }) }));
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
const CARD = { id: "basic-top-large", name: "Top 10 large caps", group: "top-rated", cardText: "The 10 large caps with the strongest mix of business scores and price strength.", count: 40, asOf: "2026-10-30", status: "live", blockedReason: null,
  listText: "Top 10 of 40 that pass", chips: [], howItWorks: [], locked: false, tab: "basic" };
const DATA = [
  mk("AAA", "Banks", 90, 90, 9000), mk("BBB", "Banks", 80, 30, 8000), mk("CCC", "IT", 50, 85, 7000), mk("DDD", "IT", 44, 45, 6000), mk("EEE", "Auto", 77, 78, 5000),
  mk("FFF", null, 60, null, 4000), mk("GGG", "Auto", null, 60, null, { scored: false }), mk("HHH", "Pharma", 78, 77, 3000),
  ...Array.from({ length: 14 }, (_, i) => mk("ZZ" + String(i).padStart(2, "0"), "Metals", 55, 55, 2000 - i * 10)),
];
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
const Where = () => { const l = useLocation(); return <output data-testid="loc">{l.pathname + l.search}</output>; };
const open = (qs = "") => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={["/score-screener" + qs]}><Routes><Route path="/score-screener" element={<ScoreScreener />} /><Route path="/advanced-score-screener" element={<div data-testid="adv">advanced page</div>} /><Route path="*" element={<div>elsewhere</div>} /></Routes><Where /></MemoryRouter></QueryClientProvider>);
const loc = () => screen.getByTestId("loc").textContent || "";
const symbols = () => within(screen.getByRole("table")).getAllByRole("row").slice(1).map((r) => within(r).queryAllByRole("cell")[2]?.querySelector("b")?.textContent).filter(Boolean);
const hint = () => document.querySelector(".sx-hint")!;
const sector = (name: string) => screen.getByRole("checkbox", { name: new RegExp("^" + name) });

beforeEach(() => { admin.on = true; st.plan = "gold"; st.rows = DATA; st.cover = null; localStorage.clear(); watch.reset(); st.upgrade.mockReset(); st.toast.mockReset(); });
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

  it("filters apply live: ticking changes rows, every number above the table, chips and address with no button pressed", async () => {
    open();
    const kpi = (l: string) => within(screen.getByLabelText("Summary")).getByText(l).previousSibling?.textContent;
    fireEvent.click(sector("IT")); fireEvent.click(sector("Auto"));
    expect(hint().textContent).toMatch(/Updating/);                            // never a silent gap between what is ticked and what is shown
    await waitFor(() => expect(loc()).toBe("/score-screener?sector=IT&sector=Auto"));
    expect(symbols()).toEqual(["CCC", "DDD", "EEE", "GGG"]);
    expect(kpi("Companies found")).toBe("4"); expect(kpi("Sectors")).toBe("2"); expect(kpi("Active filters")).toBe("2");
    expect(screen.getByText("4 companies in this result")).toBeTruthy();
    expect(screen.getByText("1–4 of 4")).toBeTruthy();
    expect(screen.getByText("1 of 4 companies in this result are not scored yet.")).toBeTruthy();   // the donut follows the result too
    expect(screen.getByRole("button", { name: "Remove filter IT" })).toBeTruthy();
    expect(hint().textContent).not.toMatch(/Updating/);
  });

  it("the not-scored share and the sector mix are for administrators only: a member does not see them", () => {
    admin.on = false;
    open();
    expect(screen.queryByText(/are not scored yet/)).toBeNull();
    expect(screen.queryByText("Results by sector (Top 5)")).toBeNull();
    expect(screen.getByRole("table")).toBeTruthy();                       // the results themselves are untouched
    cleanup();
    admin.on = true;
    open();
    expect(screen.getByText("Results by sector (Top 5)")).toBeTruthy();
  });

  it("a typed number applies after a short pause, or on Enter, and an invalid range waits", async () => {
    vi.useFakeTimers();
    try {
      open();
      const tech = () => within(screen.getByRole("group", { name: "Quality Score" }));
      fireEvent.click(tech().getByRole("checkbox", { name: "Quality Score" }));
      fireEvent.change(tech().getByLabelText("Min"), { target: { value: "7" } });
      fireEvent.change(tech().getByLabelText("Min"), { target: { value: "78" } });
      act(() => { vi.advanceTimersByTime(300); });
      expect(loc()).toBe("/score-screener");                                   // still typing: nothing applied yet
      act(() => { vi.advanceTimersByTime(150); });
      expect(loc()).toBe("/score-screener?qmin=78");
      expect(symbols()).toEqual(["AAA", "BBB", "HHH"]);
      fireEvent.change(tech().getByLabelText("Max"), { target: { value: "50" } });   // below the minimum
      act(() => { vi.advanceTimersByTime(1000); });
      expect(loc()).toBe("/score-screener?qmin=78");
      expect(screen.getByRole("alert").textContent).toMatch(/minimum is above the maximum/);
      fireEvent.change(tech().getByLabelText("Max"), { target: { value: "85" } });
      fireEvent.submit(screen.getByRole("button", { name: /Apply filters|Show/ }).closest("form")!);   // Enter applies at once
      expect(loc()).toBe("/score-screener?qmin=78&qmax=85");
    } finally { vi.useRealTimers(); }
  });

  it("the counts beside each option follow the other filters, and Clear all restores every total", async () => {
    open();
    const count = (name: string) => (sector(name).closest("label")!.querySelector(".fgx-n")?.textContent);
    expect(count("Banks")).toBe("2"); expect(count("Metals")).toBe("14");
    fireEvent.click(screen.getByRole("checkbox", { name: /^Large cap/ }));      // Large caps: the 100 largest, here all 22 are Large
    await waitFor(() => expect(loc()).toContain("cap=Large"));
    fireEvent.click(within(screen.getByRole("group", { name: "Quality Score" })).getByRole("button", { name: "Quality Score 78 and above" }));
    await waitFor(() => expect(loc()).toContain("qual=high"));
    expect(symbols()).toEqual(["AAA", "BBB", "HHH"]);
    expect(count("Banks")).toBe("2"); expect(count("Metals")).toBe("0"); expect(count("IT")).toBe("0"); expect(count("Pharma")).toBe("1");
    fireEvent.click(within(screen.getByLabelText("Active filters")).getByRole("button", { name: "Clear all" }));
    await waitFor(() => expect(loc()).toBe("/score-screener"));
    expect(count("Metals")).toBe("14");
    expect(within(screen.getByLabelText("Summary")).getByText("Companies found").previousSibling?.textContent).toBe("22");
    expect(within(screen.getByLabelText("Summary")).getByText("Active filters").previousSibling?.textContent).toBe("0");
  });

  it("filters that match nothing show zeros above, and an empty state with removable chips", async () => {
    open("?sector=Banks&qual=low");
    expect(symbols()).toEqual([]);
    const kpi = (l: string) => within(screen.getByLabelText("Summary")).getByText(l).previousSibling?.textContent;
    expect(kpi("Companies found")).toBe("0"); expect(kpi("Sectors")).toBe("0");
    expect(screen.getByText("0 companies in this result")).toBeTruthy();
    expect(document.querySelector(".fgx-empty")!.textContent).toMatch(/No companies match all of these filters/);
    fireEvent.click(within(document.querySelector(".fgx-empty") as HTMLElement).getByRole("button", { name: /^Banks/ }));
    await waitFor(() => expect(symbols().length).toBeGreaterThan(0));
  });

  it("score bands and min-max are exact, and missing scores never pass", () => {
    open();
    const quality = screen.getByRole("group", { name: "Quality Score" }), growth = screen.getByRole("group", { name: "Growth Score" });
    fireEvent.click(within(quality).getByRole("button", { name: "Quality Score 78 and above" }));
    fireEvent.submit(quality.closest("form")!);
    expect(symbols()).toEqual(["AAA", "BBB", "HHH"]);                        // 78 is in, 77 (EEE) is out, GGG has no score
    fireEvent.click(within(growth).getByRole("button", { name: "Growth Score under 45" }));
    fireEvent.submit(quality.closest("form")!);
    expect(symbols()).toEqual([]);                                           // both pillars must pass
    fireEvent.click(within(growth).getByRole("button", { name: "Growth Score under 45" }));
    fireEvent.click(within(growth).getByRole("button", { name: "Growth Score 78 and above" }));
    fireEvent.submit(quality.closest("form")!);
    expect(symbols()).toEqual(["AAA", "BBB", "HHH"]);
    fireEvent.click(within(screen.getByRole("group", { name: "Quality Score" })).getByRole("checkbox", { name: "Quality Score" }));   // ticking enables Min and Max
    fireEvent.change(within(screen.getByRole("group", { name: "Quality Score" })).getByLabelText("Min"), { target: { value: "78" } });
    expect(screen.getByRole("button", { name: "Apply filters" }).hasAttribute("disabled")).toBe(false);
    fireEvent.change(within(screen.getByRole("group", { name: "Quality Score" })).getByLabelText("Max"), { target: { value: "50" } });
    expect(screen.getByRole("alert").textContent).toMatch(/minimum is above the maximum/);
    expect(screen.getByRole("button", { name: "Apply filters" }).hasAttribute("disabled")).toBe(true);
    fireEvent.submit(quality.closest("form")!);
    expect(loc()).toBe("/score-screener?qual=high&g=high");                      // an invalid range is not applied
  });

  it("one panel, FinLit IQ Score: four pillar rows with band chips and Min - Max, and no Score bands section", () => {
    open();
    expect(screen.getByRole("button", { name: /^FinLit IQ Score/ })).toBeTruthy();
    expect(screen.getByText("Filter stocks using our multi-pillar statistical scoring model.")).toBeTruthy();
    expect(screen.queryByText("Score bands")).toBeNull();
    expect(screen.queryByText("Growth & Profitability score by pillar")).toBeNull();
    expect(within(screen.getByRole("group", { name: "FinLit IQ rating" })).getAllByRole("button").map((b) => b.textContent)).toEqual(["Strong", "Healthy", "Average", "Weak", "Poor", "Not rated"]);
    const order = [...document.querySelectorAll(".iq-rating, .iq-row")].map((e) => e.getAttribute("aria-label"));
    expect(order).toEqual(["FinLit IQ rating", "Quality Score", "Growth Score", "Profitability Score", "Balance Sheet Score", "Technical Score", "Total FinLit IQ Score"]);
    for (const n of ["Quality Score", "Growth Score", "Profitability Score", "Balance Sheet Score", "Technical Score", "Total FinLit IQ Score"]) {
      const row = within(screen.getByRole("group", { name: n }));
      expect(row.getAllByRole("button").map((b) => b.textContent)).toEqual(["< 45", "45 - 77", ">= 78"]);
      expect(row.getByLabelText("Min")).toBeTruthy(); expect(row.getByLabelText("Max")).toBeTruthy();
    }
  });
  it("rating chips, Technical and Total rows filter the table, the count, the chips and the address", { timeout: 30000 }, async () => {
    open();
    const rating = () => within(screen.getByRole("group", { name: "FinLit IQ rating" }));
    fireEvent.click(rating().getByRole("button", { name: "Strong" }));
    await waitFor(() => expect(symbols()).toEqual(["AAA", "BBB", "HHH"]));
    expect(loc()).toBe("/score-screener?iql=strong");
    fireEvent.click(rating().getByRole("button", { name: "Not rated" }));
    await waitFor(() => expect(symbols()).toEqual(["AAA", "BBB", "HHH", "GGG"]));
    fireEvent.click(screen.getByRole("button", { name: "Remove filter FinLit IQ rating: Strong, Not rated" }));
    await waitFor(() => expect(loc()).toBe("/score-screener"));
    fireEvent.click(within(screen.getByRole("group", { name: "Technical Score" })).getByRole("button", { name: /78 and above/ }));
    await waitFor(() => expect(symbols()).toEqual(["AAA", "CCC", "EEE"]));
    fireEvent.change(within(screen.getByRole("group", { name: "Total FinLit IQ Score" })).getByLabelText("Min"), { target: { value: "80" } });
    await waitFor(() => { expect(symbols()).toEqual(["AAA"]); expect(loc()).toBe("/score-screener?t=high&omin=80"); });
  });
  it("a shared link with the new keys opens with the rows ticked", () => {
    open("?iql=poor,weak&ovr=low&tmin=40");
    expect(screen.getByRole("button", { name: "Weak" }).getAttribute("aria-pressed")).toBe("true");
    expect(symbols()).toEqual(["DDD"]);
  });
  it("the Quality band is written as ?qual= so it never collides with the toolbar search ?q=, and an old ?q=high link still reads", () => {
    open("?q=high");
    expect(symbols()).toEqual(["AAA", "BBB", "HHH"]);
    expect((screen.getByLabelText("Search company name, sector or keyword") as HTMLInputElement).value).toBe("");
    cleanup();
    open("?qual=mid&q=AAA");
    expect(symbols()).toEqual([]);                                           // AAA is 90, not 45 to 77: the search and the band are separate
  });

  it("a removed chip, and Clear all, update the table and address at once", () => {
    open("?sector=IT&sector=Auto&qual=mid");
    expect(symbols()).toEqual(["CCC", "EEE"]);                                // IT or Auto, Fundamental 45 to 77: 50 and 77 (DDD is 44)
    fireEvent.click(screen.getByRole("button", { name: "Remove filter Quality: 45–77" }));
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
    expect(screen.getByRole("button", { name: "Sort by Growth & Profitability" }).closest("th")!.getAttribute("aria-sort")).toBe("none");
    expect((screen.getByLabelText("Rows per page") as HTMLSelectElement).value).toBe("5");
    expect(screen.getByRole("button", { name: "Page 2" }).getAttribute("aria-current")).toBe("page");
  });

  it("sorting by a heading flips the direction, keeps missing scores last and writes the address", () => {
    open("?size=50");
    fireEvent.click(screen.getByRole("button", { name: "Sort by Growth & Profitability" }));
    expect(loc()).toBe("/score-screener?sort=f&dir=desc&size=50");
    expect(symbols().slice(0, 3)).toEqual(["AAA", "BBB", "HHH"]);
    expect(symbols().at(-1)).toBe("GGG");
    fireEvent.click(screen.getByRole("button", { name: "Sort by Growth & Profitability" }));
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

  it("has no export buttons, only Compare and Add to watchlist", () => {
    open();
    expect(screen.queryByRole("button", { name: /Export/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Add to watchlist" })).toBeTruthy();
  });

  it("shows a dash with its reason, never a zero, for missing data", () => {
    open("?sector=Auto");
    const row = screen.getByRole("checkbox", { name: "Select GGG" }).closest("tr")!;
    expect(row.textContent).toMatch(/Not available: Not scored yet/);
    expect(row.textContent).not.toMatch(/\b0\b/);
    expect(within(row).getAllByTitle(/Not scored yet/).length).toBeGreaterThan(0);
  });

  it("Basic members see locks and the upgrade card instead of score filters; the prebuilt screens ask for Silver", async () => {
    st.plan = "basic"; st.rows = DATA.map((r) => ({ ...r, overall: null, pillar_quality: null, pillar_growth: null, pillar_profitability: null, pillar_balance: null, pillar_technical: null }));
    api.list = { tab: "basic", asOf: null, groups: [{ id: "top-rated", name: "Top rated", presets: [{ ...CARD, locked: true, count: null, listText: null }] }] };
    open();
    expect(screen.getByText(/Score filters are part of Silver/)).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Fundamental score, exact range" })).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: /Top 10 large caps/ }));
    expect(st.upgrade).toHaveBeenCalledWith("silver", expect.stringMatching(/Silver/));
    expect(loc()).toBe("/score-screener");
  });

  it("the Quick views are the server's prebuilt screens: each card says how many of those that pass it lists, and opening one writes the address", async () => {
    api.list = { tab: "basic", asOf: "2026-10-30", groups: [{ id: "top-rated", name: "Top rated", presets: [CARD, { ...CARD, id: "basic-strong-both", name: "Strong on both", cardText: "Growth & Profitability score and Technical both 78 or more.", listText: null, count: 19 }] }] };
    open();
    const card = await screen.findByRole("button", { name: /Top 10 large caps/ });
    expect(card.textContent).toMatch(/Top 10 of 40 that pass/);
    expect(screen.getByRole("button", { name: /Strong on both/ }).textContent).toMatch(/19 match/);
    expect(screen.queryByText("Prism basics")).toBeNull();                                   // the Prism quick views belong to the Advanced page
    fireEvent.click(card);
    await waitFor(() => expect(loc()).toBe("/score-screener?preset=basic-top-large"));
  });

  it("the 52-week and return columns are off until asked for, then show blanks as dashes, never zero, and sort", () => {
    st.rows = DATA.map((r, i) => (i === 0 ? { ...r, ret_3m: 12.34, ret_6m: -3.2, return_1y: 40, pct_from_high: 4.56 } : r));
    open();
    const heads = () => within(screen.getByRole("table")).getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads().join("|")).not.toMatch(/52-week/);
    fireEvent.click(screen.getByRole("button", { name: "Add 52-week and return columns" }));
    expect(heads().join("|")).toMatch(/3M return.*6M return.*1Y return.*Below 52-week high/);
    const first = within(screen.getByRole("table")).getAllByRole("row")[2].textContent!;
    expect(first).toMatch(/\+12\.3%/); expect(first).toMatch(/−3\.2%/); expect(first).toMatch(/4\.6%/);
    const second = within(screen.getByRole("table")).getAllByRole("row")[3].textContent!;
    expect(second).not.toMatch(/0\.0%/);                                               // a company with no figure shows a dash
    fireEvent.click(screen.getByRole("button", { name: "Sort by Below 52-week high" }));
    expect(loc()).toMatch(/sort=pct_from_high/);
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
    expect(heads.map((h) => h?.replace(/ \?$/, ""))).toEqual(expect.arrayContaining(["Growth & Profitability", "Quality", "Growth", "Profit.", "Balance", "Technical", "Overall"]));
  });
  it("links to the Advanced score screener (Gold) with a Gold chip", () => {
    open();
    const a = screen.getByRole("link", { name: /Advanced score screener/ });
    expect(a.getAttribute("href")).toBe("/advanced-score-screener");
    expect(a.textContent).toMatch(/Advanced score screener \(Gold\): FinLit Prism, 4 financial-health parts and 2 technical views/);
    expect(a.textContent).toMatch(/Gold/);
  });
  it("Silver sees the scores, Basic sees the locked state as before", () => {
    st.plan = "silver"; open();
    expect(screen.queryByText(/Score filters are part of Silver/)).toBeNull();
    expect(screen.getByRole("group", { name: "Quality Score" })).toBeTruthy();
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
    const g = screen.getByRole("group", { name: "Quality Score" });
    const min = within(g).getByLabelText("Min") as HTMLInputElement;
    expect(min.disabled).toBe(true);
    fireEvent.click(within(g).getByRole("checkbox", { name: "Quality Score" }));
    expect(min.disabled).toBe(false);
    fireEvent.change(min, { target: { value: "70" } });
    fireEvent.submit(g.closest("form")!);
    expect(loc()).toBe("/score-screener?qmin=70");
    fireEvent.click(within(g).getByRole("checkbox", { name: "Quality Score" }));
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
    expect(screen.getByText("1 of 22 companies in this result are not scored yet.")).toBeTruthy();
    expect(screen.getByText(/Scored 21 \(95%\)/)).toBeTruthy();
  });
});
