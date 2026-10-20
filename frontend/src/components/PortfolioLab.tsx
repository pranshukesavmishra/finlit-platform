import { useMemo, useState } from "react";
import { Link } from "react-router";
import type { Row } from "../lib/screener";
import { nf } from "../lib/format";
import { saveFile } from "../stock/derive";
import { BAND_NAMES, applySwaps, buildReportHtml, findGaps, resilience, statsOf, stressView, suggestSwaps, type Holding } from "../lib/portfolioLab";

/** Portfolio lab: what-if swaps, gaps, stress view and a printable report. Everything is simulated in the browser and nothing is saved
 *  unless the page wires `onSwap` and the person presses "Apply to my portfolio". */
export type PortfolioLabProps = {
  lines: { symbol: string; name?: string | null; row?: Row }[];
  universe: Row[];
  /** Called when the person presses "Apply to my portfolio" on a suggestion. */
  onSwap?: (removeSymbol: string, addSymbol: string) => void;
};

const BAND_C: Record<string, string> = { strong: "var(--v-strong)", healthy: "var(--k1)", mixed: "var(--k4)", watch: "var(--v-weak)", none: "var(--s3)" };
const lvl = (v: number | null | undefined) => (v == null ? "na" : v >= 78 ? "hi" : v >= 45 ? "mid" : "lo");
const sg = (d: number | null) => (d == null ? "—" : d > 0 ? `+${d}` : d < 0 ? `−${Math.abs(d)}` : "0");
const show = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : String(Math.round(v)));

function Mix({ s }: { s: ReturnType<typeof statsOf> }) {
  return (
    <div className="pl-mix">
      <div className="breadth big" role="img" aria-label="Portfolio by FinLit band">{(["strong", "healthy", "mixed", "watch", "none"] as const).filter((b) => s.band[b] > 0).map((b) => <i key={b} style={{ flex: s.band[b], background: BAND_C[b] }} />)}</div>
      <ul className="pl-bk">{(["strong", "healthy", "mixed", "watch", "none"] as const).filter((b) => s.band[b] > 0).map((b) => <li key={b}><i style={{ background: BAND_C[b] }} />{BAND_NAMES[b]} <b>{nf(s.band[b], 0)}%</b></li>)}</ul>
    </div>
  );
}

