// @vitest-environment jsdom
// FII/DII page when DII exists only for the last 150 of 400 sessions (the live shape: NSDL's DII report begins on 1 Jun 2026): the Overall line and every
// total are over the sessions where both exist and say so, unpublished days are not drawn as "missing", and nothing is a part-sum under a whole-range label.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FlowDay, Flows } from "../lib/flows";
import { commonSpan, cumulative, diiGap } from "../lib/flowsMath";
import sample from "../lib/fixtures/flows.sample.json";

const st = vi.hoisted(() => ({ data: null as unknown }));
vi.mock("../lib/flows", async (orig) => ({ ...(await orig<typeof import("../lib/flows")>()), useFlows: () => ({ data: st.data, isLoading: false, isError: false, error: null }) }));
vi.mock("../lib/ui", () => ({ useUI: () => ({ toast: vi.fn(), plan: "basic" }) }));
vi.mock("../lib/title", () => ({ useDocTitle: () => undefined }));
import { FiiDiiPage } from "./FiiDii";

const base = sample as unknown as Flows;
function series(): FlowDay[] {
  const out: FlowDay[] = []; let t = Date.UTC(2025, 8, 1);
  while (out.length < 400) {
    const dt = new Date(t); t += 864e5;
    if (dt.getUTCDay() === 0 || dt.getUTCDay() === 6) continue;
    const i = out.length;
    out.push({ d: dt.toISOString().slice(0, 10), fii: { buy: null, sell: null, net: -10 }, dii: i >= 250 ? { buy: null, sell: null, net: 4 } : null });
  }
  return out;
}
const days = series(), first = days[250].d, last = days[399].d;
const payload = (): Flows => ({
  ...base, today: last, days, index: null, correlation: null, periods: [], monthly: [], yearly: [],
  latest: { d: last, fii: days[399].fii, dii: days[399].dii, combinedNet: -6, fiiShareOfSelling: null, mood: "Balanced" },
  streaks: { fii: null, dii: null }, last30: { fii: -300, dii: 120, days: 30 },
  coverage: { from: days[0].d, to: last, sessions: 400, diiSessions: 150, diiFrom: first, diiPublishedFrom: first, diiReason: "NSDL publishes the DII report from the start; earlier DII days are not available from any official free source." },
});
beforeEach(() => { st.data = payload(); vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(cleanup);

describe("helpers", () => {
  it("commonSpan counts only sessions with both sides", () => {
    expect(commonSpan(days)).toEqual({ from: first, to: last, n: 150, fii: -1500, dii: 600, overall: -900 });
    expect(commonSpan(days.slice(0, 250))).toBeNull();
  });
  it("Overall line starts at the first session with both and ends at the common total", () => {
    const all = cumulative(days, "all"); expect(all).toHaveLength(150); expect(all[0][0]).toBe(first); expect(all.at(-1)![1]).toBe(-900);
    expect(cumulative(days, "fii")).toHaveLength(400);
  });
  it("tells a day before the report from a missing one", () => { expect(diiGap("2026-05-29", "2026-06-01")).toBe("unpublished"); expect(diiGap("2026-06-02", "2026-06-01")).toBe("missing"); expect(diiGap("2026-05-29", null)).toBe("missing"); });
});

describe("page with 150 DII sessions of 400", () => {
  const open = () => render(<MemoryRouter><FiiDiiPage /></MemoryRouter>);
  it("labels the chart totals with their own period and never mixes them", () => {
    open();
    const sum = screen.getByLabelText("Totals for the range");
    expect(sum.textContent).toContain("FII (whole range)");
    expect(sum.textContent).toMatch(/Where DII exists.*\(150 sessions\)/);
    expect(sum.textContent).toContain("DII +₹600 Cr"); expect(sum.textContent).toContain("Overall −₹900 Cr"); expect(sum.textContent).toContain("FII −₹1,500 Cr");
    expect(sum.textContent).not.toContain("DII +₹1,600");
  });
  it("calendar: DII 1Y total is over the same sessions as FII, with a not-published key distinct from missing", () => {
    open();
    const cal = screen.getByRole("region", { name: /Daily flow calendar/ });
    expect(cal.textContent).toContain(`DII since`); expect(cal.textContent).toContain("+₹600 Cr"); expect(cal.textContent).toContain("same 150 sessions as DII: −₹1,500 Cr");
    expect(cal.textContent).toContain("not published"); expect(cal.textContent).toContain("missing session");
    const dii = within(cal).getByRole("group", { name: /DII flow by day/ });
    const un = [...dii.querySelectorAll('[data-n="2"]')]; expect(un.length).toBeGreaterThan(100); expect(un.every((c) => c.getAttribute("data-d")! < first)).toBe(true); expect(dii.querySelectorAll('[data-n="1"]').length).toBe(0);
    expect(dii.querySelector(`[data-d="${days[150].d}"]`)!.getAttribute("title")).toMatch(/No DII figure for this day: our daily DII feed starts on/);
    expect(cal.textContent).toContain("DII daily figures start on"); expect(cal.textContent).toContain("before that no daily DII series is available from our sources");
  });
  it("chart: every line states its own availability window, Overall is only where both exist", () => {
    open();
    const av = screen.getByLabelText("Data available for each series in this range");
    expect(av.textContent).toMatch(/FII: .*\d+ sessions/); expect(av.textContent).toMatch(/DII: .*150 sessions/); expect(av.textContent).toMatch(/only sessions with both\): .*150 sessions/);
    expect(av.textContent).toContain("DII daily figures start on");
    const chart = screen.getByRole("region", { name: /FII\/DII activities/ });
    expect(within(chart).getAllByText(/^(both sides, )?from /).length).toBe(2);
  });
  it("daily bars view for DII states the window too", () => {
    open();
    const chart = screen.getByRole("region", { name: /FII\/DII activities/ });
    fireEvent.click(within(chart).getByRole("radio", { name: "Daily net bars" })); fireEvent.click(within(chart).getByRole("radio", { name: "DII" }));
    expect(screen.getByLabelText("Data available for each series in this range").textContent).toMatch(/DII: .*150 sessions/);
  });
});
