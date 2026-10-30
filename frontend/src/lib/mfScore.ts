// FinLit Mutual Fund Health Score: types, hooks and the words (the model is in backend/finlit/mfscore, the plain-language page is /methodology/mf-score).
// The score DESCRIBES a fund's health from its past NAVs, costs and holdings. It never advises: no buy, sell or hold wording anywhere in this file.
import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "./api";
import { scoreBand, type ScoreBand } from "./scoreBands";
import { nf } from "./format";

export const MF_SCORE_NAME = "FinLit Mutual Fund Health Score";
export const MF_SCORE_COMPLIANCE = "Describes the fund's health from its past NAVs, costs and holdings; not a recommendation. Information only, not investment advice.";
export const MF_METHOD_URL = "/methodology/mf-score";
export const PILLAR_HELP: Record<string, string> = {
  performance: "Did the fund beat funds like it, over how long, and month after month?",
  risk: "How bumpy was the ride and how deep were the falls, against similar funds?",
  cost: "How much of the return is paid away, and what does it cost to leave?",
  quality: "Is the fund proven, big enough and built soundly?",
};

export type ScoreState = "A" | "Z" | "S" | "F" | "N";
export type ScoreLine = { id: string; label: string; text: string; points: number; groupValue: number; effect: number; state: string };
export type ScoreMetric = { id: string; label: string; pillar: string; state: ScoreState; value: number | null; own: number | null; peer: number | null; peerN: number | null; points: number | null; weight: number | null; groupValue: number | null; why: string | null };
export type ScorePillar = { key: "performance" | "risk" | "cost" | "quality"; name: string; weight: number; score: number | null; allNotApplicable?: boolean };
export type FundScore = {
  locked: boolean; plan?: string; detail?: string; key?: string; kind?: string; group: string | null; groupName: string | null; fundPlan?: string | null;
  status: "RATED" | "PROVISIONAL" | "NOT RATED" | "NOT SCORED" | null; reason?: string | null; final: number | null; label: string | null; cap?: string | null; rawFinal?: number | null;
  pillars: ScorePillar[]; confidence?: number | null; months?: number; flags?: string[]; categoryLabel?: string | null; runDate?: string; nearIdentical?: boolean;
  rank?: { rank: number; of: number; scope: string; percentile: number | null; categoryLabel: string | null; plan: string } | null;
  peers?: { kind: string | null; n: number; text: string | null };
  family?: { key: string | null; index: string | null } | null;
  reasons?: { strengths: ScoreLine[]; watchouts: ScoreLine[]; gaps: { id: string; label: string; why: string; text: string }[]; notApplicable: { id: string; label: string; text: string }[]; substitutions: { id: string; label: string; text: string }[] };
  filled?: { n: number; of: number }; metrics?: ScoreMetric[]; inherited?: { code?: number; symbol?: string; name: string; why: string } | null;
  disclaimer: string; method: string; model: string;
};
export type ScoreItem = { code: number | null; symbol: string | null; plan: string; group: string | null; final: number | null; label: string | null; status: string | null; reason: string | null;
  pillars: Record<string, number | null> | null; rank: number | null; rankOf: number | null; flags: string[]; confidence: number | null };
export type ScoreList = { locked: boolean; items: ScoreItem[]; total: number | null };
/** One sub-category of the Funds dashboard: median of the scored Direct-plan funds, how many, and the counts in the three colour bands. */
export type CategoryScore = { median: number; n: number; green: number; orange: number; red: number };
export type CategoryScores = { locked: boolean; plan?: string; runDate: string | null; items: Record<string, CategoryScore>; disclaimer: string; method: string };

export const useFundScore = (code: number, kind: "mf" | "etf" = "mf", symbol = "") =>
  useQuery<FundScore, ApiError>({
    queryKey: ["mfscore", kind, kind === "etf" ? symbol : code], staleTime: 300_000, retry: 1,
    queryFn: () => apiGet<FundScore>(kind === "etf" ? `/api/mf/etf/${encodeURIComponent(symbol)}/score` : `/api/mf/${code}/score`), enabled: kind === "etf" ? !!symbol : code > 0,
  });
