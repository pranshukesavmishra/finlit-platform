/** Reading a broker's holdings file (Excel .xlsx/.xls/.xlsm/.ods, .csv, .tsv, .txt, or the HTML table some brokers save as ".xls").
 *  A broker's export holds much more than names: quantity, average price, P&L, ISIN, dates and title rows. Only the share names are taken.
 *  The name column is found by looking at the VALUES (which column's cells match listed companies), then by its header, so the file does
 *  not need a particular layout. The spreadsheet library is loaded only when a spreadsheet is chosen. */

export type Grid = string[][];
export type NameMatcher = (name: string) => boolean;

const NAME_HEAD = /^(symbol|trading ?symbol|ticker|scrip( ?name)?|stock( ?name)?|share( ?name)?|instrument( ?name)?|security( ?name)?|company( ?name)?|name( of (the )?(security|scrip|stock|company|instrument))?|name|nse|bse|isin)\b/i;
const NOT_NAME = /^(total|grand total|sub ?total|net|portfolio|summary|invested|current|holdings|equity|equities|mutual funds?|cash|margin|p ?& ?l|unrealised|realised|as on|as of|date|client|name:|id|pan|account|ucc|dp|demat|sr\.? ?no|s\.? ?no)\b/i;
const NUMERIC = /^[\s\d.,₹$%()+\-/:]*$/;
const ISIN = /^[A-Z]{2}[A-Z0-9]{9}\d$/;
const MAX_ROWS = 5000;

/** Text that holds a name: not a number, a date, a total line or a lone code. */
export function plausibleName(s: string): boolean {
  const t = s.trim();
  if (t.length < 2 || t.length > 80) return false;
  if (NUMERIC.test(t) && !/^\d{6}$/.test(t)) return false;       // a six-digit BSE code is allowed
  if (NOT_NAME.test(t)) return false;
  if (ISIN.test(t)) return false;                                // an ISIN says which company, but is not a name; the name column is used
  return true;
}

/** Cleans a broker's way of writing a name: "TCS-EQ", "RELIANCE EQ", "HDFCBANK.NS", "INFY - BE", "ITC LTD. EQ" become the plain name. */
export function tidy(s: string): string {
  return s.replace(/ /g, " ").replace(/\s+/g, " ").trim()
    .replace(/^(NSE|BSE)\s*[:\-]\s*/i, "").replace(/\.(NS|BO)$/i, "")
    .replace(/\s*[-/]\s*(EQ|BE|BZ|SM|ST|N\d|T\d|IL|GB|IV)$/i, "").replace(/\s+(EQ|BE|BZ)$/i, "")
    .replace(/\s*\((EQ|BE|NSE|BSE)\)$/i, "");
}

/** The share names in a grid of cells (rows of columns): the best column wins. `matches` says whether a name is a listed company. */
export function namesFromGrid(grid: Grid, matches?: NameMatcher): string[] {
  const rows = grid.slice(0, MAX_ROWS).map((r) => r.map((c) => (c == null ? "" : String(c))));
  if (!rows.length) return [];
  const width = Math.max(...rows.map((r) => r.length));
  // Header row: the first of the first 80 rows that names a column like a share column.
  let headerRow = -1;
  for (let i = 0; i < Math.min(rows.length, 80); i++) if (rows[i].filter((c) => NAME_HEAD.test(c.trim())).length >= 1 && rows[i].filter((c) => c.trim()).length >= 2) { headerRow = i; break; }
  let body = rows.slice(headerRow + 1);
  const endAt = body.findIndex((r) => r.some((c) => /^(grand )?total\b/i.test(c.trim())));   // broker files end with a Total line and notes
  if (endAt > 0) body = body.slice(0, endAt);

  const colValues = (c: number) => body.map((r) => tidy(r[c] || "")).filter(plausibleName);
  const headed = headerRow >= 0 ? rows[headerRow].map((h, c) => ({ c, rank: rankHead(h) })).filter((x) => x.rank > 0).sort((a, b) => b.rank - a.rank) : [];
  const score = (c: number) => { const v = colValues(c); return { c, v, hit: matches ? v.filter(matches).length : 0 }; };

  let best = { c: -1, v: [] as string[], hit: 0 };
  if (matches) for (let c = 0; c < width; c++) { const s = score(c); if (s.hit > best.hit || (s.hit === best.hit && s.hit > 0 && headed.some((h) => h.c === s.c) && !headed.some((h) => h.c === best.c))) best = s; }
  let chosen: string[];
  if (best.hit > 0) chosen = best.v;                                                  // the column whose cells are listed companies
  else if (headed.length) chosen = colValues(headed[0].c);                            // else the column headed like a share name
  else if (headerRow < 0 && width) chosen = rows.map((r) => tidy(r[0] || "")).filter(plausibleName);   // pasted text: the first column
  else chosen = [];
  return [...new Set(chosen)];
}

