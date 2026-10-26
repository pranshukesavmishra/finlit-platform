// Regression (docs/KNOWN-ISSUES.md f): when every period label fits, every label is shown (step 1), not every other one.
import { describe, expect, it } from "vitest";
import { labelEvery } from "./chartAxis";

describe("labelEvery keeps every label when they fit", () => {
  it("twelve quarters of 6 characters across 700 px", () => expect(labelEvery(12, 700, 6)).toBe(1));
  it("ten financial years of 4 characters across 560 px", () => expect(labelEvery(10, 560, 4)).toBe(1));
  it("never skips more than needed when they do not fit", () => {
    const n = labelEvery(40, 300, 8);
    expect(n).toBeGreaterThan(1);
    expect(Math.ceil(40 / n)).toBeLessThanOrEqual(Math.floor(300 / (8 * 6.2 + 10)));
  });
});