/** Scores of the funds on a page (up to 100 codes): one small request, private to the plan. */
export const useScores = (codes: number[], enabled = true) => {
  const ids = [...new Set(codes)].slice(0, 100).sort((a, b) => a - b).join(",");
  return useQuery<ScoreList, ApiError>({ queryKey: ["mfscore", "list", ids], queryFn: () => apiGet<ScoreList>(`/api/mf/scores?codes=${ids}`), enabled: enabled && ids.length > 0, staleTime: 300_000, retry: 1 });
};

/** Scores of the ETFs on a list page (up to 100 symbols): private to the plan, null fields below Gold. */
export const useEtfScores = (symbols: string[], enabled = true) => {
  const ids = [...new Set(symbols.map((x) => x.toUpperCase()))].slice(0, 100).sort().join(",");
  return useQuery<ScoreList, ApiError>({ queryKey: ["mfscore", "etf-list", ids], queryFn: () => apiGet<ScoreList>(`/api/mf/scores?symbols=${encodeURIComponent(ids)}`), enabled: enabled && ids.length > 0, staleTime: 300_000, retry: 1 });
};
/** Median score, count and band split per category for the /funds cards. Gold only; below that the server sends `locked` and no number. */
export const useCategoryScores = (enabled = true) =>
  useQuery<CategoryScores, ApiError>({ queryKey: ["mfscore", "categories"], queryFn: () => apiGet<CategoryScores>("/api/mf/scores/categories"), enabled, staleTime: 300_000, retry: 1 });

export const SCORE_BANDS = [["Poor", 0, 35], ["Weak", 35, 50], ["Average", 50, 65], ["Healthy", 65, 80], ["Strong", 80, 100]] as const;
export const scoreText = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(1));
export const bandOf = (v: number | null | undefined): ScoreBand => scoreBand(v);

/** "12 of 48 in Large Cap (Direct plan)", or the tracking family for index funds and ETFs. */
export function rankText(r: NonNullable<FundScore["rank"]>, family?: FundScore["family"]): string {
  if (r.scope === "fam") return `${r.rank} of ${r.of} funds tracking ${family?.index || "the same index"} (${r.plan === "ETF" ? "ETFs" : r.plan + " plan"})`;
  return `${r.rank} of ${r.of} in ${r.categoryLabel || "its category"} (${r.plan} plan)`;
}
export const percentileText = (p: number | null | undefined) => (p == null ? null : `Higher than ${p}% of the other funds in that group.`);

export const STATUS_TEXT: Record<string, string> = {
  RATED: "Rated: enough history and data behind the score.",
  PROVISIONAL: "Provisional: a short history or limited data, so the label is held at Healthy or below.",
  "NOT RATED": "Not rated.",
};
/** The one line that says what share of the measures had real data. */
export const confidenceText = (c: number | null | undefined) => (c == null ? "" : `${Math.round(c * 100)}% of the weight behind this score rests on real data.`);
export const filledText = (f?: { n: number; of: number }) =>
  !f || f.n === 0 ? "" : `${f.n} of ${f.of} measures used the group value because data was missing.`;
export const FLAG_TEXT: Record<string, string> = {
  NAV_BREAK: "Suspected NAV break: some month-end NAVs were missing or invalid, so some measures were left out.",
  FROZEN_NAV: "The NAV barely moved over three years, which looks stale or frozen, so the swing and fall measures were left out.",
  PROVISIONAL: "Provisional status.",
  WEAK_CAP: "A weak Risk or Quality score held the total down.",
  PILLAR_ALL_N: "One group of measures did not apply to this fund and counts as neutral.",
  NEAR_IDENTICAL: "Funds in this category are near-identical: they differ by a few hundredths of a percentage point, so cost carries the most weight.",
};
export const STATE_TEXT: Record<string, string> = { A: "Actual", Z: "Zero points (loss)", S: "Substituted", F: "Group value used", N: "Not applicable" };

