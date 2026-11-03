// Under a company's tags: the top-rated and theme screens it is in (for example "Emerging tech"), each a link to that screen. Gold, like the screens; nothing is shown when the
// company is in none, or before the first nightly run. It states a fact about a list the company is on; it is not a recommendation.
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ApiError, apiGet } from "../lib/api";
import { dateIN } from "../lib/format";
import { useGold } from "../lib/premium";
import { Row } from "./HeaderScore";

type ScreensFor = { symbol: string; screens: { id: string; name: string; group: string; asOf: string | null }[]; ready: boolean; asOf: string | null };

export function ScreenBadges({ symbol }: { symbol: string }) {
  const gold = useGold();
  const q = useQuery<ScreensFor, ApiError>({ queryKey: ["screens-for", symbol], enabled: gold && !!symbol, staleTime: 60 * 60_000, retry: false,
    queryFn: () => apiGet<ScreensFor>(`/api/screener/presets/for/${encodeURIComponent(symbol)}`) });
  const screens = q.data?.screens ?? [];
  if (!gold || q.isError || !screens.length) return null;
  return (
    <Row label="In screens">
      <div className="hs-screens" role="group" aria-label="Prebuilt screens this company is in">
      {screens.map((s) => <Link key={s.id} className="hs-sc" to={`/advanced-score-screener?preset=${encodeURIComponent(s.id)}`} title={`${s.name}${s.asOf ? `, as of ${dateIN(s.asOf)}` : ""}. A screen narrows a list; it is not a recommendation.`}>{s.name}</Link>)}
      </div>
    </Row>
  );
}
