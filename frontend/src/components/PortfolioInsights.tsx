import { useMemo } from "react";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { BAND_NAME, portfolioInsights, type InsightLine, type ShareNote } from "../lib/portfolioInsights";

/** Plain-language read of the portfolio (equal-weight). Informational only, not investment advice. */
import { scoreBand } from "../lib/scoreBands";
const lvl = scoreBand;   // one colour rule for every score: lib/scoreBands.ts
const BAND_C: Record<string, string> = { strong: "var(--v-strong)", healthy: "var(--k1)", mixed: "var(--k4)", watch: "var(--v-weak)" };

function Names({ items }: { items: ShareNote[] }) {
  return <ul className="pi-list">{items.map((s) => (
    <li key={s.symbol}><Link to={`/stocks/${s.symbol}`}><b>{s.symbol}</b></Link><span className={"band-dot " + s.band}>{s.score} · {BAND_NAME[s.band]}</span><small className="muted">{s.note}</small></li>))}</ul>;
}

export function PortfolioInsights({ lines }: { lines: InsightLine[] }) {
  const m = useMemo(() => portfolioInsights(lines), [lines]);
  if (m.empty) return null;
  const d = m.diversification, r = m.risk;
  return (
    <section className="card pi" aria-label="Portfolio insights">
      <div className="card-h"><h3><span className="ci"><Icon name="quality" /></span>Portfolio insights</h3><span className="s">Equal-weighted · information only</span></div>
      <p className="muted pi-note">{m.note}</p>
      {!m.health ? null : <>
        <div className="pi-head">
          <div className="pi-score"><span className="pi-l">Portfolio health</span><b className={"ssp-t " + lvl(m.health.score)}>{m.health.score}</b><span className="band-dot" style={{ color: BAND_C[m.health.band] }}>{BAND_NAME[m.health.band]}</span></div>
          <p className="pi-read">{m.health.reading}</p>
        </div>
        {m.priorities.length > 0 && <div className="pi-blk"><h4>What to look at first</h4>
          <ol className="pi-first">{m.priorities.map((p) => <li key={p.symbol}><Link to={`/stocks/${p.symbol}`}><b>{p.title}</b></Link><small className="muted">{p.why}</small></li>)}</ol></div>}
        <div className="pi-g">
          {d && <div className="pi-blk"><h4>Diversification</h4>
            <p>{d.summary}</p>
            <div className="pi-sec" role="img" aria-label="Share of holdings by sector">{d.sectors.slice(0, 5).map((s) => (
              <div key={s.sector} className="pi-bar"><span title={s.sector}>{s.sector}</span><i><u style={{ width: `${Math.max(3, s.share)}%` }} /></i><b>{Math.round(s.share)}%</b></div>))}</div>
            <p className="muted">{d.caps.line}</p>
            {d.flags.length > 0 && <ul className="pi-flags">{d.flags.map((f) => <li key={f}>{f}</li>)}</ul>}</div>}
          <div className="pi-blk"><h4>Pillar profile</h4>
            <p>{m.pillarSentence}</p>
            <div className="pi-pill">{m.pillars.filter((p) => p.avg != null).map((p) => <span key={p.key} className={"ssp " + lvl(p.avg)} title={p.label}>{p.short} {Math.round(p.avg as number)}</span>)}</div></div>
          {r && <div className="pi-blk"><h4>Where the risk sits</h4><ul className="pi-plain">{r.lines.map((t) => <li key={t}>{t}</li>)}</ul></div>}
          {m.enough && <div className="pi-blk"><h4>Strongest holdings</h4><Names items={m.strongest} /></div>}
          {m.enough && <div className="pi-blk"><h4>Weakest holdings</h4><Names items={m.weakest} /></div>}
        </div>
      </>}
      <p className="faint pi-foot">A reading of the scores, not a recommendation to buy or sell anything.</p>
    </section>
  );
}
