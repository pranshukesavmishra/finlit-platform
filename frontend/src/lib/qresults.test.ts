import { describe, expect, it } from "vitest";
import { csvOf, gapAlertLink, headline, queryString, signedPct, type QRow } from "./qresults";

const base = { symbol: "ACME", revenue: 1057.8, revenueYoY: 37.2, revenueQoQ: 5.4, netProfit: 73.9, profitYoY: -36.2, profitQoQ: -35.6, opm: 12.34, npm: 6.99, eps: 3.1 };

describe("headline", () => {
  it("reads like a results alert", () => {
    expect(headline(base, "Q2 FY27")).toBe("ACME Q2 FY27: NET PROFIT DOWN 36% AT Rs73.90 CR (YOY), DOWN 36% (QOQ) / REVENUE UP 37% AT Rs1,057.80 CR (YOY), UP 5% (QOQ) / OPM 12.3%, NPM 7.0% / EPS Rs3.10");
  });
  it("leaves out what cannot be worked out instead of guessing", () => {
    expect(headline({ ...base, profitYoY: null, profitQoQ: null, revenueQoQ: null, opm: null, npm: null, eps: null })).toBe("ACME: NET PROFIT AT Rs73.90 CR / REVENUE UP 37% AT Rs1,057.80 CR (YOY)");
    expect(headline({ ...base, profitYoY: null, profitQoQ: 12 })).toContain("NET PROFIT AT Rs73.90 CR, UP 12% (QOQ)");
    expect(headline({ symbol: "X", revenue: null, revenueYoY: null, revenueQoQ: null, netProfit: null, profitYoY: null, profitQoQ: null, opm: null, npm: null, eps: null })).toBeNull();
  });
  it("calls a loss a loss", () => {
    expect(headline({ ...base, netProfit: -12.5, profitYoY: null, profitQoQ: -150, npm: -1.2, eps: -0.4 })).toContain("NET LOSS AT Rs12.50 CR, DOWN 150% (QOQ)");
    expect(headline({ ...base, netProfit: -12.5, profitYoY: null, profitQoQ: null, npm: -1.2, eps: -0.4 })).toMatch(/NPM −1\.2% \/ EPS -Rs0\.40$/);
  });
});

describe("helpers", () => {
  it("builds the query without defaults", () => {
    expect(queryString({ quarter: "2026-09", scope: "all", flagged: false, offset: 0, q: "", sort: "profitYoY", dir: "asc", index: "NIFTY50" })).toBe("quarter=2026-09&sort=profitYoY&dir=asc&index=NIFTY50");
    expect(queryString({ flagged: true, offset: 50, scope: "watchlist" })).toBe("flagged=true&offset=50&scope=watchlist");
  });
  it("signs percentages with a true minus", () => { expect(signedPct(3.26)).toBe("+3.3%"); expect(signedPct(-3.26)).toBe("−3.3%"); expect(signedPct(null)).toBe("—"); });
  it("links the gap to the alert", () => { expect(gapAlertLink("M&M")).toBe("/alerts?symbol=M%26M&metric=rev_profit_gap&value=15"); });
  it("writes a CSV a spreadsheet cannot run as a formula", () => {
    const r = { date: "2026-10-14", symbol: "A", name: "=cmd|' /C calc'!A0", sector: "IT, Software", marketCap: 100, status: "declared", revenue: 1, revenueYoY: -2.5, revenueQoQ: null, operatingProfit: 1, opm: 1, netProfit: 1, profitYoY: 1, profitQoQ: 1, npm: 1, npmChange: 1, eps: 1, gap: 3.5, flagged: false, hasNumbers: true } as unknown as QRow;
    const out = csvOf([r], "Jul to Sep 2026");
    expect(out.startsWith("﻿Quarter: Jul to Sep 2026\r\n")).toBe(true);
    expect(out).toContain("'=cmd|' /C calc'!A0");
    expect(out).toContain('"IT, Software"');
    expect(out).toContain(",-2.5,,");
  });
});
