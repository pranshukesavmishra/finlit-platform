// @vitest-environment jsdom
// "Decoding ROE" under the DuPont card: real-shaped Reliance statements, the toggles, data-gap reasons, anomalies, rule cards, waterfall, calculator, explanation panel, CSV and wording.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { Table } from "../lib/api";
import reliance from "../lib/__fixtures__/relianceYearly.json";

const st = vi.hoisted(() => ({ saved: [] as { name: string; text: string; type: string }[], fin: null as unknown }));
vi.mock("./derive", () => ({ saveFile: (name: string, text: string, type: string) => st.saved.push({ name, text, type }) }));
vi.mock("../components/ChartHelp", () => ({ ChartHelp: () => null }));
vi.mock("../lib/api", async (orig) => ({ ...(await orig<typeof import("../lib/api")>()), useSection: () => ({ data: st.fin }) }));
import { DecodeRoe } from "./DecodeRoe";
import { DuPont } from "./DuPont";

const RIL = reliance.yearly as { pl: Table; bs: Table };
const t = (periods: string[], rows: Record<string, (number | null)[]>) => ({ unit: "Cr", period: "yearly", periods, periodEnds: periods, rows }) as Table;
const P8 = ["FY19", "FY20", "FY21", "FY22", "FY23", "FY24", "FY25", "FY26"];
/** Shaped like the founder's report: no equity for the four oldest years, 20,780% one-off in Mar 2022, a leveraged one-off year in Mar 2023. */
const SHAPED = {
  pl: t(P8, { revenue: [1000, 1100, 900, 20000, 100000, 1000, 1050, 1100], net_profit: [300, 90, 100, 30, 48000, 100, 190, 210], profit_before_tax: [380, 120, 140, 40, 60000, 130, 240, 270], tax: [80, 30, 40, 10, 12000, 30, 50, 60], exceptional_items: [null, null, null, 8312, 40000, null, null, null], finance_costs: [20, 25, 30, 1, 5, 10, 12, 9] }),
  bs: t(P8, { total_assets: [500, 520, 530, 560, 540000, 520, 510, 530], total_equity: [null, null, null, null, 107000, 280, 270, 266], equity_capital: [10, 10, 10, 10, 10, 10, 10, 10] }),
};
beforeAll(() => { (globalThis as { ResizeObserver?: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }; });
afterEach(() => { cleanup(); document.getElementById("financials")?.remove(); st.saved.length = 0; });
const show = (d = RIL, lender = false) => render(<DecodeRoe symbol="RELIANCE" pl={d.pl} bs={d.bs} lender={lender} />);

describe("Decoding ROE, Reliance", () => {
  it("has the heading, the plain sentence, a completeness indicator and the disclaimer", () => {
    show();
    expect(screen.getByRole("heading", { name: "Decoding ROE" })).toBeTruthy();
    expect(screen.getByText(/8 of 8 years complete/)).toBeTruthy();
    expect(screen.getByText(/Information only, not investment advice/)).toBeTruthy();
  });
  it("table has a caption, years as columns, and the same ROE figures as the DuPont card (FY26 7.7%)", () => {
    show();
    const tbl = screen.getByRole("table", { name: /Net margin, asset turnover/ });
    expect(within(tbl).getAllByRole("columnheader")).toHaveLength(9);
    const roe = within(tbl).getByRole("row", { name: /ROE, reported/ });
    expect(roe.textContent).toContain("7.7%"); expect(roe.textContent).toContain("8.7%");           // FY19 35,163 / 4,05,322; FY26 43,851 / 5,66,235
  });
  it("toggles Reported | Normalized and Year-end | Average balances, and says which is on", () => {
    show();
    const rep = screen.getByRole("button", { name: "Reported" }), norm = screen.getByRole("button", { name: "Normalized" });
    expect(rep.getAttribute("aria-pressed")).toBe("true"); fireEvent.click(norm);
    expect(norm.getAttribute("aria-pressed")).toBe("true"); expect(screen.getByRole("row", { name: /Net margin, normalized/ })).toBeTruthy();
    const avg = screen.getByRole("button", { name: "Average balances" }); fireEvent.click(avg);
    expect(avg.getAttribute("aria-pressed")).toBe("true"); expect(screen.getByText(/falls back to its year-end figure/)).toBeTruthy();
    expect(screen.getAllByText("†").length).toBeGreaterThan(0);
  });
  it("shows the average ROE with the years used", () => {
    show();
    const a = screen.getByRole("table", { name: /Average ROE/ });
    expect(within(a).getByRole("row", { name: /3-year average/ }).textContent).toContain("3 of 3");
    expect(within(a).getByRole("row", { name: /5-year average/ }).textContent).toContain("5 of 5");
  });
  it("the waterfall, the calculator and the explanation use the numbers on the page", () => {
    show();
    expect(screen.getByRole("img", { name: /ROE bridge from Mar 2019 to Mar 2026/ })).toBeTruthy();
    expect(screen.getByRole("table", { name: /Contribution of each factor/ })).toBeTruthy();
  });
  it("calculator: sliders start at the latest values, move the ROE live and solve the required margin", () => {
    show();
    const m = screen.getByLabelText("Net margin") as HTMLInputElement, e = screen.getByLabelText("Equity multiplier") as HTMLInputElement;
    expect(Number(m.value)).toBeCloseTo((43851 / 524105) * 100, 6); expect(e.type).toBe("range");
    fireEvent.change(m, { target: { value: "16.74" } });
    expect(document.querySelectorAll(".dp-simout")[0].textContent).toMatch(/^15\.\d%\sROE = 16\.74% × 0\.45 × 2\.06/);
    const goal = screen.getByLabelText(/What net margin would give an ROE of/) as HTMLInputElement; expect(goal.value).toBe("25");
    const need = (25 / ((524105 / 1165809) * (1165809 / 566235))).toFixed(1);
    expect(document.querySelectorAll(".dp-simout")[1].textContent).toContain(need + "% net margin");
    fireEvent.change(goal, { target: { value: "" } }); expect(document.querySelectorAll(".dp-simout")[1].textContent).toMatch(/positive ROE/);
    expect(screen.getByText(/not a forecast/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Reset to Mar 2026/ })); expect(Number(m.value)).toBeCloseTo((43851 / 524105) * 100, 6);
  });
  it("'How is this calculated?' opens with the actual numbers of the chosen year", () => {
    show();
    const b = screen.getByRole("button", { name: /How is this calculated/ }); expect(b.getAttribute("aria-expanded")).toBe("false"); fireEvent.click(b);
    expect(b.getAttribute("aria-expanded")).toBe("true");
    const tbl = screen.getByRole("table", { name: /Formulas for Mar 2026/ }); expect(tbl.textContent).toContain("43,851 ÷ 5,24,105"); expect(tbl.textContent).toContain("8.37%");
    fireEvent.change(screen.getByLabelText("Year"), { target: { value: "FY19" } });
    expect(screen.getByRole("table", { name: /Formulas for Mar 2019/ }).textContent).toContain("35,163 ÷ 3,84,904");
    expect(screen.getByText(/Year-end balances use the closing balance sheet/)).toBeTruthy();
  });
  it("exports the table as CSV", () => {
    show(); fireEvent.click(screen.getByRole("button", { name: /Download table/ }));
    expect(st.saved).toHaveLength(1); expect(st.saved[0].name).toBe("FinLit-RELIANCE-decoding-roe.csv"); expect(st.saved[0].type).toMatch(/text\/csv/);
    expect(st.saved[0].text).toContain("Measure,Mar 2019,Mar 2020"); expect(st.saved[0].text).toContain("Information only, not investment advice.");
  });
  it("no checks panel for steady, ordinary figures", () => { show(); expect(screen.queryByText("Checks on the numbers")).toBeNull(); });
});

