// @vitest-environment jsdom
// The Mutual Fund Screener page in a DOM: one call for the counts, filters editing the address, the no-data line, honest disabled groups and the wording scan.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const st = vi.hoisted(() => ({ calls: [] as string[] }));
const hist = (edges: number[]) => ({ edges, bins: edges.slice(1).map((_, i) => i + 1), n: 10, m: 14 });
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiGet: vi.fn(async (path: string) => {
    st.calls.push(path);
    if (path.startsWith("/api/mf/filters")) {
      const numeric: Record<string, unknown> = {};
      for (const k of ["aum", "age", "r1y", "r3y", "r5y", "ter", "ter_rel", "vol3", "fall", "sharpe", "eq_pct"]) numeric[k] = hist([0, 1, 2, 5, 10]);
      return { totals: { schemes: 20, active: 18, withHistory: 10 }, amcs: [], categories: [], dataDate: "2026-10-20", screen: {
        total: 14, numeric, type: { equity: 9, debt: 5 }, subs: [{ key: "mid-cap", label: "Mid Cap", tab: "equity", n: 4 }, { key: "liquid", label: "Liquid", tab: "debt", n: 5 }], cap: { mid: 4 }, style: { active: 14, passive: 0 },
        mat: {}, struct: { open: 14 }, amcs: [{ name: "Axis Mutual Fund", n: 3 }], house: {}, plans: { Direct: 14 }, options: { Growth: 14 }, inst: { fund: 14, etf: 0 }, status: { active: 14, stopped: 0 }, fresh: {},
        aumbasis: {}, aumrank: {}, exit: {}, chk: {}, chk_each: {}, tick: { noneg36: 3 }, rk: {}, tags: [{ tag: "defence", kind: "theme", label: "Defence & Aerospace", n: 2 }], sectors: [], portfolio: { none: 4 }, cflow: {}, cstreak: {}, csize: {},
        built: { rows: 20, run: "2026-10-20", portfolioDate: "2026-09-30", flowMonth: "2026-09-01", tagged: 2, indexTagged: 0 },
        scatter: { points: [[1, "A", 10, 12], [2, "B", 12, 15], [3, "C", 8, 9]], eligible: 3, shown: 3 }, flows: [] } };
    }
    return { total: 14, page: 1, size: 50, pages: 1, dataDate: "2026-10-20", items: [{ code: 1, name: "Alpha Mid Cap Fund", amc: "Alpha Mutual Fund", category: "Equity Scheme - Mid Cap Fund", plan: "Direct", option: "Growth", optionClass: "Growth", nav: 10, navDate: "2026-10-20", change: 0.2, active: true, r1y: 5, r3y: 12, r5y: null, noReturns: null, ter: 0.6, aum: 1200, fall3y: -14, x: { risk: { vol3: 15 }, rank: { "3y": { rank: 2, of: 9 } }, ex: {}, category: {} } }] };
  }),
}));
vi.mock("../../lib/ui", () => ({ useUI: () => ({ has: () => true, upgrade: vi.fn(), toast: vi.fn() }), TIER: {} }));
import { MfScreenerPage } from "../../pages/MfScreener";

vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
const Where = () => <output data-testid="loc">{useLocation().search}</output>;
const mount = (at = "/funds/screener") => { const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[at]}><Routes><Route path="*" element={<><MfScreenerPage /><Where /></>} /></Routes></MemoryRouter></QueryClientProvider>); };
beforeEach(() => { st.calls = []; });
afterEach(cleanup);

describe("Mutual Fund Screener page", () => {
  it("asks the server once for the counts and once for the list, with the defaults spelled out", async () => {
    mount();
    await screen.findByText("Alpha Mid Cap Fund");
    const f = st.calls.filter((c) => c.startsWith("/api/mf/filters")), l = st.calls.filter((c) => c.startsWith("/api/mf?"));
    expect(f).toHaveLength(1); expect(l).toHaveLength(1);
    expect(f[0]).toContain("screen=true"); expect(f[0]).toContain("plans=Direct"); expect(f[0]).toContain("options=Growth"); expect(l[0]).toContain("extra=true");
  });
  it("ticking a sub-category edits the address and asks again", async () => {
    mount();
    await screen.findByText("Alpha Mid Cap Fund");
    fireEvent.click(await screen.findByLabelText(/Mid Cap/, { selector: "input" }));
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toContain("subs=mid-cap"));
    await waitFor(() => expect(st.calls.some((c) => c.includes("subs=mid-cap"))).toBe(true));
    expect(screen.getByRole("button", { name: /Remove filter: Mid Cap/ })).toBeTruthy();
  });
  it("a preset sets filters and shows as on; the score preset is disabled", async () => {
    mount();
    await screen.findByText("Alpha Mid Cap Fund");
    const p = screen.getByRole("button", { name: /Defence and aerospace funds/ });
    fireEvent.click(p);
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toContain("tags=defence"));
    expect(screen.getByRole("button", { name: /Defence and aerospace funds/ }).getAttribute("aria-pressed")).toBe("true");
    expect((screen.getByRole("button", { name: /Health score 65\+/ }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("shows the no-data count and the groups that need a data source, disabled and explained", async () => {
    mount("/funds/screener?rng=ter:0:1");
    await screen.findByText("Alpha Mid Cap Fund");
    expect(screen.getAllByText(/of/).length).toBeGreaterThan(0);
    expect(document.body.textContent).toMatch(/Needs a data source/);
    expect(document.body.textContent).toMatch(/Risk-o-meter/);
  });
  it("uses no advice wording and keeps the disclaimer", async () => {
    mount();
    await screen.findByText("Alpha Mid Cap Fund");
    const text = document.body.textContent || "";
    expect(text).toMatch(/Not investment advice/);
    expect(text).not.toMatch(/\b(buy|sell|accumulate|avoid|recommended|best)\b/i);
  });
});
