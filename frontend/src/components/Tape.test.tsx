// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Tape } from "./Tape";
import type { IndexFeed } from "../lib/indices";
const state = vi.hoisted(() => ({ data: undefined as IndexFeed | undefined, isLoading: false }));
vi.mock("../lib/indices", () => ({ useIndices: () => state }));
afterEach(() => { cleanup(); state.data = undefined; state.isLoading = false; });
const feed = (live = false): IndexFeed => ({ key: ["NIF50"], asOf: "2026-10-30", marketOpen: live, live,
  items: [{ code: "NIF50", name: "Nifty 50", close: 23053.1, changePct: null, points: null, open: null, high: null, low: null, pe: null, pb: null, divYield: null, date: "2026-10-30", group: "Broad market", exchange: "NSE", source: live ? "dhan" : "finedge" }] });
describe("global market ticker", () => {
  it("shows provider closes honestly and hides the looping copy from assistive technology", () => {
    state.data = feed();
    const { container } = render(<Tape />);
    expect(screen.getByText("Last close")).toBeTruthy();
    expect(screen.getAllByText("NIFTY 50")).toHaveLength(2);
    expect(container.querySelectorAll('.tape-group[aria-hidden="true"]')).toHaveLength(1);
    expect(container.querySelector('.tape-item')?.getAttribute('title')).toBe('FinEdge · 2026-10-30');
    expect(container.querySelector('.tape-item')?.textContent).not.toContain('0.00%');
  });
  it("labels live prices only for Dhan rows during the market session", () => {
    state.data = feed(true);
    const { rerender } = render(<Tape />);
    expect(screen.getByText("Live / close")).toBeTruthy();
    state.data = { ...feed(true), marketOpen: false };
    rerender(<Tape />);
    expect(screen.getByText("Last close")).toBeTruthy();
  });
  it("lets a reader pause and restart the moving strip", () => {
    state.data = feed();
    const { container } = render(<Tape />);
    fireEvent.click(screen.getByRole("button", { name: "Pause market ticker" }));
    expect(container.querySelector('.tape')?.classList.contains('is-paused')).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Play market ticker" }));
    expect(container.querySelector('.tape')?.classList.contains('is-paused')).toBe(false);
  });
  it("retains a clear global status while prices are loading or unavailable", () => {
    state.isLoading = true;
    const { rerender } = render(<Tape />);
    expect(screen.getByText("Loading prices…")).toBeTruthy();
    state.isLoading = false;
    rerender(<Tape />);
    expect(screen.getByText("Prices unavailable")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
