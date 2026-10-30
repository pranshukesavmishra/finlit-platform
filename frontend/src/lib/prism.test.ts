import { describe, expect, it } from "vitest";
import report from "./__fixtures__/prismReport.json";
import variants from "./__fixtures__/prismVariants.json";
import { ApiError } from "./api";
import {
  backoff, buildFundamentalGrowth, cleanSymbol, factorDetail, factorValue, growthPercent, labelTone, partsOf, partsSentence, pdfName, pdfOpen,
  prismPdfUrl, prismProblem, prismReview, scoreTone, standing, transient, trendRows, type HistoryRow, type PrismReport,
} from "./prism";

const R = report as unknown as PrismReport;
const row = (category: string, points: [string, number | null][]): HistoryRow => ({ category, history: points.map(([period, value]) => ({ period, value })) });

/* ported from upstream lib/fundamentalGrowth.test.js */
describe("fundamental growth", () => {
  it("calculates annual revenue, net profit and EPS growth using exact previous years", () => {
    const result = buildFundamentalGrowth([row("revenue", [["2026", 120], ["2025", 100]]), row("net_profit", [["2026", 15], ["2025", 20]]), row("basicreinr", [["2026", 3], ["2025", 2]])]);
    expect(result[1]).toMatchObject({ revenue: 20, profit: -25, eps: 50 });
    expect(result[1].epsDetail).toMatchObject({ current: 3, previous: 2, comparison: "2025" });
  });
  it("quarterly YoY compares the same quarter last year and QoQ the preceding quarter", () => {
    const rows = [row("revenue", [["Jun 2026", 150], ["Mar 2026", 125], ["Jun 2025", 100]])];
    expect(buildFundamentalGrowth(rows, "quarterly", "yoy").at(-1)!.revenue).toBe(50);
    expect(buildFundamentalGrowth(rows, "quarterly", "qoq").at(-1)!.revenue).toBe(20);
  });
  it("preserves zero current values, gaps and non-meaningful negative or zero baselines", () => {
    const result = buildFundamentalGrowth([row("revenue", [["2026", 0], ["2025", 100], ["2023", 10]]), row("net_profit", [["2026", 5], ["2025", -10]]), row("eps", [["2026", 1], ["2025", 0]])]);
    expect(result.at(-1)).toMatchObject({ revenue: -100, profit: null, eps: null });
    expect(result.find((p) => p.period === "2024")!.revenue).toBeNull();
    expect(result.find((p) => p.period === "2025")!.revenue).toBeNull();
    expect(result.at(-1)!.profitDetail!.reason).toMatch(/negative/);
  });
  it("uses history beyond the six visible years for the first growth comparison", () => {
    const result = buildFundamentalGrowth([row("revenue", Array.from({ length: 7 }, (_, i) => [String(2020 + i), 100 + i * 10] as [string, number]))]);
    expect(result).toHaveLength(6);
    expect(result[0].revenue).toBe(10);
  });
  it("missing EPS does not become zero and TTM is excluded", () => {
    const result = buildFundamentalGrowth([row("revenue", [["2026", null], ["2025", 10], ["TTM", 20]])]);
    expect(result).toHaveLength(2);
    expect(result.at(-1)!.revenue).toBeNull();
    expect(result.at(-1)!.eps).toBeNull();
    expect(buildFundamentalGrowth([])).toEqual([]);
  });
  it("reads the report's own annual trends and words the figures", () => {
    const g = buildFundamentalGrowth(trendRows(R.trends));
    expect(g.at(-1)!.revenue).toBeCloseTo(((4295 - 3875) / 3875) * 100, 6);
    expect(growthPercent(g.at(-1)!.revenue)).toBe("+10.8%");
    expect(growthPercent(null)).toBe("N/M");
  });
});

