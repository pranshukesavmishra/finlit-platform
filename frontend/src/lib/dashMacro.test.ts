import { describe, expect, it } from "vitest";
import { rateTiles } from "./dashMacro";
import type { Macro } from "./macro";

const macro = (o: Partial<Macro> = {}) => ({ series: { cpi: { points: [["2026-08-31", 5.1], ["2026-09-30", 5.54]] }, wpi: { points: [["2026-09-30", 11.39]] }, repo: { points: [["2026-10-31", 5.5]] } },
  rates: { rates: { repo: 5.5 }, fx: { usdinr: 94.88 }, fxAsOf: "2026-11-02", seenOn: "2026-11-04" }, decisions: [{ date: "2026-06-06", rate: 5.25, bp: -25, url: "" }, { date: "2026-10-07", rate: 5.5, bp: 25, url: "" }],
  brent: { status: "ok", value: 105.55, date: "2026-11-02", avg4q: 85.9, vsAvgPct: 22.9 }, ...o } as unknown as Macro);

describe("prices and rates tiles", () => {
  it("builds the six tiles from the macro payload", () => {
    const t = Object.fromEntries(rateTiles(macro()).map((x) => [x.key, x]));
    expect(t.brent).toMatchObject({ value: "US$105.55", note: "+22.9% vs 4-quarter average", tone: "up" });
    expect(t.usdinr).toMatchObject({ value: "94.88", note: "FBIL, 2 Nov" });
    expect(t.repo).toMatchObject({ value: "5.50%", note: "+25 bp on 7 Oct" });
    expect(t.cpi).toMatchObject({ value: "5.54%", note: "September" });
    expect(t.wpi).toMatchObject({ value: "11.39%", note: "September" });
    expect(Object.keys(t)).toHaveLength(6);
  });
  it("shows the reason, not a number, for Brent without a key, and for the G-sec yield", () => {
    const t = Object.fromEntries(rateTiles(macro({ brent: { status: "nokey", reason: "Brent: source key not set" } })).map((x) => [x.key, x]));
    expect(t.brent).toMatchObject({ value: null, note: "Brent: source key not set" });
    expect(t.gsec.value).toBeNull(); expect(t.gsec.note).toMatch(/No free public yield feed/);
  });
  it("shows a price without a made-up comparison when the average is missing", () => {
    const t = rateTiles(macro({ brent: { status: "ok", value: 90, vsAvgPct: null, reason: "Brent: only 40 days held for the 4-quarter average" } })).find((x) => x.key === "brent")!;
    expect(t.value).toBe("US$90.00"); expect(t.note).toMatch(/only 40 days/); expect(t.tone).toBeUndefined();
  });
  it("copes with no payload at all", () => { expect(rateTiles(undefined).every((x) => x.value === null && x.note)).toBe(true); });
});
