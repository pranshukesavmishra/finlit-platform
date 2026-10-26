// Typed client for the FinLit API. Every stock section is a small precomputed JSON document,
// served with an ETag; React Query caches them per stock and section.
import { useQuery, type UseQueryOptions } from "@tanstack/react-query";

export type Band = { key: "strong" | "healthy" | "mixed" | "watch" | "insufficient"; label: string };
export type Meta = { symbol: string; statement: "consolidated" | "standalone"; generatedAt: string; version: number; scoreModel: string };
export type Series = (number | null)[];
export type Table = { unit: string; period: string; periods: string[]; periodEnds: string[]; rows: Record<string, Series> };

export type Profile = {
  symbol: string; name: string; nse: string | null; bse: string | null; sector: string | null; industry: string | null;
  subIndustry: string | null; macroSector: string | null; website: string | null; description: string | null;
  employees: number | null; marketCapCr: number | null; hasConsolidated: boolean;
};
export type Quote = {
  price: number | null; changePct: number | null; change: number | null; previousClose: number | null; open: number | null;
  high: number | null; low: number | null; high52: number | null; low52: number | null; volume: number | null;
  marketCapCr: number | null; asOf: string | null;
  upperCircuit?: number | null; lowerCircuit?: number | null;   // the day's price band, only in a quote from Dhan (worker.refresh_quotes)
};
export type Note = { key: string; title: string; text: string; value: number | null };
export type KeyMetric = { key: string; value: number; unit: string | null; label: string; period: string };
export type Return = { period: string; price: number | null; dividend: number | null; total: number | null; annualised: number | null };
export type QualityIssue = { key: string; severity: "critical" | "warning"; message: string; value?: number };
export type DataQuality = {
  missing: string[]; notes: string[]; provisionalLastBar: boolean; removedBadTicks: string[]; statement: string; isBank: boolean;
  priceAsOf: string | null; fundamentalsAsOf: string | null;
  basis?: { chosen: "standalone"; requested: "consolidated"; reason: "stale_consolidated"; consolidatedLatestQuarter?: string | null; standaloneLatestQuarter?: string | null };
  coverage?: { state: "complete" | "partial" | "empty"; reasons: string[]; mismatches: string[] };   // what the data provider sent for this company, in words
  checks: { status: "ok" | "warnings" | "rejected"; passed: number; total: number; issues: QualityIssue[] };
};
export type PillarSummary = { key: string; label: string; score: number | null; band: Band; coverage: number; reason?: string };
export type Summary = {
  meta: Meta; profile: Profile; quote: Quote; range52: { high: number | null; low: number | null };
  sparkline: { t: string[]; c: number[] };
  score: { overall: number | null; band: Band; model: string; pillars: PillarSummary[] };
  thesis: string | null; strengths: Note[]; watchouts: Note[]; keyMetrics: KeyMetric[]; returns: Return[]; dataQuality: DataQuality;
};
export type Financials = { meta: Meta; unit: string; yearly: { pl: Table; bs: Table; cf: Table }; quarterly: { pl: Table } };
export type RatioEntry = { value: number; period: string; label: string; unit: string | null; better: "higher" | "lower" | null; group: string | null };
export type Glossary = { key: string; label: string; unit?: string; better?: string | null; group?: string; term?: string; what?: string; why?: string; read?: string; formula?: string; note?: string; lines?: string[] };
export type PillarInput = { key: string; label: string; value: number | null; score: number | null; thresholds: number[]; lowerIsBetter: boolean };
export type Ratios = {
  meta: Meta; notes: string[]; latest: Record<string, RatioEntry>;
  groups: { id: string; label: string; pillar: string; keys: string[] }[];
  history: { periods: string[]; rows: Record<string, Series> };
  valuationHistory: { periods: string[]; rows: Record<"pe" | "pb" | "ps" | "average_price", Series> };
  score: { model: string; overall: number | null; band: Band; pillars: (PillarSummary & { inputs: PillarInput[] })[] };
  glossary: Record<string, Glossary>;
};
export type Ownership = {
  meta: Meta; periods: string[]; asOf: string | null; comparedWith: string | null; series: Record<string, Series>;
  latest: { key: string; label: string; value: number | null; change1yPts: number | null }[];
};
export type Action = { date: string; type: string; title: string; amount: number | null; adjustedAmount: number | null; ratio: string | null; paidInFY: string | null; forFY: string | null };
export type Announcement = { date: string; time: string | null; category: string; description: string; link: string | null };
export type Events = {
  meta: Meta; actions: Action[]; dividendYieldTtm: number | null; announcements: Announcement[];
  dividendsByFY: { periods: string[]; dps: number[]; dpsUnadjusted: number[]; basis: string };
};
export type Segment = { name: string; revenue: number | null; ebit: number | null; sharePct: number | null; growthPct: number | null; includes?: string[] };
export type Segments = { meta: Meta; unit: string; periods: string[]; segments: Record<string, { revenue: Series; ebit: Series }>; latest: Segment[] };
export type PeerItem = { symbol: string; name: string | null; sector?: string | null; overall?: number | null; band?: string | null; price?: number | null; market_cap?: number | null; pe?: number | null; roe?: number | null };
export type Peers = { meta: Meta; symbols: string[]; items?: PeerItem[] };
export type Technical = {
  price: number; ema20: number | null; ema50: number | null; ema200: number | null; vsEma20Pct: number | null; vsEma50Pct: number | null;
  vsEma200Pct: number | null; rsi14: number | null; rsiZone: "oversold" | "overbought" | "neutral" | null;
};
export type PriceRange = {
  meta: Meta; range: string; grain: "daily" | "weekly"; technical: Technical; complete: boolean; startsAt: string | null; provisionalLastBar: boolean;
  series: { t: string[]; o?: Series; h?: Series; l?: Series; c: number[]; v: Series; ema50: Series; ema200: Series };
};
/** Intraday candles from Dhan (1D 1-minute, 5D 5-minute, 1M hourly). Times are ISO with +05:30; `asOf` is when Dhan was asked. */
export type IntradayRange = "1D" | "5D" | "1M";
export type Intraday = {
  status: "ok" | "no_data"; available: boolean; symbol: string; range: IntradayRange; interval: number; exchange: "NSE" | "BSE"; source: string;
  asOf: string; session: string | null; sessions: string[]; lastBarAt: string | null; phase: "open" | "pre_open" | "closed"; today: string;
  stale?: boolean; detail?: string;
  series?: { t: string[]; o: number[]; h: number[]; l: number[]; c: number[]; v: (number | null)[] };
};
export type SearchRow = [symbol: string, name: string, bse: string | null, ready: number, nse?: string];