/* ported from upstream lib/premiumReportReview.test.js */
describe("report review", () => {
  const m = (metric: string, points: number | null, status: string, value: number | null) => ({ part: "risk", metric, label: metric, points, status, value, unit: "%" });
  it("older reports keep zero values, separate missing factors and respect category boundaries", () => {
    const old = { rating: { status: "RATED", parts: { risk: 50 }, partWeights: { risk: 0.1 }, metrics: [m("PLEDGE", 100, "A", 0), m("missing", 50, "F", null), m("low", 39.9, "A", 10), m("mixed", 40, "A", 20), m("excluded", null, "N", null)] } } as unknown as PrismReport;
    const part = prismReview(old).parts[0];
    expect(part.pros.map((r) => r.metric)).toEqual(["PLEDGE"]);
    expect(part.pros[0].valueText).toBe("0 %");
    expect(part.cons.map((r) => r.metric)).toEqual(["low"]);
    expect(part.mixed.map((r) => r.metric)).toEqual(["mixed"]);
    expect(part.unavailable.map((r) => r.metric)).toEqual(["missing"]);
  });
  it("uses the report's commentary and withholds category scores when not rated", () => {
    const review = { parts: [], notes: [] };
    expect(prismReview({ review } as unknown as PrismReport)).toBe(review);
    expect(prismReview({ rating: { status: "NOT RATED", parts: { risk: 50 }, partWeights: { risk: 0.1 }, metrics: [] } } as unknown as PrismReport).parts[0].score).toBeNull();
  });
  it("shows the engine's reader view for a real report", () => {
    expect(prismReview(R).parts.map((p) => p.key)).toEqual(["fundamental", "valuation", "quality", "risk"]);
  });
});

describe("parts come from the data", () => {
  it("a technical part appears when the model sends one, and nothing is invented before", () => {
    expect(partsOf(R.rating)).toEqual(["fundamental", "valuation", "quality", "risk"]);
    const more = { ...R.rating, parts: { ...R.rating.parts, technical: 61 }, partWeights: { ...R.rating.partWeights, technical: 0.1 } };
    expect(partsOf(more)).toEqual(["fundamental", "valuation", "quality", "risk", "technical"]);
    expect(partsSentence(more)).toContain("Technical 61.0");
  });
  it("withholds category scores in words for NOT RATED", () => {
    const nr = (variants as unknown as { notRated: PrismReport }).notRated;
    expect(nr.rating.final).toBeNull();
    expect(partsSentence(nr.rating)).toMatch(/withheld/);
    expect(nr.review!.parts.every((p) => p.score === null)).toBe(true);
  });
});

/* intent of upstream lib/premiumReportPolling.test.js: temporary failures are retried with a backoff, permanent ones stop */
describe("retry rules", () => {
  it.each([undefined, 408, 429, 502, 503])("retries %s", (s) => expect(transient({ status: s })).toBe(true));
  it.each([401, 403, 404, 422])("stops on %s", (s) => expect(transient({ status: s })).toBe(false));
  it("backs off 2.5 s, 5 s, 10 s, then 15 s", () => expect([0, 1, 2, 3, 4].map((n) => backoff(n))).toEqual([2500, 5000, 10000, 15000, 15000]));
});

/* intent of upstream lib/currentPremiumReport.test.js: only the current calculation; an expired one is not offered as a PDF */
describe("the PDF window", () => {
  const now = Date.parse("2026-10-25T09:30:00Z");
  it("is open until pdfAvailableUntil, then closed", () => {
    expect(pdfOpen({ pdfAvailableUntil: "2026-10-25T09:42:41+00:00" }, now)).toBe(true);
    expect(pdfOpen({ pdfAvailableUntil: "2026-10-25T09:00:00+00:00" }, now)).toBe(false);
    expect(pdfOpen({ pdfAvailableUntil: null }, now)).toBe(false);
  });
  it("downloads exactly this calculation from the API", () => {
    expect(prismPdfUrl("abc123")).toBe("/api/prism/reports/abc123/pdf");
    expect(pdfName(R)).toBe("FinLit-Prism-EXAMPLE-consolidated-2026-10-25.pdf");
  });
});

describe("problems in words", () => {
  const err = (status: number, body = {}) => new ApiError(status, body);
  it("403 asks for Gold, 404 and 502/503 are plain, 410 offers a recalculation", () => {
    expect(prismProblem(err(403)).kind).toBe("locked");
    expect(prismProblem(err(404)).kind).toBe("missing");
    expect(prismProblem(err(410)).text).toMatch(/Recalculate/);
    expect(prismProblem(err(503)).kind).toBe("unavailable");
    expect(prismProblem(err(502)).title).toMatch(/not available/);
    expect(prismProblem(new TypeError("Failed to fetch")).kind).toBe("offline");
  });
  it("429 says when to try again", () => {
    const p = prismProblem(err(429, { retryAfter: 1800 }), Date.parse("2026-10-25T09:00:00Z"));
    expect(p.text).toContain("about 30 minutes");
    expect(p.text).toMatch(/3:00 pm IST/i);
    expect(p.retryAt?.toISOString()).toBe("2026-10-25T09:30:00.000Z");
    expect(prismProblem(err(429)).text).toMatch(/later/);
  });
});

