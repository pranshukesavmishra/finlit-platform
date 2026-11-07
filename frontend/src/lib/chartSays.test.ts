import { describe, expect, it } from "vitest";
import { CHART_SAYS_HEADING, chartSaysSubtitle, dupontSays, topicOfChart } from "./chartSays";

describe("What does the chart say? (task #23)", () => {
  it("the heading is one fixed sentence and the subtitle names the analysis", () => {
    expect(CHART_SAYS_HEADING).toBe("What does the chart say?");
    expect(chartSaysSubtitle("dupont")).toBe("Get the key takeaways from this Extended DuPont analysis.");
    expect(chartSaysSubtitle("correlation")).toContain("correlation analysis");
    expect(chartSaysSubtitle("trend")).toContain("financial trend");
    const all = ["dupont", "correlation", "relationship", "trend", "comparison", "breakdown", "price", "matrix", "general"] as const;
    expect(new Set(all.map(chartSaysSubtitle)).size).toBe(all.length);                     // each kind of chart has its own sentence
  });
  it("the Chart builder maps each chart type to a topic", () => {
    expect(topicOfChart("scatter")).toBe("relationship"); expect(topicOfChart("heatmap", { matrix: true })).toBe("matrix"); expect(topicOfChart("heatmap")).toBe("correlation");
    expect(topicOfChart("line")).toBe("trend"); expect(topicOfChart("pie")).toBe("breakdown"); expect(topicOfChart("candlestick")).toBe("price"); expect(topicOfChart("bar")).toBe("comparison"); expect(topicOfChart("zzz")).toBe("general");
  });
  it("the DuPont reading is worked out from the bridge", () => {
    const t = dupontSays({ from: "Mar 2019", to: "Mar 2026", start: 10.2, end: 8.9, steps: [{ label: "Tax burden", pp: -0.9 }, { label: "Interest burden", pp: 0.6 }, { label: "EBIT margin", pp: 1.2 }, { label: "Asset turnover", pp: -1.5 }, { label: "Equity multiplier", pp: -0.7 }] });
    expect(t[0]).toBe("Return on equity fell from 10.2% in Mar 2019 to 8.9% in Mar 2026 (−1.3 pp).");
    expect(t[1]).toBe("EBIT margin added the most (+1.2 pp)."); expect(t[2]).toBe("Asset turnover took away the most (−1.5 pp).");
    expect(t.join(" ")).not.toMatch(/\b(buy|sell|hold|should|best)\b/i);
  });
});
