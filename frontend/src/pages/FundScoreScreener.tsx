// /fund-score-screener (Gold): every scored fund with the FinLit Mutual Fund Health Score, its four parts and the facts beside them; filters, quick views,
// sorting, CSV, compare tick-boxes, and a category leaderboard tab. Plans below Gold get the upgrade page and no request is made for any score.
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { Gate } from "../components/Gate";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import { apiUrl } from "../lib/api";
import { nf } from "../lib/format";
import { MF_METHOD_URL, MF_SCORE_COMPLIANCE, MF_SCORE_NAME, bandOf, scoreText } from "../lib/mfScore";
import { bandVar } from "../lib/scoreBands";
import {
  LABELS, PAGE, PILLARS, VIEWS, activeView, chips, clearChip, csvUrl, emptyQuery, paramsToQuery, queryToParams, useFacets, useLeaderboard, useScreener,
  type ScreenerItem, type SQuery,
} from "../lib/mfScoreUp";
import { HScroll } from "../components/HScroll";
import { CheckRow, FgxFocus, FilterGroup, QuickRow, RangeRow, SearchBox } from "../components/screener/FilterGroup";
import { KpiStrip, TitleCard, Toolbar } from "../components/screener/PageParts";
import "../styles/fgx.css";
import "../styles/scorescreen.css";
import "../styles/mf.css";
import "../styles/mfup.css";

const POINTS = ["The FinLit Mutual Fund Health Score of every scored fund, with its four parts", "Filters by category, plan, score, each part, cost, size and age", "Category leaderboards, compare and a CSV download"];
const MAX_COMPARE = 4;

export function FundScoreScreenerPage() {
  const { has } = useUI();
  useDocTitle("Fund score screener", "Every scored mutual fund and ETF with the FinLit Mutual Fund Health Score, its four parts, cost, size and returns. Gold plan.");
  return has("gold") ? <Screener /> : <Upgrade />;
}

function Upgrade() {
  return (
    <div className="wrap mf mfu-page">
      <p className="mf-back"><Link to="/funds">← All mutual fund schemes</Link></p>
      <header><span className="eyebrow">Fund score screener</span><h1>Screen every fund by its Health Score.</h1>
        <p className="muted">The {MF_SCORE_NAME} of every scored fund, its four parts (Performance, Risk, Cost, Quality), category leaderboards, filters and a CSV download. It is part of the Gold plan.</p></header>
      <Gate tier="gold" title="Fund score screener" points={POINTS}>
        <section className="card mf-card" aria-label="Example of the fund score screener">
          <p className="faint">Layout only. Example rows with no real fund or figure.</p>
          <div className="tw"><table className="mf-cmp"><thead><tr><th scope="col">Fund</th><th scope="col">Score</th><th scope="col">Performance</th><th scope="col">Risk</th><th scope="col">Cost</th><th scope="col">Quality</th></tr></thead>
            <tbody>{["A", "B", "C"].map((n) => <tr key={n}><th scope="row">Example fund {n}</th><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>)}</tbody></table></div>
        </section>
      </Gate>
      <p className="faint mf-fine">{MF_SCORE_COMPLIANCE} <Link to={MF_METHOD_URL}>How it works</Link></p>
    </div>
  );
}

const narrow = () => typeof window !== "undefined" && !!window.matchMedia && window.matchMedia("(max-width: 1000px)").matches;
const PLANS: [string, string][] = [["Direct", "Direct"], ["Regular", "Regular"], ["ETF", "ETF"], ["all", "All plans"]];
const STATUSES: [string, string][] = [["", "Rated and provisional"], ["RATED", "Rated"], ["PROVISIONAL", "Provisional"]];
const SORTS: [string, "asc" | "desc", string][] = [["final", "desc", "Score (high to low)"], ["final", "asc", "Score (low to high)"], ["name", "asc", "Fund name (A to Z)"], ["name", "desc", "Fund name (Z to A)"],
  ["perf", "desc", "Performance (high to low)"], ["risk", "desc", "Risk (high to low)"], ["cost", "desc", "Cost (high to low)"], ["quality", "desc", "Quality (high to low)"],
  ["aum", "desc", "AUM (high to low)"], ["age", "desc", "Age (old to young)"], ["ter", "asc", "Expense % (low to high)"], ["r1y", "desc", "1Y return (high to low)"], ["r3y", "desc", "3Y return (high to low)"], ["r5y", "desc", "5Y return (high to low)"]];
