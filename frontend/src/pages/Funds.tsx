// Mutual funds: the scheme list, one scheme's page and the side-by-side comparison. Data is AMFI's own NAV files (see backend/finlit/mf.py); the section is free.
// Information only: no ranking, no "best", no advice. Every page shows the source, the data date and the disclaimer.
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { PageArt } from "../components/PageArt";
import { Icon } from "../lib/icons";
import { useUI } from "../lib/ui";
import { useDocTitle } from "../lib/title";
import { dateIN, nf } from "../lib/format";
import {
  CHECKS, EMPTY_QUERY, RETURN_LABELS, TRAY_MAX, catNames, categoryShort, compareUrl, effectiveQuery, navFull, navText, parseIds, parseQuery, pctText, queryToParams, readCols, rowSortValue, subCats, tone,
  useFundCompare, useFundDetail, useFundFacts, useFundFilters, useFundList, useFundPortfolio, useHotList, useTray, writeCols,
  type ColId, type CompareFund, type FundDetail, type ListQuery, type RangeKey, type SortKey,
} from "../lib/mf";
import { keyLabel, selectionTitle, tabLabel } from "../lib/mfCategories";
import { ColumnPicker, Controls, Pager } from "../mf/Controls";
import { CategoryCards, CategoryPicker } from "../mf/Dashboard";
import { FundChart, SERIES_STYLE } from "../mf/FundChart";
import { FundTable } from "../mf/FundTable";
import { Fig, Foot, GTerm, PlanChip } from "../mf/Bits";
import { FactsCard } from "../mf/Facts";
import { ReturnsBlock } from "../mf/Returns";
import { HoldingsSection } from "../holdings";
import { FundHeadToHead } from "./FundHeadToHead";
import "../styles/mf.css";

const HEAD = (title: string, lead: string) => (
  <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="portfolio" />
    <div className="eyebrow">Mutual funds</div><h1>{title}</h1><p>{lead}</p></div></section>
);
const Problem = ({ title, text, retry }: { title: string; text: string; retry?: () => void }) => (
  <div className="wrap state" role="alert"><h2>{title}</h2><p>{text}</p>{retry && <button className="btn" onClick={retry}>Try again</button>} <Link className="btn" to="/funds">Back to all schemes</Link></div>
);
/** Periods that live in the Risk area of a scheme's page only (never as list or compare columns). */
const OTHER_PERIODS: { k: "1m" | "6m" | "3y"; label: string }[] = [{ k: "1m", label: "1 month" }, { k: "6m", label: "6 months" }, { k: "3y", label: "3 years, per year" }];
const axisFmt = (v: number) => nf(v, Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 100 ? 1 : 2);
const shortAmc = (a: string) => a.replace(/\s*mutual fund\s*$/i, "");

// ================================================================================================ list

/** How to read the category table: what each figure is, where it comes from, and the checklist's rules. */
function Legend() {
  return (
    <section className="faint mf-legend" aria-label="How to read the table">
      <p><b>Returns.</b> <b>1 year</b> is the total change in NAV over the year; <b>3 years</b> and <b>5 years</b> are yearly rates (<GTerm id="cagr-compound-annual-growth-rate">CAGR</GTerm>), not totals.
        <b> SIP returns</b> are the yearly rate (XIRR) of putting the same amount in every month for the last 3 or 5 years: one instalment at the last NAV of each month, everything valued at the latest NAV. A scheme without a month-end NAV for every one of those months shows a dash.
        Returns are worked out for <GTerm id="growth-option">Growth</GTerm> options only (<GTerm id="idcw-income-distribution-cum-capital-withdrawal">IDCW</GTerm> payouts change the NAV). Compare <GTerm id="direct-plan">Direct</GTerm> with Direct and <GTerm id="regular-plan">Regular</GTerm> with Regular.</p>
      <p><b>Fund size</b> is AMFI's average assets under management for the latest quarter, all plans of the scheme together (where AMFI lists none, the fund house's month-end net assets; the tooltip says which). <b>Expense ratio</b> is the plan's own total expense ratio from AMFI's latest file, percent a year.</p>
      <p><b>Checklist.</b> Five plain checks, each against the active Growth options of the same category and plan:</p>
      <ol>{CHECKS.map((c) => <li key={c.key}><b>{c.label}</b>: {c.rule}.</li>)}</ol>
      <p>“3/5” means three checks passed out of five that could be worked out. A check counts only when the scheme has the figure and at least 3 schemes of its category have it too. It sums up past figures; it is not a rating, a ranking or a recommendation, and no star ratings are shown. A dash (—) anywhere means no figure; hover or tap it for the reason.</p>
      <p>* ELSS: up to ₹1.5 lakh a year put into ELSS can be deducted under Section 80C in the old tax regime; at the 30% slab plus 4% cess that saves up to ₹46,800 of tax. The new tax regime has no 80C deduction. ELSS units are locked in for three years.</p>
    </section>
  );
}

