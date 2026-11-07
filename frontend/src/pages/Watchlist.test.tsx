// @vitest-environment jsdom
// Watchlist (task #32): the list is one table (company, industry, price, P/E, ROE, market cap, FinLit IQ, status, target, note, actions) under the strip of tiles.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Row } from "../lib/screener";

const R = (symbol: string, name: string, sector: string, overall: number, band: string, change: number, over: Partial<Row> = {}): Row => ({
  symbol, name, sector, overall, band, price: 100, market_cap: 50000, pe: 20, pb: 3, roe: 15, roce: 18, dividend_yield: 1, debt_to_equity: 0.2, sales_cagr: 8, profit_cagr: 9, operating_margin: 20,
  change_pct: change, return_1m: 1, return_1y: 10, pillar_quality: 60, pillar_growth: 60, pillar_profitability: 60, pillar_balance: 60, pillar_technical: 60, ...over,
} as unknown as Row);
const st = vi.hoisted(() => ({ rows: [] as unknown[], toast: vi.fn() }));
vi.mock("../lib/screener", async (orig) => ({ ...(await orig<typeof import("../lib/screener")>()), useUniverse: () => ({ data: { rows: st.rows, sample: false }, isLoading: false, isError: false, refetch: () => undefined }) }));
vi.mock("../lib/ui", async (orig) => ({ ...(await orig<typeof import("../lib/ui")>()), useUI: () => ({ has: () => true, toast: st.toast, upgrade: vi.fn(), plan: "gold" }) }));
vi.mock("../lib/auth", async (orig) => ({ ...(await orig<typeof import("../lib/auth")>()), useAuth: () => ({ user: { id: "u" } }) }));
vi.mock("../lib/title", () => ({ useDocTitle: () => undefined }));
vi.mock("../lib/api", async (orig) => ({ ...(await orig<typeof import("../lib/api")>()), useQuotesFor: () => ({ data: { rows: [] }, isLoading: false }) }));
vi.mock("../components/ChartHelp", () => ({ ChartHelp: () => null }));
vi.mock("../components/AlertComposer", () => ({ AlertButton: ({ symbol, className }: { symbol: string; className?: string }) => <button className={className} aria-label={`Create an alert for ${symbol}`} /> }));
import { WatchlistPage } from "./Watchlist";
import { watch } from "../lib/watchlist";

beforeEach(() => {
  localStorage.clear();
  st.rows = [R("TCS", "Tata Consultancy Services Ltd", "IT Services", 76, "healthy", 0.5), R("RCOM", "Reliance Communications Ltd", "Telecom", 26, "watch", -2, { pe: null, roe: -5 }), R("ITC", "ITC Ltd", "FMCG", 55, "mixed", 1)];
  st.toast.mockClear();
});
afterEach(cleanup);
const open = () => { for (const s of ["TCS", "RCOM", "ITC"]) watch.add(s); return render(<MemoryRouter><WatchlistPage /></MemoryRouter>); };

describe("Watchlist as a table", () => {
  it("shows one row per stock with the columns of the design", () => {
    open();
    const table = screen.getByRole("table", { name: /your stocks/i });
    for (const h of ["Company", "Industry", "Price", "P/E", "ROE", "Mkt cap", "FinLit IQ", "Status", "Target", "Your note", "Actions"]) expect(within(table).getByRole("columnheader", { name: new RegExp(h, "i") })).toBeTruthy();
    expect(within(table).getAllByRole("row").length).toBe(1 + 3);
    const tcs = within(table).getByText("Tata Consultancy Services Ltd").closest("tr") as HTMLElement;
    expect(within(tcs).getByText("76")).toBeTruthy(); expect(within(tcs).getByText("Healthy")).toBeTruthy(); expect(within(tcs).getByText("IT Services")).toBeTruthy();
  });
  it("sorts by FinLit IQ, highest first, and a header click changes the order", () => {
    open();
    const names = () => within(screen.getByRole("table")).getAllByRole("row").slice(1).map((r) => (within(r).getAllByRole("link")[0].textContent || ""));
    expect(names()[0]).toBe("TCS");
    fireEvent.click(screen.getByRole("button", { name: "Company" }));
    expect(names()[0]).toBe("ITC");
  });
  it("keeps targets, notes, alerts, removal and comparing working from the row", () => {
    open();
    const row = () => screen.getByText("ITC Ltd").closest("tr") as HTMLElement;
    fireEvent.change(within(row()).getByLabelText("ITC target price in rupees"), { target: { value: "120" } });
    expect((within(row()).getByLabelText("ITC target price in rupees") as HTMLInputElement).value).toBe("120");
    expect(within(row()).getByText(/to target/)).toBeTruthy();
    fireEvent.change(within(row()).getByLabelText("ITC note"), { target: { value: "dividends" } });
    expect((within(row()).getByLabelText("ITC note") as HTMLTextAreaElement).value).toBe("dividends");
    expect(within(row()).getByRole("button", { name: "Create an alert for ITC" })).toBeTruthy();
    fireEvent.click(within(row()).getByLabelText("Select ITC to compare")); fireEvent.click(within(screen.getByText("Tata Consultancy Services Ltd").closest("tr") as HTMLElement).getByLabelText("Select TCS to compare"));
    expect(screen.getByRole("button", { name: /Compare selected/ })).toBeTruthy();
    fireEvent.click(within(row()).getByRole("button", { name: "Remove ITC from this list" }));
    expect(screen.queryByText("ITC Ltd")).toBeNull();
  });
  it("still groups by industry when asked, with a header row for each group", () => {
    open();
    fireEvent.change(screen.getByLabelText(/Bucket by/i), { target: { value: "sector" } });
    expect(within(screen.getByRole("table")).getAllByText(/^1 stock$/).length).toBe(3);
  });
  it("names the page and its purpose in the header", () => {
    open();
    expect(screen.getByRole("heading", { name: "Watchlists" })).toBeTruthy();
    expect(screen.getByText(/Track and manage your shortlisted companies/)).toBeTruthy();
  });
});
