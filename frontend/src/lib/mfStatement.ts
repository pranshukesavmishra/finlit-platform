/** Reading a mutual fund statement for "MF portfolio": an Excel sheet, a CSV, or a consolidated-statement-style CSV export (CAMS, KFintech, broker apps).
 *  This file only FINDS THE COLUMNS (headers are matched by synonyms) and hands back the cells as written; the server decides what every cell means (numbers, dates, folios,
 *  which rows are company shares) and which scheme each row is. Reuses the spreadsheet reader of the stock portfolio (lib/holdingsFile: 5 MB, 5,000 rows, the same Excel / CSV / HTML-table
 *  handling), so the two pages accept the same files. Nothing is guessed: a file without a recognisable header is refused with the headers it did find. */
import { gridsFromFile, type Grid } from "./holdingsFile";

export const FIELDS = ["name", "isin", "amfi", "folio", "units", "avgCost", "invested", "current", "nav", "date", "kind"] as const;
export type Field = (typeof FIELDS)[number];
export const FIELD_LABEL: Record<Field, string> = {
  name: "Fund name", isin: "ISIN", amfi: "AMFI code", folio: "Folio", units: "Units", avgCost: "Average cost per unit", invested: "Amount invested", current: "Current value",
  nav: "NAV", date: "Purchase date", kind: "Asset type",
};
/** `row` is the line's place among the file's non-blank lines (a CSV or a spreadsheet read without its empty rows), shown as "Line n" in the review. */
export type RawRow = { row: number } & Partial<Record<Field, string>>;
export const MAX_ROWS = 2000;

/** Header text reduced to lower-case words: "Invested Amount (₹)" -> "invested amount", "Scheme Name / Fund" -> "scheme name fund". */
const norm = (h: string) => h.toLowerCase().replace(/[₹$%*:()\[\]/\\_.,\-]+/g, " ").replace(/\s+/g, " ").trim();

/** In priority order: the first pattern a header matches decides its field. Order matters ("current nav" is a NAV, "avg nav" a cost, "purchase date" a date). */
const RULES: [Field, RegExp][] = [
  ["isin", /\bisin\b/],
  ["amfi", /\bamfi\b|\b(scheme|sch|fund) code\b/],
  ["folio", /\bfolio\b/],
  ["avgCost", /\b(avg|average)\b|\b(purchase|cost|buy|buying|acquisition)\b.*\b(nav|price|rate)\b|\b(nav|price)\b.*\b(avg|average|cost|purchase)\b|\bcost per unit\b|\bper unit cost\b|\bunit cost\b/],
  ["date", /^(purchase|transaction|trade|buy|investment|txn|trans|invested|allotment)\b.*\bdate\b|^date( of (purchase|investment|transaction))?$|^date of (purchase|investment|transaction)\b/],
  ["nav", /^((current|latest|closing|today|todays|market|live|last|cmp)\s+)?nav( per unit)?( as (on|of).*)?$|^nav (rs|inr)$|^price$/],
  ["current", /\b(current|market|present|latest|closing|valuation)\b.*\b(value|amount|valuation)\b|^valuation\b|^value( as (on|of).*)?$|^market value\b|^current$/],
  ["invested", /\b(invested|investment|cost|purchase|buy|total cost)\b( value| amount| cost)?$|^(amount invested|total invested|invested amount|invested value|cost value|purchase value|purchase cost|total cost|cost|invested)$/],
  ["units", /\b(units?|qty|quantity)\b/],
  ["name", /\bscheme name\b|\bfund name\b|\bname of (the )?(scheme|fund)\b|^(scheme|fund|mutual fund|scheme fund|scheme name fund|name|security name|instrument name|product name|scrip name|investment name|security|instrument|scheme details)$|\b(scheme|fund|security|instrument|product|scrip)\b.*\bname\b/],
  ["kind", /\b(asset|instrument|security|product|holding)\s*(type|class)\b|^type$/],
];

/** Which field a header cell stands for, or null (an unrelated column, or a "nav date" / "valuation date" that is not a purchase date). */
export function fieldOf(header: string): Field | null {
  const h = norm(header);
  if (!h || h.length > 60) return null;
  if (/\b(nav|valuation|as on|as of|maturity|dividend|idcw|last) date\b|\bdate (of )?(nav|valuation)\b/.test(h)) return null;
  if (/\b(return|returns|gain|gains|loss|profit|p l|pnl|xirr|cagr|change|weight|allocation|share)\b/.test(h)) return null;   // a result column, not an input
  for (const [f, rx] of RULES) if (rx.test(h)) return f;
  return null;
}

export type ColumnMap = Partial<Record<Field, number>>;
export type Located = { headerRow: number; map: ColumnMap; headers: Partial<Record<Field, string>> };

