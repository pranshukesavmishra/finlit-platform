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

const rng = (v: string, set: (x: string) => void, label: string) => <input type="number" inputMode="decimal" value={v} onChange={(e) => set(e.target.value)} aria-label={label} placeholder={label.includes("min") || label.includes("Min") ? "min" : "max"} />;

function Screener() {
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const q = paramsToQuery(sp);
  const set = (patch: Partial<SQuery>) => setSp(queryToParams({ ...q, page: 1, view: "", ...patch }), { replace: !("page" in patch) });
  const facets = useFacets(true);
  const list = useScreener(q, q.tab === "table");
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const tick = (it: ScreenerItem) => setPicked((p) => (p.includes(it.key) ? p.filter((x) => x !== it.key) : p.length >= MAX_COMPARE ? p : [...p, it.key]));
  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const cats = (facets.data?.categories || []).filter((c) => q.plan === "all" || (c.n[q.plan] ?? 0) > 0);
  const sortBy = (k: string) => set({ sort: k, dir: q.sort === k && q.dir === "desc" ? "asc" : k === "name" || k === "category" ? "asc" : "desc" });
  const view = activeView(q);
  const compareCodes = picked.map((k) => k.replace("mf:", "")).filter((k) => /^\d+$/.test(k));
  const download = async () => {
    setBusy(true);
    try {
      const r = await fetch(apiUrl(csvUrl(q)), { credentials: "include" });
      if (r.ok) { const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = "finlit-fund-scores.csv"; a.click(); URL.revokeObjectURL(a.href); }
    } finally { setBusy(false); }
  };
  const th = (k: string, label: string, num = true) => <th scope="col" className={num ? "num" : ""} aria-sort={q.sort === k ? (q.dir === "asc" ? "ascending" : "descending") : "none"}><button className="mf-sort" onClick={() => sortBy(k)}>{label}{q.sort === k && <i aria-hidden="true">{q.dir === "asc" ? "▲" : "▼"}</i>}</button></th>;
  const pillarRow = (k: "perf" | "risk" | "cost" | "quality", name: string) => <div className="mfu-rg"><span>{name}</span>{rng(q[k][0], (x) => set({ [k]: [x, q[k][1]] }), `${name} min`)}{rng(q[k][1], (x) => set({ [k]: [q[k][0], x] }), `${name} max`)}</div>;
  return (
    <div className="wrap mf mfu-page">
      <p className="mf-back"><Link to="/funds">← All mutual fund schemes</Link></p>
      <header><span className="eyebrow">Fund score screener · Gold</span><h1>Every scored fund, side by side.</h1>
        <p className="muted">The {MF_SCORE_NAME} with its four parts. {MF_SCORE_COMPLIANCE} <Link to={MF_METHOD_URL}>How it works</Link></p></header>
      <div className="seg" role="tablist" aria-label="View">
        <button role="tab" aria-selected={q.tab === "table"} aria-pressed={q.tab === "table"} onClick={() => set({ tab: "table" })}>All funds</button>
        <button role="tab" aria-selected={q.tab === "board"} aria-pressed={q.tab === "board"} onClick={() => set({ tab: "board", subs: q.subs.slice(0, 1) })}>Category leaderboard</button>
      </div>
      {q.tab === "board" ? <Board q={q} cats={cats} set={set} /> : (
        <div className="mfu-layout">
          <aside className="card mf-card mfu-filters" aria-label="Filters">
            <h2 className="mf-h4">Quick views <span className="faint">from the four parts only</span></h2>
            <div className="mfu-views" role="group" aria-label="Quick views">{VIEWS.map((v) => <button key={v.id} type="button" className={"bandc" + (view === v.id ? " on" : "")} aria-pressed={view === v.id} title={v.say} onClick={() => setSp(queryToParams(view === v.id ? { ...emptyQuery(), plan: q.plan } : { ...emptyQuery(), plan: q.plan, ...v.set, view: v.id }))}>{v.label}</button>)}</div>
            <label className="mfu-f">Name<input type="search" value={q.q} onChange={(e) => set({ q: e.target.value })} placeholder="Part of a fund name" /></label>
            <label className="mfu-f">Plan<select value={q.plan} onChange={(e) => set({ plan: e.target.value })}><option value="Direct">Direct</option><option value="Regular">Regular</option><option value="ETF">ETF</option><option value="all">All plans</option></select></label>
            <label className="mfu-f">Category<select value={q.subs[0] ?? ""} onChange={(e) => set({ subs: e.target.value ? [e.target.value] : [] })}><option value="">All categories</option>{cats.map((c) => <option key={c.sub} value={c.sub}>{c.label} ({c.n[q.plan] ?? Object.values(c.n).reduce((a, b) => a + b, 0)})</option>)}</select></label>
            <div className="mfu-f"><span>Label</span><div className="mfu-chips" role="group" aria-label="Label">{LABELS.map((l) => <button key={l} type="button" className={"bandc" + (q.labels.includes(l) ? " on" : "")} aria-pressed={q.labels.includes(l)} onClick={() => set({ labels: q.labels.includes(l) ? q.labels.filter((x) => x !== l) : [...q.labels, l] })}>{l}</button>)}</div></div>
            <label className="mfu-f">Status<select value={q.status} onChange={(e) => set({ status: e.target.value })}><option value="">Rated and provisional</option><option value="RATED">Rated</option><option value="PROVISIONAL">Provisional</option></select></label>
            <div className="mfu-rg"><span>Score</span>{rng(q.min, (x) => set({ min: x }), "Score min")}{rng(q.max, (x) => set({ max: x }), "Score max")}</div>
            {pillarRow("perf", "Performance")}{pillarRow("risk", "Risk")}{pillarRow("cost", "Cost")}{pillarRow("quality", "Quality")}
            <div className="mfu-rg"><span>AUM ₹ Cr</span>{rng(q.aum[0], (x) => set({ aum: [x, q.aum[1]] }), "AUM min")}{rng(q.aum[1], (x) => set({ aum: [q.aum[0], x] }), "AUM max")}</div>
            <div className="mfu-rg"><span>Age, years</span>{rng(q.age[0], (x) => set({ age: [x, q.age[1]] }), "Age min")}{rng(q.age[1], (x) => set({ age: [q.age[0], x] }), "Age max")}</div>
            <div className="mfu-rg"><span>Expense ≤ %</span>{rng(q.terMax, (x) => set({ terMax: x }), "Expense ratio max")}</div>
            <label className="mfu-check"><input type="checkbox" checked={q.full} onChange={() => set({ full: !q.full })} /> Only funds with full data</label>
            <button type="button" className="mf-linkbtn" onClick={() => setSp(new URLSearchParams())}>Clear all filters</button>
          </aside>
          <section className="mfu-main" aria-label="Results">
            <div className="mfu-bar">
              <p className="mf-count" role="status" aria-live="polite">{list.isLoading ? "Loading funds…" : list.isError ? "Could not load the funds." : <><b>{total.toLocaleString("en-IN")}</b> fund{total === 1 ? "" : "s"}{list.data?.runDate ? ` · scores worked out ${list.data.runDate}` : ""}</>}</p>
              <button type="button" className="btn sm" disabled={busy || !total} onClick={download}><Icon name="download" /> Download CSV</button>
              <button type="button" className="btn sm" disabled={compareCodes.length < 2} onClick={() => nav(`/funds/compare?ids=${compareCodes.join(",")}`)}>Compare {compareCodes.length || ""} selected</button>
            </div>
            {chips(q).length > 0 && <div className="mfu-active" aria-label="Active filters">{chips(q).map((c) => <button key={c.id} type="button" className="chip" onClick={() => setSp(queryToParams(clearChip(q, c.id)))}>{c.text} <span aria-hidden="true">×</span><span className="sr-only">remove</span></button>)}</div>}
            <div className="tw"><table className="mf-table mfu-table">
              <caption className="sr-only">Funds with their Health Score</caption>
              <thead><tr><th scope="col"><span className="sr-only">Compare</span></th>{th("name", "Fund", false)}{th("final", "Score")}{th("perf", "Perf.")}{th("risk", "Risk")}{th("cost", "Cost")}{th("quality", "Quality")}{th("category", "Category", false)}{th("plan", "Plan", false)}{th("aum", "AUM ₹ Cr")}{th("age", "Age")}{th("ter", "Expense %")}{th("r1y", "1Y %")}{th("r3y", "3Y %")}{th("r5y", "5Y %")}</tr></thead>
              <tbody>{(list.data?.items || []).map((it) => (
                <tr key={it.key}>
                  <td><input type="checkbox" checked={picked.includes(it.key)} disabled={it.kind !== "mf" || (!picked.includes(it.key) && picked.length >= MAX_COMPARE)} onChange={() => tick(it)} aria-label={`Compare ${it.name}`} /></td>
                  <th scope="row" className="mf-name"><Link to={it.kind === "mf" ? `/funds/${it.code}` : `/etfs/${it.symbol}`}>{it.name}</Link><small>{it.amc?.replace(/\s*mutual fund\s*$/i, "")}</small></th>
                  <td className="num"><b className={"mfs-pv b-" + bandOf(it.final)}>{scoreText(it.final)}</b><small className="mfu-lb">{it.label}{it.status === "PROVISIONAL" ? " · prov." : ""}</small></td>
                  {PILLARS.map(([k]) => <td className="num" key={k}><b className={"mfs-pv b-" + bandOf(it.pillars[k])}>{scoreText(it.pillars[k])}</b></td>)}
                  <td>{it.categoryLabel}</td><td>{it.plan}</td>
                  <td className="num">{it.aumCr == null ? "—" : nf(it.aumCr, 0)}</td><td className="num">{it.ageYears == null ? "—" : it.ageYears.toFixed(1)}</td><td className="num">{it.ter == null ? "—" : it.ter.toFixed(2)}</td>
                  <td className="num">{it.r1y == null ? "—" : nf(it.r1y, 1)}</td><td className="num">{it.r3y == null ? "—" : nf(it.r3y, 1)}</td><td className="num">{it.r5y == null ? "—" : nf(it.r5y, 1)}</td>
                </tr>))}
                {list.data && list.data.items.length === 0 && <tr><td colSpan={15} className="faint">No scored fund matches these filters.</td></tr>}
              </tbody></table></div>
            {pages > 1 && <nav className="mfu-pages" aria-label="Pages"><button className="btn sm" disabled={q.page <= 1} onClick={() => set({ page: q.page - 1 })}>Previous</button><span>Page {q.page} of {pages}</span><button className="btn sm" disabled={q.page >= pages} onClick={() => set({ page: q.page + 1 })}>Next</button></nav>}
            <p className="faint mf-fine">Blank cells are figures the fund house has not reported. {MF_SCORE_COMPLIANCE}</p>
          </section>
        </div>)}
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
