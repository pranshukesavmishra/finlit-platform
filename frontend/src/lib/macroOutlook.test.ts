import { describe, expect, it } from "vitest";
import { companyRows, indicatorsForReasons, reasonsOf, type CompanyMacro, type Driver, type Indicator, type SectorRow } from "./macroOutlook";

const drv = (code: string, sign: "+" | "-", contribution: number): Driver => ({ code, name: code, contribution, sign, value: 1, unit: "%", valueText: "1%" });
const row = (code: string, drivers: Driver[], score = 60): SectorRow => ({ sector: { code, name: code }, status: "ok", score, label: "Tailwind", tone: "up", coverage: 1, drivers, snapshotDate: "2026-11-05", reason: null });
const ind = (code: string, group = "inflation"): Indicator => ({ code, name: code, group } as Indicator);
const company = (over: Partial<CompanyMacro> = {}): CompanyMacro => ({ status: "ok", symbol: "X", company: "X", modelVersion: 1, score: 44, label: "Headwind", tone: "down", coverage: 1, snapshotDate: "2026-11-05", drivers: [drv("WPI", "-", -0.9), drv("COPPER", "-", -0.5)],
  mapping: { sector: "auto_anc", sectorName: "Auto ancillaries", effectiveFrom: "", source: "", rule: null, basis: "primary", note: "" }, ...over } as CompanyMacro);

describe("companyRows", () => {
  it("a single-sector company gets exactly one row, built from its own outlook", () => {
    const r = companyRows(company(), [row("psu_banks", []), row("auto_anc", [])]);
    expect(r.length).toBe(1);
    expect(r[0].sector.name).toBe("Auto ancillaries");
    expect(r[0].score).toBe(44);
    expect(r[0].drivers.map((d) => d.code)).toEqual(["WPI", "COPPER"]);
  });
  it("a revenue-weighted company gets one row for each of its segment sectors, best score first, and nothing else", () => {
    const c = company({ mapping: { ...company().mapping!, basis: "revenue_weighted" }, segments: [{ sector: "a", name: "A", weight: 0.5, score: 1, label: "", tone: "up" }, { sector: "c", name: "C", weight: 0.5, score: 1, label: "", tone: "up" }] });
    const r = companyRows(c, [row("a", [], 40), row("b", [], 90), row("c", [], 70)]);
    expect(r.map((x) => x.sector.code)).toEqual(["c", "a"]);
  });
  it("without a mapping, or before the sector table has loaded for a weighted company, there are no rows", () => {
    expect(companyRows(company({ mapping: undefined }), [])).toEqual([]);
    expect(companyRows(company({ mapping: { ...company().mapping!, basis: "revenue_weighted" }, segments: [{ sector: "a", name: "A", weight: 1, score: 1, label: "", tone: "up" }] }), undefined)).toEqual([]);
  });
});

describe("reasonsOf and indicatorsForReasons", () => {
  const all = [ind("CPI"), ind("WPI"), ind("REPO_RATE", "monetary"), ind("COPPER", "commodities"), ind("BRENT", "commodities")];
  it("only the indicators named as top reasons come through, in the order the reasons are shown", () => {
    const rows = companyRows(company(), undefined);
    const tiles = indicatorsForReasons(all, reasonsOf(rows, company()));
    expect(tiles.map((t) => t.indicator.code)).toEqual(["WPI", "COPPER"]);
    expect(tiles[0].reason.driver?.sign).toBe("-");
  });
  it("a reason repeated by two sectors gives one tile, and each tile says which sector when there are several", () => {
    const rows = [row("a", [drv("WPI", "-", -1), drv("CPI", "+", 1)]), row("b", [drv("WPI", "-", -2)])];
    const reasons = reasonsOf(rows, company());
    expect(reasons.map((r) => r.code)).toEqual(["WPI", "CPI"]);
    expect(reasons[0].sector).toBe("a");
  });
  it("a reason with no matching indicator is skipped rather than invented", () => {
    expect(indicatorsForReasons(all, [{ code: "NOT_THERE" }])).toEqual([]);
  });
  it("Insufficient Data: the missing readings named as the reason are the tiles", () => {
    const c = company({ status: "insufficient_data", drivers: [], criticalMissing: ["BRENT"], missing: ["BRENT", "CPI"] });
    const tiles = indicatorsForReasons(all, reasonsOf(companyRows(c, undefined), c));
    expect(tiles.map((t) => t.indicator.code)).toEqual(["BRENT", "CPI"]);
    expect(tiles.every((t) => !t.reason.driver)).toBe(true);
  });
  it("no drivers and nothing missing: no tiles at all", () => {
    const c = company({ drivers: [] });
    expect(indicatorsForReasons(all, reasonsOf(companyRows(c, undefined), c))).toEqual([]);
  });
});
