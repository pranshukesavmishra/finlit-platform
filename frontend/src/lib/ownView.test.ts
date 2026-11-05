import { describe, expect, it } from "vitest";
import fixture from "./__fixtures__/ownershipInsightsReliance.json";
import { CHARTED, chartFor, chartNote, crossoverNote, csvText, donutArcs, factItems, lakh, movesFor, pc, r1, seriesFromTable, shareCountChange, signedPts, slicesAt, windowIndexes, yScale, type OwnInsights } from "./ownView";

const ins = fixture as unknown as OwnInsights;
const S = seriesFromTable(ins.table!);
const last = S.periods.length - 1;
const row = (k: string) => ins.table!.find((r) => r.key === k)!;

describe("the section's numbers equal the stored insights (RELIANCE fixture)", () => {
  it("every group's series is the fixture's spark, filing for filing", () => {
    expect(S.periods).toEqual(row("promoters").spark_periods);
    for (const r of ins.table!) expect(S.values[r.key as keyof typeof S.values]).toEqual(r.spark);
    expect(S.periods.length).toBe(21);
  });
  it("the donut and legend show table[].now for the latest filing", () => {
    const sl = slicesAt(S, last);
    expect(sl.map((s) => s.key)).toEqual(["promoters", "fii", "dii", "public", "government"]);
    for (const s of sl) expect(s.value).toBeCloseTo(row(s.key).now!, 2);
    expect(sl.map((s) => pc(s.value))).toEqual(["50.4%", "16.7%", "21.7%", "11.1%", "0.1%"]);
  });
  it("each chart's change, start and end are the fixture's (5Y)", () => {
    for (const k of CHARTED) {
      const m = chartFor(S, k, 20)!;
      expect(m.last!.value).toBe(row(k).now);
      expect(m.change!).toBeCloseTo(row(k).change_5y!, 2);
      expect(m.first!.period).toBe("Sep 2021");
    }
  });
  it("1-year bought/sold equals change_1y for every group", () => {
    const mv = movesFor(S, last, 4, ins.facts, last);
    for (const r of mv.rows) expect(r.delta!).toBeCloseTo(row(r.key).change_1y!, 2);
    expect(mv.rows.map((r) => r.badge)).toEqual(["▲ Bought 0.4 pts", "▼ Sold 2.0 pts", "▲ Bought 1.4 pts", "▲ Bought 0.2 pts"]);
    expect(mv.from).toBe("Sep 2025"); expect(mv.to).toBe("Sep 2026");
  });
  it("the facts cards equal facts (shareholders, pledge, share count, lock-in) and the holders are listed", () => {
    expect(factItems(ins.facts, null).map((f) => [f.label, f.value, f.note])).toEqual([
      ["Shareholders", "50.7 lakh", "+15% in a year"], ["Promoter shares pledged", "0.0%", "None pledged"], ["Shares outstanding", "1,353 crore", "Unchanged in a year"], ["Shares under lock-in", "0.0%", "No lock-in"]]);
    expect(ins.facts!.top_holders!.map((h) => [h.name, h.year_ago, h.now])[0]).toEqual(["Life Insurance Corporation of India", 6.94, 7.11]);
  });
});

describe("rounding and wording helpers", () => {
  it("rounds halves the way people do and never shows a blank as zero", () => {
    expect(r1(18.65)).toBe(18.7); expect(r1(-1.98)).toBe(-2); expect(pc(null)).toBe("–"); expect(pc(50.44)).toBe("50.4%");
    expect(signedPts(10.76)).toBe("▲ +10.8 pts"); expect(signedPts(-0.17)).toBe("▼ −0.2 pts"); expect(signedPts(0.03)).toBe("No change");
    expect(lakh(5072457)).toBe("50.7 lakh"); expect(lakh(12345678)).toBe("1.23 crore"); expect(lakh(76317)).toBe("76,317");
  });
  it("donut arcs add up to the circle (less the gaps)", () => {
    const arcs = donutArcs(slicesAt(S, last));
    expect(arcs).toHaveLength(5);
    const C = 2 * Math.PI * 80;
    expect(arcs.reduce((a, x) => a + parseFloat(x.dash), 0)).toBeGreaterThan(C - 12);
    expect(arcs.reduce((a, x) => a + parseFloat(x.dash), 0)).toBeLessThan(C + 0.01);
  });
});

