// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UpdateBanner } from "./UpdateBanner";
import { APP_VERSION, type ServerVersion } from "../lib/version";

// vite.config injects this bundle's version (the git sha) into tests too, so "same" and "newer" are relative to it.
const same: ServerVersion = { version: APP_VERSION, builtAt: "" };
const newer: ServerVersion = { version: "zzz9999", builtAt: "2026-10-31T08:00:00Z" };
const setHidden = (h: boolean) => { Object.defineProperty(document, "hidden", { configurable: true, get: () => h }); };
beforeEach(() => { vi.useFakeTimers(); setHidden(false); sessionStorage.clear(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });
const flush = async () => { await act(async () => { await vi.advanceTimersByTimeAsync(0); }); };

describe("UpdateBanner", () => {
  it("is hidden while the server runs the same version", async () => {
    render(<UpdateBanner fetchFn={vi.fn().mockResolvedValue(same)} enabled />); await flush();
    expect(screen.queryByRole("status")).toBeNull();
  });
  it("appears with role=status, offers Refresh and Dismiss, and remembers the dismissal per version", async () => {
    expect(APP_VERSION).not.toBe("dev");
    const fn = vi.fn().mockResolvedValue(newer);
    render(<UpdateBanner fetchFn={fn} enabled />); await flush();
    expect(screen.getByRole("status").textContent).toContain("A new version of FinLit is available. Refresh to get it.");
    expect(screen.getByRole("button", { name: "Refresh" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Dismiss/ }));
    expect(screen.queryByRole("status")).toBeNull();
    expect(sessionStorage.getItem("finlit-update-dismissed")).toBe("zzz9999");
    cleanup();
    render(<UpdateBanner fetchFn={fn} enabled />); await flush();
    expect(screen.queryByRole("status")).toBeNull();   // still dismissed for this version
  });
  it("polls on mount, on focus (throttled), when the tab becomes visible, every ~5 minutes, and never while hidden", async () => {
    const fn = vi.fn().mockResolvedValue(same);
    render(<UpdateBanner fetchFn={fn} enabled />); await flush();
    expect(fn).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(31_000); }); window.dispatchEvent(new Event("focus")); await flush();
    expect(fn).toHaveBeenCalledTimes(2);
    window.dispatchEvent(new Event("focus")); await flush();
    expect(fn).toHaveBeenCalledTimes(2);                  // straight away again: throttled
    setHidden(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(400_000); });
    expect(fn).toHaveBeenCalledTimes(2);                  // timer fired while hidden: nothing asked
    setHidden(false); document.dispatchEvent(new Event("visibilitychange")); await flush();
    expect(fn).toHaveBeenCalledTimes(3);                  // visible again: checked at once
    await act(async () => { await vi.advanceTimersByTimeAsync(361_000); });
    expect(fn.mock.calls.length).toBeGreaterThanOrEqual(4);   // the 5-minute timer
  });
  it("shows the same bar when a page file failed to load and the one automatic reload is already used", async () => {
    render(<UpdateBanner fetchFn={vi.fn().mockResolvedValue(same)} enabled />); await flush();
    expect(screen.queryByRole("status")).toBeNull();
    await act(async () => { window.dispatchEvent(new Event("finlit:stale-assets")); });
    expect(screen.getByRole("status")).toBeTruthy();
  });
});
