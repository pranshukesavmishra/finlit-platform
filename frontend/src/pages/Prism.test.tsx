// Renders the Prism page and report with the real-engine fixtures (no browser): sections present, no advice words, NOT RATED hides scores.
import { renderToStaticMarkup } from "react-dom/server";
import { Route, Routes, StaticRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import report from "../lib/__fixtures__/prismReport.json";
import variants from "../lib/__fixtures__/prismVariants.json";
import type { PrismReport } from "../lib/prism";

const state = vi.hoisted(() => ({ latest: null as unknown, gold: true, admin: true, calc: { phase: "idle" } as unknown }));
vi.mock("../lib/prism", async (orig) => {
  const m = await orig<typeof import("../lib/prism")>();
  return {
    ...m,
    useLatestPrism: () => ({ data: state.latest, isLoading: false, isError: false, refetch: () => undefined }),
    useGeneratePrism: () => ({ mutate: () => undefined, isPending: false, isError: false }),
    usePrismCalculation: () => ({ calc: state.calc, start: () => Promise.resolve() }),
    usePrismStatus: () => ({ data: { name: "FinLit Prism", available: true, reason: null, modelVersion: "3.6.10" } }),
  };
});
vi.mock("../lib/premium", () => ({ useGold: () => state.gold, useSlashFocus: () => undefined, pushRecent: () => undefined, readRecent: () => [] }));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ showcase: [], isAdmin: state.admin }) }));
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
    expect(html).toMatch(/pzr-lab average/);
    expect(t).toContain("Average");
    expect(t).toContain("Rated");
    expect(t).toContain("100% of inputs available");
    expect(t).toContain("not a probability");
    expect(t).toContain("Model 3.6.10");
    for (const name of ["Fundamentals", "Valuation", "Quality", "Risk"]) expect(t).toContain(name);
    expect(t).toContain("40% of the overall score");
    expect(t).toContain("Technical view: separate from this score");
    expect(t).toContain("All applicable factors have usable inputs");
    for (const k of ["Fundamentals", "Valuation", "Quality", "Risk"]) expect(html).toContain(`aria-label="${k} factors"`);
    for (const w of ["Strengths", "Concerns", "Estimated or missing", "What moved the score"]) expect(t).toContain(w);
    expect(t).toContain("Period used: 2021 to 2026.");
    expect(t).toContain("Company P/E: 48.01x. Industry peer median: 38.00x. Source: FinEdge. Uses 41 positive multiples; 46 of 52 peer records available.");
    for (const w of ["Quarterly results", "Annual results", "Key financial ratios", "Market price", "Balance sheet", "Ownership", "Quarterly results"]) expect(t).toContain(w);
    expect(t).toContain("Valuation against the benchmark");
    expect(t).toContain("Industry P/E median 38.00×");
    expect(t).toContain("Consolidated statements are used throughout");
    expect(t).toContain("Describes the company's financial health from its filings and prices; not a recommendation.");
    expect(t).toContain("Show as table");
  });
  it("gives every chart a conclusion as its aria-label", () => {
    expect(html).toContain('aria-label="Sales rose from ₹2,400 Cr in 2021 to ₹4,295 Cr in 2026."');
    expect(html).toMatch(/aria-label="Overall 54\.5 is the sum of Fundamentals 27\.5 of 40/);
    expect(html).toContain("Fundamentals: 68.8 out of 100");
    expect(html).toMatch(/aria-label="FinLit Prism score 54\.5 out of 100: Average\. Status: Rated\./);
  });
  it("does not leak internals", () => {
    for (const w of ["calculationTrace", "inputHash", "snapshotReceipt", R.id]) expect(html).not.toContain(w);
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
    expect(t).toContain("2 factors unavailable");
    expect(t).toContain("2 limited histories");
    expect(t).toContain("Annual P&L interest expense.");
    expect(t).toContain("Group estimate used: 50/100.");
    expect(t).toContain("3 of 10 year-on-year comparisons available");
    expect(t).toContain("7 of 14 observations available");
    expect(t).toContain("Data check: review required");
    expect(t).toContain("Consolidated statements were requested but unavailable");
    expect(t).toContain("Estimated");
  });
  it("NOT RATED hides every category score", () => {
    const html = renderToStaticMarkup(<PrismReportView report={V.notRated} actions={{}} />);
    const t = text(html);
    expect(t).toContain("Not rated");
    expect(t).toContain("no category scores are shown");
    expect(html).toContain("Category scores are withheld because the company is not rated.");
    expect(html).not.toContain("What moved the score</h3><p>Each part adds");
    expect(t).not.toMatch(/58\.2|63\.8|16\.5|67\.1/);
  });
  it("an older report without a review asks for a recalculation instead of inventing commentary", () => {
    const { review: _r, ...old } = R;
    const t = text(renderToStaticMarkup(<PrismReportView report={old as unknown as PrismReport} actions={{}} />));
    expect(t).toContain("Recalculate this report to see the latest missing-input");
    expect(t).not.toContain("All applicable scoring factors have usable inputs");
  });
  it("has no PDF button or PDF window in the report itself: the download sits in the page bar", () => {
    const t = text(renderToStaticMarkup(<PrismReportView report={{ ...R, pdfAvailableUntil: null }} actions={{}} />));
    expect(t).not.toContain("PDF window");
    expect(t).not.toContain("Download");
    expect(t).toContain("Recalculate");
  });
});

