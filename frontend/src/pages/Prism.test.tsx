// Renders the Prism page and report with the real-engine fixtures (no browser): sections present, no advice words, NOT RATED hides scores.
import { renderToStaticMarkup } from "react-dom/server";
import { Route, Routes, StaticRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import report from "../lib/__fixtures__/prismReport.json";
import variants from "../lib/__fixtures__/prismVariants.json";
import type { PrismReport } from "../lib/prism";

const state = vi.hoisted(() => ({ latest: null as unknown, gold: true }));
vi.mock("../lib/prism", async (orig) => {
  const m = await orig<typeof import("../lib/prism")>();
  return {
    ...m,
    useLatestPrism: () => ({ data: state.latest, isLoading: false, isError: false, refetch: () => undefined }),
    useGeneratePrism: () => ({ mutate: () => undefined, isPending: false, isError: false }),
    usePrismStatus: () => ({ data: { name: "FinLit Prism", available: true, reason: null, modelVersion: "3.6.9" } }),
  };
});
vi.mock("../lib/premium", () => ({ useGold: () => state.gold, useSlashFocus: () => undefined, pushRecent: () => undefined, readRecent: () => [] }));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ showcase: [] }) }));
vi.mock("../lib/api", async (orig) => ({ ...(await orig<typeof import("../lib/api")>()), useSearchIndex: () => ({ data: undefined }) }));
vi.mock("../lib/screener", () => ({ useUniverse: () => ({ data: undefined, isLoading: false, isError: false }) }));
vi.mock("../lib/ui", () => ({ useUI: () => ({ has: () => state.gold, upgrade: () => undefined }), TIER: { gold: { n: "Gold", ic: "crown", tc: "--t-gold" } } }));

import { PrismPage } from "./Prism";
import { PrismReportView } from "../components/prism/ReportView";

const page = (path: string) => renderToStaticMarkup(<StaticRouter location={path}><Routes><Route path="/prism" element={<PrismPage />} /><Route path="/prism/:symbol" element={<PrismPage />} /></Routes></StaticRouter>);
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/\s+/g, " ");
// The PDF window is real time; keep it open for the tests that look at the download button.
const R = { ...(report as unknown as PrismReport), pdfAvailableUntil: "2999-01-01T00:00:00+00:00" };
const V = variants as unknown as { limited: PrismReport; notRated: PrismReport };

