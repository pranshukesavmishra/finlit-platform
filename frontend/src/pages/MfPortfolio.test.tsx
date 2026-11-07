// @vitest-environment jsdom
// MF portfolio: the category card above the funds table. The categories and the pie chart are for reading only (task #8): no tick boxes,
// no "Select All", nothing to click except the group tabs.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Holding, MfPortfolio } from "../lib/mfPortfolio";

const st = vi.hoisted(() => ({ data: null as unknown }));
const mutation = () => ({ mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false, isError: false, error: null, reset: vi.fn() });
vi.mock("../lib/mfPortfolio", async (orig) => ({
  ...(await orig<typeof import("../lib/mfPortfolio")>()),
  useMfPortfolio: () => ({ data: st.data, isPending: false, isError: false, error: null, refetch: () => {} }),
  useMfWrites: () => new Proxy({}, { get: () => mutation() }),
}));
vi.mock("../lib/ui", () => ({ useUI: () => ({ toast: vi.fn(), plan: "gold", upgrade: vi.fn(), has: () => true }), TIER: { basic: { n: "Basic", ic: "sprout", tc: "--t-basic" }, silver: { n: "Silver", ic: "medal", tc: "--t-silver" }, gold: { n: "Gold", ic: "crown", tc: "--t-gold" } } }));
vi.mock("../lib/title", () => ({ useDocTitle: () => undefined }));
import { MfPortfolioPage } from "./MfPortfolio";

const H = (id: string, name: string, category: string, categoryLabel: string, code: number): Holding => ({
  id, code, folio: "", units: 10, lots: [], name, amc: "A", plan: "Direct", option: "Growth", category, categoryLabel, active: true,
  nav: 10, navDate: "2026-10-29", navStale: false, navNote: null, invested: 80, investedWhy: null, current: 100, currentWhy: null, gain: 20, gainPct: 25, gainWhy: null, xirr: null, xirrWhy: null,
  xirrKind: "cagr", returns: { r1y: 5, r3y: null, r5y: null, asOf: null, why: null }, ter: 0.5, terDate: null, terWhy: null, aum: 100, aumAsOf: null, aumWhy: null, weight: 25, weightWhy: null,
  score: { locked: true, final: null, label: null, status: null, reason: null, runDate: null, parts: null, inherited: null },
});
const HOLDINGS = [
  H("1", "Alpha Large Cap Fund", "Equity Scheme - Large Cap Fund", "Large Cap", 1),
  H("2", "Beta Large Cap Fund", "Equity Scheme - Large Cap Fund", "Large Cap", 2),
  H("3", "Gamma Small Cap Fund", "Equity Scheme - Small Cap Fund", "Small Cap", 3),
  H("4", "Delta Corporate Bond Fund", "Debt Scheme - Corporate Bond Fund", "Corporate Bond", 4),
];
const DATA = {
  plan: "gold", scoreLocked: true, limit: 500, count: 4, dataDate: "2026-10-29", holdings: HOLDINGS,
  summary: { funds: 4, valued: 4, withCost: 4, gainFunds: 4, invested: 320, current: 400, gain: 80, gainPct: 25, navFrom: null, navTo: null, notes: [], xirr: null, xirrFunds: 0, xirrWhy: null, score: { locked: true, value: null, label: null, why: null } },
  allocation: { byCategory: [], byAmc: [] }, concentration: { level: null, text: "", top1Pct: null, top3Pct: null }, disclaimer: "", scoreDisclaimer: "",
} as unknown as MfPortfolio;

beforeEach(() => { st.data = DATA; vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(cleanup);
const card = () => document.querySelector("section.mp-cat") as HTMLElement;
const fundRows = () => [...document.querySelectorAll("table tbody tr")].map((r) => r.textContent || "");
const show = () => render(<MemoryRouter initialEntries={["/mf-portfolio"]}><MfPortfolioPage /></MemoryRouter>);

describe("MF portfolio category card", () => {
  it("has no tick boxes and no Select All: the categories are read-only", () => {
    show();
    expect(card()).toBeTruthy();
    expect(card().querySelectorAll("input")).toHaveLength(0);
    expect(within(card()).queryByText(/Select All/i)).toBeNull();
    expect(card().textContent).not.toMatch(/ticked/i);
  });

  it("lists every category with its number of funds, and draws the pie chart", () => {
    show();
    const chips = [...card().querySelectorAll(".mp-cat-chip")].map((c) => (c.textContent || "").replace(/\s+/g, " ").trim());
    expect(chips).toEqual(["Corporate Bond1", "Large Cap2", "Small Cap1"]);
    expect(card().querySelector("svg")).toBeTruthy();
  });

  it("clicking a category does nothing: all funds stay in the table", () => {
    show();
    expect(fundRows()).toHaveLength(4);
    fireEvent.click(card().querySelector(".mp-cat-chip") as HTMLElement);
    expect(fundRows()).toHaveLength(4);
  });

  it("the group tabs still switch the categories, the pie chart and the funds table", () => {
    show();
    fireEvent.click(within(card()).getByRole("tab", { name: "Debt" }));
    const chips = [...card().querySelectorAll(".mp-cat-chip")].map((c) => (c.textContent || "").replace(/\s+/g, " ").trim());
    expect(chips).toEqual(["Corporate Bond1"]);
    expect(fundRows()).toHaveLength(1);
    expect(fundRows()[0]).toContain("Delta Corporate Bond Fund");
    fireEvent.click(within(card()).getByRole("tab", { name: "All funds" }));
    expect(fundRows()).toHaveLength(4);
  });

  it("the note under the pie chart no longer talks about ticking categories", () => {
    show();
    expect(screen.getByText(/Share of your funds by type/)).toBeTruthy();
  });
});