export function PortfolioLab({ lines, universe, onSwap }: PortfolioLabProps) {
  const held: Holding[] = useMemo(() => (lines || []).map((l) => ({ symbol: l.symbol, name: l.name, row: l.row })), [lines]);
  const uni = universe || [];
  const [pick, setPick] = useState<Record<string, string>>({});   // fromSymbol -> toSymbol (simulated)
  const base = useMemo(() => statsOf(held), [held]);
  const groups = useMemo(() => suggestSwaps(held, uni), [held, uni]);
  const gaps = useMemo(() => findGaps(held, uni), [held, uni]);
  const stress = useMemo(() => stressView(held), [held]);
  const res = useMemo(() => resilience(held), [held]);
  const bySym = useMemo(() => new Map(uni.map((r) => [r.symbol, r])), [uni]);

  const swaps = useMemo(() => {
    const o: Record<string, Row | undefined> = {};
    Object.entries(pick).forEach(([f, t]) => { if (held.some((h) => h.symbol === f)) o[f] = bySym.get(t); });
    return o;
  }, [pick, bySym, held]);
  const sim = useMemo(() => statsOf(applySwaps(held, swaps)), [held, swaps]);
  const active = Object.values(swaps).filter(Boolean).length;
  const delta = base.score != null && sim.score != null ? sim.score - base.score : null;

  const toggle = (from: string, to: string) => setPick((p) => { const n = { ...p }; if (n[from] === to) delete n[from]; else n[from] = to; return n; });
  const apply = (from: string, to: string) => { onSwap?.(from, to); setPick((p) => { const n = { ...p }; delete n[from]; return n; }); };

  const download = () => saveFile("FinLit-portfolio-report.html", buildReportHtml(held), "text/html;charset=utf-8");
  const print = () => {
    const f = document.createElement("iframe");
    f.setAttribute("aria-hidden", "true"); f.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
    f.srcdoc = buildReportHtml(held);
    f.onload = () => { try { f.contentWindow?.focus(); f.contentWindow?.print(); } finally { setTimeout(() => f.remove(), 60_000); } };
    document.body.appendChild(f);
  };

  if (!held.length) return (
    <section className="card pl" aria-label="Portfolio lab"><div className="card-h"><h3>Portfolio lab</h3><span className="s">Try changes before you make them</span></div>
      <p className="muted">Add a few shares and the lab will show what a swap would do to your portfolio score, which areas are missing and how it holds up under a stress test.</p></section>
  );
  if (!base.scored) return (
    <section className="card pl" aria-label="Portfolio lab"><div className="card-h"><h3>Portfolio lab</h3><span className="s">Preparing</span></div>
      <p className="muted">Your shares are still being scored. The lab appears as soon as the first scores are ready.</p></section>
  );

  return (
    <section className="card pl" aria-label="Portfolio lab">
      <div className="card-h"><h3>Portfolio lab</h3><span className="s">Simulated, not saved</span></div>
      <p className="muted pl-lead">Try swaps and stress tests on your own list. Scores come from company data; they are not recommendations. All shares count equally.</p>
      {base.unscored > 0 && <p className="pl-note" role="status">{base.unscored} {base.unscored === 1 ? "share is" : "shares are"} still being prepared and left out of the maths.</p>}

      {/* 1. What-if swaps */}
      <div className="pl-sec">
        <h4>What if you swapped</h4>
        <div className={"pl-hero" + (active ? " on" : "")} aria-live="polite">
          <div className="pl-sc"><small>Now</small><b className={"ssp-t " + lvl(base.score)}>{show(base.score)}</b></div>
          <div className="pl-arrow" aria-hidden="true">→</div>
          <div className="pl-sc"><small>{active ? `With ${active} ${active === 1 ? "swap" : "swaps"}` : "No swaps picked"}</small><b className={"ssp-t " + lvl(sim.score)}>{show(sim.score)}</b></div>
          <div className={"pl-d " + (delta == null || delta === 0 ? "" : delta > 0 ? "up" : "down")}>{active ? sg(delta) + " pts" : "Pick a company below"}</div>
          {active > 0 && <button className="btn" onClick={() => setPick({})}>Reset</button>}
        </div>
        {active > 0 && <div className="pl-two">
          <div><small className="pl-k">Band mix after</small><Mix s={sim} /></div>
          <div><small className="pl-k">Sector spread after</small>
            <ul className="pl-sectors">{sim.sectors.slice(0, 6).map((x) => <li key={x.name}><span>{x.name}</span><i style={{ width: Math.max(2, Math.min(100, x.pct)) + "%" }} /><b>{nf(x.pct, 0)}%</b></li>)}</ul></div>
        </div>}
        {!uni.length ? <p className="muted">The company list is still loading, so suggestions will appear in a moment.</p> :
          groups.map((g) => (
            <div className="pl-grp" key={g.from.symbol}>
              <div className="pl-from"><span className="muted">Lowest scoring</span> <Link to={`/stocks/${g.from.symbol}`}><b>{g.from.symbol}</b></Link> <span className={"ssp " + lvl(g.score)}>{g.score}</span> <small className="muted">{g.from.row?.sector || ""}</small></div>
              {g.suggestions.length === 0 ? <p className="faint pl-none">No higher-scored company of similar or larger size was found in the same sector.</p> :
                <ul className="pl-opts">{g.suggestions.map((s) => {
                  const on = pick[g.from.symbol] === s.row.symbol;
                  return (
                    <li key={s.row.symbol} className={on ? "on" : ""}>
                      <div className="pl-who"><Link to={`/stocks/${s.row.symbol}`}><b>{s.row.symbol}</b></Link><small className="muted">{s.row.name || ""}</small></div>
                      <div className="pl-nums"><span className={"ssp " + lvl(s.row.overall)}>{show(s.row.overall)}</span><small>+{s.gain} pts</small>
                        <small>Balance <b>{show(s.row.pillar_balance)}</b> · Quality <b>{show(s.row.pillar_quality)}</b></small></div>
                      <div className="pl-ba">Portfolio {show(s.before)} → <b>{show(s.after)}</b> <small className={s.delta != null && s.delta > 0 ? "up" : ""}>({sg(s.delta)})</small></div>
                      <div className="pl-act">
                        <button className={"btn" + (on ? " on" : "")} aria-pressed={on} onClick={() => toggle(g.from.symbol, s.row.symbol)}>{on ? "Simulating" : "Simulate"}</button>
                        {onSwap && <button className="btn primary" onClick={() => apply(g.from.symbol, s.row.symbol)} title={`Remove ${g.from.symbol} and add ${s.row.symbol} in My portfolio`}>Apply to my portfolio</button>}
                      </div>
                    </li>);
                })}</ul>}
            </div>))}
        <p className="faint pl-fine">Same sector, similar or larger market cap, at least 8 points higher, ranked with extra weight on Balance sheet and Quality. A comparison tool, not advice.</p>
      </div>

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
