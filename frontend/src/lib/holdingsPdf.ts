/** Reading a holdings statement saved as a PDF (a broker's holdings report, a depository statement, a contract-note summary).
 *  The PDF is read in the browser (pdf.js, loaded only when a PDF is chosen): the file and its password never leave the device.
 *  Only the names of listed companies are taken. Accuracy comes first, so:
 *   - a company is accepted only when its text equals a listed ticker, code or full name (a name that merely starts the same way is marked "close");
 *   - text pieces become rows of cells by position; a heading row (Stock / Symbol / Scrip / Security ... plus Qty / Price / Value ...) opens a table;
 *   - a name wrapped over 2-5 lines (numbers on the first, middle or last line) is put back together by position, choosing the way that gives listed names;
 *     a line left over next to a complete name casts doubt on it ("Tata Motors" + "Finance Ltd" is not Tata Motors);
 *   - ISINs written inside the name cell are split off; mutual fund, ETF, bond and G-sec lines (ISIN INF / IN0, or under a Mutual Funds / Bonds heading) are skipped;
 *   - several tables: only a table headed Holdings / Portfolio / Demat is used; tables headed or labelled sold / trades / realised / transactions / dividends are
 *     ignored; if none is headed Holdings, the one table not marked as sold is used; if still unclear, everything is shown unticked (see `findHoldingsInRows`);
 *   - when there is no table, a name at the start of a line that carries an amount is found in the text, always unticked ("scan");
 *   - the page then shows every match next to the PDF's own words, so the person confirms before anything is added; only `isSure` finds are ticked.
 *  A scanned PDF (a photo of paper) holds no text and cannot be read (no OCR): say so instead of guessing. */
import type { SearchRow } from "./api";
import { SPLIT_NAMES } from "./aliases";
import { plausibleName, tidy, type Grid } from "./holdingsFile";
import { makeLookup, makeMatcher, matchNames, type Found } from "./holdingsMatch";

export type PdfItem = { str: string; x: number; y: number; w: number; h: number };
export const PDF_MAX_BYTES = 10_000_000;
const MAX_PAGES = 80;

export class PdfPasswordError extends Error { constructor(public wrong: boolean) { super(wrong ? "That password is not correct." : "This PDF is password protected."); } }
export class PdfNoTextError extends Error { constructor() { super("This PDF has no text to read (it looks like a scan or a photo). Download the Excel or CSV version of the statement from your broker, or paste the names."); } }
export class PdfReadError extends Error { constructor() { super("That PDF could not be read. Download the statement again, or use its Excel or CSV version."); } }

/* ------------------------------------------------------------------ text pieces to rows of cells */

const median = (v: number[]) => { const s = [...v].sort((a, b) => a - b); return s.length ? s[s.length >> 1] : 0; };

/** A cell of text with where it sits on the page; `isin` is the ISIN that was written inside the cell ("INE002A01018 RELIANCE INDUSTRIES LIMITED"). */
export type PdfCell = { t: string; x0: number; x1: number; isin?: string };
/** One line of the page: cells left to right, the baseline (y), the text height and the page number. */
export type PdfRow = { cells: PdfCell[]; y: number; h: number; page: number };

const NUM_PIECE = /^\s*\d[\d,.]*\s*$/;

/** Pieces of text with positions (one array per page) into rows of cells: pieces on the same baseline form a row, and a gap wider than about
 *  half a character height starts a new cell (table columns are at least a cell padding apart, a space inside a name is about a quarter), so a table's columns come out as cells and a name's words stay together. A number that follows a name
 *  closely (a right-aligned quantity touching the name column) is still its own cell. */