describe("labels and values", () => {
  it("gives every label a word and a colour token", () => {
    expect(labelTone("STRONG")).toEqual({ word: "Strong", tone: "strong", token: "--pz-strong" });
    expect(labelTone("NOT RATED").word).toBe("Not rated");
    expect(["STRONG", "HEALTHY", "AVERAGE", "WEAK", "POOR"].map((l) => labelTone(l as never).tone)).toEqual(["strong", "healthy", "average", "weak", "poor"]);
  });
  it("bands scores like the engine", () => { expect([80, 65, 50, 35, 10, null].map(scoreTone)).toEqual(["strong", "healthy", "average", "weak", "poor", "none"]); });
  it("sorts factors like the reader view: >= 70 supports, < 40 weighs on", () => {
    expect([100, 70, 69.9, 40, 39.9].map((points) => standing({ points, status: "A" }))).toEqual(["pros", "pros", "mixed", "mixed", "cons"]);
    expect(standing({ points: 50, status: "F" })).toBe("unavailable");
    expect(standing({ points: 50, status: "L" })).toBe("unavailable");
    expect(standing({ points: null, status: "N" })).toBe("notApplicable");
    expect(standing({ points: 0, status: "Z" })).toBe("cons");
  });
  it("formats values with units and explains comparisons", () => {
    const find = (m: string) => R.rating.metrics.find((x) => x.metric === m)!;
    expect(factorValue(find("PROFIT_CAGR"))).toBe("18.19%");
    expect(factorValue(find("MARGIN_CHANGE"))).toBe("−0.52 pts");
    expect(factorValue(find("DEBT_TO_EQUITY"))).toBe("0.45×");
    expect(factorValue(find("SALES_STREAK"))).toBe("10 of 10 quarters");
    expect(factorDetail(find("SALES_CAGR"), "MFG")).toBe("5-year period: sales from ₹2,400 Cr to ₹4,295 Cr.");
    expect(factorDetail(find("PROFIT_GROWTH"), "MFG")).toContain("Trailing 4 quarters vs previous 4 quarters");
  });
  it("accepts only symbols the API accepts", () => {
    expect(cleanSymbol(" m&m ")).toBe("M&M");
    expect(cleanSymbol("bad symbol")).toBeNull();
    expect(cleanSymbol(undefined)).toBeNull();
  });
});

describe("a busy service is not a daily limit", () => {
  it("words 429 busy as busy and keeps the daily limit as a limit", () => {
    expect(prismProblem(new ApiError(429, { status: "busy", detail: "x", retryAfter: 30 })).title).toBe("FinLit Prism is busy");
    expect(prismProblem(new ApiError(429, { status: "limit", detail: "x", retryAfter: 600 })).kind).toBe("limit");
  });
});

describe("a calculation behind the page", () => {
  it("polls with a growing pause that never passes five seconds", async () => {
    const { pollDelay } = await import("./prism");
    expect([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 50].map(pollDelay)).toEqual([1000, 1000, 1500, 2000, 2000, 3000, 3000, 4000, 5000, 5000, 5000]);
    expect(pollDelay(-3)).toBe(1000);
  });
  it("the bar follows the usual time, slows afterwards and never reaches 100%", async () => {
    const { progressFraction } = await import("./prism");
    expect(progressFraction(0, 12)).toBe(0);
    expect(progressFraction(6, 12)).toBeCloseTo(0.425, 3);
    expect(progressFraction(12, 12)).toBeCloseTo(0.85, 3);
    const late = [13, 20, 60, 600].map((t) => progressFraction(t, 12));
    expect(late.every((v, i) => v > (i ? late[i - 1] : 0.85) - 1e-9 && v <= 0.95)).toBe(true);
    expect(progressFraction(10_000, 12)).toBeLessThanOrEqual(0.95);
    expect(progressFraction(-5, 12)).toBe(0);
    expect(progressFraction(5, 0)).toBeGreaterThan(0);       // a missing expectation falls back to a default
    expect(progressFraction(5, NaN)).toBeGreaterThan(0);
  });
  it("explains each way a background calculation can end, in words", async () => {
    const { jobProblem } = await import("./prism");
    expect(jobProblem({ status: 404 }).kind).toBe("missing");
    expect(jobProblem({ status: 422, detail: "This company cannot be rated as asked." }).text).toContain("cannot be rated");
    const limit = jobProblem({ status: 429, code: "limit", detail: "You have used today's 20 FinLit Prism calculations.", retry: 3600 });
    expect(limit.kind).toBe("limit");
    expect(limit.text).toContain("today's 20");
    expect(jobProblem({ status: 429, code: "busy", retry: 30 }).kind).toBe("unavailable");
    expect(jobProblem({ status: 403 }).kind).toBe("locked");
    const other = jobProblem({ status: 502, detail: "FinLit Prism could not finish this calculation just now. Please try again in a few minutes." });
    expect(other.kind).toBe("unavailable");
    expect(other.text).toContain("try again");
    expect(jobProblem({}).text).toBeTruthy();
  });
});