export function FundListPage() {
  const { toast } = useUI();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const q = useMemo(() => parseQuery(sp), [sp]);
  const eq = useMemo(() => effectiveQuery(q), [q]);   // with no chosen order: largest funds first
  const [text, setText] = useState(q.q);
  const [cols, setCols] = useState<ColId[]>(readCols);
  const [tray, toggle, clear] = useTray();
  const filt = useFundFilters();
  const subs = useMemo(() => (q.tab === "all" ? [] : subCats(filt.data?.categories, q.tab, q)), [filt.data, q]);
  const names = useMemo(() => (q.tab === "all" || q.cats === null ? null : filt.data ? catNames(filt.data.categories, q.tab, q.cats) : undefined), [filt.data, q.tab, q.cats]);
  const ready = q.view === "ready";
  const list = useFundList(eq, names, !ready);
  const year = (filt.data?.dataDate || list.data?.dataDate || new Date().toISOString()).slice(0, 4);
  const chosen = q.tab === "all" ? [] : (q.cats ?? []).map(keyLabel).sort((a, b) => a.localeCompare(b));
  const title = `${selectionTitle(q.tab, chosen, q.cats === null)} mutual funds ${year}`;
  useDocTitle(title, "Compare all mutual funds in the chosen categories based on latest returns, historic returns, SIP returns, latest NAV, checklist and more. Information only.");

  const set = (patch: Partial<ListQuery>) => setSp(queryToParams({ ...q, page: 1, ...patch }), { replace: !("page" in patch) });
  useEffect(() => { if (text.trim() === q.q) return; const t = window.setTimeout(() => set({ q: text.trim() }), 350); return () => window.clearTimeout(t); }, [text]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setText(q.q); }, [q.q]);
  const onSort = (s: SortKey) => set(eq.sort === s ? { sort: s, dir: eq.dir === "asc" ? "desc" : "asc" } : { sort: s, dir: s === "name" || s === "amc" || s === "category" ? "asc" : "desc" });
  const pick = (code: number) => { if (!toggle(code)) toast(`You can compare up to ${TRAY_MAX} schemes at a time.`); };
  const hot = useHotList(ready);
  const none = q.tab !== "all" && q.cats !== null && q.cats.length === 0;
  const d = ready || none ? undefined : list.data;
  const hotRows = useMemo(() => {
    const rows = hot.data?.items || [];
    if (!q.sort) return rows;
    const key = q.sort, sgn = q.dir === "desc" ? -1 : 1;
    return [...rows].sort((a, b) => { const x = rowSortValue(a, key), y = rowSortValue(b, key); return x == null ? 1 : y == null ? -1 : (x < y ? -1 : x > y ? 1 : 0) * sgn; });
  }, [hot.data, q.sort, q.dir]);
  const facts = (ready ? hot.data : d) || filt.data;
  const t = filt.data?.totals;

  return (
    <>
      {HEAD(title, "Compare all mutual funds in the chosen categories based on latest returns, historic returns, SIP returns, latest NAV, checklist and more.")}
      <div className="wrap mf">
        <CategoryCards q={q} onPick={(c) => set({ tab: c.tab, cats: [c.key], view: "" })} />
        <CategoryPicker q={q} subs={subs} loading={filt.isLoading} onTab={(tab) => set({ tab, cats: null })} onCats={(cats) => set({ cats })} />
        <p className="faint mf-fine" style={{ margin: 0 }}>Where the industry's money sits and moves each month: <Link to="/funds/insights">Mutual Fund Insights</Link>.</p>
        <Controls q={q} text={text} onText={setText} set={set} filters={filt.data} loading={list.isFetching} />

        <div className="mf-bar">
          <div className="seg" role="group" aria-label="Which schemes to show">
            <button aria-pressed={!ready} onClick={() => set({ view: "" })}>Chosen categories</button>
            <button aria-pressed={ready} onClick={() => set({ view: "ready" })}>Ready list ({hot.data?.items.length ?? 100})</button>
          </div>
          <p className="mf-count" role="status" aria-live="polite">
            {ready ? (hot.data ? <>The <b>{hot.data.items.length}</b> schemes kept ready for instant opening, from every category.</> : "Loading…")
              : none ? "No category ticked."
                : d ? <>Showing <b>{d.total.toLocaleString("en-IN")}</b> scheme{d.total === 1 ? "" : "s"}{q.tab === "all" ? "" : " in the chosen categories"}{d.total === 0 ? " (none match)" : ""}</> : "Loading schemes…"}
            {!ready && t && !q.stopped && <span className="faint"> · {(t.schemes - t.active).toLocaleString("en-IN")} older schemes have stopped publishing and are hidden</span>}
            {facts?.dataDate && <span className="faint"> · NAVs up to {dateIN(facts.dataDate)}</span>}
          </p>
          <ColumnPicker cols={cols} onChange={(c) => { setCols(c); writeCols(c); }} />
        </div>

        {ready ? (
          !hot.data ? <div className="card" aria-busy="true"><div className="skeleton" style={{ height: 420 }} /></div> : (
            <div className="card mf-tablecard">
              <p className="faint mf-fine mf-pad">{hot.data.basis}</p>
              <FundTable rows={hotRows} cols={cols} q={q} onSort={onSort} picked={tray} onPick={pick} />
            </div>)
        ) : none ? (
          <div className="pm-empty mf-empty"><b>Tick at least one category.</b><p>Use the tick boxes above, “Select All”, or one of the cards.</p>
            <button className="btn" onClick={() => set({ cats: null })}>Tick every {tabLabel(q.tab).toLowerCase()} category</button></div>
        ) : list.isError && !d ? <Problem title="The scheme list is unavailable right now" text="Please try again in a moment." retry={() => list.refetch()} /> : !d ? (
          <div className="card" aria-busy="true"><div className="skeleton" style={{ height: 420 }} /></div>
        ) : d.total === 0 ? (
          <div className="pm-empty mf-empty"><b>No schemes match.</b><p>Try fewer filters or a shorter search. Spaces and small typos do not matter.{q.tab !== "all" && " The search covers the chosen categories only."}</p>
            {q.tab !== "all" && q.q && <button className="btn primary" onClick={() => set({ tab: "all", cats: null })}>Search every category</button>}{" "}
            <button className="btn" onClick={() => { setText(""); setSp(new URLSearchParams(), { replace: true }); }}>Clear search and filters</button></div>
        ) : (
          <div className="card mf-tablecard">
            <FundTable rows={d.items} cols={cols} q={eq} onSort={onSort} picked={tray} onPick={pick} peers={d.peers} />
            <Pager q={q} pages={d.pages} total={d.total} onPage={(p) => { set({ page: p }); window.scrollTo({ top: 0 }); }} onSize={(n) => set({ size: n })} />
          </div>
        )}
        <Legend />
        <Foot facts={facts} />
      </div>

      {tray.length > 0 && (
        <div className="mf-tray" role="region" aria-label="Schemes chosen for comparison">
          <span><b>{tray.length}</b> scheme{tray.length > 1 ? "s" : ""} chosen{tray.length < 2 ? ". Choose one more to compare." : "."}</span>
          <button className="btn primary" disabled={tray.length < 2} onClick={() => nav(compareUrl(tray))}><Icon name="compare" />Compare</button>
          <button className="btn" onClick={clear}>Clear</button>
        </div>)}
    </>
  );
}

