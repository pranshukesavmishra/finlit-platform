// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
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
  it("shows the backdrop bar: sentiment, sector, score out of 100, the two drivers with signs, and no how-it-works block", async () => {
    wrap();
    const bar = await screen.findByRole("group", { name: "Macro backdrop summary" });
    expect(within(bar).getByText("Tailwind")).toBeTruthy(); expect(within(bar).getByText("Private banks")).toBeTruthy(); expect(within(bar).getByText("74")).toBeTruthy(); expect(within(bar).getByText("/100")).toBeTruthy();
    expect(within(bar).getByText("Credit +")).toBeTruthy(); expect(within(bar).getByText("Deposits +")).toBeTruthy(); expect(screen.queryByText("How it works")).toBeNull(); expect(screen.queryByRole("button", { name: "How it works" })).toBeNull();
    expect(screen.getByText("MACRO & SECTOR OUTLOOK")).toBeTruthy();
  });
  it("Sector impact keeps only the row marked This company: no other sector, no show-all button, 50 marked on the bar", async () => {
    const { container } = wrap();
    await screen.findByText("Sector impact");
    await screen.findByText("This company");
    const rows = container.querySelectorAll(".mo-t tbody tr");
    expect(rows.length).toBe(1);
    expect(container.querySelector("tr.me th")?.textContent).toContain("Private banks");
    expect(container.querySelector(".mo-t .mo-bar u")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Show all|Show fewer/ })).toBeNull();
    expect(container.textContent).not.toContain("PSU banks");
    expect(container.querySelector(".mo-t")?.textContent).toContain("Credit +");
    expect(st.calls.some((c) => c.includes("sector-impact"))).toBe(false);          // the 35-sector table is not even requested for a one-sector company
  });
  it("Indicator signals show only the indicators that are a reason in Sector impact, each tied to its reason", async () => {
    const { container } = wrap();
    await screen.findByText("Indicator signals");
    const tiles = [...container.querySelectorAll(".mo-tile")].map((t) => t.getAttribute("data-reason"));
    expect(tiles).toEqual(["BANK_CREDIT", "DEPOSIT_GROWTH"]);                       // the two "Top reasons" pills, in their order, nothing generic
    expect(container.querySelectorAll('section.mo-grp').length).toBe(1);
    expect(container.querySelector('section[aria-label="Credit & Banking"]')).toBeTruthy();
    for (const g of ["Inflation", "Monetary Policy", "Economic Growth", "Currency", "Commodities"]) expect(container.querySelector(`section[aria-label="${g}"]`)).toBeNull();
    expect(container.querySelector(".mo-why")?.textContent).toContain("Credit, Deposits");
    expect(container.querySelector('[data-reason="BANK_CREDIT"] .mo-eff')?.textContent).toMatch(/^supports \+1\.45/);   // the effect the pill stands for
  });
  it("a revenue-weighted company shows each of its segment sectors as This company, and the indicators behind their reasons", async () => {
    const seg = (code: string, name: string, w: number) => ({ sector: code, name, weight: w, score: 60, label: "Tailwind", tone: "up", segments: name });
    st.company = { ...ok, mapping: { ...(ok as { mapping: object }).mapping, basis: "revenue_weighted", sector: "private_banks" }, segments: [seg("private_banks", "Private banks", 0.6), seg("psu_banks", "PSU banks", 0.4)] };
    const { container } = wrap();
    await screen.findByText("Sector impact");
    await screen.findAllByText("This company");
    expect([...container.querySelectorAll(".mo-t tbody th")].map((t) => t.textContent?.replace("This company", ""))).toEqual(expect.arrayContaining(["Private banks", "PSU banks"]));
    expect(container.querySelectorAll(".mo-t tbody tr").length).toBe(2);
    expect(st.calls.some((c) => c.includes("sector-impact"))).toBe(true);
    expect(container.querySelector(".mo-t")?.textContent).not.toContain("Capital goods");
  });
  it("with nothing named as a reason, Indicator signals says so instead of showing generic tiles", async () => {
    st.company = { ...ok, drivers: [] };
    const { container } = wrap();
    await screen.findByText("Indicator signals");
    expect(container.querySelectorAll(".mo-tile").length).toBe(0);
    expect(screen.getByText(/names no dominant driver for this sector right now/)).toBeTruthy();
  });
  it("an Insufficient Data company shows the missing readings that are the stated reason, with why they are missing", async () => {
    st.company = insufficient;
    const { container } = wrap();
    await screen.findByText("Indicator signals");
    const codes = [...container.querySelectorAll(".mo-tile")].map((t) => t.getAttribute("data-reason"));
    expect(codes).toContain("BRENT");
    expect(container.querySelector('[data-reason="BRENT"] .mo-miss')?.textContent).toMatch(/Missing/);
    expect(codes.length).toBeLessThan(8);
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
  it("has no How it works block, never loads the methodology, and still carries the disclaimer and the not-validated note", async () => {
    wrap(); await screen.findByRole("group", { name: "Macro backdrop summary" });
    expect(screen.queryByText("How it works")).toBeNull(); expect(screen.queryByText("Formula")).toBeNull();
    expect(st.calls.some((c) => c.includes("methodology"))).toBe(false);
    expect(screen.getAllByText(/not validated/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/not a company-specific assessment, forecast, or investment recommendation/)).toBeTruthy();
  });
  it("never uses advice wording", async () => {
    const { container } = wrap(); await screen.findByText("Sector impact");
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
