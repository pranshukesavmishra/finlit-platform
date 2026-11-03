// @vitest-environment jsdom
// The full Stock screener: groups start closed, a chosen chip puts its column in the table at once (for the period tab it is on),
// the table opens with P/E and 3Y average P/E, saved column choices win, and the address holds the filters.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { chipColumn, defaultColumns, emptyReason, encodeState, norm, tableColumns, type Catalog, type MetricInfo } from "../lib/proscreen";

vi.mock("../lib/ui", () => ({ useUI: () => ({ upgrade: vi.fn(), toast: vi.fn(), plan: "silver" }), TIER: { gold: { n: "Gold" }, silver: { n: "Silver" }, basic: { n: "Basic" } } }));
const admin = vi.hoisted(() => ({ on: true }));
vi.mock("../lib/auth", () => ({ limitsFor: () => ({ screens: 5 }), useAuth: () => ({ isAdmin: admin.on }) }));
vi.mock("../three/support", () => ({ supports3d: () => false, whenIdle: () => () => {} }));
import { ScreenerPro } from "./ScreenerPro";

const M = (key: string, label: string, o: Partial<MetricInfo> = {}): MetricInfo => ({ key, label, unit: "x", better: "lower", tier: "basic", say: label, digits: 1, locked: false, hidden: false, variants: null,
  stats: { min: 0, p10: 5, p50: 20, p90: 60, max: 100, n: 4000, hist: [1, 2, 3, 2, 1] }, ...o });
const VAR = (b: string) => ({ now: b, "3y": `${b}_avg_3y`, "5y": `${b}_avg_5y`, "7y": `${b}_avg_7y` });
const catalog = (lockSilver = false): Catalog => ({
  plan: lockSilver ? "basic" : "silver", total: 5813, withReport: 5000, updatedAt: "2026-10-30T00:00:00Z", sectors: [], industries: [], indices: [], caps: [], bands: [], limits: { rows: null, export: true },
  defaultColumns: ["market_cap", "price"],
  groups: [
    { id: "valuation", label: "Valuation", tier: "basic", metrics: [
      M("pe", "P/E Ratio", { variants: VAR("pe") }), M("pb", "P/B Ratio", { tier: "silver", locked: lockSilver, variants: VAR("pb") }), M("dividend_yield", "Dividend Yield", { unit: "%", better: "higher" }),
      ...["pe", "pb"].flatMap((b) => ["3y", "5y", "7y"].map((p) => M(`${b}_avg_${p}`, `${b === "pe" ? "P/E Ratio" : "P/B Ratio"}, ${p.toUpperCase()} average`, { hidden: true, tier: "silver", locked: lockSilver })))] },
    { id: "profitability", label: "Profitability", tier: "basic", metrics: [M("roe", "Return on equity", { unit: "%", better: "higher" })] },
    { id: "size", label: "Size", tier: "basic", metrics: [M("market_cap", "Market cap", { unit: "Cr", better: "higher" }), M("price", "Share price", { unit: "Rs", better: "none" })] },
  ],
});
const st = vi.hoisted(() => ({ cat: null as unknown, bodies: [] as { columns: string[]; filters: Record<string, unknown>; sort: { key: string; dir: string } }[] }));

const Where = () => { const l = useLocation(); return <output data-testid="loc">{l.pathname + l.search}</output>; };
const mount = (qs = "") => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={["/screener" + qs]}><Routes><Route path="/screener" element={<><ScreenerPro /><Where /></>} /></Routes></MemoryRouter></QueryClientProvider>);
};
const heads = () => Array.from(document.querySelectorAll(".scr-t thead th button")).map((b) => (b.getAttribute("aria-label") || b.textContent || "").replace(/^Sort by /, "").replace(/\s*[▲▼▾]$/, "").trim());
const colBtn = () => screen.getByRole("button", { name: /^Columns/ }).textContent;
const group = (label: RegExp) => screen.getByRole("button", { name: label });
const ready = () => waitFor(() => expect(document.querySelector(".scr-t")).toBeTruthy());

