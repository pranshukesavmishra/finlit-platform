// Task #29: the "What does the chart say?" box brings its own styles, so it looks the same on every page (the graph builder, the company page, the advanced charts).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

describe("ChartSays styles", () => {
  it("are imported by the component itself, not borrowed from another page's stylesheet", () => {
    expect(readFileSync(join(__dirname, "ChartSays.tsx"), "utf8")).toContain('import "../styles/chartsays.css"');
    expect(readFileSync(join(__dirname, "../styles/advcharts.css"), "utf8")).not.toContain(".csay");
    const css = readFileSync(join(__dirname, "../styles/chartsays.css"), "utf8");
    expect(css).toContain(".csay > summary::-webkit-details-marker");          // one arrow only: the native triangle is hidden
    expect(css).toContain(".csay-t { flex: 1");                                  // the heading and its subtitle are one block, the subtitle under the heading
  });
});
