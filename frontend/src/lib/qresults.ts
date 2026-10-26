// Quarter results: the rows the server sends (GET /api/results/quarter), the Telegram-style one-line summary, and the CSV.
// The server decides what a plan may see and whether a company's figures are for THIS quarter; this file only formats what it is sent.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ApiError, apiGet } from "./api";
import { MINUS, csvText, nf } from "./format";

export type QStatus = "declared" | "awaiting" | "due" | "missing";
export type QRow = {
  date: string; symbol: string; name: string; sector: string | null; marketCap: number | null; cap: "Large" | "Mid" | "Small" | null; indices: string[];
  confirmed: boolean; periodEnd: string; loadedPeriodEnd: string | null; status: QStatus; awaiting: boolean; hasNumbers: boolean; locked: boolean;
  revenue: number | null; revenueYoY: number | null; revenueQoQ: number | null; operatingProfit: number | null; opYoY: number | null; opQoQ: number | null; opYoYWhy: string | null; opQoQWhy: string | null; opm: number | null;
  netProfit: number | null; profitYoY: number | null; profitQoQ: number | null; npm: number | null; npmChange: number | null; eps: number | null;
  gap: number | null; flagged: boolean; loss: boolean;
  /** Where the figures come from: the stored full report, or the light table (a smaller company, one provider call). Null without figures. */
  source?: "full" | "light" | null; basis?: "consolidated" | "standalone" | null;
  /** For an awaiting row: "provider" = we asked and the data provider has not published the quarter yet; "ours" = our own report is still being updated. */
  awaitingWhy?: "provider" | "ours" | null;
};
export type QSummary = {
  companies: number; declared: number; due: number; awaiting: number; awaitingProvider?: number; awaitingOurs?: number; withNumbers: number; flagged: number | null;
  medianRevenueYoY: number | null; medianProfitYoY: number | null; profitUpShare: number | null; marginUpShare: number | null; nRevenue: number | null; nProfit: number | null; nMargin: number | null;
};
export type QInfo = { key: string; label: string; fiscal: string; periodEnd: string; from: string; to: string };
export type QResp = {
  plan: "basic" | "silver" | "gold"; locked: boolean; today: string; quarter: QInfo | null; quarters: (QInfo & { total: number; declared: number; due: number })[];
  total: number; offset: number; limit: number; summary: QSummary; totals: QSummary; rows: QRow[]; days: { date: string; n: number }[];
  facets: { sectors: { name: string; n: number }[]; indices: { code: string; n: number }[] }; gapFlag?: number; updatedAt?: string;
  dates?: QDates | null; dateMeaning?: string;
};
/** What the server found for a date filter, before the other filters: the quarters announced in range, the nearest days with results, what we hold. */
export type QDates = {
  from: string; to: string; single: boolean; inQuarter: boolean; quarters: { key: string; label: string; fiscal: string; n: number }[];
  nearest: { date: string; n: number }[]; coverage: { earliest: string | null; latest: string | null };
};
export type QParams = {
  quarter?: string; q?: string; sector?: string; cap?: string; index?: string; scope?: "all" | "watchlist" | "portfolio"; flagged?: boolean; status?: string;
  sort?: string; dir?: "asc" | "desc"; offset?: number; limit?: number;
  date?: string; from?: string; to?: string;   // the announcement date (one day) or a from-to range, India dates as YYYY-MM-DD
};

export const PAGE = 50;
export const GAP_FLAG = 15;
export const GAP_LABEL = "Profit and sales moved apart";

export const queryString = (p: QParams) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== "" && v !== false && !(k === "scope" && v === "all") && !(k === "offset" && v === 0)) u.set(k, String(v));
  return u.toString();
};

export const useQuarterResults = (p: QParams) => useQuery({
  queryKey: ["quarter-results", queryString(p)], staleTime: 60_000, retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 1, placeholderData: keepPreviousData,
  queryFn: () => apiGet<QResp>(`/api/results/quarter?${queryString({ limit: PAGE, ...p })}`),
});

/** The alert for this gap, ready to create: /alerts reads symbol, metric and value from the link. */
export const gapAlertLink = (symbol: string) => `/alerts?symbol=${encodeURIComponent(symbol)}&metric=rev_profit_gap&value=${GAP_FLAG}`;

// ------------------------------------------------------------ dates
// "Date" on this page means the day the company ANNOUNCED its results (the exchange filing's date, or the board-meeting date until the filing is out),
// as an Indian calendar date. Everything here works on plain YYYY-MM-DD text so the browser's own time zone can never move a day.
export const DATE_MEANING = "Date means the day the company announced (declared) its results: the date on its exchange filing, or its board-meeting date until the filing is out. All dates are Indian (IST) calendar dates.";
export const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