// ================================================================================================ one scheme

function Risk({ d }: { d: FundDetail }) {
  const { vol1y, vol3y, maxDrawdown: m } = d.risk;
  return (
    <div className="card mf-card">
      <div className="card-h"><h3><span className="ci"><Icon name="gauge" /></span>Risk, from the NAV history</h3></div>
      <div className="mf-risk">
        <div><span className="label"><GTerm id="volatility">Volatility</GTerm> · 1 year</span><b>{vol1y.value == null ? <Fig v={null} why={vol1y.why} /> : pctText(vol1y.value, 2, false)}</b>
          <p className="muted">{vol1y.value == null ? vol1y.why : "How much the NAV swings, as a yearly figure. A fund at 14% typically moves about 14% either side of its average yearly path; one at 1% barely moves. It says how bumpy the ride was, not which way the NAV went."}</p></div>
        <div><span className="label"><GTerm id="volatility">Volatility</GTerm> · 3 years</span><b>{vol3y.value == null ? <Fig v={null} why={vol3y.why} /> : pctText(vol3y.value, 2, false)}</b>
          <p className="muted">{vol3y.value == null ? vol3y.why : "The same measure over three years, so one calm or wild year counts for less."}</p></div>
        <div><span className="label"><GTerm id="drawdown">Largest fall</GTerm> (maximum drawdown)</span><b>{m.value == null ? <Fig v={null} why={m.why} /> : <span className={tone(m.value)}>{pctText(m.value, 2, false)}</span>}</b>
          <p className="muted">{m.value == null ? m.why : m.peak && m.trough && m.value < 0 ? `The deepest fall from a NAV high (${dateIN(m.peak)}) to a later low (${dateIN(m.trough)}) since ${dateIN(m.since || m.peak)}. It shows how deep the worst stretch was, not what comes next.` : "The NAV never fell below an earlier high in the history on file."}</p></div>
      </div>
      <h4 className="mf-h4">Other periods</h4>
      <ul className="mf-other">{OTHER_PERIODS.map(({ k, label }) => { const r = d.returns[k]; return (
        <li key={k}><span>{label}</span><b><Fig v={r.value} why={r.why} /></b><small className="muted">{r.value == null ? r.why : r.kind === "cagr" ? "per year" : "total change"}</small></li>); })}</ul>
      <p className="faint mf-fine">Volatility is the standard deviation of daily NAV changes (weekend NAVs left out) times the square root of 252. Both measures use only the NAV history on file for this scheme.</p>
    </div>
  );
}

