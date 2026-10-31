// @vitest-environment jsdom
// The "Price position" half of the results filter card and the two table columns: address state, labels, result lines, highlight, reset, plan gate, CSV.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { QParams, QResp, QRow } from "../lib/qresults";
import { BAND_EDGES, CSV_HEAD, DEFAULT_PRICE, PRICE_PRESETS, bandLabel, bandOf, csvOf, growthFromParams, growthToParams, priceFromParams, priceHit, priceQuery, priceToParams } from "../lib/qresults";

const st = vi.hoisted(() => ({ plan: "silver" as "basic" | "silver", params: [] as unknown[], resp: null as unknown, upgrade: vi.fn(), toast: vi.fn() }));
vi.mock("../lib/qresults", async (orig) => ({
  ...(await orig<typeof import("../lib/qresults")>()),
  useQuarterResults: (p: unknown) => { st.params.push(p); return { data: st.resp, error: null, isError: false, isLoading: false, isFetching: false }; },
}));
vi.mock("../lib/ui", () => ({ useUI: () => ({ plan: st.plan, upgrade: st.upgrade, toast: st.toast }) }));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ user: null }) }));
vi.mock("../lib/title", () => ({ useDocTitle: () => undefined }));
vi.mock("../components/ChartHelp", () => ({ ChartHelp: () => null }));
import { QuarterResultsPage } from "./QuarterResults";

const summary = { companies: 10, declared: 10, due: 0, awaiting: 0, withNumbers: 8, flagged: 0, medianRevenueYoY: 1, medianProfitYoY: 1, profitUpShare: 50, marginUpShare: 50, nRevenue: 8, nProfit: 8, nMargin: 8 };
const mk = (over: Partial<QRow> = {}): QRow => ({ date: "2026-10-14", symbol: "AAA", name: "Aaa Ltd", sector: "IT", marketCap: 1, cap: "Large", indices: [], confirmed: true, periodEnd: "2026-09-30", loadedPeriodEnd: null, status: "declared", awaiting: false,
  hasNumbers: true, locked: false, revenue: 100, revenueYoY: 12, revenueQoQ: -3, operatingProfit: 20, opYoY: 5, opQoQ: 1, opYoYWhy: null, opQoQWhy: null, opm: 20, netProfit: 10, profitYoY: 30, profitQoQ: 4, npm: 10, npmChange: 0, eps: 1, gap: 0,
  flagged: false, loss: false, price: 87.6, high52: 100, low52: 60, ath: 120, athDate: "2026-01-12", below52: 12.4, belowAth: 27, above52Low: 46, stale52: false, staleAth: false, ...over } as QRow);
const resp = (over: Partial<QResp> = {}): QResp => ({
  plan: "silver", locked: false, today: "2026-10-27", quarter: { key: "2026-09", label: "Jul to Sep 2026", fiscal: "Q2 FY27", periodEnd: "2026-09-30", from: "2026-10-01", to: "2026-12-31" }, quarters: [],
  total: 5, offset: 0, limit: 50, summary, totals: summary, rows: [], days: [], facets: { sectors: [], indices: [] }, growth: null, price: null, priceStrip: null,
  distribution: { total: 5, sectors: [], caps: [] }, ...over,
});
const Where = () => { const l = useLocation(); return <output data-testid="loc">{l.pathname + l.search}</output>; };
const open = (qs = "") => render(<MemoryRouter initialEntries={["/results/quarter" + qs]}><Routes><Route path="/results/quarter" element={<QuarterResultsPage />} /></Routes><Where /></MemoryRouter>);
const loc = () => decodeURIComponent(screen.getByTestId("loc").textContent || "");
const lastParams = () => st.params[st.params.length - 1] as QParams;
const section = (n: string) => within(screen.getByRole("group", { name: new RegExp(n) }));

