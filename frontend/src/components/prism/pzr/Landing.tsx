// /prism landing: company search with suggestions, recent companies with their last stored score, sector chips and a short
// explanation of what Prism is. Also the company picker used on the report page.
import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Icon } from "../../../lib/icons";
import { ActiveFilters, FilterNote, HiddenRows, SearchFilters, useIndexFilter } from "../../SearchFilters";
import { useSlashFocus } from "../../../lib/premium";
import { useSearchIndex, type SearchRow } from "../../../lib/api";
import { indexFacets, sectorAt } from "../../../lib/searchFilters";
import {
  PRISM_NAME, PRISM_NOTE, cleanSymbol, labelTone, partInfo, partsOf, pctWhole, readPrismRecent, score1, statementWord, useStoredSummary,
  type Statement,
} from "../../../lib/prism";
import { partVar } from "../../../lib/prismReport";

/** The prism mark: white light entering a glass prism and leaving as four bands, one per part. */
export function PrismMark({ size = 220 }: { size?: number }) {
  const parts = ["fundamental", "valuation", "quality", "risk"];
  return (
    <svg className="pzr-mark" width={size} height={size * 0.72} viewBox="0 0 220 158" role="img" aria-label="A beam of light enters a prism and splits into four bands: Growth & Profitability, Valuation, Quality and Risk.">
      <defs><linearGradient id="pzr-glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#F4E3B0" stopOpacity=".55" /><stop offset="1" stopColor="#B88A2E" stopOpacity=".2" /></linearGradient></defs>
      <line x1="6" y1="86" x2="92" y2="76" className="pzr-mk-in" />
      <polygon points="86,22 138,128 34,128" className="pzr-mk-glass" /><polygon points="86,22 138,128 34,128" fill="url(#pzr-glass)" />
      {parts.map((k, i) => <line key={k} x1="120" y1={74 + i * 2} x2="214" y2={44 + i * 24} className="pzr-mk-ray" style={{ stroke: partVar(k, i) }} />)}
    </svg>
  );
}

export function StatementSwitch({ value, set, disabled }: { value: Statement; set: (s: Statement) => void; disabled?: boolean }) {
  return (
    <div className="seg pzr-seg" role="group" aria-label="Statement basis">
      {(["consolidated", "standalone"] as Statement[]).map((s) => <button key={s} type="button" className={s === value ? "on" : ""} aria-pressed={s === value} disabled={disabled} onClick={() => set(s)}>{statementWord(s)}</button>)}
    </div>
  );
}

export function Picker({ statement, big = false }: { statement: Statement; setStatement?: (s: Statement) => void; big?: boolean }) {
  const nav = useNavigate();
  const sf = useIndexFilter();
  const [text, setText] = useState(""), [open, setOpen] = useState(false), [cur, setCur] = useState(0);
  const box = useRef<HTMLInputElement>(null);
  useSlashFocus(box);
  const hits = useMemo(() => sf.search(text, 8).map((r) => ({ symbol: r[0], name: r[1] })), [sf.search, text]);   // name, symbol, BSE/NSE code or ISIN; no text with a filter on: the largest companies that pass
  const hidden = useMemo(() => sf.hidden(text, 3), [sf.hidden, text]);                                             // matches that only the filter leaves out
  const typed = text.trim();
  const go = (symbol: string) => { setText(""); setOpen(false); nav(`/prism/${encodeURIComponent(symbol)}${statement === "standalone" ? "?statement=standalone" : ""}`); };
  const submit = () => { const pick = hits[cur] ?? hits[0]; const typed = cleanSymbol(text); if (pick) go(pick.symbol); else if (typed) go(typed); };
  return (
    <div className={"pzr-pick" + (big ? " big" : "")}>
      <div className="pm-search pzr-search sf-host">
        <Icon name="search" />
        <input ref={box} value={text} role="combobox" aria-expanded={open && hits.length > 0} aria-controls="pz-sug" aria-autocomplete="list" aria-label="Choose a company"
          placeholder="Company name or symbol, for example TCS" autoComplete="off" onChange={(e) => { setText(e.target.value); setOpen(true); setCur(0); }}
          onBlur={() => setTimeout(() => setOpen(false), 150)} onFocus={() => setOpen(true)}
          onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setCur((c) => Math.min(hits.length - 1, c + 1)); } else if (e.key === "ArrowUp") { e.preventDefault(); setCur((c) => Math.max(0, c - 1)); } else if (e.key === "Enter") { e.preventDefault(); submit(); } else if (e.key === "Escape") setOpen(false); }} />
        <SearchFilters variant="panel" className="sf-inline" facets={sf.facets} value={sf.filter} onChange={sf.setFilter} count={sf.count} />
        {open && (hits.length > 0 || (typed && sf.data)) && <div className="pm-sug" id="pz-sug" role="listbox">
          {hits.map((h, i) => <button key={h.symbol} type="button" role="option" aria-selected={i === cur} className={i === cur ? "on" : ""} onMouseDown={(e) => e.preventDefault()} onClick={() => go(h.symbol)}><b>{h.symbol}</b><small>{h.name}</small></button>)}
          {typed && <div onMouseDown={(e) => e.preventDefault()}>
            {sf.on && !hits.length && <FilterNote filter={sf.filter} q={typed} onChange={sf.setFilter} hidden={hidden} />}
            {sf.on && hits.length > 0 && <HiddenRows hidden={hidden} filter={sf.filter} onChange={sf.setFilter} />}
            {!sf.on && !hits.length && cleanSymbol(typed) && <p className="sf-empty" role="status">No listed company matches “{typed}” by name, symbol or ISIN. Check the spelling, or <button type="button" onClick={() => go(cleanSymbol(typed))}>try “{cleanSymbol(typed)}” as a symbol</button>.</p>}
          </div>}
        </div>}
      </div>
      <ActiveFilters filter={sf.filter} onChange={sf.setFilter} className="pzr-af" />
    </div>
  );
}

