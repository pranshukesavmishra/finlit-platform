// Small pieces the Sector Pulse pages share: the state chip, the three breadth bars, a locked block and a blank that says why. Styles: styles/sectors.css (sx-).
import type { ReactNode } from "react";
import { Link } from "react-router";
import { Icon } from "../../lib/icons";
import { TIER, useUI, type Plan } from "../../lib/ui";
import { pct, stateClass, type Breadth } from "../../lib/sectors";
import "../../styles/sectors.css";

/** The state as a coloured chip; the word is always written, so colour is never the only signal. */
export function StateChip({ state, big, extra }: { state: string | null | undefined; big?: boolean; extra?: string }) {
  return <span className={`sx-chip ${stateClass(state)}${big ? " big" : ""}`}>{state ?? "No reading"}{extra ? ` · ${extra}` : ""}</span>;
}

/** The share of counted stocks above their 9, 20 and 50-day averages: three bars with the figure written beside each. */
export function BreadthBars({ b, name }: { b: Breadth; name?: string }) {
  const rows: [string, string, number | null][] = [["9", "b9", b.above_9], ["20", "b20", b.above_20], ["50", "b50", b.above_50]];
  const label = `${name ? name + ": " : ""}share of counted stocks above their 9-day average ${pct(b.above_9)}, 20-day ${pct(b.above_20)}, 50-day ${pct(b.above_50)}`;
  return (
    <div className="sx-bars" role="img" aria-label={label}>
      {rows.map(([n, c, v]) => (
        <div className={"r " + c} key={n} aria-hidden="true"><span>{n}</span><span className="tr"><i style={{ width: `${Math.max(0, Math.min(100, v ?? 0))}%` }} /></span><b>{pct(v)}</b></div>
      ))}
    </div>
  );
}

/** A figure the plan does not include: said in words, with the plan that opens it. Never an empty cell. */
export function LockedBlock({ plan, title, children }: { plan: Plan; title: string; children?: ReactNode }) {
  const { upgrade } = useUI();
  const t = TIER[plan];
  return (
    <div className="sx-lock" role="note">
      <b><Icon name="lock" /> {title}</b>
      <p>{children}</p>
      <button type="button" className="btn" onClick={() => upgrade(plan, `${title} is part of the ${t.n} plan.`)}>See {t.n}</button>
    </div>
  );
}

/** A section with nothing to show: the reason, and where to go. */
export function Blank({ title, reason, children }: { title: string; reason: string; children?: ReactNode }) {
  return (
    <section className="sx-blank" role="status">
      <h2>{title}</h2>
      <p>{reason}</p>
      {children}
    </section>
  );
}

/** The footer every sector page carries: the package's disclaimer, "past averages, not forecasts", and the sources. */
export function SectorFooter({ disclaimer }: { disclaimer?: string | null }) {
  return (
    <footer className="sx-footer">
      <p>{disclaimer || "Describes price and breadth data for NSE industries; not a recommendation to buy, sell or hold any security. Study results are past averages and do not predict future returns."}</p>
      <p>Sources: NSE daily files and industry classification; AMFI market caps. Prices are adjusted for splits, bonuses and rights. <Link className="sx-link" to="/learn/sector-signals">How sector signals work</Link></p>
    </footer>
  );
}