export function rowsFromPdfItems(pages: PdfItem[][]): PdfRow[] {
  const out: PdfRow[] = [];
  pages.forEach((items, page) => {
    const live = items.filter((i) => i.str.trim() !== "" && Number.isFinite(i.x) && Number.isFinite(i.y));
    if (!live.length) return;
    const hs = live.map((i) => i.h).filter((h) => h > 0);
    const tol = Math.max(1.5, median(hs) * 0.5);
    const sorted = [...live].sort((a, b) => b.y - a.y || a.x - b.x);
    const lines: PdfItem[][] = [];
    for (const it of sorted) {
      const line = lines[lines.length - 1];
      if (line && Math.abs(line[0].y - it.y) <= tol) line.push(it); else lines.push([it]);
    }
    for (const line of lines) {
      line.sort((a, b) => a.x - b.x);
      const cells: PdfCell[] = [];
      let cur: PdfCell | null = null, end = -Infinity, h = 0;
      for (const it of line) {
        const size = Math.max(it.h, h, 6), gap = it.x - end;
        if (cur && (gap > size * 0.5 || (NUM_PIECE.test(it.str) && /[A-Za-z]/.test(cur.t) && gap > size * 0.1))) { cur.t = cur.t.trim(); cells.push(cur); cur = null; }
        if (!cur) cur = { t: it.str, x0: it.x, x1: it.x + it.w };
        else { cur.t += (gap > size * 0.12 && !/\s$/.test(cur.t) && !/^\s/.test(it.str) ? " " : "") + it.str; cur.x1 = it.x + it.w; }
        end = it.x + it.w; h = it.h;
      }
      if (cur) { cur.t = cur.t.trim(); cells.push(cur); }
      const kept = cells.filter((c) => c.t);
      if (kept.length) out.push({ cells: kept, y: line[0].y, h: Math.max(median(line.map((i) => i.h).filter((x) => x > 0)), 1), page });
    }
  });
  return out;
}

/** Rows of cell texts only (what the spreadsheet reader works with). */
export function gridFromPdfItems(pages: PdfItem[][]): Grid { return rowsFromPdfItems(pages).map((r) => r.cells.map((c) => c.t)); }

/** A company name that wrapped onto a second line in a narrow column ("Tata Consultancy" / "Services Ltd") is joined back to one cell,
 *  but only when the joined text IS a listed company and neither half is. (findHoldings does this with positions; this is the grid-only version.) */
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

/* ------------------------------------------------------------------ what a row is */

const isIsin = (s: string) => /^IN[EF0-9][A-Z0-9]{8}\d$/.test(s) && (s.match(/\d/g) || []).length >= 4;
const stripCur = (s: string) => s.trim().replace(/^(rs\.?|inr|₹)\s*/i, "").replace(/\s*(cr|dr)\.?$/i, "");
/** 17,751.25  1200  (3.5)  -12.5%  ₹1,200: an amount or a quantity (not a date, not a code). */
const isNum = (s: string) => /^[(\-+]?\s*\d[\d,]*(\.\d+)?\s*%?\s*\)?$/.test(stripCur(s));
const hasAlpha = (s: string) => /[A-Za-z]/.test(s);
const PAGE_MARK = /^page\s*\d+(\s*(of|\/)\s*\d+)?$/i;
const H_NAME = /^(symbol|trading ?symbol|ticker|scrip|stock|share|instrument|security|isin|company|name|scheme)\b/i;
const H_OTHER = /^(qty|quantity|units?|avg|average|price|ltp|cmp|cur|current|value|val|p ?& ?l|pnl|profit|loss|net chg|day chg|change|chg|buy|sell|cost|closing|invested|market|mkt|returns?|unrealised|realised|amount|balance|bal|free|pledged?|lent|nav|rate|gain|total|sold|collateral|t ?\+ ?\d|%)/i;
const MONEY = /\b\d{1,3}(,\d{2,3})+(\.\d+)?\b|\b\d+\.\d{2}\b/;   // 29,001.00  1,64,000  2900.10: an amount, not a year or a phone number
const LABEL_ONLY = /^(and|of|the|ltd|limited|india|indian|bank|banks|fund|funds|group|global|power|steel|gas|oil|life|home|motors|capital|energy|finance|industries|services|systems|technologies|holdings|total|net|cash|equity|unit|units|date|name|folio|scheme|price|value|amount|balance|nav)$/i;