describe("Prism report", () => {
  const html = renderToStaticMarkup(<PrismReportView report={R} actions={{}} />);
  const t = text(html);
  it("shows the headline, the four parts, completeness, dates, history, factors, notes and benchmarks", () => {
    expect(t).toContain("Example Components Ltd");
    expect(t).toContain("54.5");
    expect(html).toMatch(/pz-lab average/);
    expect(t).toContain("Average");
    expect(t).toContain("Rated");
    expect(t).toContain("100% data coverage");
    expect(t).toContain("not a probability");
    for (const name of ["Fundamentals", "Valuation", "Quality", "Risk"]) expect(t).toContain(name);
    expect(t).toContain("Counts for 40% of the overall score");
    expect(html).toContain('aria-label="Input completeness"');
    expect(t).toContain("All applicable scoring factors have usable inputs");
    for (const k of ["fundamental", "valuation", "quality", "risk"]) expect(html).toContain(`aria-label="${k} factors"`);
    expect(html.match(/>Pros</g)).toHaveLength(4);
    expect(html.match(/>Cons</g)).toHaveLength(4);
    expect(t).toContain("Period used: 2021 to 2026.");
    expect(t).toContain("Company P/E: 48.01x. Industry peer median: 38.00x. Source: FinEdge. Uses 41 positive multiples; 46 of 52 peer records available.");
    for (const w of ["Quarterly results", "Annual results", "Key financial ratios", "Market price", "Balance sheet", "Ownership", "Quarterly results"]) expect(t).toContain(w);
    expect(t).toContain("Valuation benchmarks");
    expect(t).toContain("Industry P/E median 38.00×");
    expect(t).toContain("Consolidated statements are used throughout");
    expect(t).toContain("Describes the company's financial health from its filings and prices; not a recommendation.");
    expect(t).toContain("Show as table");
  });
  it("gives every chart a conclusion as its aria-label", () => {
    expect(html).toContain('aria-label="Revenue rose from ₹2,400 Cr in 2021 to ₹4,295 Cr in 2026."');
    expect(html).toMatch(/aria-label="Growth against the previous year, 2026: revenue \+10\.8%/);
    expect(html).toMatch(/aria-label="Category scores out of 100: Fundamentals 68\.8/);
    expect(html).toMatch(/aria-label="FinLit Prism score 54\.5 out of 100: Average\. Status: Rated\./);
  });
  it("does not leak internals", () => {
    for (const w of ["calculationTrace", "inputHash", "snapshotReceipt", "3.6.9", R.id]) expect(html).not.toContain(w);
  });
  it("never uses advice words", () => {
    for (const r of [R, V.limited, V.notRated]) {
      const all = text(renderToStaticMarkup(<PrismReportView report={r} actions={{}} />)).toLowerCase();
      expect(all).not.toMatch(/\b(buy|sell|avoid)\b/);
    }
  });
});

describe("limited and not-rated reports", () => {
  it("lists missing inputs and short histories, the data caution and the basis switch", () => {
    const t = text(renderToStaticMarkup(<PrismReportView report={V.limited} actions={{}} />));
    expect(t).toContain("Provisional");
    expect(t).toContain("Unavailable factors: 2 · Limited histories: 2");
    expect(t).toContain("Annual P&L interest expense.");
    expect(t).toContain("Group estimate used: 50/100.");
    expect(t).toContain("3 of 10 year-on-year comparisons available");
    expect(t).toContain("7 of 14 observations available");
    expect(t).toContain("Data check: review required");
    expect(t).toContain("Consolidated statements were requested but unavailable");
    expect(t).toContain("Estimated or unavailable information");
  });
  it("NOT RATED hides every category score", () => {
    const html = renderToStaticMarkup(<PrismReportView report={V.notRated} actions={{}} />);
    const t = text(html);
    expect(t).toContain("Not rated");
    expect(t).toContain("no category scores are shown");
    expect(html).toContain("Category scores are withheld because the company is not rated.");
    expect(t).not.toMatch(/58\.2|63\.8|16\.5|67\.1/);
  });
  it("an older report without a review asks for a recalculation instead of inventing commentary", () => {
    const { review: _r, ...old } = R;
    const t = text(renderToStaticMarkup(<PrismReportView report={old as unknown as PrismReport} actions={{}} />));
    expect(t).toContain("Recalculate this report to see the latest missing-input");
    expect(t).not.toContain("All applicable scoring factors have usable inputs");
  });
  it("offers a recalculation, not a download, once the PDF window has passed", () => {
    const t = text(renderToStaticMarkup(<PrismReportView report={{ ...R, pdfAvailableUntil: "2000-01-01T00:00:00+00:00" }} actions={{}} />));
    expect(t).toContain("PDF window passed");
    expect(t).not.toContain("Download PDF");
  });
});

describe("Prism page", () => {
  it("shows a clear generate button when nothing is stored", () => {
    state.latest = null; state.gold = true;
    const t = text(page("/prism/TCS"));
    expect(t).toContain("Generate the Prism rating");
    expect(t).toContain("up to two minutes");
  });
  it("shows the stored report with its actions", () => {
    state.latest = R; state.gold = true;
    const t = text(page("/prism/EXAMPLE"));
    expect(t).toContain("Download PDF");
    expect(t).toContain("Recalculate");
    expect(t).toContain("Statement basis");
  });
  it("locks the page for other plans and previews a fictional example", () => {
    state.gold = false;
    const html = page("/prism/TCS"), t = text(html);
    expect(t).toContain("FinLit Prism is part of Gold");
    expect(t).toContain("Unlock with Gold");
    expect(t).toContain("a fictional company, not TCS");
    expect(t).not.toMatch(/\b(buy|sell|avoid)\b/i);
  });
  it("the landing page searches and browses", () => {
    state.gold = true;
    const t = text(page("/prism"));
    expect(t).toContain("Choose a company");
    expect(t).toContain("Browse companies");
    expect(t).toContain("20 a day");
  });
});
