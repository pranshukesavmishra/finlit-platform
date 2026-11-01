// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const st = vi.hoisted(() => ({ gold: true, body: null as unknown, status: 200, calls: [] as string[] }));
vi.mock("../lib/api", async (orig) => {
  const m = await orig<typeof import("../lib/api")>();
  return { ...m, apiGet: vi.fn(async (path: string) => { st.calls.push(path); if (st.status !== 200) throw new m.ApiError(st.status, { status: "plan_required" }); return st.body; }) };
});
vi.mock("../lib/premium", () => ({ useGold: () => st.gold }));
import { PrismHistoryCard } from "./PrismHistory";

const pt = (day: string, final: number | null, o: Record<string, unknown> = {}) => ({ day, modelVersion: "3.6.10", final, label: "HEALTHY", status: "RATED", parts: { fundamental: 50, valuation: 60, quality: 70, risk: 80 }, shortTerm: 10, longTerm: 20, ...o });
const wrap = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><PrismHistoryCard symbol="MAZDOCK" statement="consolidated" /></QueryClientProvider>);
beforeEach(() => { st.gold = true; st.status = 200; st.calls = []; st.body = { symbol: "MAZDOCK", statement: "consolidated", points: [], firstDay: null, note: "" }; });
afterEach(cleanup);

describe("Prism score over time", () => {
  it("with no days recorded it says so and draws no empty chart", async () => {
    wrap();
    await screen.findByText(/No days are recorded for this company yet/);
    expect(document.querySelector(".phx svg")).toBeNull();
    expect(st.calls[0]).toBe("/api/prism/history?symbol=MAZDOCK&statement=consolidated");
  });
  it("with one day it says a line needs two", async () => {
    st.body = { points: [pt("2026-11-02", 62)] };
    wrap();
    await screen.findByText(/Only one day is recorded so far/);
  });
  it("draws the score line, summarises the change, marks a model change, and offers the same numbers as a table", async () => {
    st.body = { points: [pt("2026-11-02", 60), pt("2026-11-09", 62), pt("2026-11-16", 66, { modelVersion: "3.6.11" })] };
    wrap();
    await screen.findByText(/Prism score moved from 60 on 2 Nov 2026 to 66 on 16 Nov 2026 \(\+6 points\)/);
    const svg = document.querySelector(".phx svg")!;
    expect(svg.getAttribute("aria-label")).toBe("Prism score over time, 3 days recorded");
    expect(svg.querySelectorAll("path").length).toBe(1);                                      // only the score line is on by default
    expect(screen.getByText(/dashed gold line marks a day the model version changed \(16 Nov\)/)).toBeTruthy();
    expect(document.querySelectorAll(".phx-table tbody tr").length).toBe(3);
    fireEvent.click(screen.getByLabelText("Valuation"));
    expect(svg.querySelectorAll("path").length).toBe(2);                                      // a part can be added
  });
  it("the technical tab plots the two views on their own scale", async () => {
    st.body = { points: [pt("2026-11-02", 60, { shortTerm: -12.5, longTerm: 30 }), pt("2026-11-09", 62, { shortTerm: 8, longTerm: 31 })] };
    wrap();
    await screen.findByText(/Prism score moved from 60/);
    fireEvent.click(screen.getByRole("tab", { name: "Technical views" }));
    await screen.findByText(/Short-term view moved from −12.5 on 2 Nov 2026 to \+8 on 9 Nov 2026 \(\+20.5 points\)/);
    expect(document.querySelector(".phx svg")!.querySelectorAll("path").length).toBe(2);
  });
  it("is not shown, and asks nothing, below Gold; and says nothing when the server refuses", async () => {
    st.gold = false;
    const { container } = wrap();
    expect(container.textContent).toBe(""); expect(st.calls.length).toBe(0);
    cleanup(); st.gold = true; st.status = 403;
    const r = wrap();
    await vi.waitFor(() => expect(st.calls.length).toBe(1));
    await vi.waitFor(() => expect(r.container.querySelector(".phx-card")).toBeNull());        // the card appears while loading, then goes: nothing is shown to a member the server refused
  });
  it("describes and never advises", async () => {
    st.body = { points: [pt("2026-11-02", 60), pt("2026-11-09", 62)] };
    const { container } = wrap();
    await screen.findByText(/moved from/);
    expect(container.textContent).not.toMatch(/\b(buy|sell|hold|target|avoid|accumulate|best)\b/i);
    expect(container.textContent).toContain("Describes the company's financial health from its filings and prices; not a recommendation. Information only, not investment advice.");
  });
});
