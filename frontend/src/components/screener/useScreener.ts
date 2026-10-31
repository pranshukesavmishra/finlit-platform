// The state and actions both score screeners share: URL state, draft vs applied filters, selection, watchlist, CSV, sorting.
// Each page decides which columns, filters and views it shows; this hook knows nothing about the models.
import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useUniverse } from "../../lib/screener";
import { useUI } from "../../lib/ui";
import { useWatchlist, watch } from "../../lib/watchlist";
import {
  applyFilters, chipsFor, cloneFilters, concentration, emptyFilters, facetCounts, filtersKey, nextSort, pageOf, parseState, removeChip, serializeState, sortRows, summarize, toCsv, validate, withScores,
  type Band, type BandKey, type Filters, type Item, type RangeKey, type Scope, type SortKey, type State, type TechBand, type TechKey,
} from "../../lib/scoreScreen";
import { coverageFrom } from "../../lib/scorePrism";
import type { PrismLabel } from "../../lib/scorePrism";

export type Mode = "basic" | "advanced";
const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

export function useScreener(mode: Mode) {
  const { data, isLoading, isError } = useUniverse();
  const { has, upgrade, toast } = useUI();
  const nav = useNavigate();
  useWatchlist();
  const [params, setParams] = useSearchParams();
  const live = useRef(params); live.current = params;
  const scope: Scope = mode;
  const state = useMemo(() => parseState(params, scope), [params.toString(), scope]);   // eslint-disable-line react-hooks/exhaustive-deps
  const { filters: applied, sort, size } = state;
  const [draft, setDraft] = useState<Filters>(() => cloneFilters(applied));
  const [secQ, setSecQ] = useState(""), [q, setQ] = useState(() => params.get("q") ?? "");   // q: the toolbar search; it narrows the table and is kept in the address as ?q=
  const [picked, setPicked] = useState<string[]>([]);
  const [how, setHow] = useState(false), [drawer, setDrawer] = useState(false);
  const silver = has("silver"), locked = !silver, gold = has("gold"), maxCompare = gold ? 4 : 2;
  const appliedKey = filtersKey(applied);
  const mine = useRef<string | null>(null), wait = useRef(0);   // mine: the filters this page itself just applied; wait: how long to hold before applying the next draft change (0 for ticks, 400 ms for typed numbers)
  useEffect(() => {  if (mine.current === appliedKey) { mine.current = null; return; } setDraft(cloneFilters(applied)); }, [appliedKey]);   // eslint-disable-line react-hooks/exhaustive-deps -- back/forward or a pasted link refreshes the sidebar (our own applies already match the draft)

  const items = useMemo(() => withScores(data?.rows || []), [data]);
  const unscored = useMemo(() => items.filter((r) => r.scored === false).length, [items]);
  const asOf = data?.asOf ?? null;
  const cover = useMemo(() => (data?.prism ?? (gold ? { ...coverageFrom(data?.rows || []), as_of: null } : null)), [data, gold]);
  const techAsOf = (cover as { tech_as_of?: string | null } | null | undefined)?.tech_as_of ?? null;   // the newest bar date the technical columns hold: shown so an old technical view is never read as today's
  const prismAsOf = useMemo(() => cover?.as_of ?? (items.map((r) => r.prism_at).filter((d): d is string => !!d).sort().at(-1) ?? null), [cover, items]);
  const found = useMemo(() => { const k = q.trim().toLowerCase(); return k ? items.filter((r) => `${r.symbol} ${r.name ?? ""} ${r.sector ?? ""}`.toLowerCase().includes(k)) : items; }, [items, q]);   // the toolbar search narrows everything, the counts beside the options included
  const facets = useMemo(() => facetCounts(found, draft), [found, draft]);   // each option's count respects every OTHER active filter (faceted search); the option's own group is left out so you can see what ticking another one would add
  const rows = useMemo(() => sortRows(applyFilters(found, applied), sort), [found, appliedKey, sort]);   // eslint-disable-line react-hooks/exhaustive-deps
  const sum = useMemo(() => summarize(rows), [rows]);
  const mix = useMemo(() => concentration(rows), [rows]);
  const pg = pageOf(rows, state.page, size);
  const chips = chipsFor(applied);
  const problems = validate(draft), bad = Object.keys(problems).length > 0;
  const dirty = filtersKey(draft) !== appliedKey;
  const rowSet = useMemo(() => new Set(rows.map((r) => r.symbol)), [rows]);
  const sel = picked.filter((s) => rowSet.has(s));
  const selRows = rows.filter((r) => sel.includes(r.symbol));

  const withQ = (p: URLSearchParams) => { if (q.trim()) p.set("q", q.trim()); return p; };
  const go = (next: Partial<State>) => { setParams(withQ(serializeState({ ...state, ...next })), { replace: true }); };
  useEffect(() => {   // keep ?q= in step with the search box (a new search starts again from page 1)
    const t = setTimeout(() => setParams(() => {
      const prev = live.current, cur = prev.get("q") ?? "", want = q.trim();   // the latest address, not the one this render closed over (that would undo a filter applied a moment ago)
      if (cur === want) return prev;
      const n = new URLSearchParams(prev); if (want) n.set("q", want); else n.delete("q"); n.delete("page"); return n;
    }, { replace: true }), 300);
    return () => clearTimeout(t);
  }, [q]);   // eslint-disable-line react-hooks/exhaustive-deps
  const apply = (f: Filters = draft, close = false) => { if (Object.keys(validate(f)).length) return; if (filtersKey(f) !== appliedKey) mine.current = filtersKey(f); setDraft(cloneFilters(f)); go({ filters: f, page: 0 }); if (close) setDrawer(false); };
  const clear = () => { wait.current = 0; apply(emptyFilters()); };
  const drop = (id: string) => apply(removeChip(applied, id));
  // Filters apply live: a tick, chip or quick view applies at once; typed numbers apply 400 ms after the last key (or on Enter / leaving the box).
  const edit = (fn: (d: Filters) => Filters, typed = false) => { wait.current = typed ? 400 : 0; setDraft(fn); };
  const setDraftLive: Dispatch<SetStateAction<Filters>> = (fn) => edit((d) => (typeof fn === "function" ? fn(d) : fn));
  useEffect(() => {
    if (filtersKey(draft) === appliedKey || Object.keys(validate(draft)).length) return;   // nothing pending, or an invalid range that is shown in red and waits
    const t = setTimeout(() => apply(draft), wait.current);
    return () => clearTimeout(t);
  }, [draft]);   // eslint-disable-line react-hooks/exhaustive-deps
  const setBand = (k: BandKey, b: Band) => edit((d) => ({ ...d, bands: { ...d.bands, [k]: toggle(d.bands[k], b) } }));
  const setRange = (k: RangeKey, end: "min" | "max", v: string) => edit((d) => ({ ...d, ranges: { ...d.ranges, [k]: { ...d.ranges[k], [end]: v.trim() === "" ? null : Number(v) } } }), true);
  const setLabel = (l: PrismLabel) => edit((d) => ({ ...d, labels: toggle(d.labels, l) }));
  const setTech = (k: TechKey, b: TechBand) => edit((d) => ({ ...d, tech: { ...d.tech, [k]: toggle(d.tech[k], b) } }));

  const togglePick = (s: string) => setPicked((p) => (p.includes(s) ? p.filter((x) => x !== s) : [...p, s]));
  const pageSyms = pg.view.map((r) => r.symbol), allOnPage = pageSyms.length > 0 && pageSyms.every((s) => sel.includes(s)), someOnPage = pageSyms.some((s) => sel.includes(s));
  const headBox = useRef<HTMLInputElement>(null);
  useEffect(() => { if (headBox.current) headBox.current.indeterminate = someOnPage && !allOnPage; });
  const toggleAll = () => setPicked((p) => (allOnPage ? p.filter((s) => !pageSyms.includes(s)) : [...new Set([...p, ...pageSyms])]));

  const addWatch = (s: string) => {
    if (!silver) { upgrade("silver", "Watchlists come with the Silver plan."); return; }
    if (watch.has(s)) { watch.remove(s); toast(`${s} removed from your watchlist.`); } else { watch.add(s); toast(`${s} added to your watchlist.`); }
  };
  const addSelected = () => {
    if (!silver) { upgrade("silver", "Watchlists come with the Silver plan."); return; }
    const fresh = sel.filter((s) => !watch.has(s));
    fresh.forEach((s) => watch.add(s));
    toast(fresh.length ? `${fresh.length} ${fresh.length === 1 ? "company" : "companies"} added to your watchlist.` : "These companies are already on your watchlist.");
  };
  const exportCsv = (which: "selected" | "filtered") => {
    const list = which === "selected" ? selRows : rows, day = new Date().toISOString().slice(0, 10);
    const csv = toCsv(list, { filters: applied, sort, scope: which, total: rows.length, asOf, exportedOn: day, mode, prismAsOf });
    const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a"); a.href = url; a.download = `finlit-${mode}-score-screen-${day}.csv`; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const sortBy = (key: SortKey) => go({ sort: nextSort(sort, key), page: 0 });

  return {
    mode, data, isLoading, isError, has, upgrade, nav, state, applied, sort, size, draft, setDraft: setDraftLive, secQ, setSecQ, q, setQ, picked, setPicked, how, setHow, drawer, setDrawer,
    silver, locked, gold, maxCompare, items: items as Item[], unscored, asOf, cover, prismAsOf, techAsOf, facets, rows, sum, mix, pg, chips, problems, bad, dirty, flush: () => apply(draft), sel, filterCount: chips.length,
    go, apply, clear, drop, toggle, setBand, setRange, setLabel, setTech, togglePick, allOnPage, headBox, toggleAll, addWatch, addSelected, exportCsv, sortBy,
  };
}
export type Screener = ReturnType<typeof useScreener>;