/** Higher = a more likely share-name header. ISIN is the weakest (it identifies, but is not a name). */
function rankHead(h: string): number {
  const t = h.trim().toLowerCase();
  if (!NAME_HEAD.test(t)) return 0;
  if (/^isin/.test(t)) return 1;
  if (/^(symbol|trading ?symbol|ticker)/.test(t)) return 5;
  if (/^(instrument|scrip|stock|security|company|share)/.test(t)) return 4;
  return 3;
}

/** Delimited text (a CSV, TSV, ;-separated or pasted list) into a grid. Quoted cells may hold the delimiter. */
export function gridFromText(text: string): Grid {
  const clean = text.replace(/^﻿/, "");
  const first = clean.split(/\r?\n/).find((l) => l.trim()) || "";
  const delim = [",", "\t", ";", "|"].map((d) => [d, first.split(d).length] as const).sort((a, b) => b[1] - a[1])[0];
  const d = delim[1] > 1 ? delim[0] : ",";
  const out: Grid = [];
  let row: string[] = [], cell = "", q = false;
  for (let i = 0; i < clean.length; i++) {
    const ch = clean[i];
    if (q) { if (ch === '"') { if (clean[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += ch; }
    else if (ch === '"') q = true;
    else if (ch === d) { row.push(cell.trim()); cell = ""; }
    else if (ch === "\n" || ch === "\r") { if (ch === "\r" && clean[i + 1] === "\n") i++; row.push(cell.trim()); cell = ""; if (row.some(Boolean)) out.push(row); row = []; }
    else cell += ch;
  }
  row.push(cell.trim()); if (row.some(Boolean)) out.push(row);
  return out;
}

const SHEET_TYPES = /\.(xlsx|xlsm|xlsb|xls|ods|html?|xml)$/i;
export const ACCEPT = ".xlsx,.xls,.xlsm,.xlsb,.ods,.csv,.tsv,.txt,.html,.htm,text/csv,text/plain,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
export const MAX_BYTES = 5_000_000;

/** Every sheet of a file as a grid. Works on Excel (both formats), OpenDocument, CSV and the HTML/XML tables some brokers call ".xls". */
export async function gridsFromFile(file: File): Promise<Grid[]> {
  if (file.size > MAX_BYTES) throw new Error("That file is larger than 5 MB. Export only your holdings, or paste the names instead.");
  const buf = await file.arrayBuffer();
  const head = new Uint8Array(buf.slice(0, 8));
  const isZip = head[0] === 0x50 && head[1] === 0x4b, isOle = head[0] === 0xd0 && head[1] === 0xcf;
  const looksText = !isZip && !isOle;
  const asText = looksText ? new TextDecoder("utf-8").decode(buf) : "";
  const isMarkup = looksText && /^\s*(<\?xml|<!doctype|<html|<table|<\?mso)/i.test(asText.slice(0, 400));
  if (looksText && !isMarkup && !SHEET_TYPES.test(file.name)) return [gridFromText(asText)];   // plain CSV / pasted text: no library needed
  if (looksText && !isMarkup && /\.(csv|tsv|txt)$/i.test(file.name)) return [gridFromText(asText)];
  const XLSX = await import("xlsx");
  const wb = XLSX.read(buf, { type: "array", cellDates: false, cellFormula: false, cellHTML: false, cellStyles: false, sheetRows: MAX_ROWS });
  return wb.SheetNames.map((n) => (XLSX.utils.sheet_to_json(wb.Sheets[n], { header: 1, raw: false, defval: "", blankrows: false }) as unknown[][]).map((r) => r.map((c) => (c == null ? "" : String(c)))));
}

/** The share names in a file; the sheet and column with the most listed companies win. */
export async function namesFromFile(file: File, matches?: NameMatcher): Promise<string[]> {
  const grids = await gridsFromFile(file);
  let best: string[] = [], bestHit = -1;
  for (const g of grids) {
    const names = namesFromGrid(g, matches), hit = matches ? names.filter(matches).length : names.length;
    if (hit > bestHit) { best = names; bestHit = hit; }
  }
  return best;
}
