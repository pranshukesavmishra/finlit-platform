import { describe, expect, it } from "vitest";
import * as XLSX from "xlsx";
import { fieldOf, locateColumns, rowsFromGrid, statementFromFile, statementFromGrids, StatementError, MAX_ROWS } from "./mfStatement";

const f = (parts: BlobPart[], name: string) => new File(parts, name);
const book = (rows: unknown[][], bookType: "xlsx" | "xls", name: string, sheet = "Holdings") => {
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(rows), sheet);
  return f([XLSX.write(wb, { type: "array", bookType }) as ArrayBuffer], name);
};

describe("header synonyms", () => {
  it.each([
    ["Scheme Name", "name"], ["Fund Name", "name"], ["Scheme", "name"], ["Name of the Scheme", "name"], ["Scheme Name / Fund", "name"], ["Mutual Fund", "name"], ["Security Name", "name"],
    ["ISIN", "isin"], ["ISIN No.", "isin"], ["ISIN Code", "isin"], ["AMFI Code", "amfi"], ["Scheme Code", "amfi"], ["AMFI", "amfi"],
    ["Folio No", "folio"], ["Folio Number", "folio"], ["Folio", "folio"],
    ["Units", "units"], ["Unit Balance", "units"], ["Closing Unit Balance", "units"], ["Units Held", "units"], ["Balance Units", "units"], ["Qty", "units"], ["Quantity", "units"],
    ["Avg. Cost", "avgCost"], ["Average NAV", "avgCost"], ["Avg Buy Price", "avgCost"], ["Purchase NAV", "avgCost"], ["Cost per Unit", "avgCost"], ["Average Cost Price (₹)", "avgCost"],
    ["Invested Amount", "invested"], ["Invested Value (₹)", "invested"], ["Cost Value", "invested"], ["Total Cost", "invested"], ["Purchase Value", "invested"], ["Amount Invested", "invested"], ["Cost", "invested"],
    ["Current Value", "current"], ["Market Value", "current"], ["Valuation", "current"], ["Value as on 30-Oct-2026", "current"], ["Current Value (₹)", "current"],
    ["NAV", "nav"], ["Current NAV", "nav"], ["Latest NAV", "nav"], ["Closing NAV", "nav"],
    ["Date", "date"], ["Purchase Date", "date"], ["Transaction Date", "date"], ["Date of Purchase", "date"], ["Buy Date", "date"],
    ["Asset Type", "kind"], ["Instrument Type", "kind"], ["Asset Class", "kind"],
  ])("%s -> %s", (h, want) => expect(fieldOf(h)).toBe(want));

  it.each(["NAV Date", "Valuation Date", "Unrealised Gain", "Absolute Return %", "XIRR", "Day Change", "Weight %", "Fund House", "AMC", "Category", "Sr. No.", "", "Remarks"])("%j is not an input column", (h) => expect(fieldOf(h)).toBeNull());
});

const CAMS = [
  ["Consolidated Account Statement (Holdings)", "", "", "", "", "", "", ""],
  ["Investor: TEST USER", "", "", "", "", "", "", ""],
  ["As on 30-Oct-2026", "", "", "", "", "", "", ""],
  [],
  ["Folio No", "Scheme Name", "ISIN", "Closing Unit Balance", "NAV", "Cost Value", "Market Value", "Unrealised Gain"],
  ["Axis Mutual Fund", "", "", "", "", "", "", ""],
  ["1234567890 / 12", "Axis Bluechip Fund - Direct Plan - Growth", "INF846K01DP8", "2,345.678", "63.51", "1,25,000.00", "1,48,977.00", "23,977.00"],
  ["1234567890 / 13", "Axis Midcap Fund - Regular Growth", "INF846K01131", "100.000", "88.20", "7,000.00", "8,820.00", "1,820.00"],
  ["Total", "", "", "", "", "1,32,000.00", "1,57,797.00", ""],
];

