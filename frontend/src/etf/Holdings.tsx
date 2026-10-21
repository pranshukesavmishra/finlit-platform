// "What it invests in" for one ETF. The section itself (donut, "Other holdings", full table, concentration, sector and asset split, monthly changes)
// is the shared one in src/holdings, also used by mutual funds. This file only fetches the portfolio and says so when it cannot.
import { HoldingsSection } from "../holdings";
import { useEtfPortfolio } from "../lib/etf";
import { Skeleton } from "./common";

export function EtfHoldings({ symbol }: { symbol: string }) {
  const { data, isLoading, isError } = useEtfPortfolio(symbol);
  if (isLoading) return <section className="card etf-sec" aria-label="What it invests in"><Skeleton rows={3} /></section>;
  return <HoldingsSection portfolio={isError || !data ? { unavailable: "The portfolio could not be loaded right now. Nothing was changed; please try again." } : data} title="What it invests in" unit="ETF" />;
}
