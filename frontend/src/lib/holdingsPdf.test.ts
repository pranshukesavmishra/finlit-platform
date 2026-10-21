import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import type { SearchRow } from "./api";
import { PdfNoTextError, PdfPasswordError, findHoldings, gridFromPdfItems, isSure, joinWrappedNames, readPdfHoldings, rowsFromPdfItems, setPdfLoader, type PdfFinds, type PdfItem } from "./holdingsPdf";
import { makeLookup } from "./holdingsMatch";

/** ~67 listed companies, with look-alikes on purpose (Tata Motors / Tata Motors Passenger Vehicles, HDFC Bank / HDFC AMC / HDFC Life, Bajaj Finance / Finserv / Auto, ...). */
const dir = new URL("./fixtures/pdf/", import.meta.url);
type Manifest = Record<string, { expected: string[]; check: string[]; missing: string[]; note: string; mode: string }>;
const MAN: Manifest = JSON.parse(readFileSync(new URL("manifest.json", dir), "utf8"));
const INDEX: SearchRow[] = Object.entries(JSON.parse(readFileSync(new URL("index.json", dir), "utf8")) as Record<string, { name: string; bse: string }>).map(([s, v]) => [s, v.name, v.bse, 1, s] as unknown as SearchRow);
const file = (name: string) => new File([readFileSync(new URL(name, dir))], name, { type: "application/pdf" });
const syms = (f: { found: { symbol: string }[] }) => f.found.map((x) => x.symbol).sort();
const sure = (f: PdfFinds) => f.found.filter(isSure).map((x) => x.symbol).sort();
const unsure = (f: PdfFinds) => f.found.filter((x) => !isSure(x)).map((x) => x.symbol).sort();

beforeAll(() => {
  const require = createRequire(import.meta.url);
  const worker = pathToFileURL(require.resolve("pdfjs-dist/legacy/build/pdf.worker.mjs")).href;
  setPdfLoader(async () => { const m = await import("pdfjs-dist/legacy/build/pdf.mjs"); m.GlobalWorkerOptions.workerSrc = worker; return m as unknown as typeof import("pdfjs-dist"); });
});

describe("rows and cells from text pieces", () => {
  const it_ = (str: string, x: number, y: number, w = str.length * 5): PdfItem => ({ str, x, y, w, h: 9 });
  it("keeps words of one cell together and splits columns on wide gaps, top to bottom", () => {
    const g = gridFromPdfItems([[it_("Tata", 40, 700), it_("Consultancy", 62, 700), it_("Services Ltd", 120, 700), it_("5", 300, 700), it_("17,751.25", 380, 700), it_("Instrument", 40, 720), it_("Qty", 300, 720)]]);
    expect(g).toEqual([["Instrument", "Qty"], ["Tata Consultancy Services Ltd", "5", "17,751.25"]]);
  });
  it("joins a wrapped company name only when the joined text is a listed company", () => {
    const { exact } = makeLookup(INDEX);
    const out = joinWrappedNames([["Tata Motors", "9", "21,150.00"], ["Passenger Vehicles Ltd"], ["Wipro Ltd", "60", "15,300.00"], ["Unrelated", "1", "2"], ["Words"]], (n) => !!exact(n));
    expect(out).toEqual([["Tata Motors Passenger Vehicles Ltd", "9", "21,150.00"], ["Wipro Ltd", "60", "15,300.00"], ["Unrelated", "1", "2"], ["Words"]]);
  });
});