describe("statement layouts", () => {
  it("finds the header below a title block and skips section lines and totals (CAMS style)", () => {
    const loc = locateColumns(CAMS)!;
    expect(loc.headerRow).toBe(4);
    expect(loc.map).toMatchObject({ folio: 0, name: 1, isin: 2, units: 3, nav: 4, invested: 5, current: 6 });
    const { rows, skippedBlank, skippedTotal } = rowsFromGrid(CAMS, loc);
    expect(rows).toEqual([
      { row: 7, folio: "1234567890 / 12", name: "Axis Bluechip Fund - Direct Plan - Growth", isin: "INF846K01DP8", units: "2,345.678", nav: "63.51", invested: "1,25,000.00", current: "1,48,977.00" },
      { row: 8, folio: "1234567890 / 13", name: "Axis Midcap Fund - Regular Growth", isin: "INF846K01131", units: "100.000", nav: "88.20", invested: "7,000.00", current: "8,820.00" },
    ]);
    expect(skippedBlank).toBe(1);                         // the "Axis Mutual Fund" section line
    expect(skippedTotal).toBe(1);
  });

  it("messy headers: extra spaces, symbols, odd order, a repeated header, a stock row left for the server to ignore", () => {
    const grid = [
      ["Sr.", "  Name of the  Scheme ", "Asset Type", "Units  Held", "Avg. Cost (₹)", "Purchase Date", "AMFI Code", "Notes"],
      ["1", "Parag Parikh Flexi Cap Fund - Direct Plan", "Mutual Fund", "50.123", "55.5", "15-03-2022", "122639", ""],
      ["Sr.", "Name of the Scheme", "Asset Type", "Units Held", "Avg. Cost (₹)", "Purchase Date", "AMFI Code", "Notes"],
      ["2", "Reliance Industries Ltd", "Equity Shares", "10", "2400", "", "", ""],
    ];
    const loc = locateColumns(grid)!;
    expect(loc.headers).toMatchObject({ name: "Name of the Scheme", units: "Units Held", avgCost: "Avg. Cost (₹)", date: "Purchase Date", amfi: "AMFI Code", kind: "Asset Type" });
    const { rows, skippedBlank } = rowsFromGrid(grid, loc);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ name: "Parag Parikh Flexi Cap Fund - Direct Plan", units: "50.123", avgCost: "55.5", date: "15-03-2022", amfi: "122639", kind: "Mutual Fund", row: 2 });
    expect(rows[1]).toMatchObject({ name: "Reliance Industries Ltd", kind: "Equity Shares" });
    expect(skippedBlank).toBe(1);                         // the repeated header line
  });

  it("a groww / broker style export with the amount and current value only", () => {
    const grid = [["Scheme Name", "Units", "Invested Value", "Current Value", "XIRR", "Returns"], ["HDFC Flexi Cap Fund - Growth", "200.5", "150000", "210000", "18%", "40%"]];
    const { rows } = rowsFromGrid(grid, locateColumns(grid)!);
    expect(rows).toEqual([{ row: 2, name: "HDFC Flexi Cap Fund - Growth", units: "200.5", invested: "150000", current: "210000" }]);
  });

  it("needs units and a way to name the fund", () => {
    expect(locateColumns([["Scheme Name", "Folio"], ["x", "1"]])).toBeNull();
    expect(locateColumns([["Units", "Cost"], ["1", "2"]])).toBeNull();
    expect(locateColumns([["ISIN", "Units"], ["INF846K01DP8", "2"]])).not.toBeNull();
  });

  it("the sheet with the most fund rows wins; a file with no header says what it found", () => {
    const empty = [["Summary", "", ""], ["Total value", "1", "2"]];
    const st = statementFromGrids([empty, CAMS]);
    expect(st.rows).toHaveLength(2);
    expect(st.headers.name).toBe("Scheme Name");
    expect(() => statementFromGrids([[["a", "b", "c"], ["1", "2", "3"]]])).toThrow(StatementError);
    try { statementFromGrids([[["Alpha", "Beta", "Gamma"], ["1", "2", "3"]]]); } catch (e) { expect((e as Error).message).toContain("Alpha | Beta | Gamma"); }
    expect(() => statementFromGrids([[["Scheme Name", "Units"]]])).toThrow(/no fund rows/);
  });

  it("refuses more rows than one import takes", () => {
    const grid = [["Scheme Name", "Units"], ...Array.from({ length: MAX_ROWS + 1 }, (_, i) => [`Fund ${i}`, "1"])];
    expect(() => statementFromGrids([grid])).toThrow(/up to 2,000/);
    expect(statementFromGrids([grid.slice(0, MAX_ROWS + 1)]).rows).toHaveLength(MAX_ROWS);
  });
});

describe("real files", () => {
  const cams = CAMS;
  it("reads an .xlsx and a legacy .xls with the same result", async () => {
    for (const t of ["xlsx", "xls"] as const) {
      const st = await statementFromFile(book(cams, t, `holdings.${t}`));
      expect(st.rows.map((r) => r.isin)).toEqual(["INF846K01DP8", "INF846K01131"]);
      expect(st.rows[0].units).toBe("2,345.678");
    }
  });
  it("reads a CSV (quoted cells with commas) and a semicolon CSV", async () => {
    const csv = ["Folio No,Scheme Name,Units,Invested Amount", '"123/4","Axis Bluechip Fund, Direct Plan - Growth","1,000.50","1,20,000.00"', '"123/5","HDFC Top 100 Fund - Growth",20,"5,000"'].join("\r\n");
    const st = await statementFromFile(f([csv], "cas.csv"));
    expect(st.rows).toHaveLength(2);
    expect(st.rows[0]).toMatchObject({ folio: "123/4", name: "Axis Bluechip Fund, Direct Plan - Growth", units: "1,000.50", invested: "1,20,000.00" });
    const semi = await statementFromFile(f(["Scheme Name;Units;Cost Value\nX Fund;10;1000\n"], "x.csv"));
    expect(semi.rows[0]).toMatchObject({ name: "X Fund", units: "10", invested: "1000" });
  });
  it("a BOM and a title above a CSV do not matter", async () => {
    const st = await statementFromFile(f(["﻿Holdings as on 30-10-2026\n\nScheme Name,Units\nX Fund,5\n"], "x.csv"));
    expect(st.rows).toEqual([{ row: 3, name: "X Fund", units: "5" }]);
  });
  it("a file that is not a spreadsheet is refused with words", async () => {
    await expect(statementFromFile(f([new Uint8Array([0x50, 0x4b, 3, 4, 0, 0, 0, 0])], "broken.xlsx"))).rejects.toThrow(/could not be read/);
    const big = new File([new Uint8Array(5_000_001)], "big.csv");
    await expect(statementFromFile(big)).rejects.toThrow(/larger than 5 MB/);
  });
});
