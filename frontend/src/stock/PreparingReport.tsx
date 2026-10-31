import { useEffect, useState } from "react";
import { Link } from "react-router";
import "../styles/preparing.css";

/** What the waiting page says about progress. The numbers are the parts of the report the server has received so far (it counts them), never a guess. */
export function progressText(done?: number, total?: number): string {
  if (!total) return "Contacting the data provider…";
  if (!done) return "Asking the data provider for the filings…";
  if (done >= total) return `All ${total} data parts received. Building the report…`;
  return `Reading statements, ratios and prices… ${done} of ${total} parts ready`;
}

export type PreparingMode = "loading" | "building" | "busy" | "gaveUp" | "failed";

/** The page of a company whose report is not stored yet: its name, the shape of the report as placeholders (so nothing jumps when the real page
 *  arrives), a truthful progress line, and a hard end (failed / gave up) with "Try again" instead of waiting for ever. */
export function PreparingReport({ symbol, name, sector, mode, done, total, onRetry, elapsed }: { symbol: string; name?: string | null; sector?: string | null; mode: PreparingMode; done?: number; total?: number; onRetry?: () => void; elapsed?: number }) {
  const secs = useElapsed(mode === "building" || mode === "loading", elapsed);
  const title = mode === "failed" ? "We could not build this report right now" : mode === "gaveUp" ? "This is taking longer than usual" : mode === "busy" ? "Many reports are being prepared right now" : mode === "loading" ? "Opening the report" : "Preparing this report";
  const pct = total ? Math.min(100, Math.round(((done ?? 0) / total) * 100)) : 0;
  return (
    <div className="wrap prep" role="status" aria-live="polite" aria-busy={mode === "building" || mode === "loading"} data-mode={mode}>
      <div className="prep-head">
        <span className="prep-badge skeleton" aria-hidden="true" />
        <div className="prep-id">
          <h1 className="prep-name">{name || symbol}</h1>
          <div className="prep-sub"><b>{symbol}</b>{sector ? <span> · {sector}</span> : null}</div>
        </div>
        <div className="prep-price skeleton" aria-hidden="true" />
      </div>
      <div className="prep-card">
        <h2>{title}</h2>
        {mode === "failed" && <p>The data provider did not answer for this company. Nothing is wrong with your connection; trying again usually works.</p>}
        {mode === "gaveUp" && <p>The report is still being built. You can keep waiting or check again.</p>}
        {mode === "busy" && <p>Yours is in the queue and will open by itself.</p>}
        {(mode === "building" || mode === "loading") && (
          <>
            <p>{mode === "loading" ? "One moment." : <>{name || symbol} is not one of the companies we keep ready in advance, so we are building its report from the latest filings right now. The first time usually takes under half a minute; after that it stays stored and opens instantly.</>}</p>
            <div className="prep-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label="Report progress"><span style={{ width: `${pct}%` }} /></div>
            <p className="prep-hint">{progressText(done, total)}{secs > 3 ? <span className="prep-sec"> · {secs} s</span> : null}</p>
          </>
        )}
        {(mode === "failed" || mode === "gaveUp") && onRetry && <button type="button" className="btn primary" onClick={onRetry}>Try again</button>}
        {mode === "failed" && <Link className="btn" to="/research">Browse research</Link>}
      </div>
      <div className="prep-skel" aria-hidden="true">
        <div className="skeleton prep-chart" />
        <div className="prep-grid"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div>
        <div className="skeleton prep-table" />
      </div>
    </div>
  );
}

/** Seconds since the page started waiting (a prop wins, for tests). */
function useElapsed(running: boolean, fixed?: number): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!running || fixed !== undefined) return;
    const t = setInterval(() => setN((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [running, fixed]);
  return fixed ?? n;
}
