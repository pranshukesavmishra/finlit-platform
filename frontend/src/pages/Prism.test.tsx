// Renders the Prism page and report with the real-engine fixtures (no browser): sections present, no advice words, NOT RATED hides scores.
import { renderToStaticMarkup } from "react-dom/server";
import { Route, Routes, StaticRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import report from "../lib/__fixtures__/prismReport.json";
import variants from "../lib/__fixtures__/prismVariants.json";
import technical from "../lib/__fixtures__/prismTechnical.json";
import { score1, type PrismReport } from "../lib/prism";
import { fmtScore, parseTechnical, ratingWord } from "../lib/prismTechnical";

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
import { Hero } from "../components/prism/pzr/Hero";

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
    for (const name of ["Growth & Profitability", "Valuation", "Quality", "Risk"]) expect(t).toContain(name);
    expect(t).toContain("How this score was calculated");
    expect(html).toContain('<details class="report-details"><summary>How this score was calculated</summary>');
    expect(t).not.toContain("Counts for 40%");
    expect(t).toContain("Technical view");
    expect(t).toContain("All applicable factors have usable inputs");
    for (const k of ["Growth & Profitability", "Valuation", "Quality", "Risk"]) expect(html).toContain(`aria-label="${k.replace("&", "&amp;")} factors"`);
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
    expect(html).toMatch(/aria-label="Overall 54\.5 is the sum of Growth &amp; Profitability 27\.5 of 40/);
    expect(html).toContain("Growth &amp; Profitability: 68.8 out of 100");
    expect(html).toContain('aria-label="Fundamental score 54.5 out of 100: Average"');
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
  it("while a calculation runs it shows elapsed seconds without inventing percentage progress", () => {
    state.latest = null; state.gold = true;
    state.calc = { phase: "working", startedAt: Date.now() - 7000, expectedSeconds: 14 };
    const html = page("/prism/TCS"), t = text(html);
    state.calc = { phase: "idle" };
    expect(html).not.toContain('role="progressbar"');
    expect(html).toContain('role="status"');
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
    expect(t).not.toContain("Statement basis"); expect(t).not.toContain("Standalone");
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

describe("Prism summary", () => {
  const tech = technical as unknown as Record<string, unknown>;
  const withTech = { ...R, technicalAssessment: tech.ready } as PrismReport;
  const th = parseTechnical(tech.ready)!;
  const hero = (r: PrismReport) => renderToStaticMarkup(<Hero report={r} actions={{}} />);
  it("shows one financial score and separate technical values with horizons", () => {
    const html = hero(withTech), t = text(html);
    expect(html.match(/Fundamental score 54\.5 out of 100/g)).toHaveLength(1);
    expect(html).not.toMatch(/pzr-ring|pzr-minis|pzr-scale/);
    expect(t).toContain(fmtScore(th.shortTerm.score)); expect(t).toContain(fmtScore(th.longTerm.score));
    expect(t).toContain(th.shortTerm.horizon!); expect(t).toContain(th.longTerm.horizon!);
    expect(t).toContain("Separate technical view");
    expect(html).toContain(`aria-label="Technical short term ${fmtScore(th.shortTerm.score)}: ${ratingWord(th.shortTerm.rating, th.shortTerm.score).word}, ${th.shortTerm.horizon}"`);
  });
  it("keeps a provisional score, but withholds an unrated score", () => {
    expect(text(hero({ ...R, rating: { ...R.rating, status: "PROVISIONAL" } }))).toContain(score1(R.rating.final));
    const html = hero({ ...V.notRated, technicalAssessment: tech.ready } as PrismReport);
    expect(html).toContain('aria-label="Fundamental score: not rated"');
    expect(text(html)).toContain(fmtScore(th.shortTerm.score));
    expect(html).not.toContain(`>${score1(V.notRated.rating.final)}<`);
  });
  it("distinguishes complete inputs from validation warnings", () => {
    const t = text(hero({ ...R, rating: { ...R.rating, confidence: 1, dataIntegrityStatus: "REVIEW REQUIRED" } }));
    expect(t).toContain("Input completeness 100%"); expect(t).toContain("Validation Review required");
    expect(t).toContain("Validation checks need a closer look");
    expect(t).not.toContain("Enough verified history");
  });
  it("does not invent a technical score or claim unknown checks passed", () => {
    const html = hero({ ...R, rating: { ...R.rating, dataIntegrityStatus: null } } as unknown as PrismReport);
    expect(html).not.toContain("Separate technical view");
    expect(text(html)).toContain("Validation Not checked");
  });
});
