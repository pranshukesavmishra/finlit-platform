// Filter controls shared by the two score screeners. Each takes the screener state (`s`) from useScreener.
import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router";
import { BANDS, BAND_ORDER, type RangeKey } from "../../lib/scoreScreen";
import { useFocusTrap } from "../../lib/focusTrap";
import type { Screener } from "./useScreener";

/** Exact minimum and maximum boxes for one 0 to 100 score. */
export function RangeBox({ s, k, label }: { s: Screener; k: RangeKey; label: string }) {
  const { draft, problems, setRange } = s;
  return (
    <div className="sx-range" role="group" aria-label={`${label} score, exact range`}>
      <label>Min<input type="number" inputMode="numeric" min={0} max={100} step={1} value={draft.ranges[k].min ?? ""} onChange={(e) => setRange(k, "min", e.target.value)} placeholder="0" aria-invalid={!!problems[k]} /></label>
      <span aria-hidden="true">to</span>
      <label>Max<input type="number" inputMode="numeric" min={0} max={100} step={1} value={draft.ranges[k].max ?? ""} onChange={(e) => setRange(k, "max", e.target.value)} placeholder="100" aria-invalid={!!problems[k]} /></label>
      {problems[k] && <p className="sx-err" role="alert">{problems[k]}</p>}
    </div>);
}
export function Slider({ s, k, end, label }: { s: Screener; k: RangeKey; end: "min" | "max"; label: string }) {
  const dflt = end === "min" ? 0 : 100, cur = s.draft.ranges[k][end];
  return (<label className="pzs-sl">{end === "min" ? "From" : "To"}<input type="range" min={0} max={100} step={1} value={cur ?? dflt} aria-label={`${label} slider, ${end === "min" ? "lowest" : "highest"} score`}
    onChange={(e) => s.setRange(k, end, Number(e.target.value) === dflt ? "" : e.target.value)} /><output>{cur ?? dflt}</output></label>);
}
/** Score bands (Under 45, 45 to 77, 78 and above) as checkboxes, with the exact range under them. */
export function BandBoxes({ s, k, label }: { s: Screener; k: "f" | "t"; label: string }) {
  return (
    <fieldset className="ss-fs"><legend>{label} score</legend>
      {BAND_ORDER.map((b) => <label key={b}><input type="checkbox" checked={s.draft.bands[k].includes(b)} onChange={() => s.setBand(k, b)} /><span>{BANDS[b].label}</span></label>)}
      <RangeBox s={s} k={k} label={label} />
    </fieldset>);
}

/** The "How scores work" dialog frame: focus trap, Escape to close; the page supplies the definitions. */
export function HowDialog({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, true);
  useEffect(() => { ref.current?.scrollTo?.(0, 0); }, []);   // focus lands on the last link; keep the title in view
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === "Escape" && onClose(); document.addEventListener("keydown", k); return () => document.removeEventListener("keydown", k); }, [onClose]);
  return (<>
    <div className="scrim" onClick={onClose} />
    <div className="modal sx-how" role="dialog" aria-modal="true" aria-labelledby="sx-how-t" ref={ref}>
      <button className="modal-x" aria-label="Close" onClick={onClose}>×</button>
      <h3 id="sx-how-t">How scores work</h3>
      {children}
      <p className="muted">This describes financial health and price trend from filings and prices. It is information, not a recommendation. <Link to="/glossary">See the glossary</Link>.</p>
    </div>
  </>);
}
