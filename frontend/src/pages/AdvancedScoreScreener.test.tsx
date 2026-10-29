// @vitest-environment jsdom
// The Advanced score screener (FinLit Prism only, Gold) in a DOM: columns, filters, quick views, sorting, CSV, and the upgrade page for every other plan.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Row } from "../lib/screener";

const st = vi.hoisted(() => ({ plan: "gold" as "basic" | "silver" | "gold", rows: [] as unknown[], cover: null as unknown, upgrade: vi.fn(), toast: vi.fn(), loads: 0 }));
vi.mock("../lib/screener", async (orig) => ({ ...(await orig<typeof import("../lib/screener")>()), useUniverse: () => { st.loads++; return { data: { rows: st.rows, sample: true, asOf: "2026-10-26", prism: st.cover }, isLoading: false, isError: false }; } }));
vi.mock("../lib/ui", () => ({
  useUI: () => ({ has: (t: string) => ({ basic: 0, silver: 1, gold: 2 })[st.plan] >= ({ basic: 0, silver: 1, gold: 2 } as Record<string, number>)[t], upgrade: st.upgrade, toast: st.toast }),
  TIER: { basic: { n: "Basic", ic: "sprout", tc: "--t-basic" }, gold: { n: "Gold", ic: "crown", tc: "--t-gold" }, silver: { n: "Silver", ic: "medal", tc: "--t-silver" } },
}));
import { AdvancedScoreScreener } from "./AdvancedScoreScreener";
import { watch } from "../lib/watchlist";

const mk = (symbol: string, sector: string | null, cap: number | null, o: Partial<Row> = {}): Row => ({
  symbol, name: symbol + " Limited", sector, overall: 80, band: null, pillar_quality: 80, pillar_growth: 80, pillar_profitability: 80, pillar_balance: 80, pillar_technical: 80,
  price: cap == null ? null : 100, market_cap: cap, pe: null, pb: null, roe: null, roce: null, dividend_yield: null, debt_to_equity: null, sales_cagr: null, profit_cagr: null,
  operating_margin: null, change_pct: null, return_1m: null, return_1y: null, scored: true, ...o,
});
/** A rated company. The server's own technical words are deliberately the model's ("Buy", "Hold"): the page must not show them. */
const pz = (final: number | null, label: string, o: Partial<Row> = {}): Partial<Row> => ({
  prism_state: "stored", prism_final: final, prism_label: label, prism_status: final == null ? "NOT RATED" : "RATED", prism_at: "2026-10-27",
  prism_fundamental: final, prism_valuation: final == null ? null : 50, prism_quality: final == null ? null : 70, prism_risk: final == null ? null : 60,
  prism_st: final == null ? null : "Buy", prism_lt: final == null ? null : "Hold", prism_st_score: final == null ? null : 22, prism_lt_score: final == null ? null : -4, ...o,
});
const DATA: Row[] = [
  mk("AAA", "Banks", 9000, pz(85, "STRONG", { prism_valuation: 55, prism_risk: 70, prism_st_score: 55, prism_lt_score: 30 })),
  mk("BBB", "Banks", 8000, pz(66, "HEALTHY", { prism_valuation: 40, prism_st_score: 5, prism_lt_score: -35 })),
  mk("CCC", "IT", 7000, pz(55, "AVERAGE")),
  mk("DDD", "IT", 6000, { prism_state: "stored", prism_final: null, prism_label: "NOT RATED", prism_status: "NOT RATED" }),
  mk("EEE", "Auto", 5000, { prism_state: "none" }),
  mk("FFF", "Auto", 4000, pz(30, "POOR", { prism_status: "PROVISIONAL" })),
];
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
const Where = () => { const l = useLocation(); return <output data-testid="loc">{l.pathname + l.search}</output>; };
const open = (qs = "") => render(<MemoryRouter initialEntries={["/advanced-score-screener" + qs]}><Routes><Route path="/advanced-score-screener" element={<AdvancedScoreScreener />} /><Route path="*" element={<div>elsewhere</div>} /></Routes><Where /></MemoryRouter>);
const loc = () => screen.getByTestId("loc").textContent || "";
const symbols = () => within(screen.getByRole("table")).getAllByRole("row").slice(2).map((r) => within(r).queryAllByRole("cell")[2]?.querySelector("b")?.textContent).filter(Boolean);
const rowOf = (s: string) => screen.getByRole("checkbox", { name: `Select ${s}` }).closest("tr")!;
const heads = () => within(screen.getByRole("table")).getAllByRole("columnheader").map((h) => h.textContent?.replace(/[▲▼▾]/g, "").trim());
const forbidden = /\b(buy|sell|hold|reduce|avoid|accumulate)\b/;

