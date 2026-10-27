// @vitest-environment jsdom
// "Filter companies by growth" on the Latest results page: the controls, the address (URL) state, the plan gate, and the chart legends with counts.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { QParams, QResp } from "../lib/qresults";
import { DEFAULT_GROWTH, growthFromParams, growthQuery, growthToParams, valueProblem } from "../lib/qresults";

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
  growth: { qoq: true, yoy: true, join: "and", withFigures: 8, both: 2, onlyQoQ: 3, onlyYoY: 1, neither: 2, matching: 2, qoqMissing: 1, yoyMissing: 0 },
  distribution: { total: 5, sectors: [{ name: "IT", n: 3 }, { name: "Banks", n: 1 }, { name: "Others", n: 1 }], caps: [{ name: "Large", n: 4 }, { name: "Not classified", n: 1 }] }, ...over,
});
const Where = () => { const l = useLocation(); return <output data-testid="loc">{l.pathname + l.search}</output>; };
const open = (qs = "") => render(<MemoryRouter initialEntries={["/results/quarter" + qs]}><Routes><Route path="/results/quarter" element={<QuarterResultsPage />} /></Routes><Where /></MemoryRouter>);
const loc = () => decodeURIComponent(screen.getByTestId("loc").textContent || "");
const lastParams = () => st.params[st.params.length - 1] as QParams;
const card = (name: RegExp) => screen.getByRole("group", { name });

