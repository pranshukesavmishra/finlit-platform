// @vitest-environment node
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { PdfPasswordError, setPdfLoader, type PdfItem } from "./holdingsPdf";
import { casLines, holdingsFromCasLines, schemeName, statementFromPdf, statementFromPdfPages } from "./mfCas";
import { StatementError } from "./mfStatement";

const require = createRequire(import.meta.url);
beforeAll(() => {
  const worker = pathToFileURL(require.resolve("pdfjs-dist/legacy/build/pdf.worker.mjs")).href;
  setPdfLoader(async () => { const m = await import("pdfjs-dist/legacy/build/pdf.mjs"); m.GlobalWorkerOptions.workerSrc = worker; return m as unknown as typeof import("pdfjs-dist"); });
});
const fixture = () => {
  const b = readFileSync(new URL("./fixtures/cas/sample_cas_detailed.pdf", import.meta.url));
  return new File([b], "cas.pdf", { type: "application/pdf" });
};

describe("detailed CAS lines", () => {
  const L = [
    "Folio No: 91234567 / 12 PAN: ABCDE1234F KYC: OK",
    "B205 - Axis Bluechip Fund - Direct Growth - ISIN: INF846K01EW2(Advisor: DIRECT) Registrar : KFINTECH",
    "05-Oct-2026 Purchase 5,000.00 90.712 55.1200 1,234.567",
    "Closing Unit Balance: 1,234.567 NAV on 31-Oct-2026: INR 55.0900 Total Cost Value: 50,000.00 Market Value on 31-Oct-2026: INR 68,012.34",
  ];
  it("takes the closing position with its folio, never a transaction line and never the PAN", () => {
    const r = holdingsFromCasLines(L);
    expect(r.rows).toEqual([{ row: 2, name: "Axis Bluechip Fund - Direct Growth", isin: "INF846K01EW2", folio: "91234567 / 12", units: "1234.567", nav: "55.0900", invested: "50000.00", current: "68012.34" }]);
    expect(JSON.stringify(r)).not.toContain("ABCDE1234F");
  });
  it("leaves out a fully redeemed folio and counts it; a scheme with no closing balance is named, never guessed", () => {
    const r = holdingsFromCasLines([...L, "P8 - Some Fund - ISIN: INF879O01027", "Closing Unit Balance: 0.000 Market Value: 0.00", "X1 - Lost Fund Growth - ISIN: INF000000001"]);
    expect(r.rows).toHaveLength(1); expect(r.zero).toBe(1); expect(r.noBalance).toEqual(["Lost Fund Growth"]);
  });
  it("a name wrapped above its ISIN is put back together", () => {
    expect(schemeName("- ISIN: INF179K01XQ0(Advisor: DIRECT)", "H123 - HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth Option")).toBe("HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth Option");
  });
  it("a zero cost is no cost (the server then says why the gain is missing)", () => {
    const r = holdingsFromCasLines(["A1 - A Fund - ISIN: INF846K01EW2", "Closing Unit Balance: 10.000 Total Cost Value: 0.00 Market Value: 120.00"]);
    expect(r.rows[0].invested).toBeUndefined(); expect(r.rows[0].current).toBe("120.00");
  });
  it("pieces on one baseline become one line, left to right", () => {
    const it = (str: string, x: number, y: number): PdfItem => ({ str, x, y, w: 10, h: 8 });
    expect(casLines([[it("Balance:", 80, 500), it("Closing Unit", 10, 500.5), it("next", 10, 480)]])).toEqual(["Closing Unit Balance:", "next"]);
  });
  it("a PDF that is neither a CAS nor a table says so", () => {
    const it = (str: string, y: number): PdfItem => ({ str, x: 10, y, w: 10, h: 8 });
    expect(() => statementFromPdfPages([[it("Hello", 500), it("World", 480)]], () => [["Hello"], ["World"]])).toThrow(StatementError);
  });
});

describe("the sample CAS PDF (made-up investor, password protected the way CAMS / KFintech send it)", () => {
  it("asks for the password, refuses a wrong one, and reads every open scheme with the right one", async () => {
    await expect(statementFromPdf(fixture())).rejects.toBeInstanceOf(PdfPasswordError);
    await expect(statementFromPdf(fixture(), "WRONG")).rejects.toMatchObject({ wrong: true });
    const st = await statementFromPdf(fixture(), "ABCDE1234F");
    expect(st.rows.map((r) => [r.isin, r.folio, r.units, r.invested, r.current, r.nav])).toEqual([
      ["INF846K01EW2", "91234567 / 12", "1234.567", "50000.00", "68012.34", "55.0900"],
      ["INF179K01XQ0", "2233445 / 67", "200.500", "25500.00", "36140.13", "180.2500"],
    ]);
    expect(st.rows[1].name).toBe("HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth Option");
    expect((st.notes ?? []).join(" ")).toMatch(/1 scheme\(s\) with a closing balance of 0/);
  });
});
