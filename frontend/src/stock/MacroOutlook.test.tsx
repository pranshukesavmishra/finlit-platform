// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ok from "../../public/demo/macro/company-ok.json";
import insufficient from "../../public/demo/macro/company-insufficient.json";
import impact from "../../public/demo/macro/impact.json";
import hist from "../../public/demo/macro/history-6M.json";
import method from "../../public/demo/macro/method.json";

const st = vi.hoisted(() => ({ company: null as unknown, calls: [] as string[], fail: false }));
vi.mock("../lib/api", async (orig) => { const m = await orig<typeof import("../lib/api")>(); return { ...m, apiGet: vi.fn(async (p: string) => {
  st.calls.push(p);
  if (p.includes("macro-outlook")) { if (st.fail) throw new m.ApiError(503, { status: "pending" }); return st.company; }
  if (p.includes("sector-impact")) return impact; if (p.includes("history")) return hist; if (p.includes("methodology")) return method; throw new m.ApiError(404, {});
}) }; });
import { MacroOutlookSection } from "./MacroOutlook";
import { driverText, signed, insufficientText, pct } from "../lib/macroOutlook";

const wrap = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MacroOutlookSection symbol="X" /></QueryClientProvider>);
beforeEach(() => { st.calls = []; st.fail = false; st.company = ok; });
afterEach(cleanup);

describe("Macro & Sector Outlook section", () => {
  it("shows the backdrop bar: sentiment, sector, score out of 100, the two drivers with signs, and the how-it-works link", async () => {
    wrap();
    const bar = await screen.findByRole("group", { name: "Macro backdrop summary" });
    expect(within(bar).getByText("Tailwind")).toBeTruthy(); expect(within(bar).getByText("Private banks")).toBeTruthy(); expect(within(bar).getByText("74")).toBeTruthy(); expect(within(bar).getByText("/100")).toBeTruthy();
    expect(within(bar).getByText("Credit +")).toBeTruthy(); expect(within(bar).getByText("Deposits +")).toBeTruthy(); expect(within(bar).getByRole("button", { name: "How it works" })).toBeTruthy();
    expect(screen.getByText("MACRO & SECTOR OUTLOOK")).toBeTruthy();
  });
  it("highlights the viewed company's sector, marks 50 on every bar and expands to all sectors", async () => {
    const { container } = wrap();
    await screen.findByText("Sector impact");
    await screen.findByText("This company");
    expect(container.querySelector("tr.me th")?.textContent).toContain("Private banks");
    expect(container.querySelectorAll(".mo-t .mo-bar u").length).toBeGreaterThanOrEqual(6);
    const rows = () => container.querySelectorAll(".mo-t tbody tr").length;
    const before = rows(); fireEvent.click(screen.getByRole("button", { name: /Show all 35 sectors/ }));
    expect(rows()).toBe(35); expect(before).toBeLessThan(35);
    const scores = [...container.querySelectorAll(".mo-t td.num")].map((n) => Number(n.textContent)).filter((n) => !Number.isNaN(n));
    expect(scores).toEqual([...scores].sort((a, b) => b - a));                         // sorted by score, highest first
  });
  it("groups the indicator tiles and states a missing indicator's reason instead of a number", async () => {
    const { container } = wrap();
    await screen.findByText("Indicator signals");
    for (const g of ["Inflation", "Monetary Policy", "Credit & Banking", "Economic Growth", "Currency", "Commodities"]) expect(container.querySelector(`section[aria-label="${g}"]`)).toBeTruthy();
    expect(screen.getAllByText(/Missing: no price history stored/).length).toBe(4);
    expect(screen.getByText(/Stale: \d+ days since the observation date/)).toBeTruthy();
    expect(screen.getAllByText(/MoSPI/).length).toBeGreaterThan(3);
  });
  it("Insufficient Data says why and never shows a score", async () => {
    st.company = insufficient;
    const { container } = wrap();
    const bar = await screen.findByRole("group", { name: "Macro backdrop summary" });
    expect(within(bar).getByText("Insufficient Data")).toBeTruthy(); expect(within(bar).getByText("—")).toBeTruthy();
    expect(screen.getAllByText(/Insufficient Data: missing critical: Brent crude/).length).toBeGreaterThan(0);
    expect(container.querySelector(".mo-bar-a .mo-bar i")?.getAttribute("style")).toContain("width: 0");
  });
  it("shows a stale warning above the score", async () => {
    st.company = { ...ok, stale: { isStale: true, since: "2026-11-01", message: "Not refreshed for 61 hours. Showing the last successful snapshot.", reason: "overdue" } };
    wrap();
    expect((await screen.findByRole("alert")).textContent).toContain("Not refreshed for 61 hours");
  });
  it("an unmapped company or an unavailable service shows a reason, not an empty box", async () => {
    st.company = { status: "not_mapped", reason: "no label-map rule matches its Sector 'X'", symbol: "X", company: "X", modelVersion: 1, stale: { isStale: false }, disclaimer: "" };
    wrap(); expect(await screen.findByText(/no label-map rule matches/)).toBeTruthy(); cleanup();
    st.fail = true; wrap(); expect(await screen.findByText(/unavailable right now/)).toBeTruthy();
  });
  it("How it works loads the methodology only when opened and carries the disclaimer and the not-validated note", async () => {
    wrap();
    const bar = await screen.findByRole("group", { name: "Macro backdrop summary" });
    expect(st.calls.some((c) => c.includes("methodology"))).toBe(false);
    fireEvent.click(within(bar).getByRole("button", { name: "How it works" }));
    expect(await screen.findByText("Formula")).toBeTruthy();
    expect(screen.getAllByText(/tanh/).length).toBeGreaterThan(0); expect(screen.getAllByText(/not validated/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/not a company-specific assessment, forecast, or investment recommendation/)).toBeTruthy();
  });
  it("never uses advice wording", async () => {
    const { container } = wrap(); await screen.findByText("Sector impact");
    fireEvent.click(screen.getByRole("button", { name: "How it works" })); await screen.findByText("Formula");
    expect(container.textContent).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate|target|best|multibagger|top pick)\b/i);
  });
});

describe("helpers", () => {
  it("formats signs with a real minus and builds driver text", () => {
    expect(signed(0.4)).toBe("+0.40"); expect(signed(-0.4)).toBe("−0.40"); expect(signed(null)).toBe("—");
    expect(driverText({ code: "REPO_RATE", name: "Repo rate", contribution: -1, sign: "-", value: 5.5, unit: "%", valueText: "5.5%" })).toBe("Repo rate −");
    expect(insufficientText({ reason: "missing Brent crude" })).toBe("Insufficient Data: missing Brent crude"); expect(pct(120)).toBe(100); expect(pct(null)).toBe(0);
  });
});
