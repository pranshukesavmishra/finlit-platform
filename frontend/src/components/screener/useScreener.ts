// The state and actions both score screeners share: URL state, draft vs applied filters, selection, watchlist, CSV, sorting.
// Each page decides which columns, filters and views it shows; this hook knows nothing about the models.
import { useEffect, useMemo, useRef, useState } from "react";
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
  const scope: Scope = mode;
  const state = useMemo(() => parseState(params, scope), [params.toString(), scope]);   // eslint-disable-line react-hooks/exhaustive-deps
  const { filters: applied, sort, size } = state;
  const [draft, setDraft] = useState<Filters>(() => cloneFilters(applied));
  const [secQ, setSecQ] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [how, setHow] = useState(false), [drawer, setDrawer] = useState(false);
  const silver = has("silver"), locked = !silver, gold = has("gold"), maxCompare = gold ? 4 : 2;
  const appliedKey = filtersKey(applied);
  useEffect(() => { setDraft(cloneFilters(applied)); }, [appliedKey]);   // eslint-disable-line react-hooks/exhaustive-deps -- back/forward or a pasted link refreshes the sidebar

  const items = useMemo(() => withScores(data?.rows || []), [data]);
  const unscored = useMemo(() => items.filter((r) => r.scored === false).length, [items]);
  const asOf = data?.asOf ?? null;
  const cover = useMemo(() => (data?.prism ?? (gold ? { ...coverageFrom(data?.rows || []), as_of: null } : null)), [data, gold]);
  const techAsOf = (cover as { tech_as_of?: string | null } | null | undefined)?.tech_as_of ?? null;   // the newest bar date the technical columns hold: shown so an old technical view is never read as today's
  const prismAsOf = useMemo(() => cover?.as_of ?? (items.map((r) => r.prism_at).filter((d): d is string => !!d).sort().at(-1) ?? null), [cover, items]);
  const facets = useMemo(() => facetCounts(items, draft), [items, draft]);
  const rows = useMemo(() => sortRows(applyFilters(items, applied), sort), [items, appliedKey, sort]);   // eslint-disable-line react-hooks/exhaustive-deps
  const sum = useMemo(() => summarize(rows), [rows]);
  const mix = useMemo(() => concentration(rows), [rows]);
  const pg = pageOf(rows, state.page, size);
  const chips = chipsFor(applied);
  const problems = validate(draft), bad = Object.keys(problems).length > 0;
  const dirty = filtersKey(draft) !== appliedKey;
  const rowSet = useMemo(() => new Set(rows.map((r) => r.symbol)), [rows]);
  const sel = picked.filter((s) => rowSet.has(s));
  const selRows = rows.filter((r) => sel.includes(r.symbol));

  const go = (next: Partial<State>) => { setParams(serializeState({ ...state, ...next }), { replace: true }); };
  const apply = (f: Filters = draft) => { if (Object.keys(validate(f)).length) return; setDraft(cloneFilters(f)); go({ filters: f, page: 0 }); setDrawer(false); };
  const clear = () => { const e = emptyFilters(); setDraft(e); go({ filters: e, page: 0 }); };
  const drop = (id: string) => { const n = removeChip(applied, id); setDraft(cloneFilters(n)); go({ filters: n, page: 0 }); };
  const setBand = (k: BandKey, b: Band) => setDraft((d) => ({ ...d, bands: { ...d.bands, [k]: toggle(d.bands[k], b) } }));
  const setRange = (k: RangeKey, end: "min" | "max", v: string) => setDraft((d) => ({ ...d, ranges: { ...d.ranges, [k]: { ...d.ranges[k], [end]: v.trim() === "" ? null : Number(v) } } }));
  const setLabel = (l: PrismLabel) => setDraft((d) => ({ ...d, labels: toggle(d.labels, l) }));
  const setTech = (k: TechKey, b: TechBand) => setDraft((d) => ({ ...d, tech: { ...d.tech, [k]: toggle(d.tech[k], b) } }));

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
    mode, data, isLoading, isError, has, upgrade, nav, state, applied, sort, size, draft, setDraft, secQ, setSecQ, picked, setPicked, how, setHow, drawer, setDrawer,
    silver, locked, gold, maxCompare, items: items as Item[], unscored, asOf, cover, prismAsOf, techAsOf, facets, rows, sum, mix, pg, chips, problems, bad, dirty, sel, filterCount: chips.length,
    go, apply, clear, drop, toggle, setBand, setRange, setLabel, setTech, togglePick, allOnPage, headBox, toggleAll, addWatch, addSelected, exportCsv, sortBy,
  };
}
export type Screener = ReturnType<typeof useScreener>;