/** The header row (one of the first 80 rows) with the most recognised fields, and the column of each. It must give units and at least one of name / ISIN / AMFI code. */
export function locateColumns(grid: Grid): Located | null {
  let best: Located | null = null, bestN = 0;
  for (let i = 0; i < Math.min(grid.length, 80); i++) {
    const map: ColumnMap = {}, headers: Partial<Record<Field, string>> = {};
    grid[i].forEach((cell, c) => { const f = fieldOf(String(cell ?? "")); if (f && map[f] === undefined) { map[f] = c; headers[f] = cellText(cell); } });
    const ok = map.units !== undefined && (map.name !== undefined || map.isin !== undefined || map.amfi !== undefined);
    const n = Object.keys(map).length;
    if (ok && n > bestN) { best = { headerRow: i, map, headers }; bestN = n; }
  }
  return best;
}

const TOTAL = /^(grand\s+)?(sub\s*)?total\b|^net\s+(total|worth)\b|^portfolio\s+total\b/i;
const cellText = (v: unknown) => (v == null ? "" : String(v).replace(/ /g, " ").replace(/\s+/g, " ").trim());

export type ParsedSheet = { rows: RawRow[]; located: Located; skippedBlank: number; skippedTotal: number; sheet: number };

/** The rows under the header. A row with fewer than two filled cells among name / ISIN / AMFI / units / amount is a section title or a spacer, not a holding: skipped, and counted. */
export function rowsFromGrid(grid: Grid, located: Located): { rows: RawRow[]; skippedBlank: number; skippedTotal: number } {
  const rows: RawRow[] = [];
  let skippedBlank = 0, skippedTotal = 0;
  const head = (grid[located.headerRow] || []).map((h) => cellText(h).toLowerCase()).filter(Boolean);
  for (let r = located.headerRow + 1; r < grid.length; r++) {
    const line = grid[r] || [];
    if (!line.some((c) => cellText(c))) continue;
    const out: RawRow = { row: r + 1 };
    for (const f of FIELDS) { const c = located.map[f]; if (c !== undefined) { const t = cellText(line[c]); if (t) out[f] = t; } }
    const first = line.map(cellText).find(Boolean) || "";
    if (TOTAL.test(first) || TOTAL.test(out.name || "")) { skippedTotal++; continue; }
    if (head.length && line.map((c) => cellText(c).toLowerCase()).filter(Boolean).every((c) => head.includes(c))) { skippedBlank++; continue; }   // a repeated header line
    const filled = (["name", "isin", "amfi", "units", "invested", "current", "avgCost"] as Field[]).filter((f) => out[f]).length;
    if (filled < 2) { skippedBlank++; continue; }
    rows.push(out);
  }
  return { rows, skippedBlank, skippedTotal };
}

export type Statement = { rows: RawRow[]; headers: Partial<Record<Field, string>>; skippedBlank: number; skippedTotal: number; sheets: number };
export class StatementError extends Error {}

/** The best sheet of a file: the one with the most holding rows. Throws a StatementError (shown to the member) when no sheet has a usable header or no rows. */
export function statementFromGrids(grids: Grid[]): Statement {
  let best: (ParsedSheet & { n: number }) | null = null;
  let sawHeaders: string[] = [];
  grids.forEach((g, sheet) => {
    const located = locateColumns(g);
    if (!located) { if (!sawHeaders.length) sawHeaders = (g.find((r) => r.filter((c) => cellText(c)).length >= 3) || []).map(cellText).filter(Boolean).slice(0, 8); return; }
    const parsed = rowsFromGrid(g, located);
    if (!best || parsed.rows.length > best.rows.length) best = { ...parsed, located, sheet, n: parsed.rows.length };
  });
  if (!best) {
    throw new StatementError("No header row with a Units column and a fund name, ISIN or AMFI code was found." + (sawHeaders.length ? ` The first row with several columns reads: ${sawHeaders.join(" | ")}.` : "")
      + " Use a holdings statement that has columns such as Scheme Name, Folio No, Units, Invested Amount and Current Value.");
  }
  const b = best as ParsedSheet & { n: number };
  if (!b.rows.length) throw new StatementError("The header was found but there are no fund rows under it.");
  if (b.rows.length > MAX_ROWS) throw new StatementError(`The file has ${b.rows.length.toLocaleString("en-IN")} rows; up to ${MAX_ROWS.toLocaleString("en-IN")} can be imported at once. Split the file and import it in parts.`);
  return { rows: b.rows, headers: b.located.headers, skippedBlank: b.skippedBlank, skippedTotal: b.skippedTotal, sheets: grids.length };
}

/** Read a chosen file (xlsx, xls, csv, tsv, txt, or an HTML table saved as .xls) into rows ready for the preview request. */
export async function statementFromFile(file: File): Promise<Statement> {
  return statementFromGrids(await gridsFromFile(file));
}
