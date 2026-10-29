// The technical view, part two: how the two trends line up (the trend alignment and its 3 x 3 map) and "How these scores are built" (every row of both
// scores: reading now, signal, weight, points, the divisor, the ADX trend factor and the long-term stage limit). Ports of the team's indicator
// "ST/LT Score Breakdown & Peers v1.2"; the numbers are the engine's own (nothing here recalculates a score), the words come from the shared
// wording file and only describe the chart. Styles: styles/prism-technical.css (pzt-*).
import { Icon } from "../../../lib/icons";
import { MINUS, dateIN } from "../../../lib/format";
import {
  ALIGN_BAND_WORD, BAND_ORDER, HOW, STAGE_WORD, fmtScore, ratingWord, safeText, trendAlignment, verdictView,
  type TechAssessment, type TechFactor, type TechHorizon, type TrendAlignment, type VerdictTone,
} from "../../../lib/prismTechnical";

const VSHAPE: Record<VerdictTone, string> = { pos: "▲", mixed: "◆", neg: "▼", na: "–" };
const sgn = (x: number, d: number) => (x > 0 ? "+" : x < 0 ? MINUS : "") + Math.abs(x).toFixed(d);
/** A signal: two decimals with a sign; a points figure: one decimal. A zero has no sign. */
export const fmtSignal = (x: number) => sgn(Math.abs(x) < 0.005 ? 0 : x, 2);
export const fmtPoints = (x: number) => sgn(Math.abs(x) < 0.05 ? 0 : x, 1);
const score2 = (x: number) => sgn(Math.abs(x) < 0.005 ? 0 : x, 2);

/** The sentence that shows the working: both scores, both bands, and the label. */
export function alignmentSentence(a: Pick<TechAssessment, "shortTerm" | "longTerm">): string {
  const al = trendAlignment(a.shortTerm.score, a.longTerm.score);
  if (!al) return "";
  return `Short-term ${fmtScore(a.shortTerm.score)} (${al.stBandWord}) × long-term ${fmtScore(a.longTerm.score)} (${al.ltBandWord}) = ${al.label}.`;
}