/** Tables are told apart by what is written above them or in their column headings. Strong words beat "holdings"; funds and bonds are weak. */
const T_OTHER = /\b(sold|sales?|sell(ing)?|realis(ed|ation)|realiz(ed|ation)|booked|trades?|trading|transactions?|orders?|contract notes?|bought|purchas(es|ed)|dividends?|corporate actions?|ipo|watch ?list|history|expired|ledger|brokerage|charges|profit and loss|p ?& ?l statement|pending)\b/i;
const T_HOLD = /\b(holdings?|portfolio|demat|stocks? held|shares held|securities held|closing balance|equity shares|equity statement|current (equity|stocks?|investments?))\b/i;
const T_WEAK = /\b(mutual funds?|folios?|bonds?|debentures?|ncd|g-?sec|government securities|sgb|nps|etfs?|schemes?)\b/i;
const T_HEAD_SOLD = /\b(sold|sell(ing)?|sale|exit)\b/i;
const SEC_NON = /\b(mutual funds?|bonds?|debentures?|g-?sec|government securit\w*|sovereign gold|sgb|ncds?|t-?bills?|commercial papers?|units held)\b/i;
const SEC_EQ = /\b(equity|equities|shares|stocks?)\b/i;
type TableClass = "hold" | "other" | "unknown";

const isHeaderRow = (r: PdfRow) => r.cells.length >= 2 && !r.cells.some((c) => isNum(c.t)) && r.cells.some((c) => H_NAME.test(c.t.trim())) && r.cells.some((c) => H_OTHER.test(c.t.trim()));
const isChrome = (r: PdfRow) => r.cells.length <= 2 && r.cells.some((c) => PAGE_MARK.test(c.t.trim()));

/** Splits an ISIN written inside a cell off the name. */
function withIsin(c: PdfCell): PdfCell {
  const w = c.t.split(/\s+/);
  if (w.length > 1 && isIsin(w[0])) return { ...c, t: w.slice(1).join(" "), isin: w[0] };
  if (w.length > 1 && isIsin(w[w.length - 1])) return { ...c, t: w.slice(0, -1).join(" "), isin: w[w.length - 1] };
  return isIsin(c.t) ? { ...c, isin: c.t } : c;
}

function classify(heading: string, header: string): TableClass {
  if (T_HEAD_SOLD.test(header)) return "other";
  for (const text of [heading, header]) {
    if (T_OTHER.test(text)) return "other";
    if (T_HOLD.test(text)) return "hold";
  }
  return T_WEAK.test(heading) ? "other" : "unknown";
}

type Kind = "num" | "frag" | "other" | "total" | "skipSec" | "eqSec";
const kindOf = (r: PdfRow): Kind => {
  const first = r.cells[0].t.trim();
  if (/^(grand |sub |page |net )?total\b/i.test(first)) return "total";
  if (r.cells.some((c) => isNum(c.t))) return "num";
  if (r.cells.every((c) => H_OTHER.test(c.t.trim()) || H_NAME.test(c.t.trim()))) return "other";   // a heading that wrapped onto a second line
  if (r.cells.length === 1 && first.length <= 50 && !/\d/.test(first) && first.split(/\s+/).length <= 6) {
    if (SEC_NON.test(first)) return "skipSec";
    if (first === first.toUpperCase() && SEC_EQ.test(first)) return "eqSec";
  }
  return hasAlpha(first) && first.length <= 60 && first.split(/\s+/).length <= 8 && !/[:]\s*$/.test(first) && !/^(note|disclaimer|source|statement|client|pan|address|dp|bo|folio)\b/i.test(first) ? "frag" : "other";
};

/* ------------------------------------------------------------------ names in the rows */

export type PdfFound = Found & { unsure?: string };
export type PdfFinds = { found: PdfFound[]; missing: string[]; mode: "table" | "text"; rows: number; notes: string[] };
/** Whether a find may be ticked without asking: an exact name, ticker, code or retired ticker, and nothing in the statement that casts doubt on it. */
export const isSure = (f: PdfFound) => (f.how === "exact" || f.how === "alias" || f.how === "split") && !f.unsure;