/** API origin. Empty in development (Vite proxies /api); in production set VITE_API_BASE=https://api.finlitventures.com. */
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || "";
export const apiUrl = (path: string) => (path.startsWith("/") ? API_BASE + path : path);

export class ApiError extends Error {
  constructor(public status: number, public body: { status?: string; detail?: string; retryAfter?: number; plan?: string }) {
    super(body.detail || body.status || `HTTP ${status}`);
  }
}

/** FastAPI wraps errors as {detail: {status, detail}} (or a list for validation errors); flatten to one shape. */
export function errorBody(raw: unknown): ApiError["body"] {
  const r = raw as { detail?: unknown; status?: string } | null;
  if (!r) return {};
  if (r.detail && typeof r.detail === "object" && !Array.isArray(r.detail)) return r.detail as ApiError["body"];
  if (Array.isArray(r.detail)) return { status: "invalid", detail: "Please check what you entered and try again." };
  return r as ApiError["body"];
}

/** The signed-in session's CSRF token; set by the auth provider and sent on every state-changing request. */
let csrf: string | null = null;
export const setCsrf = (t: string | null) => { csrf = t; };

/** POST/PUT/PATCH/DELETE with the session cookie and CSRF header. */
export async function apiSend<T = { status?: string }>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(apiUrl(path), { method, headers, credentials: API_BASE ? "include" : "same-origin", body: body === undefined ? undefined : JSON.stringify(body) });
  let data: unknown = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const b = errorBody(data);
    b.retryAfter = Number(res.headers.get("Retry-After") || 0) || b.retryAfter;
    throw new ApiError(res.status, b);
  }
  return data as T;
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), { headers: { Accept: "application/json" }, credentials: API_BASE ? "include" : "same-origin", ...init });
  if (res.status === 202 || !res.ok) {
    let body: ApiError["body"] = {};
    try { body = errorBody(await res.json()); } catch { /* not JSON */ }
    body.retryAfter = Number(res.headers.get("Retry-After") || 0) || undefined;
    throw new ApiError(res.status, body);
  }
  return res.json() as Promise<T>;
}

import { useBasis, withBasis, type Basis } from "./basis";

const SECTION_STALE = 60_000;

function sectionQuery<T>(symbol: string, path: string, extra?: Partial<UseQueryOptions<T, ApiError>>, basis: Basis = "consolidated") {
  return {
    queryKey: ["stock", symbol, path, basis],
    queryFn: () => apiGet<T>(`/api/stocks/${encodeURIComponent(symbol)}${withBasis(path, basis)}`),
    staleTime: SECTION_STALE,
    // A stock that has never been opened is prepared on demand (202): keep asking (for up to about five minutes; the server counts
    // only the first request). 429 means many reports are being prepared at once: wait as told and ask again.
    retry: (count: number, err: ApiError) => (err.status === 202 ? count < 100 : err.status === 429 ? count < 8 : err.status >= 500 && count < 2),
    retryDelay: (_: number, err: ApiError) => (err.status === 202 ? (err.body.retryAfter || 3) * 1000 : err.status === 429 ? Math.min(30, err.body.retryAfter || 10) * 1000 : 1500),
    ...extra,
  };
}

