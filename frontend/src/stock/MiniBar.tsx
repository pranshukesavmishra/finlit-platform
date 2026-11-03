// The slim company bar: it slides in under the site header once the full company header has scrolled out of sight, so the company, its price, its score
// and the Watchlist button stay with the reader. The section tab bar stays stuck directly under it. Same data and actions as the full header.
import { Icon } from "../lib/icons";
import { initials, nf, signed } from "../lib/format";
import { badgeView } from "../lib/scoreBands";
import type { Summary } from "../lib/api";
import { NameDots, ScoreBadge } from "./HeaderScore";
import { useReportHeader } from "./useReportHeader";
import "../styles/minibar.css";

export function MiniBar({ s, on }: { s: Summary; on: boolean }) {
  const { effPlan, isAdmin, prismIn, watch, toggleWatch, has } = useReportHeader(s);
  const p = s.profile, q = s.quote, up = (q.changePct ?? 0) >= 0;
  const view = badgeView(effPlan, isAdmin, { overall: s.score.overall, word: s.score.band.label }, prismIn);
  return (
    <div className={"mhbar" + (on ? " on" : "")} aria-hidden={!on} {...(!on ? { inert: true } : {})}>
      <div className="wrap mhbar-in">
        <span className="mhbar-bd" aria-hidden="true">{initials(p.name)}</span>
        <b className="mhbar-nm" title={p.name}>{p.name}</b>
        <span className="mhbar-px">₹{q.price == null ? "–" : nf(q.price)}</span>
        {q.changePct != null && <span className={"mhbar-chg " + (up ? "up" : "down")}>{signed(q.changePct)}</span>}
        <ScoreBadge view={view} symbol={p.symbol} />
        <span className="mhbar-dots"><NameDots score={s.score} plan={effPlan} admin={isAdmin} prism={prismIn} /></span>
        <button type="button" className={"btn sm mhbar-wl" + (watch ? " on" : "")} aria-pressed={watch} onClick={toggleWatch}><Icon name="spark" /><span>{watch ? "Watching" : "Watchlist"}</span>{!has("silver") && <Icon name="lock" className="lk" />}</button>
      </div>
    </div>);
}
