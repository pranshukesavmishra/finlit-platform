import { useState } from "react";
import { Link } from "react-router";
import { GROUPS, TOOL_COPY, type GroupId } from "../lib/featureBucket";
import { TIER_LABEL, TOOL_ICONS, TOOL_IDS } from "../lib/toolIcons";
import { ToolIcon } from "./ToolIcon";
import "../styles/feature-bucket.css";

const pad = (n: number) => String(n).padStart(2, "0");

/** Tools & Research Hub: five groups of tool cards. Every card stays in the page (filters only hide groups visually), so search engines and no-script readers see all 22. */
export function FeatureBucket() {
  const [sel, setSel] = useState<GroupId | "all">("all");
  return (
    <section className="sec hh-sec fb" id="tools" aria-labelledby="fb-title"><div className="wrap">
      <div className="hh-head"><div className="hh-kicker">Tools &amp; Research Hub</div><h2 id="fb-title">Every tool, grouped by what you want to do</h2>
        <p>Screeners, research tools and calculators to discover, assess, value, manage and follow the market. Each card shows the plan it opens on; you can open any of them.</p></div>
      <div className="fb-filters" role="group" aria-label="Show tools by group">
        {([["all", "All"], ...GROUPS.map((g) => [g.id, g.name])] as [GroupId | "all", string][]).map(([k, label]) => (
          <button key={k} type="button" className="fb-pill" aria-pressed={sel === k} onClick={() => setSel(k)}>{label}</button>
        ))}
      </div>
      {GROUPS.map((g) => {
        const ids = TOOL_IDS.filter((id) => TOOL_COPY[id].group === g.id).sort((a, b) => TOOL_COPY[a].n - TOOL_COPY[b].n);
        return (
          <div key={g.id} className={`fb-group fb-g-${g.id}`} data-group={g.id} hidden={sel !== "all" && sel !== g.id} aria-labelledby={`fb-h-${g.id}`}>
            <div className="fb-ghead"><h3 id={`fb-h-${g.id}`}><span className="fb-dot" aria-hidden="true" />{g.name}</h3><span className="fb-count">{ids.length} tools</span><p>{g.desc}</p></div>
            <ul className="fb-grid">
              {ids.map((id) => {
                const m = TOOL_ICONS[id], c = TOOL_COPY[id];
                return (
                  <li key={id} className="fb-card" data-tool={id}>
                    <div className="fb-top"><ToolIcon id={id} size="lg" /><span className="fb-num">{pad(c.n)}</span><span className={`fb-chip fb-${m.tier}`}>{TIER_LABEL[m.tier]}<span className="sr-only"> plan</span></span></div>
                    <h4>{m.name}</h4>
                    <p className="fb-tag">{m.tagline}</p>
                    <p className="fb-desc">{c.desc}</p>
                    <picture className="fb-shot">
                      <img className="fb-l" src={`/feature-bucket/${id}-light.webp`} width={640} height={400} loading="lazy" decoding="async" alt={`The ${m.name} page: ${m.tagline.toLowerCase()}`} />
                      <img className="fb-d" src={`/feature-bucket/${id}-dark.webp`} width={640} height={400} loading="lazy" decoding="async" alt={`The ${m.name} page: ${m.tagline.toLowerCase()}`} />
                    </picture>
                    <ul className="fb-feat">{c.features.map((f) => <li key={f}>{f}</li>)}</ul>
                    <p className="fb-edge"><b>What is different:</b> {c.edge}</p>
                    <Link className="fb-open" to={m.route}>Open {m.name} <span aria-hidden="true">{"→"}</span></Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
      <p className="fb-fine">Tools are for information and education only {"—"} never investment advice.</p>
    </div></section>
  );
}
