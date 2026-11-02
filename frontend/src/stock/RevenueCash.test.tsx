// @vitest-environment jsdom
// Revenue-to-Cash Intelligence card: the Gold lock (nothing worked out is drawn), the lender state, the figures and wording on the page, the table view,
// the tooltips and the chart's gaps. The financials and the plan are stubbed.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { Table } from "../lib/api";

const st = vi.hoisted(() => ({ fin: null as unknown, gold: true, enabled: [] as boolean[] }));
vi.mock("../lib/api", async (orig) => ({ ...(await orig<typeof import("../lib/api")>()), useSection: (_s: string, _n: string, en: boolean) => { st.enabled.push(en); return { data: en ? st.fin : undefined }; } }));
vi.mock("../lib/ui", () => ({
  TIER: { basic: { n: "Basic", ic: "sprout", tc: "--t-basic" }, silver: { n: "Silver", ic: "medal", tc: "--t-silver" }, gold: { n: "Gold", ic: "crown", tc: "--t-gold" } },
  useUI: () => ({ has: (t: string) => t !== "gold" || st.gold, upgrade: () => undefined, plan: st.gold ? "gold" : "basic" }),
}));
vi.mock("react-router", () => ({ Link: ({ children }: { children: React.ReactNode }) => <a href="/plans">{children}</a> }));
import { OpenAccess } from "../components/Gate";
import { DISCLAIMER, RevenueCash, niceTicks } from "./RevenueCash";

