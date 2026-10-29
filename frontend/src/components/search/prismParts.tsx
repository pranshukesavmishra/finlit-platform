// Gold search results: the three small Prism scores of a row and the six of the preview panel. Words are descriptive, never advice.
import { MINUS } from "../../lib/format";
import {
  NOT_RATED_TIP, OLD_REPORT_TIP, PART_LABEL, PRISM_PARTS, TECH_LABEL, TECH_TIP, finalColor, techColor, techFill, techText,
  type PrismScore, type PrismScoreMap, type TechScore,
} from "../../lib/prismScores";
import { PRISM_NAME } from "../../lib/prism";

type State = { kind: "loading" } | { kind: "error" } | { kind: "none" } | { kind: "ok"; s: PrismScore };
export function stateOf(map: PrismScoreMap, symbol: string): State {
  const v = map[symbol];
  return v === undefined ? { kind: "loading" } : v === "error" ? { kind: "error" } : v === null || !v.rated ? { kind: "none" } : { kind: "ok", s: v };
}

function Ring({ fill, color, text, cap, tip }: { fill: number; color: string; text: string; cap: string; tip: string }) {
  const r = 15, c = 2 * Math.PI * r;
  return (
    <span className="gs-score gs-pz" style={{ "--rc": color } as React.CSSProperties} title={tip}>
      <span className="gs-ring"><svg viewBox="0 0 36 36" aria-hidden="true"><circle cx="18" cy="18" r={r} className="gs-ring-bg" /><circle cx="18" cy="18" r={r} className="gs-ring-fg" strokeDasharray={`${(c * fill) / 100} ${c}`} /></svg><b>{text}</b></span>
      <span className="gs-band">{cap}</span>
    </span>
  );
}
const techTip = (label: string, t: TechScore) => `${label}: ${t.score == null ? "not available" : `${techText(t.score)}, ${t.word.toLowerCase()}`}. ${TECH_TIP}`;

/** Three rings in a row: Prism rating (0-100), short-term technical, long-term technical (signed). */
export function PrismChips({ state }: { state: State }) {
  if (state.kind === "loading") return <span className="gs-pzs gs-pz-load" aria-hidden="true"><i /><i /><i /></span>;
  if (state.kind !== "ok") {
    const err = state.kind === "error";
    return <span className="gs-pzs"><span className="gs-pz-none" title={err ? "The Prism scores could not be loaded just now." : NOT_RATED_TIP}>{err ? "Unavailable" : "Not rated yet"}</span></span>;
  }
  const { s } = state;
  return (
    <span className="gs-pzs" role="group" aria-label={`${PRISM_NAME}: rating ${s.final == null ? "not available" : Math.round(s.final)} of 100; short-term technical ${techText(s.shortTerm.score)}; long-term technical ${techText(s.longTerm.score)}`}>
      <Ring fill={s.final ?? 0} color={finalColor(s.final)} text={s.final == null ? MINUS : String(Math.round(s.final))} cap="Prism" tip={`${PRISM_NAME} rating: ${s.final == null ? "not available" : `${Math.round(s.final)} of 100${s.label ? `, ${s.label.toLowerCase()}` : ""}`}. Green 70 or more, orange 50 to 69, red below 50.`} />
      {(["shortTerm", "longTerm"] as const).map((h) => {
        const t = s[h];
        return t.score == null
          ? <span key={h} className="gs-score gs-pz gs-none" title={OLD_REPORT_TIP}><span className="gs-ring">{MINUS}</span><span className="gs-band">{h === "shortTerm" ? "Short" : "Long"}</span></span>
          : <Ring key={h} fill={techFill(t.score)} color={techColor(t.score)} text={techText(t.score)} cap={h === "shortTerm" ? "Short" : "Long"} tip={techTip(TECH_LABEL[h], t)} />;
      })}
    </span>
  );
}

function Bar({ label, value, tip }: { label: string; value: number | null; tip?: string }) {
  return <li title={tip}><span>{label}</span><i><em style={{ width: `${value ?? 0}%`, background: finalColor(value) }} /></i><b>{value == null ? MINUS : Math.round(value)}</b></li>;
}
function TechBar({ label, t }: { label: string; t: TechScore }) {
  const v = t.score, c = techColor(v), w = v == null ? 0 : Math.abs(v) / 2;
  return (
    <li className="gs-pz-t" title={techTip(label, t)}>
      <span>{label}</span>
      <i className="gs-pz-sign"><em style={{ background: c, width: `${w}%`, left: v != null && v < 0 ? `${50 - w}%` : "50%" }} /></i>
      <b style={{ color: v == null ? undefined : c }}>{techText(v)}</b>
      <small>{t.word}</small>
    </li>
  );
}

/** The preview's six scores: the four Prism categories (0-100) and the two technical ones, under the rating ring. */
export function PrismPreviewScores({ state }: { state: State }) {
  if (state.kind === "loading") return <div className="gs-pre-sc gs-pz-prev gs-pz-load" aria-hidden="true"><i /><i /><i /><i /><i /><i /></div>;
  if (state.kind !== "ok") return <p className="gs-pre-note">{state.kind === "error" ? "The Prism scores could not be loaded just now." : <><span className="gs-pz-none">Not rated yet</span> {NOT_RATED_TIP}</>}</p>;
  const { s } = state;
  return (
    <div className="gs-pre-sc gs-pz-prev">
      <Ring fill={s.final ?? 0} color={finalColor(s.final)} text={s.final == null ? MINUS : String(Math.round(s.final))} cap={s.label ? s.label[0] + s.label.slice(1).toLowerCase() : "Prism"} tip={`${PRISM_NAME} rating out of 100`} />
      <ul className="gs-pil" aria-label={`${PRISM_NAME} scores`}>
        {PRISM_PARTS.map((k) => <Bar key={k} label={PART_LABEL[k]} value={s.parts?.[k] ?? null} />)}
        <TechBar label={TECH_LABEL.shortTerm} t={s.shortTerm} />
        <TechBar label={TECH_LABEL.longTerm} t={s.longTerm} />
      </ul>
    </div>
  );
}
