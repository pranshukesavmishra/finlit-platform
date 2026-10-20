// Quarter results: the rows the server sends (GET /api/results/quarter), the Telegram-style one-line summary, and the CSV.
// The server decides what a plan may see and whether a company's figures are for THIS quarter; this file only formats what it is sent.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet } from "./api";
import { MINUS, csvText, nf } from "./format";

export type QStatus = "declared" | "awaiting" | "due" | "missing";
export type QRow = {
  date: string; symbol: string; name: string; sector: string | null; marketCap: number | null; cap: "Large" | "Mid" | "Small" | null; indices: string[];
  confirmed: boolean; periodEnd: string; loadedPeriodEnd: string | null; status: QStatus; awaiting: boolean; hasNumbers: boolean; locked: boolean;
  revenue: number | null; revenueYoY: number | null; revenueQoQ: number | null; operatingProfit: number | null; opm: number | null;
  netProfit: number | null; profitYoY: number | null; profitQoQ: number | null; npm: number | null; npmChange: number | null; eps: number | null;
  gap: number | null; flagged: boolean; loss: boolean;
};
export type QSummary = {
  companies: number; declared: number; due: number; awaiting: number; withNumbers: number; flagged: number | null;
  medianRevenueYoY: number | null; medianProfitYoY: number | null; profitUpShare: number | null; marginUpShare: number | null; nRevenue: number | null; nProfit: number | null; nMargin: number | null;
};
export type QInfo = { key: string; label: string; fiscal: string; periodEnd: string; from: string; to: string };
export type QResp = {
  plan: "basic" | "silver" | "gold"; locked: boolean; today: string; quarter: QInfo | null; quarters: (QInfo & { total: number; declared: number; due: number })[];
  total: number; offset: number; limit: number; summary: QSummary; totals: QSummary; rows: QRow[]; days: { date: string; n: number }[];
  facets: { sectors: { name: string; n: number }[]; indices: { code: string; n: number }[] }; gapFlag?: number; updatedAt?: string;
};
export type QParams = {
  quarter?: string; q?: string; sector?: string; cap?: string; index?: string; scope?: "all" | "watchlist" | "portfolio"; flagged?: boolean; status?: string;
  sort?: string; dir?: "asc" | "desc"; offset?: number; limit?: number;
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
  queryKey: ["quarter-results", queryString(p)], staleTime: 60_000, retry: 1, placeholderData: keepPreviousData,
  queryFn: () => apiGet<QResp>(`/api/results/quarter?${queryString({ limit: PAGE, ...p })}`),
});

/** The alert for this gap, ready to create: /alerts reads symbol, metric and value from the link. */
export const gapAlertLink = (symbol: string) => `/alerts?symbol=${encodeURIComponent(symbol)}&metric=rev_profit_gap&value=${GAP_FLAG}`;

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
export const CSV_HEAD = ["Declared on", "Symbol", "Company", "Sector", "Market cap (Rs Cr)", "Status", "Revenue (Rs Cr)", "Revenue YoY %", "Revenue QoQ %", "Operating profit (Rs Cr)", "OPM %",
  "Net profit (Rs Cr)", "Profit YoY %", "Profit QoQ %", "NPM %", "Net margin change YoY (pts)", "EPS (Rs)", "Revenue vs profit gap (pts)", "Profit and sales moved apart"];
const STATUS_TEXT: Record<QStatus, string> = { declared: "Declared", awaiting: "Declared, report being updated", due: "Due", missing: "Figures not stored" };

export function csvOf(rows: QRow[], quarterLabel: string): string {
  const lines = [[`Quarter: ${quarterLabel}`], CSV_HEAD].map((l) => l.map(cell).join(","));
  for (const r of rows) {
    lines.push([r.date, r.symbol, r.name, r.sector, r.marketCap, STATUS_TEXT[r.status], r.revenue, r.revenueYoY, r.revenueQoQ, r.operatingProfit, r.opm, r.netProfit, r.profitYoY, r.profitQoQ, r.npm, r.npmChange, r.eps, r.gap,
      r.hasNumbers ? (r.flagged ? "Yes" : "No") : ""].map(cell).join(","));
  }
  return "﻿" + lines.join("\r\n") + "\r\n";
}
