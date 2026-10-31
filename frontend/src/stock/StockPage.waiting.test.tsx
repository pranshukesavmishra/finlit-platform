// @vitest-environment jsdom
// The stock page of a company that is not stored yet: what it shows while the report is built, when it gives up, and when the provider fails.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/auth", () => ({ useAuth: () => ({ showcase: [], user: null }) }));
import { StockPage } from "./StockPage";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let summaryAnswers: Array<() => Response>; let asked: number;

beforeEach(() => {
  vi.useFakeTimers();
  asked = 0;
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (String(url).includes("search-index")) return json(200, { fields: [], rows: [["QUESS", "Quess Corp Ltd", null, 0]] });
    if (/\/api\/stocks\/QUESS(\?|$)/.test(String(url))) { asked++; return (summaryAnswers[Math.min(asked - 1, summaryAnswers.length - 1)])(); }
    return json(404, {});
  }));
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

const open = () => render(
  <QueryClientProvider client={new QueryClient()}>
    <MemoryRouter initialEntries={["/stocks/QUESS"]}><Routes><Route path="/stocks/:symbol" element={<StockPage />} /></Routes></MemoryRouter>
  </QueryClientProvider>);
const settle = async (ms: number) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };

describe("opening a company with no stored report", () => {
  it("shows its name and the real part count while the server builds it, and asks again after one second", async () => {
    summaryAnswers = [() => json(202, { status: "queued", done: 4, total: 16, company: { name: "Quess Corp Ltd", sector: "Services" } })];
    open(); await settle(10);
    expect(screen.getByRole("heading", { name: "Quess Corp Ltd" })).toBeTruthy();
    expect(screen.getByText("Preparing this report")).toBeTruthy();
    expect(screen.getByText(/4 of 16 parts ready/)).toBeTruthy();
    expect(asked).toBe(1);
    await settle(1100); expect(asked).toBe(2);                    // 1 s, not the old 3 s
  });
  it("after about 45 seconds of asking it stops, says so and offers Try again", async () => {
    summaryAnswers = [() => json(202, { status: "queued", done: 2, total: 16 })];
    open(); await settle(60_000);
    expect(screen.getByText("This is taking longer than usual")).toBeTruthy();
    const n = asked; await settle(10_000); expect(asked).toBe(n);   // no endless polling
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
  it("a provider that did not answer ends at once with a clear message", async () => {
    summaryAnswers = [() => json(503, { status: "build_failed", detail: "x" })];
    open(); await settle(100);
    expect(screen.getByText("We could not build this report right now")).toBeTruthy();
    expect(asked).toBe(1);
  });
  it("the name comes from the company list while the first request is still being answered", async () => {
    summaryAnswers = [() => new Promise<Response>(() => {}) as unknown as Response];
    open(); await settle(50);
    expect(screen.getByRole("heading", { name: "Quess Corp Ltd" })).toBeTruthy();
    expect(screen.getByText("Opening the report")).toBeTruthy();
  });
});