function NavChart({ d }: { d: FundDetail }) {
  const keys = (["1M", "6M", "1Y", "3Y", "5Y", "MAX"] as RangeKey[]).filter((k) => d.series[k]);
  const [range, setRange] = useState<RangeKey>(keys.includes("1Y") ? "1Y" : keys[keys.length - 1]);
  if (!keys.length) return <div className="card mf-card"><div className="card-h"><h3><span className="ci"><Icon name="line" /></span>NAV chart</h3></div><p className="muted mf-pad">{d.returnsNote || d.history.note || "No NAV history is loaded for this scheme yet."}</p></div>;
  const p = d.series[keys.includes(range) ? range : keys[0]]!;
  const change = (p.v[p.v.length - 1] / p.v[0] - 1) * 100;
  return (
    <div className="card mf-card">
      <div className="card-h"><h3><span className="ci"><Icon name="line" /></span>NAV chart</h3>
        <div className="seg" role="group" aria-label="Chart range">{keys.map((k) => <button key={k} aria-pressed={k === range} onClick={() => setRange(k)}>{k === "MAX" ? "Since launch" : k}</button>)}</div></div>
      <FundChart series={[{ key: String(d.code), label: d.name, t: p.t, v: p.v }]} format={axisFmt} label={`NAV of ${d.name}, ${range === "MAX" ? "since the first NAV on file" : "last " + range}`} />
      <p className="faint mf-fine">Total change over this range: <b className={tone(change)}>{pctText(change)}</b> (NAV of {dateIN(p.t[0])} to NAV of {dateIN(p.t[p.t.length - 1])}).
        The chart shows NAV in rupees; the line is thinned to at most a few hundred points for long periods.</p>
    </div>
  );
}

