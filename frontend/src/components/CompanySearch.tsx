import { useId, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useSearchIndex } from "../lib/api";
import { searchStocks } from "../lib/globalSearch";
import { Icon } from "../lib/icons";

/** The public entry into research. No preselected company; the same index as global search. */
export function CompanySearch() {
  const id = useId(), nav = useNavigate();
  const { data, isError, isLoading, refetch } = useSearchIndex(true);
  const [query, setQuery] = useState(""), [open, setOpen] = useState(false), [active, setActive] = useState(0);
  const hits = useMemo(() => query.trim() ? searchStocks(data?.rows, query.trim(), 6) : [], [data, query]);
  const choose = (symbol: string) => { setOpen(false); nav(`/stocks/${encodeURIComponent(symbol)}`); };
  const show = open && !!query.trim();
  return <div className="company-search" onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false); }}>
    <form role="search" onSubmit={(e) => { e.preventDefault(); if (hits[active]) choose(hits[active].row[0]); else setOpen(true); }}>
      <label htmlFor={id}>Company name or symbol</label>
      <div className="company-search-field"><Icon name="search" />
        <input id={id} value={query} role="combobox" autoComplete="off" placeholder="Search Indian companies" aria-expanded={show} aria-controls={`${id}-results`} aria-autocomplete="list" aria-activedescendant={show && hits[active] ? `${id}-${active}` : undefined}
          onFocus={() => setOpen(true)} onChange={(e) => { setQuery(e.target.value); setActive(0); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
            if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); setOpen(true); setActive((n) => Math.max(0, Math.min(hits.length - 1, n + (e.key === "ArrowDown" ? 1 : -1)))); }
          }} />
        <button type="submit" className="btn primary">Search <Icon name="arrow" /></button>
      </div>
    </form>
    {show && <div className="company-search-results" id={`${id}-results`} role="listbox" aria-label="Matching companies">
      {hits.map(({ row }, i) => <button type="button" role="option" aria-selected={active === i} id={`${id}-${i}`} key={row[0]} onMouseDown={(e) => e.preventDefault()} onClick={() => choose(row[0])}><span>{row[1]}</span><small>{row[0]}</small></button>)}
      {!hits.length && <p role="status">{isLoading ? "Loading companies…" : isError ? "Company search is unavailable right now." : "No companies found. Try a company name, NSE symbol or BSE code."}</p>}
      {isError && <button type="button" onClick={() => refetch()}>Retry search</button>}
    </div>}
  </div>;
}
