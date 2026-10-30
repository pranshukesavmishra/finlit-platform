// /etfs: every ETF listed on the NSE. Search that forgives spaces and typos, filters, sortable columns you can choose, and a compare tray.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import {
  COLUMNS, COL_BY, DEFAULT_COLS, DEFAULT_STATE, FILTERS, MAX_COMPARE, PAGE, activeFilters, nextSort, parseState, rupee, toParams, useEtfList, useTray, whyBlank,
  type Col, type ColKey, type EtfItem, type FilterKey, type ListState,
} from "../lib/etf";
import { Blank, DataNote, ErrorState, GlossInfo, Skeleton, Tone } from "./common";
import { useUI } from "../lib/ui";
import { MF_METHOD_URL, MF_SCORE_COMPLIANCE, useEtfScores, type ScoreItem } from "../lib/mfScore";
import { ScoreCell } from "../mf/ScoreCell";
import "../styles/etfvs.css";

const COLS_KEY = "finlit-etf-cols-v2";   // v2: the Health score column is on by default; earlier saved choices are not carried over
const readCols = (): ColKey[] => {
  try {
    const v = JSON.parse(localStorage.getItem(COLS_KEY) || "null");
    const ok = Array.isArray(v) ? v.filter((k): k is ColKey => typeof k === "string" && k in COL_BY) : [];
    return ok.length ? ok : DEFAULT_COLS;
  } catch { return DEFAULT_COLS; }
};
const saveCols = (c: ColKey[]) => { try { localStorage.setItem(COLS_KEY, JSON.stringify(c)); } catch { /* private mode: the choice lasts for this visit */ } };

function Cell({ c, i, score, locked, loading }: { c: Col; i: EtfItem; score?: ScoreItem; locked: boolean; loading: boolean }) {
  if (c.key === "score") return <td className={"num etf-c-score"}><ScoreCell item={score} locked={locked} loading={loading} why="Not scored yet." /></td>;
  const v = c.get(i);
  const k = ` etf-c-${c.key}`;
  if (v == null) return <td className={(c.num ? "num" : "") + k}><Blank why={whyBlank(i, c)} /></td>;
  if (c.key === "change" || c.key.startsWith("ret") || c.key === "premium") return <td className={"num" + k}><Tone v={v as number}>{c.text(i)}</Tone></td>;
  return <td className={(c.num ? "num" : "etf-txt") + k}>{c.text(i)}</td>;
}

