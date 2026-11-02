/** Reading a Consolidated Account Statement (CAS) PDF for "MF portfolio": the detailed statement CAMS, KFintech and MF Central email each month.
 *  The PDF and its password never leave the device (pdf.js in the browser, lib/holdingsPdf). Only the closing position of each scheme is taken:
 *    Folio No: 1234567 / 89                       -> the folio of the blocks that follow
 *    B205 - Axis Bluechip Fund - Direct Growth - ISIN: INF846K01EW2 (Advisor: DIRECT) Registrar : KFINTECH
 *    ... transactions (never read) ...
 *    Closing Unit Balance: 1,234.567  NAV on 31-Oct-2026: INR 55.12  Total Cost Value: 50,000.00  Market Value on 31-Oct-2026: INR 68,012.34
 *  A scheme is taken only when BOTH its ISIN line and its closing balance are found; the server then decides which fund the ISIN is (the same preview as an
 *  Excel import), so nothing is matched by guesswork here. A folio whose closing balance is 0 (fully redeemed) is left out and counted.
 *  A PDF that is not in this layout (a summary statement, a broker's holdings report) is read as a table with the spreadsheet column rules instead. */
import { gridFromPdfItems, readPdfItems, type PdfItem } from "./holdingsPdf";
import { statementFromGrids, StatementError, MAX_ROWS, type RawRow, type Statement } from "./mfStatement";

/** Text pieces to lines: pieces on the same page whose baselines are within half a line are one line, read left to right. */
export function casLines(pages: PdfItem[][]): string[] {
  const out: string[] = [];
  for (const items of pages) {
    const sorted = items.filter((i) => i.str.trim()).sort((a, b) => b.y - a.y || a.x - b.x);
    let cur: PdfItem[] = [];
    const flush = () => { if (cur.length) out.push(cur.sort((a, b) => a.x - b.x).map((i) => i.str.trim()).join(" ").replace(/\s+/g, " ").trim()); cur = []; };
    for (const it of sorted) {
      const tol = Math.max(2, (it.h || 10) / 2);
      if (cur.length && Math.abs(cur[0].y - it.y) > tol) flush();
      cur.push(it);
    }
    flush();
  }
  return out;
}

const NUM = String.raw`\(?-?[\d,]+(?:\.\d+)?\)?`;
const CUR = String.raw`(?:INR|Rs\.?|₹)?\s*`;
const RX = {
  folio: /\bFolio\s*(?:No\.?|Number)?\s*:?\s*([0-9][0-9A-Za-z]*(?:\s*\/\s*[0-9A-Za-z]+)?)/i,
  isin: /\bISIN\s*:?\s*(INF[A-Z0-9]{9})\b/,
  closing: new RegExp(String.raw`Closing\s+Unit\s+Balance\s*:?\s*(${NUM})`, "i"),
  nav: new RegExp(String.raw`\bNAV\s+on\s+([0-9]{1,2}[-\s][A-Za-z]{3}[-\s][0-9]{4})\s*:?\s*${CUR}(${NUM})`, "i"),
  cost: new RegExp(String.raw`(?:Total\s+)?Cost\s+Value\s*:?\s*${CUR}(${NUM})`, "i"),
  market: new RegExp(String.raw`(?:Market|Valuation)\s+Value(?:\s+on\s+[0-9]{1,2}[-\s][A-Za-z]{3}[-\s][0-9]{4})?\s*:?\s*${CUR}(${NUM})`, "i"),
};
const plain = (s: string) => s.replace(/[(),\s]/g, "");
const isZero = (s: string) => Number(plain(s)) === 0;

/** The scheme's name from its ISIN line (and the line before, when the name was wrapped above the ISIN). */
export function schemeName(line: string, before: string | undefined): string {
  let name = line.slice(0, line.search(/\bISIN\b/)).replace(/[\s\-–:]+$/, "");
  name = name.replace(/^[A-Z0-9]{1,10}\s*-\s*/, "").trim();            // the registrar's scheme code: "B205 - "
  if (name.length < 6 && before && !RX.folio.test(before) && !RX.closing.test(before)) name = (before.replace(/^[A-Z0-9]{1,10}\s*-\s*/, "") + " " + name).trim();
  return name.replace(/\s*\((?:formerly|erstwhile)[^)]*\)\s*/gi, " ").replace(/\s+/g, " ").trim();
}

