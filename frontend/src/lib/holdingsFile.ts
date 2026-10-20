/** Reading a broker's holdings file (Excel .xlsx/.xls/.xlsm/.ods, .csv, .tsv, .txt, or the HTML table some brokers save as ".xls").
 *  A broker's export holds much more than names: quantity, average price, P&L, ISIN, dates and title rows. Only the share names are taken.
 *  The name column is found by looking at the VALUES (which column's cells match listed companies), then by its header, so the file does
 *  not need a particular layout. The spreadsheet library is loaded only when a spreadsheet is chosen. */

export type Grid = string[][];
export type NameMatcher = (name: string) => boolean;

const NAME_HEAD = /^(symbol|trading ?symbol|ticker|scrip( ?name)?|stock( ?name)?|share( ?name)?|instrument( ?name)?|security( ?name)?|company( ?name)?|name( of (the )?(security|scrip|stock|company|instrument))?|name|nse|bse|isin)\b/i;
const NOT_NAME = /^(total|grand total|sub ?total|net|portfolio|summary|invested|current|holdings|equity|equities|mutual funds?|cash|margin|p ?& ?l|unrealised|realised|as on|as of|date|client|name:|id|pan|account|ucc|dp|demat|sr\.? ?no|s\.? ?no)\b/i;
/** Words that are labels only when they stand alone or lead a short phrase, not when they open a company name ("Client Services Ltd"). */
const COMPANY_END = /\b(ltd|limited|corp|corporation|inc|co|company|bank|industries|finance|services|systems|technologies|enterprises)\.?$/i;
/** A bare column heading ("Symbol", "ISIN", "Scrip Name"): never a share name itself. */
const BARE_HEAD = /^(symbol|trading ?symbol|ticker|scrip( ?name)?|stock( ?name| ?symbol)?|share( ?name)?|instrument( ?name)?|security( ?name)?|company( ?name)?|name|nse|bse|isin|isin ?(code|no\.?|number)?|symbol ?name)$/i;
/** Other words that mark a header row (quantity, price, value, P&L ...). */
const HEAD_WORDS = /^(qty|quantity|units?|shares?|avg|average|price|ltp|cmp|cur|current|value|val|p ?& ?l|pnl|profit|loss|net chg|day chg|change|chg|buy|sell|cost|closing|invested|market|exchange|series|holdings?|returns?|unrealised|realised|amount|balance|free|pledged|collateral|t ?\+ ?1|dp)\b/i;
const NUMERIC = /^[\s\d.,₹$%()+\-/:]*$/;
const ISIN = /^[A-Z]{2}[A-Z0-9]{9}\d$/;
const MAX_ROWS = 5000;

/** Text that holds a name: not a number, a date, a total line or a lone code. */
export function plausibleName(s: string): boolean {
  const t = s.trim();
  if (t.length < 2 || t.length > 80) return false;
  if (NUMERIC.test(t) && !/^\d{6}$/.test(t)) return false;       // a six-digit BSE code is allowed
  if (BARE_HEAD.test(t)) return false;
  if (NOT_NAME.test(t) && !(COMPANY_END.test(t) && !/^(total|grand total|sub ?total)\b/i.test(t))) return false;
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
  // Title blocks ("Name  TEST USER", "Client ID ...") also hold words like "Name", so the row with the MOST heading-like cells wins (ties: the earliest).
  let headerRow = -1, headerScore = 0;
  for (let i = 0; i < Math.min(rows.length, 80); i++) {
    const cells = rows[i].map((c) => c.trim()).filter(Boolean);
    if (!cells.some((c) => NAME_HEAD.test(c))) continue;
    if (cells.length < 2 && !(cells.length === 1 && rows.length > 1 && i === rows.findIndex((r) => r.some((c) => c.trim())))) continue;   // a lone heading counts only as the first line of a one-column list
    const score = cells.filter((c) => NAME_HEAD.test(c) || HEAD_WORDS.test(c)).length;
    if (score > headerScore) { headerRow = i; headerScore = score; }
  }
  let body = rows.slice(headerRow + 1);
  const endAt = body.findIndex((r) => r.some((c) => /^(grand |sub ?)?total\s*[:\-]?\s*(value|holdings?|investment|invested|portfolio)?$/i.test(c.trim())));   // broker files end with a Total line and notes
  if (endAt > 0) body = body.slice(0, endAt);

  const colValues = (c: number) => body.map((r) => tidy(r[c] || "")).filter(plausibleName);
  const headed = headerRow >= 0 ? rows[headerRow].map((h, c) => ({ c, rank: rankHead(h) })).filter((x) => x.rank > 0).sort((a, b) => b.rank - a.rank) : [];
  const score = (c: number) => { const v = colValues(c); return { c, v, hit: matches ? v.filter(matches).length : 0 }; };

  let best = { c: -1, v: [] as string[], hit: 0 };
  if (matches) for (let c = 0; c < width; c++) { const s = score(c); if (s.hit > best.hit || (s.hit === best.hit && s.hit > 0 && headed.some((h) => h.c === s.c) && !headed.some((h) => h.c === best.c))) best = s; }
  let chosen: string[];
  if (headerRow < 0 && rows.length === 1 && width > 1) chosen = rows[0].map(tidy).filter(plausibleName);   // "TCS, INFY, ITC" on one line is a list, not a table
  else if (best.hit > 0) chosen = best.v;                                                  // the column whose cells are listed companies
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
  // The delimiter is the one that splits the most lines into the same number of columns (>1); a title line alone must not decide it.
  const lines = clean.split(/\r?\n|\r/).filter((l) => l.trim()).slice(0, 60);
  const fieldCount = (line: string, dl: string) => { let n = 1, qq = false; for (const ch of line) { if (ch === '"') qq = !qq; else if (ch === dl && !qq) n++; } return n; };
  let d = ",", bestLines = 0;
  for (const dl of ["\t", ";", "|", ","]) {                    // listed in preference order for ties
    const freq = new Map<number, number>();
    for (const l of lines) { const n = fieldCount(l, dl); if (n > 1) freq.set(n, (freq.get(n) || 0) + 1); }
    const top = Math.max(0, ...freq.values());
    if (top > bestLines) { bestLines = top; d = dl; }
  }
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

/** A zip ends with an "end of central directory" record (PK 05 06) within its last 64 KB + 22 bytes. */
function hasZipEnd(b: Uint8Array): boolean {
  for (let i = b.length - 22; i >= Math.max(0, b.length - 65_557); i--) if (b[i] === 0x50 && b[i + 1] === 0x4b && b[i + 2] === 5 && b[i + 3] === 6) return true;
  return false;
}

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
  const bad = new Error("That file could not be read as a spreadsheet. Save it again as .xlsx or .csv, or paste the names instead.");
  if (isZip && !hasZipEnd(new Uint8Array(buf))) throw bad;                                     // truncated or corrupt zip: the library would guess at text
  if (isOle && !(head[2] === 0x11 && head[3] === 0xe0 && head[4] === 0xa1 && head[5] === 0xb1 && head[6] === 0x1a && head[7] === 0xe1)) throw bad;
  if (looksText && !isMarkup && new Uint8Array(buf, 0, Math.min(buf.byteLength, 4096)).includes(0)) throw bad;   // binary with a spreadsheet name but no spreadsheet signature
  const XLSX = await import("xlsx");
  let wb: import("xlsx").WorkBook;
  try { wb = XLSX.read(buf, { type: "array", cellDates: false, cellFormula: false, cellHTML: false, cellStyles: false, sheetRows: MAX_ROWS }); } catch { throw bad; }
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
