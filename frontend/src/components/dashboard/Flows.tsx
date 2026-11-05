// Block 5, FII / DII flows: the two latest-session tiles (value 24px) and the 30-session totals; the long charts live on the full page.
import { Link } from "react-router";
import { dateIN } from "../../lib/format";
import { useFlows, type Streak } from "../../lib/flows";
import { ageLabel, diiState, inr } from "../../lib/flowsMath";
import { Card, Rows } from "./parts";

const cls = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "up" : "down");
const arrow = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "▲ " : "▼ ");
const streak = (s: Streak | null) => (!s || s.side === "flat" || !s.days ? "No streak" : `${s.days} day${s.days === 1 ? "" : "s"} of ${s.side === "buying" ? "buying" : "selling"}`);

export function Flows() {
  const q = useFlows(), f = q.data;
  const l = f?.latest;
  return (
    <Card id="flows" title="FII / DII flows" sub={l && f ? `${dateIN(l.d)} · ${ageLabel(l.d, f.today)}` : undefined}>
      {q.isLoading ? <Rows n={2} h={78} /> : q.isError || !f || !l ? <p className="dsh-note">FII / DII figures are not available right now. They load after each trading day.</p> : <>
        <div className="dsh-tiles2">
          <div className="dsh-big"><span>FII / FPI net</span><b className={cls(l.fii.net)}>{arrow(l.fii.net)}{inr(l.fii.net)}</b><small>{streak(f.streaks.fii)}</small></div>
          <div className="dsh-big"><span>DII net</span>{l.dii?.net != null ? <><b className={cls(l.dii.net)}>{arrow(l.dii.net)}{inr(l.dii.net)}</b><small>{streak(f.streaks.dii)}</small></> : <><b>—</b><small>{diiState(f) === "none" ? "Not published by a permitted source" : "Not published for this day"}</small></>}</div>
        </div>
        <p className="dsh-line">Last {f.last30.days} sessions: FII <b className={cls(f.last30.fii)}>{inr(f.last30.fii)}</b>{f.last30.dii != null && <> · DII <b className={cls(f.last30.dii)}>{inr(f.last30.dii)}</b></>}</p>
        <Link className="dsh-link" to="/fii-dii">Full FII/DII data, charts and history →</Link>
      </>}
    </Card>
  );
}
