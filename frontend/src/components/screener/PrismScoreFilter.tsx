// The Advanced screener's one score panel, "FinLit Prism Score": a Fundamental Score part (rating chips and a Min - Max row for each of the four Prism pillars and
// for the Total Fundamental Score) and a Technical Score part (the short-term and long-term trend views). The state and the address parameters are the ones the
// screener already had: labels (pl), the ranges zf / zv / zq / zr, the overall range z (the Prism's overall figure, which is the weighted result of the four
// pillars and leaves the price-trend views out) and the tech bands (st, lt), so saved screens and prebuilt screens keep working.
import { useId, useState, type ReactNode } from "react";
import { Icon } from "../../lib/icons";
import { TECH_BANDS, rangeToBands, TECH_BAND_ORDER, TECH_KEYS, TECH_NAMES } from "../../lib/scoreScreen";
import { LABEL_WORD, PRISM_LABELS, PRISM_PARTS, type PrismRangeKey } from "../../lib/scorePrism";
import { BandChips } from "./IqScoreFilter";
import { Chev, RangeRow } from "./FilterGroup";
import type { Screener } from "./useScreener";

export const PRISM_TITLE_PLAIN = "FinLit Prism Score";
export const PRISM_TITLE = <>FinLit <span className="pzf-mint">Prism Score</span></>;
export const PRISM_SUB = "Filter stocks using our fundamental and technical scoring model.";
export const TOTAL_FUND = "Total Fundamental Score";
export const FUND_TITLE = "Fundamental Score";
export const TECH_TITLE = "Technical Score";
/** The five rows, in the order the founder set: the four pillars, then the total. */
export const FUND_ROWS: { range: PrismRangeKey; label: string; say: string }[] = [
  ...PRISM_PARTS.map((x) => ({ range: x.range, label: x.label, say: x.say })),
  { range: "z", label: TOTAL_FUND, say: "The overall result of the four pillars above, weighed into one number from 0 to 100. The price-trend views are not part of it." },
];
const RANGE_KEYS = FUND_ROWS.map((x) => x.range);

/** How many things are set in the panel: rating chips, ranges and technical bands. */
export const prismActive = (s: Screener) => s.draft.labels.length + RANGE_KEYS.filter((k) => s.draft.ranges[k].min != null || s.draft.ranges[k].max != null).length + s.draft.tech.st.length + s.draft.tech.lt.length;

function Sub({ title, icon, active, children }: { title: string; icon: string; active: number; children: ReactNode }) {
  const [open, setOpen] = useState(true), id = useId();
  return (
    <section className={"pzf-sub" + (open ? " is-open" : "")}>
      <h4 className="pzf-sh"><button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
        <span className="iq-ico" aria-hidden="true"><Icon name={icon} /></span><span className="pzf-st">{title}</span>{active > 0 && <span className="fgx-badge">{active} active</span>}<Chev /></button></h4>
      <div id={id} className="pzf-sb" hidden={!open}>{children}</div>
    </section>);
}

/** Put inside the FilterGroup that carries the "FinLit Prism Score" title. */
export function PrismScoreRows({ s }: { s: Screener }) {
  const { draft } = s;
  const fundActive = draft.labels.length + RANGE_KEYS.filter((k) => draft.ranges[k].min != null || draft.ranges[k].max != null).length;
  return (<div className="pzf">
    <Sub title={FUND_TITLE} icon="bars" active={fundActive}>
      <p className="fgx-hint">Pick the ratings you want, then set the lowest and highest value (0 to 100) for any of the five pillars.</p>
      <div className="fgx-chips pzf-chips" role="group" aria-label="Rating">
        {PRISM_LABELS.map((l) => <button key={l} type="button" className={"fgx-chip" + (draft.labels.includes(l) ? " is-on" : "")} aria-pressed={draft.labels.includes(l)} onClick={() => s.setLabel(l)}>{draft.labels.includes(l) && <i aria-hidden="true">&#10003;</i>}{l === "NOT RATED" ? "Not rated" : LABEL_WORD[l]}</button>)}
      </div>
      {FUND_ROWS.map((x) => <div key={x.range} title={x.say}><RangeRow label={x.label} group={x.range === "z" ? `${x.label}, exact range` : `${x.label} score, exact range`} min={draft.ranges[x.range].min} max={draft.ranges[x.range].max} maxExcl={!!draft.ranges[x.range].maxExcl}
        chips={<BandChips name={x.label} bands={rangeToBands(draft.ranges[x.range])} onToggle={(b) => s.setRangeBand(x.range, b)} />} error={s.problems[x.range]} minPh="Min" maxPh="Max" onChange={(end, v) => s.setRange(x.range, end, v)} /></div>)}
      <p className="fgx-note">A high Risk score means lower risk.</p>
    </Sub>
    <Sub title={TECH_TITLE} icon="line" active={draft.tech.st.length + draft.tech.lt.length}>
      {TECH_KEYS.map((k) => (
        <div key={k} className="pzf-tv" role="group" aria-label={`${TECH_NAMES[k] === "Short-term technical" ? "Short-term" : "Long-term"} technical view`}>
          <div className="fgx-note">{k === "st" ? "Short-term" : "Long-term"} technical view</div>
          <div className="fgx-chips">
            {TECH_BAND_ORDER.map((b) => { const on = draft.tech[k].includes(b); return <button key={b} type="button" className={"fgx-chip" + (on ? " is-on" : "")} aria-pressed={on} onClick={() => s.setTech(k, b)}>{on && <i aria-hidden="true">&#10003;</i>}{TECH_BANDS[b].label}</button>; })}
          </div>
        </div>))}
    </Sub>
  </div>);
}
