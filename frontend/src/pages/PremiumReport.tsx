import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Icon } from "../lib/icons";
import { useSection, useSummary, type Ownership, type Peers, type Ratios } from "../lib/api";
import { cr, dateIN, fmtUnit, nf, signed, MINUS } from "../lib/format";
import { pushRecent, readRecent, useGold, useSlashFocus } from "../lib/premium";
import { Spark } from "../charts/Small";
import { PILLAR_COLOR } from "../stock/derive";
import { useUniverse } from "../lib/screener";
import { useDocTitle } from "../lib/title";
import { GoldLock, PremiumHead } from "./Premium";

const KEYS = ["pe", "pb", "roe", "roce", "operating_margin", "net_margin", "debt_to_equity", "current_ratio", "dividend_yield"];

function Report({ symbol }: { symbol: string }) {
  useEffect(() => { pushRecent(symbol); }, [symbol]);
  const s = useSummary(symbol), r = useSection<Ratios>(symbol, "ratios"), o = useSection<Ownership>(symbol, "ownership"), p = useSection<Peers>(symbol, "peers");
  useDocTitle(`${symbol} premium report`, `FinLit premium research report for ${symbol}.`);
  if (s.isError) return <div className="state"><h2>We could not build this report</h2><p>That company is not available yet. Choose another.</p></div>;
  if (s.isLoading || !s.data) return <div className="skeleton" style={{ height: 520 }} aria-busy="true" aria-label="Building report" />;
  const d = s.data, q = d.quote, ratios = r.data?.latest || {};
  return (
    <article className="pm-rep" aria-label={`Premium report for ${d.profile.name}`}>
      <p className="pm-noprint" style={{ textAlign: "right" }}><button className="btn primary" onClick={() => window.print()}><Icon name="notes" /> Print or save as PDF</button></p>
      <header className="pm-cover">
        <div><p className="faint" style={{ margin: 0, letterSpacing: ".14em", textTransform: "uppercase", fontSize: 11, fontWeight: 700, color: "var(--gold)" }}>FinLit Ventures · Premium report · {dateIN(new Date().toISOString())}</p>
          <h1 style={{ margin: "8px 0 4px", font: "400 clamp(28px, 4vw, 40px)/1.1 var(--serif)" }}>{d.profile.name}</h1>
          <p className="muted" style={{ margin: 0 }}>{d.profile.symbol} · {d.profile.sector || MINUS}{d.profile.industry ? ` · ${d.profile.industry}` : ""} · {d.meta.statement === "standalone" ? "Standalone" : "Consolidated"} figures</p></div>
        {d.sparkline.c.length > 1 && <div className="spk" aria-label="Price over the last year"><Spark values={d.sparkline.c} color={d.sparkline.c[d.sparkline.c.length - 1] >= d.sparkline.c[0] ? "var(--gain)" : "var(--loss)"} w={220} h={70} /><p className="faint" style={{ margin: 0, fontSize: 12, textAlign: "right" }}>Price, last 12 months</p></div>}
      </header>
      <div className="pm-cards" style={{ marginTop: 18 }}>
        <div className="pm-kpi"><small>Price</small><b>{q.price != null ? "₹" + nf(q.price) : MINUS}</b><i>{signed(q.changePct)} today</i></div>
        <div className="pm-kpi"><small>Market cap</small><b>{q.marketCapCr != null ? "₹" + cr(q.marketCapCr) + " Cr" : MINUS}</b></div>
        <div className="pm-kpi"><small>52-week range</small><b style={{ fontSize: 18 }}>{d.range52.low != null ? nf(d.range52.low) : MINUS} to {d.range52.high != null ? nf(d.range52.high) : MINUS}</b></div>
        <div className="pm-kpi"><small>FinLit score · {d.score.band.label}</small><b>{d.score.overall != null ? Math.round(d.score.overall) : MINUS}<span className="faint" style={{ fontSize: 14 }}> / 100</span></b></div>
      </div>
      {d.thesis && <><h2>Summary</h2><p style={{ lineHeight: 1.65 }}>{d.thesis}</p></>}
      <h2>What drives the score</h2>
      <div className="pm-pillars">{d.score.pillars.map((x) => <div className="pm-pillar" key={x.key}><span>{x.label} <small className="faint">· {x.band.label}</small></span>
        <span className="tr" role="img" aria-label={`${x.label} ${x.score != null ? Math.round(x.score) : "not scored"} out of 100`}><i style={{ width: `${x.score ?? 0}%`, background: `var(${(PILLAR_COLOR as Record<string, string>)[x.key] || "--gold"})` }} /></span><b>{x.score != null ? Math.round(x.score) : MINUS}</b></div>)}</div>
      {(d.strengths.length > 0 || d.watchouts.length > 0) && <div style={{ display: "grid", gap: 18, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
        <div><h2>Strengths</h2><ul>{d.strengths.map((n) => <li key={n.key}><b>{n.title}.</b> {n.text}</li>)}</ul></div>
        <div><h2>Watch-outs</h2><ul>{d.watchouts.map((n) => <li key={n.key}><b>{n.title}.</b> {n.text}</li>)}</ul></div></div>}
      <h2>Key ratios</h2>
      {r.isLoading ? <div className="skeleton" style={{ height: 120 }} /> : <div className="tw"><table className="pm-t"><thead><tr><th>Ratio</th><th className="n">Latest</th><th>Period</th></tr></thead>
        <tbody>{KEYS.filter((k) => ratios[k]).map((k) => <tr key={k}><td>{ratios[k].label}</td><td className="n">{fmtUnit(ratios[k].value, ratios[k].unit)}</td><td>{ratios[k].period}</td></tr>)}</tbody></table></div>}
      <h2>Who owns it</h2>
      {o.data?.latest?.length ? <div className="tw"><table className="pm-t"><thead><tr><th>Holder group</th><th className="n">Share %</th><th className="n">Change in a year</th></tr></thead>
        <tbody>{o.data.latest.map((x) => <tr key={x.key}><td>{x.label}</td><td className="n">{x.value != null ? nf(x.value) : MINUS}</td><td className="n">{x.change1yPts != null ? signed(x.change1yPts, 2, " pts") : MINUS}</td></tr>)}</tbody></table></div> : <p className="muted">Shareholding data is not available for this company yet.</p>}
      {p.data?.items?.length ? <><h2>Peers</h2><div className="tw"><table className="pm-t"><thead><tr><th>Company</th><th className="n">Score</th><th className="n">P/E</th></tr></thead>
        <tbody>{p.data.items.slice(0, 8).map((x) => <tr key={x.symbol}><td><Link to={`/premium/report/${x.symbol}`}>{x.name || x.symbol}</Link></td><td className="n">{x.overall != null ? Math.round(x.overall) : MINUS}</td><td className="n">{x.pe != null ? nf(x.pe, 1) : MINUS}</td></tr>)}</tbody></table></div></> : null}
      <p className="faint" style={{ marginTop: 28, fontSize: 13 }}>Prepared from company filings and market data. Scores are research, not a recommendation to buy or sell. General information, not investment advice. Past performance is not a guide to future returns.</p>
    </article>
  );
}

export function PremiumReportPage() {
  useDocTitle("Premium report", "A printable FinLit research report for any listed company: score, ratios, ownership and peers.");
  const gold = useGold(); const nav = useNavigate(); const { symbol } = useParams();
  const universe = useUniverse(); const [text, setText] = useState(""), [open, setOpen] = useState(false);
  const box = useRef<HTMLInputElement>(null); useSlashFocus(box); const recent = readRecent();
  const sug = useMemo(() => { const t = text.trim().toLowerCase(); return t ? (universe.data?.rows || []).filter((r) => r.symbol.toLowerCase().startsWith(t) || (r.name || "").toLowerCase().includes(t)).slice(0, 8) : []; }, [text, universe.data]);
  if (!gold) return <><PremiumHead eyebrow="Gold dashboard" title="Premium Report" /><GoldLock title="Premium Report" /></>;
  return (
    <>
      <div className="pm-noprint"><PremiumHead eyebrow="Gold dashboard" title="Premium Report"><p>A clean one-document research report for any company. Print it or save it as a PDF to share. <Link to="/premium">All Gold dashboards</Link></p></PremiumHead></div>
      <div className="wrap" style={{ paddingBottom: 56 }}>
        <div className="pm-search pm-noprint" style={{ marginBottom: 24 }}><Icon name="search" />
          <input ref={box} value={text} onChange={(e) => { setText(e.target.value); setOpen(true); }} onBlur={() => setTimeout(() => setOpen(false), 150)} placeholder="Choose a company, for example RELIANCE" aria-label="Choose a company" />
          {open && sug.length > 0 && <div className="pm-sug" role="listbox">{sug.map((r) => <button key={r.symbol} role="option" aria-selected={false} onMouseDown={(e) => e.preventDefault()} onClick={() => { setText(""); nav(`/premium/report/${r.symbol}`); }}><b>{r.symbol}</b><small>{r.name}</small></button>)}</div>}</div>
        {recent.length > 0 && <div className="pm-recent pm-noprint" aria-label="Recently viewed"><span className="faint">Recent</span>{recent.map((x) => <Link key={x} className={"fchip" + (x === symbol?.toUpperCase() ? " on" : "")} to={`/premium/report/${x}`}>{x}</Link>)}</div>}
        {symbol ? <Report key={symbol} symbol={symbol.toUpperCase()} /> : <div className="pm-empty"><b>Choose a company to build its report.</b><p>Try <Link to="/premium/report/RELIANCE">RELIANCE</Link>, <Link to="/premium/report/TCS">TCS</Link> or <Link to="/premium/report/HDFCBANK">HDFCBANK</Link>.</p></div>}
      </div>
    </>
  );
}
