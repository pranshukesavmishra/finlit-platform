// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const st = vi.hoisted(() => ({ status: 200, body: null as unknown, calls: [] as string[] }));
vi.mock("../lib/api", async (orig) => { const m = await orig<typeof import("../lib/api")>(); return { ...m, apiGet: vi.fn(async (p: string) => { st.calls.push(p); if (st.status !== 200) throw new m.ApiError(st.status, { status: "off" }); return st.body; }) }; });
import { MacroSectorImpact } from "./MacroSectorImpact";
import { MacroBackdrop } from "../stock/MacroBackdrop";

const sec = (key: string, name: string, score: number, label: string, reasons: string[]) => ({ key, name, score, label, raw: 0, reasons });
const BODY = { asOf: "2026-11-01", switchedOn: true, disclaimer: "Describes the macro backdrop of the company's sector from official data (MoSPI, RBI); not a view on the company and not a recommendation. Information only, not investment advice.", method: "m",
  signals: [{ key: "crude", label: "Crude", signal: null, reading: null, reason: "No three months of Brent prices are stored yet, so crude oil is left out." }],
  sectors: [sec("private_banks", "Private banks", 84.2, "Strong tailwind", ["Credit +", "Rate hikes +"]), sec("aviation", "Aviation", 54.49, "Neutral", ["No strong driver today"]), sec("fmcg", "FMCG", 4.7, "Strong headwind", ["Food CPI -", "WPI-CPI -"])] };
const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
beforeEach(() => { st.status = 200; st.calls = []; st.body = BODY; });
afterEach(cleanup);

describe("macro backdrop", () => {
  it("the sector table shows each score, label and reasons, rounded as the spec does, with real minus signs", async () => {
    wrap(<MacroSectorImpact />);
    await screen.findByText("Private banks");
    expect(screen.getByText("84")).toBeTruthy(); expect(screen.getByText("54")).toBeTruthy(); expect(screen.getByText("5")).toBeTruthy();
    expect(screen.getByText("Food CPI −, WPI−CPI −")).toBeTruthy();
    expect(screen.getByText(/not used: No three months of Brent prices/)).toBeTruthy();       // a missing indicator says why
  });
  it("a company line names its sector, or says why it has none; nothing at all when the server says off", async () => {
    st.body = { ...BODY, company: { symbol: "X", sectorKey: "fmcg", sector: BODY.sectors[2], industry: "Packaged Foods", reason: null } };
    const a = wrap(<MacroBackdrop symbol="X" />);
    await screen.findByText("Strong headwind");
    expect(a.container.textContent).toContain("FMCG · 5/100 · Food CPI −, WPI−CPI −");
    cleanup();
    st.body = { ...BODY, company: { symbol: "Y", sectorKey: null, sector: null, industry: "Diversified", reason: "This company's industry (Diversified) is not one of the 18 sectors the macro model covers." } };
    wrap(<MacroBackdrop symbol="Y" />);
    await screen.findByText(/not one of the 18 sectors/);
    cleanup(); st.status = 404; st.calls = [];
    const off = wrap(<MacroSectorImpact />);
    await vi.waitFor(() => expect(st.calls.length).toBe(1));
    expect(off.container.textContent).toBe("");
  });
  it("uses no advice wording", async () => {
    const { container } = wrap(<MacroSectorImpact />);
    await screen.findByText("Private banks");
    expect(container.textContent).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate|target|best)\b/i);
  });
});
