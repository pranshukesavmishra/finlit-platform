// @vitest-environment jsdom
// "Filter companies by growth" on the Latest results page: the controls, the address (URL) state, the plan gate, and the chart legends with counts.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { QParams, QResp } from "../lib/qresults";
import { DEFAULT_GROWTH, GROWTH_CELLS, GROWTH_PRESETS, FIELD_OF, applyPreset, cellHit, emptyCells, growthFromParams, growthQuery, growthToParams, valueProblem, type CellKey, type GrowthState, type QRow } from "../lib/qresults";

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
const resp = (over: Partial<QResp> = {}): QResp => ({
  plan: "silver", locked: false, today: "2026-10-27", quarter: { key: "2026-09", label: "Jul to Sep 2026", fiscal: "Q2 FY27", periodEnd: "2026-09-30", from: "2026-10-01", to: "2026-12-31" }, quarters: [],
  total: 5, offset: 0, limit: 50, summary, totals: summary, rows: [], days: [], facets: { sectors: [], indices: [] },
  growth: { join: "and", k: 2, withFigures: 8, matching: 2, metAll: 2, metSome: 4, metNone: 2, conditions: [
    { metric: "revenue", period: "qoq", op: ">=", value: 1, met: 5, missing: 1 }, { metric: "netProfit", period: "yoy", op: ">=", value: 10, met: 3, missing: 0 }] },
  distribution: { total: 5, sectors: [{ name: "IT", n: 3 }, { name: "Banks", n: 1 }, { name: "Others", n: 1 }], caps: [{ name: "Large", n: 4 }, { name: "Not classified", n: 1 }] }, ...over,
});
const Where = () => { const l = useLocation(); return <output data-testid="loc">{l.pathname + l.search}</output>; };
const open = (qs = "") => render(<MemoryRouter initialEntries={["/results/quarter" + qs]}><Routes><Route path="/results/quarter" element={<QuarterResultsPage />} /></Routes><Where /></MemoryRouter>);
const loc = () => decodeURIComponent(screen.getByTestId("loc").textContent || "");
const lastParams = () => st.params[st.params.length - 1] as QParams;
const cellIn = (what: string) => ({ op: screen.getByLabelText(`${what} operator`) as HTMLSelectElement, val: screen.getByLabelText(`${what} value in per cent`) as HTMLInputElement });
const type = (what: string, v: string) => { const { val } = cellIn(what); fireEvent.change(val, { target: { value: v } }); fireEvent.keyDown(val, { key: "Enter" }); };

