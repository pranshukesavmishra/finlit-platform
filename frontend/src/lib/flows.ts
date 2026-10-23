// FII / DII institutional flows: the contract of GET /api/flows (built by backend/finlit/flows.py) and the pure helpers the page and the
// dashboard panel share. Every amount is ₹ crore as published; a figure that no permitted source publishes is null, never estimated.
import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "./api";

export type Side = { buy: number | null; sell: number | null; net: number | null };
/** One trading day of cash-market activity. `dii` is null on days (or in a whole deployment) where no permitted source publishes it. */
export type FlowDay = { d: string; fii: Side; dii: Side | null };
export type Streak = { side: "buying" | "selling" | "flat"; days: number; since: string | null; sum: number; velocity: number | null };
export type Period = { key: string; label: string; from: string; to: string; days: number; fii: number | null; diiNet: number | null; fiiBuy: number | null; fiiSell: number | null };
/** Futures and options positioning by participant (open interest, contracts) from the exchanges' participant-wise files; null when not published to us. */
export type Positioning = {
  asOf: string;
  rows: { participant: "FII" | "DII" | "Pro" | "Client"; instrument: "Index Futures" | "Index Options" | "Stock Futures" | "Stock Options"; long: number | null; short: number | null; net: number | null }[];
} | null;
export type FpiDetail = { asOf: string; equityNet: number | null; debtNet: number | null; hybridNet: number | null; totalNet: number | null; usdMillion: number | null; inr: number | null } | null;
export type SourceNote = { id: string; label: string; url: string; covers: string; status: "ok" | "stale" | "unavailable"; lastDate: string | null; note?: string };

export type Flows = {
  updatedAt: string; today: string;
  latest: { d: string; fii: Side; dii: Side | null; combinedNet: number | null; fiiShareOfSelling: number | null; mood: "Heavy outflow" | "Mild outflow" | "Balanced" | "Mild inflow" | "Heavy inflow" | null } | null;
  streaks: { fii: Streak | null; dii: Streak | null };
  last30: { fii: number | null; dii: number | null; days: number };
  days: FlowDay[];                 // newest last; as many sessions as the sources give (up to 5 years)
  periods: Period[];               // this week, this month, this financial year, calendar year, rolling 30 / 90 / 365 sessions
  monthly: { m: string; fii: number | null; dii: number | null; days: number }[];
  yearly: { y: string; fii: number | null; dii: number | null; days: number }[];
  derivatives: Positioning;
  fpi: FpiDetail;                  // NSDL's all-asset view of FPI flows for the latest reporting day (equity, debt, hybrid)
  correlation: { index: string; label: string; fiiVsIndex: number | null; diiVsIndex: number | null; days: number } | null;
  /** Optional (backwards compatible): the index's daily close over the same sessions, for the Flow vs Nifty chart. The page degrades to the correlation figures alone when it is absent. */
  index?: { d: string; close: number }[] | null;
  coverage: { from: string | null; to: string | null; sessions: number; diiSessions: number };
  sources: SourceNote[];
  disclaimer: string;
};

export const useFlows = () => useQuery<Flows, ApiError>({ queryKey: ["flows"], queryFn: () => apiGet<Flows>("/api/flows"), staleTime: 300_000, retry: 1 });
