// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Row } from "../lib/screener";

const st = vi.hoisted(() => ({ plan: "gold" as "basic" | "silver" | "gold", rows: [] as unknown[] }));
vi.mock("../lib/ui", () => ({ useUI: () => ({ toast: vi.fn(), plan: st.plan, upgrade: vi.fn(), has: (t: string) => t === "basic" || (t === "silver" && st.plan !== "basic") || (t === "gold" && st.plan === "gold") }), TIER: { basic: { n: "Basic", ic: "sprout", tc: "--t-basic" }, silver: { n: "Silver", ic: "medal", tc: "--t-silver" }, gold: { n: "Gold", ic: "crown", tc: "--t-gold" } } }));
vi.mock("../lib/screener", async (orig) => ({ ...(await orig<typeof import("../lib/screener")>()), useUniverse: () => ({ data: { rows: st.rows, sample: true }, isLoading: false, isError: false }) }));
import { Compare } from "./Compare";

const base = { sector: "Energy", price: 100, change_pct: 1, market_cap: 1000, pe: 10, roe: 12, debt_to_equity: 0.5, overall: 66, band: "healthy", pillar_quality: 60, pillar_growth: 50, pillar_profitability: 55, pillar_balance: 70, pillar_technical: 40 };
const row = (sym: string, prism: number | null): Row => ({ ...base, symbol: sym, name: sym + " Ltd", prism_final: prism, prism_label: prism == null ? null : prism >= 65 ? "HEALTHY" : "AVERAGE", prism_status: prism == null ? null : "RATED", prism_state: prism == null ? "none" : "stored", prism_fundamental: prism, prism_valuation: prism, prism_quality: prism, prism_risk: prism } as unknown as Row);
const view = () => render(<MemoryRouter initialEntries={["/compare?c=AAA,BBB"]}><Compare /></MemoryRouter>);

beforeEach(() => { st.rows = [row("AAA", 71), row("BBB", null), row("CCC", 55)]; });
afterEach(cleanup);

describe("Compare: FinLit IQ and FinLit Prism (task #13)", () => {
  it("Gold sees both models as separate toggles; IQ alone is on at first, so the existing layout is unchanged", () => {
    st.plan = "gold"; const { container } = view();
    const iq = screen.getByRole("button", { name: "FinLit IQ" }), pr = screen.getByRole("button", { name: "FinLit Prism" });
    expect(iq.getAttribute("aria-pressed")).toBe("true"); expect(pr.getAttribute("aria-pressed")).toBe("false");
    expect(container.querySelectorAll(".cc-prism")).toHaveLength(0);
    expect(container.querySelectorAll(".cc-s")).toHaveLength(2);
  });
  it("turning Prism on adds its score and parts card; both can be on, either can be off, and one always stays on", () => {
    st.plan = "gold"; const { container } = view();
    fireEvent.click(screen.getByRole("button", { name: "FinLit Prism" }));
    expect(container.querySelectorAll(".cc-prism")).toHaveLength(2);
    expect(container.textContent).toContain("The FinLit Prism parts");
    expect(container.textContent).toContain("The five FinLit pillars");                   // IQ is still on
    fireEvent.click(screen.getByRole("button", { name: "FinLit IQ" }));                    // IQ off: Prism only
    expect(container.textContent).not.toContain("The five FinLit pillars");
    expect(container.querySelectorAll(".cc-s:not(.cc-prism)")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "FinLit Prism" }));                 // the last one cannot be switched off
    expect(screen.getByRole("button", { name: "FinLit Prism" }).getAttribute("aria-pressed")).toBe("true");
  });
  it("a company with no stored Prism rating says so instead of a number", () => {
    st.plan = "gold"; const { container } = view();
    fireEvent.click(screen.getByRole("button", { name: "FinLit Prism" }));
    const cards = [...container.querySelectorAll(".cc-prism")].map((c) => c.textContent);
    expect(cards[0]).toContain("71"); expect(cards[1]).toContain("Not rated yet");
  });
  it("Silver sees only FinLit IQ: no model toggle and no Prism anywhere", () => {
    st.plan = "silver"; const { container } = view();
    expect(screen.queryByRole("button", { name: "FinLit Prism" })).toBeNull();
    expect(container.querySelectorAll(".cmp-models")).toHaveLength(0);
    expect(container.querySelector(".cmp-cards")!.textContent).not.toContain("FinLit Prism");   // (the page header names Prism as a link, so only the comparison is checked)
    expect(container.textContent).not.toContain("The FinLit Prism parts");
    expect(container.querySelector(".cmp-cards")!.textContent).toContain("FinLit IQ");
  });
});
