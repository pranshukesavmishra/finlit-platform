// The Basic screener's one score panel, "FinLit IQ Score": a row per pillar with its three band chips and an exact Min - Max range.
// The state is the same as before (bands q/g/p/b with the 45 / 77 / 78 edges, and the exact ranges), so saved screens and presets keep working.
import { useId, useState } from "react";
import { Icon } from "../../lib/icons";
import { BAND_ORDER, PILLARS, type Band } from "../../lib/scoreScreen";
import type { Screener } from "./useScreener";

export const IQ_TITLE = "FinLit IQ Score";
export const IQ_SUB = "Filter stocks using our multi-pillar statistical scoring model.";
const CHIP: Record<Band, string> = { low: "< 45", mid: "45 - 77", high: ">= 78" };
const ICON: Record<string, string> = { q: "quality", g: "growth", p: "profit", b: "balance" };
const NAME: Record<string, string> = { q: "Quality Score", g: "Growth Score", p: "Profitability Score", b: "Balance Sheet Score" };

function PillarRow({ s, k, say }: { s: Screener; k: "q" | "g" | "p" | "b"; say: string }) {
  const { draft, problems, setBand, setRange } = s;
  const bands = draft.bands[k], r = draft.ranges[k], name = NAME[k], id = useId();
  const has = bands.length > 0 || r.min != null || r.max != null;
  const [ticked, setTicked] = useState(has);
  const on = ticked || has;
  const toggle = () => {
    if (on) { bands.forEach((b) => setBand(k, b)); setRange(k, "min", ""); setRange(k, "max", ""); setTicked(false); } else setTicked(true);
  };
  return (
    <div className={"iq-row" + (on ? " is-on" : "")} role="group" aria-label={name} title={say}>
      <label className="iq-head">
        <input type="checkbox" checked={on} onChange={toggle} aria-controls={id} />
        <span className="iq-ico" aria-hidden="true"><Icon name={ICON[k]} /></span>
        <span className="iq-name">{name}</span>
      </label>
      <div className="iq-chips" id={id}>
        {BAND_ORDER.map((b) => {
          const sel = bands.includes(b);
          return <button key={b} type="button" className={"iq-chip" + (sel ? " is-on" : "")} aria-pressed={sel} aria-label={`${name} ${b === "low" ? "under 45" : b === "mid" ? "45 to 77" : "78 and above"}`} onClick={() => setBand(k, b)}>{CHIP[b]}</button>;
        })}
      </div>
      <div className="iq-mm">
        <label>Min<input type="number" inputMode="numeric" min={0} max={100} step={1} placeholder="0" value={r.min ?? ""} disabled={!on} aria-invalid={!!problems[k]} onChange={(e) => setRange(k, "min", e.target.value)} /></label>
        <label>Max<input type="number" inputMode="numeric" min={0} max={100} step={1} placeholder="100" value={r.max ?? ""} disabled={!on} aria-invalid={!!problems[k]} onChange={(e) => setRange(k, "max", e.target.value)} /></label>
      </div>
      {problems[k] && <p className="fgx-err iq-err" role="alert">{problems[k]}</p>}
    </div>);
}

/** The four pillar rows, in the order the screener's data has them. Put inside the group that carries the title. */
export function IqScoreRows({ s, allStrong, setAllStrong }: { s: Screener; allStrong: boolean; setAllStrong: () => void }) {
  return (<div className="iq-rows">
    <button type="button" className={"fgx-chip fgx-all" + (allStrong ? " is-on" : "")} aria-pressed={allStrong} onClick={setAllStrong}>{allStrong && <i aria-hidden="true">&#10003;</i>}Strong on all four (78 and above)</button>
    {PILLARS.map((x) => <PillarRow key={x.k} s={s} k={x.k} say={x.say} />)}
  </div>);
}

/** How many of the four pillars have a band or an exact range set. */
export const iqActive = (s: Screener) => PILLARS.filter((x) => s.draft.bands[x.k].length > 0 || s.draft.ranges[x.k].min != null || s.draft.ranges[x.k].max != null).length;
