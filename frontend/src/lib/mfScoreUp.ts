// Gold-only upgrades of the FinLit Mutual Fund Health Score: history, breakdown helpers, the Fund Score Screener, the category leaderboard, compare and alerts.
// Everything describes past NAVs, costs and holdings. No buy, sell or hold wording anywhere in this file.
import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "./api";
import { bandOf, type FundScore, type ScoreMetric } from "./mfScore";

export const PILLARS = [["performance", "Performance"], ["risk", "Risk"], ["cost", "Cost"], ["quality", "Quality"]] as const;
export type PillarKey = (typeof PILLARS)[number][0];
export type PillarMap = Record<PillarKey, number | null>;
export const LABELS = ["Strong", "Healthy", "Average", "Weak", "Poor"] as const;
/** Edges of the labels, drawn as zones behind the history chart. */
export const ZONES: [string, number, number][] = [["Poor", 0, 35], ["Weak", 35, 50], ["Average", 50, 65], ["Healthy", 65, 80], ["Strong", 80, 100]];

export type HistPoint = { date: string; week: string; final: number | null; label: string | null; status: string; pillars: PillarMap; rank: number | null; rankOf: number | null; percentile: number | null };
export type Changes = { since: string; until: string; from: number; to: number; delta: number; fromLabel: string | null; toLabel: string | null; pillar: { key: string; name: string; delta: number } | null; rankFrom: number | null; rankTo: number | null; rankOf: number | null; text: string };
export type ScoreHistory = { locked: boolean; points: HistPoint[]; count: number | null; firstDate: string | null; note: string | null; changes: Changes | null };
export const useScoreHistory = (code: number, kind: "mf" | "etf" = "mf", symbol = "", enabled = true) =>
  useQuery<ScoreHistory, ApiError>({
    queryKey: ["mfscore", "hist", kind, kind === "etf" ? symbol : code], staleTime: 600_000, retry: 1, enabled: enabled && (kind === "etf" ? !!symbol : code > 0),
    queryFn: () => apiGet<ScoreHistory>(kind === "etf" ? `/api/mf/etf/${encodeURIComponent(symbol)}/score/history` : `/api/mf/${code}/score/history`),
  });
export type ManyHistory = { locked: boolean; series: Record<string, { date: string; final: number | null; label: string | null }[]> };
export const useManyHistory = (codes: number[], enabled = true) => {
  const ids = [...new Set(codes)].slice(0, 10).sort((a, b) => a - b).join(",");
  return useQuery<ManyHistory, ApiError>({ queryKey: ["mfscore", "hist-many", ids], enabled: enabled && !!ids, staleTime: 600_000, retry: 1, queryFn: () => apiGet<ManyHistory>(`/api/mf/scores/history?codes=${ids}`) });
};

// ------------------------------------------------------------------------------------------------------------------ breakdown
export const STATE_WORD: Record<string, string> = { A: "Actual", Z: "Actual", S: "Substituted", F: "Filled", N: "Not applicable" };
export const STATE_EXPLAIN: Record<string, string> = {
  A: "The fund's own figure was measured and scored.",
  Z: "The fund's own figure was a loss, which earns 0 points.",
  S: "A nearby figure or a wider peer group stood in for the one asked for.",
  F: "No usable figure, so the group value (never better than a typical fund) was used.",
  N: "This measure does not apply to this kind of fund and is left out of the weights.",
};
export const stateLine = (m: ScoreMetric & { whyText?: string | null }) => `${STATE_EXPLAIN[m.state] ?? ""}${m.whyText ? ` Reason: ${m.whyText}.` : ""}`.trim();
export const barBand = (points: number | null) => bandOf(points);
export type MetricGroup = { key: PillarKey; name: string; score: number | null; metrics: (ScoreMetric & { whyText?: string | null })[] };
export function groupMetrics(s: Pick<FundScore, "pillars" | "metrics">): MetricGroup[] {
  return PILLARS.map(([key, name]) => ({ key, name, score: s.pillars.find((p) => p.key === key)?.score ?? null, metrics: (s.metrics || []).filter((m) => m.pillar === key) }));
}
export const dataGaps = (s: Pick<FundScore, "metrics">) => (s.metrics || []).filter((m) => m.state === "F" || m.state === "S");
export const PEER_KIND_WORD: Record<string, string> = { sub: "category and plan", grp: "widened to the whole group (too few in the category)", fam: "tracking the same index" };
export type CategoryMedian = { performance: number | null; risk: number | null; cost: number | null; quality: number | null; final: number | null; n: number; plan: string; categoryLabel: string | null };

// ------------------------------------------------------------------------------------------------------------------ compare
/** The gap (in points, 0 to 100) inside which two funds count as level. */
export const LEVEL_TOLERANCE = 3;
export type Ahead = "ahead" | "level" | "behind" | "na";
export const compareTo = (v: number | null | undefined, ref: number | null | undefined): Ahead => (v == null || ref == null ? "na" : v - ref > LEVEL_TOLERANCE ? "ahead" : ref - v > LEVEL_TOLERANCE ? "behind" : "level");