export function FundDetailPage() {
  const { id = "" } = useParams();
  const code = /^\d{1,7}$/.test(id) ? Number(id) : 0;
  const { data: d, isLoading, error, refetch } = useFundDetail(code);
  const nav = useNavigate();
  const { toast } = useUI();
  const [tray, toggle] = useTray();
  const facts = useFundFacts(code), portfolio = useFundPortfolio(code);
  useDocTitle(d ? d.name : "Mutual fund", d ? `${d.name}: NAV, returns and risk from AMFI data. Information only.` : undefined);

  if (!code || (error && (error as { status?: number }).status === 404)) return <><div className="wrap state" role="alert"><h2>We could not find this scheme</h2><p>No mutual fund scheme has the code “{id}”.</p><Link className="btn primary" to="/funds">Search all schemes</Link></div></>;
  if (error && !d) return <Problem title="This scheme is unavailable right now" text="Please try again in a moment." retry={() => refetch()} />;
  if (isLoading || !d) return <div className="wrap mf" aria-busy="true"><div className="skeleton" style={{ height: 140, marginTop: 28 }} /><div className="skeleton" style={{ height: 320, marginTop: 16 }} /></div>;

  const inTray = tray.includes(d.code);
  const ch = d.change;
  return (
    <div className="wrap mf mf-detail">
      <p className="mf-back"><Link to="/funds">← All mutual fund schemes</Link></p>
      <header className="mf-head">
        <div>
          <span className="eyebrow">{d.categoryGroup}</span>
          <h1>{d.name}</h1>
          <ul className="mf-chips" aria-label="About this scheme">
            <li><Link className="chip gold" to={`/funds?amc=${encodeURIComponent(d.amc)}`}>{d.amc}</Link></li>
            <li><Link className="chip ghost" to={`/funds?category=${encodeURIComponent(d.category)}`}>{categoryShort(d.category)}</Link></li>
            <li><span className="chip ghost"><GTerm id={d.plan === "Regular" ? "regular-plan" : "direct-plan"}>{d.plan === "Unspecified" ? "Plan not stated" : d.plan + " plan"}</GTerm></span></li>
            <li><span className="chip ghost"><GTerm id={d.optionClass === "IDCW" ? "idcw-income-distribution-cum-capital-withdrawal" : "growth-option"}>{d.option}</GTerm></span></li>
            <li><span className="chip ghost"><GTerm id="open-ended-and-closed-ended-funds">{d.schemeType}</GTerm></span></li>
          </ul>
          <p className="faint mf-ids">{d.isin ? <><GTerm id="isin">ISIN</GTerm> {d.isin} · </> : null}AMFI scheme code {d.code}{d.isinReinvest ? <> · reinvestment ISIN {d.isinReinvest}</> : null}</p>
        </div>
        <div className="mf-navbox card">
          <span className="label"><GTerm id="net-asset-value-nav">NAV</GTerm> · {d.navDate ? dateIN(d.navDate) : "no date"}</span>
          <b className="mf-nav" title={navFull(d.nav)}>{navText(d.nav)}</b>
          {ch ? <span className={"mf-chg " + tone(ch.pct)}>{ch.abs > 0 ? "+" : ch.abs < 0 ? "−" : ""}₹{nf(Math.abs(ch.abs), 4)} ({pctText(ch.pct)}) <small className="muted">vs NAV of {ch.since ? dateIN(ch.since) : "the previous day"}</small></span>
            : <span className="muted">Previous NAV not on file yet, so no day change is shown.</span>}
          <div className="mf-acts">
            <button className={"btn" + (inTray ? " on" : "")} aria-pressed={inTray} onClick={() => { if (!toggle(d.code)) toast(`You can compare up to ${TRAY_MAX} schemes at a time.`); }}><Icon name="compare" />{inTray ? "Chosen to compare" : "Add to compare"}</button>
            {tray.length >= 2 && <button className="btn primary" onClick={() => nav(compareUrl(tray))}>Compare {tray.length}</button>}
          </div>
        </div>
      </header>

      {!d.active && <p className="mf-note warn" role="note"><Icon name="alert" /><span>This scheme has stopped publishing NAVs{d.navDate ? `; its last NAV is dated ${dateIN(d.navDate)}` : ""}. Matured, merged and closed schemes stay in AMFI's file.</span></p>}
      {d.history.source === "mirror" && <p className="mf-note" role="note"><Icon name="info" /><span>{d.history.note}. AMFI's own history for this scheme is not loaded yet; the mirror's newest NAV was checked against AMFI's.</span></p>}

      {d.optionClass !== "Growth" && (() => {
        const g = d.family.find((f) => f.optionClass === "Growth" && f.plan === d.plan && f.active) || d.family.find((f) => f.optionClass === "Growth" && f.active);
        return g ? <p className="mf-note" role="note"><Icon name="info" /><span>Returns are shown for the Growth option of this fund: <Link to={`/funds/${g.code}`}>{g.name}</Link>.</span></p> : null;
      })()}
      <ReturnsBlock d={d} />
      <NavChart key={d.code} d={d} />
      <div className="mf-grid">
        <FactsCard facts={facts.data} loading={facts.isLoading} failed={facts.isError} />
        <Risk d={d} />
      </div>
      <HoldingsSection portfolio={portfolio.data} title="What it invests in" unit="fund" />

      {d.family.length > 0 && (
        <div className="card mf-card">
          <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>Other plans and options of this fund</h3></div>
          <div className="tw"><table className="mf-fam">
            <thead><tr><th scope="col">Plan and option</th><th scope="col">NAV</th><th scope="col">NAV date</th><th scope="col"><span className="sr-only">Compare</span></th></tr></thead>
            <tbody>{d.family.map((f) => (
              <tr key={f.code}>
                <th scope="row"><Link to={`/funds/${f.code}`}>{f.name}</Link><small><PlanChip plan={f.plan} option={f.option} />{!f.active && <span className="chip ghost">Stopped publishing</span>}</small></th>
                <td className="num">{navText(f.nav)}</td><td className="num">{f.navDate ? dateIN(f.navDate) : "—"}</td>
                <td className="num"><Link className="mf-linkbtn" to={compareUrl([d.code, f.code])}>Compare with this</Link></td>
              </tr>))}</tbody>
          </table></div>
          <p className="faint mf-fine">Plans of one fund hold the same investments but charge different costs, so their NAVs and returns differ. Compare Direct with Direct and Regular with Regular.</p>
        </div>)}

      <div className="mf-grid">
        <div className="card mf-card">
          <div className="card-h"><h3><span className="ci"><Icon name="notes" /></span>About the data</h3></div>
          <ul className="mf-facts">
            <li><span>NAV history on file</span><b>{d.history.points ? `${d.history.points.toLocaleString("en-IN")} daily NAVs, ${dateIN(d.history.from!)} to ${dateIN(d.history.to!)}` : "None yet"}</b></li>
            <li><span>History source</span><b>{d.history.source === "amfi" ? "AMFI's official NAV history" : d.history.source === "mirror" ? "Third-party mirror of AMFI data (api.mfapi.in)" : "—"}</b></li>
            <li><span>Latest NAV source</span><b>AMFI NAVAll file</b></li>
          </ul>
        </div>
      </div>
      <Foot facts={d} history={d.history} />
    </div>
  );
}

// ================================================================================================ compare

const RANGE_BUTTONS: RangeKey[] = ["1M", "6M", "1Y", "3Y", "5Y", "MAX"];

function Picker({ ids, onAdd }: { ids: number[]; onAdd: (code: number) => void }) {
  const [text, setText] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = window.setTimeout(() => setDebounced(text.trim()), 300); return () => window.clearTimeout(t); }, [text]);
  const res = useFundList({ ...EMPTY_QUERY, q: debounced.length >= 2 ? debounced : "", size: 25, option: "Growth" });
  const show = debounced.length >= 2 ? (res.data?.items || []) : [];
  return (
    <div className="mf-picker">
      <label className="mf-search"><Icon name="search" /><span className="sr-only">Find a scheme to add</span>
        <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a scheme: type its name, e.g. axis large cap direct" autoComplete="off" disabled={ids.length >= TRAY_MAX} /></label>
      {ids.length >= TRAY_MAX && <p className="faint">You are comparing the most schemes this page can show ({TRAY_MAX}). Remove one to add another.</p>}
      {show.length > 0 && (
        <ul className="mf-results" aria-label="Matching schemes">{show.map((r) => (
          <li key={r.code}><span><b>{r.name}</b><small>{shortAmc(r.amc)} · <PlanChip plan={r.plan} option={r.option} /></small></span>
            <button className="btn" disabled={ids.includes(r.code)} onClick={() => { onAdd(r.code); setText(""); }}>{ids.includes(r.code) ? "Added" : "Add"}</button></li>))}</ul>)}
      {debounced.length >= 2 && !res.isFetching && !show.length && <p className="muted">No Growth-option scheme matches “{debounced}”. Returns are compared for Growth options.</p>}
    </div>
  );
}

