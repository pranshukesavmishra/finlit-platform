import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { NAV } from "../lib/sectionNav";

describe("Earnings call section removed from every company page (task #16)", () => {
  it("the stock page no longer renders it and the section bar no longer lists it", () => {
    expect(readFileSync(join(__dirname, "StockPage.tsx"), "utf8")).not.toContain("EarningsCallSection");
    expect(NAV.some(([id]) => id === "earnings-call")).toBe(false);
  });
});