export const useSummary = (s: string, enabled = true) => { const b = useBasis(s); return useQuery<Summary, ApiError>({ ...sectionQuery<Summary>(s, "", undefined, b), placeholderData: (prev) => (prev?.meta.symbol === s.toUpperCase() ? prev : undefined), enabled: enabled && !!s }); };
export const useSection = <T,>(s: string, name: string, enabled = true, basis?: Basis) => { const own = useBasis(s), b = basis ?? own; return useQuery<T, ApiError>({ ...sectionQuery<T>(s, `/${name}`, undefined, b), placeholderData: (prev) => ((prev as { meta?: { symbol?: string } } | undefined)?.meta?.symbol === s.toUpperCase() ? prev : undefined), enabled }); };
export const usePrice = (s: string, range: string, enabled = true) => {
  const b = useBasis(s);
  return useQuery<PriceRange, ApiError>({ ...sectionQuery<PriceRange>(s, `/price?range=${range}`, undefined, b), placeholderData: (prev) => prev, enabled });
};

/** While the market is open (or in pre-open) the server keeps a copy for a minute, so the chart asks again each minute. 401/403/404 are answers, not failures. */
export const useIntraday = (s: string, range: IntradayRange, enabled = true) =>
  useQuery<Intraday, ApiError>({
    ...sectionQuery<Intraday>(s, `/intraday?range=${range}`, { staleTime: 30_000 }), enabled, placeholderData: (prev) => (prev?.range === range ? prev : undefined),
    retry: (count: number, err: ApiError) => (err.status === 202 ? count < 10 : err.status === 503 || err.status === 429 ? count < 2 : false),
    refetchInterval: (q) => (q.state.data && q.state.data.phase !== "closed" ? 60_000 : false),
  });

export const useSearchIndex = (enabled: boolean) =>
  useQuery<{ fields: string[]; rows: SearchRow[] }, ApiError>({
    queryKey: ["search-index"], queryFn: () => apiGet("/api/stocks/search-index"), enabled, staleTime: 3_600_000, gcTime: Infinity,
  });
/** Price, day change, score (or "locked" below Silver) and logo per company, joined to the name list by symbol. Private: varies by plan. */
export const useSearchQuotes = (enabled: boolean) =>
  useQuery<import("./globalSearch").Quotes, ApiError>({
    queryKey: ["search-quotes"], queryFn: () => apiGet("/api/search/quotes"), enabled, staleTime: 60_000, gcTime: 600_000, retry: 1,
  });

/** Warm a report. One try, no polling (an unprepared stock answers 202 and would otherwise be re-asked for minutes per hover; the page itself polls).
 *  With `dwell`, only the last symbol pointed at is fetched, after the pointer rests on it: sweeping a list asks for nothing. */
let dwellTimer = 0;
export function prefetchStock(qc: import("@tanstack/react-query").QueryClient, symbol: string, dwell = 0) {
  const go = () => { qc.prefetchQuery({ ...sectionQuery<Summary>(symbol, ""), retry: false }); };
  if (dwell > 0) { window.clearTimeout(dwellTimer); dwellTimer = window.setTimeout(go, dwell); } else go();
}

export type ScorePoint = { day: string; overall: number | null; pillar_quality: number | null; pillar_growth: number | null; pillar_profitability: number | null; pillar_balance: number | null; pillar_technical: number | null };
/** Score over time. Quietly absent when the plan or the deployment does not offer it. */
export const useScoreHistory = (symbol: string, enabled = true) => {
  const b = useBasis(symbol);
  return useQuery<{ points: ScorePoint[] }, ApiError>({ queryKey: ["stock", symbol, "/score-history", b], queryFn: () => apiGet(`/api/stocks/${encodeURIComponent(symbol)}${withBasis("/score-history", b)}`), enabled, retry: false, staleTime: 300_000 });
};

/** Change against the reading about a quarter ago (or the oldest one at least a week old); null until there is history. */
export function scoreChange(points: ScorePoint[] | undefined): { delta: number; since: string } | null {
  if (!points || points.length < 2) return null;
  const last = points[points.length - 1];
  if (last.overall == null) return null;
  const day = (d: string) => new Date(d + "T00:00:00").getTime(), DAY = 86_400_000;
  const old = [...points].reverse().find((p) => p.overall != null && day(last.day) - day(p.day) >= 80 * DAY) ?? points.find((p) => p.overall != null && day(last.day) - day(p.day) >= 7 * DAY);
  return old && old.overall != null ? { delta: last.overall - old.overall, since: old.day } : null;
}