beforeEach(() => { st.plan = "silver"; st.params = []; st.resp = resp(); st.upgrade.mockClear(); vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(cleanup);

const withCells = (o: Partial<Record<CellKey, [string, string]>>, join: "and" | "or" = "and"): GrowthState => ({ cells: { ...emptyCells(), ...Object.fromEntries(Object.entries(o).map(([k, [op, value]]) => [k, { op, value }])) } as GrowthState["cells"], join });

describe("growth filter state in the address", () => {
  it("round-trips every cell and keeps a clean address clean", () => {
    expect(growthToParams(new URLSearchParams("quarter=2026-09"), DEFAULT_GROWTH).toString()).toBe("quarter=2026-09");
    const g = withCells({ revQoQ: ["<", "-2.5"], revYoY: [">=", "5"], opQoQ: [">", "0"], opYoY: ["<=", "1"], npQoQ: [">=", "3"], npYoY: [">=", "10"] }, "or");
    const sp = growthToParams(new URLSearchParams("quarter=2026-09"), g);
    expect(sp.get("quarter")).toBe("2026-09"); expect(sp.get("join")).toBe("or");
    expect(growthFromParams(sp)).toEqual(g);
    expect(growthQuery(g)).toEqual({ revQoQOp: "<", revQoQValue: "-2.5", revYoYOp: ">=", revYoYValue: "5", opQoQOp: ">", opQoQValue: "0", opYoYOp: "<=", opYoYValue: "1", npQoQOp: ">=", npQoQValue: "3", npYoYOp: ">=", npYoYValue: "10", join: "or" });
    for (const k of GROWTH_CELLS) expect(growthFromParams(growthToParams(new URLSearchParams(), withCells({ [k]: [">", "7"] }))).cells[k]).toEqual({ op: ">", value: "7" });   // one cell alone
  });
  it("opens links shared before the grid existed with the same filter", () => {
    const g = growthFromParams(new URLSearchParams("qoqMetric=revenue&qoqOp=%3C&qoqValue=-2.5&yoyValue=10&join=or"));
    expect(g.cells.revQoQ).toEqual({ op: "<", value: "-2.5" });
    expect(g.cells.npYoY).toEqual({ op: ">=", value: "10" });   // an old filter without a metric meant net profit
    expect(onlyFilled(g)).toEqual(["revQoQ", "npYoY"]); expect(g.join).toBe("or");
    const op = growthFromParams(new URLSearchParams("qoqMetric=operatingProfit&qoqOp=%3E&qoqValue=4&yoyMetric=netProfit&yoyOp=%3C%3D&yoyValue=1"));
    expect(onlyFilled(op)).toEqual(["opQoQ", "npYoY"]);   // both profit kinds at once, which the old form allowed
    expect(growthFromParams(new URLSearchParams("qoqValue=5&revQoQOp=%3E&revQoQValue=7")).cells.npQoQ.value).toBe("5");
    expect(growthFromParams(new URLSearchParams("qoqMetric=revenue&qoqValue=5&revQoQValue=7")).cells.revQoQ.value).toBe("7");   // a grid value wins on the same cell
    // saving rewrites an old link into grid names and drops the old ones
    const out = growthToParams(new URLSearchParams("qoqMetric=revenue&qoqOp=%3C&qoqValue=-2.5&yoyValue=10"), g);
    expect(out.has("qoqValue")).toBe(false); expect(out.get("revQoQValue")).toBe("-2.5"); expect(out.get("npYoYValue")).toBe("10");
  });
  it("ignores unknown values in the address and never sends an invalid number", () => {
    const g = growthFromParams(new URLSearchParams("qoqMetric=bogus&qoqOp=!!&qoqValue=abc&join=xor&revYoYOp=zz&revYoYValue=oops"));
    expect(g.join).toBe("and"); expect(g.cells.revYoY.op).toBe(">=");
    expect(growthQuery(g)).toEqual({});
    for (const bad of ["abc", "1e3", "NaN", "Infinity", "1,5", "--1", "-", "."]) expect(valueProblem(bad), bad).toBeTruthy();
    for (const ok of ["", "0", "-2.5", "+3", ".5", "12.", "\u22122"]) expect(valueProblem(ok), ok).toBeNull();
  });
});
const onlyFilled = (g: GrowthState) => GROWTH_CELLS.filter((k) => g.cells[k].value !== "");

describe("which cells a row meets (highlight rule, same as the server)", () => {
  const row = { hasNumbers: true, revenueQoQ: 5, revenueYoY: 0, opQoQ: null, opYoY: -1, profitQoQ: 10, profitYoY: null } as unknown as QRow;
  it("tests every operator, equality, negatives and missing figures", () => {
    const hit = (k: CellKey, op: string, v: string) => cellHit(row, k, { op: op as never, value: v });
    expect([">=", ">", "<=", "<"].map((op) => hit("revQoQ", op, "5"))).toEqual([true, false, true, false]);
    expect([">=", ">", "<=", "<"].map((op) => hit("revYoY", op, "0"))).toEqual([true, false, true, false]);
    expect(hit("opYoY", "<", "-0.5")).toBe(true); expect(hit("opYoY", ">=", "\u22121")).toBe(true);
    for (const op of [">=", ">", "<=", "<"]) { expect(hit("opQoQ", op, "0")).toBe(false); expect(hit("npYoY", op, "-100")).toBe(false); }   // no figure: never, even for < or a negative limit
    expect(hit("npQoQ", ">=", "")).toBe(false); expect(hit("npQoQ", ">=", "abc")).toBe(false);
    expect(cellHit({ ...row, hasNumbers: false }, "revQoQ", { op: ">=", value: "0" })).toBe(false);
    expect(FIELD_OF.npYoY).toBe("profitYoY");
  });
});

describe("presets", () => {
  it("fill exactly the four revenue and net profit cells and leave operating profit empty", () => {
    const grow = applyPreset(GROWTH_PRESETS[0]), strong = applyPreset(GROWTH_PRESETS[1]);
    expect(onlyFilled(grow)).toEqual(["revQoQ", "revYoY", "npQoQ", "npYoY"]);
    expect(GROWTH_CELLS.filter((k) => grow.cells[k].value !== "").every((k) => grow.cells[k].op === ">" && grow.cells[k].value === "0")).toBe(true);
    expect(onlyFilled(strong).map((k) => strong.cells[k])).toEqual(Array(4).fill({ op: ">=", value: "10" }));
    expect(grow.join).toBe("and");
  });
});

describe("the panel", () => {
  it("has a grid with a labelled operator and value for every metric and period, and a live result line", () => {
    st.resp = resp({ growth: null });
    open();
    for (const m of ["Revenue", "Operating profit", "Net profit"]) {
      expect(screen.getByRole("group", { name: `${m} growth` })).toBeTruthy();
      for (const p of ["QoQ", "YoY"]) { const c = cellIn(`${m} ${p}`); expect(c.op.value).toBe(">="); expect(c.val.value).toBe(""); }
    }
    expect(document.querySelector(".qg-state")!.getAttribute("aria-live")).toBe("polite");
    expect(screen.getByText("No growth filter is on, so every company in the table is shown.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Match all" }).getAttribute("aria-pressed")).toBe("true");
  });
  it("asks the server with every filled cell, keeps them in the address, and switches all/any", () => {
    open();
    expect(lastParams().revQoQValue).toBeUndefined();
    fireEvent.change(cellIn("Revenue QoQ").op, { target: { value: "<" } });
    type("Revenue QoQ", "-2.5");
    expect(loc()).toContain("revQoQOp=<"); expect(loc()).toContain("revQoQValue=-2.5");
    type("Revenue YoY", "10"); type("Net profit QoQ", "0"); type("Net profit YoY", "15");
    expect(lastParams()).toMatchObject({ revQoQOp: "<", revQoQValue: "-2.5", revYoYOp: ">=", revYoYValue: "10", npQoQOp: ">=", npQoQValue: "0", npYoYOp: ">=", npYoYValue: "15", join: "and" });
    expect(lastParams().opQoQValue).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: "Match any" }));
    expect(loc()).toContain("join=or"); expect(lastParams().join).toBe("or");
    expect(screen.getByRole("button", { name: "Match any" }).getAttribute("aria-pressed")).toBe("true");
  });
  it("fills the grid from a preset and Reset clears only the growth filters", () => {
    open("?quarter=2026-09");
    fireEvent.click(screen.getByRole("button", { name: "10% or more on all four" }));
    expect(cellIn("Revenue QoQ").val.value).toBe("10"); expect(cellIn("Net profit YoY").val.value).toBe("10"); expect(cellIn("Operating profit QoQ").val.value).toBe("");
    expect(screen.getByRole("button", { name: "10% or more on all four" }).getAttribute("aria-pressed")).toBe("true");
    expect(lastParams()).toMatchObject({ quarter: "2026-09", revQoQValue: "10", revYoYValue: "10", npQoQValue: "10", npYoYValue: "10" });
    fireEvent.click(screen.getByRole("button", { name: "Revenue and net profit both growing" }));
    expect(lastParams()).toMatchObject({ revQoQOp: ">", revQoQValue: "0" });
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(loc()).toBe("/results/quarter?quarter=2026-09");
    expect(lastParams().revQoQValue).toBeUndefined();
    expect((screen.getByRole("button", { name: "Reset filters" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("starts from an old shared link and from a grid link", () => {
    open("?quarter=2026-09&qoqMetric=revenue&qoqValue=1&yoyValue=-3&yoyOp=%3C%3D&join=or");
    expect(cellIn("Revenue QoQ").val.value).toBe("1"); expect(cellIn("Net profit YoY").op.value).toBe("<="); expect(cellIn("Net profit YoY").val.value).toBe("-3");
    expect(lastParams()).toMatchObject({ quarter: "2026-09", revQoQValue: "1", npYoYValue: "-3", npYoYOp: "<=", join: "or" });
    expect((lastParams() as Record<string, unknown>).qoqValue).toBeUndefined();
  });
  it("rejects a bad number in words and does not ask the server", () => {
    open();
    const { val } = cellIn("Revenue QoQ");
    fireEvent.change(val, { target: { value: "1e3" } }); fireEvent.blur(val);
    expect(screen.getByRole("alert").textContent).toMatch(/Type a number/);
    expect(val.getAttribute("aria-invalid")).toBe("true");
    expect(st.params.every((p) => (p as QParams).revQoQValue === undefined)).toBe(true);
  });
  it("says why banks never match an operating-profit filter, only when one is on", () => {
    open();
    expect(screen.queryByText(/never match an operating-profit filter/)).toBeNull();
    type("Operating profit YoY", "5");
    expect(screen.getByText(/Banks and lenders do not report operating profit growth/)).toBeTruthy();
  });
  it("sends a Basic visitor to the upgrade prompt and puts nothing in the address or the request", () => {
    st.plan = "basic"; st.resp = resp({ plan: "basic", locked: true, growth: null });
    open();
    type("Revenue QoQ", "5");
    expect(st.upgrade).toHaveBeenCalledWith("silver", expect.stringMatching(/growth/i));
    expect(loc()).toBe("/results/quarter");
    expect(st.params.every((p) => (p as QParams).revQoQValue === undefined)).toBe(true);
    expect(screen.getByText(/part of the Silver plan/, { selector: ".qg-none" })).toBeTruthy();
  });
  it("uses only wording that is information, never advice", () => {
    open();
    const text = (document.querySelector(".qg") as HTMLElement).textContent || "";
    expect(text).not.toMatch(/\b(buy|sell|hold|target|recommend|should|outperform|undervalued|multibagger)\b/i);
    expect(text).toMatch(/Information only, not advice/);
  });
});

describe("the result line", () => {
  const conds = (n: number[]) => n.map((missing, i) => ({ metric: (["revenue", "operatingProfit", "netProfit"] as const)[i % 3], period: (i < 3 ? "qoq" : "yoy") as "qoq" | "yoy", op: ">=" as const, value: 1, met: 1, missing }));
  it("counts matches of all conditions and itemises the missing figures, largest first, collapsing beyond three", () => {
    st.resp = resp({ growth: { join: "and", k: 5, withFigures: 100, matching: 7, metAll: 7, metSome: 60, metNone: 33, conditions: conds([14, 0, 46, 3, 20]) } });
    open("?revQoQValue=1");
    const line = document.querySelector(".qg-state")!.textContent!;
    expect(line).toContain("7 of 100 companies with figures match all 5 conditions.");
    expect(screen.getByText("46 companies have no QoQ net profit growth figure and cannot match it.")).toBeTruthy();
    expect(screen.getByText("20 companies have no YoY operating profit growth figure and cannot match it.")).toBeTruthy();
    expect(screen.getByText("14 companies have no QoQ revenue growth figure and cannot match it.")).toBeTruthy();
    expect(screen.queryByText(/^3 companies have no/)).toBeNull();
    const more = screen.getByRole("button", { name: /and 1 more condition \(details\)/ });
    expect(more.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(more);
    expect(screen.getByText("3 companies have no YoY revenue growth figure and cannot match it.")).toBeTruthy();
    expect(more.getAttribute("aria-expanded")).toBe("true");
  });
  it("says any-of for OR, the singular for one condition and one company, and nothing about missing when none", () => {
    st.resp = resp({ growth: { join: "or", k: 2, withFigures: 8, matching: 6, metAll: 2, metSome: 4, metNone: 2, conditions: conds([1, 0]) } });
    open("?revQoQValue=1&npYoYValue=1&join=or");
    expect(document.querySelector(".qg-state")!.textContent).toContain("6 of 8 companies with figures match any of the 2 conditions.");
    expect(screen.getByText("1 company has no QoQ revenue growth figure and cannot match it.")).toBeTruthy();
    cleanup();
    st.resp = resp({ growth: { join: "and", k: 1, withFigures: 8, matching: 3, metAll: 3, metSome: 0, metNone: 5, conditions: conds([0]) } });
    open("?revQoQValue=1");
    expect(document.querySelector(".qg-state")!.textContent).toBe("3 of 8 companies with figures match the condition.");
  });
});

describe("the table", () => {
  it("marks the cells that met a filter, for sighted and screen reader users", () => {
    const row = { date: "2026-10-14", symbol: "AAA", name: "Aaa Ltd", sector: "IT", marketCap: 1, cap: "Large", indices: [], confirmed: true, periodEnd: "2026-09-30", loadedPeriodEnd: null, status: "declared", awaiting: false, hasNumbers: true, locked: false,
      revenue: 100, revenueYoY: 12, revenueQoQ: -3, operatingProfit: 20, opYoY: 5, opQoQ: 1, opYoYWhy: null, opQoQWhy: null, opm: 20, netProfit: 10, profitYoY: 30, profitQoQ: 4, npm: 10, npmChange: 0, eps: 1, gap: 0, flagged: false, loss: false } as QRow;
    st.resp = resp({ rows: [row], total: 1 });
    open("?revYoYValue=10&revQoQValue=0&npYoYOp=%3E&npYoYValue=29");
    const hits = Array.from(document.querySelectorAll("td.qr-hit")).map((td) => td.textContent);
    expect(hits).toEqual(["+12.0% (meets your growth filter)", "+30.0% (meets your growth filter)"]);   // revenue QoQ -3 does not meet >= 0
  });
});

describe("the charts", () => {
  it("shows the three-way split with counts and shares, and the same text in the aria-label", () => {
    open("?revQoQValue=1&npYoYValue=10");
    const svg = screen.getByRole("img", { name: /^Companies meeting the growth conditions/ });
    expect(svg.getAttribute("aria-label")).toBe("Companies meeting the growth conditions: Meet all 2 2 (25.0%), Meet some, not all 4 (50.0%), Meet none 2 (25.0%)");
    const legend = screen.getByRole("list", { name: /Companies meeting the growth conditions, counts and shares/ });
    const counts = within(legend).getAllByRole("listitem").map((li) => Number(li.querySelector("b")!.textContent));
    expect(counts).toEqual([2, 4, 2]); expect(counts.reduce((a, b) => a + b, 0)).toBe(8);
  });
  it("shows the sector and market cap donuts from the server's counts", () => {
    open();
    expect(screen.getByRole("img", { name: "Sector-wise distribution: IT 3 (60.0%), Banks 1 (20.0%), Others 1 (20.0%)" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Market cap distribution: Large 4 (80.0%), Not classified 1 (20.0%)" })).toBeTruthy();
  });
  it("uses a two-slice split for a single condition and a sentence when there is nothing to chart", () => {
    st.resp = resp({ growth: { join: "and", k: 1, withFigures: 4, matching: 1, metAll: 1, metSome: 0, metNone: 3, conditions: [{ metric: "revenue", period: "qoq", op: ">=", value: 1, met: 1, missing: 0 }] }, distribution: { total: 0, sectors: [], caps: [] } });
    open("?revQoQValue=1");
    expect(screen.getByRole("img", { name: "Companies meeting the growth conditions: Meets the condition 1 (25.0%), Does not meet it 3 (75.0%)" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Sector-wise distribution: No companies in this view." })).toBeTruthy();
  });
});
