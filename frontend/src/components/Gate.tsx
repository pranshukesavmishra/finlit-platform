import { createContext, useContext, type ReactNode } from "react";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { TIER, useUI, type Plan } from "../lib/ui";

/** True on the page of a free example company: the server already sent everything, so nothing on it is locked. */
export const OpenAccess = createContext(false);

/** Locks content the current plan doesn't include. In production the API never sends locked
 *  data; this overlay is what users see in its place. */
export function Gate({ tier, title, points, children }: { tier: Plan; title: string; points: string[]; children: ReactNode }) {
  const { has, upgrade } = useUI();
  const open = useContext(OpenAccess);
  const locked = !open && !has(tier);
  const t = TIER[tier];
  return (
    <div className={"gate" + (locked ? " is-locked" : "")}>
      <div inert={locked || undefined}>{children}</div>
      <div className="lock" style={{ "--tc": `var(${t.tc})` } as React.CSSProperties}>
        <div className="lock-card">
          <div className="lk-ic"><Icon name="lock" /></div>
          <span className={"tier " + tier}><Icon name={t.ic} />{t.n} plan</span>
          <h4>{title}</h4>
          <ul>{points.map((p) => <li key={p}><Icon name="check" /><span>{p}</span></li>)}</ul>
          <button className="btn" onClick={() => upgrade(tier, `${title} is part of ${t.n}.`)}>
            Unlock with {t.n} <Icon name="arrow" />
          </button>
          <span className="sub">Pricing at launch · <Link to="/plans">Compare plans</Link></span>
        </div>
      </div>
    </div>
  );
}

export function TierChip({ tier }: { tier: Plan }) {
  return <span className={"tier " + tier}>{TIER[tier].n}</span>;
}