describe("real PDFs, read by pdf.js", () => {
  it("a broker holdings report across two pages: every company, nothing else, repeated headings ignored", async () => {
    const f = await readPdfHoldings(file("zerodha_holdings.pdf"), INDEX);
    expect(f.mode).toBe("table");
    // TATAMOTORS is the retired ticker: an old holder now holds both parts (TMPV and TMCV)
    expect(syms(f)).toEqual(["ADANIPORTS", "ASIANPAINT", "BHARTIARTL", "COALINDIA", "HDFCBANK", "HINDUNILVR", "ICICIBANK", "INFY", "ITC", "LT", "MARUTI", "NTPC", "POWERGRID", "RELIANCE", "SBIN", "SUNPHARMA", "TCS", "TITAN", "TMCV", "TMPV", "WIPRO"]);
    expect(f.found.every((x) => x.how !== "scan")).toBe(true);
    expect(f.missing).toEqual([]);                                   // the footer's disclaimer and totals are not companies
  });
  it("a depository statement: ISIN and name in one cell, wrapped names, funds are not taken for shares", async () => {
    const f = await readPdfHoldings(file("depository_statement.pdf"), INDEX);
    expect(syms(f)).toEqual(["HDFCBANK", "HINDUNILVR", "INFY", "LT", "RELIANCE", "TCS"]);
    expect(f.found.some((x) => /fund/i.test(x.name))).toBe(false);
  });
  it("a password-protected statement asks for the password, rejects a wrong one, and opens with the right one", async () => {
    await expect(readPdfHoldings(file("protected_statement.pdf"), INDEX)).rejects.toBeInstanceOf(PdfPasswordError);
    await expect(readPdfHoldings(file("protected_statement.pdf"), INDEX, "wrong")).rejects.toMatchObject({ wrong: true });
    expect(syms(await readPdfHoldings(file("protected_statement.pdf"), INDEX, "ABCDE1234F"))).toEqual(["ITC", "RELIANCE", "TCS"]);
  });
  it("a scanned PDF (no text) says so instead of guessing", async () => {
    await expect(readPdfHoldings(file("scanned.pdf"), INDEX)).rejects.toBeInstanceOf(PdfNoTextError);
  });
  it("without a table, whole company names in rows that carry numbers are found and marked as found in text", async () => {
    const f = await readPdfHoldings(file("narrative.pdf"), INDEX);
    expect(f.mode).toBe("text");
    expect(syms(f)).toEqual(["RELIANCE", "TCS"]);
    expect(f.found.every((x) => x.how === "scan")).toBe(true);
  });
  it("company names that only appear in notices and disclaimers are not holdings", async () => {
    const f = await readPdfHoldings(file("boilerplate.pdf"), INDEX);
    expect(f.found).toEqual([]);
  });
  it("a file that is not a PDF is refused", async () => {
    await expect(readPdfHoldings(new File(["hello"], "x.pdf"), INDEX)).rejects.toThrow();
  });
});

/* ------------------------------------------------------------------ every generated statement: the exact set, nothing more, nothing less */

describe("generated broker and depository statements (fixtures/pdf/manifest.json)", () => {
  const names = Object.keys(MAN).sort();
  it("has a broad set of layouts", () => { expect(names.length).toBeGreaterThanOrEqual(35); });
  for (const name of names) {
    const m = MAN[name];
    it(`${name}: ${m.note}`, async () => {
      const f = await readPdfHoldings(file(name), INDEX, name.startsWith("protected") ? "ABCPM1234F" : undefined);
      expect(sure(f)).toEqual([...m.expected].sort());                       // every held company, ticked; no other company ticked
      for (const u of unsure(f)) expect(m.check, `${u} must not be offered`).toContain(u);   // anything else offered is "please check", and only the listed ones
      expect(f.mode).toBe(m.mode);
      for (const want of m.missing) expect(f.missing.some((x) => x.includes(want)), `"${want}" listed as not matched`).toBe(true);
    });
  }
});

