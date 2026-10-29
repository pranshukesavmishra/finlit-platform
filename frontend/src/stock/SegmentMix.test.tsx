import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

// The help popover opens in a portal on document.body; it is not part of this card's own markup.
vi.mock("../components/ChartHelp", () => ({ ChartHelp: () => null }));
import type { Segments } from "../lib/api";
import real from "../lib/__fixtures__/segments-reliance-fixture.json";
import large from "../lib/__fixtures__/segments-large-fixture.json";
import { SegmentCard } from "./Sections2";
import { SegmentHistory } from "./SegmentMix";

const REAL = real as unknown as Segments, LARGE = large as unknown as Segments;
const card = (seg?: Segments) => renderToStaticMarkup(<MemoryRouter><SegmentCard seg={seg} /></MemoryRouter>);
const mk = (periods: string[], rows: Record<string, (number | null)[]>): Segments => ({
  meta: REAL.meta, unit: "Cr", periods, latest: [], segments: Object.fromEntries(Object.entries(rows).map(([k, v]) => [k, { revenue: v, ebit: v.map(() => null) }])),
});

describe("segment card with history", () => {
  it("keeps the latest-year strip and tiles and adds the chart, table and insights", () => {
    const html = card(LARGE);
    expect(html).toContain("Where the revenue comes from");
    expect(html).toContain('class="rib"');
    expect(html).toContain("seg-l2");
    expect(html).toContain("How the mix has changed");
    expect(html).toContain("Segment trends");
    expect(html).toContain("Revenue (₹ Cr)");
    expect(html).toContain("Share of revenue (%)");
    expect(html).toContain("Insights");
    expect(html).toContain("Information only, not advice");
    expect(html).toContain("sum of the segment revenues");
    expect(html).toContain('role="img"');
    expect(html).toContain("Stacked bar chart of revenue by segment");
    for (const y of ["FY19", "FY22", "FY26"]) expect(html).toContain(`>${y}<`);   // every year is labelled
    expect(html).toContain("6.62 L");                                              // lakh crore in the table
    expect(html).toContain("Retail gained the most share");
    expect(html).toContain("Discontinued") ;                                       // not-reported rows are explained
    expect(html).toContain("Not reported in FY26");
  });
  it("uses the same colour for a segment in the tile, the legend and the table", () => {
    const html = card(LARGE);
    expect(html.match(/--bc:var\(--k1\)/g)!.length).toBeGreaterThanOrEqual(3);   // tile, table row (and the strip)
    expect(html).toContain("background:var(--k1)");                                // legend + chart swatches
  });
  it("renders the real recorded data with its definition-change warning", () => {
    const html = card(REAL);
    expect(html).toContain("Definition may have changed");
    expect(html).toContain("Segment definitions can change when a company reorganises");
    expect(html).toContain("Petrochemicals");
  });
  it("never crashes on an older report without insights, and says what is missing", () => {
    const old = { ...REAL, insights: undefined } as Segments;
    const html = card(old);
    expect(html).toContain("How the mix has changed");
    expect(html).toContain("Segment trends");
    expect(html).not.toContain("mx-ins");
    expect(html).toContain("once this report is refreshed");
  });
  it("gives each honest empty state", () => {
    expect(renderToStaticMarkup(<SegmentHistory seg={mk(["FY24", "FY25", "FY26"], { A: [1, 2, 3] })} />)).toContain("This company reports a single business segment.");
    expect(renderToStaticMarkup(<SegmentHistory seg={mk([], {})} />)).toContain("Segment history is not available for this company.");
    const short = renderToStaticMarkup(<SegmentHistory seg={mk(["FY26"], { A: [1], B: [2] })} />);
    expect(short).toContain("Only 1 year of segment data is available");
    expect(short).not.toContain("<svg");
    const two = renderToStaticMarkup(<SegmentHistory seg={mk(["FY25", "FY26"], { A: [1, 2], B: [2, 2] })} />);
    expect(two).toContain("no trends are drawn yet") ;
  });
  it("does not use advice wording", () => {
    const text = card(LARGE).replace(/<[^>]+>/g, " ").toLowerCase();
    for (const w of [" buy ", " sell ", "accumulate", "avoid ", "target price", "recommend"]) expect(text).not.toContain(w);
  });
});