describe("Decoding ROE, report-shaped data with gaps and one-offs", () => {
  it("gives a visible reason beside every dash, groups the reasons and counts complete years", () => {
    show(SHAPED);
    expect(screen.getByText(/4 of 8 years complete/)).toBeTruthy();
    expect(screen.getAllByText("equity data not available").length).toBeGreaterThanOrEqual(8);       // multiplier, ROE and normalized ROE rows, four years each (plus the average)
    const note = screen.getAllByRole("note")[0]; expect(note.getAttribute("title")).toMatch(/no total equity figure/); expect(note.getAttribute("tabindex")).toBe("0");
    fireEvent.focus(note); expect(document.querySelector(".dp-hint")!.textContent).toMatch(/no total equity figure/);
    expect(screen.getByLabelText("Why some cells are blank").textContent).toContain("Mar 2019, Mar 2020, Mar 2021, Mar 2022");
  });
  it("shows the 20,780% one-off ratio as an implausible-ratio caution, and marks low-quality years", () => {
    show(SHAPED);
    const c = screen.getByLabelText(/Implausible ratio of 20,780 per cent/); expect(c.textContent).toContain("implausible"); expect(c.textContent).toContain("20,780%");
    expect(screen.getAllByText(/Low quality/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("table", { name: /Average ROE/ }).textContent).toContain("Mar 2022, Mar 2023 (low-quality earnings)");
  });
  it("lists anomalies with the neutral prompt, and links to the financials section only where it exists", () => {
    const first = show(SHAPED);
    expect(screen.getAllByText(/Possible equity raise, merger or restructuring: check the cash flow and equity statements\./).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /financial statements/ })).toBeNull(); first.unmount();
    const el = document.createElement("section"); el.id = "financials"; el.scrollIntoView = vi.fn(); document.body.appendChild(el);
    show(SHAPED); const a = screen.getAllByRole("link", { name: /See the financial statements/ })[0]; expect(a.getAttribute("href")).toBe("#financials");
    fireEvent.click(a); expect(el.scrollIntoView).toHaveBeenCalled();
  });
  it("insight cards come from the rule list and show their numbers", () => {
    show(SHAPED);
    const cards = screen.getAllByRole("listitem").filter((x) => x.className === "dp-insc");
    expect(cards.length).toBeGreaterThan(0); expect(cards.length).toBeLessThanOrEqual(4);
    expect(cards[0].textContent).toMatch(/one-off items above 50%/); expect(cards.every((c) => c.querySelector("ul li"))).toBe(true);
  });
});