export function TrendMap({ al }: { al: TrendAlignment }) {
  const cell = (st: string, lt: string) => al.cells.find((c) => c.stBand === st && c.ltBand === lt)!;
  return (
    <div className="pzt-tw pzt-mapw">
      <table className="pzt-map">
        <caption>Trend map: the short-term band down the side, the long-term band across the top. The highlighted cell is where this company is now.</caption>
        <thead><tr><td aria-hidden="true" />{BAND_ORDER.map((lt) => <th scope="col" key={lt}><small>Long-term</small>{ALIGN_BAND_WORD[lt]}</th>)}</tr></thead>
        <tbody>
          {BAND_ORDER.map((st) => (
            <tr key={st}>
              <th scope="row"><small>Short-term</small>{ALIGN_BAND_WORD[st]}</th>
              {BAND_ORDER.map((lt) => {
                const c = cell(st, lt);
                return (
                  <td key={lt} className={"pzt-mc " + c.tone + (c.current ? " now" : "")} aria-current={c.current ? "true" : undefined}>
                    {c.label}{c.current && <><b className="pzt-now" aria-hidden="true">Now</b><span className="sr-only"> (this is where the company is now)</span></>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Under the two scores: the alignment label, how it was reached, and the map. Nothing when one score is missing. */
export function TrendAlignmentBlock({ a }: { a: TechAssessment }) {
  const v = verdictView(a), al = trendAlignment(a.shortTerm.score, a.longTerm.score);
  return (
    <section className={"pzt-verdict " + v.tone} aria-label={`Trend alignment: ${v.word}. ${v.detail}`}>
      <span className="pzt-vk">Trend alignment</span>
      <span className={"pzt-vchip " + v.tone}><i aria-hidden="true">{VSHAPE[v.tone]}</i>{v.word}</span>
      <span className="pzt-vd">{al ? <>{alignmentSentence(a)} {al.rule}</> : v.detail} It is separate from the 0 to 100 financial-health score.</span>
      {al && <TrendMap al={al} />}
    </section>
  );
}

/* ------------------------------------------------------------------ how the scores are built */
function Reading({ f }: { f: TechFactor }) {
  const detail = safeText(f.detail);
  return f.status === "disabled" ? <span className="pzt-off-t">Switched off in this model: not counted and nothing replaces it.</span> : <>{detail || "—"}</>;
}

function Table({ title, horizon: h, kind, a }: { title: string; horizon: TechHorizon; kind: "st" | "lt"; a: TechAssessment }) {
  const rows = h.factors, o = a.observations;
  const built = h.divisor != null && rows.some((f) => f.points != null);
  const word = ratingWord(h.rating, h.score).word;
  const total = rows.reduce((s, f) => s + (f.points ?? 0), 0);
  return (
    <details className="pzt-bd">
      <summary><span>{title}</span><small>{h.score != null ? `${fmtScore(h.score)} · ${word}` : "Not available"}</small><Icon name="arrow" className="pzt-chev" /></summary>
      {!built ? (
        <p className="pzt-none">This stored report was made before the breakdown existed, so it has no weights or points to show. Recalculate to add them. The score above is unchanged.</p>
      ) : (
        <>
          <p className="pzt-sub">Each row gives a signal from −1 to +1. Points = weight × signal × 100 ÷ {h.divisor} (the weights in use). The points add up to the score{kind === "lt" ? ", before the stage limit below" : ""}. Based on prices as of {a.asOf ? dateIN(a.asOf) : "an unknown date"}.</p>
          <div className="pzt-tw"><table className="pzt-tbl pzt-bt">
            <caption className="sr-only">{title}: reading now, signal, weight and points of every row</caption>
            <thead><tr><th scope="col">Row</th><th scope="col">Reading now</th><th scope="col" className="r">Signal</th><th scope="col" className="r">Weight</th><th scope="col" className="r">Points</th></tr></thead>
            <tbody>
              {rows.map((f) => {
                const how = HOW[kind][f.key];
                return (
                  <tr key={f.key} className={f.status === "disabled" ? "off" : f.status === "unavailable" ? "na" : ""}>
                    <th scope="row"><b>{safeText(f.label)}</b>{how && <details className="pzt-how"><summary>How it is read</summary><p>{how}</p></details>}</th>
                    <td className="pzt-rd"><Reading f={f} /></td>
                    <td className="r">{f.status === "available" && f.signal != null ? fmtSignal(f.signal) : "—"}</td>
                    <td className="r">{f.status === "disabled" || f.weight == null ? "—" : f.weight}</td>
                    <td className="r">{f.points != null ? fmtPoints(f.points) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr><th scope="row" colSpan={2}>Total of the points</th><td className="r" colSpan={2}>weights in use {h.divisor}</td><td className="r"><b>{h.status === "ready" ? fmtPoints(total) : "—"}</b></td></tr>
            </tfoot>
          </table></div>
          {h.score != null && <p className="pzt-sub pzt-eq">Score {score2(h.stageCapped && h.uncappedScore != null ? h.uncappedScore : h.score)}{h.stageCapped && h.uncappedScore != null ? `, limited to ${score2(h.score)} by the market stage (below)` : ""}; shown as {fmtScore(h.score)}.</p>}
          {kind === "st" && (o.adx != null && o.trendMultiplier != null
            ? <p className="pzt-fact"><Icon name="activity" /><span><b>Trend factor.</b> ADX is {o.adx.toFixed(1)}, so the first three rows (EMA alignment, price and short-term trend, daily MACD) are multiplied by ×{o.trendMultiplier.toFixed(2)}. ADX above 25 gives ×1, below 20 gives ×0.5, anything between gives ×0.75.</span></p>
            : <p className="pzt-fact quiet"><Icon name="info" /><span>The first three rows are multiplied by a trend factor from ADX (above 25 ×1, below 20 ×0.5, otherwise ×0.75). This stored report did not keep the ADX; recalculate to add it.</span></p>)}
          {kind === "lt" && (
            <p className="pzt-fact"><Icon name="layers" /><span><b>Market stage.</b> {o.stage ? STAGE_WORD[o.stage] + ". " : "The stage is not available. "}
              {o.stage === 3 || o.stage === 4
                ? (h.stageCapped ? `In Stage 3 and Stage 4 the long-term score cannot be higher than +19, so ${h.uncappedScore != null ? `${score2(h.uncappedScore)} became +19` : "the score was limited to +19"}.` : "In Stage 3 and Stage 4 the long-term score cannot be higher than +19; here the score was already below that, so the limit changed nothing.")
                : "The +19 limit applies only in Stage 3 and Stage 4."}</span></p>
          )}
        </>
      )}
    </details>
  );
}

export function Breakdown({ a, onRecalculate }: { a: TechAssessment; onRecalculate?: () => void }) {
  const any = [a.shortTerm, a.longTerm].some((h) => h.divisor != null);
  return (
    <div className="pzt-blk" id="pzt-built"><h4>How these scores are built</h4>
      <p className="pzt-sub">Every row of both scores, as the technical model reads it today: what it reads, the signal it gives, how much weight the row carries and the points that come out. Open a timeframe to see its table.{!any && onRecalculate && <> <button type="button" className="pzr-link pzr-noprint" onClick={onRecalculate}>Recalculate to add the breakdown</button></>}</p>
      <div className="pzt-bds"><Table title="Short term: how the score is built" horizon={a.shortTerm} kind="st" a={a} /><Table title="Long term: how the score is built" horizon={a.longTerm} kind="lt" a={a} /></div>
    </div>
  );
}