beforeEach(() => { st.plan = "gold"; st.rows = DATA; st.cover = { rated: 3, provisional: 1, not_rated: 1, stored: 5, total: 6, as_of: "2026-10-27", per_night: 30 }; st.loads = 0; localStorage.clear(); watch.reset(); st.upgrade.mockReset(); st.toast.mockReset(); });
afterEach(cleanup);

describe("Advanced score screener (Gold)", () => {
  it("shows the Prism score with its word, the four parts and the two technical views in the site's words, and nothing of the FinLit score", () => {
    open();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/FinLit Prism/);
    const h = heads();
    expect(h).toEqual(expect.arrayContaining(["Prism", "Fundamentals", "Valuation", "Quality", "Risk", "Short-term technical", "Long-term technical"]));
    expect(h.join("|")).not.toMatch(/Overall|Growth|Profit|Balance|Fundamental\b(?!s)|^Technical$/);
    const r = rowOf("AAA").textContent!;
    expect(r).toMatch(/85\s*Strong/); expect(r).toMatch(/Strongly positive\+55/); expect(r).toMatch(/Positive\+30/);
    expect(rowOf("BBB").textContent).toMatch(/Neutral\+5/); expect(rowOf("BBB").textContent).toMatch(/Negative−35/);
    expect(rowOf("FFF").textContent).toMatch(/30\s*PoorProvisional/);
    expect(document.body.textContent?.toLowerCase()).not.toMatch(forbidden);   // the model's own "Buy" / "Hold" never reach the screen
    expect(screen.queryByRole("group", { name: "Fundamental score" })).toBeNull();
  });

  it("says Prism has rated X of Y with a progress bar, and a company without a rating says why, with a Rate now link", () => {
    open();
    expect(document.querySelector(".pzs-cover")!.textContent).toMatch(/Prism has rated 4 of 6 companies \(67%\)/);
    expect(document.querySelector(".pzs-bar i")).toBeTruthy();
    const e = rowOf("EEE");
    expect(e.textContent).toMatch(/Not rated yet/);
    expect(within(e).getByRole("link", { name: "Rate EEE with Prism now" }).getAttribute("href")).toBe("/prism/EEE");
    const d = rowOf("DDD");
    expect(d.textContent).toMatch(/Not rated/); expect(d.textContent).not.toMatch(/Rate now/);
  });

  it("filters by label chips, the rated switch and the Prism range, and writes them to the address", () => {
    open();
    const prism = screen.getByRole("group", { name: "Prism rating label" });
    fireEvent.click(within(prism).getByRole("button", { name: "Strong" })); fireEvent.click(within(prism).getByRole("button", { name: "Healthy" }));
    fireEvent.submit(prism.closest("form")!);
    expect(symbols()).toEqual(["AAA", "BBB"]); expect(loc()).toBe("/advanced-score-screener?pl=strong%2Chealthy");
    fireEvent.click(screen.getByRole("button", { name: "Remove filter Prism rating: Strong, Healthy" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Only companies rated by Prism" }));
    fireEvent.submit(prism.closest("form")!);
    expect(symbols()).toEqual(["AAA", "BBB", "CCC", "FFF"]); expect(loc()).toBe("/advanced-score-screener?rated=1");
    fireEvent.change(within(screen.getByRole("group", { name: "Prism score, exact range" })).getByLabelText("Min"), { target: { value: "60" } });
    fireEvent.submit(prism.closest("form")!);
    expect(symbols()).toEqual(["AAA", "BBB"]);
    fireEvent.click(within(screen.getByLabelText("Active filters")).getByRole("button", { name: "Clear all" }));
    expect(symbols()).toHaveLength(6);
  });

  it("has a min and max for each of the four parts, and a missing value never passes", () => {
    open();
    const box = (name: string, end: "Min" | "Max") => within(screen.getByRole("group", { name: `${name}, exact range` })).getByLabelText(end);
    fireEvent.change(box("Prism Valuation score", "Min"), { target: { value: "50" } });
    fireEvent.change(box("Prism Risk score", "Min"), { target: { value: "65" } });
    fireEvent.submit(screen.getByRole("button", { name: "Apply filters" }).closest("form")!);
    expect(symbols()).toEqual(["AAA"]);
    expect(loc()).toBe("/advanced-score-screener?zvmin=50&zrmin=65");
    expect(screen.getByRole("button", { name: "Remove filter Prism Valuation: 50 or more" })).toBeTruthy();
    for (const p of ["Fundamentals", "Quality"]) expect(screen.getByRole("group", { name: `Prism ${p} score, exact range` })).toBeTruthy();
  });

  it("filters each technical view by Positive, Neutral or Negative, using the Prism card's bands", () => {
    open();
    const st = screen.getByRole("group", { name: "Short-term technical view" }), lt = screen.getByRole("group", { name: "Long-term technical view" });
    expect(within(st).getByRole("checkbox", { name: /^Positive \(\+20 and above\)/ })).toBeTruthy();
    fireEvent.click(within(st).getByRole("checkbox", { name: /^Positive/ }));
    fireEvent.submit(st.closest("form")!);
    expect(symbols()).toEqual(["AAA", "CCC", "FFF"]);                         // +55, +22, +22 are Positive; BBB +5 is Neutral; unrated have no score
    expect(loc()).toBe("/advanced-score-screener?st=pos");
    fireEvent.click(within(lt).getByRole("checkbox", { name: /^Negative/ }));
    fireEvent.submit(st.closest("form")!);
    expect(symbols()).toEqual([]);                                            // Positive short term and Negative long term: nobody here
    expect(screen.getByRole("button", { name: "Remove filter Long-term technical: Negative" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove filter Short-term technical: Positive" }));
    expect(symbols()).toEqual(["BBB"]);
  });

  it("offers four quick views built from the Prism parts only, each applying at once and switching off again", () => {
    open();
    const views = screen.getAllByRole("button", { name: /^(Prism strong and lower risk|Strong fundamentals at a fair valuation|Positive on both technical views|Fundamentals strong but valuation weak)$/ });
    expect(views).toHaveLength(4);
    fireEvent.click(screen.getByRole("button", { name: "Prism strong and lower risk" }));
    expect(symbols()).toEqual(["AAA"]); expect(loc()).toBe("/advanced-score-screener?zmin=80&zrmin=65&rated=1");
    fireEvent.click(screen.getByRole("button", { name: "Prism strong and lower risk" }));
    expect(symbols()).toHaveLength(6); expect(loc()).toBe("/advanced-score-screener");
    fireEvent.click(screen.getByRole("button", { name: "Positive on both technical views" }));
    expect(symbols()).toEqual(["AAA"]); expect(loc()).toBe("/advanced-score-screener?st=pos&lt=pos");
    fireEvent.click(screen.getByRole("button", { name: "Fundamentals strong but valuation weak" }));
    expect(symbols()).toEqual(["BBB"]);                                        // Fundamentals 66 or more and Valuation 40 (50 or less)
    expect(document.body.textContent?.toLowerCase()).not.toMatch(forbidden);
  });

  it("sorts on the Prism score, each part and each technical view, companies without a value last", () => {
    open("?size=50");
    fireEvent.click(screen.getByRole("button", { name: "Sort by Prism" }));
    expect(symbols()).toEqual(["AAA", "BBB", "CCC", "FFF", "DDD", "EEE"]);
    fireEvent.click(screen.getByRole("button", { name: "Sort by Prism" }));
    expect(symbols()).toEqual(["FFF", "CCC", "BBB", "AAA", "DDD", "EEE"]);
    fireEvent.click(screen.getByRole("button", { name: "Sort by Long-term technical" }));
    expect(loc()).toContain("sort=prism_lt_score"); expect(symbols().slice(-2)).toEqual(["DDD", "EEE"]);
    fireEvent.click(screen.getByRole("button", { name: "Sort by Risk" }));
    expect(loc()).toContain("sort=prism_risk");
  });

  it("ignores FinLit-score parameters in the address", () => {
    open("?f=high&omin=90&sort=overall");
    expect(symbols()).toHaveLength(6);
    expect(within(screen.getByLabelText("Summary")).getByText("Active filters").previousSibling?.textContent).toBe("0");
  });

  it("selects, compares up to 4 and adds to the watchlist", () => {
    open();
    ["AAA", "BBB", "CCC"].forEach((s) => fireEvent.click(screen.getByRole("checkbox", { name: `Select ${s}` })));
    fireEvent.click(screen.getByRole("button", { name: "Compare 3" }));
    expect(loc()).toBe("/compare?c=AAA,BBB,CCC");
  });

  it("adds the selection to the watchlist", () => {
    open();
    fireEvent.click(screen.getByRole("checkbox", { name: "Select AAA" }));
    fireEvent.click(screen.getByRole("button", { name: "Add to watchlist" }));
    expect(watch.has("AAA")).toBe(true);
  });

  it("exports only the Prism columns, with the site's words and blanks for unrated companies", async () => {
    open();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    let blob: Blob | null = null;
    URL.createObjectURL = vi.fn((b: Blob) => { blob = b; return "blob:x"; }); URL.revokeObjectURL = vi.fn();
    fireEvent.click(screen.getByRole("button", { name: /Export all 6/ }));
    const text = await new Promise<string>((res) => { const fr = new FileReader(); fr.onload = () => res(String(fr.result)); fr.readAsText(blob!); });
    expect(text).toMatch(/Prism ratings as of: 2026-10-27/);
    expect(text).toContain("Symbol,Name,Sector,Size,Price (Rs),Market cap (Rs Cr),Prism,Prism label,Prism status,Prism Fundamentals,Prism Valuation,Prism Quality,Prism Risk,Technical short term,Technical short term score,Technical long term,Technical long term score,Prism rated on");
    expect(text).toContain("AAA,AAA Limited,Banks,Large cap,100,9000,85,Strong,RATED,85,55,70,70,Strongly positive,55,Positive,30,2026-10-27");
    expect(text).toContain("EEE,EEE Limited,Auto,Large cap,100,5000,,,,,,,,,,,,");
    expect(text).not.toMatch(/Overall|Balance sheet|\bBuy\b|\bHold\b/);
  });

  it("opens the How scores work dialog with the Prism definitions and the technical bands", () => {
    open();
    fireEvent.click(screen.getAllByRole("button", { name: /How scores work/ })[0]);
    const d = screen.getByRole("dialog", { name: "How scores work" });
    expect(d.textContent).toMatch(/Strong 80 and above, Healthy 65 to 79/);
    expect(d.textContent).toMatch(/Positive \(\+20 and above\)/);
    expect(d.textContent?.toLowerCase()).not.toMatch(forbidden);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("Advanced score screener: every plan below Gold gets the upgrade page", () => {
  const nothing = () => {
    expect(st.loads).toBe(0);                                                  // the universe is never requested
    const page = document.body.textContent || "";
    expect(page).not.toMatch(/AAA|BBB|CCC|FFF|Rate now|Prism has rated/);          // no company of the data, no coverage line
    expect(screen.queryByRole("table", { name: /matching the filters/ })).toBeNull();
  };
  for (const plan of ["basic", "silver"] as const) {
    it(`${plan}: explanation, a labelled static example, the benefits and an Unlock with Gold button; no request, no real value`, () => {
      st.plan = plan; open();
      nothing();
      expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/FinLit Prism/);
      expect(screen.getByText("Example")).toBeTruthy();
      expect(screen.getByText(/Sample companies and figures, only to show the layout/)).toBeTruthy();
      expect(screen.getByRole("table", { hidden: true, name: /Example of the advanced score screener/ }).textContent).toMatch(/Example Company A/);
      expect(screen.getAllByText(/Four fundamental parts, each 0 to 100/).length).toBeGreaterThan(0);
      fireEvent.click(screen.getAllByRole("button", { name: /Unlock with Gold/ })[0]);
      expect(st.upgrade).toHaveBeenCalledWith("gold", expect.any(String));
      expect(document.body.textContent?.toLowerCase()).not.toMatch(forbidden);
      expect(screen.getByRole("link", { name: "Basic score screener" }).getAttribute("href")).toBe("/score-screener");
    });
  }
  it("a Silver response (rows with no Prism values) still renders nothing of Prism", () => {
    st.plan = "silver"; st.rows = DATA.map((r) => ({ ...r, ...Object.fromEntries(Object.keys(r).filter((k) => k.startsWith("prism_")).map((k) => [k, null])) }));
    open(); nothing();
  });
});
