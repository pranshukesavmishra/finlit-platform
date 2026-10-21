/** Reading a holdings statement saved as a PDF (a broker's holdings report, a depository statement, a contract-note summary).
 *  The PDF is read in the browser (pdf.js, loaded only when a PDF is chosen): the file and its password never leave the device.
 *  Only the names of listed companies are taken. Accuracy comes first, so:
 *   - a company is accepted only when its text equals a listed ticker, code or full name (a name that merely starts the same way is marked "close");
 *   - the table's name column is found by which column's cells are listed companies, as for Excel files;
 *   - when there is no table, the text is searched for whole company names, and each such find is marked "found in text";
 *   - the page then shows every match next to the PDF's own words, so the person confirms before anything is added.
 *  A scanned PDF (a photo of paper) holds no text and cannot be read: say so instead of guessing. */
import type { SearchRow } from "./api";
import { namesFromGrid, plausibleName, tidy, type Grid } from "./holdingsFile";
import { makeLookup, makeMatcher, matchNames, type Found } from "./holdingsMatch";

export type PdfItem = { str: string; x: number; y: number; w: number; h: number };
export const PDF_MAX_BYTES = 10_000_000;
const MAX_PAGES = 80;

export class PdfPasswordError extends Error { constructor(public wrong: boolean) { super(wrong ? "That password is not correct." : "This PDF is password protected."); } }
export class PdfNoTextError extends Error { constructor() { super("This PDF has no text to read (it looks like a scan or a photo). Download the Excel or CSV version of the statement from your broker, or paste the names."); } }
export class PdfReadError extends Error { constructor() { super("That PDF could not be read. Download the statement again, or use its Excel or CSV version."); } }

/* ------------------------------------------------------------------ text pieces to rows of cells */

const median = (v: number[]) => { const s = [...v].sort((a, b) => a - b); return s.length ? s[s.length >> 1] : 0; };

/** Pieces of text with positions (one array per page) into rows of cells: pieces on the same baseline form a row, and a gap wider than about
 *  one character starts a new cell, so a table's columns come out as cells and a name's words stay together. */
export function gridFromPdfItems(pages: PdfItem[][]): Grid {
  const out: Grid = [];
  for (const items of pages) {
    const live = items.filter((i) => i.str.trim() !== "" && Number.isFinite(i.x) && Number.isFinite(i.y));
    if (!live.length) continue;
    const tol = Math.max(1.5, median(live.map((i) => i.h).filter((h) => h > 0)) * 0.5);
    const sorted = [...live].sort((a, b) => b.y - a.y || a.x - b.x);
    const lines: PdfItem[][] = [];
    for (const it of sorted) {
      const line = lines[lines.length - 1];
      if (line && Math.abs(line[0].y - it.y) <= tol) line.push(it); else lines.push([it]);
    }
    for (const line of lines) {
      line.sort((a, b) => a.x - b.x);
      const row: string[] = [];
      let cell = "", end = -Infinity, h = 0;
      for (const it of line) {
        const size = Math.max(it.h, h, 6);
        const gap = it.x - end;
        if (cell && gap > size * 0.9) { row.push(cell.trim()); cell = ""; }
        cell += (cell && gap > size * 0.12 && !/\s$/.test(cell) && !/^\s/.test(it.str) ? " " : "") + it.str;
        end = it.x + it.w; h = it.h;
      }
      if (cell.trim()) row.push(cell.trim());
      if (row.length) out.push(row);
    }
  }
  return out;
}

/** A company name that wrapped onto a second line in a narrow column ("Tata Consultancy" / "Services Ltd") is joined back to one cell,
 *  but only when the joined text IS a listed company and neither half is. */
export function joinWrappedNames(grid: Grid, isExact: (name: string) => boolean): Grid {
  const out: Grid = [];
  const lone = (r?: string[]) => !!r && r.length === 1 && /[A-Za-z]/.test(r[0]) && !/\d/.test(r[0].replace(/\b(ltd|limited|and)\b/gi, ""));   // a continuation line has no numbers of its own
  for (let i = 0; i < grid.length; i++) {
    const row = grid[i], next = grid[i + 1], third = grid[i + 2];
    const first = row[0] || "";
    if (first && /[A-Za-z]/.test(first) && lone(next) && !isExact(next![0])) {
      const two = `${first} ${next![0]}`;
      if (isExact(two)) { out.push([two, ...row.slice(1)]); i += 1; continue; }
      if (lone(third) && !isExact(third![0]) && isExact(`${two} ${third![0]}`)) { out.push([`${two} ${third![0]}`, ...row.slice(1)]); i += 2; continue; }
    }
    out.push(row);
  }
  return out;
}

/* ------------------------------------------------------------------ names in the grid */

export type PdfFinds = { found: Found[]; missing: string[]; mode: "table" | "text"; rows: number };