// ------------------------------------------------------------------------------------------------------------------ screener
export type ScreenerItem = {
  key: string; kind: "mf" | "etf"; code: number | null; symbol: string | null; name: string; amc: string | null; plan: string; group: string; sub: string; categoryLabel: string | null;
  final: number | null; label: string | null; status: string; reason: string | null; pillars: PillarMap; rank: number | null; rankOf: number | null;
  aumCr: number | null; ageYears: number | null; ter: number | null; r1y: number | null; r3y: number | null; r5y: number | null; fullData: boolean; flags: string[];
};
export type ScreenerList = { locked: boolean; total: number | null; runDate: string | null; items: ScreenerItem[] };
export type Facets = { locked: boolean; categories: { sub: string; label: string; group: string; n: Record<string, number> }[]; runDate: string | null };
export type Leaderboard = { locked: boolean; sub: string; plan: string; categoryLabel: string | null; items: ScreenerItem[]; stats: ({ median: number | null; p25: number | null; p75: number | null; min: number | null; max: number | null; n: number; notRated: number } & Partial<Record<PillarKey, number | null>>) | null; nearIdentical: boolean; nearIdenticalText: string | null };

export type SQuery = {
  plan: string; subs: string[]; labels: string[]; status: string; min: string; max: string; perf: [string, string]; risk: [string, string]; cost: [string, string]; quality: [string, string];
  aum: [string, string]; age: [string, string]; terMax: string; full: boolean; q: string; sort: string; dir: "asc" | "desc"; page: number; view: string; tab: "table" | "board";
};
export const PAGE = 50;
export const emptyQuery = (): SQuery => ({ plan: "Direct", subs: [], labels: [], status: "", min: "", max: "", perf: ["", ""], risk: ["", ""], cost: ["", ""], quality: ["", ""], aum: ["", ""], age: ["", ""],
  terMax: "", full: false, q: "", sort: "final", dir: "desc", page: 1, view: "", tab: "table" });
/** Quick views, built from the four parts only and named neutrally. */
export const VIEWS: { id: string; label: string; say: string; set: Partial<SQuery> }[] = [
  { id: "lowcost", label: "High score with a low-cost part", say: "Score 65 or more and a Cost part of 70 or more.", set: { min: "65", cost: ["70", ""] } },
  { id: "risk", label: "High Risk part", say: "A Risk part of 70 or more: a smoother ride against similar funds.", set: { risk: ["70", ""] } },
  { id: "consistent", label: "High Performance and Risk parts", say: "Performance and Risk parts both 65 or more: returns that were also steady.", set: { perf: ["65", ""], risk: ["65", ""] } },
];
export const activeView = (q: SQuery) => VIEWS.find((v) => q.view === v.id)?.id ?? "";

export function queryToParams(q: SQuery): URLSearchParams {
  const p = new URLSearchParams(), d = emptyQuery();
  const put = (k: string, v: string) => { if (v !== "") p.set(k, v); };
  if (q.plan !== d.plan) p.set("plan", q.plan);
  if (q.subs.length) p.set("sub", q.subs.join(","));
  if (q.labels.length) p.set("labels", q.labels.join(","));
  put("status", q.status); put("min", q.min); put("max", q.max);
  for (const k of ["perf", "risk", "cost", "quality", "aum", "age"] as const) { put(k + "_min", q[k][0]); put(k + "_max", q[k][1]); }
  put("ter_max", q.terMax); put("q", q.q);
  if (q.full) p.set("full", "1");
  if (q.sort !== d.sort || q.dir !== d.dir) { p.set("sort", q.sort); p.set("dir", q.dir); }
  if (q.page > 1) p.set("page", String(q.page));
  put("view", q.view);
  if (q.tab === "board") p.set("tab", "board");
  return p;
}
export function paramsToQuery(p: URLSearchParams): SQuery {
  const q = emptyQuery(), g = (k: string) => p.get(k) ?? "";
  const list = (k: string) => g(k).split(",").filter(Boolean);
  q.plan = ["Direct", "Regular", "ETF", "all"].includes(g("plan")) ? g("plan") : "Direct";
  q.subs = list("sub"); q.labels = list("labels").filter((l) => (LABELS as readonly string[]).includes(l));
  q.status = ["RATED", "PROVISIONAL"].includes(g("status")) ? g("status") : "";
  q.min = g("min"); q.max = g("max"); q.terMax = g("ter_max"); q.q = g("q"); q.full = g("full") === "1";
  for (const k of ["perf", "risk", "cost", "quality", "aum", "age"] as const) q[k] = [g(k + "_min"), g(k + "_max")];
  q.sort = g("sort") || "final"; q.dir = g("dir") === "asc" ? "asc" : "desc";
  q.page = Math.max(1, parseInt(g("page")) || 1); q.view = VIEWS.some((v) => v.id === g("view")) ? g("view") : ""; q.tab = g("tab") === "board" ? "board" : "table";
  return q;
}
/** The server's parameters for a query (without paging). */
export function serverParams(q: SQuery, paging: { limit: number; offset: number } | null): URLSearchParams {
  const p = queryToParams({ ...q, page: 1, view: "", tab: "table" });
  p.delete("view");
  p.set("plan", q.plan);
  if (paging) { p.set("limit", String(paging.limit)); p.set("offset", String(paging.offset)); }
  return p;
}
export const useScreener = (q: SQuery, enabled: boolean) => {
  const qs = serverParams(q, { limit: PAGE, offset: (q.page - 1) * PAGE }).toString();
  return useQuery<ScreenerList, ApiError>({ queryKey: ["mfscore", "screener", qs], enabled, staleTime: 300_000, retry: 1, placeholderData: (x) => x, queryFn: () => apiGet<ScreenerList>(`/api/mf/score-screener?${qs}`) });
};
export const useFacets = (enabled: boolean) => useQuery<Facets, ApiError>({ queryKey: ["mfscore", "facets"], enabled, staleTime: 600_000, retry: 1, queryFn: () => apiGet<Facets>("/api/mf/score-screener/facets") });
export const useLeaderboard = (sub: string, plan: string, enabled: boolean) =>
  useQuery<Leaderboard, ApiError>({ queryKey: ["mfscore", "board", sub, plan], enabled: enabled && !!sub, staleTime: 600_000, retry: 1, queryFn: () => apiGet<Leaderboard>(`/api/mf/leaderboard?sub=${encodeURIComponent(sub)}&plan=${plan === "all" ? "Direct" : plan}`) });