beforeEach(() => { st.plan = "silver"; st.params = []; st.resp = resp(); st.upgrade.mockClear(); vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(cleanup);

describe("price position state in the address", () => {
  it("is off by default, round-trips bands, typed ranges and Match any, and ignores unknown values", () => {
    expect(priceFromParams(new URLSearchParams(""))).toEqual(DEFAULT_PRICE);
    expect(priceToParams(new URLSearchParams("quarter=2026-09"), DEFAULT_PRICE).toString()).toBe("quarter=2026-09");
    const sp = new URLSearchParams("quarter=2026-09&p52=2&pAthMin=40&pJoin=or&zzz=1");
    const p = priceFromParams(sp);
    expect(p).toEqual({ w52: { band: "2", min: "", max: "" }, ath: { band: "", min: "40", max: "" }, join: "or" });
    const out = priceToParams(sp, p);
    expect(out.get("p52")).toBe("2"); expect(out.get("pAthMin")).toBe("40"); expect(out.get("pJoin")).toBe("or"); expect(out.get("zzz")).toBe("1"); expect(out.get("quarter")).toBe("2026-09");
    expect(priceQuery(p)).toEqual({ p52: "2", pAthMin: "40", pJoin: "or" });
    for (const bad of ["p52=8", "p52=x", "p52=-1", "pAth=1.5", "pJoin=xor", "p52min=abc", "p52max=101"]) expect(priceQuery(priceFromParams(new URLSearchParams(bad))), bad).toEqual({});
  });
  it("leaves the growth parameters alone, and old links without price parameters open unchanged", () => {
    const sp = new URLSearchParams("revQoQOp=%3E%3D&revQoQValue=5&join=or");
    expect(priceFromParams(sp)).toEqual(DEFAULT_PRICE);
    const both = priceToParams(growthToParams(new URLSearchParams(), growthFromParams(sp)), priceFromParams(new URLSearchParams("p52=0")));
    expect(both.get("join")).toBe("or"); expect(both.get("pJoin")).toBeNull(); expect(both.get("p52")).toBe("0"); expect(growthFromParams(both).join).toBe("or");
  });
});

describe("bands", () => {
  it("are labelled exactly as the mockup and are half-open", () => {
    expect(BAND_EDGES.map((_, i) => bandLabel(i, "w52"))).toEqual(["0–5% below 52-week high", "5–10% below 52-week high", "10–15% below 52-week high", "15–20% below 52-week high",
      "20–30% below 52-week high", "30–40% below 52-week high", "40–50% below 52-week high", "Above 50% below 52-week high"]);
    expect(bandLabel(0, "ath")).toBe("0–5% below all-time high"); expect(bandLabel(7, "ath")).toBe("Above 50% below all-time high");
    expect([0, 4.9, 5, 9.9, 10, 15, 20, 30, 40, 49.9, 50, 100].map(bandOf)).toEqual([0, 0, 1, 1, 2, 3, 4, 5, 6, 6, 7, 7]);
  });
  it("hit rule: bands half-open, typed range closed, missing figure never", () => {
    const at = (v: number | null) => mk({ below52: v });
    const b = (n: string) => ({ band: n, min: "", max: "" });
    expect([4.9, 5, 5.1].map((v) => priceHit(at(v), "w52", b("0")))).toEqual([true, false, false]);
    expect([4.9, 5, 9.9, 10].map((v) => priceHit(at(v), "w52", b("1")))).toEqual([false, true, true, false]);
    expect(priceHit(at(50), "w52", b("7"))).toBe(true); expect(priceHit(at(null), "w52", b("0"))).toBe(false);
    expect([39.9, 40, 80].map((v) => priceHit(at(v), "w52", { band: "", min: "40", max: "" }))).toEqual([false, true, true]);
    expect(priceHit(at(20), "w52", { band: "", min: "10", max: "20" })).toBe(true);
    expect(priceHit(at(5), "w52", DEFAULT_PRICE.w52)).toBe(false);
  });
});

describe("the combined card", () => {
  it("has the new title, the one-line rule, the New filter badge, both sections with Any as the default and the mockup wording", () => {
    open();
    expect(screen.getByRole("heading", { name: "Filter companies by growth and price position" })).toBeTruthy();
    expect(screen.getByText("Growth filters and price-position filters apply together.")).toBeTruthy();
    expect(screen.getByText("New filter")).toBeTruthy();
    expect(screen.getByText("Identify companies based on how far their current market price is below their highest recorded price.")).toBeTruthy();
    expect(screen.getByText("1. Distance from 52-week high")).toBeTruthy(); expect(screen.getByText("2. Distance from all-time high")).toBeTruthy();
    expect(screen.getByText("Current price compared with the highest price in the last 52 weeks.")).toBeTruthy();
    expect(screen.getByText("Current price compared with the highest price in the company's available historical price data.")).toBeTruthy();
    for (const [n, word] of [["1\\.", "52-week high"], ["2\\.", "all-time high"]]) {
      const s = section(n);
      expect(s.getAllByRole("radio")).toHaveLength(9);
      expect((s.getByRole("radio", { name: "Any" }) as HTMLInputElement).checked).toBe(true);
      expect(s.getByRole("radio", { name: `0–5% below ${word}` })).toBeTruthy(); expect(s.getByRole("radio", { name: `Above 50% below ${word}` })).toBeTruthy();
    }
    expect(screen.getByText("Filter logic")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Match all price-position conditions" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Companies must satisfy both selected price-position conditions.")).toBeTruthy();
    expect(screen.getByText("No growth or price-position filter is on, so every company in the table is shown.")).toBeTruthy();
    expect(lastParams().p52).toBeUndefined(); expect(lastParams().pAth).toBeUndefined();   // starts unfiltered
  });
  it("picks a band, asks the server, keeps it in the address, switches Match any and clears a typed range", () => {
    open("?quarter=2026-09");
    fireEvent.click(screen.getByRole("radio", { name: "10–15% below 52-week high" }));
    expect(loc()).toContain("p52=2"); expect(lastParams()).toMatchObject({ quarter: "2026-09", p52: "2", pJoin: "and" });
    fireEvent.change(screen.getByLabelText("Distance from all-time high minimum in per cent"), { target: { value: "40" } });
    expect(loc()).toContain("pAthMin=40"); expect(lastParams()).toMatchObject({ pAthMin: "40", p52: "2" });
    fireEvent.click(screen.getByRole("button", { name: "Match any price-position condition" }));
    expect(loc()).toContain("pJoin=or"); expect(screen.getByText("Companies that satisfy either selected condition are shown.")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "5–10% below all-time high" }));
    expect(loc()).toContain("pAth=1"); expect(loc()).not.toContain("pAthMin");
    fireEvent.change(screen.getByLabelText("Distance from 52-week high maximum in per cent"), { target: { value: "abc" } });
    expect(screen.getAllByRole("alert").some((a) => /0 to 100/.test(a.textContent || ""))).toBe(true);
    expect(loc()).not.toContain("p52max");
  });
  it("one Reset filters clears both blocks and keeps the quarter; quick fills set both blocks in one go", () => {
    open("?quarter=2026-09");
    fireEvent.click(screen.getByRole("button", { name: "Growth and near 52-week high" }));
    expect(lastParams()).toMatchObject({ p52: "0", revQoQValue: "0", npYoYValue: "0" });
    expect(screen.getByRole("button", { name: "Growth and near 52-week high" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Deep below the all-time high" }));
    expect(lastParams().pAthMin).toBe("40"); expect(lastParams().p52).toBeUndefined(); expect(lastParams().revQoQValue).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(loc()).toBe("/results/quarter?quarter=2026-09");
    expect((screen.getByRole("button", { name: "Reset filters" }) as HTMLButtonElement).disabled).toBe(true);
    expect(PRICE_PRESETS.map((p) => p.label)).toEqual(["Near the 52-week high", "Deep below the all-time high", "Growth and near 52-week high"]);
  });
  it("an old growth-only link is unaffected: price off, the growth filter still applied", () => {
    open("?revQoQOp=%3E%3D&revQoQValue=5&join=or");
    expect(lastParams()).toMatchObject({ revQoQValue: "5", join: "or" }); expect(lastParams().p52).toBeUndefined(); expect(lastParams().pJoin).toBeUndefined();
    expect((screen.getAllByRole("radio", { name: "Any" })[0] as HTMLInputElement).checked).toBe(true);
  });
  it("sends a Basic visitor to the upgrade prompt and puts nothing in the address", () => {
    st.plan = "basic";
    open();
    fireEvent.click(screen.getByRole("radio", { name: "0–5% below 52-week high" }));
    expect(st.upgrade).toHaveBeenCalled(); expect(loc()).toBe("/results/quarter"); expect(lastParams().p52).toBeUndefined();
  });
  it("uses only descriptive wording, never advice", () => {
    open();
    const text = (document.querySelector(".qg") as HTMLElement).textContent || "";
    expect(text).not.toMatch(/\b(buy|sell|hold|target|recommend|should|outperform|undervalued|multibagger|dip|bargain|cheap)\b/i);
    expect(text).toMatch(/Information only, not advice/);
    expect(text).toMatch(/intraday high/); expect(text).toMatch(/highest close/);
  });
});

describe("the result lines", () => {
  const price = { join: "and" as const, k: 2, companies: 100, withFigures: 90, matching: 12, conditions: [
    { key: "w52" as const, band: 0, min: 0, max: 5, met: 20, missing: 4 }, { key: "ath" as const, band: 6, min: 40, max: 50, met: 15, missing: 10 }] };
  it("says N of M, who cannot match per condition, and the combined count with the growth filter", () => {
    st.resp = resp({ price: { ...price, combined: 7 }, growth: { join: "and", k: 1, withFigures: 80, matching: 30, metAll: 30, metSome: 0, metNone: 50, conditions: [{ metric: "revenue", period: "qoq", op: ">=", value: 1, met: 30, missing: 2 }], combined: 7 } });
    open("?p52=0&pAth=6&revQoQValue=1");
    const state = document.querySelector(".qg-state") as HTMLElement;
    expect(state.textContent).toContain("12 of 90 companies with price-position figures match both price-position conditions.");
    expect(state.textContent).toContain("4 companies have no 52-week high figure and cannot match it.");
    expect(state.textContent).toContain("10 companies have no all-time high figure and cannot match it.");
    expect(state.textContent).toContain("30 of 80 companies with figures match the condition.");
    expect(state.textContent).toContain("7 companies meet both the growth and the price-position filters.");
  });
  it("uses the singular for one condition and either-of for Match any", () => {
    st.resp = resp({ price: { ...price, k: 1, matching: 1, conditions: [{ key: "w52", band: 0, min: 0, max: 5, met: 1, missing: 1 }] } });
    open("?p52=0");
    expect((document.querySelector(".qg-state") as HTMLElement).textContent).toContain("1 company has no 52-week high figure and cannot match it.");
    expect((document.querySelector(".qg-state") as HTMLElement).textContent).toContain("match the price-position condition.");
    st.resp = resp({ price: { ...price, join: "or" } });
    cleanup(); open("?p52=0&pAth=6&pJoin=or");
    expect((document.querySelector(".qg-state") as HTMLElement).textContent).toContain("match either price-position condition.");
  });
});

describe("the table columns", () => {
  it("are always there: distance, band, a dash with the reason when a high is not held, At high, and a stale marker", () => {
    st.resp = resp({ total: 4, rows: [mk(), mk({ symbol: "BBB", below52: 0, belowAth: 0 }), mk({ symbol: "CCC", below52: 0, stale52: true, high52: 90, price: 95 }), mk({ symbol: "DDD", below52: null, belowAth: null, high52: null, ath: null })] });
    open();
    expect(screen.getByRole("button", { name: /Below 52-week high/ })).toBeTruthy(); expect(screen.getByRole("button", { name: /Below all-time high/ })).toBeTruthy();
    const rows = Array.from(document.querySelectorAll("tr.qr-r"));
    const cells = (i: number) => Array.from(rows[i].querySelectorAll("td.qr-pp")).map((td) => td.querySelector(".qr-ppv b, abbr")?.textContent);
    expect(cells(0)).toEqual(["12.4%", "27.0%"]); expect(rows[0].querySelector("td.qr-pp small")!.textContent).toBe("10–15%");
    expect(cells(1)).toEqual(["At 52-week high", "At all-time high"]);
    expect(cells(2)[0]).toBe("At 52-week high*"); expect(rows[2].querySelector("td.qr-pp .qr-ppv")!.getAttribute("title")).toMatch(/above the stored 52-week high/);
    expect(cells(3)).toEqual(["—", "—"]); expect(rows[3].querySelector("abbr")!.getAttribute("title")).toMatch(/No 52-week high is held/);
    expect(rows[0].querySelectorAll("td.qr-pp .qr-ppv")[1].getAttribute("title")).toMatch(/highest close, week of 12 Jan 2026/);
  });
  it("highlights the cells that met the price filter, for sighted and screen reader users", () => {
    st.resp = resp({ total: 1, rows: [mk()] });
    open("?p52=2&pAth=0");
    const hits = Array.from(document.querySelectorAll("td.qr-hit")).map((td) => td.textContent);
    expect(hits).toHaveLength(1); expect(hits[0]).toContain("12.4%"); expect(hits[0]).toContain("meets your price-position filter");
  });
  it("sorts both ways from the header and shows the line above the table", () => {
    st.resp = resp({ total: 1, rows: [mk()], priceStrip: { companies: 157, have52: 150, near52: 34, haveAth: 140, nearAth: 12 } });
    open();
    expect(screen.getByText(/companies are within 5% of their 52-week high/).textContent).toContain("34 of 150 companies are within 5% of their 52-week high; 12 of 140 are within 5% of their all-time high.");
    fireEvent.click(screen.getByRole("button", { name: /Below 52-week high/ }));
    expect(lastParams()).toMatchObject({ sort: "below52", dir: "asc" });
    fireEvent.click(screen.getByRole("button", { name: /Below 52-week high/ }));
    expect(lastParams()).toMatchObject({ sort: "below52", dir: "desc" });
  });
  it("Basic sees a dash and the Silver message, not a figure", () => {
    st.plan = "basic";
    st.resp = resp({ locked: true, total: 1, rows: [mk({ below52: null, belowAth: null, price: null, high52: null, ath: null, hasNumbers: true, locked: true })] });
    open();
    expect(document.querySelector("td.qr-pp abbr")!.getAttribute("title")).toMatch(/Silver/);
  });
});

describe("the CSV", () => {
  it("carries the price, both highs, the low, the dates and both distances", () => {
    const head = CSV_HEAD.slice(-9);
    expect(head).toEqual(["Price (Rs)", "52-week high (Rs)", "52-week low (Rs)", "Below 52-week high %", "Above 52-week low %", "All-time high (Rs)", "All-time high date", "Below all-time high %", "Price above a stored high"]);
    const lines = csvOf([mk(), mk({ symbol: "ZZZ", stale52: true })], "Q2").trim().split("\r\n");
    expect(lines[2].endsWith(",87.6,100,60,12.4,46,120,2026-01-12,27,")).toBe(true);
    expect(lines[3].endsWith(",52-week high")).toBe(true);
  });
});
