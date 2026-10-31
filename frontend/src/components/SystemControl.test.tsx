// @vitest-environment jsdom
// The admin System control: a time-boxed pause (30 min / 2 h / 12 h), the "Paused until 14:35 IST, resumes automatically" line, and resuming.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SystemControl } from "./SystemControl";
import { istClock, loadsText, pauseText } from "../lib/systemStatus";

const base = { bootEnvOff: false, fundEnvOff: false, memory: { totalMb: 1200, usedMb: 600, availableMb: 600 }, uptimeSeconds: 120, startedAt: "2026-10-31T08:00:00Z", pauseChoicesMinutes: [30, 120, 720], resumesAutomatically: true };
const m = vi.hoisted(() => ({ systemStatus: vi.fn(), systemLoads: vi.fn(), systemRestart: vi.fn() }));
vi.mock("../lib/account", () => m);

beforeEach(() => { m.systemStatus.mockReset(); m.systemLoads.mockReset(); });
afterEach(cleanup);
const open = async () => { render(<SystemControl />); fireEvent.click(screen.getByRole("button", { name: "System controls" })); await waitFor(() => expect(m.systemStatus).toHaveBeenCalled()); };

describe("pause text", () => {
  it("shows the end time in IST and says it resumes by itself", () => {
    const now = new Date("2026-10-31T08:00:00Z");                       // 13:30 IST
    expect(istClock("2026-10-31T09:05:00Z", now)).toBe("14:35 IST");
    expect(pauseText({ loadsEnabled: false, pausedUntil: "2026-10-31T09:05:00Z", pausedBy: null }, now)).toBe("Paused until 14:35 IST, resumes automatically.");
    expect(istClock("2026-11-01T01:00:00Z", now)).toBe("1 Nov 06:30 IST");               // another IST day: the date is shown too
    expect(pauseText({ loadsEnabled: true, pausedUntil: null, pausedBy: null }, now)).toBeNull();
    expect(pauseText({ loadsEnabled: false, pausedUntil: "2026-10-31T09:05:00Z", pausedBy: "a@b.c", pauseWasLegacy: true }, now)).toContain("An old switch with no end time");
    expect(loadsText({ loadsEnabled: true, bootEnvOff: false, fundEnvOff: false })).toBe("Heavy data loads are running.");
    expect(loadsText({ loadsEnabled: false, bootEnvOff: false, fundEnvOff: false })).toBe("Heavy data loads are paused.");
  });
});

describe("SystemControl", () => {
  it("offers 30 minutes, 2 hours and 12 hours and pauses for the chosen time", async () => {
    m.systemStatus.mockResolvedValue({ ...base, loadsEnabled: true });
    m.systemLoads.mockResolvedValue({ ...base, loadsEnabled: false, pausedUntil: new Date(Date.now() + 120 * 60000).toISOString(), pausedBy: "boss@example.com" });
    await open();
    const sel = await screen.findByRole("combobox", { name: "Pause length" }) as HTMLSelectElement;
    expect([...sel.options].map((o) => o.textContent)).toEqual(["30 minutes", "2 hours", "12 hours"]);
    expect(sel.value).toBe("30");
    fireEvent.change(sel, { target: { value: "120" } });
    fireEvent.click(screen.getByRole("switch", { name: "Heavy data loads" }));
    await waitFor(() => expect(m.systemLoads).toHaveBeenCalledWith(false, 120));
    expect(await screen.findByText(/^Paused until .* IST, resumes automatically\./)).toBeTruthy();
    expect((screen.getByRole("switch", { name: "Heavy data loads" }) as HTMLInputElement).checked).toBe(false);
  });

  it("pauses for 30 minutes by default", async () => {
    m.systemStatus.mockResolvedValue({ ...base, loadsEnabled: true });
    m.systemLoads.mockResolvedValue({ ...base, loadsEnabled: false, pausedUntil: new Date(Date.now() + 30 * 60000).toISOString() });
    await open();
    fireEvent.click(await screen.findByRole("switch", { name: "Heavy data loads" }));
    await waitFor(() => expect(m.systemLoads).toHaveBeenCalledWith(false, 30));
  });

  it("shows the paused line from the server and resumes at once when switched back on", async () => {
    m.systemStatus.mockResolvedValue({ ...base, loadsEnabled: false, pausedUntil: new Date(Date.now() + 20 * 60000).toISOString(), pausedBy: "boss@example.com" });
    m.systemLoads.mockResolvedValue({ ...base, loadsEnabled: true });
    await open();
    expect((await screen.findByTestId("loads-text")).textContent).toMatch(/^Paused until .* IST, resumes automatically\. Set by boss@example\.com\.$/);
    expect(screen.queryByRole("combobox", { name: "Pause length" })).toBeNull();      // no length to choose while paused
    fireEvent.click(screen.getByRole("switch", { name: "Heavy data loads" }));
    await waitFor(() => expect(m.systemLoads).toHaveBeenCalledWith(true, undefined));
    expect((await screen.findByTestId("loads-text")).textContent).toBe("Heavy data loads are running.");
  });

  it("says plainly that results, quotes and alerts are never paused", async () => {
    m.systemStatus.mockResolvedValue({ ...base, loadsEnabled: false, pausedUntil: new Date(Date.now() + 20 * 60000).toISOString() });
    await open();
    expect(await screen.findByText(/Results, quotes, alerts and report builds are never paused/)).toBeTruthy();
  });
});