describe("who bought and who sold: the 0.5% share-count rule", () => {
  const facts = (by: Record<string, number>, y?: number) => ({ share_count_by_period: by, share_count_change_1y_pct: y });
  it("unchanged share count: Bought / Sold and the plain note", () => {
    const m = movesFor(S, last, 4, facts({ "Sep 2025": 1000, "Sep 2026": 1003 }), last);
    expect(m.mode).toBe("trade"); expect(m.rows[0].badge).toBe("▲ Bought 0.4 pts"); expect(m.rows[1].badge).toBe("▼ Sold 2.0 pts");
    expect(m.note).toBe("No new shares were issued in this period, so a rise means buying and a fall means selling.");
  });
  it("0.5% or more: Up / Down and a note that the share count changed", () => {
    const m = movesFor(S, last, 4, facts({ "Sep 2025": 1000, "Sep 2026": 1005 }), last);
    expect(m.mode).toBe("issued"); expect(m.rows[0].badge).toBe("▲ Up 0.4 pts"); expect(m.rows[1].badge).toBe("▼ Down 2.0 pts");
    expect(m.note).toContain("new shares were issued"); expect(m.note).not.toContain("a rise means buying");
    const bb = movesFor(S, last, 4, facts({ "Sep 2025": 1000, "Sep 2026": 990 }), last);
    expect(bb.mode).toBe("issued"); expect(bb.note).toContain("bought back");
  });
  it("exactly 0.5% counts as changed; just under does not", () => {
    expect(movesFor(S, last, 4, facts({ "Sep 2025": 1000, "Sep 2026": 1005 }), last).mode).toBe("issued");
    expect(movesFor(S, last, 4, facts({ "Sep 2025": 1000, "Sep 2026": 1004.9 }), last).mode).toBe("trade");
  });
  it("a missing share count for a filing says so, with Up / Down", () => {
    const m = movesFor(S, last, 20, ins.facts, last);                      // Sep 2021 is not among the 13 counts
    expect(m.mode).toBe("unknown"); expect(m.rows[2].badge).toBe("▲ Up 10.8 pts"); expect(m.rows[0].badge).toBe("▼ Down 0.2 pts"); expect(m.note).toBe("The share count for Sep 2021 is not in the data, so a change may include new shares issued; the badges say Up or Down.");
  });
  it("the 1-year figure in the facts stands in when the per-filing counts are missing", () => {
    expect(shareCountChange({ share_count_change_1y_pct: 3.4 }, "Sep 2025", "Sep 2026", true)).toBe(3.4);
    expect(shareCountChange({ share_count_change_1y_pct: 3.4 }, "Sep 2025", "Sep 2026", false)).toBeNull();
    expect(movesFor(S, last, 4, { share_count_change_1y_pct: 3.4 }, last).mode).toBe("issued");
  });
  it("every window of the fixture: last quarter, 1, 3 and 5 years", () => {
    expect(movesFor(S, last, 1, ins.facts, last).from).toBe("Jun 2026");
    expect(movesFor(S, last, 12, ins.facts, last).from).toBe("Sep 2023");
    expect(movesFor(S, last, 12, ins.facts, last).mode).toBe("trade");     // 1353.22 -> 1353.25
    expect(movesFor(S, last, 20, ins.facts, last).from).toBe("Sep 2021");
  });
  it("an earlier year uses that year's last filing, and the first filing has nothing to compare", () => {
    const sel = S.periods.indexOf("Sep 2024");
    const m = movesFor(S, sel, 4, ins.facts, last);
    expect(m.from).toBe("Sep 2023"); expect(m.to).toBe("Sep 2024");
    const first = movesFor(S, 0, 4, ins.facts, last);
    expect(first.rows.every((r) => r.badge === "Not filed")).toBe(true);
  });
});