beforeEach(() => {
  st.cat = catalog(); st.bodies = []; localStorage.clear();
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false })) as never;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).includes("/api/screener/catalog")) return new Response(JSON.stringify(st.cat), { status: 200 });
    const body = JSON.parse(String(init?.body || "{}")); st.bodies.push(body);
    return new Response(JSON.stringify({ total: 2, offset: 0, limit: 50, capped: false, columns: body.columns, took: 3, rows: [
      { symbol: "AAA", name: "Alpha", sector: null, cap: "Large", band: null, full: true, v: Object.fromEntries(body.columns.map((c: string) => [c, 12])) },
      { symbol: "BBB", name: "Beta", sector: null, cap: "Mid", band: null, full: true, v: Object.fromEntries(body.columns.map((c: string) => [c, c === "pe" ? null : 8])) }] }), { status: 200 });
  }));
});
afterEach(cleanup);

describe("Stock screener groups", () => {
  it("a fresh visit has every group closed", async () => {
    mount(); await ready();
    for (const t of document.querySelectorAll("button.fgx-hb")) expect(t.getAttribute("aria-expanded")).toBe("false");
  });

  it("a group opens only when the visitor opens it", async () => {
    mount(); await ready();
    fireEvent.click(group(/^Valuation/));
    expect(group(/^Valuation/).getAttribute("aria-expanded")).toBe("true");
    expect(group(/^Profitability/).getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(group(/^Valuation/));
    expect(group(/^Valuation/).getAttribute("aria-expanded")).toBe("false");
  });

  it("a group holding an active filter from the address starts open, the others closed", async () => {
    mount("?s=" + encodeState(norm({ ranges: { roe: { min: 15 } } }), "market_cap", "desc")); await ready();
    expect(group(/^Profitability/).getAttribute("aria-expanded")).toBe("true");
    expect(group(/^Valuation/).getAttribute("aria-expanded")).toBe("false");
    expect(heads()).toContain("Return on equity");
  });
});

describe("Stock screener columns", () => {
  it("opens with market cap, price, P/E, 3Y average P/E and P/B, and the button counts them truthfully", async () => {
    mount(); await ready();
    expect(heads()).toEqual(["Company", "Market cap", "Share price", "P/E Ratio", "P/E Ratio, 3Y average", "P/B Ratio"]);
    expect(colBtn()).toBe("Columns · 5");
    expect(st.bodies[0].columns).toEqual(["market_cap", "price", "pe", "pe_avg_3y", "pb"]);   // asked of the server straight away, no slider needed
  });

  it("choosing a chip adds its column at once and unchoosing takes it away", async () => {
    mount(); await ready();
    fireEvent.click(group(/^Valuation/));
    fireEvent.click(screen.getByRole("button", { name: "Dividend Yield" }));
    await waitFor(() => expect(heads()).toContain("Dividend Yield"));
    expect(colBtn()).toBe("Columns · 6");
    expect(st.bodies.at(-1)!.filters).toEqual({});                                          // no range was set
    fireEvent.click(screen.getByRole("button", { name: "Dividend Yield" }));
    await waitFor(() => expect(heads()).not.toContain("Dividend Yield"));
    expect(colBtn()).toBe("Columns · 5");
  });

  it("choosing a chip on the Now / 3Y / 5Y / 7Y card shows the column of the tab it is on, and switching tab switches the column", async () => {
    // P/B and its averages are not in the default set here: drop them with a saved choice so the effect is visible
    localStorage.setItem("finlit.screener.cols", JSON.stringify(["market_cap"]));
    mount(); await ready();
    fireEvent.click(group(/^Valuation/));
    fireEvent.click(screen.getByRole("button", { name: "P/B Ratio" }));
    await waitFor(() => expect(heads()).toEqual(["Company", "Market cap", "P/B Ratio"]));
    fireEvent.click(screen.getByRole("tab", { name: /3Y avg/ }));
    await waitFor(() => expect(heads()).toEqual(["Company", "Market cap", "P/B Ratio, 3Y average"]));
    expect(st.bodies.at(-1)!.columns).toEqual(["market_cap", "pb_avg_3y"]);
    fireEvent.click(screen.getByRole("tab", { name: /7Y avg/ }));
    await waitFor(() => expect(heads()).toEqual(["Company", "Market cap", "P/B Ratio, 7Y average"]));
    fireEvent.click(screen.getByRole("tab", { name: /Now/ }));
    await waitFor(() => expect(heads()).toEqual(["Company", "Market cap", "P/B Ratio"]));
  });

  it("a range keeps its column even after the chip is unselected", async () => {
    localStorage.setItem("finlit.screener.cols", JSON.stringify(["market_cap"]));
    mount(); await ready();
    fireEvent.click(group(/^Valuation/));
    fireEvent.click(screen.getByRole("button", { name: "P/B Ratio" }));
    fireEvent.change(screen.getByLabelText("P/B Ratio maximum", { exact: true }), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "P/B Ratio" }));   // close the card
    await waitFor(() => expect(heads()).toContain("P/B Ratio"));
    await waitFor(() => expect(st.bodies.at(-1)!.filters).toEqual({ pb: { max: 3 } }));
  });

  it("a saved column choice wins over the defaults, and Reset brings the defaults back", async () => {
    localStorage.setItem("finlit.screener.cols", JSON.stringify(["market_cap", "roe"]));
    mount(); await ready();
    expect(heads()).toEqual(["Company", "Market cap", "Return on equity"]);
    expect(colBtn()).toBe("Columns · 2");
    fireEvent.click(screen.getByRole("button", { name: /^Columns/ }));
    fireEvent.click(screen.getByRole("button", { name: "Reset columns" }));
    await waitFor(() => expect(heads()).toContain("P/E Ratio, 3Y average"));
    expect(localStorage.getItem("finlit.screener.cols")).toBeNull();
  });

  it("removing a default column from the panel is remembered", async () => {
    mount(); await ready();
    fireEvent.click(screen.getByRole("button", { name: /^Columns/ }));
    fireEvent.click(within(document.querySelector(".pl-colmenu") as HTMLElement).getByRole("checkbox", { name: /^P\/B Ratio$/ }));
    await waitFor(() => expect(heads()).not.toContain("P/B Ratio"));
    expect(JSON.parse(localStorage.getItem("finlit.screener.cols")!)).toEqual(["market_cap", "price", "pe", "pe_avg_3y"]);
  });

  it("an empty cell is a dash with the reason in its tooltip", async () => {
    mount(); await ready();
    const cell = Array.from(document.querySelectorAll(".scr-t tbody tr")[1].querySelectorAll("td"))[3];
    expect(cell.textContent).toBe("–");
    expect(cell.getAttribute("title")).toMatch(/Loss-making/);
  });

  it("on the Basic plan only the columns the plan can see are asked for", async () => {
    st.cat = catalog(true); mount(); await ready();
    expect(st.bodies[0].columns).toEqual(["market_cap", "price", "pe"]);
    expect(st.bodies[0].columns).not.toContain("pb");
    expect(st.bodies[0].columns).not.toContain("pe_avg_3y");
  });
});

