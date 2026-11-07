// The refreshed dashboard's pure logic (no React): names and greeting, heat-map tile colours and labels, "results today" and "filings and news" cleaning, year-on-year
// figures, the phone tab memory and the Customise moves. Descriptive only; a figure that cannot be worked out is null and the page says why.
import type { FeedItem } from "./feed";
import type { DashTab, WidgetPref } from "./prefs";
import type { IndexRow } from "./indices";
import type { Row } from "./screener";
import { MAX_MOVE, largest } from "./markets";

// ---------------------------------------------------------------------------------------------------------------- greeting
const cap = (s: string) => (s ? s[0].toLocaleUpperCase("en-IN") + s.slice(1) : s);
/** The member's first name with a capital letter ("pranjal kumar" is "Pranjal"); the part of the email before the @ when no name was given; "" when neither exists. */
export function firstName(name?: string | null, email?: string | null): string {
  const n = (name || "").trim().split(/\s+/)[0] || "";
  if (n) return cap(n);
  const e = (email || "").split("@")[0].split(/[._+-]/)[0].replace(/\d+/g, "");
  return cap(e);
}
export const greetingWord = (hour: number) => (hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening");
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
/** "Sep 2026" or "4 Nov" from a YYYY-MM-DD date, always with the three-letter month ("Sept" is never used). */
export const monthYear = (iso: string) => `${MONTHS[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}`;
export const dayMonth = (iso: string, year = false) => `${+iso.slice(8, 10)} ${MONTHS[+iso.slice(5, 7) - 1]}${year ? " " + iso.slice(0, 4) : ""}`;
export const monthName = (iso: string) => MONTHS_LONG[+iso.slice(5, 7) - 1];
/** "Wednesday, 4 November" in Indian time. */
export const longDay = (d: Date = new Date()) => {
  const iso = d.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
  return `${d.toLocaleDateString("en-GB", { weekday: "long", timeZone: "Asia/Kolkata" })}, ${+iso.slice(8, 10)} ${monthName(iso)}`;
};
export const istHour = (d: Date = new Date()) => +d.toLocaleString("en-GB", { hour: "2-digit", hour12: false, timeZone: "Asia/Kolkata" }) % 24;
export const istToday = (d: Date = new Date()) => d.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

// ---------------------------------------------------------------------------------------------------------------- heat-map tiles
/** Seven tile colours, white text on each at 4.5:1 or better: <= -2%, -2 to -0.75, -0.75 to -0.1, flat (+-0.1), 0.1 to 0.75, 0.75 to 2, >= 2%. */
export const TILE_COLOURS = ["#8E2620", "#A12E26", "#B5473D", "#6B6455", "#2E7D57", "#1F6B49", "#17583B"] as const;
export const NO_PRICE_TILE = "#6B6455";
export function tileColour(change: number | null | undefined): string {
  if (change == null || !Number.isFinite(change)) return NO_PRICE_TILE;
  if (change <= -2) return TILE_COLOURS[0];
  if (change < -0.75) return TILE_COLOURS[1];
  if (change < -0.1) return TILE_COLOURS[2];
  if (change <= 0.1) return TILE_COLOURS[3];
  if (change < 0.75) return TILE_COLOURS[4];
  if (change < 2) return TILE_COLOURS[5];
  return TILE_COLOURS[6];
}
const lin = (c: number) => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
const lum = (hex: string) => { const n = parseInt(hex.replace("#", ""), 16); return 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255); };
/** WCAG contrast ratio of two #rrggbb colours. */
export const contrast = (a: string, b: string) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

export type TileLabel = { size: 11 | 13 | 16; pct: boolean } | null;
/** What a tile of w x h pixels says: the ticker at 16px on big tiles, 13px, or 11px at the least; the move (12px) under it when the height allows. null = no label at all (the hover or tap card names the tile), never a smaller font. */
export function tileLabel(ticker: string, w: number, h: number): TileLabel {
  const fits = (size: number) => ticker.length * size * 0.68 + 12 <= w;     // bold capitals run about 0.68 of the font size per letter
  const size = w >= 150 && h >= 84 && fits(16) ? 16 : h >= 30 && fits(13) ? 13 : h >= 18 && fits(11) ? 11 : null;
  if (!size) return null;
  return { size, pct: h >= size + 12 + 16 && w >= 56 };
}

