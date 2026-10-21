import { describe, expect, it } from "vitest";
import { PL_INFO, PL_LABEL, plCell } from "./plDefinitions";

describe("P&L cells keep their sign", () => {
  it("shows a negative EPS with a true minus (the stock page used to drop it)", () => {
    expect(plCell("eps", -5.14)).toBe("−5.14");
    expect(plCell("eps", 3.52)).toBe("3.52");
    expect(plCell("eps", 0.52)).toBe("0.52");
  });
  it("shows crore losses with a true minus and no decimals", () => {
    expect(plCell("operating_profit", -39.12)).toBe("−39");
    expect(plCell("profit_before_tax", -36.84)).toBe("−37");
    expect(plCell("revenue", 247.82)).toBe("248");
  });
  it("shows a dash for a missing figure, not zero", () => {
    expect(plCell("eps", null)).toBe("—");
    expect(plCell("net_profit", undefined)).toBe("—");
  });
});

describe("P&L definitions", () => {
  it("explains every line the table shows", () => {
    for (const k of ["revenue", "other_income", "expenses", "operating_profit", "finance_costs", "depreciation", "profit_before_tax", "tax", "net_profit", "eps"]) {
      expect(PL_INFO[k]?.what).toBeTruthy();
    }
  });
  it("labels operating profit as EBITDA and expenses as total expenses", () => {
    expect(PL_LABEL.operating_profit).toContain("EBITDA");
    expect(PL_LABEL.expenses).toBe("Total expenses");
  });
});
