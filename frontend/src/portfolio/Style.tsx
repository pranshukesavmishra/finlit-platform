import { Link } from "react-router";
import * as W from "../components/diversification/wording";
import type { StyleTilt } from "../components/diversification/types";
import { TILT_FOOT_EXTRA } from "./words";

/** Style tilt (Gold): where the list's average share ranks among the companies Prism rates, part by part. Silver sees why it is blank. */
export function Style({ tilt }: { tilt: StyleTilt | undefined }) {
  if (!tilt) return null;
  if ("locked" in tilt) return (
    <section className="pfx-card pfx-wide" id="pf-style" aria-labelledby="pfx-st"><div className="pfx-h"><h2 id="pfx-st">Style tilt</h2></div>
      <p className="pfx-line">{tilt.reason} <Link to="/plans">See the Gold plan</Link>.</p></section>);
  const rated = tilt.parts.some((p) => p.avgPercentile != null);
  return (
    <section className="pfx-card pfx-wide" id="pf-style" aria-labelledby="pfx-st">
      <div className="pfx-h"><h2 id="pfx-st">Style tilt</h2><p className="pfx-note">Where the list's average share ranks among the companies Prism rates</p></div>
      <p className="pfx-line">{rated ? tilt.sentence : "None of these shares has a Prism rating yet, so there is no style tilt to show."}</p>
      {rated && <ul className="pfx-tilt">{tilt.parts.map((p) => { const at = p.avgPercentile; return (
        <li key={p.part}><span>{p.part.replace("technical view", "trend")}</span>
          <span className="pfx-track" aria-hidden="true"><i className="band" />{at != null && <b style={{ left: `${at}%` }} className={at > 65 ? "hi" : ""} />}</span>
          <span className="pfx-tilt-v">{at == null ? W.tiltRead(p) : <><b>{W.ordinal(at)}</b> · {W.tiltRead(p)}</>}</span></li>); })}</ul>}
      {rated && <p className="pfx-fine">The shaded band, 35th to 65th, reads as typical. {TILT_FOOT_EXTRA}</p>}
      {W.notRatedNote(tilt.notRated) && <p className="pfx-fine">{W.notRatedNote(tilt.notRated)}</p>}
    </section>
  );
}
