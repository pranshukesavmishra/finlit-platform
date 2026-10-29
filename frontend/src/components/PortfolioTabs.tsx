import { useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { HScroll } from "./HScroll";
import { Icon } from "../lib/icons";
import { MINUS } from "../lib/format";
import { scoreBand, type ScoreBand } from "../lib/scoreBands";
import { PRISM_STATUS_WORD } from "../lib/scorePrism";
import {
  BAND_CHIPS, BASIS_WORD, TABS, bandCounts, blankWhy, capText, changeText, columnsFor, dash, isReady, money, monthYear, nextTab,
  priceText, ratioTip, scoreOf, scoreWhy, signedPoints, sizeWord, sortLines, summarize, visibleLines,
  type BandFilter, type Col, type Line, type Model, type Period, type Ready, type Tab,
} from "../lib/portfolioOverview";
import "../styles/scorescreen.css";

/** The imported holdings as three tabs over one table: Overview (share, price, size and the plan's score model), Ratios and Financials.
 *  Silver sees the basic FinLit score and its pillars; Gold only FinLit Prism (four parts and two technical views). Information only, not advice. */

const heat = (v: number | null | undefined) => (v == null ? undefined : ({ "--hc": `hsl(${Math.round(Math.max(0, Math.min(100, v)) * 1.25)} 62% 46%)` } as CSSProperties));
const tone: Record<ScoreBand, string> = { hi: "hi", mid: "mid", lo: "lo", na: "na" };
const BAND_COLOR: Record<ScoreBand, string> = { hi: "var(--band-hi)", mid: "var(--band-mid)", lo: "var(--band-lo)", na: "var(--faint)" };

const Dash = ({ why }: { why: string }) => <span className="pf-dash" title={why}>{MINUS}<span className="sr"> not available: {why}</span></span>;
const Num = ({ v, d = 2, why, tip }: { v: number | null | undefined; d?: number; why?: string | null; tip?: string }) =>
  v == null ? <Dash why={why || "Not available."} /> : <span title={tip}>{dash(v, d)}</span>;

/** The plan's score as one compact badge: number and word, or why there is none (Gold: "Not rated yet" with a Rate now link). */
function ScoreBadge({ l, model }: { l: Line; model: Model }) {
  const s = scoreOf(l.ov, model), why = scoreWhy(l.ov, model);
  if (s.value != null) {
    const p = isReady(l.ov) ? l.ov.prism : undefined;
    return <span className="pzs"><span className={"ssp pzs-n " + tone[s.band]}>{Math.round(s.value)}</span>
      <span className="pzs-l"><b className={tone[s.band]}>{s.word}</b>{model === "prism" && p && p.status && p.status !== "RATED" && <small>{PRISM_STATUS_WORD[p.status] ?? p.status}</small>}</span></span>;
  }
  if (model === "prism" && isReady(l.ov) && (!l.ov.prism || l.ov.prism.state === "none"))
    return <span className="pzs-no" title={why || undefined}>Not rated yet<span className="sr">: {why}</span><Link to={`/prism/${encodeURIComponent(l.symbol)}`} className="pzs-go" aria-label={`Rate ${l.symbol} with Prism now`}>Rate now</Link></span>;
  if (model === "prism" && isReady(l.ov)) return <span className="pzs-no" title={why || undefined}>Not rated<span className="sr">: {why}</span></span>;
  return <span className="faint" title={why || undefined}>{isReady(l.ov) ? MINUS : "Preparing…"}</span>;
}

function ShareCell({ l, flag }: { l: Line; flag?: string }) {
  const h = isReady(l.ov) ? l.ov : null;
  const where = h ? [h.sector, h.industry && h.industry !== h.sector ? h.industry : null].filter(Boolean).join(" · ") : "";
  return <><Link to={`/stocks/${l.symbol}`}><b>{l.symbol}</b></Link><small className="muted">{l.name || h?.name}</small>{where && <small className="faint">{where}</small>}
    {flag && <small className="down" title={flag}> ⚑ {flag}</small>}</>;
}

function Part({ v, name }: { v: number | null | undefined; name: string }) {
  if (v == null) return <span className="ssp na" title={`${name}: not scored for this company`}>{MINUS}<span className="sr">{name}: not scored</span></span>;
  return <span className={"ssp pzs-n " + tone[scoreBand(v)]} title={`${name}: ${Math.round(v)} out of 100`}>{Math.round(v)}</span>;
}
function Trend({ t, name }: { t: { score: number; word: string } | null | undefined; name: string }) {
  if (!t) return <span className="ssp na" title={`${name}: not calculated for this rating`}>{MINUS}<span className="sr">{name}: not calculated</span></span>;
  return <span className="pzs-w" title={`${t.word} (${signedPoints(t.score)} on a scale of ${MINUS}100 to +100)`}><b>{t.word}</b><small>{signedPoints(t.score)}</small></span>;
}

function OverviewCells({ l, h, model, cols, maxCap }: { l: Line; h: Ready; model: Model; cols: Col[]; maxCap: number }) {
  const ch = h.changePct, size = sizeWord(h.marketCapCr), s = scoreOf(h, model);
  return <>{cols.slice(1).map((c) => {
    switch (c.id) {
      case "price": return <td key={c.id} className="hprice">{h.price == null ? <Dash why="No price in the stored report." /> : priceText(h.price)}</td>;
      case "change": return <td key={c.id}>{ch == null ? <Dash why="No change in the stored report." /> : <span className={"hchg " + (ch > 0 ? "up" : ch < 0 ? "down" : "")}>{changeText(ch)}</span>}</td>;
      case "cap": return <td key={c.id} className="hcap">{h.marketCapCr == null ? <Dash why="No market cap in the stored report." /> : <><span className="hcb" style={{ "--w": (h.marketCapCr / maxCap).toFixed(3) } as CSSProperties}><i /></span>{capText(h.marketCapCr)}{size && <small className="pf-size">{size}</small>}</>}</td>;
      case "score": return <td key={c.id}>{model === "finlit" && s.value != null
        ? <span className={"hscore " + (h.finlit?.band || "")} style={heat(s.value)}><span className="hsb"><i style={{ width: s.value + "%" }} /></span><b>{s.value}</b><em>{s.word}</em></span>
        : <ScoreBadge l={l} model={model} />}</td>;
      default: {
        if (c.id.startsWith("p_")) { const k = c.id.slice(2) as "fundamental"; return <td key={c.id}><Part v={h.prism?.parts?.[k]} name={c.label} /></td>; }
        if (c.id.startsWith("t_")) { const k = c.id.slice(2) as "shortTerm"; return <td key={c.id}><Trend t={h.prism?.[k]} name={c.label} /></td>; }
        if (c.id.startsWith("f_")) { const k = c.id.slice(2) as "quality"; const v = h.finlit?.pillars[k]; return <td key={c.id}><span className={"hp " + scoreBand(v)} style={heat(v)} title={v == null ? `${c.label}: not scored` : `${c.label}: ${v} out of 100`}>{v == null ? MINUS : v}</span></td>; }
        return <td key={c.id} />;
      }
    }
  })}</>;
}

function RatioCells({ l, h, model, cols }: { l: Line; h: Ready; model: Model; cols: Col[] }) {
  const size = sizeWord(h.marketCapCr), ch = h.changePct;
  return <>{cols.slice(1).map((c) => {
    switch (c.id) {
      case "score": return <td key={c.id}><ScoreBadge l={l} model={model} /></td>;
      case "price": return <td key={c.id} className="hprice">{h.price == null ? <Dash why="No price in the stored report." /> : priceText(h.price)}</td>;
      case "change": return <td key={c.id}>{ch == null ? <Dash why="No change in the stored report." /> : <span className={"hchg " + (ch > 0 ? "up" : ch < 0 ? "down" : "")}>{changeText(ch)}</span>}</td>;
      case "cap": return <td key={c.id} className="hcap">{h.marketCapCr == null ? <Dash why="No market cap in the stored report." /> : <>{capText(h.marketCapCr)}{size && <small className="pf-size">{size}</small>}</>}</td>;
      default: { const f = h.ratios[c.id as keyof Ready["ratios"]]; return <td key={c.id}><Num v={f.value} why={f.why} tip={ratioTip(f, c.label.replace(/ \(.*\)$/, ""))} /></td>; }
    }
  })}</>;
}

function FinancialCells({ l, h, model, cols, period }: { l: Line; h: Ready; model: Model; cols: Col[]; period: Period }) {
  const s = h.financials[period], ch = h.changePct;
  return <>{cols.slice(1).map((c) => {
    switch (c.id) {
      case "score": return <td key={c.id}><ScoreBadge l={l} model={model} /></td>;
      case "price": return <td key={c.id} className="hprice">{h.price == null ? <Dash why="No price in the stored report." /> : priceText(h.price)}</td>;
      case "change": return <td key={c.id}>{ch == null ? <Dash why="No change in the stored report." /> : <span className={"hchg " + (ch > 0 ? "up" : ch < 0 ? "down" : "")}>{changeText(ch)}</span>}</td>;
      case "yearEnd": return <td key={c.id} title={s.period ? `${s.period} (${s.periodEnd})` : undefined}>{s.periodEnd ? monthYear(s.periodEnd) : <Dash why={blankWhy(h, "revenue", period) || "No statement is stored yet."} />}</td>;
      case "basis": return <td key={c.id}>{h.basis ? BASIS_WORD[h.basis] : <Dash why="The report does not say which statement it used." />}</td>;
      default: { const f = s[c.id as "revenue"]; const d = c.id === "eps" || c.id === "tax_ratio" ? 2 : 0;
        return <td key={c.id}>{f?.value == null ? <Dash why={blankWhy(h, c.id, period) || "Not available."} /> : <span title={f.note}>{c.id === "tax_ratio" ? dash(f.value, 1) : money(f.value, d)}</span>}</td>; }
    }
  })}</>;
}

/** The tab strip (Overview, Ratios, Financials): arrow keys, Home and End move between tabs; scrolls sideways on a phone. The panel it controls has id "pf-panel". */
export function TabStrip({ tab, onTab }: { tab: Tab; onTab: (t: Tab) => void }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: KeyboardEvent, i: number) => {
    const to = nextTab(TABS[i].id, e.key);
    if (!to) return;
    e.preventDefault(); onTab(to); refs.current[TABS.findIndex((t) => t.id === to)]?.focus();
  };
  return (
    <div className="pf-tabs" role="tablist" aria-label="Portfolio views">
      {TABS.map((t, i) => <button key={t.id} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" id={`pf-tab-${t.id}`} aria-selected={tab === t.id} aria-controls="pf-panel" tabIndex={tab === t.id ? 0 : -1}
        className={tab === t.id ? "on" : ""} onClick={() => onTab(t.id)} onKeyDown={(e) => onKey(e, i)}>{t.label}</button>)}
    </div>
  );
}