describe("edge cases", () => {
  it("a bank gets the three-factor view only, no leverage score and no calculator crash", () => {
    show(RIL, true);
    expect(screen.getByText(/Not shown for banks and lenders/)).toBeTruthy(); expect(screen.queryByRole("img", { name: /ROE bridge/ })).toBeNull();
    expect(screen.getByText("not scored for banks and lenders")).toBeTruthy();
  });
  it("negative equity reads 'negative equity' and 'ROE not meaningful'; one year only and all-null data render", () => {
    const neg = { pl: t(["FY25", "FY26"], { revenue: [100, 100], net_profit: [10, 10], profit_before_tax: [14, 14] }), bs: t(["FY25", "FY26"], { total_assets: [500, 500], total_equity: [-50, -40] }) };
    show(neg); expect(screen.getAllByText("negative equity").length).toBe(2); expect(screen.getAllByText("ROE not meaningful").length).toBeGreaterThan(0); cleanup();
    show({ pl: t(["FY26"], { revenue: [100], net_profit: [10], profit_before_tax: [14] }), bs: t(["FY26"], { total_assets: [200], total_equity: [100] }) }); expect(screen.getByText(/1 of 1 years complete/)).toBeTruthy(); expect(screen.getByText(/Needs pre-tax profit, finance costs/)).toBeTruthy(); cleanup();
    show({ pl: t(["FY25", "FY26"], { revenue: [null, null], net_profit: [null, null] }), bs: t(["FY25", "FY26"], { total_assets: [null, null], total_equity: [null, null] }) }); expect(screen.getByText(/0 of 2 years complete/)).toBeTruthy(); expect(screen.getAllByText("no revenue").length).toBeGreaterThan(0);
    expect(screen.getByText(/nothing to start from/)).toBeTruthy();
  });
  it("renders nothing without statements", () => { const r = show({ pl: undefined as never, bs: undefined as never }); expect(r.container.innerHTML).toBe(""); });
});

describe("DuPont placement", () => {
  it("the existing card stays where it was, with 'Decoding ROE' now above the new block and not above the card", () => {
    st.fin = { yearly: { pl: RIL.pl, bs: RIL.bs } };
    const { container } = render(<DuPont symbol="RELIANCE" periods={[]} rows={{}} lender={false} />);
    const kids = [...container.querySelector(".dp")!.children];
    expect(kids[0].className).toContain("dp-card"); expect(kids[0].querySelector("h3")?.textContent).toContain("DuPont analysis");
    expect(kids[1].className).toBe("dp-deep"); expect(kids[1].querySelector(".dp-head h3")?.textContent).toBe("Decoding ROE");
    expect(container.querySelectorAll(".dp-head")).toHaveLength(1);
    expect(kids[0].querySelector(".dp-head")).toBeNull();
    expect(kids[0].textContent).toContain("7.7%");
  });
});

describe("compliance wording on screen", () => {
  it("no buy, sell, hold or target language anywhere in the block, in either view or basis", () => {
    const BAD = /\b(buy|buying|sell|selling|hold|holding|target|targets|recommend\w*|outperform\w*|undervalued|overvalued|upside|downside|accumulate)\b/i;
    for (const d of [RIL, SHAPED]) {
      show(d); fireEvent.click(screen.getByRole("button", { name: /How is this calculated/ })); fireEvent.click(screen.getByRole("button", { name: "Normalized" })); fireEvent.click(screen.getByRole("button", { name: "Average balances" }));
      const text = document.body.textContent || ""; expect(text.length).toBeGreaterThan(1500); expect(text).not.toMatch(BAD); expect(text).toMatch(/Information only, not investment advice/);
      const sr = [...document.querySelectorAll("[aria-label],[title]")].map((e) => (e.getAttribute("aria-label") || "") + (e.getAttribute("title") || "")).join(" "); expect(sr).not.toMatch(BAD);
      cleanup();
    }
  });
});