export const todayIST = (now: Date = new Date()) => now.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
export const isRealDay = (v: string) => ISO_DAY.test(v) && new Date(v + "T00:00:00Z").toISOString().slice(0, 10) === v;
export const addDays = (iso: string, n: number) => new Date(new Date(iso + "T00:00:00Z").getTime() + n * 86_400_000).toISOString().slice(0, 10);
const weekday = (iso: string) => new Date(iso + "T00:00:00Z").getUTCDay();   // 0 = Sunday
export const isWeekend = (iso: string) => weekday(iso) === 0 || weekday(iso) === 6;
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"], MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const weekdayName = (iso: string) => DAYS[weekday(iso)];
export const longDay = (iso: string) => `${DAYS[weekday(iso)].slice(0, 3)}, ${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`;   // fixed wording: the same in every browser
export const mondayOf = (iso: string) => addDays(iso, -((weekday(iso) + 6) % 7));
export const quarterStartOf = (iso: string) => `${iso.slice(0, 4)}-${String(Math.floor((Number(iso.slice(5, 7)) - 1) / 3) * 3 + 1).padStart(2, "0")}-01`;   // calendar quarter: Jan, Apr, Jul, Oct

export type DateSel = { date?: string; from?: string; to?: string };
export type DateChip = { id: string; label: string; sel: { date: string } | { from: string; to: string } };

/** The quick choices, worked out from today's Indian date. "This quarter" is the calendar quarter's announcements so far (1 Oct to today, in October). */
export const dateChips = (today: string): DateChip[] => [
  { id: "today", label: "Today", sel: { date: today } },
  { id: "yesterday", label: "Yesterday", sel: { date: addDays(today, -1) } },
  { id: "week", label: "This week", sel: { from: mondayOf(today), to: today } },
  { id: "last7", label: "Last 7 days", sel: { from: addDays(today, -6), to: today } },
  { id: "quarter", label: "This quarter", sel: { from: quarterStartOf(today), to: today } },
];

/** Which chip the current selection is exactly (so it can show as pressed). A single day that is also a one-day range counts as the same. */
export const activeChip = (sel: DateSel, today: string): string | null => {
  const from = sel.date || sel.from, to = sel.date || sel.to || (sel.from ? today : undefined);
  if (!from || !to) return null;
  for (const c of dateChips(today)) {
    const cf = "date" in c.sel ? c.sel.date : c.sel.from, ct = "date" in c.sel ? c.sel.date : c.sel.to;
    if (cf === from && ct === to) return c.id;
  }
  return null;
};

/** A plain-words problem with a date choice, or null when it is fine. The server checks the same rules; this only saves a round trip. */
export function dateProblem(sel: DateSel, today: string): string | null {
  const bad = (v?: string) => !!v && !isRealDay(v);
  if (bad(sel.date) || bad(sel.from) || bad(sel.to)) return "Enter a real date as day, month and year.";
  if (sel.to && !sel.from) return "Choose the from date as well as the to date.";
  const hi = [sel.date, sel.from, sel.to].filter(Boolean).sort().pop();
  if (hi && hi > today) return `Results can be looked up for dates up to today (${longDay(today)}, India time).`;
  if (sel.from && sel.to && sel.from > sel.to) return "The from date is after the to date.";
  return null;
}

/** The selection a page address carries (?date= or ?from=&to=). A single day wins over a range. */
export const dateFromParams = (sp: URLSearchParams): DateSel => {
  const date = sp.get("date") || "", from = sp.get("from") || "", to = sp.get("to") || "";
  return date ? { date } : from || to ? { from: from || undefined, to: to || undefined } : {};
};

export const describeSel = (sel: DateSel, today: string) =>
  sel.date ? `announced on ${longDay(sel.date)}` : sel.from ? (sel.from === (sel.to || today) ? `announced on ${longDay(sel.from)}` : `announced from ${longDay(sel.from)} to ${longDay(sel.to || today)}`) : "";

// ------------------------------------------------------------ text
const rs = (v: number) => `Rs${nf(Math.abs(v), 2)} CR`;
const dir = (v: number) => (v >= 0 ? "UP" : "DOWN");
const pc = (v: number) => `${Math.round(Math.abs(v))}%`;
const move = (v: number | null, tag: string) => (v == null ? null : `${dir(v)} ${pc(v)} (${tag})`);