export type PortfolioTableProps = {
  lines: Line[]; model: Model; tab: Tab; period: Period; limit: number; state: "loading" | "ready" | "error"; errorText?: string;
  onPeriod: (p: Period) => void; onExport: () => void;
  flags?: Record<string, string>; actions?: (symbol: string) => ReactNode;
};

export function PortfolioTable({ lines, model, tab, period, limit, state, errorText, onPeriod, onExport, flags, actions }: PortfolioTableProps) {
  const cols = useMemo(() => columnsFor(tab, model, period), [tab, model, period]);
  const [sortId, setSortId] = useState("score"), [dir, setDir] = useState<1 | -1>(-1);
  const [band, setBand] = useState<BandFilter>(null), [q, setQ] = useState("");
  const counts = useMemo(() => bandCounts(lines, model), [lines, model]);
  const col = cols.find((c) => c.id === sortId) || cols.find((c) => c.id === "score");
  const shown = useMemo(() => sortLines(visibleLines(lines, q, band, model), col, dir), [lines, q, band, model, col, dir]);
  const maxCap = useMemo(() => Math.max(1, ...lines.map((l) => (isReady(l.ov) ? l.ov.marketCapCr ?? 0 : 0))), [lines]);
  const sum = useMemo(() => summarize(lines, model), [lines, model]);
  const head = (c: Col) => !c.sort ? <th key={c.id} scope="col">{c.label}</th> :
    <th key={c.id} scope="col" aria-sort={col?.id === c.id ? (dir === 1 ? "ascending" : "descending") : "none"} title={c.hint}>
      <button type="button" className={"hsort" + (col?.id === c.id ? " on" : "")} onClick={() => { if (col?.id === c.id) setDir((d) => (d === 1 ? -1 : 1)); else { setSortId(c.id); setDir(c.id === "share" ? 1 : -1); } }}>{c.label}<i aria-hidden="true">{col?.id === c.id ? (dir === 1 ? "▲" : "▼") : "↕"}</i></button></th>;
  const unit = model === "prism" ? "Prism" : "FinLit";
  const avgFor = (c: Col) => c.id === "score" ? (sum.average == null ? null : Math.round(sum.average)) : sum.parts.find((p) => p.label === c.label)?.value ?? null;

  return (
    <section className="card hold-card pf-tabs-card"><div className="card-h"><h3><span className="ci"><Icon name="table" /></span>Your shares</h3>
      <span className="s">{shown.length === lines.length ? lines.length : `${shown.length} of ${lines.length}`} · limit {limit}</span>
      <button type="button" className="btn" onClick={onExport} disabled={!lines.length}>Export CSV</button></div>
        <div className="hold-bar">
          <div className="hold-chips" role="group" aria-label={`Filter by ${unit} score colour`}>
            <button type="button" className={"hchip" + (band == null ? " on" : "")} aria-pressed={band == null} onClick={() => setBand(null)}>All <b>{lines.length}</b></button>
            {BAND_CHIPS.filter((b) => counts[b.band]).map((b) => <button key={b.band} type="button" className={"hchip" + (band === b.band ? " on" : "")} aria-pressed={band === b.band} title={b.rule}
              style={{ "--bc": BAND_COLOR[b.band] } as CSSProperties} onClick={() => setBand(band === b.band ? null : b.band)}><i />{b.label} <b>{counts[b.band]}</b></button>)}
          </div>
          {tab === "financials" && <div className="seg pf-period" role="group" aria-label="Period shown">
            {([["year", "Latest year"], ["quarter", "Latest quarter"]] as const).map(([p, label]) => <button key={p} type="button" aria-pressed={period === p} onClick={() => onPeriod(p)}>{label}</button>)}</div>}
          <input className="hold-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a share or sector" aria-label="Find a share or sector in your portfolio" />
        </div>
        {state === "error" && <p className="pf-miss" role="alert">{errorText || "The scores could not be loaded. Try again in a moment."}</p>}
        <HScroll label="table"><table className={"qtt hold hold-heat pf-t pf-t-" + tab}>
          <caption className="sr">{TABS.find((t) => t.id === tab)?.label} of your shares</caption>
          <thead><tr>{cols.map(head)}{tab === "overview" && actions && <th scope="col"><span className="sr">Actions</span></th>}</tr></thead>
          <tbody>{shown.map((l) => { const h = l.ov; return (
            <tr key={l.symbol}><td><ShareCell l={l} flag={flags?.[l.symbol]} /></td>
              {isReady(h)
                ? tab === "overview" ? <OverviewCells l={l} h={h} model={model} cols={cols} maxCap={maxCap} /> : tab === "ratios" ? <RatioCells l={l} h={h} model={model} cols={cols} /> : <FinancialCells l={l} h={h} model={model} cols={cols} period={period} />
                : <td colSpan={cols.length - 1} className="faint pf-wait">{h ? (h.status === "preparing" ? "Preparing… " : "") + h.reason : state === "error" ? "Not loaded." : "Preparing…"}</td>}
              {tab === "overview" && actions && <td className="ra">{actions(l.symbol)}</td>}</tr>); })}
            {!shown.length && <tr><td colSpan={cols.length + (tab === "overview" && actions ? 1 : 0)} className="faint" style={{ textAlign: "center", padding: 24 }}>{lines.length ? "No share matches this filter." : "No shares yet."}</td></tr>}</tbody>
          {tab === "overview" && sum.scored > 0 && !band && !q.trim() && <tfoot><tr className="pf-avg"><th scope="row">Portfolio average<small className="muted">{sum.scored} scored {sum.scored === 1 ? "share" : "shares"}, counted equally</small></th>
            {cols.slice(1).map((c) => { const v = avgFor(c); return <td key={c.id}>{v == null ? "" : <span className={"ssp pzs-n " + tone[scoreBand(v)]}>{Math.round(v)}</span>}</td>; })}{actions && <td />}</tr></tfoot>}
        </table></HScroll>
        <p className="faint pf-fine">
          {tab === "overview" && (model === "prism"
            ? "Fundamentals, Valuation, Quality and Risk run 0 to 100 (green from 70, orange 50 to 69, red under 50; a high Risk score means lower risk). Short and long term are the price-trend readings from −100 to +100. They describe the trend only and are not part of the Prism score."
            : "Each pillar runs 0 to 100 (green from 70, orange 50 to 69, red under 50).")}
          {tab === "ratios" && "These are the figures on each company's own page (the data provider's, with the period on hover). A dash says why on hover. Industry P/E is not stored, so it is not shown."}
          {tab === "financials" && `The latest ${period === "year" ? "full year" : "quarter"} in each company's stored statements, in ₹ crore except EPS. Tax ratio is tax divided by profit before tax from the same statement.`}
          {" "}Shares count equally; the page takes share names only, so no quantity-weighted totals are shown. Information only, not investment advice.</p>
        {state === "loading" && <p className="faint pf-fine" role="status">Loading the scores…</p>}
    </section>
  );
}