// ---------------------------------------------------------------------------------------------------------------- year on year
/** Latest quarter against the same quarter a year earlier. `base <= 0` has no meaningful percentage (a loss a year ago), and a gap that is not about a year (a missing quarter) is refused. */
export function yoyOf(values: (number | null)[] | undefined, ends: string[] | undefined): { pct: number | null; reason: string | null } {
  const n = values?.length ?? 0;
  if (!values || !ends || n < 5) return { pct: null, reason: "Fewer than five quarters reported" };
  const a = values[n - 1], b = values[n - 5];
  const gap = (Date.parse(ends[n - 1]) - Date.parse(ends[n - 5])) / 864e5;
  if (!(gap > 330 && gap < 400)) return { pct: null, reason: "The year-ago quarter is missing" };
  if (a == null || b == null) return { pct: null, reason: "Not reported" };
  if (b <= 0) return { pct: null, reason: "Not meaningful: the year-ago figure was zero or a loss" };
  return { pct: ((a - b) / b) * 100, reason: null };
}
/** What to show for a quarter against the same quarter a year earlier, in words when a percentage means nothing. A percentage change needs a positive year-ago figure; when
 *  that was a loss the figures still say something real, so they are shown as words (never a blank with the reason hidden): "Turned profit", "Turned loss",
 *  "Loss narrowed" or "Loss widened". tone: up / down / flat for the colour. */
export function yoyLabel(values: (number | null)[] | undefined, ends: string[] | undefined): { text: string | null; pct: number | null; tone: "up" | "down" | "flat"; reason: string | null } {
  const y = yoyOf(values, ends);
  if (y.pct != null) return { text: null, pct: y.pct, tone: y.pct > 0 ? "up" : y.pct < 0 ? "down" : "flat", reason: null };
  const n = values?.length ?? 0;
  if (!values || !ends || n < 5 || !/loss/.test(y.reason || "")) return { text: null, pct: null, tone: "flat", reason: y.reason };
  const a = values[n - 1], b = values[n - 5];
  if (a == null || b == null) return { text: null, pct: null, tone: "flat", reason: y.reason };
  if (a > 0 && b <= 0) return { text: "Turned profit", pct: null, tone: "up", reason: "A profit this quarter against a loss a year earlier" };
  if (a < 0 && b === 0) return { text: "Turned loss", pct: null, tone: "down", reason: "A loss this quarter against no profit a year earlier" };
  if (a < 0 && b < 0) return a > b ? { text: "Loss narrowed", pct: null, tone: "up", reason: "A smaller loss than the same quarter a year earlier" }
    : a < b ? { text: "Loss widened", pct: null, tone: "down", reason: "A bigger loss than the same quarter a year earlier" } : { text: "Loss unchanged", pct: null, tone: "flat", reason: "The same loss as a year earlier" };
  return { text: null, pct: null, tone: "flat", reason: y.reason };
}
/** "Sep 2026" from a quarter-end date. */
export const quarterEndLabel = (iso: string | undefined) => (iso ? monthYear(iso) : "");

