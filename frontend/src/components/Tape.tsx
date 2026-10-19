import { useQuery } from "@tanstack/react-query";
import { getTicker } from "../lib/siteApi";
import { useIndices } from "../lib/indices";
import { nf, MINUS } from "../lib/format";

/** Market strip at the top of every page: the key indices (NIFTY 50, SENSEX, Bank, Midcap, Smallcap, IT, VIX) from /api/indices,
 *  refreshed every minute, followed by the site backend's stock ticker when that feed is up. Hidden when neither answers. */
export function Tape() {
  const idx = useIndices();
  const { data } = useQuery({ queryKey: ["ticker"], queryFn: getTicker, refetchInterval: 60_000, staleTime: 30_000, retry: 1 });
  const key = (idx.data?.key || []).map((c) => idx.data?.items.find((r) => r.code === c)).filter((r) => r && r.close != null)
    .map((r) => ({ name: r!.name.replace(/^nifty/i, "NIFTY").replace(/^bse /i, ""), price: r!.close as number, c: r!.changePct ?? 0, rupee: false }));
  const stocks = (data?.items || []).filter((i) => i.price != null).map((i) => ({ name: i.name || i.symbol, price: i.price as number, c: i.changePercent ?? i.changePct ?? 0, rupee: true }));
  const items = [...key, ...stocks];
  if (!items.length) return null;
  const row = [...items, ...items];
  return (
    <div className="tape" aria-label="Market snapshot">
      <div className="tape-track">
        {row.map((i, k) => (
          <span key={k} aria-hidden={k >= items.length || undefined}><b>{i.name}</b>{i.rupee ? "₹" : ""}{nf(i.price)}{" "}
            <span className={i.c > 0 ? "u" : i.c < 0 ? "d" : ""}>{i.c > 0 ? "▲ +" : i.c < 0 ? "▼ " + MINUS : ""}{nf(Math.abs(i.c))}%</span></span>
        ))}
      </div>
    </div>
  );
}
