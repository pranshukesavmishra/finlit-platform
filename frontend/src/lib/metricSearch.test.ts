import { describe, expect, it } from "vitest";
import { distance, rankMetrics, score } from "./metricSearch";

const items = [{ key: "pe", label: "P/E Ratio" }, { key: "ev_cfo", label: "EV / CFO" }, { key: "ev_sales", label: "EV / Sales" }, { key: "roce", label: "Return on capital employed" },
  { key: "op_profit", label: "Operating profit, annual (latest year)" }, { key: "q_operating_profit", label: "Operating profit, quarterly (latest quarter)" }, { key: "peg", label: "PEG Ratio" }];
const top = (q: string) => rankMetrics(items, q)[0]?.key;
describe("metric search", () => {
  it("finds EV/CFO however it is typed", () => { for (const q of ["EV / CFO", "ev/cfo", "EV-CFO", "ev cfo", "evcfo", "CFO EV"]) expect(top(q)).toBe("ev_cfo"); });
  it("aliases", () => { expect(top("pe")).toBe("pe"); expect(top("roce")).toBe("roce"); });
  it("typos", () => { expect(top("oparating profit")).toBe("op_profit"); expect(top("ev cgo")).toBe("ev_cfo"); expect(distance("ab", "ba")).toBe(1); });
  it("prefix and both operating profits", () => { expect(rankMetrics(items, "operating").map((m) => m.key)).toEqual(["op_profit", "q_operating_profit"]); });
  it("no match for nonsense", () => { expect(score("zzzzzz", "P/E Ratio")).toBe(0); expect(rankMetrics(items, "qqqq")).toEqual([]); });
});
