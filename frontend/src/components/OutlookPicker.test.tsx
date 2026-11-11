// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const U = vi.hoisted(() => ({ rows: [] as unknown[] }));
vi.mock("../lib/screener", async (orig) => ({ ...(await orig<typeof import("../lib/screener")>()), useUniverse: () => ({ data: { rows: U.rows }, isLoading: false }) }));
vi.mock("./SearchFilters", () => ({ useIndexFilter: () => ({ idx: { data: {} }, search: (q: string) => (/rel/i.test(q) ? [["RELIANCE", "Reliance Industries Ltd", null, 1, "RELIANCE"]] : []) }) }));
import { OutlookPicker } from "./OutlookPicker";
import { pushRecent } from "../lib/outlookPick";

const Where = () => <output data-testid="loc">{useLocation().pathname}</output>;
const mount = (current?: string, intro = false) => render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={["/outlook"]}><Routes><Route path="*" element={<><OutlookPicker current={current} intro={intro} /><Where /></>} /></Routes></MemoryRouter></QueryClientProvider>);
beforeEach(() => { localStorage.clear(); U.rows = [{ symbol: "RELIANCE", name: "Reliance Industries Ltd", price: 1234.5, change_pct: 1.25, market_cap: 1650000, pe: 24.3, return_1y: -3.4 }, { symbol: "TCS", name: "Tata Consultancy Services", price: 4000, change_pct: -0.5, market_cap: 1400000, pe: null, return_1y: 10 }]; });
afterEach(cleanup);

describe("outlook company picker", () => {
  it("explains the simulator and offers the five quick picks, each with today's move", () => {
    mount(undefined, true);
    expect(screen.getByText(/estimates a company's/i)).toBeTruthy();
    const picks = within(screen.getByRole("list", { name: "Quick picks" })).getAllByRole("link");
    expect(picks.map((a) => a.querySelector("b")?.textContent)).toEqual(["Reliance", "TCS", "HDFC Bank", "Infosys", "ICICI Bank"]);
    expect(picks[0].textContent).toMatch(/\+1\.25%/); expect(picks[1].textContent).toMatch(/−0\.50%/); expect(picks[2].textContent).not.toMatch(/%/);   // no figure: no number
    expect(picks[0].getAttribute("href")).toBe("/outlook/RELIANCE");
  });
  it("shows a snapshot with dashes, never zeros, for missing figures; and the last searched companies", () => {
    pushRecent("TCS");
    mount();
    expect(document.querySelector(".olp-cap b")?.textContent).toBe("Tata Consultancy Services");                       // snapshot caption: the last company opened
    const snap = screen.getByLabelText(/at a glance/);
    expect(snap.textContent).toMatch(/₹4,000/); expect(within(snap).getByText("P/E").nextSibling?.textContent).toBe("−");
    expect(within(screen.getByRole("list", { name: "Last searched" })).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["/outlook/TCS"]);
  });
  it("searches by name and opens the first match on Enter", () => {
    mount();
    const box = screen.getByRole("searchbox");
    fireEvent.change(box, { target: { value: "relia" } });
    expect(screen.getByRole("link", { name: /Reliance Industries Ltd/ }).getAttribute("href")).toBe("/outlook/RELIANCE");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(screen.getByTestId("loc").textContent).toBe("/outlook/RELIANCE");
  });
  it("on a company page the current company is marked and not repeated under Last searched", () => {
    pushRecent("TCS"); pushRecent("RELIANCE");
    mount("RELIANCE");
    expect(screen.getByRole("heading", { name: "Change company" })).toBeTruthy();
    expect(within(screen.getByRole("list", { name: "Quick picks" })).getAllByRole("link")[0].getAttribute("aria-current")).toBe("page");
    expect(within(screen.getByRole("list", { name: "Last searched" })).getAllByRole("link")).toHaveLength(1);
  });
});
