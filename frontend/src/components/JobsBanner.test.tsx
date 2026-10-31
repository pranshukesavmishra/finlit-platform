// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JobsBanner } from "./JobsBanner";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const show = (body: unknown, ok = true) => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok, status: ok ? 200 : 500, headers: new Headers({ "content-type": "application/json" }), json: async () => body, text: async () => JSON.stringify(body) } as Response);
  render(<QueryClientProvider client={new QueryClient()}><JobsBanner /></QueryClientProvider>);
};
const healthy = { healthy: true, overdue: [], resultsDelayed: false, dataFresh: true, supervisor: { alive: true }, pause: { paused: false }, disabledByConfig: [], jobs: [], data: { checkedAt: "2026-10-31T08:00:00Z", datasets: [] }, canary: { ok: true, mismatches: [] } };

describe("JobsBanner", () => {
  it("says everything is healthy", async () => {
    show(healthy);
    expect((await screen.findByTestId("jobs-banner")).textContent).toContain("Background jobs and data are healthy");
  });
  it("raises an alert listing the overdue job", async () => {
    show({ ...healthy, healthy: false, jobs: [{ name: "results", overdue: true, ageHours: 5, slaHours: 1.5, reason: "waiting for memory" }] });
    const b = await screen.findByRole("alert");
    expect(b.textContent).toContain("Background jobs need attention");
    expect(b.textContent).toContain("results is overdue: last success 5.0 h ago, promised every 1.5 h");
  });
});