// ---------------------------------------------------------------------------------------------------------------- results today
const quarterIn = (s: string) => { const m = /\bQ([1-4])\s*FY\s*'?(\d{2,4})\b/i.exec(s); return m ? `Q${m[1]} FY${m[2].slice(-2)}` : null; };
const isPress = (x: FeedItem) => /press release|media release/i.test(`${x.category || ""} ${x.title}`);
const mentionsResults = (s: string) => /results?\b/i.test(s);
export type ResultLine = { key: string; symbol: string | null; company: string | null; date: string; text: string };

/** One line per company per day, from the results feed. Kept: a results date, financial results, an "Outcome of Board Meeting" whose title mentions results, and a press release about results.
 *  Dropped: press releases and other filings that are not about results. */
export function resultLines(items: readonly FeedItem[]): ResultLine[] {
  const groups = new Map<string, { filed: boolean; meeting: boolean; press: boolean; period: string | null; it: FeedItem }>();
  for (const it of items) {
    const cat = (it.category || "").trim().toLowerCase(), t = it.title || "";
    const press = isPress(it);
    const filed = !press && (cat === "financial results" || cat === "financial result" || cat === "result" || cat === "results" || (cat.includes("outcome of board meeting") && mentionsResults(t)));
    const meeting = !press && !filed && (cat === "results date" || (/board meeting/i.test(`${cat} ${t}`) && mentionsResults(t)));
    const pressOk = press && mentionsResults(t);
    if (!filed && !meeting && !pressOk) continue;
    const key = `${it.symbol || it.company || it.title}|${it.date}`;
    const g = groups.get(key) ?? { filed: false, meeting: false, press: false, period: null, it };
    g.filed ||= filed; g.meeting ||= meeting; g.press ||= pressOk;
    g.period = g.period || it.period || quarterIn(t);
    groups.set(key, g);
  }
  return [...groups.entries()].map(([key, g]) => {
    const p = g.period ? `${g.period} results` : "Results";
    const text = g.filed && g.press ? `${p} and press release` : g.filed ? `${p} filed` : g.press && !g.meeting ? `${p} and press release` : "Board meets on results";
    return { key, symbol: g.it.symbol, company: g.it.company, date: g.it.date, text };
  }).sort((a, b) => a.date.localeCompare(b.date));
}

// ---------------------------------------------------------------------------------------------------------------- filings and news
export type FilingTag = "Results" | "Board" | "Capital" | "Dividend" | "Order" | "Corporate" | "Other";
const TAGS: [FilingTag, RegExp][] = [
  ["Results", /\b(financial results?|results?)\b/i],
  ["Board", /\b(directors?|kmp|key managerial|resignation|resigns?|appointment|appoints?)\b/i],
  ["Capital", /\b(call money|rights|allotment|buy-?back|split|bonus)\b/i],
  ["Dividend", /\b(dividend|record date)\b/i],
  ["Order", /\b(orders?|contracts?)\b/i],
  ["Corporate", /\b(agm|egm|moa|aoa|memorandum|articles of association|name change|change in name)\b/i],
];
export function filingTag(x: Pick<FeedItem, "category" | "title">): FilingTag {
  const s = `${x.category || ""} ${x.title || ""}`;
  for (const [tag, re] of TAGS) if (re.test(s)) return tag;
  return "Other";
}

const BOILERPLATE: RegExp[] = [
  /^.*? (Limited|Ltd\.?) has (informed|submitted to) the Exchange (regarding|about|that)? ?/i,
  /^.*? \( ?Company ?\)/i,
  /^Resignation:\s*/i,
];
/** The filing's own words in one line: the exchange's boilerplate stripped, a capital first letter, and at most about `max` characters, cut at a word boundary with an ellipsis (never mid-word). */
export function shorten(text: string | null | undefined, max = 110): string {
  let t = (text || "").replace(/\s+/g, " ").trim();
  for (const re of BOILERPLATE) { const r = t.replace(re, "").trim(); if (r.length >= 3) t = r; }
  t = t.replace(/^[\s:;,.\-–]+/, "");
  if (!t) return "";
  t = t[0].toLocaleUpperCase("en-IN") + t.slice(1);
  if (t.length <= max) return t;
  const cut = t.slice(0, max + 1), at = cut.lastIndexOf(" ");
  return cut.slice(0, at > 20 ? at : max).replace(/[\s,;:.\-–(]+$/, "") + "…";
}
export const filingLine = (x: Pick<FeedItem, "title" | "summary">) => shorten(x.summary || x.title);

/** The same company, the same day and the same kind of filing is shown once (the exchange often files one notice twice). */
export function dedupeFilings<T extends Pick<FeedItem, "symbol" | "company" | "date" | "category" | "title">>(items: readonly T[]): T[] {
  const seen = new Set<string>(), out: T[] = [];
  for (const x of items) {
    const kind = (x.category || "").trim().toLowerCase();
    const key = [x.symbol || x.company || "", x.date, kind && kind !== "general" ? kind : filingTag(x) + ":" + shorten(x.title, 40).toLowerCase()].join("|");
    if (seen.has(key)) continue;
    seen.add(key); out.push(x);
  }
  return out;
}

/** "Today", "Yesterday", "Tomorrow", or "4 Nov" (and the year when it is not this one). */
export function shortDay(iso: string, today: string): string {
  const d = Date.parse(iso + "T00:00:00Z"), t = Date.parse(today + "T00:00:00Z"), diff = Math.round((d - t) / 864e5);
  if (diff === 0) return "Today";
  if (diff === -1) return "Yesterday";
  if (diff === 1) return "Tomorrow";
  return dayMonth(iso, iso.slice(0, 4) !== today.slice(0, 4));
}

// ---------------------------------------------------------------------------------------------------------------- IPOs
/** "Opens Soon Ltd" cleaned to title case: a name in capitals ("ANTALA INDUSTRIES LTD") becomes "Antala Industries Ltd"; mixed-case names are left alone. */
export function titleCase(name: string): string {
  if (name !== name.toUpperCase()) return name;
  return name.toLowerCase().replace(/\b([a-z])([a-z]*)/g, (_m, a: string, b: string) => (/^(ltd|pvt|llp|ipo|sme)$/.test(a + b) ? (a + b).replace(/^./, (c) => c.toUpperCase()) : a.toUpperCase() + b));
}

// ---------------------------------------------------------------------------------------------------------------- phone tabs
const TAB_KEY = "finlit-dash-tab:";
const TABS: DashTab[] = ["stocks", "market", "news"];
/** The last phone tab this member used (per member, per browser); "stocks" when none is remembered. */
export function readTab(userId: string | null | undefined, store: Pick<Storage, "getItem"> | null = safeStore()): DashTab {
  try { const v = store?.getItem(TAB_KEY + (userId || "guest")); return TABS.includes(v as DashTab) ? (v as DashTab) : "stocks"; } catch { return "stocks"; }
}
export function writeTab(userId: string | null | undefined, tab: DashTab, store: Pick<Storage, "setItem"> | null = safeStore()): void {
  try { store?.setItem(TAB_KEY + (userId || "guest"), tab); } catch { /* private mode: the tab is simply not remembered */ }
}
function safeStore(): Storage | null { try { return typeof localStorage === "undefined" ? null : localStorage; } catch { return null; } }

// ---------------------------------------------------------------------------------------------------------------- Customise
/** Moves the block at `from` to the place of the block at `to` (drag and drop, and the up and down buttons, both use it). Returns a new list. */
export function moveBlock(list: readonly WidgetPref[], from: number, to: number): WidgetPref[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return [...list];
  const a = [...list];
  const [x] = a.splice(from, 1);
  a.splice(to, 0, x);
  return a;
}

// ---------------------------------------------------------------------------------------------------------------- market blocks

/** The seven index cards, in order, named in one case. `re` finds the row in /api/indices by its name. */
export const INDEX_TILES: { label: string; re: RegExp }[] = [
  { label: "Nifty 50", re: /^nifty 50$/i }, { label: "Sensex", re: /^(bse )?sensex$/i }, { label: "Nifty Bank", re: /^nifty bank$/i }, { label: "Nifty Midcap 100", re: /^nifty midcap 100$/i },
  { label: "Nifty Smallcap 100", re: /^nifty smallcap 100$/i }, { label: "Nifty IT", re: /^nifty it$/i }, { label: "India VIX", re: /^(india )?vix$/i },
];
export type IndexCard = { label: string; row: IndexRow | null };
export function pickIndices(items: readonly IndexRow[]): IndexCard[] {
  return INDEX_TILES.map((t) => ({ label: t.label, row: items.find((r) => t.re.test(r.name.replace(/\s+/g, " ").trim()) && r.close != null) ?? null }));
}

export type Scope = "n50" | "n500" | "all";
const traded = (r: Row) => r.price != null && r.price > 0 && r.change_pct != null;
/** The stocks the gainers and decliners are drawn from. Nifty 50 and Nifty 500 use the exchange's member lists; when a list is not loaded, Nifty 500 says so (empty) and Nifty 50 falls
 *  back to the 50 largest companies, with a note. "All stocks" leaves out companies under 100 crore and moves past 40%. */
export function scopeStocks(scope: Scope, rows: readonly Row[], members: Record<string, string[]> | undefined): { stocks: Row[]; note: string | null } {
  const by = () => new Map(rows.map((r) => [r.symbol, r]));
  if (scope === "all") return { stocks: rows.filter((r) => traded(r) && (r.market_cap ?? 0) >= 100 && Math.abs(r.change_pct as number) <= MAX_MOVE), note: null };
  const list = members?.[scope === "n50" ? "NIFTY50" : "NIFTY500"];
  if (list && list.length >= (scope === "n50" ? 20 : 100)) { const m = by(); return { stocks: list.map((s) => m.get(s)).filter((r): r is Row => !!r && traded(r)), note: null }; }
  if (scope === "n50") return { stocks: largest(rows, 50), note: "The exchange's Nifty 50 list is not loaded yet, so this shows the 50 largest companies by market value." };
  return { stocks: [], note: "The exchange's Nifty 500 list is not loaded yet." };
}