/** The weights of each group, percent of the final score (Performance, Risk, Cost, Quality): the same table as backend/finlit/mfscore/sheets.py. */
export const GROUP_WEIGHTS: { group: string; name: string; w: [number, number, number, number] }[] = [
  { group: "EQ-LARGE", name: "Equity: Large Cap", w: [35, 30, 15, 20] }, { group: "EQ-BROAD", name: "Equity: Flexi, Multi, Large & Mid, Value, Contra, Focused, Dividend Yield, ELSS", w: [35, 30, 15, 20] },
  { group: "EQ-MID", name: "Equity: Mid Cap", w: [35, 30, 15, 20] }, { group: "EQ-SMALL", name: "Equity: Small Cap", w: [35, 30, 15, 20] }, { group: "EQ-THEME", name: "Equity: Sectoral / Thematic", w: [35, 30, 15, 20] },
  { group: "DB-CASH", name: "Debt: Overnight, Liquid, Money Market, Ultra Short, Low Duration", w: [20, 30, 35, 15] }, { group: "DB-ACCRUAL", name: "Debt: Short Duration, Banking & PSU, Corporate Bond, Floater", w: [25, 35, 20, 20] },
  { group: "DB-DURATION", name: "Debt: Medium to Long Duration, Dynamic Bond, Gilt", w: [30, 35, 15, 20] }, { group: "DB-CREDIT", name: "Debt: Credit Risk", w: [25, 40, 15, 20] },
  { group: "HY-ARB", name: "Hybrid: Arbitrage", w: [20, 20, 45, 15] }, { group: "HY-CONS", name: "Hybrid: Conservative, Equity Savings", w: [25, 35, 20, 20] },
  { group: "HY-AGGR", name: "Hybrid: Aggressive, Balanced", w: [35, 30, 15, 20] }, { group: "HY-DYN", name: "Hybrid: Dynamic Allocation, Multi Asset", w: [30, 35, 15, 20] },
  { group: "SOL", name: "Solution oriented: Retirement, Children's", w: [30, 35, 15, 20] }, { group: "OT-PASSIVE", name: "Others: Index funds and ETFs", w: [20, 15, 40, 25] }, { group: "OT-OTHER", name: "Others: Fund of funds and the rest", w: [30, 30, 20, 20] },
];

/** The two measures only ETFs have, called out on the ETF page. `tone`: lift or watch when the measure is one of the reasons listed, else neutral; gap when it could not be measured. */
export type EtfMeasure = { id: "ETF_LIQUIDITY" | "ETF_PREMIUM"; label: string; tone: "lift" | "watch" | "neutral" | "gap"; points: number | null; text: string };
const ETF_IDS = ["ETF_LIQUIDITY", "ETF_PREMIUM"] as const;
export function etfMeasures(s: Pick<FundScore, "final" | "metrics" | "reasons">): EtfMeasure[] {
  if (s.final == null) return [];
  const out: EtfMeasure[] = [];
  for (const id of ETF_IDS) {
    const m = s.metrics?.find((x) => x.id === id);
    if (!m || m.state === "N") continue;
    const label = m.label || (id === "ETF_LIQUIDITY" ? "How easily it trades" : "Price against NAV");
    if (m.state === "F") {
      const g = s.reasons?.gaps.find((x) => x.id === id);
      out.push({ id, label, tone: "gap", points: null, text: `Not measured: ${g?.text || "no usable value"}. The group value was used.` });
      continue;
    }
    const lift = s.reasons?.strengths.find((x) => x.id === id), watch = s.reasons?.watchouts.find((x) => x.id === id);
    let text = (lift || watch)?.text ?? "";
    if (!text && m.own != null) {
      text = id === "ETF_LIQUIDITY" ? `It traded about ₹${nf(m.own, m.own >= 10 ? 0 : 2)} crore a day on the exchange.`
        : m.own === 0 ? "Its exchange price matched its NAV on the NAV date."
          : `Its exchange price was ${nf(Math.abs(m.own), 2)}% ${m.own > 0 ? "above" : "below"} its NAV on the NAV date.`;
    }
    out.push({ id, label, tone: lift ? "lift" : watch ? "watch" : "neutral", points: m.points, text });
  }
  return out;
}
