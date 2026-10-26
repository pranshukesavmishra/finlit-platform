// Logic of the Prism report page: contribution maths, arcs, factor filters and sorting, threshold ticks, history series, and the
// automatic fifth part. Fixtures are real-engine outputs (the example) and the production RELIANCE report.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PrismReportView } from "../components/prism/ReportView";
import reliance from "./__fixtures__/prismReliance.json";
import example from "./__fixtures__/prismReport.json";
import variants from "./__fixtures__/prismVariants.json";
import type { PrismMetric, PrismReport } from "./prism";
import {
  THRESHOLDS, arcSegments, bandLabel, capNotes, contributionTotal, contributions, daysBefore, filterFactors, monthIndex, peerRows, ratioPct,
  sortFactors, thresholdTicks, topFactors, valueBar, yoy,
} from "./prismReport";

const E = example as unknown as PrismReport, R = reliance as unknown as PrismReport, V = variants as unknown as { notRated: PrismReport; limited: PrismReport };

describe("contributions", () => {
  it("add up to the final score (weight x part score)", () => {
    for (const r of [E, R]) {
      const rows = contributions(r.rating);
      expect(rows).toHaveLength(4);
      expect(contributionTotal(rows)).toBeCloseTo(r.rating.final!, 6);
      rows.forEach((c) => expect(c.points + c.lost).toBeCloseTo(c.weight * 100, 9));
    }
  });
  it("are withheld when the company is not rated", () => { expect(contributions(V.notRated.rating)).toEqual([]); });
  it("reports caps honestly: nothing when none applied, the loss ceiling and its points when one did", () => {
    expect(capNotes(R.rating)).toEqual([]);
    const notes = capNotes({ lossCapped: true, valuationCapped: false, capPointsLost: 4.2, loss: { cap: 40, rawFundamental: 62 } as never });
    expect(notes[0]).toContain("limited to 40.0");
    expect(notes[0]).toContain("62.0");
    expect(notes[1]).toContain("4.2 points");
    expect(capNotes({ valuationCapped: true })[0]).toContain("limited to 60");
  });
  it("shows a cap's lost points on its part", () => {
    const rows = contributions({ ...R.rating, adjustments: [{ metric: "x", part: "valuation", rawScore: 70, cap: 60, pointsLost: 3 }] });
    expect(rows.find((c) => c.key === "valuation")!.capLost).toBe(3);
  });
});

describe("prism ring arcs", () => {
  it("arc length follows the weight and the fill follows the score", () => {
    const segs = arcSegments(R.rating, 0);
    expect(segs.map((s) => s.key)).toEqual(["fundamental", "valuation", "quality", "risk"]);
    expect(segs.map((s) => s.span)).toEqual([0.4, 0.3, 0.2, 0.1].map((x) => expect.closeTo(x, 9)));
    expect(segs[0].fill).toBeCloseTo(0.4 * R.rating.parts.fundamental! / 100, 9);
    expect(segs[3].start).toBeCloseTo(0.9, 9);
  });
  it("draws no fill for a company that is not rated", () => {
    expect(arcSegments(V.notRated.rating).every((s) => s.fill === 0 && s.score === null)).toBe(true);
  });
  it("adds a fifth arc when the data has a technical part", () => {
    const r = { ...R.rating, partWeights: { fundamental: 0.3, valuation: 0.25, quality: 0.2, risk: 0.1, technical: 0.15 }, parts: { ...R.rating.parts, technical: 60 } };
    const segs = arcSegments(r);
    expect(segs).toHaveLength(5);
    expect(segs[4].key).toBe("technical");
  });
});

describe("threshold ticks and bands", () => {
  it("are the label thresholds", () => { expect(thresholdTicks()).toEqual([35, 50, 65, 80]); expect(THRESHOLDS).toEqual([35, 50, 65, 80]); });
  it("map a score to the model's label", () => {
    expect([bandLabel(34.9), bandLabel(35), bandLabel(50), bandLabel(65), bandLabel(80), bandLabel(null)]).toEqual(["POOR", "WEAK", "AVERAGE", "HEALTHY", "STRONG", "NOT RATED"]);
  });
  it("places a factor's value between its 0-point and 100-point values, either direction", () => {
    const up = valueBar({ value: 10, worst: 0, best: 20, redBoundary: 8, greenBoundary: 14, status: "A" })!;
    expect(up.pos).toBeCloseTo(0.5); expect(up.red).toBeCloseTo(0.4); expect(up.green).toBeCloseTo(0.7);
    const down = valueBar({ value: 1.0, worst: 1.6, best: 0.6, redBoundary: 1.2, greenBoundary: 0.9, status: "A" })!;
    expect(down.pos).toBeCloseTo(0.6); expect(down.red).toBeCloseTo(0.4); expect(down.green).toBeCloseTo(0.7);
    expect(valueBar({ value: 99, worst: 0, best: 20, redBoundary: null, greenBoundary: null, status: "A" })!.pos).toBe(1);
  });
  it("has no bar for an estimate, a missing value or a factor without bounds", () => {
    expect(valueBar({ value: 5, worst: 0, best: 10, redBoundary: 3, greenBoundary: 7, status: "F" })).toBeNull();
    expect(valueBar({ value: null, worst: 0, best: 10, redBoundary: 3, greenBoundary: 7, status: "A" })).toBeNull();
    expect(valueBar({ value: 5, worst: null, best: null, redBoundary: null, greenBoundary: null, status: "A" })).toBeNull();
  });
});

