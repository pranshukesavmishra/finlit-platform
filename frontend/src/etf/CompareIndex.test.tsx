// @vitest-environment jsdom
// ETF vs index fund page: the selectors, the address state, the six sections with their reasons, collapsible sections, and a scan of every word on the page for advice-like language.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { COMPARE, OPTIONS } from "../lib/__fixtures__/etfVsIndex";

const st = vi.hoisted(() => ({ compare: null as unknown, queries: [] as string[] }));
vi.mock("../lib/etfVsIndex", async (orig) => ({
  ...(await orig<typeof import("../lib/etfVsIndex")>()),
  useEviOptions: () => ({ data: OPTIONS, isError: false, refetch: () => undefined }),
  useEviCompare: (s: unknown, enabled: boolean) => { st.queries.push(JSON.stringify([s, enabled])); return { data: enabled ? st.compare : undefined, isError: false, error: null, refetch: () => undefined }; },
}));
vi.mock("../lib/title", () => ({ useDocTitle: () => undefined }));
import { EtfVsIndexPage } from "./CompareIndex";

const Where = () => { const l = useLocation(); return <output data-testid="loc">{l.pathname + l.search}</output>; };
const open = (qs = "") => render(<MemoryRouter initialEntries={["/etfs/compare-index-funds" + qs]}><Routes><Route path="/etfs/compare-index-funds" element={<EtfVsIndexPage />} /></Routes><Where /></MemoryRouter>);
const loc = () => decodeURIComponent(screen.getByTestId("loc").textContent || "");
beforeEach(() => {
  st.compare = COMPARE; st.queries = [];
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

describe("choosing products", () => {
  it("starts empty with the Compare button off, and explains what will appear", () => {
    open();
    expect(screen.getByRole("heading", { name: /ETF vs Index Fund/ })).toBeTruthy();
    expect((screen.getByRole("button", { name: "Compare products" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Choose at least one ETF and one index fund/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Comparison dashboard" })).toBeTruthy();
    expect((screen.getByLabelText("Select benchmark") as HTMLSelectElement).value).toBe("nifty50");
    expect(screen.getByRole("option", { name: /BSE SENSEX/ }).hasAttribute("disabled")).toBe(true);     // an index with no index fund is listed but cannot be chosen
  });
  it("lists only the products of the chosen index, adds them and puts the choice in the address on Compare", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: /Select ETF/ }));
    const etfs = within(screen.getByRole("list", { name: /^Select ETF: / })).getAllByRole("checkbox").map((b) => b.textContent);
    expect(etfs.length).toBe(2); expect(etfs.join(" ")).not.toContain("Sensex");
    fireEvent.click(within(screen.getByRole("list", { name: /^Select ETF: / })).getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    fireEvent.click(screen.getByRole("button", { name: /Select Index Fund/ }));
    fireEvent.click(within(screen.getByRole("list", { name: /^Select Index Fund: / })).getAllByRole("checkbox")[1]);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.getByText("1 ETF and 1 index fund chosen.")).toBeTruthy();
    const go = screen.getByRole("button", { name: "Compare products" }) as HTMLButtonElement;
    expect(go.disabled).toBe(false);
    fireEvent.click(go);
    expect(loc()).toBe("/etfs/compare-index-funds?index=nifty50&etf=SAMPLEETF&fund=910002");
  });
  it("stops at four products", () => {
    open("?index=nifty50&etf=SAMPLEETF,OTHERETF&fund=910001");
    fireEvent.click(screen.getByRole("button", { name: /Select Index Fund/ }));
    const list = within(screen.getByRole("list", { name: /^Select Index Fund: / }));
    expect(list.getAllByRole("checkbox").filter((b) => !(b as HTMLButtonElement).disabled && b.getAttribute("aria-checked") === "false").length).toBe(2);    // one slot is left: 910002 and 910003 are free until the fourth product is chosen
    fireEvent.click(list.getAllByRole("checkbox")[1]);
    expect(list.getAllByRole("checkbox").every((b) => (b as HTMLButtonElement).disabled === (b.getAttribute("aria-checked") === "false"))).toBe(true);
    expect(screen.getAllByText(/2 selected \(the most this page can show\)/).length).toBe(2);
  });
});

describe("the dashboard", () => {
  it("shows the six tiles, the sections, the reasons for blanks and the dates", () => {
    open("?index=nifty50&etf=SAMPLEETF&fund=910001");
    const tiles = screen.getAllByRole("link").filter((a) => a.getAttribute("href")?.startsWith("#evi-"));
    expect(tiles.map((a) => within(a).getByText(/./, { selector: "b" }).textContent)).toEqual(["Performance", "Cost analysis", "Tracking quality", "Risk analysis", "Investment calculator", "Summary by category"]);
    for (const h of ["Performance", "Cost analysis", "Tracking quality", "Risk analysis", "Investment calculator", "Summary by category"]) expect(screen.getByRole("heading", { level: 2, name: h })).toBeTruthy();
    // a blank 5-year figure says why (screen-reader text next to the dash)
    expect(screen.getAllByText(/not available: Common history starts on 29 Oct 2021/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Brokerage, the gap between buying and selling prices/)).toBeTruthy();
    expect(screen.getByText("0.05% × ₹10,00,000 = ₹500 a year")).toBeTruthy();
    expect(screen.getByText(/against the price index; total-return index not available/i)).toBeTruthy();
    expect(screen.getByText(/The tracking row uses tracking error only/)).toBeTruthy();
    expect(screen.getAllByText(/Differences of this size can reverse in other periods\. Information only, not investment advice\./).length).toBe(2);
    expect(screen.getAllByText(/as of 29 Oct 2026/).length).toBeGreaterThan(0);
  });
  it("collapses and opens a section from its heading, and a tile opens a closed one", () => {
    open("?index=nifty50&etf=SAMPLEETF&fund=910001");
    const btn = within(screen.getByRole("heading", { level: 2, name: "Cost analysis" })).getByRole("button");
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(document.getElementById("evi-b-cost")!.hasAttribute("hidden")).toBe(true);
    fireEvent.click(screen.getAllByRole("link").find((a) => a.getAttribute("href") === "#evi-cost")!);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
  });
  it("recalculates from the calculator through the address and refuses a silly amount", () => {
    open("?index=nifty50&etf=SAMPLEETF&fund=910001");
    const sip = screen.getByLabelText("Monthly SIP (₹)");
    fireEvent.change(sip, { target: { value: "5" } });
    expect(screen.getByRole("alert").textContent).toContain("between ₹100");
    fireEvent.change(sip, { target: { value: "25000" } });
    fireEvent.click(screen.getByRole("button", { name: "Recalculate" }));
    expect(loc()).toContain("sip=25000");
  });
  it("says why when the products share too little history", () => {
    st.compare = { ...COMPARE, returns: undefined, rolling: undefined, tracking: undefined, risk: undefined, sip: undefined, lump: undefined, chart: undefined, summary: null, common: { days: 12, why: "The chosen products share only 12 dates with a price: not enough to compare." } };
    open("?index=nifty50&etf=SAMPLEETF&fund=910001");
    expect(screen.getAllByText(/share only 12 dates/).length).toBeGreaterThan(0);
  });
  it("uses no advice-like words anywhere on the page or in its source", () => {
    open("?index=nifty50&etf=SAMPLEETF&fund=910001");
    const text = (document.body.textContent || "").toLowerCase();
    const bad = [/\bbuy\b/, /\bsell\b/, /\bhold\b/, /best[- ]to/, /\bwinner/, /\brecommend/, /\bshould\b/, /\bgood choice/, /\bbetter (fund|etf|choice|product)/, /\boutperform/, /guarantee/, /\bwill (rise|grow|beat)/];
    for (const rx of bad) expect(rx.test(text.replace("information only, not investment advice", "").replace("past returns do not guarantee future returns", "")), String(rx)).toBe(false);
    for (const f of ["../lib/etfVsIndex.ts", "./CompareIndex.tsx", "./CompareIndexSections.tsx"]) {
      const src = readFileSync(new URL(f, import.meta.url), "utf8").split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
      const shown = [...src.matchAll(/(?:"([^"\n]{10,})"|`([^`\n]{10,})`|>([^<>{}\n]{10,})<)/g)].map((m) => m[1] || m[2] || m[3]).join(" ").toLowerCase();
      for (const rx of [/\bbuy\b/, /\bsell\b/, /best[- ]to/, /\bwinner/, /\brecommend/]) expect(rx.test(shown.replace("not advice to buy", "")), `${f} ${rx}`).toBe(false);
    }
  });
});