describe("Prism page", () => {
  it("shows a clear generate button when nothing is stored", () => {
    state.latest = null; state.gold = true;
    const t = text(page("/prism/TCS"));
    expect(t).toContain("Generate the Prism rating");
    expect(t).toContain("under half a minute");
  });
  it("while a calculation runs it shows a plain progress bar with the real elapsed seconds, not a spinner", () => {
    state.latest = null; state.gold = true;
    state.calc = { phase: "working", startedAt: Date.now() - 7000, expectedSeconds: 14 };
    const html = page("/prism/TCS"), t = text(html);
    state.calc = { phase: "idle" };
    expect(html).toContain('role="progressbar"');
    expect(html).not.toContain("pzr-spin");
    expect(t).toContain("Calculating the rating");
    expect(t).toMatch(/\b[6-8] seconds so far/);
    expect(t).toContain("about 14 seconds");
    expect(t).not.toContain("Generate the Prism rating");      // the empty card does not sit beside a running calculation
    expect(t).not.toContain("two minutes");
  });
  it("a failed calculation says why and offers Retry, and is never left as a spinner", () => {
    state.latest = null; state.gold = true;
    state.calc = { phase: "failed", problem: { kind: "unavailable", title: "The rating could not be calculated", text: "The data providers did not answer in time." }, retryable: true };
    const html = page("/prism/TCS"), t = text(html);
    state.calc = { phase: "idle" };
    expect(t).toContain("The rating could not be calculated");
    expect(t).toContain("did not answer in time");
    expect(html).toMatch(/>Retry</);
    expect(html).not.toContain('role="progressbar"');
  });
  it("a running recalculation keeps the stored report on screen", () => {
    state.latest = R; state.gold = true;
    state.calc = { phase: "working", startedAt: Date.now(), expectedSeconds: 12 };
    const t = text(page("/prism/EXAMPLE"));
    state.calc = { phase: "idle" };
    expect(t).toContain("Calculating the rating");
    expect(t).toContain("Example Components Ltd");
  });
  it("shows the stored report with its actions", () => {
    state.latest = R; state.gold = true;
    const t = text(page("/prism/EXAMPLE"));
    expect(t).toContain("Download report (PDF)");
    expect(t).toContain("Recalculate");
    expect(t).toContain("Statement basis");
    state.admin = false;
    expect(text(page("/prism/EXAMPLE"))).not.toContain("Download report (PDF)");      // administrators only, for now
    state.admin = true;
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

describe("the income line is called Sales for every company, with a sector note", () => {
  const as = (group: string) => ({ ...R, rating: { ...R.rating, group } }) as PrismReport;
  const BANNED_WORDS = /net premium income/;   // (factor labels such as "Revenue growth" come from the model)
  it.each([["MFG", null], ["BANK", /net interest income: interest earned less interest paid/], ["NBFC", /net interest income/], ["INSURANCE", /net premium earned/]])("%s", (group, note) => {
    const t = text(renderToStaticMarkup(<PrismReportView report={as(group)} actions={{}} />));
    expect(t).toContain("Sales");
    expect(t).not.toMatch(BANNED_WORDS);
    expect(t).not.toContain("Net interest income ");
    if (note) expect(t).toMatch(note); else expect(t).not.toMatch(/net interest income|net premium earned/);
  });
});
