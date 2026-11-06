// The shape of POST /api/portfolio/page (backend/finlit/portfolio_page). Names go in; every figure and every sentence comes back, nothing is written by the page.
import type { StyleTilt } from "../components/diversification/types";

export type Mode = "eq" | "mc";
export type SizeCode = "L" | "M" | "S" | "U";
export type Reading = { rule: string; section: "where" | "together" | "risk" | "market" | "data"; priority: number; text: string; mode: Mode | "both" };
export type Group = { members: string[]; avg_corr: number; letter: string };
export type Seg = { pairs: number; avg: number | null; median: number | null; at_least_05: number; share_at_least_05: number | null; top: { a: string; b: string; corr: number }[]; hist: number[] };
export type Segments = { same: Seg; cross: Seg; bins: [number, number][] };
export type Market = { beta: number; worst10_list: number; worst10_nifty: number; vol: number; vol_nifty: number; max_fall: number; max_fall_nifty: number };
export type PerMode<T> = { eq: T; mc: T };
export type Score = { score: number; band: string; comovement: number; sector_spread: number; effective_stocks: number; effective_sectors: number };

export type PageObject = {
  layout: "short" | "long"; weeks: number; from: string; to: string; score: Score; order: string[]; corr: number[][]; groups: Group[]; segments: Segments;
  within: Record<string, { n: number; avg: number }>; avg_with_rest: Record<string, number>; near_duplicates: { a: string; b: string; corr: number }[];
  sector_weight: PerMode<Record<string, number>>; size_weight: PerMode<Record<string, number>>; size_count: Record<string, number>;
  share_weight: PerMode<Record<string, number>>; share_risk: PerMode<Record<string, number>>; sector_risk: PerMode<Record<string, number>>; market: PerMode<Market>;
  first_k?: { k: number; effective_stocks: number; rest: number; added: number } | null;
  readings: Reading[]; summary: PerMode<Reading[]>; together_open_by_default: boolean; short_history: string[];
};
export type Meta = { name: string; sector: string | null; size: SizeCode; mcap_cr: number | null };
export type PageResponse = {
  week: string; symbols: string[]; unknown: string[]; noPrices: string[]; page: PageObject | null; meta: Record<string, Meta>; styleTilt?: StyleTilt;
};