describe("column helpers", () => {
  const cat = catalog(); const by = new Map(cat.groups.flatMap((g) => g.metrics.map((m) => [m.key, m] as const)));
  it("defaults add P/E, P/E 3Y and P/B; a phone drops P/B", () => {
    expect(defaultColumns(cat)).toEqual(["market_cap", "price", "pe", "pe_avg_3y", "pb"]);
    expect(defaultColumns(cat, true)).toEqual(["market_cap", "price", "pe", "pe_avg_3y"]);
  });
  it("chip column follows the period and skips locked metrics", () => {
    const pb = by.get("pb")!;
    expect(chipColumn(pb, undefined, by)).toBe("pb");
    expect(chipColumn(pb, "5y", by)).toBe("pb_avg_5y");
    expect(chipColumn(pb, "nope", by)).toBe("pb");
    const locked = new Map(by); locked.set("pb_avg_5y", { ...by.get("pb_avg_5y")!, locked: true });
    expect(chipColumn(pb, "5y", locked)).toBeNull();
  });
  it("table columns: base first, then ranges and chips once each", () => {
    expect(tableColumns(["a", "b"], { c: { min: 1 }, a: { max: 2 } }, ["d", null, "c"], () => true)).toEqual(["a", "b", "c", "d"]);
    expect(tableColumns(["a"], { zz: { min: 1 } }, [], (k) => k !== "zz")).toEqual(["a"]);
  });
  it("empty-cell reasons", () => {
    expect(emptyReason("pe", true)).toMatch(/Loss-making/);
    expect(emptyReason("pe_avg_3y", true)).toMatch(/No 3-year history/);
    expect(emptyReason("pe", false)).toMatch(/No financial report/);
  });
});