function CompareTable({ funds }: { funds: CompareFund[] }) {
  const notes: string[] = [];
  const mark = (why: string | null | undefined, who: string) => { if (!why) return null; const text = `${who}: ${why}`; let i = notes.indexOf(text); if (i < 0) { notes.push(text); i = notes.length - 1; } return String.fromCharCode(97 + (i % 26)); };
  const val = (v: number | null, why: string | null, who: string, o: { d?: number; plain?: boolean; plus?: boolean } = {}) => {
    if (v != null) return <Fig v={v} d={o.d ?? 2} plain={o.plain} plus={o.plus} />;
    const m = mark(why, who);
    return <span className="mf-na" aria-label={`No figure. ${why || ""}`}>—{m && <sup>{m}</sup>}</span>;
  };
  const rows: { label: React.ReactNode; cell: (f: CompareFund) => React.ReactNode; head?: boolean }[] = [
    { label: "Fund house", cell: (f) => shortAmc(f.amc) }, { label: "Category", cell: (f) => categoryShort(f.category) },
    { label: "Plan and option", cell: (f) => <PlanChip plan={f.plan} option={f.option} /> },
    { label: <GTerm id="net-asset-value-nav">Latest NAV</GTerm>, cell: (f) => <>{navText(f.nav)}<small className="muted"> {f.navDate ? dateIN(f.navDate, { day: "numeric", month: "short" }) : ""}</small></> },
    { label: "Returns", head: true, cell: () => null },
    { label: RETURN_LABELS.d1, cell: (f) => val(f.change?.pct ?? null, f.active ? "The previous NAV is not on file yet." : "Stopped publishing NAVs.", shortName(f) + ", 1 day") },
    { label: RETURN_LABELS.y1, cell: (f) => val(f.returns["1y"].value, f.returns["1y"].why, shortName(f) + ", 1 year") },
    { label: RETURN_LABELS.y5, cell: (f) => val(f.returns["5y"].value, f.returns["5y"].why, shortName(f) + ", 5 year") },
    { label: "Risk", head: true, cell: () => null },
    { label: <><GTerm id="volatility">Volatility</GTerm> 1 year</>, cell: (f) => val(f.risk.vol1y.value, f.risk.vol1y.why, shortName(f) + ", volatility 1 year", { plain: true, plus: false }) },
    { label: <><GTerm id="volatility">Volatility</GTerm> 3 years</>, cell: (f) => val(f.risk.vol3y.value, f.risk.vol3y.why, shortName(f) + ", volatility 3 years", { plain: true, plus: false }) },
    { label: <><GTerm id="drawdown">Largest fall</GTerm></>, cell: (f) => val(f.risk.maxDrawdown.value, f.risk.maxDrawdown.why, shortName(f) + ", largest fall", { plus: false }) },
    { label: "NAV history", cell: (f) => (f.history.source === "amfi" ? "AMFI" : f.history.source === "mirror" ? "Mirror of AMFI data" : "Not loaded") },
  ];
  const body = rows.map((r, i) => r.head ? <tr key={i} className="mf-grp"><th scope="colgroup" colSpan={funds.length + 1}>{r.label}</th></tr>
    : <tr key={i}><th scope="row">{r.label}</th>{funds.map((f) => <td key={f.code}>{r.cell(f)}</td>)}</tr>);
  return (
    <>
      <div className="tw"><table className="mf-cmp">
        <caption className="sr-only">Side-by-side comparison of the chosen schemes</caption>
        <thead><tr><th scope="col"><span className="sr-only">Measure</span></th>{funds.map((f, i) => (
          <th scope="col" key={f.code}><i className="mf-sw" style={{ borderColor: SERIES_STYLE[i].color, borderTopStyle: i === 0 ? "solid" : i === 1 ? "dashed" : "dotted" }} aria-hidden="true" /><Link to={`/funds/${f.code}`}>{f.name}</Link></th>))}</tr></thead>
        <tbody>{body}</tbody>
      </table></div>
      {notes.length > 0 && <ol className="mf-notes faint" aria-label="Why some figures are blank">{notes.map((n, i) => <li key={i} value={i + 1}><sup>{String.fromCharCode(97 + (i % 26))}</sup> {n}</li>)}</ol>}
    </>
  );
}
const shortName = (f: CompareFund) => (f.name.length > 40 ? f.name.slice(0, 38) + "…" : f.name);

