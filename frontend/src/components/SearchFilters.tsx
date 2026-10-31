// The sector and market-cap filters of every company search (the Ctrl K palette and the company pickers), one module:
//  - variant "bar": two compact dropdowns, "Sector" and "Market cap", each showing the active choice and a Clear option (the palette, wide pickers);
//  - variant "panel": one "Filters" button that opens a small panel with the same two choices (narrow pickers, inline autocompletes).
// Keyboard: Enter, Space or the arrow keys open a dropdown; arrows, Home and End move; Enter picks; Esc closes only the open list or panel.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchIndex, type SearchIndex, type SearchRow } from "../lib/api";
import { searchStocks } from "../lib/globalSearch";
import { NO_FILTER, facetsOf, filterNoun, filterOn, filterParts, filteredRows, hasFilterData, hiddenMatches, indexFacets, passes, passesValues, relaxed, type Facets, type HiddenHit, type Sized, type StockFilter } from "../lib/searchFilters";
import "../styles/searchfilters.css";

/** State for a picker that searches the search index: the filter, the facets of the real data, and the rows that pass (the index rows untouched while no filter is on). */
export function useIndexFilter(enabled = true) {
  const idx = useSearchIndex(enabled);
  const [filter, setFilter] = useState<StockFilter>(NO_FILTER);
  const data: SearchIndex | undefined = idx.data;
  const facets = useMemo(() => indexFacets(data), [data]);
  const rows = useMemo<SearchRow[]>(() => filteredRows(data, filter), [data, filter]);
  /** Companies for the typed text, best first, by name, symbol, BSE or NSE code or ISIN, only those that pass the filter. No text: the largest that pass while a filter is on, nothing otherwise. */
  const search = useCallback((q: string, limit = 8, exclude: readonly string[] = []): SearchRow[] => {
    if (!data) return [];
    const skip = new Set(exclude.map((x) => x.toUpperCase()));
    if (!q.trim()) return filterOn(filter) ? filteredRows(data, filter).filter((r) => !skip.has(r[0].toUpperCase())).slice(0, limit) : [];
    return searchStocks(data.rows, q, 1e9, new Set(), (i) => passes(data, i, filter), data.isin).map((h) => h.row).filter((r) => !skip.has(r[0].toUpperCase())).slice(0, limit);
  }, [data, filter]);
  /** Companies that match the typed text but are left out by the filter, each with the reason. */
  const hidden = useCallback((q: string, limit = 3) => hiddenMatches(data, q, filter, limit), [data, filter]);
  return { idx, data, filter, setFilter, facets, rows, search, hidden, on: filterOn(filter), available: hasFilterData(data), count: rows.length };
}

export type FilterOption = { id: string; label: string; hint?: string; n: number };

export function FilterMenu({ name, value, options, open, onOpen, onPick, note, keyHint, clearLabel }: {
  name: string; value: string | null; options: FilterOption[]; open: boolean; onOpen: (v: boolean) => void; onPick: (id: string | null) => void;
  note?: string; keyHint?: string; clearLabel: string;
}) {
  const [at, setAt] = useState(0);                 // highlighted entry; 0 is "Clear" (shown only while a choice is active)
  const btn = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const id = "sf-fm-" + name.toLowerCase().replace(/\W+/g, "");
  const entries: { id: string | null; label: string; hint?: string; n?: number }[] = [...(value ? [{ id: null, label: clearLabel }] : []), ...options];
  const chosen = options.find((o) => o.id === value);

  useEffect(() => {
    if (!open) return;
    const i = entries.findIndex((e) => e.id === value);
    setAt(i >= 0 ? i : 0);
    list.current?.focus();
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) onOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  useEffect(() => { if (open) list.current?.querySelector<HTMLElement>(`[data-k="${at}"]`)?.scrollIntoView({ block: "nearest" }); }, [at, open]);

  const choose = (i: number) => { const e = entries[i]; if (!e) return; onPick(e.id); onOpen(false); };
  const key = (e: React.KeyboardEvent) => {
    const last = entries.length - 1;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onOpen(false); btn.current?.focus(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setAt((a) => Math.min(a + 1, last)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Home") { e.preventDefault(); setAt(0); }
    else if (e.key === "End") { e.preventDefault(); setAt(last); }
    else if (e.key === "PageDown") { e.preventDefault(); setAt((a) => Math.min(a + 6, last)); }
    else if (e.key === "PageUp") { e.preventDefault(); setAt((a) => Math.max(a - 6, 0)); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(at); }
    else if (e.key === "Tab") onOpen(false);
  };

  return (
    <div className={`sf-fm${value ? " on" : ""}`} ref={box}>
      <button ref={btn} type="button" className="sf-fb" aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? id : undefined} title={keyHint ? `${name} (${keyHint})` : name}
        onClick={() => onOpen(!open)}
        onKeyDown={(e) => { if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); onOpen(true); } }}>
        <span className="sf-k">{name}</span>
        <b>{chosen ? chosen.label : value ?? "All"}</b>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
      </button>
      {open && (
        <div className="sf-fp">
          <ul id={id} ref={list} role="listbox" tabIndex={-1} aria-label={name} aria-activedescendant={`${id}-${at}`} onKeyDown={key}>
            {entries.map((e, k) => (
              <li key={e.id ?? "clear"} id={`${id}-${k}`} data-k={k} role="option" aria-selected={e.id === value && e.id !== null} className={`${k === at ? "cur" : ""}${e.id === null ? " clr" : ""}`}
                onMouseMove={() => setAt(k)} onClick={() => choose(k)}>
                <span className="sf-ot">{e.label}{e.hint && <small>{e.hint}</small>}</span>
                {e.n != null && <em>{e.n.toLocaleString("en-IN")}</em>}
              </li>
            ))}
          </ul>
          {note && <p className="sf-fn">{note}</p>}
        </div>
      )}
    </div>
  );
}