beforeEach(() => { st.plan = "silver"; st.params = []; st.resp = resp(); st.upgrade.mockClear(); vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(cleanup);

describe("growth filter state in the address", () => {
  it("round-trips and keeps a clean address clean", () => {
    expect(growthToParams(new URLSearchParams("quarter=2026-09"), DEFAULT_GROWTH).toString()).toBe("quarter=2026-09");
    const g = growthFromParams(new URLSearchParams("qoqMetric=revenue&qoqOp=%3C&qoqValue=-2.5&yoyValue=10&join=or"));
    expect(g.qoq).toEqual({ metric: "revenue", op: "<", value: "-2.5" });
    expect(g.yoy).toEqual({ metric: "netProfit", op: ">=", value: "10" }); expect(g.join).toBe("or");
    expect(growthToParams(new URLSearchParams("quarter=2026-09"), g).get("qoqValue")).toBe("-2.5");
    expect(growthQuery(g)).toEqual({ qoqMetric: "revenue", qoqOp: "<", qoqValue: "-2.5", yoyMetric: "netProfit", yoyOp: ">=", yoyValue: "10", join: "or" });
  });
  it("ignores unknown values in the address and never sends an invalid number", () => {
    const g = growthFromParams(new URLSearchParams("qoqMetric=bogus&qoqOp=!!&qoqValue=abc&join=xor"));
    expect(g.qoq.metric).toBe("netProfit"); expect(g.join).toBe("and");
    expect(growthQuery(g)).toEqual({});
    for (const bad of ["abc", "1e3", "NaN", "Infinity", "1,5", "--1", "-", "."]) expect(valueProblem(bad), bad).toBeTruthy();
    for (const ok of ["", "0", "-2.5", "+3", ".5", "12.", "−2"]) expect(valueProblem(ok), ok).toBeNull();
  });
});

describe("the panel", () => {
  it("asks the server with the typed thresholds and keeps them in the address", () => {
    open();
    expect(lastParams().qoqValue).toBeUndefined();
    const qoq = within(card(/Quarter-on-quarter/));
    fireEvent.change(qoq.getByLabelText("Metric"), { target: { value: "revenue" } });
    fireEvent.change(qoq.getByLabelText("Operator"), { target: { value: "<" } });
    fireEvent.change(qoq.getByLabelText("Value %"), { target: { value: "-2.5" } });
    fireEvent.keyDown(qoq.getByLabelText("Value %"), { key: "Enter" });
    expect(loc()).toContain("qoqMetric=revenue"); expect(loc()).toContain("qoqOp=<"); expect(loc()).toContain("qoqValue=-2.5");
    expect(lastParams()).toMatchObject({ qoqMetric: "revenue", qoqOp: "<", qoqValue: "-2.5", join: "and" });
    const yoy = within(card(/Year-on-year/));
    fireEvent.change(yoy.getByLabelText("Value %"), { target: { value: "10" } });
    fireEvent.blur(yoy.getByLabelText("Value %"));
    expect(lastParams()).toMatchObject({ yoyMetric: "netProfit", yoyOp: ">=", yoyValue: "10" });
    fireEvent.click(screen.getByRole("button", { name: "OR" }));
    expect(loc()).toContain("join=or"); expect(lastParams().join).toBe("or");
    expect(screen.getByRole("button", { name: "OR" }).getAttribute("aria-pressed")).toBe("true");
  });
  it("starts from a shared link, shows the hint, and Reset filters clears only the growth filters", () => {
    open("?quarter=2026-09&qoqValue=1&yoyValue=-3&yoyOp=%3C%3D&join=or");
    expect((within(card(/Quarter-on-quarter/)).getByLabelText("Value %") as HTMLInputElement).value).toBe("1");
    expect((within(card(/Year-on-year/)).getByLabelText("Operator") as HTMLSelectElement).value).toBe("<=");
    expect(screen.getByText("e.g. Net profit QoQ >= 1%")).toBeTruthy();
    expect(lastParams()).toMatchObject({ quarter: "2026-09", qoqValue: "1", yoyValue: "-3", yoyOp: "<=", join: "or" });
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(loc()).toBe("/results/quarter?quarter=2026-09");
    expect(lastParams().qoqValue).toBeUndefined();
    expect((screen.getByRole("button", { name: "Reset filters" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("rejects a bad number in words and does not ask the server", () => {
    open();
    const v = within(card(/Quarter-on-quarter/)).getByLabelText("Value %");
    fireEvent.change(v, { target: { value: "1e3" } }); fireEvent.blur(v);
    expect(screen.getByRole("alert").textContent).toMatch(/Type a number/);
    expect(v.getAttribute("aria-invalid")).toBe("true");
    expect(st.params.every((p) => (p as QParams).qoqValue === undefined)).toBe(true);
  });
  it("says why banks never match an operating-profit filter", () => {
    open();
    expect(screen.queryByText(/never match an operating-profit filter/)).toBeNull();
    fireEvent.change(within(card(/Year-on-year/)).getByLabelText("Metric"), { target: { value: "operatingProfit" } });
    expect(screen.getByText(/Banks and lenders do not report operating profit growth/)).toBeTruthy();
  });
  it("sends a Basic visitor to the upgrade prompt and puts nothing in the address or the request", () => {
    st.plan = "basic"; st.resp = resp({ plan: "basic", locked: true, growth: null });
    open();
    const v = within(card(/Quarter-on-quarter/)).getByLabelText("Value %");
    fireEvent.change(v, { target: { value: "5" } }); fireEvent.blur(v);
    expect(st.upgrade).toHaveBeenCalledWith("silver", expect.stringMatching(/growth/i));
    expect(loc()).toBe("/results/quarter");
    expect(st.params.every((p) => (p as QParams).qoqValue === undefined)).toBe(true);
    expect(screen.getByText(/part of the Silver plan/, { selector: ".qg-none" })).toBeTruthy();
  });
});

describe("the charts", () => {
  it("shows the four-way split with counts and shares, and the same text in the aria-label", () => {
    open("?qoqValue=1&yoyValue=10");
    const svg = screen.getByRole("img", { name: /^Companies meeting both filters/ });
    expect(svg.getAttribute("aria-label")).toBe("Companies meeting both filters: Both filters 2 (25.0%), Only QoQ 3 (37.5%), Only YoY 1 (12.5%), Neither 2 (25.0%)");
    const legend = screen.getByRole("list", { name: /Companies meeting both filters, counts and shares/ });
    const rows = within(legend).getAllByRole("listitem").map((li) => li.textContent);
    expect(rows).toEqual(["Both filters225.0%", "Only QoQ337.5%", "Only YoY112.5%", "Neither225.0%"]);
    const counts = within(legend).getAllByRole("listitem").map((li) => Number(li.querySelector("b")!.textContent));
    expect(counts.reduce((a, b) => a + b, 0)).toBe(8);
    expect(screen.getByText(/1 company has no QoQ net profit growth figure/)).toBeTruthy();
  });
  it("shows the sector and market cap donuts from the server's counts", () => {
    open();
    expect(screen.getByRole("img", { name: "Sector-wise distribution: IT 3 (60.0%), Banks 1 (20.0%), Others 1 (20.0%)" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Market cap distribution: Large 4 (80.0%), Not classified 1 (20.0%)" })).toBeTruthy();
  });
  it("uses a two-slice split for a single filter and a sentence when there is nothing to chart", () => {
    st.resp = resp({ growth: { qoq: true, yoy: false, join: "and", withFigures: 4, both: 0, onlyQoQ: 1, onlyYoY: 0, neither: 3, matching: 1, qoqMissing: 0, yoyMissing: 0 }, distribution: { total: 0, sectors: [], caps: [] } });
    open("?qoqValue=1");
    expect(screen.getByRole("img", { name: "Companies meeting both filters: Meets the QoQ filter 1 (25.0%), Does not meet it 3 (75.0%)" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Sector-wise distribution: No companies in this view." })).toBeTruthy();
  });
});