type Rec = { row: PdfRow; own?: PdfCell; skip: boolean; name: string; isin?: string; others: string[]; doubt?: string };
type Table = { cls: TableClass; heading: string; recs: Rec[]; rows: PdfRow[]; above: Set<string> };

/** The records of one table (one record per line that carries numbers), with wrapped names put back together. For every candidate name column the
 *  best way of giving the wrapped lines to the records above and below is chosen by how many records then name a listed company. */
function recordsOf(region: PdfRow[], grade: (name: string) => number): Rec[] {
  const kinds = region.map(kindOf);
  const href = Math.max(6, median(region.map((r) => r.h)));
  const nearD = href * 1.75;
  const idx: number[] = []; let skipping = false; const skipAt = new Set<number>();
  kinds.forEach((k, i) => { if (i && region[i].page !== region[i - 1].page) skipping = false;   // a new page: the fund / bond section may have ended (the ISIN check still guards)
    if (k === "skipSec") skipping = true; else if (k === "eqSec") skipping = false; else if (k === "num") { idx.push(i); if (skipping) skipAt.add(i); } });
  if (!idx.length) return [];
  const namey = (c: PdfCell) => hasAlpha(c.t) && !(c.isin && c.t === c.isin) && !isNum(c.t);
  // candidate name columns: x positions where the text cells of the records (and their wrapped lines) start
  const xs: number[] = [];
  region.forEach((r, i) => { if (kinds[i] === "num" || kinds[i] === "frag") r.cells.forEach((c) => { if (namey(c)) xs.push(c.x0); }); });
  xs.sort((a, b) => a - b);
  const clusters: { x: number; n: number }[] = [];
  for (const x of xs) { const c = clusters[clusters.length - 1]; if (c && x - c.x <= 2.5) { c.x = (c.x * c.n + x) / (c.n + 1); c.n++; } else clusters.push({ x, n: 1 }); }
  const need = Math.max(2, Math.ceil(idx.length * 0.25));
  const cands = clusters.filter((c) => c.n >= need).sort((a, b) => b.n - a.n).slice(0, 4);
  if (!cands.length) return [];
  let best: { score: number; recs: Rec[] } | null = null;
  for (const cl of cands) {
    const at = (r: PdfRow) => r.cells.find((c) => namey(c) && Math.abs(c.x0 - cl.x) <= 2.5);
    const eligible = (j: number, from: number) => kinds[j] === "frag" && !!at(region[j]) && region[j].page === region[from].page && Math.abs(region[j].y - region[from].y) <= nearD;
    // chains of wrapped lines that follow (tail) or precede (head) each record
    const tail: number[][] = [], head: number[][] = [];
    for (const i of idx) {
      const t: number[] = []; let from = i;
      for (let j = i + 1; j < region.length && eligible(j, from) && t.length < 5; j++) { t.push(j); from = j; }
      const h: number[] = []; from = i;
      for (let j = i - 1; j >= 0 && eligible(j, from) && h.length < 5; j--) { h.unshift(j); from = j; }
      tail.push(t); head.push(h);
    }
    const n = idx.length;
    const text = (r: PdfRow) => at(r)?.t || "";
    const assemble = (k: number, h: number, t: number) => {
      const own = at(region[idx[k]]);
      const parts = [...head[k].slice(head[k].length - h).map((j) => text(region[j])), own?.t || "", ...tail[k].slice(0, t).map((j) => text(region[j]))].filter(Boolean);
      const spaced = parts.join(" ").replace(/\s+/g, " ").trim();
      if (parts.length < 2 || parts.length > 5 || grade(spaced) >= 3) return spaced;
      // a long word that was broken at the end of a line ("TECHNOL" / "OGIES"): try gluing some of the joins
      for (let mask = 1; mask < 1 << (parts.length - 1); mask++) {
        const glued = parts.reduce((acc, p, i) => (i === 0 ? p : acc + (mask & (1 << (i - 1)) ? "" : " ") + p), "");
        if (grade(glued) >= 3) return glued;
      }
      return spaced;
    };
    const val = (k: number, h: number, t: number) => (skipAt.has(idx[k]) ? 0 : grade(assemble(k, h, t))) * 1e6 + t;
    // gap between record k and k+1: tail chain of k and head chain of k+1 may overlap; used lines count once
    const unused = (k: number, t: number, h: number) => {
      const used = new Set<number>([...tail[k].slice(0, t), ...(k + 1 < n ? head[k + 1].slice(head[k + 1].length - h) : [])]);
      const all = new Set<number>([...tail[k], ...(k + 1 < n ? head[k + 1] : [])]);
      return all.size - used.size;
    };
    const ok = (k: number, t: number, h: number) => k + 1 >= n || ![...tail[k].slice(0, t)].some((j) => head[k + 1].slice(head[k + 1].length - h).includes(j));
    // dynamic programme over records; state = how many head lines record k took
    type St = { v: number; prev: number; t: number };
    let f: (St | null)[] = Array.from({ length: head[0].length + 1 }, (_, h) => ({ v: -(head[0].length - h) * 1e3, prev: -1, t: 0 }));
    const trace: (St | null)[][] = [];
    for (let k = 0; k < n; k++) {
      const g: (St | null)[] = Array.from({ length: (k + 1 < n ? head[k + 1].length : 0) + 1 }, () => null);
      for (let h = 0; h < f.length; h++) {
        const cur = f[h]; if (!cur) continue;
        for (let t = 0; t <= tail[k].length; t++) for (let h2 = 0; h2 < g.length; h2++) {
          if (!ok(k, t, h2)) continue;
          const v = cur.v + val(k, h, t) - unused(k, t, h2) * 1e3;
          if (!g[h2] || v > g[h2]!.v) g[h2] = { v, prev: h, t };
        }
      }
      trace.push(f); f = g;
    }
    // walk back
    const hs: number[] = new Array(n), ts: number[] = new Array(n);
    let cur = f[0]!;
    for (let k = n - 1; k >= 0; k--) { ts[k] = cur.t; hs[k] = cur.prev; cur = trace[k][cur.prev]!; }
    // wrapped lines nobody took, next to a record whose name is complete as it stands: the name may have been cut. Each such line belongs to the record it is nearer to.
    const doubtful = new Set<number>();
    const usedLines = new Set<number>();
    for (let k = 0; k < n; k++) { tail[k].slice(0, ts[k]).forEach((j) => usedLines.add(j)); head[k].slice(head[k].length - hs[k]).forEach((j) => usedLines.add(j)); }
    for (let k = 0; k < n; k++) for (const j of [...tail[k], ...head[k]]) if (!usedLines.has(j)) {
      const d = (kk: number) => Math.abs(region[idx[kk]].y - region[j].y) + (region[idx[kk]].page === region[j].page ? 0 : 1e6);
      let near = k; if (k + 1 < n && d(k + 1) < d(near)) near = k + 1; if (k > 0 && d(k - 1) < d(near)) near = k - 1;
      doubtful.add(near);
    }
    const recs: Rec[] = idx.map((i, k) => {
      const row = region[i], own = at(row);
      const rest = row.cells.filter((c) => c !== own && namey(c)).map((c) => c.t);
      const isin = row.cells.find((c) => c.isin)?.isin;
      const r: Rec = { row, own, skip: skipAt.has(i), name: assemble(k, hs[k], ts[k]), isin, others: rest };
      if (doubtful.has(k)) r.doubt = "The line next to it in the statement is not part of the name, or the name was cut: please check";
      return r;
    });
    const score = recs.reduce((s, r) => s + (r.skip ? 0 : grade(r.name)), 0);
    if (!best || score > best.score) best = { score, recs };
  }
  return best ? best.recs : [];
}

