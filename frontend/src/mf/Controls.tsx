// The list's controls: search, filters, the column picker and the page buttons.
import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "../lib/icons";
import { COLUMNS, DEFAULT_COLS, SIZES, activeFilterCount, cleanNum, pageWindow, type ColId, type FundFilters, type ListQuery } from "../lib/mf";
import { Pick, type PickItem } from "./Pick";

const RANGES: { k: "1y" | "3y" | "5y"; label: string }[] = [{ k: "1y", label: "1 year return" }, { k: "3y", label: "3 year return, per year" }, { k: "5y", label: "5 year return, per year" }];

function Seg({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <div className="mf-seg-w"><span className="label" id={`seg-${label}`}>{label}</span>
      <div className="seg" role="group" aria-labelledby={`seg-${label}`}>{options.map(([v, t]) => <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}>{t}</button>)}</div></div>
  );
}

function RangeBox({ label, lo, hi, onLo, onHi }: { label: string; lo: string; hi: string; onLo: (v: string) => void; onHi: (v: string) => void }) {
  // typed text is kept locally and applied when the box loses focus or Enter is pressed, so every keystroke does not reload the list
  const [a, setA] = useState(lo), [b, setB] = useState(hi);
  useEffect(() => setA(lo), [lo]);
  useEffect(() => setB(hi), [hi]);
  const go = (v: string, cur: string, f: (v: string) => void) => { const c = cleanNum(v); if (c !== cur) f(c); };
  return (
    <fieldset className="mf-range"><legend>{label}</legend>
      <label><span className="sr-only">{label}, at least</span><input inputMode="decimal" value={a} placeholder="from" onChange={(e) => setA(e.target.value)} onBlur={() => go(a, lo, onLo)} onKeyDown={(e) => e.key === "Enter" && go(a, lo, onLo)} /></label>
      <span aria-hidden="true">to</span>
      <label><span className="sr-only">{label}, at most</span><input inputMode="decimal" value={b} placeholder="to" onChange={(e) => setB(e.target.value)} onBlur={() => go(b, hi, onHi)} onKeyDown={(e) => e.key === "Enter" && go(b, hi, onHi)} /></label>
      <span aria-hidden="true">%</span>
    </fieldset>
  );
}

export function Controls({ q, text, onText, set, filters, loading }: { q: ListQuery; text: string; onText: (t: string) => void; set: (p: Partial<ListQuery>) => void; filters?: FundFilters; loading: boolean }) {
  const cats: PickItem[] = useMemo(() => (filters?.categories || []).filter((c) => q.stopped || c.active > 0).map((c) => ({ value: c.name, label: c.name, count: q.stopped ? c.total : c.active })), [filters, q.stopped]);
  const amcs: PickItem[] = useMemo(() => (filters?.amcs || []).filter((a) => q.stopped || a.active > 0).map((a) => ({ value: a.name, label: a.name, count: q.stopped ? a.total : a.active })), [filters, q.stopped]);
  const n = activeFilterCount(q);
  const [more, setMore] = useState(() => RANGES.some((r) => q[`min${r.k}` as "min1y"] || q[`max${r.k}` as "max1y"]));
  return (
    <section className="card mf-ctl" aria-label="Search and filters">
      <label className="mf-search"><Icon name="search" /><span className="sr-only">Search schemes by name or fund house</span>
        <input type="search" value={text} onChange={(e) => onText(e.target.value)} placeholder="Search by scheme or fund house, e.g. hdfc mid cap" autoComplete="off" spellCheck={false} />
        {loading && <span className="mf-busy" role="status">Loading…</span>}
      </label>
      <div className="mf-filters">
        <Pick label="Category" value={q.category} items={cats} any="All categories" onChange={(v) => set({ category: v })} />
        <Pick label="Fund house" value={q.amc} items={amcs} any="All fund houses" onChange={(v) => set({ amc: v })} />
        <Seg label="Plan" value={q.plan} onChange={(v) => set({ plan: v })} options={[["", "All"], ["Direct", "Direct"], ["Regular", "Regular"]]} />
        <Seg label="Option" value={q.option} onChange={(v) => set({ option: v })} options={[["", "All"], ["Growth", "Growth"], ["IDCW", "IDCW"], ["Other", "Not stated"]]} />
      </div>
      <div className="mf-more">
        <button type="button" className="mf-linkbtn" aria-expanded={more} onClick={() => setMore((m) => !m)}>{more ? "Hide return ranges" : "Filter by return range"}</button>
        <label className="mf-check"><input type="checkbox" checked={q.stopped} onChange={(e) => set({ stopped: e.target.checked })} /> Include schemes that stopped publishing NAVs</label>
        {n > 0 && <button type="button" className="mf-linkbtn" onClick={() => set({ category: "", amc: "", plan: "", option: "", stopped: false, min1y: "", max1y: "", min3y: "", max3y: "", min5y: "", max5y: "" })}>Clear {n} filter{n > 1 ? "s" : ""}</button>}
      </div>
      {more && (
        <div className="mf-ranges">
          {RANGES.map((r) => <RangeBox key={r.k} label={r.label} lo={q[`min${r.k}` as "min1y"]} hi={q[`max${r.k}` as "max1y"]} onLo={(v) => set({ [`min${r.k}`]: v } as Partial<ListQuery>)} onHi={(v) => set({ [`max${r.k}`]: v } as Partial<ListQuery>)} />)}
          <p className="faint">Schemes without a figure for a period (younger funds, IDCW options) are left out while a range is set for it.</p>
        </div>)}
    </section>
  );
}