export const csvUrl = (q: SQuery) => `/api/mf/score-screener?${(() => { const p = serverParams(q, { limit: 6000, offset: 0 }); p.set("format", "csv"); return p; })().toString()}`;
export const CSV_HEADS = ["Fund", "Fund house", "Plan", "Category", "Score", "Label", "Status", "Performance", "Risk", "Cost", "Quality", "Rank in category", "Funds ranked", "AUM (Rs crore)", "Age (years)", "Expense ratio (%)", "1Y return (%)", "3Y return (% a year)", "5Y return (% a year)"];
export function chips(q: SQuery): { id: string; text: string }[] {
  const out: { id: string; text: string }[] = [];
  if (q.plan !== "Direct") out.push({ id: "plan", text: q.plan === "all" ? "All plans" : q.plan + " plan" });
  if (q.subs.length) out.push({ id: "subs", text: `${q.subs.length} categor${q.subs.length === 1 ? "y" : "ies"}` });
  if (q.labels.length) out.push({ id: "labels", text: q.labels.join(", ") });
  if (q.status) out.push({ id: "status", text: q.status === "RATED" ? "Rated" : "Provisional" });
  const rng = (id: string, name: string, [a, b]: [string, string]) => { if (a || b) out.push({ id, text: `${name} ${a || "0"} to ${b || "∞"}` }); };
  rng("score", "Score", [q.min, q.max]); rng("perf", "Performance", q.perf); rng("risk", "Risk", q.risk); rng("cost", "Cost", q.cost); rng("quality", "Quality", q.quality); rng("aum", "AUM (₹ Cr)", q.aum); rng("age", "Age (yrs)", q.age);
  if (q.terMax) out.push({ id: "ter", text: `Expense ratio up to ${q.terMax}%` });
  if (q.full) out.push({ id: "full", text: "Full data only" });
  if (q.q) out.push({ id: "q", text: `Name has "${q.q}"` });
  return out;
}
export function clearChip(q: SQuery, id: string): SQuery {
  const d = emptyQuery(), n = { ...q, page: 1, view: "" };
  switch (id) {
    case "plan": n.plan = d.plan; break; case "subs": n.subs = []; break; case "labels": n.labels = []; break; case "status": n.status = ""; break;
    case "score": n.min = n.max = ""; break; case "perf": case "risk": case "cost": case "quality": case "aum": case "age": n[id] = ["", ""]; break;
    case "ter": n.terMax = ""; break; case "full": n.full = false; break; case "q": n.q = ""; break;
  }
  return n;
}

// ------------------------------------------------------------------------------------------------------------------ alerts
export type ScoreAlert = { id: string; key: string; name: string; kind: "band" | "move"; points: number | null; channels: string[]; status: string };

// ------------------------------------------------------------------------------------------------------------------ admin
export type AdminHealth = {
  internal: true; lastRun: Record<string, unknown> | null; total: number; status: Record<string, number>; distribution: { bins: string[]; byGroup: Record<string, number[]> };
  filled: { group: string; funds: number; withAGap: number; measuresFilled: number }[]; zeroCounters: Record<string, number>; notRated: { reason: string; n: number }[];
  topMissing: { id: string; label: string; why: string; whyText: string; n: number }[]; peerSizes: { buckets: string[]; byKind: Record<string, number[]> }; history: { rows: number; first: string | null; last: string | null };
};
export type Calibration = { internal: true; label: string; monthsAgo: number; asOf: string; historyStarts: string | null; funds: number; note: string | null; how: string;
  quintiles: { quintile: number; funds: number; avgScore: number; avgLaterReturn: number; avgReturnRank: number }[] };
