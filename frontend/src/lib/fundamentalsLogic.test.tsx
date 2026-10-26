import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AssetQuality, DataNotes, GrowthPanel, KeyFactors } from "../pages/FundamentalsExtras";
import { assetQualityTable, buildGrowth, buildPanels, cagr, dividendReturn, fallbackSources, periodIndex, pricePoints, priceReturn, type FundInput, type Row } from "./fundamentalsLogic";

const h = (vals: (number | null)[], periods: string[]) => vals.map((v, i) => ({ period: periods[i], value: v }));
const Y = ["Mar 2024", "Mar 2023", "Mar 2022", "Mar 2021"];
const income: Row[] = [
  { category: "revenue", history: h([120, 100, 80, 80], Y) }, { category: "net_profit", history: h([15, 10, -5, 4], Y) },
  { category: "operating_profit", history: h([30, 24, 18, 16], Y) }, { category: "interest", history: h([5, 4, 3, 3], Y) }, { category: "eps", history: h([3, null, 1, 1], Y) },
];
const fx: FundInput = {
  profile: { sector: "Refineries", industry: "Petroleum Products", marketCap: 123456 }, quote: { price: 100 },
  ratios: [{ name: "P/E", company_value: 20, sector_value: 25 }, { name: "ROE", company_value: 12, sector_value: 10 }],
  incomeStatement: { units_in: "Cr", income_statement: income }, cashFlow: { cash_flow: [{ category: "operating", history: h([20], ["Mar 2024"]) }] },
  balanceSheet: { history: [{ period: "Mar 2024", total_asset: 1000 }] },
};

describe("growth", () => {
  it("period index", () => { expect(periodIndex("Mar 2024", "yearly")).toBe(2024); expect(periodIndex("TTM 2024", "yearly")).toBeNull(); expect(periodIndex("Jun 2024", "quarterly")).toBe(2024 * 12 + 5); });
  it("yoy: missing, zero or negative comparison gives null, never a number", () => {
    const g = buildGrowth(income, "yearly", "yoy"), by = Object.fromEntries(g.map((p) => [p.period, p]));
    expect(by["Mar 2024"].revenue).toBeCloseTo(20); expect(by["Mar 2024"].profit).toBeCloseTo(50);
    expect(by["Mar 2023"].profit).toBeNull(); expect(by["Mar 2023"].reasons.profit).toMatch(/zero or negative/);
    expect(by["Mar 2024"].eps).toBeNull(); expect(by["Mar 2024"].reasons.eps).toMatch(/unavailable/);
  });
  it("quarterly qoq lags one quarter, yoy four", () => {
    const Q = ["Dec 2023", "Sep 2023", "Jun 2023", "Mar 2023", "Dec 2022"], rows = [{ category: "revenue", history: h([130, 120, 110, 100, 100], Q) }];
    expect(buildGrowth(rows, "quarterly", "qoq").pop()!.revenue).toBeCloseTo(8.333, 2);
    expect(buildGrowth(rows, "quarterly", "yoy").pop()!.revenue).toBeCloseTo(30);
  });
});

describe("key factors", () => {
  it("uses the upstream definitions and leaves unreported values null", () => {
    const p = buildPanels(fx), q = (l: string) => p.quality.find((r) => r.label.includes(l))!;
    expect(q("Sales CAGR").value).toBeCloseTo((Math.pow(120 / 80, 1 / 3) - 1) * 100, 5);
    expect(q("Cash from operations").value).toBeCloseTo(20 / 15 * 100);
    expect(q("Institutional").value).toBeNull(); expect(p.technicals[0].value).toBeNull(); expect(p.technicals[0].text).toBe("—");
    expect(p.snapshot.find((s) => s.label === "Operating margin")!.value).toBeCloseTo(25);
    expect(p.dna.find((d) => d.label === "Market cap")!.text).toBe("₹1,23,456 Cr");
  });
  it("cagr and returns", () => { expect(cagr(h([121, 100], ["b", "a"])).value).toBeCloseTo(21); expect(cagr(h([5], ["a"])).value).toBeNull(); });
  it("rsi, ema and returns on a price series", () => {
    const px = Array.from({ length: 260 }, (_, i) => ({ date: new Date(2025, 0, 1 + i).toISOString().slice(0, 10), close: 100 + i }));
    const pts = pricePoints(px), last = pts[pts.length - 1];
    expect(last.rsi).toBe(100); expect(last.ema200).not.toBeNull(); expect(pts[10].rsi).toBeNull();
    expect(priceReturn(pts, 21)).toBeCloseTo((359 - 338) / 338 * 100); expect(priceReturn(pts.slice(0, 5), 21)).toBeNull();
  });
  it("dividend return is null without actions", () => { expect(dividendReturn([], 100, 12)).toBeNull(); expect(dividendReturn([{ type: "Dividend", ex_date: "2024-01-01", amount: 5 }], 100, 12, "2024-06-01")).toBe(5); });
});

describe("bank asset quality and data notes", () => {
  const rows: Row[] = [{ category: "gross_npa_percent", history: h([2.1, 3.4], ["Mar 2024", "Mar 2023"]) }, { category: "cet1_ratio", history: h([14, null], ["Mar 2024", "Mar 2023"]) }];
  it("table keeps gaps", () => { const t = assetQualityTable(rows); expect(t.rows).toHaveLength(2); expect(t.rows[1].values).toEqual([14, null]); });
  it("fallback sources only", () => { expect(fallbackSources({ quote: "upstox", profile: "finedge" })).toEqual([{ section: "Latest price", source: "Upstox" }]); });
  it("renders with conclusion aria-labels, tables on demand and dashes", () => {
    const aq = renderToStaticMarkup(<AssetQuality rows={rows} basis="standalone" />);
    expect(aq).toContain("Gross NPA fell from 3.4% in Mar 2023 to 2.1% in Mar 2024"); expect(aq).toContain("standalone"); expect(aq).toContain("Show as table");
    expect(renderToStaticMarkup(<AssetQuality rows={[]} />)).toBe("");
    const kf = renderToStaticMarkup(<KeyFactors p={buildPanels(fx)} />);
    expect(kf).toContain('aria-label="Valuation: P/E ratio 20 against industry 25, 20% below.'); expect(kf.match(/Show as table/g)!.length).toBeGreaterThanOrEqual(3); expect(kf).toContain("—");
    const gp = renderToStaticMarkup(<GrowthPanel rows={income} period="yearly" />);
    expect(gp).toContain("Growth against the previous year for Mar 2024: revenue +20%, net profit +50%, eps not available");
    expect(renderToStaticMarkup(<GrowthPanel rows={[]} period="yearly" />)).toContain("Not enough comparable");
    expect(renderToStaticMarkup(<DataNotes />)).toBe("");
    expect(renderToStaticMarkup(<DataNotes flags={[{ section: "cashFlow", message: "Upstox was used as a fallback." }]} sources={{ quote: "upstox" }} />)).toContain("Data notes (2)");
  });
});
