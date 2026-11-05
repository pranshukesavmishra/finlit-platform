// The shape of POST /api/diversification (backend/finlit/diversification/calc.py). Names only go in; every figure comes back with its basis.
export type Horizon = "weekly" | "monthly" | "yearly";
export type Excluded = { symbol: string; reason: "history" | "noPrices" | "unknown" | "overlap"; weeks?: number; months?: number };
export type Score = { value: number; unrounded: number; band: string; coMovement: number; sectorSpread: number; effectiveSectors: number };
export type Headline = { effectiveStocks: number; effectiveStocksRounded: number; avgCorrelation: number };
export type Cluster = { symbols: string[]; avgCorrelation: number };
export type SpreadStock = { symbol: string; name: string; sector: string; size: string | null; group: string | null };
export type Spread = {
  sectors: { name: string; count: number }[]; size: { Large: number; Mid: number; Small: number }; sizeUnknown: string[];
  groups: { name: string; symbols: string[] }[]; unclassified: string[]; largestSector: { name: string; count: number; share: number } | null; stocks: SpreadStock[];
};
export type Pair = { pair: [string, string]; recent: number; longRun: number; change: number; flag: boolean; direction: "more" | "less" | null };
export type Recent = {
  recent: { weeks: number; effectiveStocks: number; avgCorrelation: number }; longRun: { weeks: number; effectiveStocks: number; avgCorrelation: number };
  largestRises: Pair[]; largestFalls: Pair[]; flagged: Pair[];
};
export type RiskRows = { stocks: { symbol: string; pct: number; weightPct: number }[]; sectors: { name: string; pct: number; amountPct: number }[] };
export type Basket = { volPct: number; maxDrawdownPct: number; beta: number; stressAvgPct: number; riskShare: RiskRows };
export type TiltPart = { part: string; listAverage: number | null; universeMedian: number | null; avgPercentile: number | null; lean: "high" | "low" | "typical" | null; wording: string | null; stocks: number };
export type StyleTilt = { universe: number; notRated: string[]; parts: TiltPart[]; sentence?: string } | { locked: string; reason: string };
export type AsOf = { fromWeek?: string; toWeek?: string; weeks?: number; fromMonth?: string; toMonth?: string; months?: number; frequency: Horizon; label: string; effectiveObservations?: number };
export type PairRow = { pair: [string, string]; correlation: number };

export type Diversification = {
  horizon: Horizon; scoreVersion: string; included: number; excluded: Excluded[]; spread: Spread; names: Record<string, string>;
  needsThree?: boolean; viewNote?: string; indicative?: boolean;
  asOf?: AsOf; score?: Score; headline?: Headline; clusters?: Cluster[]; overlap?: { symbol: string; avgCorrelation: number }[];
  matrix?: { symbols: string[]; values: number[][] } | null;
  market?: { benchmark: string; betaEqual: number; betaMcap?: number | null; benchmarkReturns?: number; stocks?: { symbol: string; beta: number }[] };
  stress?: { worstWeeks: number; benchmarkAvgPct: number; equalAvgPct: number; mcapAvgPct: number | null; stocks: { symbol: string; fellMoreThanIndex: number }[] };
  riskShare?: { equal: RiskRows; mcap: RiskRows | null };
  basket?: { equal: Basket; mcap: Basket | null; benchmark: { volPct: number; maxDrawdownPct: number } };
  mcapMissing?: string[];
  recentVsLongRun?: Recent; styleTilt?: StyleTilt; mostRelated?: PairRow[]; leastRelated?: PairRow[];
};
