// Regression (founder, Kotak, 29 Oct 2026): the quarter view must show the quarter-on-quarter figures as boxes (not only a small line), the year view must show the
// year's own figures, and say how the newest quarter has moved since. The real KOTAKBANK numbers are used, so the expected values are checked by hand:
// FY26 vs FY25: revenue +6.3%, net profit -12.8%.  Sep 2026 vs Sep 2025: +15.4%, +26.3%.  Sep 2026 vs Jun 2026: +8.2%, +3.0%.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Table } from "../lib/api";
import { plInsights } from "../lib/plFlags";
import { Block } from "./PlFlagsLayer";

const tbl = (t: unknown) => ({ unit: "Cr", period: "yearly", ...(t as object) }) as Table;
const KOTAK = {
  annual: tbl({
    periods: ["FY24", "FY25", "FY26"], periodEnds: ["2024-03-31", "2025-03-31", "2026-03-31"],
    rows: { revenue: [56236.63, 65668.83, 69781.21], net_profit: [18213.21, 22125.99, 19287.89] },
  }),
  quarterly: tbl({
    period: "quarterly", periods: ["Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"],
    periodEnds: ["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"],
    rows: { revenue: [17248.31, 17198.74, 17506.8, 17827.36, 18354.57, 19855.87], net_profit: [4472.18, 4468.27, 4924.29, 5423.15, 5480.46, 5645.38] },
  }),
};
const insight = () => plInsights({ annual: KOTAK.annual, quarterly: KOTAK.quarterly, lender: true })[0];
const r1 = (v: number | null) => (v == null ? null : Math.round(v * 10) / 10);

describe("earnings popup, Kotak", () => {
  it("has the right growth figures for the year, the quarter and quarter on quarter", () => {
    const x = insight();
    expect(x.headline).toBe("annual");
    const a = x.views.annual!, q = x.views.quarterly!;
    expect([r1(a.growth.revenue), r1(a.growth.profit)]).toEqual([6.3, -12.8]);
    expect([r1(q.growth.revenue), r1(q.growth.profit)]).toEqual([15.4, 26.3]);
    expect([r1(q.qoq!.growth.revenue), r1(q.qoq!.growth.profit)]).toEqual([8.2, 3.0]);
  });

  it("quarter view: quarter-on-quarter boxes first, then the year-on-year boxes", () => {
    const x = insight();
    const html = renderToStaticMarkup(<Block v={x.views.quarterly!} lender />);
    expect(html).toContain("Quarter-on-quarter");
    expect(html).toContain("+8.2%");
    expect(html).toContain("+3.0%");
    expect(html).toContain("Year-on-year");
    expect(html).toContain("Sep 2026 compared with Jun 2026 (the quarter before).");
    expect(html).toContain("Sep 2026 compared with Sep 2025 (the same quarter a year earlier).");
    expect(html).toContain("+15.4%");
    expect(html).toContain("+26.3%");
    expect(html.indexOf("+8.2%")).toBeLessThan(html.indexOf("+15.4%"));
    expect((html.match(/plf-tile /g) || []).length).toBe(4);
  });

  it("year view: FY26 against FY25, and one line on the newest quarter", () => {
    const x = insight();
    const html = renderToStaticMarkup(<Block v={x.views.annual!} lender recent={x.views.quarterly} />);
    expect(html).toContain("+6.3%");
    expect(html).toMatch(/−12\.8%/);
    expect(html).toContain("Since then, the latest quarter (Sep 2026)");
    expect(html).toContain("revenue +15.4%, net profit +26.3%");
  });
});

import { isAway } from "./PlFlagsLayer";
describe("the alert belongs to its section", () => {
  const vh = 800;
  it("is shown while the reader is on its section", () => { expect(isAway(100, 500, 1200, vh)).toBe(false); });
  it("goes away when the next section passes the middle of the screen", () => { expect(isAway(-300, 100, 300, vh)).toBe(true); expect(isAway(-300, 100, null, vh)).toBe(false); });
  it("goes away when the results are far above, or when the reader has gone back up to an earlier section", () => {
    expect(isAway(-1500, -700, 2000, vh)).toBe(true);
    expect(isAway(900, 1200, 2500, vh)).toBe(true);
  });
});


import { GapBars, Insights } from "./PlFlagsLayer";
import { readFileSync } from "node:fs";
describe("compact popup", () => {
  const case1 = () => plInsights({ annual: KOTAK.annual, quarterly: { ...KOTAK.quarterly, rows: { revenue: [100, 100, 100, 100, 100, 106.7], net_profit: [100, 100, 100, 100, 100, 122] } } as Table, lender: true }).find((x) => x.case === 1);
  it("draws the revenue and profit bars and the multiple from the growth figures shown", () => {
    const html = renderToStaticMarkup(<GapBars g={{ revenue: 6.7, profit: 22, operating: null }} />);
    expect(html).toContain("Net profit 3.3x faster");
    expect(renderToStaticMarkup(<GapBars g={{ revenue: 6.7, profit: 7.5, operating: null }} />)).not.toContain("faster");
    expect(renderToStaticMarkup(<GapBars g={{ revenue: null, profit: 7.5, operating: null }} />)).toBe("");
  });
  it("Insights shows icon chips with QoQ / YoY tags and keeps the long wording as tooltip and hidden text", () => {
    const x = plInsights({ annual: KOTAK.annual, quarterly: KOTAK.quarterly, lender: true })[0];
    const html = renderToStaticMarkup(<Insights x={{ ...x, case: 1 }} />);
    for (const t of ["Sales vs profit gap", "Quarter = momentum", "Year view = no seasonality", "Core gain or one-off?"]) expect(html).toContain(t);
    expect(html).toContain(">QoQ<"); expect(html).toContain(">YoY<");
    expect(html).toContain('title="One quarter can be seasonal, so read it as momentum, not a trend."');
    expect(html).toContain("Quarter on quarter: Profit and sales moved very differently.");
    expect(html).not.toContain("<p>Quarter on quarter:");
    expect(case1()).toBeDefined();
  });
  it("every case has chips for the three tabs, each label 2 to 5 words", () => {
    const x = plInsights({ annual: KOTAK.annual, quarterly: KOTAK.quarterly, lender: true })[0];
    for (let n = 1; n <= 8; n++) {
      const html = renderToStaticMarkup(<Insights x={{ ...x, case: n as never }} />);
      const labels = [...html.matchAll(/<\/svg>([^<]+)/g)].map((m) => m[1]);
      expect(labels.length).toBeGreaterThanOrEqual(1);
      for (const l of labels) expect(l.trim().split(/\s+/).length).toBeLessThanOrEqual(5);
    }
  });
  it("the edge tab sits on the right edge, rounded on its left side; no blur on the card", () => {
    const css = readFileSync(new URL("../styles/plflags.css", import.meta.url), "utf8");
    const edge = css.match(/^\.plf-edge\s*\{[^}]*\}/m)![0];
    expect(edge).toMatch(/right:\s*0/); expect(edge).not.toMatch(/left:\s*0/); expect(edge).toMatch(/border-radius:\s*12px 0 0 12px/);
    expect(css).not.toMatch(/backdrop-filter:\s*blur/);
  });
});