/** The four tiles over the Overview: how many shares, the average score of the plan's model, the band mix (green, orange, red) and the sector spread. Shares count equally. */
export function SummaryTiles({ lines, model, limit }: { lines: Line[]; model: Model; limit: number }) {
  const sum = useMemo(() => summarize(lines, model), [lines, model]);
  const top = sum.sectors[0], avg = sum.average == null ? null : Math.round(sum.average);
  const tile = (color: string): CSSProperties => ({ "--tc": color } as CSSProperties);
  return (
    <div className="pf-k" aria-label="Portfolio summary">
      <div className="card ipo-t" style={tile("var(--k1)")}><span>Shares</span><b>{sum.shares}</b><small>{sum.preparing ? `${sum.preparing} being prepared` : `of ${limit} on your plan`}</small></div>
      <div className="card ipo-t" style={tile("var(--k7)")}><span>Average {model === "prism" ? "Prism" : "FinLit"} score</span><b className={"ssp-t " + scoreBand(avg)}>{avg == null ? MINUS : avg}</b>
        <small>{sum.scored ? `average of ${sum.scored} scored ${sum.scored === 1 ? "share" : "shares"}` : "no share is scored yet"}</small></div>
      <div className="card ipo-t" style={tile("var(--band-hi)")}><span>Score colours</span>
        <b className="pf-mix" aria-label={`${sum.bands.hi} green, ${sum.bands.mid} orange, ${sum.bands.lo} red`}><i className="hi">{sum.bands.hi}</i><i className="mid">{sum.bands.mid}</i><i className="lo">{sum.bands.lo}</i></b>
        <small>green 70+ · orange 50 to 69 · red under 50{sum.bands.na ? ` · ${sum.bands.na} not scored` : ""}</small></div>
      <div className="card ipo-t" style={tile("var(--k4)")}><span>Sectors</span><b>{sum.sectors.length || MINUS}</b>
        <small>{top ? `largest: ${top.name} (${top.count} of ${sum.shares})` : "sectors appear as the reports are ready"}</small></div>
    </div>
  );
}