export type CasRead = { rows: RawRow[]; zero: number; noBalance: string[] };

/** The detailed-CAS layout read from lines. A scheme line with no closing balance before the next scheme is listed in `noBalance` (never guessed). */
export function holdingsFromCasLines(lines: string[]): CasRead {
  const rows: RawRow[] = [], noBalance: string[] = [];
  let folio = "", zero = 0;
  let open: { name: string; isin: string; folio: string; line: number } | null = null;
  const close = () => { if (open) noBalance.push(open.name || open.isin); open = null; };
  lines.forEach((line, i) => {
    const isin = RX.isin.exec(line);
    if (isin) { close(); open = { name: schemeName(line, lines[i - 1]), isin: isin[1], folio, line: i + 1 }; return; }
    const f = RX.folio.exec(line);
    if (f && !RX.closing.test(line)) { folio = f[1].replace(/\s+/g, " ").trim(); return; }
    const c = RX.closing.exec(line);
    if (c && open) {
      const tail = [line, lines[i + 1] ?? "", lines[i + 2] ?? ""].join(" ");     // the values sometimes wrap onto the next line or two
      const o: { name: string; isin: string; folio: string; line: number } = open;
      open = null;
      if (isZero(c[1])) { zero++; return; }
      const nav = RX.nav.exec(tail), cost = RX.cost.exec(tail), mkt = RX.market.exec(tail);
      const r: RawRow = { row: o.line, name: o.name, isin: o.isin, units: plain(c[1]) };
      if (o.folio) r.folio = o.folio;
      if (cost && !isZero(cost[1])) r.invested = plain(cost[1]);
      if (mkt) r.current = plain(mkt[1]);
      if (nav) r.nav = plain(nav[2]);
      rows.push(r);
    }
  });
  close();
  return { rows, zero, noBalance };
}

export const CAS_HEADERS = { name: "Scheme (CAS)", isin: "ISIN", folio: "Folio No", units: "Closing Unit Balance", invested: "Total Cost Value", current: "Market Value", nav: "NAV" } as const;

/** A statement from the PDF's pages: the detailed CAS layout when it is there, otherwise the PDF read as a table. */
export function statementFromPdfPages(pages: PdfItem[][], gridOf: (pages: PdfItem[][]) => string[][]): Statement {
  const cas = holdingsFromCasLines(casLines(pages));
  const notes: string[] = [];
  if (cas.rows.length || cas.zero) {
    if (!cas.rows.length) throw new StatementError(`Every scheme in this statement has a closing balance of 0 (${cas.zero} fully redeemed), so there is nothing to import.`);
    if (cas.rows.length > MAX_ROWS) throw new StatementError(`The statement has ${cas.rows.length} schemes; up to ${MAX_ROWS} can be imported at once.`);
    if (cas.zero) notes.push(`${cas.zero} scheme(s) with a closing balance of 0 were left out (fully redeemed).`);
    if (cas.noBalance.length) notes.push(`No closing balance was found for ${cas.noBalance.length} scheme(s), so they were left out: ${cas.noBalance.slice(0, 5).join("; ")}${cas.noBalance.length > 5 ? "; …" : ""}.`);
    return { rows: cas.rows, headers: { ...CAS_HEADERS }, skippedBlank: 0, skippedTotal: 0, sheets: 1, notes };
  }
  try { return { ...statementFromGrids([gridOf(pages)]), notes }; }
  catch (e) {
    if (e instanceof StatementError) throw new StatementError("This PDF is not a CAMS / KFintech detailed statement (no “Closing Unit Balance” lines were found) and no holdings table was found in it. " + e.message);
    throw e;
  }
}

/** Read a chosen PDF (asks the caller for the password through PdfPasswordError, as the stock import does). */
export async function statementFromPdf(file: File, password?: string): Promise<Statement> {
  return statementFromPdfPages(await readPdfItems(file, password), gridFromPdfItems);
}
