// @vitest-environment jsdom
// Brent crude (U.S. EIA) and monthly copper, aluminium, natural gas (World Bank) on the India macro page, and the Brent card on the Commodities page.
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Macro } from "../lib/macro";
import type { Commodities } from "../lib/commodities";

const st = vi.hoisted(() => ({ macro: null as unknown, cm: null as unknown }));
vi.mock("../lib/macro", async (orig) => ({ ...(await orig<typeof import("../lib/macro")>()), useMacro: () => ({ data: st.macro, isLoading: false, isError: false, error: null }) }));
vi.mock("../lib/commodities", async (orig) => ({ ...(await orig<typeof import("../lib/commodities")>()), useCommodities: () => ({ data: st.cm, isLoading: false, isError: false, error: null }) }));
vi.mock("../lib/ui", () => ({ useUI: () => ({ toast: vi.fn(), plan: "basic" }) }));
vi.mock("../lib/title", () => ({ useDocTitle: () => undefined }));
vi.mock("../components/MacroSectorImpact", () => ({ MacroSectorImpact: () => null }));
import { MacroPage } from "./Macro";
import { CommoditiesPage } from "./Commodities";

const pts = (n: number, base: number): [string, number][] => Array.from({ length: n }, (_, i) => [new Date(Date.UTC(2026, 9, 1 + i)).toISOString().slice(0, 10), base + i]);
const macro = (over: Partial<Macro> = {}): Macro => ({
  updatedAt: "2026-11-05T00:00:00Z", today: "2026-11-05", cards: [], insights: [], targetWatch: { target: 4, band: [2, 6], quarters: [], streak: 0, side: null, lastQuarter: null, rule: "" },
  series: {}, cpiDivisions: [], rates: null, reserves: null, decisions: [], coverage: [], runs: {}, issues: [], sources: [], disclaimer: "Information only.", ...over,
});
const brentCard = { key: "brent_d", label: "Brent crude, daily", value: 102, unit: "US$/bbl", date: "2026-11-03", period: "3 Nov 2026", prev: 100.5, prevPeriod: "2 Nov 2026", change: 1.5, changeUnit: "US$/bbl",
  yearAgo: null, source: "U.S. EIA", sourceUrl: null, what: null, spark: pts(10, 100) as [string, number][], lag: "U.S. EIA daily price, published 1-2 business days after the trading day" };
beforeEach(() => vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }));
afterEach(cleanup);

const renderMacro = () => render(<MemoryRouter><MacroPage /></MemoryRouter>);

describe("India macro page", () => {
  it("shows Brent with its price, date, source and the publication lag", () => {
    st.macro = macro({ cards: [brentCard as never] });
    renderMacro();
    const card = screen.getByRole("button", { name: /Brent crude, daily: US\$ 102\.00/ });
    expect(card.textContent).toContain("U.S. EIA");
    expect(card.textContent).toContain("3 Nov 2026");
    expect(card.textContent).toContain("published 1-2 business days");
  });
  it("says why there is no Brent or metal price instead of leaving a gap", () => {
    st.macro = macro({ brent: { status: "nokey", reason: "Brent: source key not set" }, metals: { copper_m: { label: "Copper, monthly", reason: "Not loaded yet: the macro job downloads the World Bank price file each night." } } });
    renderMacro();
    expect(screen.getByText("Brent: source key not set")).toBeTruthy();
    expect(screen.getByText(/Not loaded yet: the macro job downloads the World Bank/)).toBeTruthy();
  });
  it("offers Brent, copper and aluminium, and gas history tabs", () => {
    st.macro = macro({ cards: [brentCard as never] });
    renderMacro();
    for (const t of ["Brent crude", "Copper and aluminium", "Natural gas"]) expect(screen.getByRole("tab", { name: t })).toBeTruthy();
  });
});

const eia = (over: object = {}) => ({
  state: "ok", usd: "102.50", unit: "$ per barrel", date: "2026-11-03", prevDate: "2026-11-02", changePct: "2.50", source: "U.S. EIA", lag: "U.S. EIA, daily, 1-2 business day lag", note: null,
  inr: { value: "9,033", unit: "₹ per barrel", usdinr: "88.1234", usdinrDate: "2026-11-04", priceDate: "2026-11-03", label: "Conversion, not a quote: the EIA price at the FBIL USD/INR rate" }, ...over,
});
const cmData = (e: object): Commodities => ({
  asOf: "2026-11-05T10:00:00+05:30", status: "ok", market: { mcx: { open: false, opens: "09:00", closes: "23:30", hoursConfirmed: true, why: null }, global: { open: false } },
  sources: { mcx: { connected: false, label: "", error: null }, intl: { connected: false, metals: null, energy: null, errors: {} } }, fx: { state: "off", usdinr: null, asOf: null, vendor: null },
  assumptions: { k22: "", mcxGoldFineness: "", fineFineness: "", parity: "" }, ratio: { goldSilver: null}, worker: { ageSeconds: null },
  items: [{ code: "brent", name: "Brent crude", group: "energy", mcx: null, intl: [], parity: null, notes: [], eia: e as never }],
});

describe("Commodities page", () => {
  it("shows the Brent card with the dollar price, the rupee conversion with both dates, and the EIA source line", () => {
    st.cm = cmData(eia());
    render(<MemoryRouter><CommoditiesPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Brent crude" })).toBeTruthy();
    expect(screen.getByText("$102.50")).toBeTruthy();
    const body = document.body.textContent ?? "";
    expect(body).toContain("Conversion, not a quote");
    expect(body).toContain("88.1234 on 4 Nov 2026");
    expect(body).toContain("Brent of 3 Nov 2026");
    expect(body).toContain("U.S. EIA, daily, 1-2 day lag");
    expect(body).not.toMatch(/Dhan\)/);
  });
  it("shows only the reason when there is no price", () => {
    st.cm = cmData(eia({ state: "none", usd: null, inr: null, changePct: null, note: "Brent: source key not set" }));
    render(<MemoryRouter><CommoditiesPage /></MemoryRouter>);
    expect(screen.getByText("Brent: source key not set")).toBeTruthy();
    expect(screen.queryByText(/Conversion, not a quote/)).toBeNull();
  });
});
