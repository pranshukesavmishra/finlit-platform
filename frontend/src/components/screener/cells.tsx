// Table cells shared by the two score screeners. A missing figure says why (a dash or a lock, with the reason in words), never zero.
import { Link } from "react-router";
import { Icon } from "../../lib/icons";
import { MINUS, nf } from "../../lib/format";
import { asOfText } from "../../lib/scoreBands";
import { level, missingReason, trendWord, type Item, type PILLARS } from "../../lib/scoreScreen";
import { scoreBand } from "../../lib/scoreBands";
import { LABEL_WORD, PRISM_STATUS_WORD, hasPrism, prismCell, prismReason, type PrismLabel } from "../../lib/scorePrism";

export const Score = ({ r, k, locked }: { r: Item; k: "f" | "t" | "overall" | (typeof PILLARS)[number]["col"]; locked: boolean }) => {
  const v = k === "f" ? r.f : k === "t" ? r.t : r[k];
  if (v != null) return <span className={"ssp " + level(v)}>{v}</span>;
  const why = missingReason(r, k, locked);
  return <span className="ssp na" title={why}>{locked ? <Icon name="lock" /> : MINUS}<span className="sr">Not available: {why}</span></span>;
};
/** The Prism rating: score and label in words; a company without one says why and (Gold) links to its Prism page, which starts the calculation. */
export const PrismScore = ({ r, gold }: { r: Item; gold: boolean }) => {
  if (hasPrism(r)) {
    const tone = scoreBand(r.prism_final), word = LABEL_WORD[r.prism_label as PrismLabel] ?? r.prism_label;
    return (<span className="pzs"><span className={"ssp pzs-n " + tone}>{Math.round(r.prism_final as number)}</span><span className="pzs-l"><b className={tone}>{word}</b>{r.prism_status && r.prism_status !== "RATED" && <small>{PRISM_STATUS_WORD[r.prism_status] ?? r.prism_status}</small>}</span></span>);
  }
  const why = prismReason(r, gold), cell = prismCell(r, gold);
  if (cell === "locked") return <span className="ssp na" title={why}><Icon name="lock" /><span className="sr">Not available: {why}</span></span>;
  return (<span className="pzs-no" title={why}>{cell === "not-yet" ? "Not rated yet" : "Not rated"}<span className="sr">: {why}</span>
    {cell === "not-yet" && <Link to={`/prism/${encodeURIComponent(r.symbol)}`} className="pzs-go" aria-label={`Rate ${r.symbol} with Prism now`}>Rate now</Link>}</span>);
};
export const PrismPart = ({ r, v, gold }: { r: Item; v: number | null | undefined; gold: boolean }) => {
  if (v != null) return <span className={"ssp pzs-n " + scoreBand(v)}>{Math.round(v)}</span>;
  const why = prismReason(r, gold, "part");
  return <span className="ssp na" title={why}>{prismCell(r, gold) === "locked" ? <Icon name="lock" /> : MINUS}<span className="sr">Not available: {why}</span></span>;
};
/** A technical view: the site's descriptive word for the score (never the model's own word) and the signed score, -100 to +100. */
export const PrismTrend = ({ r, score, gold, col }: { r: Item; score: number | null | undefined; gold: boolean; col: "st" | "lt" }) => {
  const word = trendWord(score);
  if (word && score != null) { const sg = score > 0 ? "+" : score < 0 ? MINUS : ""; return <span className="pzs-w" title={`${word} (${sg}${nf(Math.abs(score), 0)} on a scale of ${MINUS}100 to +100)${r.prism_tech_at ? `, as of ${asOfText(r.prism_tech_at)}` : ""}`}><b>{word}</b><small>{sg}{nf(Math.abs(score), 0)}</small></span>; }
  const why = prismReason(r, gold, col);
  return <span className="ssp na" title={why}>{prismCell(r, gold) === "locked" ? <Icon name="lock" /> : MINUS}<span className="sr">Not available: {why}</span></span>;
};
export const Dash = ({ why }: { why: string }) => <span title={why}>{MINUS}<span className="sr"> not available: {why}</span></span>;
export const med = (v: number | null) => (v == null ? null : nf(v, v % 1 ? 1 : 0));