describe("factor filters and sorting", () => {
  const rows = R.rating.metrics;
  it("strengths are 70+ actual points, concerns are below 40, estimated means F or L", () => {
    expect(filterFactors(rows, "strengths").every((r) => r.points! >= 70)).toBe(true);
    expect(filterFactors(rows, "concerns").every((r) => r.points! < 40)).toBe(true);
    expect(filterFactors(rows, "all")).toHaveLength(rows.length);
    const lim = V.limited.rating.metrics;
    const est = filterFactors(lim, "estimated");
    expect(est.length).toBeGreaterThan(0);
    expect(est.every((r) => r.status === "F" || r.status === "L")).toBe(true);
    expect(filterFactors(lim, "strengths").some((r) => r.status === "F" || r.status === "L")).toBe(false);
  });
  it("sorts by points, keeps ties in model order and puts missing points last", () => {
    const mk = (m: string, points: number | null) => ({ metric: m, points }) as PrismMetric;
    const list = [mk("a", 50), mk("b", null), mk("c", 90), mk("d", 50), mk("e", 10)];
    expect(sortFactors(list, "high").map((r) => r.metric)).toEqual(["c", "a", "d", "e", "b"]);
    expect(sortFactors(list, "low").map((r) => r.metric)).toEqual(["e", "a", "d", "c", "b"]);
    expect(sortFactors(list, "model")).toBe(list);
  });
  it("picks a top strength and a biggest drag from real factors only", () => {
    const { strength, drag } = topFactors(R.rating.metrics.filter((m) => m.part === "fundamental"));
    expect(strength!.points).toBeGreaterThanOrEqual(70);
    expect(drag!.points).toBeLessThan(70);
    const est = [{ metric: "x", status: "F", points: 50, share: 1 }, { metric: "y", status: "A", points: 20, share: 0.1, pointsLost: 1 }] as PrismMetric[];
    expect(topFactors(est).drag!.metric).toBe("y");
  });
});

describe("history series", () => {
  it("reads quarter, month and year labels", () => { expect([monthIndex("2023-03"), monthIndex("Mar 2023"), monthIndex("2023")]).toEqual([2023 * 12 + 2, 2023 * 12 + 2, 2023 * 12]); });
  it("computes year-on-year growth against the same period a year earlier, skipping gaps", () => {
    const g = yoy([{ period: "2021", value: 100 }, { period: "2022", value: 150 }, { period: "2023", value: null }, { period: "2024", value: 200 }]);
    expect(g[0]).toBeNull(); expect(g[1]).toBeCloseTo(50); expect(g[2]).toBeNull(); expect(g[3]).toBeNull();
    const q = yoy([{ period: "2023-03", value: 10 }, { period: "2023-06", value: 12 }, { period: "2024-03", value: 15 }, { period: "2024-06", value: 6 }]);
    expect(q[2]).toBeCloseTo(50); expect(q[3]).toBeCloseTo(-50);
    expect(yoy([{ period: "2023", value: -5 }, { period: "2024", value: 5 }])[1]).toBeNull();
  });
  it("margins are ratios of reported figures and never invented", () => { expect(ratioPct(25, 100)).toBe(25); expect(ratioPct(null, 100)).toBeNull(); expect(ratioPct(5, 0)).toBeNull(); });
  it("counts days from a data date to the calculation", () => { expect(daysBefore("2026-10-23", "2026-10-26T05:00:00+00:00")).toBe(3); expect(daysBefore(null, "2026-10-26")).toBeNull(); });
  it("lists the multiples that have a company figure or a benchmark", () => {
    const rows = peerRows(R);
    expect(rows.map((r) => r.key)).toEqual(["pe", "pb", "ev_ebitda"]);
    expect(rows[0].benchmark).toBeCloseTo(15.98);
    expect(rows[0].detail!.provider).toBe("Upstox");
  });
});

describe("report rendering", () => {
  it("shows a fifth part card and arc by itself when the model sends a technical part", () => {
    const r = JSON.parse(JSON.stringify(E)) as PrismReport;
    r.rating.partWeights = { fundamental: 0.3, valuation: 0.25, quality: 0.2, risk: 0.1, technical: 0.15 };
    r.rating.parts.technical = 61.2; r.rating.coverage.technical = 1;
    const html = renderToStaticMarkup(<PrismReportView report={r} />);
    expect(html).toContain("Technical: 61.2 out of 100");
    expect(html).not.toContain("Technical part coming soon");
  });
  it("marks the locked preview as an example", () => {
    expect(renderToStaticMarkup(<PrismReportView report={E} example />)).toContain("A fictional company, to show the layout");
  });
  it("renders the real RELIANCE report with its waterfall and benchmark", () => {
    const html = renderToStaticMarkup(<PrismReportView report={R} />);
    expect(html).toContain("Overall 58.4 is the sum of");
    expect(html).toContain("Sector P/E benchmark 15.98×");
    expect(html).toContain("No loss or valuation limit was applied");
  });
});
