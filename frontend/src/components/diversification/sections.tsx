import { useState, type ReactNode } from "react";
import type { Diversification, Horizon, TiltPart } from "./types";
import * as W from "./wording";

/** A bar whose width is a share of `max`; the value is always printed next to it, so the bar is only a picture of the number. */
export function Bar({ value, max, tick }: { value: number; max: number; tick?: number }) {
  const w = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return <span className="dv-bar" aria-hidden="true"><i style={{ width: `${w}%` }} />{tick != null && max > 0 && <b style={{ left: `${Math.min(100, (tick / max) * 100)}%` }} />}</span>;
}

export const Section = ({ id, title, lede, aside, children }: { id: string; title: string; lede?: ReactNode; aside?: ReactNode; children: ReactNode }) => (
  <section className="dv-sec" aria-labelledby={`dv-${id}`}><div className="dv-sech"><h3 id={`dv-${id}`}>{title}</h3>{aside}</div>{lede && <p className="dv-lede">{lede}</p>}{children}</section>
);

export function BandScale({ value }: { value: number }) {
  return (
    <div className="dv-scale">
      <div className="dv-scale-bar" role="img" aria-label={`Score ${value} on a 0 to 100 scale. 0 to 39 Concentrated, 40 to 59 Somewhat concentrated, 60 to 79 Fairly spread, 80 and above Widely spread.`}>
        {W.BANDS.map((b) => <i key={b.label} className={value >= b.from && value <= b.to ? "on" : ""} style={{ flex: b.to - b.from + 1 }} />)}
        <b style={{ left: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
      <div className="dv-scale-k" aria-hidden="true">{W.BANDS.map((b) => <span key={b.label} className={value >= b.from && value <= b.to ? "on" : ""} style={{ flex: b.to - b.from + 1 }}>{b.from === 80 ? "80+" : `${b.from}–${b.to}`} {"·"} {b.label}</span>)}</div>
    </div>
  );
}

export function ScoreBlock({ d, listLabel }: { d: Diversification; listLabel?: string }) {
  const s = d.score!;
  return (
    <div className="dv-score">
      <div className="dv-score-l">
        <p className="dv-eyebrow">Diversification score{listLabel ? ` · ${listLabel}` : ""}</p>
        <p className="dv-big"><span className="num">{s.value}</span><small>/ 100</small><span className="dv-chip">{s.band}</span></p>
        <p className="dv-headline">{W.headlineSentence(d)}</p>
        <BandScale value={s.value} />
        <p className="dv-note">{W.NOT_SAFETY} {W.SCORE_FORMULA}</p>
      </div>
      <div className="dv-parts">
        <div className="dv-part"><div className="dv-part-h"><b>Co-movement</b><span className="num">{s.coMovement} <small>{"·"} 60% of score</small></span></div><Bar value={s.coMovement} max={100} /><p>{W.partCoText(d)}</p></div>
        <div className="dv-part"><div className="dv-part-h"><b>Sector spread</b><span className="num">{s.sectorSpread} <small>{"·"} 40% of score</small></span></div><Bar value={s.sectorSpread} max={100} /><p>{W.partSectorText(d)}</p></div>
      </div>
    </div>
  );
}

export function HorizonToggle({ value, onChange }: { value: Horizon; onChange: (h: Horizon) => void }) {
  return (
    <div className="dv-toggle-row">
      <span className="dv-lab" id="dv-hz-l">Correlations from</span>
      <div className="dv-seg" role="radiogroup" aria-labelledby="dv-hz-l">{W.HORIZONS.map((h) => <button key={h.id} type="button" role="radio" aria-checked={value === h.id} className={value === h.id ? "on" : ""} onClick={() => onChange(h.id)}>{h.label}</button>)}</div>
      <span className="dv-faint">{W.SCORE_ALWAYS_WEEKLY}</span>
    </div>
  );
}

export function Tiles({ w, v, h }: { w: Diversification; v: Diversification; h: Horizon }) {
  const m = h === "monthly" ? v.market : w.market, st = w.stress;
  return (
    <div className="dv-tiles">
      <div className="dv-tile"><span className="dv-lab">Average correlation between pairs</span><b className="num">{W.corr(v.headline!.avgCorrelation)}</b><small>0 = unrelated, 1 = move identically</small></div>
      <div className="dv-tile"><span className="dv-lab">Market sensitivity (beta to NIFTY 50)</span>
        {h === "yearly" || !m ? <><b className="num">{"–"}</b><small>Not shown on yearly returns: too few years to state a beta.</small></>
          : <><b className="num">{W.num(m.betaEqual)}</b><small>1.00 = moves in line with the index {"·"} {W.BASIS_EQUAL}{h === "monthly" && m.benchmarkReturns ? ` · ${m.benchmarkReturns} monthly returns` : ""}{h === "weekly" && m.betaMcap != null ? ` (${W.num(m.betaMcap)} ${W.BASIS_MCAP})` : ""}</small></>}</div>
      <div className="dv-tile"><span className="dv-lab">In NIFTY 50's {st?.worstWeeks ?? 10} worst weeks, on average</span>
        {st ? <><b className="num">{W.pct(st.equalAvgPct, 1)} <small>vs NIFTY 50 {W.pct(st.benchmarkAvgPct, 1)}</small></b><small>These stocks {W.BASIS_EQUAL}{st.mcapAvgPct != null ? ` (${W.pct(st.mcapAvgPct, 1)} ${W.BASIS_MCAP})` : ""} {"·"} weekly returns</small></>
          : <small>Not available.</small>}</div>
    </div>
  );
}

export function SpreadBlock({ d }: { d: Diversification }) {
  const max = Math.max(1, ...d.spread.sectors.map((s) => s.count));
  return (
    <Section id="spread" title="Spread by count" lede={W.spreadSentence(d)}>
      <ul className="dv-rows">{d.spread.sectors.map((s) => <li key={s.name}><span>{s.name}</span><Bar value={s.count} max={max} /><b className="num">{s.count}</b></li>)}</ul>
      <p className="dv-meta"><b>{W.sizeLine(d)}</b></p><p className="dv-meta"><b>{W.groupLine(d)}</b></p>
      {W.unclassifiedNote(d) && <p className="dv-note">{W.unclassifiedNote(d)}</p>}
    </Section>
  );
}

export function GroupsBlock({ d, v, h }: { d: Diversification; v: Diversification; h: Horizon }) {
  if (h === "yearly") {
    const rows = [...(v.mostRelated || []), ...(v.leastRelated || [])];
    return (
      <Section id="groups" title="Most and least related pairs" lede="Indicative only: yearly returns are too few to form groups.">
        <ul className="dv-pairs">{rows.map((p, i) => <li key={i}><span>{W.pairNames(d, p.pair)}</span><b className="num">{W.corr(p.correlation)}</b></li>)}</ul>
        <p className="dv-note">{i18nMost}</p>
      </Section>
    );
  }
  const cl = v.clusters || [];
  return (
    <Section id="groups" title="Groups that move together" lede={W.clusterIntroFor(h)}>
      {cl.length > 0 && <ul className="dv-clusters">{cl.map((c, i) => <li key={i}><span className="dv-tags">{c.symbols.map((s) => <em key={s}>{W.nameOf(d, s)}</em>)}</span><span className="dv-avg">average <b className="num">{W.corr(c.avgCorrelation)}</b></span></li>)}</ul>}
      <p className="dv-note">{W.otherStocks(v)}</p>
    </Section>
  );
}
const i18nMost = "Pairs are ranked by yearly correlation, highest first and lowest last.";

export function RecentBlock({ d }: { d: Diversification }) {
  const r = d.recentVsLongRun; if (!r) return null;
  const Rows = ({ rows }: { rows: typeof r.largestRises }) => <ul className="dv-pairs">{rows.map((p, i) => <li key={i}><span>{W.pairNames(d, p.pair)}</span><b className="num">{W.corr(p.longRun)} {W.ARROW} {W.corr(p.recent)}</b></li>)}</ul>;
  return (
    <Section id="recent" title="Last year vs 3 years" lede={W.recentSentence(d)}>
      <div className="dv-two">
        <div className="dv-box"><span className="dv-lab">Last 1 year ({r.recent.weeks} weeks)</span><p><b className="num">{W.num(r.recent.effectiveStocks, 1)}</b> effective stocks {"·"} average correlation {W.corr(r.recent.avgCorrelation)}</p></div>
        <div className="dv-box"><span className="dv-lab">3 years ({r.longRun.weeks} weeks)</span><p><b className="num">{W.num(r.longRun.effectiveStocks, 1)}</b> effective stocks {"·"} average correlation {W.corr(r.longRun.avgCorrelation)}</p></div>
      </div>
      <div className="dv-two"><div><span className="dv-lab">Largest rises in correlation</span><Rows rows={r.largestRises} /></div><div><span className="dv-lab">Largest falls in correlation</span><Rows rows={r.largestFalls} /></div></div>
      <p className="dv-note">{W.recentFoot(d)}</p>
    </Section>
  );
}

export function RiskBlock({ d, view, by, onView, onBy }: { d: Diversification; view: "equal" | "mcap"; by: "sector" | "stock"; onView: (v: "equal" | "mcap") => void; onBy: (b: "sector" | "stock") => void }) {
  const mcapOk = !!d.riskShare?.mcap;
  const rs = (view === "mcap" && d.riskShare?.mcap ? d.riskShare.mcap : d.riskShare!.equal);
  const rows = by === "sector" ? rs.sectors.map((s) => ({ k: s.name, label: s.name, risk: s.pct, amount: s.amountPct })) : rs.stocks.map((s) => ({ k: s.symbol, label: W.nameOf(d, s.symbol), risk: s.pct, amount: s.weightPct }));
  const max = Math.max(1, ...rows.flatMap((r) => [r.risk, r.amount]));
  const b = d.basket!, cur = view === "mcap" && b.mcap ? b.mcap : b.equal;
  const per = view === "equal" ? ` (${W.pct(100 / d.included)} per stock)` : "";
  return (
    <Section id="risk" title="Share of risk" lede={W.riskSentence(d, view, by)} aside={
      <div className="dv-ctrl">
        <div className="dv-seg" role="radiogroup" aria-label="Basis of the amounts">
          <button type="button" role="radio" aria-checked={view === "equal"} className={view === "equal" ? "on" : ""} onClick={() => onView("equal")}>If equal amounts</button>
          <button type="button" role="radio" aria-checked={view === "mcap"} className={view === "mcap" ? "on" : ""} disabled={!mcapOk} onClick={() => onView("mcap")}>If sized by company value</button>
        </div>
        <div className="dv-seg" role="radiogroup" aria-label="Group the risk by">
          <button type="button" role="radio" aria-checked={by === "sector"} className={by === "sector" ? "on" : ""} onClick={() => onBy("sector")}>By sector</button>
          <button type="button" role="radio" aria-checked={by === "stock"} className={by === "stock" ? "on" : ""} onClick={() => onBy("stock")}>By stock</button>
        </div>
      </div>}>
      {!mcapOk && <p className="dv-note">Company value is not on file for {d.mcapMissing?.length ? d.mcapMissing.join(", ") : "some of these stocks"}, so the company-value view is not shown.</p>}
      <p className="dv-key"><span><i className="a" />Share of risk</span><span><i className="b" />Share of the amount{per}</span></p>
      <ul className="dv-rows risk">{rows.map((r) => <li key={r.k}><span>{r.label}</span><Bar value={r.risk} max={max} tick={r.amount} /><b className="num">{W.pct(r.risk)} <small>of risk {"·"} {W.pct(r.amount)} of amount</small></b></li>)}</ul>
      <p className="dv-meta"><b>These stocks {view === "equal" ? W.BASIS_EQUAL : W.BASIS_MCAP}: swings of {W.pct(cur.volPct)} a year, worst fall {W.pct(cur.maxDrawdownPct)}</b>
        <b>NIFTY 50: swings of {W.pct(b.benchmark.volPct)} a year, worst fall {W.pct(b.benchmark.maxDrawdownPct)}</b></p>
    </Section>
  );
}

export function EachStock({ d, v, h }: { d: Diversification; v: Diversification; h: Horizon }) {
  const ov = new Map((v.overlap || d.overlap || []).map((o) => [o.symbol, o.avgCorrelation]));
  const beta = new Map((d.market?.stocks || []).map((s) => [s.symbol, s.beta])), fell = new Map((d.stress?.stocks || []).map((s) => [s.symbol, s.fellMoreThanIndex]));
  const sector = new Map(d.spread.stocks.map((s) => [s.symbol, s.sector]));
  const order = [...(v.overlap || d.overlap || [])].map((o) => o.symbol);
  const of = d.stress?.worstWeeks ?? 10;
  return (
    <Section id="each" title="Each stock">
      <table className="dv-table"><thead><tr><th scope="col">Stock</th><th scope="col">Sector</th><th scope="col" className="r">Moves with the rest{h !== "weekly" ? ` (${h})` : ""}</th><th scope="col" className="r">Beta to NIFTY 50 (weekly)</th><th scope="col" className="r">Fell more than NIFTY 50 (weekly)</th></tr></thead>
        <tbody>{order.map((s) => <tr key={s}><th scope="row" data-label="Stock">{W.nameOf(d, s)}</th><td data-label="Sector">{sector.get(s)}</td><td data-label="Moves with the rest" className="r num">{ov.has(s) ? W.corr(ov.get(s)!) : "–"}</td>
          <td data-label="Beta to NIFTY 50" className="r num">{beta.has(s) ? W.num(beta.get(s)!) : "–"}</td><td data-label="Fell more than NIFTY 50" className="r num">{fell.has(s) ? W.fellText(fell.get(s)!, of) : "–"}</td></tr>)}</tbody></table>
      <p className="dv-note">{W.eachStockFoot(d)}</p>
    </Section>
  );
}

export function TiltRow({ p }: { p: TiltPart }) {
  const at = p.avgPercentile;
  return (
    <li><span>{p.part}</span>
      <span className="dv-track" aria-hidden="true"><i className="band" />{at != null && <b style={{ left: `${at}%` }} />}</span>
      <span className="dv-tilt-v">{at == null ? <>{W.tiltRead(p)}</> : <><b className="num">{W.tiltPercentile(p)}</b> {"·"} {W.tiltRead(p)}</>}</span></li>
  );
}

export function TiltBlock({ d }: { d: Diversification }) {
  const t = d.styleTilt; if (!t) return null;
  if ("locked" in t) return <Section id="tilt" title="Style tilt"><p className="dv-note dv-locked">{t.reason}</p></Section>;
  const rated = t.parts.some((p) => p.avgPercentile != null);
  return (
    <Section id="tilt" title="Style tilt" lede={rated ? t.sentence : "None of these stocks has a Prism rating yet, so there is no style tilt to show."}>
      {rated && <ul className="dv-tilt">{t.parts.map((p) => <TiltRow key={p.part} p={p} />)}</ul>}
      {rated && <p className="dv-note">{W.tiltFoot(t.universe)}</p>}
      {W.notRatedNote(t.notRated) && <p className="dv-note">{W.notRatedNote(t.notRated)}</p>}
    </Section>
  );
}

/** A grid of pair correlations in one hue: the stronger the shade, the higher the correlation. Negative pairs stay unshaded and say so in their label. */
export function Heatmap({ d }: { d: Diversification }) {
  const [open, setOpen] = useState(false);
  const m = d.matrix; if (!m) return null;
  const n = m.symbols.length, showNum = n <= 10;
  return (
    <details className="dv-heat" onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>Pair correlations, weekly returns</summary>
      {open && <div className="dv-heat-w"><table><caption className="sr-only">Correlation of weekly returns between each pair of stocks</caption>
        <thead><tr><td />{m.symbols.map((s) => <th key={s} scope="col" title={W.nameOf(d, s)}><span>{s}</span></th>)}</tr></thead>
        <tbody>{m.symbols.map((r, i) => <tr key={r}><th scope="row">{r}</th>{m.values[i].map((v, j) => <td key={j} title={`${W.nameOf(d, r)} & ${W.nameOf(d, m.symbols[j])}: ${W.corr(v)}`} aria-label={`${r} and ${m.symbols[j]} ${W.corr(v)}`}
          style={{ background: `color-mix(in srgb, var(--dv-hue) ${Math.round(Math.max(0, v) * 100)}%, transparent)` }}>{showNum ? W.corr(v) : ""}</td>)}</tr>)}</tbody></table>
        <p className="dv-note">Darker means the two stocks' weekly returns have moved together more. Pairs with a negative correlation are left unshaded.</p></div>}
    </details>
  );
}
