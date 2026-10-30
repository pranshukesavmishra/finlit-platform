import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TechAsOf } from "./PrismTechRow";
import { asOfText, goldDots } from "../lib/scoreBands";

describe("the technical view shows the day it is as of", () => {
  it("says the last completed trading day, and whether a newer day is coming", () => {
    const h = renderToStaticMarkup(<TechAsOf asOf="2026-10-23" />);
    expect(h).toContain("Technical view as of"); expect(h).toContain("23 Oct 2026"); expect(h).not.toContain("being added");
    expect(renderToStaticMarkup(<TechAsOf asOf="2026-10-16" stale refreshing />)).toContain("A newer day is being added now.");
    expect(renderToStaticMarkup(<TechAsOf asOf="2026-10-16" stale />)).toContain("added each evening");
    expect(renderToStaticMarkup(<TechAsOf asOf={null} />)).toBe("");
  });
  it("puts the date in the header dots' tooltips (technical dots only)", () => {
    const dots = goldDots({ kind: "report", final: 60, word: "Healthy", status: "RATED", parts: { fundamental: 70, valuation: 50, quality: 80, risk: 60 },
      short: { score: 31, rating: "Buy" }, long: { score: -12, rating: "Hold" }, techAsOf: "2026-10-23" })!;
    expect(dots[4].label).toContain("as of 23 Oct 2026"); expect(dots[5].label).toContain("as of 23 Oct 2026"); expect(dots[0].label).not.toContain("as of");
    expect(asOfText("2026-01-05")).toBe("5 Jan 2026");
  });
});