describe("income wording and the PDF download", () => {
  it("is Sales for every group, with a note only for lenders and insurers", async () => {
    const { incomeWord, incomeNote } = await import("./prism");
    for (const g of ["MFG", "BANK", "NBFC", "INSURANCE", "", "UNKNOWN"]) expect(incomeWord(g)).toBe("Sales");
    expect(incomeNote("MFG")).toBeNull();
    expect(incomeNote("BANK")).toMatch(/net interest income/);
    expect(incomeNote("INSURANCE")).toMatch(/net premium earned/);
    expect(factorDetail({ ...R.rating.metrics.find((m) => m.metric === "SALES_CAGR")! }, "BANK")).toMatch(/sales from/);
  });
  it("downloadPrismPdf cleans up the link and the object URL even when the click throws", async () => {
    const { downloadPrismPdf } = await import("./prism");
    const { vi } = await import("vitest");
    vi.useFakeTimers();
    const revoke = vi.fn(), removed = vi.fn();
    const link = { click: () => { throw new Error("blocked"); }, remove: removed } as unknown as HTMLAnchorElement;
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, blob: async () => new Blob(["x"]) })));
    vi.stubGlobal("URL", { createObjectURL: () => "blob:x", revokeObjectURL: revoke });
    vi.stubGlobal("document", { createElement: () => link, body: { appendChild: () => undefined } });
    await expect(downloadPrismPdf(R)).rejects.toThrow("blocked");
    expect(removed).toHaveBeenCalled();
    vi.advanceTimersByTime(31_000);
    expect(revoke).toHaveBeenCalledWith("blob:x");
    vi.useRealTimers(); vi.unstubAllGlobals();
  });
});

describe("not-rated reasons", () => {
  const base = { status: "NOT RATED" as const, confidence: 1 };
  it("shows the report's specific reason and explains the full inputs figure", async () => {
    const { notRatedReason, ringWhy, completenessNote } = await import("./prism");
    const r = { ...base, notRatedReasons: [{ code: "classification" as const, text: 'Prism has no model group for this industry yet ("X"). The inputs were available; the rating needs the industry rules extended.' }] };
    expect(notRatedReason(r)).toContain('no model group for this industry yet ("X")');
    expect(ringWhy(r)).toBe("industry not mapped");
    expect(completenessNote(r)).toContain("share of inputs found");
    expect(ringWhy(base)).toBe("not enough evidence");
    expect(notRatedReason({ status: "RATED", notRatedReasons: r.notRatedReasons })).toBeNull();
  });
  it("the card text is the stored reason, never a generic 'too little data', and the inputs line never contradicts a classification block", async () => {
    const { notRatedLede, inputsLine } = await import("./prism");
    const r = { ...base, notRatedReasons: [{ code: "classification" as const, text: "Prism has no model group for this industry yet (\"Coal\")." }] };
    expect(notRatedLede(r)).toContain("Coal");
    expect(notRatedLede(r).toLowerCase()).not.toContain("too little");
    const line = inputsLine(r);
    expect(line.text).toBe("100% of inputs available");
    expect(line.ok).toBe(false);
    expect(line.note).toContain("Inputs are not the cause");
    expect(notRatedLede(base)).toContain("recalculate");
    expect(notRatedLede(base).toLowerCase()).not.toContain("too little");
    const thin = { status: "NOT RATED" as const, confidence: 0.3, notRatedReasons: [{ code: "low_confidence" as const, text: "Only 30% of the inputs" }] };
    expect(inputsLine(thin)).toMatchObject({ ok: true, note: null });
  });
});