export function ColumnPicker({ cols, onChange }: { cols: ColId[]; onChange: (c: ColId[]) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const out = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", out); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", out); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="mf-cols" ref={ref}>
      <button type="button" className="btn" aria-haspopup="true" aria-expanded={open} onClick={() => setOpen((o) => !o)}><Icon name="table" />Columns</button>
      {open && (
        <div className="mf-cols-pop" role="group" aria-label="Choose columns">
          {COLUMNS.map((c) => (
            <label key={c.id}><input type="checkbox" checked={cols.includes(c.id)} onChange={() => onChange(cols.includes(c.id) ? cols.filter((x) => x !== c.id) : COLUMNS.map((d) => d.id).filter((id) => id === c.id || cols.includes(id)))} />
              <span>{c.label}<small>{c.hint}</small></span></label>))}
          <button type="button" className="mf-linkbtn" onClick={() => onChange(DEFAULT_COLS)}>Back to the default columns</button>
        </div>)}
    </div>
  );
}

export function Pager({ q, pages, total, onPage, onSize }: { q: ListQuery; pages: number; total: number; onPage: (p: number) => void; onSize: (n: number) => void }) {
  const from = total ? (q.page - 1) * q.size + 1 : 0, to = Math.min(total, q.page * q.size);
  return (
    <nav className="mf-pager" aria-label="Pages">
      <span className="muted">{from.toLocaleString("en-IN")}–{to.toLocaleString("en-IN")} of {total.toLocaleString("en-IN")}</span>
      <div className="mf-pages">
        <button className="btn" disabled={q.page <= 1} onClick={() => onPage(q.page - 1)} aria-label="Previous page">‹</button>
        {pageWindow(q.page, pages).map((p, i) => p === "…" ? <span key={"g" + i} aria-hidden="true">…</span> : <button key={p} className={"btn" + (p === q.page ? " on" : "")} aria-current={p === q.page ? "page" : undefined} onClick={() => onPage(p)}>{p}</button>)}
        <button className="btn" disabled={q.page >= pages} onClick={() => onPage(q.page + 1)} aria-label="Next page">›</button>
      </div>
      <label className="mf-size"><span className="label">Per page</span><select value={q.size} onChange={(e) => onSize(Number(e.target.value))}>{SIZES.map((s) => <option key={s}>{s}</option>)}</select></label>
    </nav>
  );
}