/** /funds/compare: the head-to-head Fund Compare by default; the 2 to 4 scheme compare when the address has ?ids= (also empty, from its link). */
export function FundComparePage() {
  const [sp] = useSearchParams();
  return sp.has("ids") ? <FundMultiCompare /> : <FundHeadToHead />;
}

function FundMultiCompare() {
  useDocTitle("Compare mutual funds", "Put 2 to 4 mutual fund schemes side by side: NAV, returns, risk and a rebased NAV chart. Information only.");
  const { toast } = useUI();
  const [sp, setSp] = useSearchParams();
  const ids = useMemo(() => parseIds(sp.get("ids")), [sp]);
  const rangeParam = sp.get("range");
  const range: RangeKey = RANGE_BUTTONS.includes(rangeParam as RangeKey) ? (rangeParam as RangeKey) : "1Y";
  const [tray] = useTray();
  const { data, error, isFetching, refetch } = useFundCompare(ids, range);
  const put = (next: number[], r: RangeKey = range) => setSp((() => { const p = new URLSearchParams(); p.set("ids", next.join(",")); if (r !== "1Y") p.set("range", r); return p; })(), { replace: true });

  return (
    <>
      {HEAD("Mutual funds, side by side.", "Put two to four schemes next to each other: NAV, returns, risk and a chart that starts every fund at 100. Information only.")}
      <div className="wrap mf">
        <div className="card mf-card mf-setup">
          <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>Schemes to compare</h3>
            {ids.length >= 2 && <button className="btn" onClick={() => { navigator.clipboard?.writeText(location.href).then(() => toast("Link to this comparison copied."), () => toast(location.href)); }}><Icon name="spark" />Copy link</button>}</div>
          {ids.length > 0 && (
            <ul className="mf-chosen" aria-label="Chosen schemes">{ids.map((c, i) => { const f = data?.funds.find((x) => x.code === c); return (
              <li key={c}><i className="mf-sw" style={{ borderColor: SERIES_STYLE[i].color, borderTopStyle: i === 0 ? "solid" : i === 1 ? "dashed" : "dotted" }} aria-hidden="true" /><span>{f ? f.name : `Scheme ${c}`}</span>
                <button className="mf-x" aria-label={`Remove ${f ? f.name : c}`} onClick={() => put(ids.filter((x) => x !== c))}>×</button></li>); })}</ul>)}
          <Picker ids={ids} onAdd={(c) => put([...ids, c])} />
          {ids.length < 2 && (
            <div className="pm-empty mf-empty"><b>Choose at least two schemes.</b>
              <p>Search above, or tick “compare” boxes on the <Link to="/funds">scheme list</Link> and press Compare.</p>
              {tray.length >= 2 && <button className="btn primary" onClick={() => put(tray)}>Compare the {tray.length} you chose in the list</button>}
              <p><Link to="/funds/compare">Or compare two funds of one category head to head</Link>: returns, risk, consistency and costs, against the category average.</p></div>)}
        </div>

        {ids.length >= 2 && error && !data && <Problem title="This comparison is unavailable right now" text={(error as { status?: number }).status === 404 ? "One of these schemes could not be found." : "Please try again in a moment."} retry={() => refetch()} />}
        {ids.length >= 2 && !data && !error && <div className="card" aria-busy="true"><div className="skeleton" style={{ height: 360 }} /></div>}
        {ids.length >= 2 && data && (
          <>
            <div className="card mf-card" aria-busy={isFetching}>
              <div className="card-h"><h3><span className="ci"><Icon name="line" /></span>NAV, every scheme starting at 100</h3>
                <div className="seg" role="group" aria-label="Chart range">{RANGE_BUTTONS.map((k) => <button key={k} aria-pressed={k === range} onClick={() => put(ids, k)}>{k === "MAX" ? "Since launch" : k}</button>)}</div></div>
              {data.chart ? (
                <>
                  <FundChart base={100} format={(v) => nf(v, 1)} label={`NAV of the chosen schemes, rebased to 100 on ${dateIN(data.chart.from)}`}
                    series={data.chart.series.map((s) => ({ key: String(s.code), label: shortName(data.funds.find((f) => f.code === s.code)!), t: s.t, v: s.v }))} />
                  <p className="faint mf-fine">Each line starts at 100 on {dateIN(data.chart.from)} (the latest start date among the schemes for this range) and follows that scheme's NAV. It is a picture of past NAVs, not a forecast.</p>
                </>) : <p className="muted mf-pad">{data.chartNote}</p>}
            </div>
            <div className="card mf-card"><div className="card-h"><h3><span className="ci"><Icon name="table" /></span>The numbers</h3></div><CompareTable funds={data.funds} />
              <p className="faint mf-fine">1 year is the total change in NAV over the year; 5 year is a yearly rate (CAGR), not the five-year total. Only Growth options have returns, because payouts change the NAV of IDCW options. Different plans of one fund differ only by cost. Fund size, costs and holdings are on each scheme's own page.</p></div>
            {data.funds.some((f) => f.history.source === "mirror") && <p className="mf-note" role="note"><Icon name="info" /><span>Some NAV history here comes from a third-party mirror of AMFI data (api.mfapi.in), after its newest NAV was checked against AMFI's.</span></p>}
            <Foot facts={data} history={data.funds.find((f) => f.history.source === "mirror")?.history} />
          </>)}
        {ids.length < 2 && <Foot facts={null} />}
      </div>
    </>
  );
}