/** Companies in a PDF's rows. Table first: the table's name column is the one whose cells are listed companies, wrapped names are put back together
 *  by position, and when a statement holds several tables only the holdings table is used (see `chooseTables`). When there is no table, whole company
 *  names at the start of rows that also carry an amount are found in the text, each marked "scan" (never ticked). */
export function findHoldingsInRows(rowsIn: PdfRow[], index: SearchRow[]): PdfFinds {
  const notes: string[] = [];
  if (!rowsIn.length || !index.length) return { found: [], missing: [], mode: "table", rows: rowsIn.length, notes };
  const { exact, find, norm } = makeLookup(index);
  const matcher = makeMatcher(index)!;
  const rows = rowsIn.filter((r) => !isChrome(r)).map((r) => ({ ...r, cells: r.cells.map(withIsin) }));
  const graded = new Map<string, number>();     // the wrapped-name search asks about the same text again and again
  const grade = (name: string) => {
    let g = graded.get(name);
    if (g === undefined) { const t = tidyName(name, matcher); g = exact(t) || SPLIT_NAMES[t.toUpperCase().replace(/\s+/g, " ")] ? 3 : find(t) ? 1 : 0; graded.set(name, g); }
    return g;
  };

  // tables: every heading row opens one, the lines up to the next heading row belong to it
  const heads = rows.map((r, i) => (isHeaderRow(r) ? i : -1)).filter((i) => i >= 0);
  const tables: Table[] = [];
  const sig = (r: PdfRow) => r.cells.map((c) => c.t.trim().toLowerCase()).join("|");
  if (heads.length) {
    heads.forEach((h, n) => {
      const end = n + 1 < heads.length ? heads[n + 1] : rows.length;
      const above: string[] = [];
      for (let j = h - 1; j >= 0 && above.length < 4 && rows[j].page === rows[h].page && !rows[j].cells.some((c) => isNum(c.t)) && !isHeaderRow(rows[j]); j--) above.push(rows[j].cells.map((c) => c.t).join(" "));
      // the nearest line that says what kind of table it is decides
      const heading = above.find((a) => T_OTHER.test(a) || T_HOLD.test(a) || T_WEAK.test(a)) || "";
      let cls = classify(heading, rows[h].cells.map((c) => c.t).join(" "));
      const prev = tables[tables.length - 1];
      const lines = above.map((a) => a.toLowerCase());
      // the same table continuing on the next page: same column headings, and only the lines that were above the table before (the page's running title)
      const same = !!prev && sig(prev.rows[0]) === sig(rows[h]);
      const continuing = same && cls === "unknown" && lines.every((a) => prev.above.has(a));
      if (continuing) cls = prev.cls;
      const body = rows.slice(h + 1, end);
      if (same && cls === prev.cls && (continuing || cls !== "unknown")) { prev.rows.push(rows[h], ...body); lines.forEach((a) => prev.above.add(a)); }
      else tables.push({ cls, heading, recs: [], rows: [rows[h], ...body], above: new Set(lines) });
    });
  } else tables.push({ cls: "unknown", heading: "", recs: [], rows, above: new Set() });
  for (const t of tables) t.recs = recordsOf(t.rows.slice(heads.length ? 1 : 0), grade).filter((r) => !r.skip);

  // match each table's records
  const names = new Set<string>();
  const nameOf = new Map<Rec, string>();
  for (const t of tables) for (const r of t.recs) { const n = tidyName(r.name, matcher); nameOf.set(r, n); if (n) names.add(n); }
  const matched = matchNames([...names], index);
  const byInput = new Map<string, Found[]>();
  for (const f of matched.found) byInput.set(f.input, [...(byInput.get(f.input) || []), f]);
  const missingSet = new Set(matched.missing);

  type TableFinds = { table: Table; found: PdfFound[]; missing: string[] };
  const results: TableFinds[] = tables.map((table) => {
    const found: PdfFound[] = [], missing: string[] = [];
    for (const r of table.recs) {
      const n = nameOf.get(r)!;
      const hits = byInput.get(n);
      if (!hits) { if (n && missingSet.has(n) && plausibleName(n) && !LABEL_ONLY.test(n.trim())) missing.push(n); continue; }
      let doubt = r.doubt && hits.every((h) => h.how === "exact" || h.how === "alias" || h.how === "split") ? r.doubt : undefined;
      const t = r.isin?.slice(7, 9);
      if (r.isin && /^IN[F0]/.test(r.isin) && !r.isin.startsWith("INE")) continue;                         // a mutual fund unit or a government security, not a share
      if (r.isin?.startsWith("INE") && t !== "01") doubt = doubt || `Its ISIN ${r.isin} is not an equity share's (type ${t}): a bond or another security of the company? Please check`;
      for (const h of hits) {
        let u = doubt;
        if (!u && h.how === "close") {                       // a name that only starts like a company: say how many companies start that way
          const key = norm(tidy(n)), many = index.filter((r) => norm(r[1]).startsWith(key + " ") || norm(r[1]) === key);
          if (many.length > 1) u = `${many.length} companies start with this name (${many.slice(0, 3).map((r) => r[0]).join(", ")}${many.length > 3 ? ", ..." : ""}): please check which one`;
        }
        if (!u && h.how === "split" && !/^TATAMOTORS$/i.test(n)) u = "Tata Motors was split in two: this name could be either part. Please check which you hold";
        if (!u) { const other = r.others.map((o) => exact(tidyName(o, matcher))).find((x) => x && x[0] !== h.symbol); if (other && h.how !== "split") u = `Another column of this line says ${other[0]}: please check`; }
        found.push(u ? { ...h, unsure: u } : { ...h });
      }
    }
    return { table, found: dedupe(found), missing };
  });

  const withFinds = results.filter((r) => r.found.length);
  const hold = withFinds.filter((r) => r.table.cls === "hold"), unknown = withFinds.filter((r) => r.table.cls === "unknown"), other = withFinds.filter((r) => r.table.cls === "other");
  let chosen: TableFinds[], why: string | undefined;
  if (hold.length) { chosen = hold; if (withFinds.length > hold.length) notes.push(`This statement has more than one table. Only the table headed like "${hold[0].table.heading.trim() || "Holdings"}" is used; the other ${withFinds.length - hold.length === 1 ? "table (" : "tables ("}${[...unknown, ...other].map((r) => r.table.heading.trim() || "untitled").join(", ")}) ${withFinds.length - hold.length === 1 ? "is" : "are"} ignored.`); }
  else if (unknown.length === 1) { chosen = unknown; if (other.length) notes.push(`Only the table that is not headed as sold or traded shares is used (${other.map((r) => r.table.heading.trim() || "untitled").join(", ")} ignored).`); }
  else if (unknown.length > 1) { chosen = [...unknown, ...other]; why = "This statement has several tables and none is headed Holdings or Portfolio, so it cannot be told which one lists what you hold: please check"; }
  else { chosen = other; why = "This table is headed as sold, traded or fund lines, not as your holdings: please check"; }
  if (why) notes.push(why);
  const found = dedupe(chosen.flatMap((r) => r.found.map((f) => (why && !f.unsure ? { ...f, unsure: why } : f))));
  const missing = [...new Set(chosen.flatMap((r) => r.missing))];
  if (found.length) return { found, missing, mode: "table", rows: rowsIn.length, notes };
  return { ...textFinds(rows, exact), rows: rowsIn.length, notes: [...notes, ...(notes.length ? [] : [])], missing: [] };
}