describe("precision: look-alike companies are never confused", () => {
  it("HDFC Bank is not HDFC Asset Management or HDFC Life, and the other way round", async () => {
    const f1 = await readPdfHoldings(file("lookalikes_1.pdf"), INDEX);
    expect(sure(f1)).toContain("HDFCBANK"); expect(sure(f1)).not.toContain("HDFCAMC"); expect(sure(f1)).not.toContain("HDFCLIFE");
    const f2 = await readPdfHoldings(file("lookalikes_2.pdf"), INDEX);
    expect(sure(f2)).toContain("HDFCAMC"); expect(f2.found.map((x) => x.symbol)).not.toContain("HDFCBANK");
  });
  it("Bajaj Finance, Bajaj Finserv, Bajaj Auto; Adani Ports, Adani Power; Power Grid, Power Finance; SBI, SBI Life, SBI Cards; ITC, ITC Hotels; Axis Bank, Axis Capital", async () => {
    const one = sure(await readPdfHoldings(file("lookalikes_1.pdf"), INDEX)), two = sure(await readPdfHoldings(file("lookalikes_2.pdf"), INDEX));
    for (const s of ["BAJFINANCE", "BAJAJ-AUTO", "ADANIPORTS", "POWERGRID", "SBILIFE", "ITC", "AXISBANK"]) { expect(one).toContain(s); expect(two).not.toContain(s); }
    for (const s of ["BAJAJFINSV", "ADANIPOWER", "PFC", "SBICARD", "ITCHOTELS", "AXISCAP"]) { expect(two).toContain(s); expect(one).not.toContain(s); }
    expect(one).not.toContain("SBIN");                                      // "SBI Life Insurance Company Ltd" is not State Bank of India
  });
  it("names cut short are offered for checking but never ticked ('HDFC' is never HDFC Bank)", async () => {
    const f = await readPdfHoldings(file("lookalikes_abbrev.pdf"), INDEX);
    expect(sure(f)).toEqual(["HDFCAMC", "BAJAJFINSV", "ITCHOTELS"].sort());
    for (const x of f.found.filter((y) => ["HDFCBANK", "SBIN", "AXISBANK"].includes(y.symbol))) expect(isSure(x)).toBe(false);
  });
  it("Tata Motors: the retired ticker is both parts; the plain name is ambiguous and is not ticked; the full new name is exact", async () => {
    const z = await readPdfHoldings(file("zerodha_console.pdf"), INDEX);
    expect(sure(z)).toEqual(expect.arrayContaining(["TMPV", "TMCV"]));
    const l = await readPdfHoldings(file("lookalikes_2.pdf"), INDEX);
    expect(unsure(l)).toEqual(["TMCV", "TMPV"]);
    expect(sure(await readPdfHoldings(file("lookalikes_1.pdf"), INDEX))).toContain("TMPV");
    expect(sure(await readPdfHoldings(file("lookalikes_1.pdf"), INDEX))).not.toContain("TMCV");
  });
  it("a listed name at the start of an unlisted one (Tata Motors Finance, ITC Infotech, Tata Steel Long Products, an HDFC Bank fund) is not taken, wrapped or not", async () => {
    for (const name of ["wrap_hazard_top.pdf", "wrap_hazard_middle.pdf"]) {
      const f = await readPdfHoldings(file(name), INDEX);
      expect(sure(f)).not.toContain("TMCV"); expect(sure(f)).not.toContain("TATASTEEL");
      expect(f.found.filter((x) => x.symbol === "ITC").every((x) => isSure(x))).toBe(true);        // the real "ITC Ltd" row is still ticked
    }
  });
});

describe("tables: which table is the holdings", () => {
  it("rule: with several tables only the one headed Holdings / Portfolio is read; a table headed or labelled sold / trades / realised is ignored", async () => {
    const a = await readPdfHoldings(file("two_tables_holdings_first.pdf"), INDEX), b = await readPdfHoldings(file("two_tables_sold_first.pdf"), INDEX);
    expect(sure(a)).toEqual(sure(b));
    expect(a.found.map((x) => x.symbol).sort()).toEqual(["HDFCBANK", "INFY", "ITC", "LT", "RELIANCE", "TCS", "TITAN"]);   // WIPRO, NTPC, COALINDIA, SUNPHARMA, AXISBANK were sold: not offered at all
    expect(a.notes.join(" ")).toMatch(/more than one table/);
  });
  it("a table without a clue is not guessed: two unlabelled tables are all shown, none ticked, with a note", async () => {
    const f = await readPdfHoldings(file("two_tables_unlabelled.pdf"), INDEX);
    expect(sure(f)).toEqual([]); expect(unsure(f)).toHaveLength(12); expect(f.notes.join(" ")).toMatch(/cannot be told which one/);
  });
  it("a company sold in part and still held is one holding; the same company on NSE and BSE, as ticker, name and code, is one", async () => {
    expect(sure(await readPdfHoldings(file("two_tables_overlap.pdf"), INDEX))).toEqual(["HDFCBANK", "INFY", "ITC", "LT", "RELIANCE", "TCS", "TITAN"]);
    const d = await readPdfHoldings(file("duplicates.pdf"), INDEX);
    expect(d.found.map((x) => x.symbol).sort()).toEqual(["INFY", "ITC", "RELIANCE", "TCS"]);
  });
  it("funds, ETFs, bonds and government securities in a depository statement are not shares; a bond's issuer is not a holding", async () => {
    const f = await readPdfHoldings(file("nsdl_cas.pdf"), INDEX);
    expect(sure(f).filter((s) => s === "LT")).toHaveLength(1);              // LT comes from the equity line only (its NCD line is in the Bonds section)
    expect(f.missing.join("|")).not.toMatch(/Dividend Yield Fund|Bluechip/); // fund lines in the demat statement are skipped, not reported as unmatched shares
  });
});

