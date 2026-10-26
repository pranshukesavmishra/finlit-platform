// /prism landing: company search with suggestions, recent companies with their last stored score, sector chips and a short
// explanation of what Prism is. Also the company picker used on the report page.
import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Icon } from "../../../lib/icons";
import { useSearchIndex } from "../../../lib/api";
import { rankCompanies } from "../../../lib/companySearch";
import { useSlashFocus } from "../../../lib/premium";
import { useUniverse } from "../../../lib/screener";
import {
  PRISM_NAME, PRISM_NOTE, cleanSymbol, labelTone, partInfo, partsOf, pctWhole, readPrismRecent, score1, statementWord, useStoredSummary,
  type Statement,
} from "../../../lib/prism";
import { partVar } from "../../../lib/prismReport";

/** The prism mark: white light entering a glass prism and leaving as four bands, one per part. */
export function PrismMark({ size = 220 }: { size?: number }) {
  const parts = ["fundamental", "valuation", "quality", "risk"];
  return (
    <svg className="pzr-mark" width={size} height={size * 0.72} viewBox="0 0 220 158" role="img" aria-label="A beam of light enters a prism and splits into four bands: Fundamentals, Valuation, Quality and Risk.">
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

export function Picker({ statement, setStatement, big = false }: { statement: Statement; setStatement: (s: Statement) => void; big?: boolean }) {
  const nav = useNavigate();
  const idx = useSearchIndex(true);
  const [text, setText] = useState(""), [open, setOpen] = useState(false), [cur, setCur] = useState(0);
  const box = useRef<HTMLInputElement>(null);
  useSlashFocus(box);
  const hits = useMemo(() => rankCompanies(idx.data?.rows, text, 8), [idx.data, text]);
  const go = (symbol: string) => { setText(""); setOpen(false); nav(`/prism/${encodeURIComponent(symbol)}${statement === "standalone" ? "?statement=standalone" : ""}`); };
  const submit = () => { const pick = hits[cur] ?? hits[0]; const typed = cleanSymbol(text); if (pick) go(pick.symbol); else if (typed) go(typed); };
  return (
    <div className={"pzr-pick" + (big ? " big" : "")}>
      <div className="pm-search pzr-search">
        <Icon name="search" />
        <input ref={box} value={text} role="combobox" aria-expanded={open && hits.length > 0} aria-controls="pz-sug" aria-autocomplete="list" aria-label="Choose a company"
          placeholder="Company name or symbol, for example TCS" autoComplete="off" onChange={(e) => { setText(e.target.value); setOpen(true); setCur(0); }}
          onBlur={() => setTimeout(() => setOpen(false), 150)} onFocus={() => setOpen(true)}
          onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setCur((c) => Math.min(hits.length - 1, c + 1)); } else if (e.key === "ArrowUp") { e.preventDefault(); setCur((c) => Math.max(0, c - 1)); } else if (e.key === "Enter") { e.preventDefault(); submit(); } else if (e.key === "Escape") setOpen(false); }} />
        {open && hits.length > 0 && <div className="pm-sug" id="pz-sug" role="listbox">{hits.map((h, i) => <button key={h.symbol} type="button" role="option" aria-selected={i === cur} className={i === cur ? "on" : ""} onMouseDown={(e) => e.preventDefault()} onClick={() => go(h.symbol)}><b>{h.symbol}</b><small>{h.name}</small></button>)}</div>}
      </div>
      <label className="pzr-lbl">Statement basis<StatementSwitch value={statement} set={setStatement} /></label>
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

/** Browse by sector: sector chips, then the companies of one sector. */
function Browse({ statement }: { statement: Statement }) {
  const [on, setOn] = useState(false), [sector, setSector] = useState<string | null>(null);
  const u = useUniverse(on);
  const sectors = useMemo(() => { const m = new Map<string, number>(); (u.data?.rows || []).forEach((r) => r.sector && m.set(r.sector, (m.get(r.sector) || 0) + 1)); return [...m].sort((a, b) => a[0].localeCompare(b[0])); }, [u.data]);
  const list = useMemo(() => (u.data?.rows || []).filter((r) => r.sector === sector).sort((a, b) => (a.name || a.symbol).localeCompare(b.name || b.symbol)), [u.data, sector]);
  const q = statement === "standalone" ? "?statement=standalone" : "";
  return (
    <section className="pzr-browse" aria-label="Browse companies">
      <div className="pzr-browse-h"><h3>Browse companies</h3><button type="button" className="pzr-link" aria-expanded={on} onClick={() => setOn(!on)}>{on ? "Hide sectors" : "Show sectors"}</button></div>
      {!on && <p className="pzr-small">Pick a sector, then a company.</p>}
      {on && (u.isLoading ? <div className="skeleton" style={{ height: 80 }} aria-busy="true" /> : u.isError ? <p className="pzr-empty">The sector list is not available right now. Search by name or symbol instead.</p> : <>
        <div className="pzr-chipsrow" role="group" aria-label="Sectors">{sectors.map(([s, n]) => <button type="button" key={s} className={"pzr-chip" + (s === sector ? " on" : "")} aria-pressed={s === sector} onClick={() => setSector(s === sector ? null : s)}>{s} <small>{n}</small></button>)}</div>
        {sector && <ul className="pzr-colist" aria-label={`Companies in ${sector}`}>{list.slice(0, 60).map((r) => <li key={r.symbol}><Link to={`/prism/${r.symbol}${q}`}><b>{r.symbol}</b><small>{r.name}</small></Link></li>)}</ul>}
        {sector && list.length > 60 && <p className="pzr-small">Showing 60 of {list.length}. Use the search box to find another.</p>}
      </>)}
    </section>
  );
}

const WHAT = ["A score out of 100 and a label from Strong to Poor, or Not rated when the evidence is thin", "Four parts: Fundamentals, Valuation, Quality and Risk, each with what supports it and what holds it back", "Every factor with its value, points and status, and which inputs are missing", "A PDF of exactly the calculation you see"];
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
          <p>Choose a company. If a rating was calculated recently it opens at once; otherwise Prism calculates it from the latest filings and prices, which can take up to two minutes. Each member can calculate 20 a day.</p>
          <p className="pzr-note">{PRISM_NOTE}</p>
        </div>
      </section>
    </div>
  );
}
