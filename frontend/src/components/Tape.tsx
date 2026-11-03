import { useIndices } from "../lib/indices";
import { nf, MINUS, dateIN } from "../lib/format";

/** Market strip at the top of every page: the key indices (NIFTY 50, SENSEX, Bank, Midcap, Smallcap, IT, VIX) from /api/indices,
 *  refreshed every minute. Hidden until the levels arrive. */
export function Tape() {
  const idx = useIndices();
  const items = (idx.data?.key || []).map((c) => idx.data?.items.find((r) => r.code === c)).filter((r) => r && r.close != null)
    .map((r) => ({ name: r!.name.replace(/^nifty/i, "NIFTY").replace(/^bse /i, ""), price: r!.close as number, c: r!.changePct ?? 0 }));
  if (!items.length) return null;
  const row = [...items, ...items];
  const live = !!idx.data?.live && !!idx.data?.marketOpen, asOf = idx.data?.asOf;
  return (
    <div className="tape" aria-label="Market snapshot">
      <span className={"tape-st" + (live ? " live" : "")} title={live ? "Levels are live during the market session" : "Last close; live levels return when the market opens"}>{live ? "LIVE" : asOf ? `Close · ${dateIN(asOf, { day: "numeric", month: "short" })}` : "Last close"}</span>
      <div className="tape-track">
        {row.map((i, k) => (
          <span key={k} aria-hidden={k >= items.length || undefined}><b>{i.name}</b>{nf(i.price)}{" "}
            <span className={i.c > 0 ? "u" : i.c < 0 ? "d" : ""}>{i.c > 0 ? "▲ +" : i.c < 0 ? "▼ " + MINUS : ""}{nf(Math.abs(i.c))}%</span></span>
        ))}
      </div>
    </div>
  );
}