/** The same for a picker that holds screener rows (sector and market_cap on each row) instead of the search index. */
export function useRowFilter<T>(items: readonly T[], size: (t: T) => Sized) {
  const [filter, setFilter] = useState<StockFilter>(NO_FILTER);
  const facets = useMemo(() => facetsOf(items.map(size)), [items]);   // eslint-disable-line react-hooks/exhaustive-deps
  const rows = useMemo(() => (filterOn(filter) ? items.filter((t) => { const z = size(t); return passesValues(z.sector, z.cap, filter); }) : items), [items, filter]);   // eslint-disable-line react-hooks/exhaustive-deps
  return { filter, setFilter, facets, rows, on: filterOn(filter), count: rows.length };
}

const capOptions = (f: Facets) => f.caps.map((o) => ({ id: o.id as string, label: o.label, hint: o.range, n: o.n }));
const sectorOptions = (f: Facets) => f.sectors.map((o) => ({ id: o.name, label: o.name, n: o.n }));
const nIN = (n: number) => n.toLocaleString("en-IN");
const unknownNote = (n: number, what: string, pick: string) => (n ? `${nIN(n)} companies with no ${what} on file are left out while ${pick} is chosen.` : undefined);

type Props = {
  facets: Facets; value: StockFilter; onChange: (f: StockFilter) => void;
  variant?: "bar" | "panel";
  /** how many companies pass the filter right now (the panel shows it); omit to hide the line */
  count?: number;
  menu?: "sector" | "cap" | null; onMenu?: (m: "sector" | "cap" | null) => void;   // bar only: lets the host open a list from a shortcut
  onDone?: () => void;                                                              // after a choice: the host puts the focus back in its search box
  className?: string;
};

