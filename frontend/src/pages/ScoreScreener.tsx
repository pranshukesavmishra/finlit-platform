import { HScroll } from "../components/HScroll";
import { SplitDivider, useSideWidth } from "../components/SplitDivider";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { PageArt } from "../components/PageArt";
import { Plain } from "../components/Plain";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { useUniverse } from "../lib/screener";
import { useUI } from "../lib/ui";
import { useFocusTrap } from "../lib/focusTrap";
import { useWatchlist, watch } from "../lib/watchlist";
import { cr, nf, dateIN, MINUS } from "../lib/format";
import { ChartHelp } from "../components/ChartHelp";
import {
  BANDS, BAND_ORDER, CAPS, PAGE_SIZES, PILLARS, PRESETS, activePreset, applyFilters, chipsFor, cloneFilters, concentration, emptyFilters, facetCounts, filtersKey, level, missingReason,
  nextSort, pageList, pageOf, parseState, removeChip, serializeState, sortRows, summarize, toCsv, validate, withPreset, withScores,
  type Band, type BandKey, type Filters, type Item, type RangeKey, type SortKey, type State,
} from "../lib/scoreScreen";
import "../styles/scorescreen.css";

/** Score screener: filter the whole company universe by size, sector and FinLit scores. Informational; not a recommendation. */
const Score = ({ r, k, locked }: { r: Item; k: "f" | "t" | "overall" | (typeof PILLARS)[number]["col"]; locked: boolean }) => {
  const v = k === "f" ? r.f : k === "t" ? r.t : r[k];
  if (v != null) return <span className={"ssp " + level(v)}>{v}</span>;
  const why = missingReason(r, k, locked);
  return <span className="ssp na" title={why}>{locked ? <Icon name="lock" /> : MINUS}<span className="sr">Not available: {why}</span></span>;
};
const Dash = ({ why }: { why: string }) => <span title={why}>{MINUS}<span className="sr"> not available: {why}</span></span>;
const med = (v: number | null) => (v == null ? null : nf(v, v % 1 ? 1 : 0));

function HowDialog({ asOf, onClose }: { asOf: string | null; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, true);
  useEffect(() => { ref.current?.scrollTo?.(0, 0); }, []);   // focus lands on the last link; keep the title in view
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === "Escape" && onClose(); document.addEventListener("keydown", k); return () => document.removeEventListener("keydown", k); }, [onClose]);
  return (<>
    <div className="scrim" onClick={onClose} />
    <div className="modal sx-how" role="dialog" aria-modal="true" aria-labelledby="sx-how-t" ref={ref}>
      <button className="modal-x" aria-label="Close" onClick={onClose}>×</button>
      <h3 id="sx-how-t">How scores work</h3>
      <p>Every score runs from 0 to 100 and is worked out from a company's filed statements and its prices. Nothing on this page is computed differently from the company's own report page.</p>
      <dl>
        <dt>Fundamental</dt><dd>The average of four business pillars, rounded to a whole number: Quality (steady earnings, cash that matches profit), Growth (sales and profit growth over 3 to 5 years), Profitability (margins and returns on capital) and Balance sheet (debt, interest cover, liquidity). It needs at least 3 of the 4 pillars; with fewer it shows a dash.</dd>
        <dt>Technical</dt><dd>The technical pillar: how the price is trending against its 50 and 200 day averages, and its momentum.</dd>
        <dt>Overall</dt><dd>The FinLit overall score shown on every company page: the average of the pillar scores that are available, rounded to a whole number.</dd>
        <dt>Bands</dt><dd>Strong 78 and above, Healthy 62 to 77, Mixed 45 to 61, Watch under 45. The filter groups Healthy and Mixed together as 45 to 77. Bands use whole numbers: 44 is Watch, 45 is Mixed, 77 is Healthy, 78 is Strong.</dd>
        <dt>Size</dt><dd>Follows SEBI's rule, ranked by market value among the companies loaded here: the 100 largest are Large cap, the next 150 Mid cap, the rest Small cap.</dd>
        <dt>Missing data</dt><dd>A dash means the figure is not available (not scored yet, not enough data, or not in your plan). It never counts as a pass and is never treated as zero.</dd>
        <dt>Data date</dt><dd>{asOf ? <>Newest scores were computed on {dateIN(asOf)}. </> : <>The score date is not available right now. </>}Scores refresh every night; prices come from the latest market refresh.</dd>
      </dl>
      <p className="muted">This describes financial health and price trend from filings and prices. It is information, not a recommendation. <Link to="/glossary">See the glossary</Link>.</p>
    </div>
  </>);
}

