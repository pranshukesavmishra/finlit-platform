import { useState } from "react";
import { Link } from "react-router";
import { GROUPS, TOOL_COPY, type GroupId } from "../lib/featureBucket";
import { TIER_LABEL, TOOL_ICONS, TOOL_IDS, type ToolTier } from "../lib/toolIcons";
import { ToolIcon } from "./ToolIcon";
import "../styles/feature-bucket.css";

const pad = (n: number) => String(n).padStart(2, "0");
/** Where a plan chip leads: that plan on the Plans page. */
const PLAN_LINK: Record<ToolTier, string> = { free: "/plans#basic", silver: "/plans#silver", gold: "/plans#gold" };
/** Each plan includes the plans below it: Gold = Gold tools + everything in Silver + everything in Free; Silver = Silver tools + everything in Free. */
const INCLUDES: Record<ToolTier, ToolTier[]> = { free: [], silver: ["free"], gold: ["silver", "free"] };
const PLAN_FILTERS: [ToolTier | "all", string][] = [["all", "Any plan"], ["free", "Free"], ["silver", "Silver"], ["gold", "Gold"]];

/** Tools & Research Hub: five groups of tool cards, filtered by group and by the plan that opens them. Every card stays in the page (the filters only hide
 *  cards visually), so search engines and no-script readers see all 22. It replaces the numbered "Explore our platform" grid that listed the same tools. */
export function FeatureBucket() {
  const [sel, setSel] = useState<GroupId | "all">("all");
  const [plan, setPlan] = useState<ToolTier | "all">("all");
  return (
    <section className="sec hh-sec fb" id="tools" aria-labelledby="fb-title"><div className="wrap">
      <div className="hh-head"><div className="hh-kicker">Tools &amp; Research Hub</div><h2 id="fb-title">Every tool, grouped by what you want to do</h2>
        <p>Screeners, research tools and calculators to discover, assess, value, manage and follow the market. Each card shows the plan it opens on; you can open any of them.</p></div>
      <div className="fb-filters" role="group" aria-label="Show tools by group">
        {([["all", "All"], ...GROUPS.map((g) => [g.id, g.name])] as [GroupId | "all", string][]).map(([k, label]) => (
          <button key={k} type="button" className="fb-pill" aria-pressed={sel === k} onClick={() => setSel(k)}>{label}</button>
        ))}
        <span className="fb-sep" aria-hidden="true" />
        <span className="fb-flabel" id="fb-plan-l">Plan</span>
        <span role="group" aria-labelledby="fb-plan-l" className="fb-plans">
          {PLAN_FILTERS.map(([k, label]) => (
            <button key={k} type="button" className={`fb-pill fb-pp fb-pp-${k}`} aria-pressed={plan === k} onClick={() => setPlan(k)}>{label}</button>
          ))}
        </span>
      </div>
      {GROUPS.map((g) => {
        const ids = TOOL_IDS.filter((id) => TOOL_COPY[id].group === g.id).sort((a, b) => TOOL_COPY[a].n - TOOL_COPY[b].n);
        const shown = ids.filter((id) => plan === "all" || TOOL_ICONS[id].tier === plan).length;
        return (
          <div key={g.id} className={`fb-group fb-g-${g.id}`} data-group={g.id} hidden={(sel !== "all" && sel !== g.id) || shown === 0} aria-labelledby={`fb-h-${g.id}`}>
            <div className="fb-ghead"><h3 id={`fb-h-${g.id}`}><span className="fb-dot" aria-hidden="true" />{g.name}</h3><span className="fb-count">{shown === ids.length ? `${ids.length} tools` : `${shown} of ${ids.length} tools`}</span><p>{g.desc}</p></div>
            <ul className="fb-grid" style={{ ["--fb-cols" as string]: Math.min(ids.length, 5) }}>
              {ids.map((id) => {
                const m = TOOL_ICONS[id], c = TOOL_COPY[id];
                return (
                  <li key={id} className="fb-card" data-tool={id} data-tier={m.tier} hidden={plan !== "all" && m.tier !== plan}>
                    <div className="fb-top"><ToolIcon id={id} size="md" /><div className="fb-name"><h4>{m.name}</h4><p className="fb-tag">{c.desc}</p></div>
                      <Link className={`fb-chip fb-${m.tier}`} to={PLAN_LINK[m.tier]} title={`Opens on the ${TIER_LABEL[m.tier]} plan: see what it includes`}>{TIER_LABEL[m.tier]}<span className="sr-only"> plan</span></Link></div>
                    <picture className="fb-shot">
                      <img className="fb-l" src={`/feature-bucket/${id}-light.webp`} width={640} height={400} loading="lazy" decoding="async" alt={`The ${m.name} page: ${m.tagline.toLowerCase()}`} />
                      <img className="fb-d" src={`/feature-bucket/${id}-dark.webp`} width={640} height={400} loading="lazy" decoding="async" alt={`The ${m.name} page: ${m.tagline.toLowerCase()}`} />
                    </picture>
                    <ul className="fb-feat">{c.features.map((f) => <li key={f}>{f}</li>)}</ul>
                    <p className="fb-edge">{c.edge}</p>
                    <Link className="fb-open" to={m.route}><span className="fb-n">{pad(c.n)}</span>Open {m.name} <span aria-hidden="true">{"→"}</span></Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
      {plan !== "all" && INCLUDES[plan].length > 0 && (
        <div className="fb-plus" aria-label={`Also included in the ${TIER_LABEL[plan]} plan`}>
          {INCLUDES[plan].map((t) => (
            <div key={t} className={`fb-plus-row fb-plus-${t}`}>
              <p><b>Plus all features of {TIER_LABEL[t]}</b> <span>{t === "free" ? "(everything in the free account)" : "(and everything in Free)"}</span></p>
              <ul>{TOOL_IDS.filter((id) => TOOL_ICONS[id].tier === t).sort((a, b) => TOOL_COPY[a].n - TOOL_COPY[b].n).map((id) => (
                <li key={id}><Link to={TOOL_ICONS[id].route}><ToolIcon id={id} size="sm" />{TOOL_ICONS[id].name}</Link></li>))}</ul>
            </div>
          ))}
        </div>
      )}
      <p className="fb-fine">Tools are for information and education only {"—"} never investment advice.</p>
    </div></section>
  );
}
