// The Health score cell of a table row (funds list, ETF list): the number with its colour band and label; a lock below Gold; the specific reason where there is no score.
import { Icon } from "../lib/icons";
import { bandOf, scoreText, type ScoreItem } from "../lib/mfScore";
import "../styles/mf.css";

export function ScoreCell({ item, locked, why, loading = false }: { item?: ScoreItem; locked: boolean; why: string; loading?: boolean }) {
  if (locked) return <span className="mf-na" title="The FinLit Mutual Fund Health Score is part of the Gold plan."><Icon name="lock" /><span className="sr-only">Locked: Gold plan</span></span>;
  if (loading && !item) return <span className="mf-na" aria-busy="true"><span className="sr-only">Loading</span>…</span>;
  if (!item || item.final == null) return <span className="mf-na" title={item?.reason || why} aria-label={`No score. ${item?.reason || why}`}>—{item?.status === "NOT RATED" && <small>not rated</small>}</span>;
  const band = bandOf(item.final);
  return <span className="mfs-cell" title={`${item.label}${item.status === "PROVISIONAL" ? ", provisional" : ""}. Describes the past; not a recommendation.`}><b className={"mfs-pv b-" + band}>{scoreText(item.final)}</b><small>{item.label}{item.status === "PROVISIONAL" ? " · provisional" : ""}</small></span>;
}