export function EtfListPage() {
  useDocTitle("ETFs", "Every exchange-traded fund listed on the NSE: price, returns, risk and how it compares. Information only.");
  const [sp, setSp] = useSearchParams();
  const state = useMemo(() => parseState(sp), [sp]);
  const { has: planHas } = useUI();
  const [cols, setCols] = useState<ColKey[]>(readCols);
  const showScore = cols.includes("score");
  const canScore = planHas("gold");
  // a Basic visitor cannot order by the score (the server refuses it, as an order would give the ranking away): the list falls back to the most traded
  const query = !canScore && state.sort === "score" ? { ...state, sort: DEFAULT_STATE.sort, order: DEFAULT_STATE.order } : state;
  const { data, isLoading, isError, isFetching, refetch } = useEtfList(query);
  const { tray, has, toggle, full, remove, clear } = useTray();
  const [openCols, setOpenCols] = useState(false), [openFilters, setOpenFilters] = useState(() => activeFilters(state) > 0);
  const [typed, setTyped] = useState(state.q);
  const update = (patch: Partial<ListState>) => setSp(toParams({ ...state, offset: 0, ...patch }), { replace: true });

  // typing waits a moment before it asks the server; the address bar (back button, shared link) can also change the box
  useEffect(() => { setTyped(state.q); }, [state.q]);
  useEffect(() => {
    if (typed.trim() === state.q) return;
    const h = window.setTimeout(() => update({ q: typed.trim() }), 250);
    return () => window.clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typed]);
  const shown = useMemo(() => COLUMNS.filter((c) => cols.includes(c.key)), [cols]);
  const setCol = (k: ColKey, on: boolean) => { const n = COLUMNS.map((c) => c.key).filter((x) => (x === k ? on : cols.includes(x))); setCols(n); saveCols(n); };

  const items = data?.items ?? [];
  const sq = useEtfScores(items.map((x) => x.symbol), showScore && canScore);
  const scoreBy = useMemo(() => new Map((sq.data?.items || []).map((x) => [x.symbol, x])), [sq.data]);
  const scoresLocked = showScore && (!canScore || !!sq.data?.locked);
  const from = data && data.total ? data.offset + 1 : 0, to = data ? Math.min(data.total, data.offset + items.length) : 0;
  const filtered = activeFilters(state) > 0 || !!state.q;

  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap">        <div className="eyebrow">Exchange-traded funds</div><h1>ETFs on the NSE, in one list.</h1>
        <p>Price and 1-day, 1-year and 5-year returns for every ETF we find on the exchange. Search, filter, sort and compare up to four. Information only: nothing here is advice to buy or sell.</p></div></section>

      <div className="wrap etf-page">
        <Link className="evi-promo" to="/etfs/compare-index-funds">
          <span className="evi-promo-ic" aria-hidden="true"><Icon name="compare" /></span>
          <span className="evi-promo-t"><b>ETF vs Index Fund <span className="evi-badge">Compare</span></b>
            <small>Pick an index such as the Nifty 50, then see the ETFs and direct-plan index funds that follow it side by side: returns, costs, tracking and risk.</small></span>
          <span className="evi-promo-go" aria-hidden="true">Open →</span>
        </Link>
        <div className="etf-tools">
          <label className="etf-search"><Icon name="search" /><span className="sr-only">Search ETFs by name, symbol, fund house or ISIN</span>
            <input type="search" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Search: nifty bank, gold, liquid, HDFC, INF204KB14I2…" autoComplete="off" spellCheck={false} maxLength={60} />
          </label>
          <button className={"btn" + (openFilters ? " on" : "")} aria-expanded={openFilters} aria-controls="etf-filters" onClick={() => setOpenFilters((o) => !o)}><Icon name="table" />Filters{activeFilters(state) ? ` (${activeFilters(state)})` : ""}</button>
          <div className="etf-colwrap">
            <button className={"btn" + (openCols ? " on" : "")} aria-expanded={openCols} aria-controls="etf-cols" onClick={() => setOpenCols((o) => !o)}><Icon name="panel" />Columns</button>
            {openCols && (
              <div className="etf-pop" id="etf-cols" role="group" aria-label="Choose the columns">
                <div className="etf-pop-h"><b>Columns</b><button className="alx-link" onClick={() => { setCols(DEFAULT_COLS); saveCols(DEFAULT_COLS); }}>Reset</button></div>
                {COLUMNS.map((c) => (
                  <label key={c.key} className="etf-check"><input type="checkbox" checked={cols.includes(c.key)} onChange={(e) => setCol(c.key, e.target.checked)} /><span><b>{c.label}</b><small>{c.help}</small></span></label>))}
              </div>)}
          </div>
        </div>

        {openFilters && (
          <div className="card etf-filters" id="etf-filters">
            <div className="etf-fgroup"><h3>Type</h3>
              <div className="fchips">{(data?.groups ?? []).filter((g) => g.count).map((g) => (
                <button key={g.key} className={"chip-b" + (state.asset.includes(g.key) ? " on" : "")} aria-pressed={state.asset.includes(g.key)}
                  onClick={() => update({ asset: state.asset.includes(g.key) ? state.asset.filter((x) => x !== g.key) : [...state.asset, g.key] })}>{g.label} <small>{g.count}</small></button>))}</div></div>
            <div className="etf-fgroup"><h3>Category <small>what the ETF follows, from its registered name</small></h3>
              <div className="fchips">{(data?.categories ?? []).map((c) => (
                <button key={c.key} className={"chip-b" + (state.category.includes(c.key) ? " on" : "")} aria-pressed={state.category.includes(c.key)}
                  onClick={() => update({ category: state.category.includes(c.key) ? state.category.filter((x) => x !== c.key) : [...state.category, c.key] })}>{c.label} <small>{c.count}</small></button>))}</div></div>
            <div className="etf-fgroup"><h3>Ranges <small>an ETF with no figure for a chosen range is left out, and counted below the table</small></h3>
              <div className="etf-ranges">{FILTERS.map((f) => <RangeBox key={f.key} k={f.key} label={f.label} value={state.bounds[f.key]} onCommit={(b) => { const bounds = { ...state.bounds }; if (b[0] == null && b[1] == null) delete bounds[f.key]; else bounds[f.key] = b; update({ bounds }); }} />)}</div></div>
            {filtered && <button className="btn" onClick={() => { setTyped(""); setSp(toParams({ ...DEFAULT_STATE, sort: state.sort, order: state.order }), { replace: true }); }}>Clear search and filters</button>}
          </div>)}

        <p className="etf-count" role="status" aria-live="polite">
          {isLoading ? "Loading ETFs…" : data ? <>Showing <b>{from}–{to}</b> of <b>{data.total}</b> ETFs{data.total < data.universe ? <> (filtered from {data.universe})</> : null}{isFetching ? " · updating…" : ""}</> : ""}
        </p>

        {data && data.hotCount ? <p className="etf-foot faint etf-hotnote">All {data.universe} ETFs on the NSE are listed and sortable. The {data.hotCount} most traded (by rupees traded a day) open instantly; the other {data.universe - data.hotCount} fetch their price chart from the data source when you open them.</p> : null}

        {isError && !data ? <ErrorState what="The ETF list" onRetry={() => refetch()} /> : isLoading ? <Skeleton /> : (
          <>
            {items.length === 0 ? (
              <div className="etf-state"><h2>No ETF matches</h2><p>{state.q ? `Nothing found for “${state.q}” with these filters. Check the spelling or clear a filter.` : "No ETF fits these filters."}</p>
                <button className="btn" onClick={() => { setTyped(""); setSp(new URLSearchParams(), { replace: true }); }}>Clear search and filters</button></div>
            ) : (
              <div className="tw etf-tw" tabIndex={0} role="region" aria-label="ETF table. Scroll sideways for more columns.">
                <table className="etf-table">
                  <caption className="sr-only">Exchange-traded funds on the NSE. Returns are price returns.</caption>
                  <thead><tr>
                    <th scope="col" className="etf-first" aria-sort={state.sort === "name" ? (state.order === "asc" ? "ascending" : "descending") : "none"}>
                      <button className="etf-sort" onClick={() => update(nextSort(state, "name"))}>ETF{state.sort === "name" ? (state.order === "asc" ? " ▲" : " ▼") : ""}</button></th>
                    {shown.map((c) => (
                      <th key={c.key} scope="col" className={(c.num ? "num" : "") + ` etf-c-${c.key}`} aria-sort={c.sort && query.sort === c.sort ? (state.order === "asc" ? "ascending" : "descending") : "none"}>
                        {c.sort && !(c.key === "score" && scoresLocked) ? <button className="etf-sort" onClick={() => update(nextSort(state, c.sort!))} title={c.help}>{c.short}{state.sort === c.sort ? (state.order === "asc" ? " ▲" : " ▼") : ""}</button> : <span title={c.help}>{c.short}</span>}
                        {c.term && <GlossInfo name={c.term} fallback={c.help} />}
                      </th>))}
                  </tr></thead>
                  <tbody>{items.map((i) => (
                    <tr key={i.symbol}>
                      <th scope="row" className="etf-first etf-name">
                        <Link to={`/etfs/${encodeURIComponent(i.symbol)}`}>{i.name}</Link>
                        <div className="etf-sub"><span className="mono">{i.symbol}</span><span className="etf-pricem mono">{i.price == null ? "" : rupee(i.price)}</span>
                          <button className={"etf-add" + (has(i.symbol) ? " on" : "")} aria-pressed={has(i.symbol)} disabled={!has(i.symbol) && full} title={!has(i.symbol) && full ? `You can compare up to ${MAX_COMPARE} ETFs` : undefined}
                            onClick={() => toggle(i.symbol)}>{has(i.symbol) ? "✓ In compare" : "+ Compare"}<span className="sr-only"> {i.name}</span></button></div>
                      </th>
                      {shown.map((c) => <Cell key={c.key} c={c} i={i} score={scoreBy.get(i.symbol)} locked={scoresLocked} loading={sq.isLoading} />)}
                    </tr>))}</tbody>
                </table>
              </div>)}
            <p className="etf-foot faint">— means the figure is not available (hover or open the ETF to see why). 1 day is the change from the previous close. 1 year and 5 years are price returns; 5 years is the total change over the five years, not a yearly rate. Dividends are not included. More periods, risk and the chart are on each ETF's page.</p>
            {showScore && <p className="etf-foot faint">Health score (Gold plan): {MF_SCORE_COMPLIANCE} <Link to={MF_METHOD_URL}>How it works</Link></p>}
            {data && data.excluded > 0 && <p className="etf-foot">{data.excluded} ETF{data.excluded === 1 ? " was" : "s were"} left out because {data.excluded === 1 ? "it has" : "they have"} no figure for a range you chose (for example, listed less than a year).</p>}
            {data && data.total > PAGE && (
              <nav className="etf-pager" aria-label="Pages">
                <button className="btn" disabled={state.offset === 0} onClick={() => update({ offset: Math.max(0, state.offset - PAGE) })}>← Previous {PAGE}</button>
                <span>{from}–{to} of {data.total}</span>
                <button className="btn" disabled={to >= data.total} onClick={() => update({ offset: state.offset + PAGE })}>Next {PAGE} →</button>
              </nav>)}
          </>)}

        <p className="etf-foot faint">Categories are read from each fund's registered name (AMFI); where the name does not say clearly, the category is left blank rather than guessed.</p>
        <DataNote asOf={data?.asOf} updatedAt={data?.updatedAt} source={data?.source} />
        {tray.length > 0 && <div style={{ height: 150 }} aria-hidden="true" />}
      </div>

      {tray.length > 0 && (
        <aside className="etf-tray" aria-label="ETFs chosen to compare">
          <div className="etf-tray-in">
            <span className="etf-tray-l">Compare {tray.length}/{MAX_COMPARE}</span>
            <ul>{tray.map((s) => <li key={s}><span className="mono">{s}</span><button aria-label={`Remove ${s} from the comparison`} onClick={() => remove(s)}>×</button></li>)}</ul>
            <button className="alx-link" onClick={clear}>Clear</button>
            {tray.length >= 2 ? <Link className="btn primary" to={`/etfs/compare?symbols=${tray.join(",")}`}>Compare <Icon name="arrow" /></Link> : <span className="faint">Add one more to compare</span>}
          </div>
        </aside>)}
    </>
  );
}

