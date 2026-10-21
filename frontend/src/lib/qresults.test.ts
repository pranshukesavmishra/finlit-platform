import { describe, expect, it } from "vitest";
import { activeChip, addDays, csvOf, dateChips, dateFromParams, dateProblem, describeSel, gapAlertLink, headline, isRealDay, isWeekend, mondayOf, queryString, quarterStartOf, signedPct, todayIST, type QRow } from "./qresults";

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

describe("announcement dates (India calendar days)", () => {
  const T = "2026-10-21";   // a Wednesday
  it("takes today from India, whatever the browser clock says", () => {
    expect(todayIST(new Date("2026-10-20T19:00:00Z"))).toBe("2026-10-21");   // 00:30 IST is already the next day
    expect(todayIST(new Date("2026-10-21T18:29:00Z"))).toBe("2026-10-21");
  });
  it("works out the quick choices", () => {
    const c = Object.fromEntries(dateChips(T).map((x) => [x.id, x.sel]));
    expect(c.today).toEqual({ date: T }); expect(c.yesterday).toEqual({ date: "2026-10-20" });
    expect(c.week).toEqual({ from: "2026-10-19", to: T }); expect(c.last7).toEqual({ from: "2026-10-15", to: T }); expect(c.quarter).toEqual({ from: "2026-10-01", to: T });
    expect(mondayOf("2026-10-25")).toBe("2026-10-19"); expect(mondayOf("2026-10-19")).toBe("2026-10-19");               // a Sunday belongs to the week before it
    expect(quarterStartOf("2026-03-31")).toBe("2026-01-01"); expect(quarterStartOf("2026-12-31")).toBe("2026-10-01"); expect(quarterStartOf("2026-05-02")).toBe("2026-04-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28"); expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });
  it("shows the matching chip as pressed", () => {
    expect(activeChip({ date: T }, T)).toBe("today"); expect(activeChip({ from: T, to: T }, T)).toBe("today"); expect(activeChip({ from: "2026-10-15" }, T)).toBe("last7");
    expect(activeChip({ date: "2026-10-05" }, T)).toBeNull(); expect(activeChip({}, T)).toBeNull();
  });
  it("refuses what cannot be looked up, in plain words", () => {
    expect(dateProblem({ date: T }, T)).toBeNull(); expect(dateProblem({ from: "2026-10-01", to: T }, T)).toBeNull(); expect(dateProblem({ from: "2026-10-01" }, T)).toBeNull();
    expect(dateProblem({ date: "2026-10-22" }, T)).toContain("up to today"); expect(dateProblem({ from: "2026-10-01", to: "2026-12-31" }, T)).toContain("up to today");
    expect(dateProblem({ from: "2026-10-20", to: "2026-10-01" }, T)).toBe("The from date is after the to date.");
    expect(dateProblem({ to: "2026-10-01" }, T)).toContain("from date"); expect(dateProblem({ date: "2026-02-30" }, T)).toContain("real date");
    expect(isRealDay("2026-02-29")).toBe(false); expect(isRealDay("2028-02-29")).toBe(true); expect(isRealDay("21-10-2026")).toBe(false);
  });
  it("reads deep links", () => {
    expect(dateFromParams(new URLSearchParams("date=2026-10-14&quarter=2026-09"))).toEqual({ date: "2026-10-14" });
    expect(dateFromParams(new URLSearchParams("from=2026-10-01&to=2026-10-14"))).toEqual({ from: "2026-10-01", to: "2026-10-14" });
    expect(dateFromParams(new URLSearchParams("date=2026-10-14&from=2026-10-01"))).toEqual({ date: "2026-10-14" });
    expect(dateFromParams(new URLSearchParams(""))).toEqual({});
    expect(queryString({ date: "2026-10-14", from: "", to: "" })).toBe("date=2026-10-14");
    expect(queryString({ from: "2026-10-01", to: "2026-10-14" })).toBe("from=2026-10-01&to=2026-10-14");
  });
  it("describes the choice and knows weekends", () => {
    expect(describeSel({ date: T }, T)).toBe("announced on Wed, 21 Oct 2026");
    expect(describeSel({ from: "2026-10-15", to: T }, T)).toBe("announced from Thu, 15 Oct 2026 to Wed, 21 Oct 2026");
    expect(isWeekend("2026-10-24")).toBe(true); expect(isWeekend("2026-10-21")).toBe(false);
  });
});

describe("operating profit columns in the CSV", () => {
  it("writes growth after the operating profit, and a blank where it cannot be worked out", () => {
    const r = { date: "2026-10-14", symbol: "A", name: "A", sector: null, marketCap: 1, status: "declared", revenue: 100, revenueYoY: 1, revenueQoQ: 2, operatingProfit: 33, opYoY: 50, opQoQ: null, opm: 20, netProfit: 10, profitYoY: 1, profitQoQ: 1, npm: 10, npmChange: 0, eps: 1, gap: 0, flagged: false, hasNumbers: true } as unknown as QRow;
    const out = csvOf([r], "Q");
    expect(out).toContain("Operating profit YoY %,Operating profit QoQ %,OPM %");
    expect(out).toContain(",33,50,,20,10,");
  });
});