/** One line in the style of a results alert channel:
 *  "DLF Q2 FY27: NET PROFIT UP 10% AT Rs1,260.58 CR (YOY), UP 3% (QOQ) / REVENUE DOWN 23% AT Rs... / OPM 20.1%, NPM 13.3% / EPS Rs2.20"
 *  Only what is known is said: a growth rate that cannot be worked out (the year-ago profit was a loss) is left out, never guessed. */
export function headline(r: Pick<QRow, "symbol" | "revenue" | "revenueYoY" | "revenueQoQ" | "netProfit" | "profitYoY" | "profitQoQ" | "opm" | "npm" | "eps">, fiscal?: string): string | null {
  const part = (label: string, v: number | null, yoy: number | null, qoq: number | null) => {
    if (v == null) return null;
    const moves = [yoy == null ? null : `${dir(yoy)} ${pc(yoy)} AT ${rs(v)} (YOY)`, move(qoq, "QOQ")].filter(Boolean) as string[];
    if (yoy == null) return `${label} AT ${rs(v)}${qoq == null ? "" : ", " + moves.join(", ")}`;
    return `${label} ${moves.join(", ")}`;
  };
  const np = r.netProfit != null && r.netProfit < 0
    ? `NET LOSS AT ${rs(r.netProfit)}${[move(r.profitQoQ, "QOQ")].filter(Boolean).map((x) => ", " + x).join("")}`
    : part("NET PROFIT", r.netProfit, r.profitYoY, r.profitQoQ);
  const margins = [r.opm == null ? null : `OPM ${nf(r.opm, 1)}%`, r.npm == null ? null : `NPM ${r.npm < 0 ? MINUS : ""}${nf(r.npm, 1)}%`].filter(Boolean).join(", ");
  const parts = [np, part("REVENUE", r.revenue, r.revenueYoY, r.revenueQoQ), margins || null, r.eps == null ? null : `EPS ${r.eps < 0 ? "-" : ""}Rs${nf(r.eps, 2)}`].filter(Boolean) as string[];
  return parts.length ? `${r.symbol}${fiscal ? " " + fiscal : ""}: ${parts.join(" / ")}` : null;
}

export const signedPct = (v: number | null, d = 1) => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? MINUS : ""}${nf(v, d)}%`);

// ------------------------------------------------------------ CSV
const cell = (v: string | number | boolean | null | undefined) => {
  if (v == null || v === "") return "";
  const s = csvText(String(v));
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
export const CSV_HEAD = ["Declared on", "Symbol", "Company", "Sector", "Market cap (Rs Cr)", "Status", "Revenue (Rs Cr)", "Revenue YoY %", "Revenue QoQ %", "Operating profit (Rs Cr)", "Operating profit YoY %", "Operating profit QoQ %", "OPM %",
  "Net profit (Rs Cr)", "Profit YoY %", "Profit QoQ %", "NPM %", "Net margin change YoY (pts)", "EPS (Rs)", "Revenue vs profit gap (pts)", "Profit and sales moved apart"];
const dayShort = (iso: string) => { const d = new Date(iso + "T00:00:00"); return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short" }); };
/** The honest reason a declared company has no figures yet: the data provider is behind, or our own report is still being updated. */
export const awaitingText = (date: string, why?: "provider" | "ours" | null): string =>
  why === "provider" ? `Declared on ${dayShort(date)}; the data provider has not published the figures yet` : "Declared, report being updated";
/** One plain status line per row (the CSV's Status column). */
export const statusText = (r: Pick<QRow, "status" | "date" | "awaitingWhy">): string =>
  r.status === "awaiting" ? awaitingText(r.date, r.awaitingWhy) : ({ declared: "Declared", due: "Due", missing: "Figures not stored", awaiting: "" } as Record<QStatus, string>)[r.status];

export function csvOf(rows: QRow[], quarterLabel: string): string {
  const lines = [[`Quarter: ${quarterLabel}`], CSV_HEAD].map((l) => l.map(cell).join(","));
  for (const r of rows) {
    lines.push([r.date, r.symbol, r.name, r.sector, r.marketCap, statusText(r), r.revenue, r.revenueYoY, r.revenueQoQ, r.operatingProfit, r.opYoY, r.opQoQ, r.opm, r.netProfit, r.profitYoY, r.profitQoQ, r.npm, r.npmChange, r.eps, r.gap,
      r.hasNumbers ? (r.flagged ? "Yes" : "No") : ""].map(cell).join(","));
  }
  return "﻿" + lines.join("\r\n") + "\r\n";
}