const WORD = /[A-Za-z0-9&'.\-]+/g;
const MONEY = /\b\d{1,3}(,\d{2,3})+(\.\d+)?\b|\b\d+\.\d{2}\b/;   // 29,001.00  1,64,000  2900.10: an amount, not a year or a phone number
const LABEL_ONLY = /^(and|of|the|ltd|limited|india|indian|bank|banks|fund|funds|group|global|power|steel|gas|oil|life|home|motors|capital|energy|finance|industries|services|systems|technologies|holdings|total|net|cash|equity|unit|units|date|name|folio|scheme|price|value|amount|balance|nav)$/i;

/** Companies in a PDF's rows. Table first (the column whose cells are listed companies); when no column matches, whole company names or
 *  tickers found inside the text of rows that also carry numbers (a holding has a quantity and a value), each marked "scan". */
export function findHoldings(grid: Grid, index: SearchRow[]): PdfFinds {
  if (!grid.length || !index.length) return { found: [], missing: [], mode: "table", rows: grid.length };
  const matcher = makeMatcher(index)!;
  const { exact, norm } = makeLookup(index);
  const joined = joinWrappedNames(grid, (n) => !!exact(n));
  const names = namesFromGrid(joined, matcher);
  const table = matchNames(names, index);
  if (table.found.length) {
    // headings that repeat on every page are not companies
    const missing = table.missing.filter((m) => plausibleName(m) && !LABEL_ONLY.test(m.trim()));
    return { found: dedupe(table.found), missing, mode: "table", rows: grid.length };
  }
  const seen = new Map<string, Found>();
  for (const row of joined) {
    if (!row.some((c) => MONEY.test(c) || /^[\s\d.,₹()\-+%]*\d[\s\d.,₹()\-+%]*$/.test(c))) continue;   // no amount or number cell: a heading or a sentence, not a holding
    const original = row.filter((c) => !/^[\s\d.,₹()\-+%/:]+$/.test(c)).join(" ");
    const words = (original.toUpperCase().match(WORD) || []), raw = original.match(WORD) || [];
    for (let i = 0; i < words.length; i++) {
      for (let len = Math.min(7, words.length - i); len >= 1; len--) {
        const phrase = words.slice(i, i + len).join(" ");
        if (len === 1 && (phrase.length < 3 || LABEL_ONLY.test(phrase) || /^\d+$/.test(phrase) || /^INE[0-9A-Z]{9}$/.test(phrase) || raw[i] !== phrase)) continue;   // a lone ticker must be written in capitals, as statements do
        if (len > 1 && norm(phrase).split(" ").length < 2 && norm(phrase).length < 6) continue;
        const hit = exact(phrase);
        if (hit && !seen.has(hit[0])) { seen.set(hit[0], { input: phrase, symbol: hit[0], name: hit[1], how: "scan" }); i += len - 1; break; }
      }
    }
  }
  return { found: [...seen.values()], missing: [], mode: "text", rows: grid.length };
}

function dedupe(found: Found[]): Found[] {
  const by = new Map<string, Found>();
  for (const f of found) { const cur = by.get(f.symbol); if (!cur || rank(f.how) < rank(cur.how)) by.set(f.symbol, f); }
  return [...by.values()];
}
const rank = (h: Found["how"]) => ({ exact: 0, alias: 1, split: 1, close: 2, scan: 3 }[h]);

/* ------------------------------------------------------------------ reading the file */

type PdfJs = typeof import("pdfjs-dist");
let loader: () => Promise<PdfJs> = async () => {
  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = (await import("pdfjs-dist/build/pdf.worker.min.mjs?url")).default;
  return pdfjs;
};
/** For tests: supply a pdf.js that runs under Node. */
export function setPdfLoader(fn: () => Promise<PdfJs>) { loader = fn; }

export const isPdf = (file: File, head?: Uint8Array) => (head ? String.fromCharCode(...head.slice(0, 5)) === "%PDF-" : /\.pdf$/i.test(file.name) || file.type === "application/pdf");

/** Every page's text pieces. Throws PdfPasswordError (ask for the password and call again), PdfNoTextError (a scan) or PdfReadError. */
export async function readPdfItems(file: File, password?: string): Promise<PdfItem[][]> {
  if (file.size > PDF_MAX_BYTES) throw new Error("That PDF is larger than 10 MB. Download only the holdings statement, or use its Excel or CSV version.");
  const data = new Uint8Array(await file.arrayBuffer());
  if (String.fromCharCode(...data.slice(0, 5)) !== "%PDF-") throw new PdfReadError();
  const pdfjs = await loader();
  let doc: Awaited<ReturnType<PdfJs["getDocument"]>["promise"]>;
  try {
    doc = await pdfjs.getDocument({ data, password, isEvalSupported: false, disableFontFace: true, useSystemFonts: false, verbosity: 0 }).promise;
  } catch (e) {
    const err = e as { name?: string; code?: number };
    if (err?.name === "PasswordException") throw new PdfPasswordError(err.code === 2);
    throw new PdfReadError();
  }
  const pages: PdfItem[][] = [];
  try {
    for (let p = 1; p <= Math.min(doc.numPages, MAX_PAGES); p++) {
      const page = await doc.getPage(p), content = await page.getTextContent();
      pages.push(content.items.flatMap((it) => ("str" in it && it.str ? [{ str: it.str, x: it.transform[4], y: it.transform[5], w: it.width, h: it.height || Math.abs(it.transform[3]) }] : [])));
    }
  } catch { throw new PdfReadError(); } finally { try { await doc.destroy(); } catch { /* already gone */ } }
  if (!pages.some((p) => p.some((i) => i.str.trim()))) throw new PdfNoTextError();
  return pages;
}

/** The whole job: a PDF file and the list of listed companies in, the companies found (and the lines that were not recognised) out. */
export async function readPdfHoldings(file: File, index: SearchRow[], password?: string): Promise<PdfFinds> {
  const grid = gridFromPdfItems(await readPdfItems(file, password));
  return findHoldings(grid, index);
}

export { tidy };
