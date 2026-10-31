// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, POLL_MAX_TRIES, pollDelayMs, retryDelayMs, shouldRetry } from "../lib/api";
import { PreparingReport, progressText } from "./PreparingReport";

afterEach(cleanup);
const show = (props: Partial<Parameters<typeof PreparingReport>[0]> = {}) =>
  render(<MemoryRouter><PreparingReport symbol="QUESS" name="Quess Corp Ltd" sector="Services" mode="building" done={3} total={16} {...props} /></MemoryRouter>);

describe("the waiting page of a company that is being built", () => {
  it("shows the company, a progress bar and a truthful part count, not a bare spinner", () => {
    show();
    expect(screen.getByRole("heading", { name: "Quess Corp Ltd" })).toBeTruthy();
    expect(screen.getByText("QUESS")).toBeTruthy();
    expect(screen.getByText("Preparing this report")).toBeTruthy();
    expect(screen.getByText(/Reading statements, ratios and prices… 3 of 16 parts ready/)).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("19");
  });
  it("does not promise 'a few seconds' and says what is stored afterwards", () => {
    const { container } = show();
    expect(container.textContent).not.toMatch(/few seconds/i);
    expect(container.textContent).toMatch(/not one of the companies we keep ready in advance/);
    expect(container.textContent).toMatch(/opens instantly/);
  });
  it("falls back to the symbol before the name is known", () => {
    show({ name: null });
    expect(screen.getByRole("heading", { name: "QUESS" })).toBeTruthy();
  });
  it("progress words follow the counts", () => {
    expect(progressText()).toMatch(/Contacting/);
    expect(progressText(0, 16)).toMatch(/Asking the data provider/);
    expect(progressText(5, 16)).toMatch(/5 of 16/);
    expect(progressText(16, 16)).toMatch(/All 16/);
  });
  it("ends in a clear failure with Try again, never an endless wait", () => {
    const retry = vi.fn();
    show({ mode: "failed", onRetry: retry });
    expect(screen.getByText("We could not build this report right now")).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });
  it("after the polling budget it says so and offers Try again", () => {
    show({ mode: "gaveUp", onRetry: () => {} });
    expect(screen.getByText("This is taking longer than usual")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
  it("keeps the same placeholder blocks in every state (nothing jumps)", () => {
    const a = show(); const n = a.container.querySelectorAll(".skeleton").length; a.unmount();
    const b = show({ mode: "failed" });
    expect(b.container.querySelectorAll(".skeleton").length).toBe(n);
  });
});

describe("how the page asks again", () => {
  const e = (status: number, body: ApiError["body"] = {}) => new ApiError(status, body);
  it("polls every second at first, then every two seconds", () => {
    expect([0, 1, 2, 3, 4].map(pollDelayMs)).toEqual([1000, 1000, 1000, 1000, 1000]);
    expect([5, 6, 20].map(pollDelayMs)).toEqual([2000, 2000, 2000]);
    expect(retryDelayMs(0, e(202, { retryAfter: 3 }))).toBe(1000);   // the server's Retry-After no longer slows the poll
  });
  it("gives up after about 45 seconds of asking", () => {
    let total = 0, n = 0;
    while (shouldRetry(n, e(202))) { total += pollDelayMs(n); n++; }
    expect(n).toBe(POLL_MAX_TRIES);
    expect(total).toBeGreaterThanOrEqual(40_000); expect(total).toBeLessThanOrEqual(50_000);
  });
  it("a provider failure is final at once; other server errors get two quick retries", () => {
    expect(shouldRetry(0, e(503, { status: "build_failed" }))).toBe(false);
    expect(shouldRetry(1, e(500))).toBe(true); expect(shouldRetry(2, e(500))).toBe(false);
    expect(shouldRetry(0, e(404))).toBe(false);
    expect(shouldRetry(7, e(429))).toBe(true); expect(shouldRetry(8, e(429))).toBe(false);
  });
});