export function SearchFilters({ facets, value, onChange, variant = "bar", count, menu, onMenu, onDone, className }: Props) {
  const [own, setOwn] = useState<"sector" | "cap" | null>(null);
  const cur = menu !== undefined ? menu : own, setMenu = onMenu ?? setOwn;
  const [panel, setPanel] = useState(false);
  const wrap = useRef<HTMLDivElement>(null), btn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!panel) return;
    const away = (e: MouseEvent) => { if (!wrap.current?.contains(e.target as Node)) setPanel(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [panel]);
  if (!facets.sectors.length && !facets.caps.some((c) => c.n > 0)) return null;     // no data to filter by (an older server)
  const on = filterOn(value), active = (value.sector ? 1 : 0) + (value.cap ? 1 : 0);
  const clear = () => { onChange(NO_FILTER); onDone?.(); };

  if (variant === "panel") {
    return (
      <div className={`sf-panelwrap ${className || ""}`} ref={wrap} onKeyDown={(e) => { if (e.key === "Escape" && panel) { e.preventDefault(); e.stopPropagation(); setPanel(false); btn.current?.focus(); } }}>
        <button ref={btn} type="button" className={`sf-btn${on ? " on" : ""}`} aria-haspopup="dialog" aria-expanded={panel} aria-label={on ? `Filters: ${active} active. ${filterParts(value).join(", ")}` : "Filters: none active"} title={on ? `${filterParts(value).join(" · ")}. Click to change.` : "Filter companies by sector or market cap"} onClick={() => setPanel((p) => !p)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4" /></svg><span>Filters</span>{on && <em>{active}</em>}
        </button>
        {panel && (
          <div className="sf-panel" role="dialog" aria-label="Filter companies">
            <label>Sector
              <select value={value.sector ?? ""} onChange={(e) => onChange({ ...value, sector: e.target.value || null })}>
                <option value="">Any sector</option>
                {facets.sectors.map((o) => <option key={o.name} value={o.name}>{o.name} ({nIN(o.n)})</option>)}
              </select></label>
            <label>Market cap
              <select value={value.cap ?? ""} onChange={(e) => onChange({ ...value, cap: (e.target.value || null) as StockFilter["cap"] })}>
                <option value="">Any size</option>
                {facets.caps.map((o) => <option key={o.id} value={o.id}>{o.label} · {o.range} ({nIN(o.n)})</option>)}
              </select></label>
            {on && <p className="sf-count" data-testid="sf-active-list">On now: {filterParts(value).join(" · ")}</p>}
            {on && count != null && <p className="sf-count" role="status">{nIN(count)} {filterNoun(value, count)}</p>}
            <p className="sf-fn">{[unknownNote(value.sector ? facets.unknown.sector : 0, "sector", "a sector"), unknownNote(value.cap ? facets.unknown.cap : 0, "market value", "a band")].filter(Boolean).join(" ") || "Companies with no sector or market value on file are left out only while that filter is chosen."}</p>
            <div className="sf-acts">{on && <button type="button" onClick={clear}>Clear filters</button>}<button type="button" className="sf-done" onClick={() => { setPanel(false); btn.current?.focus(); }}>Done</button></div>
          </div>
        )}
      </div>
    );
  }
  return (
    <div className={`sf-bar ${className || ""}`} role="group" aria-label="Narrow the companies">
      <FilterMenu name="Sector" clearLabel="Clear sector" value={value.sector} open={cur === "sector"} onOpen={(v) => setMenu(v ? "sector" : null)} keyHint="Alt+S"
        options={sectorOptions(facets)} note={unknownNote(facets.unknown.sector, "sector", "a sector")}
        onPick={(v) => { onChange({ ...value, sector: v }); onDone?.(); }} />
      <FilterMenu name="Market cap" clearLabel="Clear market cap" value={value.cap} open={cur === "cap"} onOpen={(v) => setMenu(v ? "cap" : null)} keyHint="Alt+M"
        options={capOptions(facets)} note={unknownNote(facets.unknown.cap, "market value", "a band")}
        onPick={(v) => { onChange({ ...value, cap: v as StockFilter["cap"] }); onDone?.(); }} />
      {on && <button type="button" className="sf-x" onClick={clear}>Clear filters</button>}
    </div>
  );
}

/** Always visible while a filter is on: says exactly what is active, with a one-click way to clear it (the funnel button only shows a number). */
export function ActiveFilters({ filter, onChange, className }: { filter: StockFilter; onChange: (f: StockFilter) => void; className?: string }) {
  if (!filterOn(filter)) return null;
  const parts = filterParts(filter);
  return (
    <p className={`sf-active ${className || ""}`} role="status" data-testid="active-filters">
      <span>{parts.length === 1 ? "1 filter on" : `${parts.length} filters on`}: {parts.join(" · ")}. Companies outside it are hidden.</span>
      <button type="button" onClick={() => onChange(NO_FILTER)}>Clear filters</button>
    </p>
  );
}

/** Companies that match what was typed but are left out by the filter: greyed, with the reason and a one-click way to show them. */
export function HiddenRows({ hidden, filter, onChange }: { hidden: readonly HiddenHit[]; filter: StockFilter; onChange: (f: StockFilter) => void }) {
  if (!hidden.length) return null;
  return (
    <ul className="sf-hidden" aria-label="Matches hidden by your filter">
      {hidden.map((h) => (
        <li key={h.symbol} className="sf-hid">
          <span className="sf-hid-t"><b>{h.symbol}</b><small>{h.name}</small><em>{h.why}</em></span>
          <button type="button" onClick={() => onChange(relaxed(filter, h.keys))} aria-label={`Show ${h.name}: remove ${h.keys.map((k) => (k === "sector" ? "sector" : "market cap")).join(" and ")} filter`}>Show it</button>
        </li>
      ))}
    </ul>
  );
}

/** Shown by a picker in place of its "no match" line while a filter is on: says plainly what is empty, shows the matches the filter hides, and offers the way out. */
export function FilterNote({ filter, q, onChange, hidden }: { filter: StockFilter; q?: string; onChange: (f: StockFilter) => void; hidden?: readonly HiddenHit[] }) {
  const noun = filterNoun(filter);
  const both = !!filter.sector && !!filter.cap;
  return (
    <div className="sf-empty" role="status">
      <p>{q ? `No ${noun} match “${q}”.` : `No ${noun} in the list.`}{hidden?.length ? "" : q ? " Try fewer filters, or check the spelling." : ""}</p>
      <HiddenRows hidden={hidden || []} filter={filter} onChange={onChange} />
      <p className="sf-relax">
        {both && <button type="button" onClick={() => onChange({ ...filter, sector: null })}>Any sector</button>}
        {both && <button type="button" onClick={() => onChange({ ...filter, cap: null })}>Any size</button>}
        <button type="button" onClick={() => onChange(NO_FILTER)}>Clear filters</button>
      </p>
    </div>
  );
}
