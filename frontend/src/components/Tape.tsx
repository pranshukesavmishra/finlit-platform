import { useState } from "react";
import { useIndices } from "../lib/indices";
import { nf, MINUS } from "../lib/format";

/** One site-wide index feed, polled every minute. Provider closing prices are never labelled live. */
export function Tape() {
  const idx = useIndices();
  const [paused, setPaused] = useState(false);
  const items = (idx.data?.key || []).flatMap(code => {
    const row = idx.data?.items.find(item => item.code === code);
    return row && row.close != null && Number.isFinite(row.close) ? [row] : [];
  });
  const live = !!idx.data?.marketOpen && items.some(row => row.source === "dhan");
  return (
    <div className={"tape" + (paused ? " is-paused" : "")} aria-label="Market snapshot">
      <span className={"tape-state" + (live ? " is-live" : "")} title={items.length ? `${live ? "Live prices where available; other indices show their last close" : "Last reported closing prices"}. Feed date: ${idx.data?.asOf || "not supplied"}. Refreshes every minute.` : undefined}>
        {items.length ? live ? "Live / close" : "Last close" : idx.isLoading ? "Loading prices…" : "Prices unavailable"}
      </span>
      {items.length > 0 && <>
        <div className="tape-window" tabIndex={0} aria-label="Index prices. Pause or hover to read; scroll sideways for more.">
          <div className="tape-track">
            {[0, 1].map(copy => <div className="tape-group" key={copy} aria-hidden={copy === 1 ? true : undefined}>
              {items.map(row => <span className="tape-item" key={row.code} title={`${row.source === "dhan" ? "Dhan" : "FinEdge"} · ${row.time || row.date || "Date not supplied"}`}>
                <b>{row.name.replace(/^nifty/i, "NIFTY").replace(/^bse /i, "")}</b>{nf(row.close!)}{" "}
                <span className={row.changePct != null && row.changePct > 0 ? "u" : row.changePct != null && row.changePct < 0 ? "d" : ""}>
                  {row.changePct == null ? MINUS : `${row.changePct > 0 ? "▲ +" : row.changePct < 0 ? "▼ " + MINUS : ""}${nf(Math.abs(row.changePct))}%`}
                </span>
              </span>)}
            </div>)}
          </div>
        </div>
        <button type="button" className="tape-toggle" aria-label={paused ? "Play market ticker" : "Pause market ticker"} aria-pressed={paused} onClick={() => setPaused(value => !value)}>{paused ? "▶" : "Ⅱ"}</button>
      </>}
    </div>
  );
}
