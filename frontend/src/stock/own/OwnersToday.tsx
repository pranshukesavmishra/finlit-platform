import { useState } from "react";
import { ChartHelp } from "../../components/ChartHelp";
import { DONUT_R, donutArcs, pc, type GroupKey, type Slice } from "../../lib/ownView";
import { ChartZoom } from "../../components/ChartZoom";

/** The donut: hover (or focus, or tap) a slice or a name and it is read in the centre. One-line legend rows. Every label is page text. */
export function OwnersToday({ slices, when, isLatest }: { slices: Slice[]; when: string; isLatest: boolean }) {
  const [hover, setHover] = useState<GroupKey | null>(null);
  if (!slices.length) return null;
  const arcs = donutArcs(slices), cur = slices.find((s) => s.key === hover) ?? slices[0];
  const label = `Owners in ${when}: ${slices.map((s) => `${s.name} ${pc(s.value)}`).join(", ")}`;
  return (
    <section className="ow-card" aria-labelledby="ow-owners">
      <div className="ow-sec-h"><h3 id="ow-owners" className="ow-h2">Owners {isLatest ? "today" : `in ${when}`}<ChartHelp id="own-donut" /></h3><span className="ow-small ow-muted">{when} · hover a slice</span></div>
      <ChartZoom label="Owners of the company">
      <div className="ow-donut-wrap" onMouseLeave={() => setHover(null)}>
        <div className="ow-donut">
          <svg width="200" height="200" viewBox="0 0 200 200" role="img" aria-label={label}>
            <circle cx="100" cy="100" r={DONUT_R} fill="none" className="ow-ring" strokeWidth="24" />
            {arcs.map((a) => (
              <circle key={a.key} cx="100" cy="100" r={DONUT_R} fill="none" stroke={slices.find((s) => s.key === a.key)!.color} strokeWidth={hover === a.key ? 28 : 24}
                strokeDasharray={a.dash} strokeDashoffset={a.offset} data-slice={a.key} onMouseEnter={() => setHover(a.key)} onClick={() => setHover(a.key)} />
            ))}
          </svg>
          <div className="ow-center" aria-hidden="true"><span className="ow-cl">{cur.name.toUpperCase()}</span><span className="ow-cv">{pc(cur.value)}</span><span className="ow-small ow-muted">of all shares</span></div>
        </div>
        <ul className="ow-legend">
          {slices.map((s) => (
            <li key={s.key} className={hover === s.key ? "on" : ""} tabIndex={0} onMouseEnter={() => setHover(s.key)} onFocus={() => setHover(s.key)} onBlur={() => setHover(null)} onClick={() => setHover(s.key)}>
              <span className="ow-dot" style={{ background: s.color }} aria-hidden="true" />
              <span className="ow-lg-t"><span className="ow-n">{s.name}</span><span className="ow-d">{s.desc}</span></span>
              <span className="ow-v">{pc(s.value)}</span>
            </li>
          ))}
        </ul>
      </div>
      </ChartZoom>
    </section>
  );
}
