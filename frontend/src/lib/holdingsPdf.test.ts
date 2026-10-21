import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import type { SearchRow } from "./api";
import { PdfNoTextError, PdfPasswordError, gridFromPdfItems, joinWrappedNames, readPdfHoldings, setPdfLoader, type PdfItem } from "./holdingsPdf";
import { makeLookup } from "./holdingsMatch";

const R = (s: string, n: string, b: string) => [s, n, b, 1, s] as unknown as SearchRow;
const INDEX: SearchRow[] = [
  R("RELIANCE", "Reliance Industries Ltd.", "500325"), R("TCS", "Tata Consultancy Services Ltd.", "532540"), R("HDFCBANK", "HDFC Bank Ltd.", "500180"), R("INFY", "Infosys Ltd.", "500209"),
  R("ITC", "ITC Ltd.", "500875"), R("LT", "Larsen & Toubro Ltd.", "500510"), R("ICICIBANK", "ICICI Bank Ltd.", "532174"), R("SBIN", "State Bank of India", "500112"),
  R("BHARTIARTL", "Bharti Airtel Ltd.", "532454"), R("TMPV", "Tata Motors Passenger Vehicles Ltd.", "500570"), R("TMCV", "Tata Motors Ltd.", "544569"), R("WIPRO", "Wipro Ltd.", "507685"),
  R("ASIANPAINT", "Asian Paints Ltd.", "500820"), R("HINDUNILVR", "Hindustan Unilever Ltd.", "500696"), R("MARUTI", "Maruti Suzuki India Ltd.", "532500"), R("SUNPHARMA", "Sun Pharmaceutical Industries Ltd.", "524715"),
  R("TITAN", "Titan Company Ltd.", "500114"), R("NTPC", "NTPC Ltd.", "532555"), R("POWERGRID", "Power Grid Corporation of India Ltd.", "532898"), R("COALINDIA", "Coal India Ltd.", "533278"),
  R("ADANIPORTS", "Adani Ports and Special Economic Zone Ltd.", "532921"), R("AXISBANK", "Axis Bank Ltd.", "532215"), R("KOTAKBANK", "Kotak Mahindra Bank Ltd.", "500247"),
];
const dir = new URL("./fixtures/pdf/", import.meta.url);
const file = (name: string) => new File([readFileSync(new URL(name, dir))], name, { type: "application/pdf" });
const syms = (f: { found: { symbol: string }[] }) => f.found.map((x) => x.symbol).sort();

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
