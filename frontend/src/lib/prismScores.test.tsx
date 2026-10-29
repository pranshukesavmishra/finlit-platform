import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { missingChunks, techColor, techFill, techText, type PrismScore } from "./prismScores";
import { scoreBand100, scoreBandColor } from "./scoreBandColor";
import { PrismChips, PrismPreviewScores, stateOf } from "../components/search/prismParts";

const S: PrismScore = {
  rated: true, final: 54.5, label: "AVERAGE", status: "RATED", parts: { fundamental: 68.8, valuation: 16.5, quality: 73.3, risk: 73.7 },
  shortTerm: { score: 34.2, word: "Positive" }, longTerm: { score: -22.4, word: "Negative" },
};

describe("score bands", () => {
  it("green from 70, orange 50-69, red below 50", () => {
    expect([100, 70, 69.9, 50, 49.9, 0].map(scoreBand100)).toEqual(["green", "green", "orange", "orange", "red", "red"]);
    expect(scoreBand100(null)).toBeNull();
    expect(scoreBandColor(null)).toBe("var(--faint)");
  });
  it("technical scores keep their sign and trend band", () => {
    expect(techText(34.2)).toBe("+34"); expect(techText(-22.4)).toMatch(/^[−-]22$/); expect(techText(null)).toBe("—");
    expect(techFill(-100)).toBe(0); expect(techFill(0)).toBe(50); expect(techFill(100)).toBe(100);
    expect(techColor(34)).toBe("var(--gain)"); expect(techColor(0)).toBe("var(--warn)"); expect(techColor(-30)).toBe("var(--loss)");
  });
});

describe("batching", () => {
  it("asks only for unknown symbols, once each, at most 40 per request", () => {
    const syms = Array.from({ length: 85 }, (_, i) => "S" + i);
    const chunks = missingChunks([...syms, "S1"], { S0: null });
    expect(chunks.map((c) => c.length)).toEqual([40, 40, 4]);
    expect(chunks.flat()).not.toContain("S0");
    expect(missingChunks(["A"], { A: "error" })).toEqual([]);
  });
});

describe("palette Prism scores", () => {
  const html = (el: React.ReactElement) => renderToStaticMarkup(el);
  it("a row shows three scores", () => {
    const h = html(<PrismChips state={stateOf({ TCS: S }, "TCS")} />);
    expect(h).toContain(">55<"); expect(h).toContain(">+34<"); expect(h).toMatch(/>[−-]22</);
    expect(h).toContain("short-term technical +34"); expect(h).toContain("from −100 to +100");
  });
  it("no stored rating reads Not rated yet with the reason", () => {
    const h = html(<PrismChips state={stateOf({ X: null }, "X")} />);
    expect(h).toContain("Not rated yet"); expect(h).toMatch(/has not been calculated/);
  });
  it("the preview shows six labelled scores", () => {
    const h = html(<PrismPreviewScores state={stateOf({ TCS: S }, "TCS")} />);
    for (const l of ["Fundamentals", "Valuation", "Quality", "Risk", "Short-term technical", "Long-term technical"]) expect(h).toContain(l);
    expect(h).toContain("Positive"); expect(h).toContain("Negative");
    for (const bad of [/\bbuy\b/i, /\bsell\b/i, /\bhold\b/i, /\breduce\b/i, /target/i]) expect(h).not.toMatch(bad);
  });
});