/** A recent company with the score stored for it, if any. Never triggers a calculation. */
function RecentCard({ symbol }: { symbol: string }) {
  const s = useStoredSummary(symbol);
  const d = s.data, rated = !!d && d.status !== "NOT RATED" && d.final != null;
  const tone = d ? labelTone(d.label) : null;
  const parts = rated && d!.parts && d!.partWeights ? partsOf({ parts: d!.parts, partWeights: d!.partWeights }).filter((k) => (d!.partWeights![k] ?? 0) > 0) : [];
  return (
    <li><Link to={`/prism/${symbol}`} className={"pzr-rc" + (tone ? " " + tone.tone : "")} aria-label={d ? `${symbol}: ${rated ? `${score1(d.final)} out of 100, ${tone!.word}` : "not rated"}` : `${symbol}: no stored rating`}>
      <span className="pzr-rc-s">{symbol}</span>
      {s.isLoading ? <span className="skeleton pzr-rc-sk" /> : d ? <>
        <span className="pzr-rc-n">{rated ? score1(d.final) : "—"}</span>
        <span className="pzr-rc-l"><i aria-hidden="true" />{rated ? tone!.word : "Not rated"}{d.status === "PROVISIONAL" ? " · provisional" : ""}</span>
        {parts.length > 0 && <span className="pzr-rc-b" aria-hidden="true">{parts.map((k, i) => <i key={k} style={{ "--c": partVar(k, i), flex: d.partWeights![k] } as React.CSSProperties} title={partInfo(k).name}><b style={{ height: `${Math.max(4, d.parts![k] ?? 0)}%` }} /></i>)}</span>}
        <small>{d.confidence != null ? `${pctWhole(d.confidence)} of inputs · ` : ""}{new Date(d.generatedAt).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</small>
      </> : <span className="pzr-rc-l none">No stored rating yet</span>}
    </Link></li>
  );
}

const NO_SECTOR = "\u0000none";
/** Browse by sector: sector chips, then the companies of one sector. Reads the same all-company list as the search box (never only the scored ones), and a last chip holds the companies with no sector on file. */
export function Browse({ statement }: { statement: Statement }) {
  const [on, setOn] = useState(false), [sector, setSector] = useState<string | null>(null), [all, setAll] = useState(false);
  const idx = useSearchIndex(on);
  const data = idx.data;
  const { sectors, none } = useMemo(() => { const f = indexFacets(data); return { sectors: f.sectors, none: f.unknown.sector }; }, [data]);
  const list = useMemo(() => {
    if (!data || !sector) return [];
    const out: SearchRow[] = [];
    data.rows.forEach((r, i) => { if (r[0] && !r[0].startsWith("^") && (sector === NO_SECTOR ? sectorAt(data, i) == null : sectorAt(data, i) === sector)) out.push(r); });
    return out.sort((a, b) => (a[1] || a[0]).localeCompare(b[1] || b[0]));
  }, [data, sector]);
  const q = statement === "standalone" ? "?statement=standalone" : "";
  const label = sector === NO_SECTOR ? "No sector on file" : sector;
  const shown = all ? list : list.slice(0, 60);
  return (
    <section className="pzr-browse" aria-label="Browse companies">
      <div className="pzr-browse-h"><h3>Browse companies</h3><button type="button" className="pzr-link" aria-expanded={on} onClick={() => setOn(!on)}>{on ? "Hide sectors" : "Show sectors"}</button></div>
      {!on && <p className="pzr-small">Pick a sector, then a company.</p>}
      {on && (idx.isLoading ? <div className="skeleton" style={{ height: 80 }} aria-busy="true" /> : idx.isError ? <p className="pzr-empty">The sector list is not available right now. Search by name or symbol instead.</p> : <>
        <div className="pzr-chipsrow" role="group" aria-label="Sectors">
          {sectors.map((f) => <button type="button" key={f.name} className={"pzr-chip" + (f.name === sector ? " on" : "")} aria-pressed={f.name === sector} onClick={() => { setSector(f.name === sector ? null : f.name); setAll(false); }}>{f.name} <small>{f.n}</small></button>)}
          {none > 0 && <button type="button" className={"pzr-chip" + (sector === NO_SECTOR ? " on" : "")} aria-pressed={sector === NO_SECTOR} onClick={() => { setSector(sector === NO_SECTOR ? null : NO_SECTOR); setAll(false); }}>No sector on file <small>{none}</small></button>}
        </div>
        {sector && <ul className="pzr-colist" aria-label={`Companies in ${label}`}>{shown.map((r) => <li key={r[0]}><Link to={`/prism/${r[0]}${q}`}><b>{r[0]}</b><small>{r[1]}</small></Link></li>)}</ul>}
        {sector && list.length > 60 && !all && <p className="pzr-small">Showing 60 of {list.length}. <button type="button" className="pzr-link" onClick={() => setAll(true)}>Show all {list.length}</button> or use the search box.</p>}
      </>)}
    </section>
  );
}

const WHAT = ["A score out of 100 and a label from Strong to Poor, or Not rated when the evidence is thin", "Four parts: Growth & Profitability, Valuation, Quality and Risk, each with what supports it and what weighs on it", "Every factor with its value, points and status, and which inputs are missing", "A PDF of exactly the calculation you see"];
export const PRISM_WHAT = WHAT;

export function LandingBody({ statement, setStatement }: { statement: Statement; setStatement: (s: Statement) => void }) {
  const recent = readPrismRecent();
  return (
    <div className="wrap pzr-land">
      <section className="pzr-find" aria-label="Find a company">
        <Picker statement={statement} setStatement={setStatement} big />
        <p className="pzr-small">Press <kbd>/</kbd> to search from anywhere on this page.</p>
      </section>
      {recent.length > 0 && (
        <section className="pzr-sec" aria-label="Recently opened">
          <header className="pzr-sh"><h3>Recently opened</h3><p>The last score stored for each company. Opening one never starts a calculation.</p></header>
          <ul className="pzr-recent">{recent.slice(0, 6).map((x) => <RecentCard key={x} symbol={x} />)}</ul>
        </section>
      )}
      <Browse statement={statement} />
      <section className="pzr-what" aria-label={`What ${PRISM_NAME} is`}>
        <div className="pzr-what-art"><PrismMark /></div>
        <div className="pzr-what-t">
          <h3>What you get</h3>
          <p>A company's financial health, split into four parts the way a prism splits light, each read against its own industry group.</p>
          <ul>{WHAT.map((w) => <li key={w}><Icon name="check" />{w}</li>)}</ul>
        </div>
        <div className="pzr-what-h">
          <h3>How it works</h3>
          <p>Choose a company. If a rating was calculated recently it opens at once; otherwise Prism starts calculating it from the latest filings and prices, which usually takes under half a minute, and shows it here when it is ready. Each member can calculate 20 a day.</p>
          <p className="pzr-note">{PRISM_NOTE}</p>
        </div>
      </section>
    </div>
  );
}