describe("rows and cells: layout details", () => {
  const it_ = (str: string, x: number, y: number, w = str.length * 5): PdfItem => ({ str, x, y, w, h: 9 });
  it("a quantity that touches the name column is still its own cell", () => {
    const g = gridFromPdfItems([[it_("Infosys Ltd", 40, 700), it_("30", 40 + 55 + 1.5, 700, 10), it_("1,234.50", 400, 700)]]);
    expect(g).toEqual([["Infosys Ltd", "30", "1,234.50"]]);
  });
  it("tightly packed columns (about 6 pt apart) are separate cells, words inside a name are not", () => {
    const g = rowsFromPdfItems([[it_("MOTOCORP LTD", 100, 700, 62), it_("HEROMOTOCO", 168, 700, 50), it_("Tata", 300, 700, 20), it_("Power", 323, 700, 25)]]);
    expect(g[0].cells.map((c) => c.t)).toEqual(["MOTOCORP LTD", "HEROMOTOCO", "Tata Power"]);
  });
  it("a gap-free grid (no positions) still reads: findHoldings on cell texts", () => {
    const f = findHoldings([["Stock Name", "Qty", "Value"], ["Infosys Ltd", "10", "14,500.00"], ["TCS", "5", "17,751.25"], ["Sub total", "", "32,251.25"]], INDEX);
    expect(sure(f)).toEqual(["INFY", "TCS"]);
  });
  it("text mode never ticks: a name inside a sentence is not a holding, a holding line is offered for checking", async () => {
    const f = await readPdfHoldings(file("text_lines.pdf"), INDEX);
    expect(sure(f)).toEqual([]); expect(unsure(f)).toEqual(["BAJAJ-AUTO", "HDFCBANK", "INFY", "LT", "M&M"]);     // RELIANCE only appears in a note
    const n = await readPdfHoldings(file("name_list_only.pdf"), INDEX);
    expect(sure(n)).toEqual([]); expect(unsure(n)).toEqual(["HDFCBANK", "INFY", "RELIANCE", "TCS"]);
  });
  it("with the real list of ~6000 companies a 150-row statement with 84 unknown lines still reads in well under 5 seconds", async () => {
    const filler: SearchRow[] = Array.from({ length: 6000 }, (_, i) => [`ZZ${i}`, `Zeta ${["Alpha", "Beta", "Gamma", "Delta"][i % 4]} ${i} Industries Ltd`, String(600000 + i), 0, `ZZ${i}`] as unknown as SearchRow);
    const t0 = performance.now();
    const f = await readPdfHoldings(file("large_150_rows.pdf"), [...INDEX, ...filler]);
    const ms = performance.now() - t0;
    expect(sure(f)).toHaveLength(MAN["large_150_rows.pdf"].expected.length);
    expect(ms).toBeLessThan(2500);
  });
  it("a 150-row, 5-page statement reads in well under 5 seconds", async () => {
    const t0 = performance.now();
    const f = await readPdfHoldings(file("large_150_rows.pdf"), INDEX);
    const ms = performance.now() - t0;
    expect(sure(f)).toHaveLength(MAN["large_150_rows.pdf"].expected.length);
    expect(ms).toBeLessThan(2500);
  });
});
