import { useMemo } from "react";
import { Link } from "react-router";
import type { Row } from "../lib/screener";
import { saveFile } from "../stock/derive";
import { buildReportHtml, findGaps, resilience, statsOf, stressView, type Holding } from "../lib/portfolioLab";

/** Portfolio lab: gaps, stress view and a printable report. Everything is worked out in the browser; nothing is saved. */
export type PortfolioLabProps = {
  lines: { symbol: string; name?: string | null; row?: Row }[];
  universe: Row[];
};

const lvl = (v: number | null | undefined) => (v == null ? "na" : v >= 78 ? "hi" : v >= 45 ? "mid" : "lo");
const sg = (d: number | null) => (d == null ? "—" : d > 0 ? `+${d}` : d < 0 ? `−${Math.abs(d)}` : "0");
const show = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : String(Math.round(v)));

export function PortfolioLab({ lines, universe }: PortfolioLabProps) {
  const held: Holding[] = useMemo(() => (lines || []).map((l) => ({ symbol: l.symbol, name: l.name, row: l.row })), [lines]);
  const uni = universe || [];
  const base = useMemo(() => statsOf(held), [held]);
  const gaps = useMemo(() => findGaps(held, uni), [held, uni]);
  const stress = useMemo(() => stressView(held), [held]);
  const res = useMemo(() => resilience(held), [held]);

  const download = () => saveFile("FinLit-portfolio-report.html", buildReportHtml(held), "text/html;charset=utf-8");
  const print = () => {
    const f = document.createElement("iframe");
    f.setAttribute("aria-hidden", "true"); f.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
    f.srcdoc = buildReportHtml(held);
    f.onload = () => { try { f.contentWindow?.focus(); f.contentWindow?.print(); } finally { setTimeout(() => f.remove(), 60_000); } };
    document.body.appendChild(f);
  };

  if (!held.length) return (
    <section className="card pl" aria-label="Portfolio lab"><div className="card-h"><h3>Portfolio lab</h3><span className="s">Gaps, stress view and report</span></div>
      <p className="muted">Add a few shares and the lab will show which areas are missing and how the list holds up under a stress test.</p></section>
  );
  if (!base.scored) return (
    <section className="card pl" aria-label="Portfolio lab"><div className="card-h"><h3>Portfolio lab</h3><span className="s">Preparing</span></div>
      <p className="muted">Your shares are still being scored. The lab appears as soon as the first scores are ready.</p></section>
  );

  return (
    <section className="card pl" aria-label="Portfolio lab">
      <div className="card-h"><h3>Portfolio lab</h3><span className="s">Information only</span></div>
      <p className="muted pl-lead">Gaps and stress tests on your own list. Scores come from company data; they are not recommendations. All shares count equally.</p>
      {base.unscored > 0 && <p className="pl-note" role="status">{base.unscored} {base.unscored === 1 ? "share is" : "shares are"} still being prepared and left out of the maths.</p>}

      {/* 2. Gaps */}
      <div className="pl-sec">
        <h4>Gaps in your list</h4>
        {gaps.length === 0 ? <p className="muted">No obvious gaps: your list touches the main sector groups and no pillar averages below 50.</p> :
          <ul className="pl-gaps">{gaps.map((g) => (
            <li key={g.id}><div><b>{g.label}</b><small className="muted">{g.reason}</small></div>
              {g.pick ? <div className="pl-gp"><Link to={`/stocks/${g.pick.symbol}`}><b>{g.pick.symbol}</b></Link><span className={"ssp " + lvl(g.pick.overall)}>{show(g.pick.overall)}</span><small className="muted">top scored here</small></div> : <small className="faint">No scored company available yet</small>}</li>))}</ul>}
      </div>

      {/* 3. Stress view */}
      <div className="pl-sec">
        <h4>Stress view</h4>
        <div className="pl-two">
          <div>
            <small className="pl-k">Resilience</small>
            <div className="pl-meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={res.pct ?? 0} aria-label="Share of holdings with Balance sheet and Quality at 62 or more">
              <i style={{ width: (res.pct ?? 0) + "%" }} className={lvl(res.pct == null ? null : res.pct >= 70 ? 80 : res.pct >= 40 ? 50 : 20)} /></div>
            <p className="pl-mt"><b>{res.pct == null ? "—" : res.pct + "%"}</b> <span className="muted">({res.sound} of {res.total} have Balance sheet and Quality both 62 or more). {res.label}.</span></p>
          </div>
          <div>
            <small className="pl-k">Without the weakest 25% on Balance sheet</small>
            {stress.eligible ? <>
              <p className="pl-mt"><b>{show(stress.before)} → {show(stress.after)}</b> <small className={stress.delta != null && stress.delta > 0 ? "up" : stress.delta != null && stress.delta < 0 ? "down" : ""}>({sg(stress.delta)} pts)</small></p>
              <p className="muted pl-mt">Set aside: {stress.removedSymbols.join(", ")}. If these were removed, the average of the rest would be {show(stress.after)}.</p></> :
              <p className="muted pl-mt">Needs at least {stress.need} shares with a Balance sheet score. Add more to see this.</p>}
          </div>
        </div>
      </div>

      {/* 4. Trend readiness: honest about missing history */}
      <div className="pl-sec">
        <h4>Score trend</h4>
        <p className="muted">No score history is stored for your portfolio yet, so no trend is shown. Today's score is {show(base.score)}; use the report below to keep a dated copy.</p>
      </div>

      {/* 5. Report */}
      <div className="pl-sec pl-rep">
        <div><h4>Portfolio report</h4><p className="muted">A clean one-page summary with score, pillars, bands, sector split and every holding.</p></div>
        <div className="row"><button className="btn primary" onClick={download}>Download portfolio report</button><button className="btn" onClick={print}>Print</button></div>
      </div>
      <p className="faint pl-fine">Information only, not investment advice.</p>
    </section>
  );
}
