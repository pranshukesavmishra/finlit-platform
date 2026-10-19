import { useEffect, useMemo, useRef, useState } from "react";
import { cr, nf } from "../lib/format";
import type { Row } from "../lib/screener";

const ITEM = 56, VIEW = 336;
const POPULAR: string[][] = [["TCS", "INFY"], ["INFY", "WIPRO"], ["TCS", "HCLTECH"], ["WIPRO", "TECHM"], ["HDFCBANK", "ICICIBANK"], ["ICICIBANK", "SBIN"], ["HDFCBANK", "KOTAKBANK"], ["SBIN", "PNB"], ["AXISBANK", "KOTAKBANK"], ["RELIANCE", "ONGC"], ["MARUTI", "TATAMOTORS"], ["HINDUNILVR", "ITC"], ["SUNPHARMA", "CIPLA"], ["BAJFINANCE", "BAJAJFINSV"]];
const ini = (r: Row) => (r.name || r.symbol).replace(/[^A-Za-z]/g, "").slice(0, 2).toUpperCase();

/** One field for the whole comparison: picked companies are chips with a cross, and the box beside them searches every listed company. */
export function CompareBar({ rows, ids, max, onChange, onLimit }: { rows: Row[]; ids: string[]; max: number; onChange: (ids: string[]) => void; onLimit: () => void }) {
  const [open, setOpen] = useState(false), [q, setQ] = useState(""), [sector, setSector] = useState(""), [active, setActive] = useState(0), [top, setTop] = useState(0);
  const box = useRef<HTMLDivElement>(null), input = useRef<HTMLInputElement>(null), scroller = useRef<HTMLDivElement>(null);
  const bySym = useMemo(() => new Map(rows.map((r) => [r.symbol, r])), [rows]);
  const picked = ids.map((s) => bySym.get(s)).filter((r): r is Row => !!r);
  const first = picked[0];

  // every company, biggest first, so an empty box is a browsable list rather than a blank
  const all = useMemo(() => [...rows].sort((a, b) => (b.market_cap ?? -1) - (a.market_cap ?? -1) || a.symbol.localeCompare(b.symbol)), [rows]);
  const sectors = useMemo(() => { const m = new Map<string, number>(); rows.forEach((r) => r.sector && m.set(r.sector, (m.get(r.sector) || 0) + 1)); return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0])); }, [rows]);
  const list = useMemo(() => {
    const t = q.trim().toLowerCase();
    const hit = all.filter((r) => (!sector || r.sector === sector) && (!t || r.symbol.toLowerCase().includes(t) || (r.name || "").toLowerCase().includes(t)));
    return t ? hit.sort((a, b) => Number(b.symbol.toLowerCase().startsWith(t)) - Number(a.symbol.toLowerCase().startsWith(t)) || Number((b.name || "").toLowerCase().startsWith(t)) - Number((a.name || "").toLowerCase().startsWith(t))) : hit;
  }, [all, q, sector]);

  useEffect(() => { const h = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); }; document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h); }, []);
  useEffect(() => { setActive(0); scroller.current && (scroller.current.scrollTop = 0); setTop(0); }, [q, sector]);

  const toggle = (sym: string) => {
    if (ids.includes(sym)) { onChange(ids.filter((s) => s !== sym)); return; }
    if (ids.length >= max) { onLimit(); return; }
    onChange([...ids, sym]); setQ(""); input.current?.focus();
  };
  const move = (to: number) => {
    const i = Math.max(0, Math.min(list.length - 1, to)); setActive(i);
    const el = scroller.current; if (!el) return;
    if (i * ITEM < el.scrollTop) el.scrollTop = i * ITEM; else if ((i + 1) * ITEM > el.scrollTop + VIEW) el.scrollTop = (i + 1) * ITEM - VIEW;
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); move(active + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(active - 1); }
    else if (e.key === "PageDown") { e.preventDefault(); move(active + 6); }
    else if (e.key === "PageUp") { e.preventDefault(); move(active - 6); }
    else if (e.key === "Enter" && open && list[active]) { e.preventDefault(); toggle(list[active].symbol); }
    else if (e.key === "Escape") setOpen(false);
    else if (e.key === "Backspace" && !q && ids.length) onChange(ids.slice(0, -1));
  };
  const from = Math.max(0, Math.floor(top / ITEM) - 4), to = Math.min(list.length, from + Math.ceil(VIEW / ITEM) + 9);
  const quick = POPULAR.filter((p) => p.every((s) => bySym.has(s))).slice(0, 10);
  const peers = first ? all.filter((r) => r.sector === first.sector && r.symbol !== first.symbol && !ids.includes(r.symbol)).slice(0, 6) : [];

  return (
    <div className="cb" ref={box}>
      <div className={"cb-field" + (open ? " open" : "")} onClick={() => { setOpen(true); input.current?.focus(); }}>
        {picked.map((r) => (
          <span key={r.symbol} className="cb-chip"><b>{r.symbol}</b>
            <button aria-label={`Remove ${r.name || r.symbol}`} onClick={(e) => { e.stopPropagation(); onChange(ids.filter((s) => s !== r.symbol)); }}>×</button></span>))}
        <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onKeyDown={onKey} role="combobox" aria-expanded={open} aria-controls="cb-list" aria-autocomplete="list"
          aria-activedescendant={open && list[active] ? `cb-o-${list[active].symbol}` : undefined} aria-label="Search a company to compare" placeholder={ids.length ? (ids.length >= max ? `You are comparing ${max}` : "Add another company: name or ticker") : "Search a stock: name or ticker"} />
        {ids.length > 0 && <button className="cb-clear" aria-label="Remove all companies" onClick={(e) => { e.stopPropagation(); onChange([]); }}>Clear</button>}
      </div>
      <p className="cb-count" aria-live="polite">Compare 2 to {max} stocks · {ids.length} chosen{rows.length ? ` · ${nf(rows.length, 0)} companies to choose from` : ""}</p>
      {open && (
        <div className="cb-menu">
          <div className="cb-tools"><label><span className="sr">Sector</span><select value={sector} onChange={(e) => setSector(e.target.value)} aria-label="Only show one sector"><option value="">All sectors ({nf(rows.length, 0)})</option>{sectors.map(([s, n]) => <option key={s} value={s}>{s} ({n})</option>)}</select></label>
            {first?.sector && <button className={"cb-t" + (sector === first.sector ? " on" : "")} onClick={() => setSector(sector === first.sector ? "" : first.sector!)}>Only {first.sector}</button>}
            <span className="cb-n">{nf(list.length, 0)} {list.length === 1 ? "company" : "companies"}</span></div>
          <div className="cb-scroll" id="cb-list" role="listbox" aria-multiselectable="true" ref={scroller} style={{ height: Math.min(VIEW, Math.max(ITEM, list.length * ITEM)) }} onScroll={(e) => setTop((e.target as HTMLElement).scrollTop)}>
            <div style={{ height: list.length * ITEM, position: "relative" }}>
              {list.slice(from, to).map((r, k) => { const i = from + k, on = ids.includes(r.symbol); return (
                <button key={r.symbol} id={`cb-o-${r.symbol}`} role="option" aria-selected={on} className={"cb-o" + (i === active ? " act" : "") + (on ? " on" : "")} style={{ position: "absolute", top: i * ITEM, height: ITEM }} onMouseMove={() => setActive(i)} onClick={() => toggle(r.symbol)}>
                  <span className="av mini" aria-hidden="true">{ini(r)}</span><span className="cb-nm"><b>{r.symbol}</b><small>{r.name}{r.sector ? ` · ${r.sector}` : ""}</small></span>
                  <span className="cb-mc">{r.market_cap != null ? "₹" + cr(r.market_cap) + " Cr" : ""}</span><span className="cb-st" aria-hidden="true">{on ? "✓" : "+"}</span></button>); })}
              {!list.length && <p className="muted" style={{ padding: 16 }}>No company matches “{q}”. Try the ticker, or part of the name.</p>}
            </div>
          </div>
          <p className="cb-hint">Scroll to browse every company, or type to search. Click to add, click again to remove. Arrow keys and Enter work too.</p>
        </div>)}
      {ids.length < 2 && !open && <p className="cb-need">Pick at least two companies to compare.</p>}
      <div className="cb-rows">
        {quick.length > 0 && <div className="cb-pop"><span className="cb-l">Popular</span>{quick.map((p) => <button key={p.join("")} className="cb-p" onClick={() => onChange(p.slice(0, max))}>{p.join(" vs ")}</button>)}</div>}
        {peers.length > 0 && <div className="cb-pop"><span className="cb-l">Peers of {first!.symbol}</span>{peers.map((r) => <button key={r.symbol} className="cb-p" disabled={ids.length >= max && !ids.includes(r.symbol)} onClick={() => toggle(r.symbol)} title={r.name || ""}>+ {r.symbol}</button>)}</div>}
      </div>
    </div>
  );
}
