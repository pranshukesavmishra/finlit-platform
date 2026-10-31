import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FundamentalSection, TechnicalSection, CardSkeleton } from "./PrismCardView";
import { partsOf } from "./PrismCompare";
import type { PrismLatest } from "./PrismCard";
import { parseTechnical } from "../lib/prismTechnical";
import tech from "../lib/__fixtures__/prismTechnical.json";

const rating = (o: Partial<PrismLatest["rating"]> = {}): PrismLatest["rating"] => ({ final: 59.1, label: "AVERAGE", status: "RATED", parts: { fundamental: 55, valuation: 42, quality: 79, risk: 88 }, confidence: 1, ...o });
const rep = (r: PrismLatest["rating"], t?: unknown): PrismLatest => ({ id: "x", createdAt: "", completedAt: "", statementType: "consolidated", company: { symbol: "X", name: "X" }, rating: r, technicalAssessment: t });
const text = (h: string) => h.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/\s+/g, " ");
const fund = (r = rating()) => renderToStaticMarkup(<FundamentalSection r={r} parts={partsOf(r).parts} />);
const BANNED = /\b(buy|buying|sell|selling|hold|accumulate|target|entry|stop[- ]loss|avoid)\b/i;

describe("Fundamental section", () => {
  it("draws one arc and one card per component, tinted by band, with weights and words", () => {
    const h = fund(), t = text(h);
    expect(h.match(/class="pcx-arc/g)).toHaveLength(4);
    expect(h.match(/class="pcx-card band-/g)).toHaveLength(4);
    for (const b of ["band-mid", "band-lo", "band-hi"]) expect(h).toContain(b);
    for (const w of ["AVERAGE", "Weak", "Healthy", "Strong", "59.1", "/ 100"]) expect(t.toLowerCase()).toContain(w.toLowerCase());
    expect(h).toContain('aria-label="Valuation 42 of 100: Weak. Counts for 30% of the overall score. Higher is better: a higher score is a stronger result."');
    expect(h).toContain("a higher Risk score means lower risk");
    expect(t).toContain("Fundamental analysis");
  });
  it("is calm when not rated: grey ring, No data cards, no score", () => {
    const r = rating({ status: "NOT RATED", label: "NOT RATED", final: null });
    const h = fund(r);
    expect(h).toContain("Not rated"); expect(h.match(/band-na/g)!.length).toBeGreaterThanOrEqual(4); expect(text(h)).toContain("No data");
    expect(h).not.toContain("pcx-fill"); expect(h).not.toMatch(/\d+ of 100/);
  });
  it("shows the example marker in the locked preview", () => {
    expect(renderToStaticMarkup(<FundamentalSection r={rating()} parts={partsOf(rating()).parts} example />)).toContain("EXAMPLE");
  });
  it("counts a technical part as part of the score when the model sends one", () => {
    const r = rating({ parts: { fundamental: 55, valuation: 42, quality: 79, risk: 88, technical: 44 }, partWeights: { fundamental: 0.3, valuation: 0.25, quality: 0.2, risk: 0.1, technical: 0.15 } });
    const t = text(fund(r));
    expect(t).toContain("Prism score"); expect(t).toContain("5 weighted components"); expect(t).not.toContain("not included in this score");
  });
});

describe("Technical section", () => {
  const draw = (t: unknown, r = rating()) => renderToStaticMarkup(<TechnicalSection a={parseTechnical(t)} report={rep(r, t)} />);
  it("shows both horizons with our captions, scores, words, scale labels, signals and the alignment", () => {
    const h = draw((tech as Record<string, unknown>).mixed), t = text(h);
    for (const w of ["Technical short term", "5–20 sessions", "6–18 months", "−35", "+23", "Negative", "Positive", "Strongly negative", "Neutral", "Strongly positive", "14 of 14 signals available", "13 of 13 signals available", "Trend alignment", "Short-term pullback within a long-term uptrend", "The short-term trend is negative, while the long-term trend is positive."]) expect(t).toContain(w);
    expect(h).toContain("pcx-sc");
  });
  it("says Not available for a horizon without a score, and hides the alignment", () => {
    const t = text(draw((tech as Record<string, unknown>).incomplete));
    expect(t).toContain("Not available"); expect(t).not.toContain("Trend alignment"); expect(t).toContain("12 of 13 signals available");
  });
  it("keeps the quiet line for a report stored before the technical view", () => {
    expect(text(draw(undefined))).toContain("Technical view: recalculate to add");
  });
});

describe("band rule and reading direction", () => {
  it("explains the cut-offs and shows the Risk direction", () => {
    const h = renderToStaticMarkup(fund(rating())), t = text(h);
    expect(h).toContain("Strong 80 and above, Healthy 65 to 79"); expect(t).toContain("Higher = lower risk"); expect(t).toContain("Higher is better");
  });
});

describe("loading and wording", () => {
  it("has a skeleton in the same two-section shape", () => { const h = renderToStaticMarkup(<CardSkeleton />); expect(h.match(/pcx-skel-sec/g)).toHaveLength(2); expect(h.match(/s-card/g)).toHaveLength(4); });
  it("never uses advice words in any state", () => {
    for (const k of ["ready", "incomplete", "capped", "mixed"]) {
      const t = (tech as Record<string, unknown>)[k];
      expect(text(renderToStaticMarkup(<TechnicalSection a={parseTechnical(t)} report={rep(rating(), t)} />))).not.toMatch(BANNED);
    }
    for (const r of [rating(), rating({ status: "NOT RATED", label: "NOT RATED", final: null }), rating({ status: "PROVISIONAL", label: "HEALTHY", final: 66 })]) expect(text(fund(r))).not.toMatch(BANNED);
  });
});
