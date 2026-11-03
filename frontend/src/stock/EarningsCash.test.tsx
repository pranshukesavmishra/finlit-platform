import { describe, expect, it } from "vitest";
import { flagsOf } from "./EarningsCash";

const pr = (o: Record<string, unknown> = {}) => ({ years: [{ period: "2026-03-31", receivablesFlag: true, receivablesGrowth: 38.9, revenueGrowth: 10.2, otherIncomeShare: 44 }], ...o }) as never;
const m = (L: Record<string, unknown>, warnings: unknown[] = []) => ({ state: "ok", latest: L, warnings }) as never;

describe("Earnings & cash: the red flag is written once", () => {
  it("the receivables warning gives both the year-end and the average-balance growth in one sentence", () => {
    const { flag } = flagsOf(pr(), m({ receivablesGrowth: 36.4 }, [{ id: "receivables", text: "x", why: "y" }]), null);
    expect(flag?.title).toBe("Customers are paying more slowly");
    expect(flag?.text).toContain("38.9% on year-end balances and 36.4% on average balances");
    expect(flag?.text).toContain("against revenue growth of 10.2%");
  });
  it("other warnings stay as watch items, the receivables one never appears twice, and other income becomes the item to investigate", () => {
    const { watch, investigate } = flagsOf(pr(), m({ receivablesGrowth: 36.4 }, [{ id: "receivables", text: "a", why: "b" }, { id: "inventory", text: "c", why: "d" }]), { questions: ["Are receivables rising?", "Is inventory piling up?"] } as never);
    expect(watch.map((w) => w.id)).toEqual(["inventory"]);
    expect(investigate[0]).toContain("Other income is 44% of pre-tax profit");
    expect(investigate).toHaveLength(2); expect(investigate.join(" ")).not.toMatch(/receivables rising/);
  });
  it("no receivables problem, no red flag", () => {
    expect(flagsOf(pr({ years: [{ period: "2026-03-31", receivablesFlag: false, receivablesGrowth: 3 }] }), m({ receivablesGrowth: 3 }), null).flag).toBeNull();
  });
});
