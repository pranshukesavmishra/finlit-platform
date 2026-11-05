// The Basic screener's one score panel, "FinLit IQ Score": a row per pillar with its three band chips and an exact Min - Max range.
// The state is the same as before (bands q/g/p/b with the 45 / 77 / 78 edges, and the exact ranges), so saved screens and presets keep working.
import { useId, useState } from "react";
import { Icon } from "../../lib/icons";
import { BAND_ORDER, IQ_LABELS, IQ_LABEL_SAY, IQ_LABEL_WORD, PILLARS, type Band, type BandKey } from "../../lib/scoreScreen";
import type { Screener } from "./useScreener";

export const IQ_TITLE = "FinLit IQ Score";
export const IQ_SUB = "Filter stocks using our multi-pillar statistical scoring model.";
const CHIP: Record<Band, string> = { low: "< 45", mid: "45 - 77", high: ">= 78" };
const ICON: Record<string, string> = { q: "quality", g: "growth", p: "profit", b: "balance", t: "line", o: "bars" };
const NAME: Record<string, string> = { q: "Quality Score", g: "Growth Score", p: "Profitability Score", b: "Balance Sheet Score", t: "Technical Score", o: "Total FinLit IQ Score" };
/** The two rows after the four pillars: the price-trend pillar and the overall FinLit IQ (the average of the pillars that are available, Technical included). */
const EXTRA: { k: "t" | "o"; say: string }[] = [
  { k: "t", say: "The Technical pillar of the FinLit IQ: how the price is trending against its 50 and 200 day averages, and its momentum." },
  { k: "o", say: "The FinLit IQ shown on the company page: the average of the pillar scores that are available, Technical included." },
];

/** The three shortcut chips of a score row. Shared by the Basic and Advanced panels, so both look and behave the same. */
export function BandChips({ id, name, bands, onToggle }: { id?: string; name: string; bands: Band[]; onToggle: (b: Band) => void }) {
  return (
    <div className="iq-chips" id={id}>
      {BAND_ORDER.map((b) => {
        const sel = bands.includes(b);
        return <button key={b} type="button" className={"iq-chip" + (sel ? " is-on" : "")} aria-pressed={sel} aria-label={`${name} ${b === "low" ? "under 45" : b === "mid" ? "45 to 77" : "78 and above"}`} onClick={() => onToggle(b)}>{CHIP[b]}</button>;
      })}
    </div>);
}

function PillarRow({ s, k, say }: { s: Screener; k: BandKey; say: string }) {
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
      <BandChips id={id} name={name} bands={bands} onToggle={(b) => setBand(k, b)} />
      <div className="iq-mm">
        <label>Min<input type="number" inputMode="numeric" min={0} max={100} step={1} placeholder="0" value={r.min ?? ""} disabled={!on} aria-invalid={!!problems[k]} onChange={(e) => setRange(k, "min", e.target.value)} /></label>
        <label>Max<input type="number" inputMode="numeric" min={0} max={100} step={1} placeholder="100" value={r.max ?? ""} disabled={!on} aria-invalid={!!problems[k]} onChange={(e) => setRange(k, "max", e.target.value)} /></label>
      </div>
      {problems[k] && <p className="fgx-err iq-err" role="alert">{problems[k]}</p>}
    </div>);
}

/** The rating chips, the four pillar rows, then the Technical and Total rows. Put inside the group that carries the title. */
export function IqScoreRows({ s, allStrong, setAllStrong }: { s: Screener; allStrong: boolean; setAllStrong: () => void }) {
  const on = s.draft.iqLabels;
  return (<div className="iq-rows">
    <div className="iq-rating" role="group" aria-label="FinLit IQ rating">
      <span className="iq-rl">Rating</span>
      <div className="fgx-chips">
        {IQ_LABELS.map((l) => <button key={l} type="button" className={"fgx-chip" + (on.includes(l) ? " is-on" : "")} aria-pressed={on.includes(l)} title={IQ_LABEL_SAY[l]} onClick={() => s.setIqLabel(l)}>{on.includes(l) && <i aria-hidden="true">&#10003;</i>}{IQ_LABEL_WORD[l]}</button>)}
      </div>
    </div>
    <button type="button" className={"fgx-chip fgx-all" + (allStrong ? " is-on" : "")} aria-pressed={allStrong} onClick={setAllStrong}>{allStrong && <i aria-hidden="true">&#10003;</i>}Strong on all four (78 and above)</button>
    {[...PILLARS, ...EXTRA].map((x) => <PillarRow key={x.k} s={s} k={x.k} say={x.say} />)}
  </div>);
}

/** How many things are set in the panel: the rating chips (as one), and each pillar, Technical or Total row with a band or an exact range. */
export const iqActive = (s: Screener) => (s.draft.iqLabels.length ? 1 : 0) + [...PILLARS, ...EXTRA].filter((x) => s.draft.bands[x.k].length > 0 || s.draft.ranges[x.k].min != null || s.draft.ranges[x.k].max != null).length;