describe("the line charts: scale rule, axis steps, windows", () => {
  it("a window is 5, 13 or 21 filings, fewer when the history is short", () => {
    expect(windowIndexes(21, 4)).toHaveLength(5); expect(windowIndexes(21, 12)).toHaveLength(13); expect(windowIndexes(21, 20)).toHaveLength(21);
    expect(windowIndexes(41, 20)[0]).toBe(20); expect(windowIndexes(6, 20)).toHaveLength(6); expect(windowIndexes(21, 4)[4]).toBe(20);
  });
  it("is at least 4 pts tall around the middle, plus 8% padding", () => {
    const s = yScale([50, 50.66]);
    expect(s.hi - s.lo).toBeCloseTo(4 * 1.16, 5);
    expect((s.lo + s.hi) / 2).toBeCloseTo(50.33, 5);
  });
  it("uses the real range when it is taller than 4 pts", () => {
    const s = yScale([16.67, 27.68]);
    expect(s.hi - s.lo).toBeCloseTo(11.01 * 1.16, 5);
  });
  it("labels every 1, 2, 5 or 10: the first step that gives at most four", () => {
    expect(yScale([50, 50.66]).ticks).toEqual([50, 52]);                       // 4.64 tall: 2
    expect(yScale([10, 12]).step).toBe(2);                                      // never 1: a chart is at least 4.64 tall, which is 5 labels at a step of 1
    expect(yScale([10, 25]).step).toBe(5);                                      // 17.4 tall: 5
    expect(yScale([10, 60]).step).toBe(10);                                     // 58 tall: even 10 gives six labels, 10 is the last step
    expect(yScale([0, 100]).step).toBe(10);
  });
  it("Foreign and Domestic 5Y labels match the team's screenshots", () => {
    expect(chartFor(S, "fii", 20)!.ticks.map((t) => t.value)).toEqual([20, 25]);
    expect(chartFor(S, "dii", 20)!.ticks.map((t) => t.value)).toEqual([15, 20]);
    expect(chartFor(S, "public", 20)!.ticks.map((t) => t.value)).toEqual([10, 12]);
    expect(chartFor(S, "promoters", 20)!.ticks.map((t) => t.value)).toEqual([50, 52]);
  });
  it("each chart has its own scale; a window uses only its own filings", () => {
    const a = chartFor(S, "promoters", 4)!, b = chartFor(S, "promoters", 20)!;
    expect(a.points).toHaveLength(5); expect(b.points).toHaveLength(21);
    expect(a.first!.period).toBe("Sep 2025"); expect(a.last!.period).toBe("Sep 2026");
    expect(a.lo).not.toBe(b.lo);
  });
  it("the line starts at the first filing and ends at the last, with its dots on the line", () => {
    const m = chartFor(S, "dii", 12)!;
    expect(m.path.startsWith("M0.0 ")).toBe(true); expect(m.path.split(" L")[0]).toBeTruthy();
    expect(m.xOf(0)).toBe(0); expect(m.xOf(12)).toBe(100);
    expect(m.yOf(m.first!.value!)).toBeGreaterThan(m.yOf(m.last!.value!));   // a rising line: the start sits lower
  });
  it("a missing filing is skipped, and fewer than two points draws nothing", () => {
    const gap = { periods: S.periods.slice(0, 5), values: { promoters: [50, null, 50.2, null, 50.4] } };
    expect(chartFor(gap, "promoters", 4)!.path.match(/[ML]/g)).toHaveLength(3);
    expect(chartFor({ periods: ["Sep 2026"], values: { promoters: [50] } }, "promoters", 4)).toBeNull();
    expect(chartFor(S, "government", 4)).not.toBeNull();                      // computed, but the page does not chart Government
    expect(CHARTED).not.toContain("government");
  });
  it("the note under the charts gives Government's share and when Indian funds passed foreign funds", () => {
    expect(chartNote(S)).toBe("Each chart has its own scale, at least 4 pts tall, so small moves stay small. Government holds 0.1%. Indian funds have held more than foreign funds since Mar 2025.");
    expect(crossoverNote({ periods: ["a", "b"], values: { fii: [10, 20], dii: [20, 10] } })).toBe("Foreign funds have held more than Indian funds since b.");
    expect(crossoverNote({ periods: ["a", "b"], values: { fii: [10, 12], dii: [20, 22] } })).toBeNull();
  });
});

describe("the numbers table and the CSV", () => {
  it("the CSV has every filing and every group, with the fixture's values", () => {
    const lines = csvText(S).split("\n");
    expect(lines[0]).toBe("Filing,Promoters,Foreign institutions,Domestic institutions,Retail & others,Government");
    expect(lines).toHaveLength(22);
    expect(lines[1]).toBe("Sep 2021,50.61,27.68,10.96,10.56,0.18");
    expect(lines[21]).toBe("Sep 2026,50.44,16.67,21.72,11.07,0.09");
  });
  it("a missing figure is an empty cell", () => {
    expect(csvText({ periods: ["a", "b"], values: { promoters: [1, null] } })).toBe("Filing,Promoters\na,1\nb,");
  });
});

describe("also from the filing: every blank says why", () => {
  it("gives the reason in each card when the premium part is missing", () => {
    const items = factItems({}, "These details come from the data provider and are fetched overnight.");
    expect(items.map((i) => i.value)).toEqual(["–", "–", "–", "–"]);
    for (const i of items) expect(i.note).toBe("These details come from the data provider and are fetched overnight.");
  });
  it("a pledge, a lock-in and a share issue read plainly", () => {
    const f = factItems({ shareholders: 76317, shareholders_change_1y_pct: -12.4, promoter_pledged_pct: 10.4, share_count_cr: 12.5, share_count_change_1y_pct: 3.43, locked_in_pct: 29.6 }, null);
    expect(f[0]).toMatchObject({ value: "76,317", note: "−12% in a year" }); expect(f[1]).toMatchObject({ value: "10.4%", note: "of promoters’ shares" });
    expect(f[2]).toMatchObject({ value: "13 crore", note: "+3.4% in a year" }); expect(f[3]).toMatchObject({ value: "29.6%", note: "cannot be sold yet" });
  });
});