export function ScoreScreener() {
  const [sideW, setSide] = useSideWidth("score");
  useDocTitle("Score screener", "Filter companies by their FinLit scores: size, sector, Fundamental, Technical and Overall.");
  const { data, isLoading, isError } = useUniverse();
  const { has, upgrade, toast } = useUI();
  const nav = useNavigate();
  useWatchlist();
  const [params, setParams] = useSearchParams();
  const state = useMemo(() => parseState(params), [params.toString()]);   // eslint-disable-line react-hooks/exhaustive-deps
  const { filters: applied, sort, size } = state;
  const [draft, setDraft] = useState<Filters>(() => cloneFilters(applied));
  const [secQ, setSecQ] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [how, setHow] = useState(false), [drawer, setDrawer] = useState(false);
  const silver = has("silver"), locked = !silver, maxCompare = has("gold") ? 4 : 2;
  const appliedKey = filtersKey(applied);
  useEffect(() => { setDraft(cloneFilters(applied)); }, [appliedKey]);   // eslint-disable-line react-hooks/exhaustive-deps -- back/forward or a pasted link refreshes the sidebar

  const items = useMemo(() => withScores(data?.rows || []), [data]);
  const unscored = useMemo(() => items.filter((r) => r.scored === false).length, [items]);
  const asOf = data?.asOf ?? null;
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
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const setBand = (k: BandKey, b: Band) => setDraft((d) => ({ ...d, bands: { ...d.bands, [k]: toggle(d.bands[k], b) } }));
  const setRange = (k: RangeKey, end: "min" | "max", v: string) => setDraft((d) => ({ ...d, ranges: { ...d.ranges, [k]: { ...d.ranges[k], [end]: v.trim() === "" ? null : Number(v) } } }));
  const allStrong = PILLARS.every((x) => draft.bands[x.k].length === 1 && draft.bands[x.k][0] === "high");
  const setAllStrong = () => setDraft((d) => ({ ...d, bands: { ...d.bands, ...Object.fromEntries(PILLARS.map((x) => [x.k, allStrong ? [] : ["high"]])) } }));
  const preset = activePreset(applied);
  const usePreset = (id: string) => {
    if (locked) { upgrade("silver", "Score filters come with the Silver plan."); return; }
    apply(preset === id ? { ...draft, bands: { ...draft.bands, f: [], t: [] } } : withPreset(draft, PRESETS.find((p) => p.id === id)!));
  };

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
  const exportCsv = (scope: "selected" | "filtered") => {
    const list = scope === "selected" ? selRows : rows;
    const csv = toCsv(list, { filters: applied, sort, scope, total: rows.length, asOf, exportedOn: new Date().toISOString().slice(0, 10) });
    const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a"); a.href = url; a.download = `finlit-score-screen-${new Date().toISOString().slice(0, 10)}.csv`; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const sortBy = (key: SortKey) => go({ sort: nextSort(sort, key), page: 0 });
  const th = (key: SortKey, label: string, cls = "", help?: string, title?: string) => (
    <th scope="col" className={cls} title={title} aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => sortBy(key)} aria-label={`Sort by ${label}`}>{label} <span aria-hidden="true">{sort.key === key ? (sort.dir > 0 ? "▲" : "▼") : "▾"}</span></button>{help && <ChartHelp id={help} />}
    </th>);
  const rangeBox = (k: RangeKey, label: string) => (
    <div className="sx-range" role="group" aria-label={`${label} score, exact range`}>
      <label>Min<input type="number" inputMode="numeric" min={0} max={100} step={1} value={draft.ranges[k].min ?? ""} onChange={(e) => setRange(k, "min", e.target.value)} placeholder="0" aria-invalid={!!problems[k]} /></label>
      <span aria-hidden="true">to</span>
      <label>Max<input type="number" inputMode="numeric" min={0} max={100} step={1} value={draft.ranges[k].max ?? ""} onChange={(e) => setRange(k, "max", e.target.value)} placeholder="100" aria-invalid={!!problems[k]} /></label>
      {problems[k] && <p className="sx-err" role="alert">{problems[k]}</p>}
    </div>);
  const bandBoxes = (k: "f" | "t", label: string) => (
    <fieldset className="ss-fs"><legend>{label} score</legend>
      {BAND_ORDER.map((b) => <label key={b}><input type="checkbox" checked={draft.bands[k].includes(b)} onChange={() => setBand(k, b)} /><span>{BANDS[b].label}</span></label>)}
      {rangeBox(k, label)}
    </fieldset>);

  const filterCount = chips.length;
  const tiles: [string, string, string?][] = [
    ["Companies found", isLoading ? "…" : nf(sum.found, 0)],
    ["Sectors", isLoading ? "…" : nf(sum.sectors, 0)],
    ["Median Fundamental", med(sum.medF) ?? MINUS, sum.medF == null ? (locked ? "Scores are part of the Silver plan" : "No company in this result has a Fundamental score") : `Middle value of ${nf(sum.nF, 0)} companies with a Fundamental score`],
    ["Median Technical", med(sum.medT) ?? MINUS, sum.medT == null ? (locked ? "Scores are part of the Silver plan" : "No company in this result has a Technical score") : `Middle value of ${nf(sum.nT, 0)} companies with a Technical score`],
    ["Active filters", nf(filterCount, 0)],
  ];

  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="research" />
        <div className="eyebrow">Score screener</div><h1>Filter companies by their FinLit scores.</h1>
        <p>Choose a size, sectors and score ranges. Every company is scored from its latest statements and prices. Need more rules? Use the <Link to="/screener">full screener</Link>.</p></div></section>
      <div className="wrap scr-wrap">
        <div className={"scr sx" + (drawer ? " sx-open" : "")} style={{ "--side-w": `${sideW}px` } as React.CSSProperties}>
          {drawer && <div className="sx-back" onClick={() => setDrawer(false)} aria-hidden="true" />}
          <aside className="scr-side card sx-side" aria-label="Score screener filters" hidden={sideW === 0}>
            <button type="button" className="sx-close btn" onClick={() => setDrawer(false)}>Close filters</button>
            <form onSubmit={(e) => { e.preventDefault(); apply(); }} noValidate>
              <div className="label">Quick views <ChartHelp id="score-filter" /></div>
              <div className="sx-presets" role="group" aria-label="Quick views by score band">
                {PRESETS.map((p) => <button key={p.id} type="button" className={"bandc" + (preset === p.id ? " on" : "")} aria-pressed={preset === p.id} title={p.say} onClick={() => usePreset(p.id)}>{locked && <Icon name="lock" />} {p.label}</button>)}
              </div>
              <div className="label" style={{ marginTop: 18 }}>Market cap</div>
              <div className="sx-opts" role="group" aria-label="Market cap size">
                {CAPS.map((c) => <label key={c} className={"sx-opt" + (draft.caps.includes(c) ? " on" : "")}><input type="checkbox" checked={draft.caps.includes(c)} onChange={() => setDraft((d) => ({ ...d, caps: toggle(d.caps, c) }))} /><span>{c} cap</span><small>{facets.caps[c]}</small></label>)}
              </div>
              <div className="label" style={{ marginTop: 18, display: "flex", justifyContent: "space-between" }}>Industry / sector{draft.sectors.length > 0 && <button type="button" className="alx-link" onClick={() => setDraft((d) => ({ ...d, sectors: [] }))}>Clear {draft.sectors.length}</button>}</div>
              <label className="scr-find sm"><Icon name="table" /><input value={secQ} onChange={(e) => setSecQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && e.preventDefault()} placeholder="Search sectors" aria-label="Search sectors" type="search" /></label>
              <ul className="scr-sec" aria-label="Sectors">
                {facets.sectors.filter(([s]) => s.toLowerCase().includes(secQ.trim().toLowerCase())).map(([s, n]) => (
                  <li key={s}><label><input type="checkbox" checked={draft.sectors.includes(s)} onChange={() => setDraft((d) => ({ ...d, sectors: toggle(d.sectors, s) }))} /><span>{s}</span><small className="faint" style={{ marginLeft: "auto" }}>{n}</small></label></li>))}
                {!facets.sectors.length && !isLoading && <li className="faint">No sectors loaded yet.</li>}
                {!!facets.sectors.length && !facets.sectors.some(([s]) => s.toLowerCase().includes(secQ.trim().toLowerCase())) && <li className="faint">No sector matches “{secQ}”.</li>}
              </ul>
              <div className="label" style={{ marginTop: 18, display: "flex", justifyContent: "space-between" }}>Score filters<button type="button" className="alx-link" onClick={() => setHow(true)}><Icon name="info" /> How scores work</button></div>
              {locked ? (
                <div className="scr-lock"><b><Icon name="lock" /> Score filters are part of Silver</b><span>See and filter by Fundamental, Technical and Overall scores.</span>
                  <button type="button" className="btn primary" onClick={() => upgrade("silver", "Score filters come with the Silver plan.")}>Unlock with Silver</button></div>
              ) : (<>
                {bandBoxes("f", "Fundamental")}
                <fieldset className="ss-fs ss-pil"><legend>Fundamental, by pillar</legend>
                  <button type="button" className={"bandc ss-all" + (allStrong ? " on" : "")} aria-pressed={allStrong} onClick={setAllStrong}>Strong on all four (78 and above)</button>
                  {PILLARS.map((x) => (
                    <div key={x.k} className="ss-prow" role="group" aria-label={`${x.label} score`}>
                      <span className="ss-pn" title={x.say}>{x.label}</span>
                      <span className="ss-seg">{BAND_ORDER.map((b) => (
                        <button key={b} type="button" className={"ss-sb " + b + (draft.bands[x.k].includes(b) ? " on" : "")} aria-pressed={draft.bands[x.k].includes(b)} aria-label={`${x.label} ${BANDS[b].label}`} onClick={() => setBand(x.k, b)}>{BANDS[b].short}</button>))}</span>
                    </div>))}
                </fieldset>
                {bandBoxes("t", "Technical")}
                <fieldset className="ss-fs"><legend>Overall score</legend>{rangeBox("o", "Overall")}</fieldset>
              </>)}
              <div className="sx-hint" role="status" aria-live="polite">{bad ? "Fix the highlighted ranges to apply." : dirty ? "Unsaved changes. Press Apply filters (or Enter) to update the table." : ""}</div>
              <div className="ss-actions"><button type="submit" className="btn primary" disabled={bad}>Apply filters</button><button type="button" className="btn" onClick={clear}>Clear all</button></div>
            </form>
          </aside>
          <SplitDivider width={sideW} set={setSide} />

          <section className="scr-main card" aria-label="Results">
            <div className="sx-top">
              <button type="button" className="btn sx-fbtn" onClick={() => setDrawer(true)} aria-haspopup="dialog">Filters{filterCount > 0 && <span className="dotn">{filterCount}</span>}{dirty && <span className="sr"> (unsaved changes)</span>}</button>
              <button type="button" className="btn" onClick={() => setHow(true)}><Icon name="info" /> How scores work</button>
            </div>
            <div className="ss-stats sx-stats" aria-label="Summary">
              {tiles.map(([l, v, why]) => <div key={l} className="ss-stat" title={why}><b>{v}</b><small>{l}</small></div>)}
            </div>
            {!isLoading && unscored > 0 && <p className="muted" role="note">{nf(unscored, 0)} of {nf(items.length, 0)} listed companies are not scored yet. Scoring fills in every night, or open a company's report to score it now.</p>}
            {chips.length > 0 && <div className="scr-chips" aria-label="Active filters">{chips.map((c) => <button type="button" key={c.id} className="fchip" onClick={() => drop(c.id)} aria-label={`Remove filter ${c.label}`}>{c.label}<span aria-hidden="true">×</span></button>)}<button type="button" className="alx-link" onClick={clear}>Clear all</button></div>}
            {mix.length > 0 && (
              <div className="sx-mix" aria-label="Sector mix of the result">
                <div className="sx-bar" aria-hidden="true">{mix.map((m, i) => <i key={m.label} className={"sx-c" + i} style={{ width: m.pct + "%" }} />)}</div>
                <ul>{mix.map((m, i) => <li key={m.label}><i className={"sx-c" + i} aria-hidden="true" />{m.label} <b>{nf(m.n, 0)}</b> <small>{nf(m.pct, 0)}%</small></li>)}</ul>
              </div>)}
            {isError ? <div className="state"><h2>The score screener is unavailable right now</h2><p>Please try again in a moment.</p></div> : isLoading ? <div className="skeleton" style={{ height: 380 }} /> : (
              <>
                <div className="sx-bulk" role="toolbar" aria-label="Actions for the table">
                  <span aria-live="polite">{sel.length ? `${nf(sel.length, 0)} selected` : `${nf(rows.length, 0)} ${rows.length === 1 ? "company" : "companies"} in this result`}</span>
                  <span className="sx-bulkb">
                    <button type="button" className="btn primary" disabled={sel.length < 2 || sel.length > maxCompare} onClick={() => nav(`/compare?c=${sel.join(",")}`)}
                      title={sel.length > maxCompare ? `Your plan compares up to ${maxCompare} companies` : "Select 2 to " + maxCompare + " companies"}>{sel.length >= 2 && sel.length <= maxCompare ? `Compare ${sel.length}` : "Compare"}</button>
                    <button type="button" className="btn" disabled={!sel.length} onClick={addSelected}>Add to watchlist</button>
                    <button type="button" className="btn" disabled={!sel.length} onClick={() => exportCsv("selected")}>Export selected</button>
                    <button type="button" className="btn" disabled={!rows.length} onClick={() => exportCsv("filtered")}>Export all {nf(rows.length, 0)}</button>
                    {sel.length > 0 && <button type="button" className="alx-link" onClick={() => setPicked([])}>Clear selection</button>}
                  </span>
                  {sel.length > maxCompare && <small className="muted">{has("gold") ? "Compare takes up to 4 companies." : "Your plan compares up to 2 companies; Gold compares 4."}</small>}
                </div>
                <HScroll className="scr-tw" label="results table"><table className="scr-t ss-t sx-t">
                  <caption className="sr">Companies matching the filters, {sort.key === "name" ? "sorted by name" : "sorted by " + sort.key}. Select a column heading to sort.</caption>
                  <thead><tr>
                    <th scope="col"><input ref={headBox} type="checkbox" checked={allOnPage} onChange={toggleAll} aria-label="Select all companies on this page" disabled={!pg.view.length} /></th>
                    <th scope="col" className="sx-n">#</th>
                    {th("name", "Stock", "stick")}{th("price", "LTP (₹)")}{th("market_cap", "Market cap")}{th("sector", "Sector")}{th("f", "Fundamental", "", "score-table")}
                    {PILLARS.map((x) => <Fragment key={x.k}>{th(x.col, x.short, "ss-ph", undefined, x.say)}</Fragment>)}
                    {th("t", "Technical")}{th("overall", "Overall")}<th scope="col">Action</th></tr></thead>
                  <tbody>{pg.view.map((r, i) => {
                    const on = sel.includes(r.symbol);
                    return (
                    <tr key={r.symbol} className={on ? "sx-sel" : ""}>
                      <td><input type="checkbox" checked={on} onChange={() => togglePick(r.symbol)} aria-label={`Select ${r.symbol}`} /></td>
                      <td className="sx-n">{pg.page * size + i + 1}</td>
                      <td className="stick"><Link to={`/stocks/${r.symbol}`} className="co"><span className="av mini" aria-hidden="true">{(r.name || r.symbol).slice(0, 2).toUpperCase()}</span><span><b>{r.symbol}</b><small>{r.name}</small></span></Link></td>
                      <td>{r.price != null ? nf(r.price) : <Dash why="no price yet" />}</td>
                      <td>{r.market_cap != null ? <>{cr(r.market_cap)}{r.cap && <small className="sx-cap">{r.cap} cap</small>}</> : <Dash why="market value not available" />}</td>
                      <td style={{ fontFamily: "var(--sans)", textAlign: "left" }}>{r.sector || <Dash why="sector not listed" />}</td>
                      <td><Score r={r} k="f" locked={locked} /></td>
                      {PILLARS.map((x) => <td key={x.k} className="ss-pc"><Score r={r} k={x.col} locked={locked} /></td>)}
                      <td><Score r={r} k="t" locked={locked} /></td><td><Score r={r} k="overall" locked={locked} /></td>
                      <td className="ss-act"><Link className="btn" to={`/stocks/${r.symbol}`} aria-label={`Open ${r.symbol} report`}>Report</Link>
                        <button type="button" className={"btn" + (watch.has(r.symbol) ? " on" : "")} aria-pressed={watch.has(r.symbol)} aria-label={`${watch.has(r.symbol) ? "Remove" : "Add"} ${r.symbol} ${watch.has(r.symbol) ? "from" : "to"} watchlist`} onClick={() => addWatch(r.symbol)}><Icon name="wallet" /></button></td>
                    </tr>);
                  })}
                    {!rows.length && <tr><td colSpan={15} className="empty">No companies match all of these filters. Try loosening one, or clear them all.</td></tr>}
                  </tbody>
                </table></HScroll>
                <div className="ss-foot">
                  <label className="muted">Rows per page <select value={size} onChange={(e) => go({ size: Number(e.target.value), page: 0 })} aria-label="Rows per page">{PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
                  <span className="muted" aria-live="polite">{pg.from}–{pg.to} of {nf(rows.length, 0)}</span>
                  <nav className="sx-pager" aria-label="Pages">
                    <button type="button" className="btn" disabled={pg.page <= 0} onClick={() => go({ page: pg.page - 1 })} aria-label="Previous page">‹</button>
                    {pageList(pg.page, pg.pages).map((n, i) => n == null ? <span key={"g" + i} aria-hidden="true">…</span> :
                      <button type="button" key={n} className={"btn" + (n === pg.page ? " on" : "")} aria-current={n === pg.page ? "page" : undefined} aria-label={`Page ${n + 1}`} onClick={() => go({ page: n })}>{n + 1}</button>)}
                    <button type="button" className="btn" disabled={pg.page >= pg.pages - 1} onClick={() => go({ page: pg.page + 1 })} aria-label="Next page">›</button>
                  </nav>
                </div>
              </>
            )}
            <Plain>A score screen narrows a long list. It describes financial health and price trend from filings and prices; it is not a recommendation. Open a company's report to see why a score looks the way it does.</Plain>
          </section>
        </div>
      </div>
      {how && <HowDialog asOf={asOf} onClose={() => setHow(false)} />}
    </>
  );
}
