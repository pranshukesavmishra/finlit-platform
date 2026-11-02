// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const st = vi.hoisted(() => ({ gold: true, body: null as unknown, status: 200, calls: [] as string[] }));
vi.mock("../lib/api", async (orig) => {
  const m = await orig<typeof import("../lib/api")>();
  return { ...m, apiGet: vi.fn(async (p: string) => { st.calls.push(p); if (st.status !== 200) throw new m.ApiError(st.status, { status: "plan_required" }); return st.body; }) };
});
vi.mock("../lib/premium", () => ({ useGold: () => st.gold }));
import { ScreenBadges } from "./ScreenBadges";

const show = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><ScreenBadges symbol="MAZDOCK" /></MemoryRouter></QueryClientProvider>);
beforeEach(() => { st.gold = true; st.status = 200; st.calls = []; st.body = { symbol: "MAZDOCK", screens: [{ id: "emerging-tech", name: "Emerging tech", group: "themes", asOf: "2026-10-30" }, { id: "highest-rated-mid", name: "Highest-rated mid caps", group: "top-rated", asOf: "2026-10-30" }], ready: true, asOf: "2026-10-30" }; });
afterEach(cleanup);

describe("the screens a company is in", () => {
  it("names each one as a link to that screen, with its date", async () => {
    show();
    const a = await screen.findByRole("link", { name: "Emerging tech" });
    expect(a.getAttribute("href")).toBe("/advanced-score-screener?preset=emerging-tech");
    expect(a.getAttribute("title")).toMatch(/as of 30 Oct 2026.*not a recommendation/);
    expect(screen.getByRole("link", { name: "Highest-rated mid caps" })).toBeTruthy();
    expect(st.calls[0]).toBe("/api/screener/presets/for/MAZDOCK");
  });
  it("shows nothing when the company is in no screen, or the server refuses", async () => {
    st.body = { symbol: "MAZDOCK", screens: [], ready: true, asOf: "2026-10-30" };
    const { container } = show();
    await vi.waitFor(() => expect(st.calls.length).toBe(1));
    expect(container.textContent).toBe("");
    cleanup(); st.status = 403; st.calls = [];
    const r = show();
    await vi.waitFor(() => expect(st.calls.length).toBe(1));
    expect(r.container.textContent).toBe("");
  });
  it("below Gold it asks nothing and shows nothing; and no advice word appears", async () => {
    st.gold = false;
    const { container } = show();
    expect(container.textContent).toBe(""); expect(st.calls.length).toBe(0);
    cleanup(); st.gold = true;
    const r = show();
    await screen.findByText("In screens");
    expect(r.container.textContent).not.toMatch(/\b(buy|sell|hold|target|avoid|accumulate|best)\b/i);
  });
});
