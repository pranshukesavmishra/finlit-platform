import { describe, expect, it } from "vitest";
import { axisDay, barSpan, changePct, dayDomain, istDate, istDay, istMinutes, istTime, sessionStarts, status } from "./intraday";
import type { Intraday } from "./api";

const base: Intraday = {
  status: "ok", available: true, symbol: "RELIANCE", range: "1D", interval: 1, exchange: "NSE", source: "Dhan", asOf: "2026-10-23T11:00:30+05:30",
  session: "2026-10-23", sessions: ["2026-10-23"], lastBarAt: "2026-10-23T10:59:00+05:30", phase: "open", today: "2026-10-23",
  series: { t: ["2026-10-23T09:15:00+05:30", "2026-10-23T10:59:00+05:30"], o: [1400, 1410], h: [1402, 1412], l: [1399, 1408], c: [1401, 1414], v: [10, 20] },
};

describe("Indian time, whatever the visitor's zone", () => {
  it("reads +05:30 and UTC times as the same Indian clock time and date", () => {
    expect(istTime("2026-10-23T09:15:00+05:30")).toBe("09:15");
    expect(istTime("2026-10-23T03:45:00Z")).toBe("09:15");
    expect(istMinutes("2026-10-23T15:29:00+05:30")).toBe(929);
    expect(istDate("2026-10-22T20:00:00Z")).toBe("2026-10-23");          // 01:30 IST the next day
    expect(istDay("2026-10-23")).toBe("Fri, 23 Oct");
    expect(axisDay("2026-10-23T09:15:00+05:30", "5D")).toBe("Fri 23");
    expect(axisDay("2026-10-23T09:15:00+05:30", "1M")).toBe("23 Oct");
  });
  it("gives each bar its span, an hourly bar ending at the close", () => {
    expect(barSpan("2026-10-23T11:41:00+05:30", 1)).toBe("11:41–11:42");
    expect(barSpan("2026-10-23T15:15:00+05:30", 60)).toBe("15:15–15:30");
    expect(barSpan("2026-10-23T09:07:00+05:30", 1)).toBe("09:07–09:08");
  });
});

describe("axes", () => {
  it("1D spans the whole session, widened for the pre-open bar", () => {
    expect(dayDomain(["2026-10-23T09:15:00+05:30", "2026-10-23T10:59:00+05:30"], 1)).toEqual([555, 930]);
    expect(dayDomain(["2026-10-23T09:07:00+05:30", "2026-10-23T15:29:00+05:30"], 1)).toEqual([547, 930]);
  });
  it("finds the first bar of every session", () => {
    expect(sessionStarts(["2026-10-22T09:15:00+05:30", "2026-10-22T15:15:00+05:30", "2026-10-23T09:15:00+05:30"])).toEqual([0, 2]);
  });
  it("measures change from the first bar's open", () => {
    expect(changePct(base)).toBeCloseTo(1, 10);
    expect(changePct({ ...base, series: undefined })).toBeNull();
  });
});

describe("status line", () => {
  it("says live, with source and as-of time, while today's session runs", () => {
    const s = status(base);
    expect(s.title).toBe("Live · Fri, 23 Oct");
    expect(s.asOf).toBe("Dhan (NSE) · 1-minute bars · as of 11:00 IST");
    expect(s.note).toBeNull();
  });
  it("labels the last session with its date on a weekend and never claims a holiday", () => {
    const s = status({ ...base, today: "2026-10-24", phase: "closed", asOf: "2026-10-24T11:00:00+05:30" });
    expect(s.title).toBe("Last session · Fri, 23 Oct, 2026");
    expect(s.note).toBe("The market is closed.");
    expect(s.asOf).toContain("as of 11:00 IST, Sat, 24 Oct");
    expect(status({ ...base, today: "2026-10-26", phase: "open" }).note).toBe("No trade in this stock today so far.");
    expect(status({ ...base, today: "2026-10-26", phase: "pre_open" }).note).toBe("Today's session has not opened yet.");
  });
  it("never says live on a stale copy, and shows why", () => {
    const s = status({ ...base, stale: true, detail: "The intraday price source did not answer, so this is the last copy we have." });
    expect(s.title.startsWith("Live")).toBe(false);
    expect(s.note).toContain("last copy");
  });
  it("names the span of a multi-day range and its bar size", () => {
    const s = status({ ...base, range: "1M", interval: 60, sessions: ["2026-09-22", "2026-10-23"] });
    expect(s.title).toBe("Tue, 22 Sept to Fri, 23 Oct");
    expect(s.asOf).toContain("hourly bars");
  });
});
