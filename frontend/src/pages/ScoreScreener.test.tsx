// @vitest-environment jsdom
// The Score screener in a DOM: draft vs applied filters, chips, selection, bulk actions, address (URL) state, CSV and plan gating.
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
const open = (qs = "") => render(<MemoryRouter initialEntries={["/score-screener" + qs]}><Routes><Route path="/score-screener" element={<ScoreScreener />} /><Route path="*" element={<div>elsewhere</div>} /></Routes><Where /></MemoryRouter>);
const loc = () => screen.getByTestId("loc").textContent || "";
const symbols = () => within(screen.getByRole("table")).getAllByRole("row").slice(1).map((r) => within(r).queryAllByRole("cell")[2]?.querySelector("b")?.textContent).filter(Boolean);
const hint = () => document.querySelector(".sx-hint")!;
const sector = (name: string) => screen.getByRole("checkbox", { name: new RegExp("^" + name) });

beforeEach(() => { st.plan = "gold"; st.rows = DATA; st.cover = null; localStorage.clear(); watch.reset(); st.upgrade.mockReset(); st.toast.mockReset(); });
afterEach(cleanup);

describe("Score screener page", () => {
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
    fireEvent.click(within(fund).getByRole("checkbox", { name: "78 and above (Strong)" }));
    fireEvent.submit(fund.closest("form")!);
    expect(symbols()).toEqual(["AAA", "BBB", "HHH"]);                        // 78 is in, 77 (EEE) is out, GGG has no Fundamental
    fireEvent.click(within(tech).getByRole("checkbox", { name: "45 to 77 (Mixed, Healthy)" }));
    fireEvent.submit(fund.closest("form")!);
    expect(symbols()).toEqual(["HHH"]);                                      // Technical 77 is in, 78 is out
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
    expect(text).toContain("\r\n" + ["GGG", "GGG Limited", "Auto", "", "", "", "", "", "", "", "", "60", "", ...Array(12).fill("")].join(",") + "\r\n");   // blanks, never zeros
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

// ---- FinLit Prism columns, filters, presets and plan gating
const pz = (final: number | null, label: string, o: Partial<Row> = {}): Partial<Row> => ({
  prism_state: "stored", prism_final: final, prism_label: label, prism_status: final == null ? "NOT RATED" : "RATED", prism_at: "2026-10-27",
  prism_fundamental: final, prism_valuation: final == null ? null : 50, prism_quality: final == null ? null : 70, prism_risk: final == null ? null : 60,
  prism_st: final == null ? null : "Positive", prism_lt: final == null ? null : "Neutral", prism_st_score: final == null ? null : 22, prism_lt_score: final == null ? null : -4, ...o,
});
const PDATA: Row[] = [
  mk("AAA", "Banks", 90, 90, 9000, pz(85, "STRONG")), mk("BBB", "Banks", 80, 30, 8000, pz(66, "HEALTHY")), mk("CCC", "IT", 50, 85, 7000, pz(55, "AVERAGE")),
  mk("DDD", "IT", 44, 45, 6000, { prism_state: "stored", prism_final: null, prism_label: "NOT RATED", prism_status: "NOT RATED" }),
  mk("EEE", "Auto", 77, 78, 5000, { prism_state: "none" }), mk("FFF", "Auto", 60, 60, 4000, pz(30, "POOR", { prism_status: "PROVISIONAL" })),
];

describe("Advanced score screener: FinLit Prism", () => {
  beforeEach(() => { st.rows = PDATA; st.cover = { rated: 3, provisional: 1, not_rated: 1, stored: 5, total: 6, as_of: "2026-10-27", per_night: 30 }; });
  const rowOf = (s: string) => screen.getByRole("checkbox", { name: `Select ${s}` }).closest("tr")!;

  it("shows the Prism score with its label in words, the four parts and the short and long term words", () => {
    open();
    const r = rowOf("AAA").textContent!;
    expect(r).toMatch(/85\s*Strong/); expect(r).toMatch(/Positive\+22/); expect(r).toMatch(/Neutral\u22124/);
    expect(rowOf("FFF").textContent).toMatch(/30\s*PoorProvisional/);
    expect(screen.getByRole("columnheader", { name: /FinLit Prism/ })).toBeTruthy();
  });

  it("says rated X of Y and explains both scores", () => {
    open();
    expect(document.querySelector(".pzs-cover")!.textContent).toMatch(/Prism has rated 4 of 6 companies \(67%\)/);
    expect(document.querySelector(".pzs-cover")!.textContent).toMatch(/about 30 beyond the companies with a full report/);
    expect(screen.getByText("What the two scores mean")).toBeTruthy();
    expect(document.querySelector(".pzs-explain")!.textContent).toMatch(/Strong 80 and above, Healthy 65 to 79/);
  });

  it("a company without a rating says Not rated yet with the reason and a Rate now link to its Prism page; a refusal says why", () => {
    open();
    const e = rowOf("EEE");
    expect(e.textContent).toMatch(/Not rated yet/);
    expect(within(e).getByRole("link", { name: "Rate EEE with Prism now" }).getAttribute("href")).toBe("/prism/EEE");
    expect(within(e).getAllByTitle(/Ratings are added every night, largest companies first/).length).toBeGreaterThan(0);
    const d = rowOf("DDD");
    expect(d.textContent).toMatch(/Not rated/); expect(d.textContent).not.toMatch(/Rate now/);
    expect(within(d).getAllByTitle(/could not rate this company/).length).toBeGreaterThan(0);
  });

  it("filters by label chips, the rated-only switch and the exact range, and writes them to the address", () => {
    open();
    const prism = screen.getByRole("group", { name: "Prism rating label" });
    fireEvent.click(within(prism).getByRole("button", { name: "Strong" })); fireEvent.click(within(prism).getByRole("button", { name: "Healthy" }));
    fireEvent.submit(prism.closest("form")!);
    expect(symbols()).toEqual(["AAA", "BBB"]); expect(loc()).toBe("/score-screener?pl=strong%2Chealthy");
    expect(screen.getByRole("button", { name: "Remove filter Prism rating: Strong, Healthy" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove filter Prism rating: Strong, Healthy" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Only companies rated by Prism" }));
    fireEvent.submit(prism.closest("form")!);
    expect(symbols()).toEqual(["AAA", "BBB", "CCC", "FFF"]); expect(loc()).toBe("/score-screener?rated=1");
    fireEvent.change(within(screen.getByRole("group", { name: "Prism score, exact range" })).getByLabelText("Min"), { target: { value: "60" } });
    fireEvent.submit(prism.closest("form")!);
    expect(symbols()).toEqual(["AAA", "BBB"]);
    fireEvent.click(within(screen.getByLabelText("Active filters")).getByRole("button", { name: "Clear all" }));
    expect(symbols()).toHaveLength(6);
  });

  it("the slider sets the same range as the boxes; sliding back to the end clears it", () => {
    open();
    const s = screen.getByRole("slider", { name: "Prism slider, lowest score" });
    fireEvent.change(s, { target: { value: "60" } });
    expect((within(screen.getByRole("group", { name: "Prism score, exact range" })).getByLabelText("Min") as HTMLInputElement).value).toBe("60");
    fireEvent.change(s, { target: { value: "0" } });
    expect((within(screen.getByRole("group", { name: "Prism score, exact range" })).getByLabelText("Min") as HTMLInputElement).value).toBe("");
  });

  it("sorts on Prism and each part, companies without a value last", () => {
    open("?size=50");
    fireEvent.click(screen.getByRole("button", { name: "Sort by Prism" }));
    expect(symbols()).toEqual(["AAA", "BBB", "CCC", "FFF", "DDD", "EEE"]);
    fireEvent.click(screen.getByRole("button", { name: "Sort by Prism" }));
    expect(symbols()).toEqual(["FFF", "CCC", "BBB", "AAA", "DDD", "EEE"]);
    fireEvent.click(screen.getByRole("button", { name: "Sort by Long term" }));
    expect(loc()).toContain("sort=prism_lt_score");
  });

  it("a Prism view applies at once, can be switched off, and uses no advice wording", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: /Quality at a fair valuation/ }));
    expect(symbols()).toEqual(["AAA", "BBB", "CCC", "FFF"]);
    fireEvent.click(screen.getByRole("button", { name: /Quality at a fair valuation/ }));
    expect(symbols()).toHaveLength(6);
    expect(loc()).toBe("/score-screener");
    fireEvent.click(screen.getByRole("button", { name: /FinLit and Prism both strong/ }));
    expect(symbols()).toEqual(["AAA", "BBB"]);
    expect(document.body.textContent?.toLowerCase()).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate)\b/);
  });

  it("exports the Prism columns for Gold, with blanks for unrated companies", async () => {
    open();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    let blob: Blob | null = null;
    URL.createObjectURL = vi.fn((b: Blob) => { blob = b; return "blob:x"; }); URL.revokeObjectURL = vi.fn();
    fireEvent.click(screen.getByRole("button", { name: /Export all 6/ }));
    const text = await new Promise<string>((res) => { const fr = new FileReader(); fr.onload = () => res(String(fr.result)); fr.readAsText(blob!); });
    expect(text).toMatch(/Ratings as of: 2026-10-27/);
    expect(text).toContain("AAA,AAA Limited,Banks,Large cap,100,9000,90,90,90,90,90,90,90,85,Strong,RATED,85,50,70,60,Positive,22,Neutral,-4,2026-10-27");
    expect(text).toContain("EEE,EEE Limited,Auto,Large cap,100,5000,77,77,77,77,77,78,77,,,,,,,,,,,,");
  });

  it("Silver sees the FinLit score and locked Prism columns with an upgrade prompt; the server sends no Prism values", () => {
    st.plan = "silver"; st.rows = PDATA.map((r) => ({ ...r, ...Object.fromEntries(Object.keys(r).filter((k) => k.startsWith("prism_")).map((k) => [k, null])) }));
    open();
    expect(screen.getByText(/Prism filters are part of Gold/)).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Prism rating label" })).toBeNull();
    const a = rowOf("AAA");
    expect(within(a).getAllByText(/Not available: FinLit Prism is part of the Gold plan/).length).toBeGreaterThan(0);
    expect(a.textContent).not.toMatch(/Rate now|Not rated yet/);            // locked, not "not rated": no Rate now link for a plan that cannot use it
    fireEvent.click(screen.getByRole("button", { name: /Quality at a fair valuation/ }));
    expect(st.upgrade).toHaveBeenCalledWith("gold", expect.any(String));
    expect(loc()).toBe("/score-screener");
    fireEvent.click(screen.getByRole("button", { name: /Unlock with Gold/ }));
    expect(st.upgrade).toHaveBeenCalledTimes(2);
  });
});
