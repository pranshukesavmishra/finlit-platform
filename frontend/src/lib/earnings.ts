import { useQuery } from "@tanstack/react-query";
import { ApiError, apiGet } from "./api";

/** Earnings-call summaries (docs/EARNINGS-CALLS.md). The server writes every word shown here ahead of time, from one call's transcript, and checks that each quote is in it.
 *  The list is open to everyone; the answers are Gold and arrive only from the detail request. Nothing here is advice. */
export const NOTE = "AI-summarised from the transcript. Check the quotes.";
export const DISCLAIMER = "Information only, not investment advice.";
export const NOT_COVERED = "The call did not cover this.";
export const NOT_AVAILABLE = "Earnings-call summaries are not available yet";

export type CallRow = { fiscalYear: number; quarter: number; label: string; callDate: string | null; filedAt: string | null; transcriptUrl: string | null; pages: number };
export type QuestionMeta = { id: string; label: string; title: string };
export type Usage = { used: number; limit: number | null };
export type CallList = { symbol: string; name: string | null; available: boolean; locked: boolean; calls: CallRow[]; questions: QuestionMeta[]; usage: Usage | null; note: string; disclaimer: string };
export type Sentence = { text: string; quote: string; quoteRef: string };
export type Answer = QuestionMeta & { ready: boolean; covered: boolean; sentences: Sentence[] };
export type CallDetail = CallRow & { symbol: string; name: string | null; questions: Answer[]; usage: Usage; summarisedByAi: boolean; note: string; notCovered: string; disclaimer: string };

const retry = (n: number, e: unknown) => !(e instanceof ApiError && e.status < 500) && n < 1;
export const useEarningsCalls = (symbol: string, enabled = true) =>
  useQuery<CallList, ApiError>({ queryKey: ["earnings-calls", symbol], queryFn: () => apiGet<CallList>(`/api/earnings-calls/${encodeURIComponent(symbol)}`), staleTime: 10 * 60_000, retry, enabled: enabled && !!symbol });
/** One call's answers. Asking for a call counts it against the member's monthly allowance on the server, so this is asked only when the dialog shows that call. */
export const useEarningsCall = (symbol: string, fy: number | null, q: number | null, enabled = true) =>
  useQuery<CallDetail, ApiError>({
    queryKey: ["earnings-call", symbol, fy, q], queryFn: () => apiGet<CallDetail>(`/api/earnings-calls/${encodeURIComponent(symbol)}/${fy}/${q}`),
    staleTime: 10 * 60_000, retry, enabled: enabled && !!symbol && fy != null && q != null,
  });

export const fyShort = (fy: number) => `FY${String(fy % 100).padStart(2, "0")}`;
export const callLabel = (fy: number, q: number) => `Q${q} ${fyShort(fy)}`;
export const callKey = (c: { fiscalYear: number; quarter: number }) => `${c.fiscalYear}-${c.quarter}`;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-10-23" -> "23 Oct 2026" (read from the text, so the viewer's time zone cannot move the day). */
export function dayText(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : "";
}

/** The newest call, and the calls of one fiscal year by quarter: the pickers only offer calls that exist. */
export const newest = (calls: CallRow[]): CallRow | null => calls[0] ?? null;
export const yearsOf = (calls: CallRow[]): number[] => [...new Set(calls.map((c) => c.fiscalYear))].sort((a, b) => b - a);
export const findCall = (calls: CallRow[], fy: number, q: number): CallRow | undefined => calls.find((c) => c.fiscalYear === fy && c.quarter === q);
/** Picking a year keeps the quarter when that year has it, otherwise the newest quarter the year has. */
export function pickYear(calls: CallRow[], fy: number, q: number): CallRow | null {
  return findCall(calls, fy, q) ?? calls.filter((c) => c.fiscalYear === fy).sort((a, b) => b.quarter - a.quarter)[0] ?? null;
}

/** The title of the dialog and the "n of N calls" line. */
export const usageText = (u: Usage | null | undefined): string => (u && u.limit != null ? `${Math.min(u.used, u.limit)} of ${u.limit} calls this month` : "");

// ---- the questions a reader has asked in this browser tab (session only: nothing is sent to the server)
export type HistoryItem = { fy: number; q: number; qid: string };
const HKEY = (symbol: string) => `finlit.ec.history.${symbol}`;
const HMAX = 8;
export function loadHistory(symbol: string, store: Pick<Storage, "getItem"> | null = safeStore()): HistoryItem[] {
  try {
    const v = JSON.parse(store?.getItem(HKEY(symbol)) || "[]");
    return Array.isArray(v) ? v.filter((x) => x && Number.isInteger(x.fy) && Number.isInteger(x.q) && typeof x.qid === "string").slice(0, HMAX) : [];
  } catch { return []; }
}
export function pushHistory(symbol: string, item: HistoryItem, store: Pick<Storage, "getItem" | "setItem"> | null = safeStore()): HistoryItem[] {
  const next = [item, ...loadHistory(symbol, store).filter((h) => !(h.fy === item.fy && h.q === item.q && h.qid === item.qid))].slice(0, HMAX);
  try { store?.setItem(HKEY(symbol), JSON.stringify(next)); } catch { /* private window: the list lives in memory only */ }
  return next;
}
function safeStore(): Storage | null { try { return typeof sessionStorage === "undefined" ? null : sessionStorage; } catch { return null; } }