/** From / to inputs for one range. Applied when the box loses focus or Enter is pressed; letters are ignored. */
function RangeBox({ k, label, value, onCommit }: { k: FilterKey; label: string; value: [number | null, number | null] | undefined; onCommit: (b: [number | null, number | null]) => void }) {
  const [lo, setLo] = useState(value?.[0] != null ? String(value[0]) : ""), [hi, setHi] = useState(value?.[1] != null ? String(value[1]) : "");
  const last = useRef(value);
  useEffect(() => { if (last.current !== value) { last.current = value; setLo(value?.[0] != null ? String(value[0]) : ""); setHi(value?.[1] != null ? String(value[1]) : ""); } }, [value]);
  const parse = (s: string): number | null => (s.trim() === "" || !Number.isFinite(Number(s)) || Math.abs(Number(s)) > 100000 ? null : Number(s));
  const bad = (s: string) => s.trim() !== "" && parse(s) == null;
  const commit = () => { const b: [number | null, number | null] = [parse(lo), parse(hi)]; if (b[0] !== (value?.[0] ?? null) || b[1] !== (value?.[1] ?? null)) onCommit(b); };
  const key = (e: React.KeyboardEvent) => { if (e.key === "Enter") commit(); };
  return (
    <fieldset className="etf-range"><legend>{label}</legend>
      <label><span className="sr-only">{label}, from (percent)</span><input inputMode="decimal" value={lo} placeholder="from" aria-invalid={bad(lo)} onChange={(e) => setLo(e.target.value)} onBlur={commit} onKeyDown={key} /></label>
      <span aria-hidden="true">to</span>
      <label><span className="sr-only">{label}, to (percent)</span><input inputMode="decimal" value={hi} placeholder="to" aria-invalid={bad(hi)} onChange={(e) => setHi(e.target.value)} onBlur={commit} onKeyDown={key} /></label>
      <span className="faint" aria-hidden="true">%</span>
      <span className="sr-only" id={`r-${k}`}>Percent. Leave a box empty for no limit.</span>
    </fieldset>
  );
}