/** "RELIANCE-EQ", "TCS - EQ", "HDFCBANK.NS", and a quantity that was glued to the name ("Infosys Ltd 30"): the name only. */
function tidyName(s: string, matcher: (n: string) => boolean): string {
  const t = tidy(s);
  const key = t.toUpperCase().replace(/[.,]+$/, "").replace(/\s+/g, " ");
  if (SPLIT_NAMES[key]) return key;                 // "Tata Motors Ltd." is the split company, with or without the full stop
  if (matcher(t)) return t;
  const m = /^(.*[A-Za-z.)&])\s*[\d,.]+$/.exec(t);
  return m && matcher(tidy(m[1])) ? tidy(m[1]) : t;
}

/** No table: a holding line starts with the company's name and goes on with an amount ("1. Infosys Ltd 25 shares @ Rs. 1,450.00"). A name inside a sentence
 *  is not a holding. A statement that is only a list of names is returned too. All of these are marked "scan" and are never ticked. */
function textFinds(rows: PdfRow[], exact: (s: string) => SearchRow | undefined): PdfFinds {
  const seen = new Map<string, PdfFound>();
  const add = (phrase: string, hit: SearchRow, why: string) => { if (!seen.has(hit[0])) seen.set(hit[0], { input: phrase, symbol: hit[0], name: hit[1], how: "scan", unsure: why }); };
  const AFTER = /^(worth|valued|at|bought|purchased|is|are|was|@)$/i;
  const UNIT = /^(shares?|qty|quantity|units?|nos\.?|@|x|-|–|:|isin)$/i;
  for (const row of rows) {
    if (!row.cells.some((c) => isNum(c.t) || MONEY.test(c.t))) continue;
    for (const cell of row.cells) {
      if (!hasAlpha(cell.t)) continue;
      const text = cell.t.replace(/^\(?\d{1,3}[.)]\s+/, "").replace(/^IN[EF0-9][A-Z0-9]{8}\d\s+/, "");
      const words = text.split(/\s+/).map((w) => w.replace(/[,;]+$/, ""));
      for (let i = 0; i < words.length; i++) {
        // a name starts the line ("1. Infosys Ltd 25 ..."), or follows "10 shares of" / "5 units in"
        if (i > 0 && !(/^(of|in)$/i.test(words[i - 1]) && /^(shares?|units?|stocks?|qty|quantity)$/i.test(words[i - 2] || ""))) continue;
        let hit: SearchRow | undefined, phrase = "";
        for (let len = Math.min(8, words.length - i); len >= 1 && !hit; len--) {
          phrase = words.slice(i, i + len).join(" ");
          const after = words[i + len];
          if (after !== undefined && !isNum(after) && !UNIT.test(after) && !AFTER.test(after)) continue;
          if (len === 1 && (phrase.length < 3 || LABEL_ONLY.test(phrase) || phrase !== phrase.toUpperCase() || isIsin(phrase))) continue;   // a lone ticker is written in capitals
          hit = exact(phrase);
        }
        if (hit) { add(phrase, hit, "Found in the text, not in a table: please check"); break; }
      }
    }
  }
  if (!seen.size) {
    for (const row of rows) if (row.cells.length === 1) { const hit = row.cells[0].t.split(/\s+/).length >= 2 ? exact(row.cells[0].t) : undefined; if (hit) add(row.cells[0].t, hit, "Listed by name only, with no quantity: please check"); }
  }
  return { found: [...seen.values()], missing: [], mode: "text", rows: rows.length, notes: [] };
}

/** Companies in a grid of cell texts (rows of columns, no positions): the same reading, with the cells laid out evenly. */
export function findHoldings(grid: Grid, index: SearchRow[]): PdfFinds {
  const rows: PdfRow[] = grid.filter((r) => r.length).map((r, i) => ({ cells: r.map((t, c) => ({ t, x0: c * 100, x1: c * 100 + 80 })), y: -i * 10, h: 8, page: 0 }));
  return findHoldingsInRows(rows, index);
}

function dedupe(found: PdfFound[]): PdfFound[] {
  const by = new Map<string, PdfFound>();
  for (const f of found) { const cur = by.get(f.symbol); if (!cur || score(f) < score(cur)) by.set(f.symbol, f); }
  return [...by.values()];
}
const rank = (h: Found["how"]) => ({ exact: 0, alias: 1, split: 1, close: 2, scan: 3 }[h]);
const score = (f: PdfFound) => (isSure(f) ? 0 : 10) + rank(f.how);

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
  return findHoldingsInRows(rowsFromPdfItems(await readPdfItems(file, password)), index);
}

export { tidy };
