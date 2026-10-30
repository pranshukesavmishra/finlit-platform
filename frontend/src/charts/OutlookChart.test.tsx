import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import fx from "../lib/__fixtures__/outlookReliance.json";
import type { HistoryPoint, Outlook, YearRow } from "../lib/outlook";
import { BuildTable, YearTable } from "../pages/Outlook";
import { OutlookChart, buildSeries } from "./OutlookChart";

const rel = (k: string) => (fx as unknown as Record<string, Outlook>)[k];
const H = (vals: (number | null)[]): HistoryPoint[] => vals.map((v, i) => ({ period: `FY${20 + i}`, valueCr: v, reportedCr: v, adjusted: false }));
const E = (vals: number[], from: number): YearRow[] => vals.map((v, i) => ({ period: `FY${from + i}`, valueCr: v, growthPct: 10, changeCr: 0 }));
const BANNED = /\b(buy|sell|hold|target price|recommend\w*|guarantee\w*|will reach|will grow|prediction of)\b/i;

describe("OutlookChart", () => {
  it("draws a solid reported line, a dashed estimate line, filled and hollow dots, a divider and a legend", () => {
    const d = rel("revenue:mid"), html = renderToStaticMarkup(<OutlookChart kind="revenue" symbol="RELIANCE" series={buildSeries(d.history.points, d.forecast.years)} who="FinLit model" horizonLabel="mid-term" />);
    expect(html).toContain('role="img"'); expect(html).toContain("Revenue: reported ₹");
    expect(html).toContain('stroke-dasharray="7 6"');            // the estimate line
    expect((html.match(/<circle/g) ?? []).length).toBe(8 + 3 + 2);    // one dot per year, plus the two legend samples
    expect((html.match(/fill="var\(--s1\)"/g) ?? []).length).toBeGreaterThanOrEqual(3);   // hollow estimate dots
    expect(html).toContain("Forecast starts FY27"); expect(html).toContain("Reported"); expect(html).toContain("Estimate (FinLit model)");
    expect(html).toContain("Show as table"); expect(html).toContain("Download CSV"); expect(html).toContain('tabindex="0"');
    expect(html).toContain("₹ lakh crore"); expect(html).not.toMatch(BANNED);
  });
  it("labels a second dashed line when two estimates are drawn", () => {
    const s = buildSeries(H([100, 110, 121]), E([133, 146], 23), E([130, 140], 23));
    const html = renderToStaticMarkup(<OutlookChart kind="profit" symbol="X" series={s} who="Your weights" horizonLabel="mid-term" />);
    expect(html).toContain("Estimate (Your weights)"); expect(html).toContain("Estimate (FinLit model)"); expect(html).toContain('stroke-dasharray="2 5"');
  });
  it("shows a loss-making company with a zero line and no estimate line", () => {
    const html = renderToStaticMarkup(<OutlookChart kind="profit" symbol="X" series={buildSeries(H([50, 10, -30, -40]), null)} who="FinLit model" horizonLabel="short-term" />);
    expect(html).toContain(">−50<"); expect(html).toContain("−₹40 Cr"); expect(html).toContain('stroke-width="1.6"');      // the zero line is drawn heavier
    expect(html).not.toContain("Forecast starts"); expect(html).not.toContain('stroke-dasharray="7 6"'); expect(html).toContain("No estimate is shown");
  });
  it("a one-year history still draws", () => {
    const html = renderToStaticMarkup(<OutlookChart kind="revenue" symbol="X" series={buildSeries(H([500]), E([550], 21))} who="FinLit model" horizonLabel="short-term" />);
    expect(html).toContain("Forecast starts FY21"); expect((html.match(/<circle/g) ?? []).length).toBe(2 + 2);
  });
  it("says why when there is nothing to chart", () => {
    const html = renderToStaticMarkup(<OutlookChart kind="revenue" symbol="X" series={buildSeries([], null)} who="x" horizonLabel="x" />);
    expect(html).toContain("No reported revenue figures are stored");
  });
});

describe("the tables beside the chart and the page text", () => {
  it("lists every input with its weight, the used weight and its contribution, and the weighted rate", () => {
    const d = rel("profit:mid"), html = renderToStaticMarkup(<BuildTable d={d} />);
    for (const r of d.rate.rows) expect(html).toContain(r.label);
    expect(html).toContain("Weighted growth rate, per year"); expect(html).toContain("+11.60%");
    expect(html).toContain("relative change in the net profit margin");
  });
  it("says when an input was limited by the cap", () => {
    const d = rel("profit:mid"), capped: Outlook = { ...d, rate: { ...d.rate, rows: d.rate.rows.map((r) => (r.key === "margin" ? { ...r, valuePct: 50, rawPct: 83.4, capped: true } : r)) } };
    expect(renderToStaticMarkup(<BuildTable d={capped} />)).toContain("limited from +83.4%");
  });
  it("shows blanks with their reason and the year table from the same payload", () => {
    const d = rel("revenue:short"), blank: Outlook = { ...d, rate: { ...d.rate, unavailable: ["Sector revenue growth (1Y)"], rows: d.rate.rows.map((r) => (r.key === "sec_1y" ? { ...r, status: "unavailable" as const, valuePct: null, effectiveWeightPct: 0, contributionPts: null, method: null, reason: "Only 2 peers have this figure; at least 5 are needed for a median." } : r)) } };
    const html = renderToStaticMarkup(<BuildTable d={blank} />) + renderToStaticMarkup(<YearTable d={blank} />);
    expect(html).toContain("Only 2 peers have this figure"); expect(html).toContain("Their weight was shared across the other inputs in proportion");
    expect(html).toContain("FY26"); expect(html).toContain("FY27"); expect(html).toContain("Estimate"); expect(html).toContain("held constant");
  });
  it("gives the reason instead of a table when there is no estimate", () => {
    const d = rel("profit:short"), none: Outlook = { ...d, forecast: { ...d.forecast, available: false, years: [], base: null, reason: "The latest year's net profit was not positive, so a growth rate cannot be applied to it." } };
    expect(renderToStaticMarkup(<YearTable d={none} />)).toContain("not positive");
  });
  it("uses neutral wording everywhere", () => {
    let text = "";
    for (const k of Object.keys(fx)) { const d = rel(k); text += renderToStaticMarkup(<BuildTable d={d} />) + renderToStaticMarkup(<YearTable d={d} />) + renderToStaticMarkup(<OutlookChart kind={d.kind} symbol="R" series={buildSeries(d.history.points, d.forecast.years)} who="FinLit model" horizonLabel="x" />) + d.disclaimer; }
    expect(text).not.toMatch(BANNED);
    expect(rel("revenue:mid").disclaimer).toContain("not a prediction or advice"); expect(rel("revenue:mid").disclaimer).toContain("not yet been validated");
    expect(<MemoryRouter />).toBeTruthy();
  });
});
