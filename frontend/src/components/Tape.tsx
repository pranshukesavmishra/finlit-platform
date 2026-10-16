import { useQuery } from "@tanstack/react-query";
import { getTicker } from "../lib/siteApi";
import { nf, MINUS } from "../lib/format";

/** NIFTY 50 live strip from the site backend (/api/market-ticker, Upstox). Hidden when the feed is unavailable. */
export function Tape() {
  const { data } = useQuery({ queryKey: ["ticker"], queryFn: getTicker, refetchInterval: 60_000, staleTime: 30_000, retry: 1 });
  const items = (data?.items || []).filter((i) => i.price != null);
  if (!items.length) return null;
  const row = [...items, ...items];
  return (
    <div className="tape" aria-label="Market snapshot">
      <div className="tape-track">
        {row.map((i, k) => {
          const c = i.changePercent ?? i.changePct ?? 0;
          return (
            <span key={k}><b>{i.name || i.symbol}</b>₹{nf(i.price as number)}{" "}
              <span className={c > 0 ? "u" : c < 0 ? "d" : ""}>{c > 0 ? "▲ +" : c < 0 ? "▼ " + MINUS : ""}{nf(c)}%</span></span>
          );
        })}
      </div>
    </div>
  );
}
