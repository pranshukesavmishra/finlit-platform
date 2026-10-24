import { useQuery } from "@tanstack/react-query";
import { ApiError, apiGet } from "./api";

/** The Leader / In line / Laggard label of a stock. Everything shown on the site (the line under the name, the Peers table, the bottom section)
 *  reads this one object, so the copy cannot disagree between them. It describes past price performance only. */
export type LeadLabel = "leader" | "in_line" | "laggard";
export type Direction = "gaining" | "weakening" | null;
export type LeadPeer = { symbol: string; name: string | null; rank: number; label: LeadLabel; direction: Direction; rel13: number | null; rel52: number | null; rel52Market: number | null; marketCap: number | null };
export type Reliability = { tier: "consistent" | "mixed" | "not_reliable" | "insufficient"; hitRate6m: number | null; checks: number; from: string | null; to: string | null; periods: { years: string; hitRate6m: number; checks?: number }[]; sentence?: string };
export type LeadParts = { rank: string; sector: { pts: string; name: string; v: number | null }; market: { pts: string; name: string; v: number | null } | null; direction: Direction };
export type LeadDisplay = { chip: string | null; line: string; parts?: LeadParts; note: string | null; tooltip: string | null; benchmarkNote?: string };
export type LeadershipOn = {
  available: true; asOf: string; stale: boolean; held: boolean;
  peerGroup: { id: string; name: string; short: string; kind: "industry" | "sector"; ranked: number };
  benchmarks: { sector: { code: string | null; name: string; kind: "index" | "peer_average"; ret52: number | null }; market: { code: string; name: string; ret52: number | null } | null };
  rel: { w13: number | null; w26: number | null; w52: number | null; w52Market: number | null };
  rank: number; label: LeadLabel; rawLabel: LeadLabel; direction: Direction; fundamentalNote: "below_peers" | "stronger_than_price" | null;
  fundamentalRank: number | null; fundamentalOf: number | null; labelSince: string | null; sectorReliability: Reliability; display: LeadDisplay; peers: LeadPeer[];
};
export type LeadershipOff = { available: false; reason: "history" | "stale" | "liquidity" | "group"; display: LeadDisplay };
export type Leadership = LeadershipOn | LeadershipOff;
export type LeadRun = { date: string; rank: number; ranked: number; label: LeadLabel; direction: Direction; rel52: number | null; rel52Market: number | null };
export type LeadHistory = { available: boolean; rows: LeadRun[]; series: { dates: string[]; stock: (number | null)[]; sector: (number | null)[] | null; market: (number | null)[] | null } | null };

const retry = (n: number, e: unknown) => !(e instanceof ApiError && e.status < 500) && n < 1;
export const useLeadership = (symbol: string, enabled = true) =>
  useQuery<Leadership, ApiError>({ queryKey: ["leadership", symbol], queryFn: () => apiGet<Leadership>(`/api/stocks/${encodeURIComponent(symbol)}/leadership`), staleTime: 15 * 60_000, retry, enabled: enabled && !!symbol });
export const useLeadershipHistory = (symbol: string, enabled = true) =>
  useQuery<LeadHistory, ApiError>({ queryKey: ["leadership-history", symbol], queryFn: () => apiGet<LeadHistory>(`/api/stocks/${encodeURIComponent(symbol)}/leadership-history`), staleTime: 15 * 60_000, retry, enabled: enabled && !!symbol });

export const LABEL_WORD: Record<LeadLabel, string> = { leader: "Leader", in_line: "In line", laggard: "Laggard" };
const MINUS = "−";
/** A fraction as percentage points with one decimal and a real minus sign: 0.012 -> "+1.2", -0.072 -> "−7.2". */
export const pts = (x: number | null | undefined, plus = true): string => {
  if (x == null || !Number.isFinite(x)) return "—";
  const v = Math.round(x * 1000) / 10;
  return (v > 0 && plus ? "+" : v < 0 ? MINUS : "") + Math.abs(v).toFixed(1);
};
export const tone = (x: number | null | undefined): "up" | "down" | "flat" => (x == null || Math.abs(x) < 0.0005 ? "flat" : x > 0 ? "up" : "down");
export const ordinal = (n: number): string => `${n}${n % 100 >= 10 && n % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] || "th"}`;
export const monthYear = (iso: string): string => new Date(iso + "T00:00:00Z").toLocaleDateString("en-IN", { month: "short", year: "numeric", timeZone: "UTC" });

/** The sentence over the rank-history chart: the story in words. */
export function rankStory(name: string, rows: LeadRun[]): string {
  if (!rows.length) return "";
  const n = rows.length, count = (l: LeadLabel) => rows.filter((r) => r.label === l).length;
  const best = (["leader", "laggard", "in_line"] as LeadLabel[]).reduce((a, l) => (count(l) > count(a) ? l : a), "in_line" as LeadLabel);
  const where = best === "leader" ? "in the leader zone" : best === "laggard" ? "in the laggard zone" : "in the middle of its peers";
  return `${name} has been ${where} in ${count(best)} of ${n} checks since ${monthYear(rows[0].date)}`;
}

/** Words for the conclusion of the relative-strength chart (read out by screen readers). */
export function relativeSentence(name: string, bench: string, last: number | null, range: string): string {
  if (last == null) return `${name} against ${bench}: not enough data for this range.`;
  const d = Math.round((last - 100) * 10) / 10;
  if (d === 0) return `Over ${range}, ${name} has matched ${bench}.`;
  return `Over ${range}, ${name} has ${d > 0 ? "outperformed" : "been behind"} ${bench} by ${Math.abs(d).toFixed(1)} points.`;
}