const t = (periods: string[], rows: Record<string, (number | null)[]>) => ({ unit: "Cr", period: "yearly", periods, periodEnds: periods, rows }) as Table;
const P = ["FY20", "FY21", "FY22", "FY23", "FY24", "FY25", "FY26"];
/** The spec's company: revenue +57.9%, OCF margin −6.4%, receivables +89%, inventory +102.3% in the latest year. */
const FIN = {
  yearly: {
    pl: t(P, { revenue: [1000, 1000, 1000, 1000, 1000, 1000, 1579], net_profit: [80, 80, 80, 80, 80, 80, 90] }),
    bs: t(P, { receivables: [null, null, null, null, null, 100, 189], inventories: [null, null, null, null, null, 100, 202.3], fixed_assets: Array(7).fill(500), cwip: Array(7).fill(20) }),
    cf: t(P, { operating: [80, 80, 80, 80, 80, 80, -101], capex: Array(7).fill(-40), free_cash_flow: [40, 40, 40, 40, 40, 40, -141] }),
  },
  quarterly: { pl: t(["Q1", "Q2"], { revenue: [1, 1e9], net_profit: [1, 1] }) },
};
beforeAll(() => { (globalThis as { ResizeObserver?: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }; });
afterEach(() => { cleanup(); st.gold = true; st.fin = FIN; st.enabled.length = 0; });
const show = (lender = false, open = false, labels?: string[]) => render(<OpenAccess.Provider value={open}><RevenueCash symbol="X" lender={lender} labels={labels} /></OpenAccess.Provider>);

describe("Revenue-to-Cash Intelligence card", () => {
  it("has the title, the line under it, the Gold tag and the section id the nav jumps to", () => {
    st.fin = FIN;
    const { container } = show();
    expect(screen.getByRole("heading", { name: /Revenue turning into cash/ })).toBeTruthy();
    expect(screen.getByText("Understand how efficiently sales convert into cash.")).toBeTruthy();
    expect(container.querySelector("#revenue-cash")).toBeTruthy();
    expect(container.querySelector(".tier.gold")?.textContent).toBe("Gold");
  });
  it("shows the headline −6.4% with 'Needs attention' as a shape and a word", () => {
    st.fin = FIN; const { container } = show();
    expect(container.querySelector(".rcx-big")?.textContent).toBe("−6.4%");
    expect(screen.getByText("Operating cash flow / Revenue · FY26")).toBeTruthy();
    const pill = container.querySelector(".rcx-pill")!;
    expect(pill.textContent).toContain("Needs attention"); expect(pill.querySelector("[aria-hidden]")?.textContent).toBe("✕");
    expect(screen.getByText(/Industry benchmark not available/)).toBeTruthy();
  });
  it("shows the four indicators with ▲/▼ and the U+2212 minus", () => {
    st.fin = FIN; const { container } = show();
    const tiles = [...container.querySelectorAll(".rcx-tile")].map((x) => x.querySelector(".rcx-tv")!.textContent);
    expect(tiles).toEqual(["▲ +57.9%", "▼ −6.4%", "▲ +89.0%", "▲ +102.3%"]);
    expect(container.textContent).not.toMatch(/-[0-9]/);
  });
  it("says in a tooltip which balances the growth was measured on", () => {
    st.fin = FIN; const { container } = show();
    const tips = [...container.querySelectorAll("[role=tooltip]")].map((x) => x.textContent);
    expect(tips[2]).toMatch(/year-end balances/); expect(tips[3]).toMatch(/year-end balances/);
    expect(container.querySelectorAll(".rcx-i")).toHaveLength(4);
    const btn = screen.getByRole("button", { name: "About Receivables growth" });
    expect(btn.getAttribute("aria-describedby")).toBe(container.querySelectorAll("[role=tooltip]")[2].id);
  });
  it("lists the warnings with severity as text and a marker, the numbers, and an Investigate hint", () => {
    st.fin = FIN; const { container } = show();
    const items = [...container.querySelectorAll(".rcx-w")];
    expect(items.map((x) => x.querySelector(".rcx-wh > b")!.textContent)).toEqual(["Revenue is not generating positive operating cash", "Sales growth is not translating into cash", "Customer collection risk", "Inventory accumulation risk", "Earnings have weak cash backing"]);
    const rec = items.find((x) => /Customer collection risk/.test(x.textContent!))!;
    expect(rec.querySelector(".rcx-sev")!.textContent).toBe("◆High");
    expect(rec.textContent).toContain("Receivables grew 89.0%, exceeding revenue growth (57.9%) by 31.1 percentage points.");
    expect(rec.textContent).toContain("Investigate: customer collections and debtor days");
    const sales = items.find((x) => /Sales growth is not/.test(x.textContent!))!;
    expect(sales.querySelector(".rcx-sev")!.textContent).toBe("■Critical"); expect(sales.textContent).toContain("Investigate: working capital requirements and customer collections");
    expect(sales.textContent).toContain("This year only");
  });
  it("writes 'Reading the numbers' and 'What to investigate next' from the warnings, then the disclaimer", () => {
    st.fin = FIN; const { container } = show();
    expect(screen.getByRole("heading", { name: "Reading the numbers" })).toBeTruthy();
    expect(container.textContent).toContain("Revenue expansion is strong, but cash conversion is weak.");
    expect(container.textContent).toContain("Rising receivables and inventory may be contributing to working capital pressure.");
    expect(screen.getByRole("heading", { name: "What to investigate next" })).toBeTruthy();
    expect(container.textContent).toContain("Debtor days, inventory days, operating cash flow trend and cash flow from operations over the last five years.");
    expect(screen.getByText(DISCLAIMER)).toBeTruthy();
    expect(DISCLAIMER).toBe("Describes cash conversion from the company's filings; not a recommendation. Information only, not investment advice.");
    expect(container.textContent).not.toMatch(/Investor interpretation/);
  });
  it("never reads quarterly figures (a huge quarterly revenue changes nothing)", () => {
    st.fin = FIN; const { container } = show();
    expect(container.querySelector(".rcx-big")?.textContent).toBe("−6.4%");
  });
});

describe("trend chart", () => {
  it("draws two lines, a zero line, direct labels and a hover/focus tooltip per year", () => {
    st.fin = FIN; const { container } = show();
    const svg = container.querySelector(".rcx-chart svg")!;
    expect(svg.querySelectorAll(".rcx-l-rev").length).toBeGreaterThanOrEqual(1); expect(svg.querySelectorAll(".rcx-l-ocf").length).toBeGreaterThanOrEqual(1);
    expect(svg.querySelector(".rcx-zero")).toBeTruthy();
    expect([...svg.querySelectorAll(".rcx-ax")].map((x) => x.textContent)).toContain("0%");
    expect([...svg.querySelectorAll(".rcx-dl")].map((x) => x.textContent)).toEqual(["Revenue growth+57.9%", "OCF margin−6.4%"]);
    const hits = svg.querySelectorAll(".rcx-hit"); expect(hits).toHaveLength(5);
    fireEvent.focus(hits[4]);
    const tip = container.querySelector(".rcx-tip")!; expect(tip.textContent).toContain("FY26"); expect(tip.textContent).toContain("+57.9%"); expect(tip.textContent).toContain("−6.4%");
    fireEvent.blur(hits[4]); expect(container.querySelector(".rcx-tip")).toBeNull();
    fireEvent.mouseEnter(hits[2]); expect(container.querySelector(".rcx-tip")!.textContent).toContain("FY24");
  });
  it("'Show as table' opens the same numbers as a table, and hides it again", () => {
    st.fin = FIN; show();
    const link = screen.getByRole("button", { name: "Show as table" }); expect(link.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(link);
    const tbl = screen.getByRole("table"); const rows = within(tbl).getAllByRole("row");
    expect(rows).toHaveLength(6); expect(rows[5].textContent).toBe("FY26+57.9%−6.4%₹1,579 crore−₹101 crore");
    expect(screen.getByRole("button", { name: "Hide table" }).getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Hide table" })); expect(screen.queryByRole("table")).toBeNull();
  });
  it("a missing year is a gap and 'n/a' in the table, never 0", () => {
    st.fin = { ...FIN, yearly: { ...FIN.yearly, cf: t(P, { operating: [80, 80, 80, null, 80, 80, 80], capex: Array(7).fill(-40), free_cash_flow: Array(7).fill(40) }) } };
    const { container } = show();
    expect(container.querySelectorAll(".rcx-l-ocf").length).toBe(2);   // two separate segments around the hole
    fireEvent.click(screen.getByRole("button", { name: "Show as table" }));
    const row = within(screen.getByRole("table")).getAllByRole("row").find((r) => r.textContent!.startsWith("FY23"))!;
    expect(row.textContent).toBe("FY230.0%n/a₹1,000 croren/a");
  });
  it("the axis always contains zero and uses round ticks", () => {
    expect(niceTicks(-6.4, 57.9)).toEqual([-20, 0, 20, 40, 60]); expect(niceTicks(3, 8)[0]).toBe(0); expect(niceTicks(-8, -2).at(-1)).toBe(0);
    for (const [lo, hi] of [[-6.4, 57.9], [0.2, 0.9], [-500, 10], [0, 0]]) { const k = niceTicks(lo, hi); expect(k[0]).toBeLessThanOrEqual(Math.min(0, lo)); expect(k.at(-1)!).toBeGreaterThanOrEqual(Math.max(0, hi)); expect(k).toContain(0); }
  });
});

describe("plan and lenders", () => {
  it("non-Gold: header and lock only, nothing worked out is in the page and the data is not even requested", () => {
    st.gold = false; st.fin = FIN;
    const { container } = show();
    expect(screen.getByRole("heading", { name: /Revenue turning into cash/ })).toBeTruthy();
    expect(container.querySelector(".gate.is-locked")).toBeTruthy();
    expect(screen.getByText("Unlock with Gold")).toBeTruthy();
    expect(container.textContent).not.toMatch(/57\.9|6\.4|89\.0|102\.3|Customer collection risk|crore/);
    expect(container.querySelector(".rcx-big")).toBeNull();
    expect(st.enabled.every((e) => e === false)).toBe(true);
  });
  it("the free example company (open access) is not locked", () => {
    st.gold = false; st.fin = FIN;
    const { container } = show(false, true);
    expect(container.querySelector(".rcx-big")?.textContent).toBe("−6.4%");
  });
  it("lenders: 'Not comparable for lenders' instead of the card contents", () => {
    st.fin = FIN; const { container } = show(true);
    expect(screen.getByText("Not comparable for lenders")).toBeTruthy();
    expect(container.querySelector(".rcx-big")).toBeNull(); expect(container.querySelector(".rcx-chart")).toBeNull(); expect(container.querySelector(".rcx-w")).toBeNull();
    expect(container.textContent).not.toMatch(/crore|%/);
  });
  it("an insurer named by its industry is also shown as not comparable", () => {
    st.fin = FIN; show(false, false, ["Financial Services", "Life Insurance"]);
    expect(screen.getByText("Not comparable for lenders")).toBeTruthy();
  });
  it("an EPC company gets its industry caveat on the card", () => {
    st.fin = FIN; const { container } = show(false, false, ["Industrials", "Construction"]);
    expect(container.querySelector(".rcx-caveat")?.textContent).toMatch(/Project and EPC/);
  });
  it("no data at all: says so instead of drawing an empty card", () => {
    st.fin = { yearly: { pl: t(P, { revenue: Array(7).fill(null) }), bs: t(P, {}), cf: t(P, {}) } };
    show(); expect(screen.getByText(/not reported for enough years/)).toBeTruthy();
  });
});
