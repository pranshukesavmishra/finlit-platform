import { describe, expect, it } from "vitest";
import { TRENDS, changeText, folios, money, monthLabel, pctSigned, tone, trendSeries, type InsightsOk } from "./mfInsights";

describe("Indian units", () => {
  it("amounts in crore read as lakh crore from ₹1 lakh crore up, else whole crore", () => {
    expect(money(8264116.63)).toBe("₹82.64 L cr");
    expect(money(-133375.57)).toBe("−₹1.33 L cr");
    expect(money(41353.6, true)).toBe("+₹41,354 cr");
    expect(money(-443771.11, true)).toBe("−₹4.44 L cr");
    expect(money(0, true)).toBe("₹0 cr");
    expect(money(null)).toBe("—");
  });
  it("folios read as crore, lakh or the plain count", () => {
    expect(folios(286231680)).toBe("28.62 cr");
    expect(folios(2712595, true)).toBe("+27.13 lakh");
    expect(folios(-768)).toBe("−768");
    expect(folios(undefined)).toBe("—");
  });
  it("percent, tone and months", () => {
    expect(pctSigned(0.9568)).toBe("+0.96%");
    expect(pctSigned(-5.1)).toBe("−5.10%");
    expect(pctSigned(null)).toBe("");
    expect([tone(2), tone(-1), tone(0), tone(null)]).toEqual(["pos", "neg", "", ""]);
    expect(monthLabel("2026-09")).toBe("Sep 2026");
    expect(monthLabel("2026-09-30", true)).toBe("Sep 26");
    expect(monthLabel("garbage")).toBe("garbage");
  });
  it("a change against the month before, or why there is none", () => {
    const k = { value: 286231680, prev: 283519085, change: 2712595, changePct: 0.96 };
    expect(changeText(k, folios, "2026-08")).toBe("+27.13 lakh (+0.96%) vs Aug 2026");
    expect(changeText({ ...k, change: null }, folios, null)).toMatch(/no comparison/);
    expect(changeText({ value: -133375.57, prev: 41353.6, change: -174729.17, changePct: null }, money, "2026-08")).toBe("−₹1.75 L cr vs Aug 2026");
  });
});

describe("trend series", () => {
  const d = {
    series: { t: ["2026-07-31", "2026-08-31", "2026-09-30"], aum: [8575656.5, null, 8264116.6], netFlow: [235902, 41353, -133375], folios: [280865000, 283519085, 286231680], equityAum: [1, 2, 3] },
  } as unknown as InsightsOk;
  it("leaves out months without a figure and keeps the dates aligned", () => {
    const s = trendSeries(d, "aum");
    expect(s.t).toEqual(["2026-07-31", "2026-09-30"]);
    expect(s.v).toEqual([8575656.5, 8264116.6]);
    expect(trendSeries(d, "netFlow").v).toHaveLength(3);
  });
  it("axis labels in lakh crore and crore", () => {
    const [aum, net, fol] = TRENDS;
    expect(aum.axis(8000000)).toBe("80 L");
    expect(aum.axis(250000)).toBe("2.5 L");
    expect(net.axis(-200000)).toBe("−2.0 L");
    expect(fol.axis(250000000)).toBe("25 cr");
    expect(net.kind).toBe("bars");
  });
});