const nz = (...v: string[]) => (v.some(Boolean) ? 1 : 0);
const PARTS = ["perf", "risk", "cost", "quality"] as const;

function Screener() {
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const q = paramsToQuery(sp);
  const set = (patch: Partial<SQuery>) => setSp(queryToParams({ ...q, page: 1, view: "", ...patch }), { replace: !("page" in patch) });
  const facets = useFacets(true);
  const list = useScreener(q, q.tab === "table");
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [drawer, setDrawer] = useState(false), [collapsed, setCollapsed] = useState(false), [catQ, setCatQ] = useState("");
  const [want, setWant] = useState<{ id: string | null; n: number }>({ id: null, n: 0 });
  const showPanel = (id: string | null) => { if (narrow()) setDrawer(true); else setCollapsed(false); if (id) setWant((w) => ({ id, n: w.n + 1 })); };
  const tick = (it: ScreenerItem) => setPicked((p) => (p.includes(it.key) ? p.filter((x) => x !== it.key) : p.length >= MAX_COMPARE ? p : [...p, it.key]));
  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const cats = (facets.data?.categories || []).filter((c) => q.plan === "all" || (c.n[q.plan] ?? 0) > 0);
  const sortBy = (k: string) => set({ sort: k, dir: q.sort === k && q.dir === "desc" ? "asc" : k === "name" || k === "category" ? "asc" : "desc" });
  const view = activeView(q);
  const active = chips(q);
  const compareCodes = picked.map((k) => k.replace("mf:", "")).filter((k) => /^\d+$/.test(k));
  const download = async () => {
    setBusy(true);
    try {
      const r = await fetch(apiUrl(csvUrl(q)), { credentials: "include" });
      if (r.ok) { const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = "finlit-fund-scores.csv"; a.click(); URL.revokeObjectURL(a.href); }
    } finally { setBusy(false); }
  };
  const clearAll = () => setSp(new URLSearchParams());
  const th = (k: string, label: string, num = true) => <th scope="col" className={num ? "num" : ""} aria-sort={q.sort === k ? (q.dir === "asc" ? "ascending" : "descending") : "none"}><button className="mf-sort" onClick={() => sortBy(k)}>{label}{q.sort === k && <i aria-hidden="true">{q.dir === "asc" ? "▲" : "▼"}</i>}</button></th>;
  const pair = (k: "perf" | "risk" | "cost" | "quality" | "aum" | "age", name: string) =>
    <RangeRow key={k} label={name} min={q[k][0]} max={q[k][1]} onChange={(end, v) => set({ [k]: end === "min" ? [v, q[k][1]] : [q[k][0], v] })} />;
  const catRows = cats.filter((c) => c.label.toLowerCase().includes(catQ.trim().toLowerCase()));
  const sortVal = `${q.sort}:${q.dir}`;
  const filterCount = active.length;
  const filtersOpen = drawer || !collapsed;
  const link = (it: ScreenerItem) => (it.kind === "mf" ? `/funds/${it.code}` : `/etfs/${it.symbol}`);
  return (
    <div className="wrap mf mfu-page scr-wrap">
      <p className="mf-back"><Link to="/funds">← All mutual fund schemes</Link></p>
      <TitleCard tier="gold" title="Fund score screener" learnTo={MF_METHOD_URL}
        sub={<>The {MF_SCORE_NAME} of every scored fund, with its four parts. {MF_SCORE_COMPLIANCE}</>} />
      <div className="seg" role="tablist" aria-label="View">
        <button role="tab" aria-selected={q.tab === "table"} aria-pressed={q.tab === "table"} onClick={() => set({ tab: "table" })}>All funds</button>
        <button role="tab" aria-selected={q.tab === "board"} aria-pressed={q.tab === "board"} onClick={() => set({ tab: "board", subs: q.subs.slice(0, 1) })}>Category leaderboard</button>
      </div>
      {q.tab === "board" ? <Board q={q} cats={cats} set={set} /> : (<>
        <KpiStrip items={[
          { icon: "layers", label: "Funds found", value: list.data ? total.toLocaleString("en-IN") : "…", why: "Every scored fund that matches the filters" },
          ...(facets.data ? [{ icon: "building" as const, label: "Categories", value: String(cats.length), why: "Categories that have a scored fund in the chosen plan" }] : []),
          ...(list.data?.runDate ? [{ icon: "layers" as const, label: "Scores worked out", value: list.data.runDate }] : []),
        ]} active={filterCount} filtersOpen={filtersOpen} onFilters={() => (narrow() ? setDrawer(true) : setCollapsed((c) => !c))} />
        <Toolbar q={q.q} setQ={(v) => set({ q: v })} searchLabel="Search in results by fund name" buttons={[
          { id: "category", label: "Category", active: q.subs.length, onClick: () => showPanel("category") },
          { id: "plan", label: "Plan", active: q.plan !== "Direct" ? 1 : 0, onClick: () => showPanel("plan") },
          { id: "scores", label: "Score filters", active: nz(q.min, q.max) + PARTS.reduce((n, k) => n + nz(q[k][0], q[k][1]), 0), onClick: () => showPanel("score") }]}
          sort={<label className="fgx-sort"><span className="sr-only">Sort by</span><select aria-label="Sort by" value={sortVal} onChange={(e) => { const [k, d] = e.target.value.split(":"); set({ sort: k, dir: d as "asc" | "desc" }); }}>
            {!SORTS.some(([k, d]) => `${k}:${d}` === sortVal) && <option value={sortVal}>Sorted by column</option>}
            {SORTS.map(([k, d, l]) => <option key={k + d} value={`${k}:${d}`}>Sort by {l}</option>)}</select></label>} />
        <div className={"fgx-fl sx" + (drawer ? " sx-open" : "") + (collapsed ? " fgx-collapsed" : "")}>
          {drawer && <div className="sx-back" onClick={() => setDrawer(false)} aria-hidden="true" />}
          <aside className="card mf-card sx-side fgx-side" aria-label="Filters" hidden={collapsed && !drawer}>
            <button type="button" className="sx-close btn" onClick={() => setDrawer(false)}>Close filters</button>
            <FgxFocus.Provider value={want}>
              <div className="fgx-top"><span>Filters{filterCount > 0 ? ` · ${filterCount} active` : ""}</span><span className="fgx-tl">{filterCount > 0 && <button type="button" className="fgx-link" onClick={clearAll}>Clear all</button>}<Link className="fgx-link" to={MF_METHOD_URL}>How scores work</Link></span></div>
              <FilterGroup id="quick" title="Quick views" defaultOpen active={view ? 1 : 0} hint="Ready-made combinations of the four parts only.">
                {VIEWS.map((v) => <QuickRow key={v.id} label={v.label} title={v.say} on={view === v.id} onClick={() => setSp(queryToParams(view === v.id ? { ...emptyQuery(), plan: q.plan } : { ...emptyQuery(), plan: q.plan, ...v.set, view: v.id }))} />)}
              </FilterGroup>
              <FilterGroup id="search" title="Search fund" defaultOpen active={nz(q.q)}>
                <SearchBox value={q.q} onChange={(v) => set({ q: v })} placeholder="Part of a fund name" label="Fund name" />
              </FilterGroup>
              <FilterGroup id="plan" title="Plan" defaultOpen active={q.plan !== "Direct" ? 1 : 0}>
                <div role="group" aria-label="Plan" style={{ display: "grid", gap: 8 }}>{PLANS.map(([v, l]) => <QuickRow key={v} label={l} on={q.plan === v} onClick={() => set({ plan: v })} />)}</div>
              </FilterGroup>
              <FilterGroup id="category" title="Category" defaultOpen active={q.subs.length}>
                <SearchBox value={catQ} onChange={setCatQ} placeholder="Search category" label="Search categories" />
                <ul className="fgx-list" aria-label="Categories">
                  {catRows.map((c) => <li key={c.sub}><CheckRow label={c.label} count={c.n[q.plan] ?? Object.values(c.n).reduce((a, b) => a + b, 0)} checked={q.subs.includes(c.sub)} onChange={() => set({ subs: q.subs.includes(c.sub) ? q.subs.filter((x) => x !== c.sub) : [c.sub] })} /></li>)}
                  {!cats.length && !facets.isLoading && <li className="fgx-none">No categories loaded yet.</li>}
                  {!!cats.length && !catRows.length && <li className="fgx-none">No category matches “{catQ}”.</li>}
                </ul>
              </FilterGroup>
              <FilterGroup id="label" title="Fund label" defaultOpen active={q.labels.length}>
                <div className="fgx-chips" role="group" aria-label="Label">{LABELS.map((l) => { const on = q.labels.includes(l); return <button key={l} type="button" className={"fgx-chip" + (on ? " is-on" : "")} aria-pressed={on} onClick={() => set({ labels: on ? q.labels.filter((x) => x !== l) : [...q.labels, l] })}>{on && <i aria-hidden="true">&#10003;</i>}{l}</button>; })}</div>
              </FilterGroup>
              <FilterGroup id="status" title="Status" active={q.status ? 1 : 0}>
                <div role="group" aria-label="Status" style={{ display: "grid", gap: 8 }}>{STATUSES.map(([v, l]) => <QuickRow key={v || "any"} label={l} on={q.status === v} onClick={() => set({ status: v })} />)}</div>
              </FilterGroup>
              <FilterGroup id="score" title="Score filters" active={nz(q.min, q.max)}>
                <RangeRow label="Score" min={q.min} max={q.max} onChange={(end, v) => set(end === "min" ? { min: v } : { max: v })} />
              </FilterGroup>
              <FilterGroup id="parts" title="Component scores" active={PARTS.reduce((n, k) => n + nz(q[k][0], q[k][1]), 0)}>
                {pair("perf", "Performance")}{pair("risk", "Risk")}{pair("cost", "Cost")}{pair("quality", "Quality")}
              </FilterGroup>
              <FilterGroup id="size" title="Size and age" active={nz(...q.aum) + nz(...q.age) + nz(q.terMax)}>
                {pair("aum", "AUM ₹ Cr")}{pair("age", "Age, years")}
                <RangeRow label="Expense ratio, up to %" maxOnly min="" max={q.terMax} step="any" onChange={(_e, v) => set({ terMax: v })} />
              </FilterGroup>
              <div className="fgx-g"><div className="fgx-body" style={{ paddingTop: 10 }}><CheckRow label="Only funds with full data" checked={q.full} onChange={() => set({ full: !q.full })} /></div></div>
            </FgxFocus.Provider>
            <div className="ss-actions"><button type="button" className="btn primary" onClick={() => setDrawer(false)}>Show {list.data ? total.toLocaleString("en-IN") : ""} funds</button><button type="button" className="btn" onClick={clearAll}>Clear all</button></div>
          </aside>
          <section className="mfu-main card scr-main" aria-label="Results">
            <div className="sx-top"><button type="button" className="btn sx-fbtn" onClick={() => setDrawer(true)} aria-haspopup="dialog">Filters{filterCount > 0 && <span className="dotn">{filterCount}</span>}</button></div>
            <div className="sx-bulk">
              <p className="mf-count" role="status" aria-live="polite">{list.isLoading ? "Loading funds…" : list.isError ? "Could not load the funds." : <><b>{total.toLocaleString("en-IN")}</b> fund{total === 1 ? "" : "s"}{list.data?.runDate ? ` · scores worked out ${list.data.runDate}` : ""}</>}</p>
              <span className="sx-bulkb">
                <button type="button" className="btn sm" disabled={busy || !total} onClick={download}><Icon name="download" /> Download CSV</button>
                <button type="button" className="btn sm" disabled={compareCodes.length < 2} onClick={() => nav(`/funds/compare?ids=${compareCodes.join(",")}`)}>Compare {compareCodes.length || ""} selected</button>
              </span>
            </div>
            {active.length > 0 && <div className="scr-chips mfu-active" aria-label="Active filters">{active.map((c) => <button key={c.id} type="button" className="fchip" onClick={() => setSp(queryToParams(clearChip(q, c.id)))}>{c.text} <span aria-hidden="true">×</span><span className="sr-only">remove</span></button>)}<button type="button" className="alx-link" onClick={clearAll}>Clear all</button></div>}
            <HScroll className="scr-tw" label="results table"><table className="mf-table mfu-table scr-t sx-t">
              <caption className="sr-only">Funds with their Health Score</caption>
              <thead><tr><th scope="col"><span className="sr-only">Compare</span></th><th scope="col" className="sx-n">#</th>{th("name", "Fund", false)}{th("final", "Score")}{th("perf", "Performance")}{th("risk", "Risk")}{th("cost", "Cost")}{th("quality", "Quality")}{th("category", "Category", false)}{th("plan", "Plan", false)}{th("aum", "AUM ₹ Cr")}{th("age", "Age")}{th("ter", "Expense %")}{th("r1y", "1Y %")}{th("r3y", "3Y %")}{th("r5y", "5Y %")}<th scope="col"><span className="sr-only">Open</span></th></tr></thead>
              <tbody>{(list.data?.items || []).map((it, i) => (
                <tr key={it.key} className={picked.includes(it.key) ? "sx-sel" : ""}>
                  <td><input type="checkbox" checked={picked.includes(it.key)} disabled={it.kind !== "mf" || (!picked.includes(it.key) && picked.length >= MAX_COMPARE)} onChange={() => tick(it)} aria-label={`Compare ${it.name}`} /></td>
                  <td className="sx-n">{(q.page - 1) * PAGE + i + 1}</td>
                  <th scope="row" className="mf-name stick"><Link to={link(it)}>{it.name}</Link><small>{it.amc?.replace(/\s*mutual fund\s*$/i, "")}</small></th>
                  <td className="num"><b className={"mfs-pv b-" + bandOf(it.final)}>{scoreText(it.final)}</b><small className="mfu-lb">{it.label}{it.status === "PROVISIONAL" ? " · prov." : ""}</small></td>
                  {PILLARS.map(([k]) => <td className="num" key={k}><b className={"mfs-pv b-" + bandOf(it.pillars[k])}>{scoreText(it.pillars[k])}</b></td>)}
                  <td>{it.categoryLabel}</td><td>{it.plan}</td>
                  <td className="num">{it.aumCr == null ? "—" : nf(it.aumCr, 0)}</td><td className="num">{it.ageYears == null ? "—" : it.ageYears.toFixed(1)}</td><td className="num">{it.ter == null ? "—" : it.ter.toFixed(2)}</td>
                  <td className="num">{it.r1y == null ? "—" : nf(it.r1y, 1)}</td><td className="num">{it.r3y == null ? "—" : nf(it.r3y, 1)}</td><td className="num">{it.r5y == null ? "—" : nf(it.r5y, 1)}</td>
                  <td className="fgx-go"><Link to={link(it)} aria-label={`Open ${it.name}`} tabIndex={-1}><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg></Link></td>
                </tr>))}
                {list.data && list.data.items.length === 0 && <tr><td colSpan={17} className="faint">No scored fund matches these filters.</td></tr>}
              </tbody></table></HScroll>
            {pages > 1 && <nav className="mfu-pages" aria-label="Pages"><button className="btn sm" disabled={q.page <= 1} onClick={() => set({ page: q.page - 1 })}>Previous</button><span>Page {q.page} of {pages}</span><button className="btn sm" disabled={q.page >= pages} onClick={() => set({ page: q.page + 1 })}>Next</button></nav>}
            <p className="faint mf-fine">Blank cells are figures the fund house has not reported. {MF_SCORE_COMPLIANCE}</p>
          </section>
        </div></>)}
    </div>
  );
}

function Board({ q, cats, set }: { q: SQuery; cats: { sub: string; label: string; n: Record<string, number> }[]; set: (p: Partial<SQuery>) => void }) {
  const sub = q.subs[0] || cats[0]?.sub || "";
  const plan = q.plan === "all" ? "Direct" : q.plan;
  const b = useLeaderboard(sub, plan, true);
  const d = b.data;
  return (
    <section className="card mf-card mfu-board" aria-label="Category leaderboard">
      <div className="mfu-bar">
        <label className="mfu-f">Category<select value={sub} onChange={(e) => set({ subs: [e.target.value] })}>{cats.map((c) => <option key={c.sub} value={c.sub}>{c.label}</option>)}</select></label>
        <label className="mfu-f">Plan<select value={plan} onChange={(e) => set({ plan: e.target.value })}><option>Direct</option><option>Regular</option></select></label>
      </div>
      {b.isLoading ? <div className="skeleton" style={{ height: 220 }} /> : !d || d.locked ? <p className="faint">The leaderboard is not available right now.</p> : (
        <>
          {d.stats && <p className="mfu-stats" data-testid="board-stats">{d.stats.n} scored fund{d.stats.n === 1 ? "" : "s"} in {d.categoryLabel} ({plan} plan). Median score <b>{scoreText(d.stats.median)}</b>, middle half between <b>{scoreText(d.stats.p25)}</b> and <b>{scoreText(d.stats.p75)}</b>, range {scoreText(d.stats.min)} to {scoreText(d.stats.max)}.{d.stats.notRated > 0 ? ` ${d.stats.notRated} more not rated.` : ""}</p>}
          {d.nearIdentical && <p className="mf-note" role="note"><Icon name="info" /><span>{d.nearIdenticalText}</span></p>}
          <ol className="mfu-lb-list">{d.items.map((it, i) => (
            <li key={it.key}>
              <span className="mfu-pos" aria-label={`Ranks ${i + 1} of ${d.items.length} on this score`}>{i + 1}</span>
              <Link to={it.kind === "mf" ? `/funds/${it.code}` : `/etfs/${it.symbol}`} className="mfu-ln">{it.name}</Link>
              <span className="mfu-mini" aria-hidden="true">{PILLARS.map(([k, n]) => <i key={k} title={`${n} ${scoreText(it.pillars[k])}`} style={{ height: `${Math.max(6, it.pillars[k] ?? 0)}%`, background: bandVar(bandOf(it.pillars[k])) }} />)}</span>
              <b className={"mfs-pv b-" + bandOf(it.final)}>{scoreText(it.final)}</b><small>{it.label}</small>
            </li>))}</ol>
          <p className="faint mf-fine">Order is by this score only: a fund higher in the list ranks higher on this score. {MF_SCORE_COMPLIANCE}</p>
        </>)}
    </section>
  );
}
