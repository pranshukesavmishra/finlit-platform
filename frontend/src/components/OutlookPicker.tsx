import "../styles/outlook.css";   // the picker is also used by Stress Lab, which does not load the Outlook page
// "Choose a company" for the profit and revenue outlook: a short explanation of the simulator, search by company name or NSE symbol, five quick picks, the companies last
// opened here, and (for the open company) a small market snapshot. Numbers come from the screener list; a missing one is a dash, never zero.
import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { Icon } from "../lib/icons";
import { cr, nf, MINUS } from "../lib/format";
import { QUICK_PICKS, readRecent } from "../lib/outlookPick";
import { useUniverse, type Row } from "../lib/screener";
import { useIndexFilter } from "./SearchFilters";
import { CoLogo } from "./CoLogo";

const pct = (v: number | null | undefined) => (v == null ? MINUS : `${v > 0 ? "+" : v < 0 ? MINUS : ""}${nf(Math.abs(v), 2)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? " up" : " dn");

function Snapshot({ r }: { r: Row }) {
  const items: [string, string, string?][] = [
    ["Price", r.price == null ? MINUS : "₹" + nf(r.price, 2)], ["Today", pct(r.change_pct), tone(r.change_pct)], ["Market cap", r.market_cap == null ? MINUS : "₹" + cr(r.market_cap) + " Cr"],
    ["P/E", r.pe == null ? MINUS : nf(r.pe, 1) + "×"], ["1-year return", pct(r.return_1y), tone(r.return_1y)],
  ];
  return (
    <dl className="olp-snap" aria-label={`${r.name || r.symbol} at a glance`}>
      {items.map(([k, v, t]) => <div key={k}><dt>{k}</dt><dd className={"mono" + (t ?? "")}>{v}</dd></div>)}
    </dl>);
}

/** `current`: the company open on the page (none on the landing page). */
export function OutlookPicker({ current, intro, base = "/outlook", introText }: { current?: string; intro?: boolean; base?: string; introText?: ReactNode }) {
  const to = (s: string) => `${base}/${encodeURIComponent(s)}`;
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const sf = useIndexFilter(true);
  const uni = useUniverse(true);
  const hits = useMemo(() => (q.trim() ? sf.search(q, 8) : []), [sf.search, q]);   // eslint-disable-line react-hooks/exhaustive-deps
  const by = useMemo(() => new Map((uni.data?.rows ?? []).map((r) => [r.symbol.toUpperCase(), r])), [uni.data]);
  const all = readRecent(), recent = all.filter((s) => s !== current?.toUpperCase());
  const shown = current ?? all[0] ?? QUICK_PICKS[0].symbol;       // the landing page shows the last company opened, else Reliance, so it is never empty
  const open = by.get(shown.toUpperCase());
  return (
    <section className="card olp" aria-labelledby="olp-h">
      <h2 id="olp-h">{current ? "Change company" : "Choose a company"}</h2>
      {intro && (introText ? <p className="olp-intro">{introText}</p> : <p className="olp-intro">This simulator estimates a company's <b>revenue and net profit</b> for the next 1, 3 or 5 years from its own reported growth and its sector's. Use <b>our model</b>, or <b>set your own</b> weights and see how the estimate changes. It is a what-if tool built on past results, not a prediction or advice.</p>)}
      {open && <><p className="olp-cap faint">Snapshot: <b>{open.name || open.symbol}</b></p><Snapshot r={open} /></>}
      <label className="ol-search"><Icon name="search" /><span className="sr-only">Search a company by name or NSE symbol</span>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by company name or NSE symbol, e.g. Reliance or TCS" autoComplete="off" spellCheck={false} maxLength={60}
          onKeyDown={(e) => { if (e.key === "Enter" && hits[0]) { e.preventDefault(); nav(to(hits[0][0])); } }} /></label>
      {hits.length > 0 && <ul className="ol-hits" aria-label="Matching companies">{hits.map((h) => <li key={h[0]}><Link to={to(h[0])}><span className="ol-hn"><CoLogo symbol={h[0]} name={h[1]} size={22} inline /><b>{h[1]}</b></span><span className="mono faint">{h[4] || h[0]}</span></Link></li>)}</ul>}
      {q.trim() && sf.idx.data && hits.length === 0 && <p className="faint">No listed company matches “{q.trim()}”.</p>}
      <div className="olp-row"><span className="olp-l" id="olp-qp">Quick picks</span>
        <ul className="olp-chips" aria-labelledby="olp-qp">{QUICK_PICKS.map((p) => { const r = by.get(p.symbol); return (
          <li key={p.symbol}><Link to={to(p.symbol)} className={"olp-chip" + (current?.toUpperCase() === p.symbol ? " on" : "")} aria-current={current?.toUpperCase() === p.symbol ? "page" : undefined}>
            <CoLogo symbol={p.symbol} name={p.name} size={20} inline /><b>{p.name}</b>{r && <small className={"mono" + tone(r.change_pct)}>{pct(r.change_pct)}</small>}</Link></li>); })}</ul></div>
      {recent.length > 0 && (
        <div className="olp-row"><span className="olp-l" id="olp-rc">Last searched</span>
          <ul className="olp-chips" aria-labelledby="olp-rc">{recent.map((s) => <li key={s}><Link to={to(s)} className="olp-chip"><CoLogo symbol={s} name={by.get(s)?.name} size={20} inline /><b>{by.get(s)?.name ?? s}</b><small className="mono faint">{s}</small></Link></li>)}</ul></div>)}
      <p className="ol-disc faint">Estimates from past results, not a prediction or advice.</p>
    </section>);
}
