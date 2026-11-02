// The Mutual Fund Screener's filter panel: collapsible groups with an "n active" badge, checkbox lists and chips with the count beside every value,
// and numeric filters (histogram + slider + typed boxes + quick ranges + "N of M funds have this figure"). It only edits the query; the page asks the server.
// Groups the spec lists but whose data we do not hold are drawn at the bottom as "Needs a data source", disabled, with the reason: never hidden, never faked.
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Icon } from "../../lib/icons";
import { nf } from "../../lib/format";
import { isBoolMap, loadUi, saveUi } from "../../lib/persist";
import { CheckRow, FilterGroup, SearchBox } from "../../components/screener/FilterGroup";
import {
  AUMRANK_OPTS, BASIS_OPTS, CAP_OPTS, CFLOW_OPTS, CHK_EACH, COMING, CSIZE_OPTS, CSTREAK_OPTS, EXIT_OPTS, FRESH_OPTS, HOUSE_OPTS, INST_OPTS, MAT_OPTS, NUM_BY, OPTION_OPTS, PFDATE_OPTS,
  PLAN_OPTS, RK_BANDS, STATUS_OPTS, STRUCT_OPTS, STYLE_OPTS, TAG_KIND_LABEL, TICK_DATA, TICK_FALL, TICK_LISTS, TYPE_OPTS, type Opt,
} from "../../lib/mfScreenDefs";
import { DEFAULTS, rangeOf, toggleIn, useStockSearch, withRange, type SQ, type ScreenFacets } from "../../lib/mfScreen";
import { FlowBars } from "./Graphics";
import { RangeFilter } from "./RangeFilter";

export type PanelProps = { q: SQ; set: (fn: (q: SQ) => SQ) => void; fac?: ScreenFacets; waiting: boolean; canScore: boolean };

// ------------------------------------------------------------------------------------------------ small pieces

/** Toggle chips with a count each. `any` adds a leading "All" chip that clears the selection. */
function Chips({ opts, sel, counts, onToggle, label, any }: { opts: Opt[]; sel: string[]; counts?: Record<string, number>; onToggle: (v: string) => void; label: string; any?: () => void }) {
  return (
    <div className="fgx-chips mfs-chips" role="group" aria-label={label}>
      {any && <button type="button" className={"fgx-chip" + (sel.length === 0 ? " is-on" : "")} aria-pressed={sel.length === 0} onClick={any}>{sel.length === 0 && <i aria-hidden="true">&#10003;</i>}All</button>}
      {opts.map((o) => { const on = sel.includes(o.v), n = counts?.[o.v]; return (
        <button key={o.v} type="button" className={"fgx-chip" + (on ? " is-on" : "") + (n === 0 && !on ? " is-zero" : "")} aria-pressed={on} title={o.hint} onClick={() => onToggle(o.v)}>
          {on && <i aria-hidden="true">&#10003;</i>}{o.label}{n != null && <small>{nf(n, 0)}</small>}</button>); })}
    </div>);
}
function Opts({ opts, sel, counts, onToggle, label }: { opts: Opt[]; sel: string[]; counts?: Record<string, number>; onToggle: (v: string) => void; label: string }) {
  return <ul className="fgx-list mfs-opts" aria-label={label}>{opts.map((o) => <li key={o.v}><CheckRow label={<>{o.label}{o.hint && <small className="mfs-sub">{o.hint}</small>}</>} count={counts?.[o.v] ?? null} checked={sel.includes(o.v)} onChange={() => onToggle(o.v)} disabled={counts?.[o.v] === 0 && !sel.includes(o.v)} /></li>)}</ul>;
}
const Sub = ({ children }: { children: ReactNode }) => <h4 className="mfs-sh">{children}</h4>;
const Tabs = ({ items, value, onPick, label }: { items: { v: string; label: string; off?: boolean }[]; value: string; onPick: (v: string) => void; label: string }) => (
  <div className="mfs-tabs" role="group" aria-label={label}>{items.map((t) => <button key={t.v} type="button" aria-pressed={value === t.v} disabled={t.off} onClick={() => onPick(t.v)}>{t.label}</button>)}</div>);

type Fig = { field: string; label: string; tabs?: { v: string; label: string; field: string }[]; firstTab?: boolean };
/** The three calendar years the nightly run works out: the years before the run's year (the same years for every fund). */
const calendarFig = (run: string | null | undefined): Fig => {
  const y = Number((run ?? "").slice(0, 4)) || new Date().getFullYear();
  return { field: "", label: "Calendar year", firstTab: true, tabs: [1, 2, 3].map((i) => ({ v: "cy" + i, label: String(y - i), field: "cy" + i })) };
};
const RETURN_FIGS: Fig[] = [
  { field: "", label: "Return", tabs: [{ v: "1y", label: "1Y", field: "r1y" }, { v: "3y", label: "3Y", field: "r3y" }, { v: "5y", label: "5Y", field: "r5y" }] },
  { field: "", label: "SIP return (XIRR)", tabs: [{ v: "3y", label: "3Y", field: "sip3y" }, { v: "5y", label: "5Y", field: "sip5y" }] },
  { field: "", label: "Against category median", tabs: [{ v: "1y", label: "1Y", field: "ex1y" }, { v: "3y", label: "3Y", field: "ex3y" }, { v: "5y", label: "5Y", field: "ex5y" }] },
  { field: "", label: "Short-term change", tabs: [{ v: "1d", label: "1 day", field: "r1d" }, { v: "1m", label: "1M", field: "r1m" }, { v: "6m", label: "6M", field: "r6m" }] },
  calendarFig(null),   // the panel relabels the tabs with the years of the latest run
  { field: "up_m", label: "Biggest monthly gain" },
  { field: "consist", label: "Months ahead of peers" },
];
const RISK_FIGS: Fig[] = [
  { field: "", label: "Volatility", tabs: [{ v: "1y", label: "1Y", field: "vol1" }, { v: "3y", label: "3Y", field: "vol3" }] },
  { field: "vol_rel", label: "Volatility vs category" }, { field: "down_dev", label: "Downside deviation" },
  { field: "fall", label: "Biggest fall" }, { field: "worst_m", label: "Worst month" }, { field: "worst_12m", label: "Worst 12 months" }, { field: "neg_share", label: "Months with a fall" },
  { field: "below_high", label: "Time below high" }, { field: "down_cap", label: "Downside capture" }, { field: "sharpe", label: "Sharpe ratio" },
];
const PORT_FIGS: Fig[] = [{ field: "eq_pct", label: "Equity" }, { field: "debt_pct", label: "Debt" }, { field: "cash_pct", label: "Cash" }, { field: "other_pct", label: "Other" }];
const COST_FIGS: Fig[] = [{ field: "ter", label: "Expense ratio" }, { field: "ter_rel", label: "Against category" }, { field: "ter_gap", label: "Regular − Direct" }, { field: "fee_share", label: "Fee share of return" }, { field: "exit_pct", label: "Exit load %" }];
const MARKET_FIGS: Fig[] = [{ field: "cf_aum_mom", label: "Net assets, month" }, { field: "cf_aum_yoy", label: "Net assets, year" }, { field: "cf_folio_mom", label: "Folios, month" }, { field: "cf_share", label: "Share of industry" }];
const fieldsOf = (figs: Fig[]) => figs.flatMap((f) => (f.tabs ? f.tabs.map((t) => t.field) : [f.field]));

function useUiState<T>(key: string, init: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => loadUi(key, 1, (d) => (d && typeof d === "object" ? (d as T) : null), init));
  return [v, (n: T) => { setV(n); saveUi(key, 1, n); }];
}

// ------------------------------------------------------------------------------------------------ the panel

export function Panel({ q, set, fac, waiting, canScore }: PanelProps) {
  const [open, setOpenMap] = useState<Record<string, boolean>>(() => loadUi("mfscreen.groups", 1, isBoolMap, {}));
  const og = (id: string) => ({ open: open[id], onOpenChange: (o: boolean) => { const n = { ...open, [id]: o }; setOpenMap(n); saveUi("mfscreen.groups", 1, n); } });
  const upd = (p: Partial<SQ>) => set((s) => ({ ...s, ...p, page: 1 }));
  const tog = <K extends keyof SQ>(k: K) => (v: string) => upd({ [k]: toggleIn(q[k] as string[], v) } as Partial<SQ>);
  const rf = (field: string, hideHead = false) => {
    const def = NUM_BY[field]; const [lo, hi] = rangeOf(q, field);
    return <RangeFilter key={field} def={def} hist={fac?.numeric[field]} lo={lo} hi={hi} nodata={q.nd.includes(field)} waiting={waiting} builtRows={fac?.built.rows} hideHead={hideHead}
      onRange={(a, b) => set((s) => withRange(s, field, a, b))} onNodata={(on) => set((s) => ({ ...s, nd: on ? [...s.nd.filter((f) => f !== field), field] : s.nd.filter((f) => f !== field), page: 1 }))} />;
  };
  const nr = (fields: string[]) => fields.filter((f) => f in q.rng).length;
  const [fig, setFig] = useUiState<Record<string, string>>("mfscreen.figs", {});
  /** A group whose chips pick the figure the slider works on, and whose tabs pick the period (spec section 1). */
  const figured = (id: string, figs: Fig[], tabLabel = "Period") => {
    const cur = figs.find((f) => f.label === fig[id]) ?? figs[0];
    const tab = cur.tabs ? (cur.tabs.find((t) => t.v === fig[id + ":t"]) ?? cur.tabs[cur.firstTab ? 0 : Math.min(1, cur.tabs.length - 1)]) : null;
    const field = tab ? tab.field : cur.field;
    return (
      <>
        <div className="fgx-chips mfs-chips" role="group" aria-label="Which figure the slider works on">
          {figs.map((f) => { const on = f.label === cur.label, act = fieldsOf([f]).some((x) => x in q.rng); return (
            <button key={f.label} type="button" className={"fgx-chip" + (on ? " is-on" : "") + (act && !on ? " has-set" : "")} aria-pressed={on} onClick={() => setFig({ ...fig, [id]: f.label })}>{on && <i aria-hidden="true">&#10003;</i>}{f.label}{act && <b className="mfs-dot" aria-label="has a range set" />}</button>); })}
        </div>
        {cur.tabs && <Tabs label={tabLabel} value={tab!.v} items={cur.tabs.map((t) => ({ v: t.v, label: t.label }))} onPick={(v) => setFig({ ...fig, [id + ":t"]: v })} />}
        {rf(field)}
      </>);
  };

  const subsAll = fac?.subs ?? [];
  const [subQ, setSubQ] = useState(""), [showAllSubs, setShowAllSubs] = useState(false), [houseQ, setHouseQ] = useState(""), [showAllHouses, setShowAllHouses] = useState(false);
  const [stock, setStock] = useState("");
  const stocks = useStockSearch(stock.trim());
  const subs = useMemo(() => subsAll.filter((s) => (!q.group || s.tab === q.group) && s.label.toLowerCase().includes(subQ.trim().toLowerCase())), [subsAll, q.group, subQ]);
  const subRows = showAllSubs || subQ ? subs : subs.slice(0, 12);
  const houses = useMemo(() => (fac?.amcs ?? []).filter((a) => a.name.toLowerCase().includes(houseQ.trim().toLowerCase())), [fac, houseQ]);
  const houseRows = showAllHouses || houseQ ? houses : houses.slice(0, 10);
  const tagsBy = useMemo(() => { const m: Record<string, ScreenFacets["tags"]> = {}; for (const t of fac?.tags ?? []) (m[t.kind] ||= []).push(t); return m; }, [fac]);
  const short = (n: string) => n.replace(/\s*mutual fund\s*$/i, "");
  const subLabel = (k: string) => subsAll.find((s) => s.key === k)?.label ?? k;
  const typeCounts = fac?.type ?? {};

  return (
    <div className="mfs-panel">
      {/* ----- type and category */}
      <FilterGroup id="type" title="Type and category" defaultOpen active={(q.group ? 1 : 0) + q.subs.length + q.cap.length + q.style.length + q.struct.length + q.mat.length} {...og("type")}>
        <Tabs label="Type" value={q.group} onPick={(v) => upd({ group: v === q.group ? "" : v, subs: v === q.group ? q.subs : [] })}
          items={[{ v: "", label: "All" }, ...TYPE_OPTS.map((t) => ({ v: t.v, label: `${t.label}${fac ? ` ${nf(typeCounts[t.v] ?? 0, 0)}` : ""}`, off: (typeCounts[t.v] ?? 1) === 0 && q.group !== t.v }))]} />
        <Sub>Sub-category</Sub>
        <SearchBox value={subQ} onChange={setSubQ} placeholder="Search sub-category" label="Search sub-categories" />
        <ul className="fgx-list mfs-opts" aria-label="Sub-categories">
          {subRows.map((s) => <li key={s.key}><CheckRow label={s.label} count={s.n} checked={q.subs.includes(s.key)} onChange={() => upd({ subs: toggleIn(q.subs, s.key) })} disabled={s.n === 0 && !q.subs.includes(s.key)} /></li>)}
          {q.subs.filter((k) => !subs.some((s) => s.key === k)).map((k) => <li key={k}><CheckRow label={subLabel(k)} count={0} checked onChange={() => upd({ subs: toggleIn(q.subs, k) })} /></li>)}
          {!subs.length && <li className="fgx-none">{fac ? (subQ ? `No sub-category matches “${subQ}”.` : "No sub-category in this result.") : "Loading…"}</li>}
        </ul>
        {!subQ && subs.length > 12 && <button type="button" className="fgx-link mfs-all" onClick={() => setShowAllSubs(!showAllSubs)}>{showAllSubs ? "Show fewer" : `Show all ${subs.length}`}</button>}
        <Sub>Cap size</Sub>
        <Chips opts={CAP_OPTS} sel={q.cap} counts={fac?.cap} onToggle={tog("cap")} label="Cap size" />
        <Sub>Investment style</Sub>
        <Chips opts={STYLE_OPTS} sel={q.style} counts={fac?.style} onToggle={tog("style")} label="Investment style" />
        <Sub>Scheme structure</Sub>
        <Opts opts={STRUCT_OPTS} sel={q.struct} counts={fac?.struct} onToggle={tog("struct")} label="Scheme structure" />
        {(q.group === "" || q.group === "debt") && (<>
          <Sub>Debt maturity band <small className="mfs-tag">category band</small></Sub>
          <p className="fgx-note">The band SEBI sets for the category, not the fund's measured duration (which is not in our data).</p>
          <Chips opts={MAT_OPTS} sel={q.mat} counts={fac?.mat} onToggle={tog("mat")} label="Debt maturity band of the category" />
        </>)}
      </FilterGroup>

      {/* ----- fund house */}
      <FilterGroup id="house" title="Fund house" active={q.amcs.length + q.house.length} {...og("house")}>
        <SearchBox value={houseQ} onChange={setHouseQ} placeholder="Search fund house" label="Search fund houses" />
        <ul className="fgx-list mfs-opts" aria-label="Fund houses">
          {houseRows.map((a) => <li key={a.name}><CheckRow label={short(a.name)} count={a.n} checked={q.amcs.includes(a.name)} onChange={() => upd({ amcs: toggleIn(q.amcs, a.name) })} disabled={a.n === 0 && !q.amcs.includes(a.name)} /></li>)}
          {q.amcs.filter((n) => !houses.some((a) => a.name === n)).map((n) => <li key={n}><CheckRow label={short(n)} count={0} checked onChange={() => upd({ amcs: toggleIn(q.amcs, n) })} /></li>)}
          {!houses.length && <li className="fgx-none">{fac ? `No fund house matches “${houseQ}”.` : "Loading…"}</li>}
        </ul>
        {!houseQ && houses.length > 10 && <button type="button" className="fgx-link mfs-all" onClick={() => setShowAllHouses(!showAllHouses)}>{showAllHouses ? "Show fewer" : `Show all ${houses.length}`}</button>}
        <Sub>Fund house size</Sub>
        <p className="fgx-note">All the house's funds together (each scheme counted once); understated where a scheme has no size.</p>
        <Chips opts={HOUSE_OPTS} sel={q.house} counts={fac?.house} onToggle={tog("house")} label="Fund house size" />
      </FilterGroup>

      {/* ----- plan, option, status */}
      <FilterGroup id="plan" title="Plan, option and status" defaultOpen active={(q.plans.join() !== DEFAULTS.plans.join() ? 1 : 0) + (q.options.join() !== DEFAULTS.options.join() ? 1 : 0) + q.inst.length + (q.status !== "active" ? 1 : 0) + (q.family ? 1 : 0) + (q.fresh ? 1 : 0)} {...og("plan")}>
        <Sub>Plan</Sub>
        <Chips opts={PLAN_OPTS} sel={q.plans} counts={fac?.plans} onToggle={tog("plans")} label="Plan" any={() => upd({ plans: [] })} />
        <Sub>Option</Sub>
        <Chips opts={OPTION_OPTS} sel={q.options} counts={fac?.options} onToggle={tog("options")} label="Option" any={() => upd({ options: [] })} />
        <p className="fgx-note">IDCW and Other options have no return figures by design: they drop out while a returns filter is set.</p>
        <Sub>Instrument</Sub>
        <Chips opts={INST_OPTS} sel={q.inst} counts={fac?.inst} onToggle={tog("inst")} label="Instrument" />
        <Sub>Status</Sub>
        <Chips opts={STATUS_OPTS} sel={q.status === "both" ? ["active", "stopped"] : [q.status]} counts={fac?.status} label="Status"
          onToggle={(v) => { const cur = new Set(q.status === "both" ? ["active", "stopped"] : [q.status]); cur.has(v) ? cur.delete(v) : cur.add(v); upd({ status: cur.size === 2 || cur.size === 0 ? "both" : (cur.has("stopped") ? "stopped" : "active") }); }} />
        <Sub>Data freshness</Sub>
        <Chips opts={FRESH_OPTS} sel={q.fresh ? [q.fresh] : []} counts={fac?.fresh} onToggle={(v) => upd({ fresh: q.fresh === v ? "" : v })} label="Data freshness" />
        <Sub>Family view</Sub>
        <CheckRow label="One row per fund family (plans and options collapsed)" checked={q.family} onChange={() => upd({ family: !q.family })} />
      </FilterGroup>

      {/* ----- size and age */}
      <FilterGroup id="size" title="Size and age" active={nr(["aum", "age", "aum_share", "na_chg"]) + q.aumbasis.length + q.aumrank.length + (q.launchFrom || q.launchTo ? 1 : 0)} {...og("size")}>
        {rf("aum")}
        <Sub>Size basis</Sub>
        <Chips opts={BASIS_OPTS} sel={q.aumbasis} counts={fac?.aumbasis} onToggle={tog("aumbasis")} label="Size basis" />
        <Sub>Rank by size inside its category</Sub>
        <Chips opts={AUMRANK_OPTS} sel={q.aumrank} counts={fac?.aumrank} onToggle={tog("aumrank")} label="Rank by size inside the category" />
        <Sub>Share of its category's size</Sub>{rf("aum_share", true)}
        <Sub>Net assets, change over the stored month-ends</Sub>{rf("na_chg", true)}
        <Sub>Age</Sub>{rf("age", true)}
        <Sub>Launch date</Sub>
        <div className="mfs-dates" role="group" aria-label="Launch date range">
          <label>From<input type="date" value={q.launchFrom} max={q.launchTo || undefined} onChange={(e) => upd({ launchFrom: e.target.value })} /></label>
          <label>To<input type="date" value={q.launchTo} min={q.launchFrom || undefined} onChange={(e) => upd({ launchTo: e.target.value })} /></label>
        </div>
        <p className="fgx-note">A few schemes have no launch date from AMFI; they are left out while a date is set.</p>
      </FilterGroup>

      {/* ----- returns */}
      <FilterGroup id="returns" title="Returns" active={nr(fieldsOf(RETURN_FIGS)) + q.rk.length + (q.tick.includes("has_hist3") ? 1 : 0) + (q.tick.includes("has_hist5") ? 1 : 0)} {...og("returns")}>
        {figured("ret", RETURN_FIGS.map((f) => (f.label === "Calendar year" ? calendarFig(fac?.built.run) : f)))}
        <Sub>Rank inside its category</Sub>
        {(["1y", "3y", "5y"] as const).map((p) => (
          <div key={p} className="mfs-rkrow"><span>{p.replace("y", " year")}</span>
            <Chips opts={RK_BANDS} sel={q.rk.filter((r) => r.startsWith(p + ":")).map((r) => r.slice(3))} onToggle={(b) => upd({ rk: toggleIn(q.rk, `${p}:${b}`) })} label={`Rank inside the category, ${p}`} /></div>))}
        <p className="fgx-note">Rank among funds of the same category and plan; needs at least three funds with a figure. Q1 is the top quarter.</p>
        <Sub>Track record</Sub>
        <CheckRow label="Has a 3-year return" count={fac?.tick.has_hist3 ?? null} checked={q.tick.includes("has_hist3")} onChange={() => upd({ tick: toggleIn(q.tick, "has_hist3") })} />
        <CheckRow label="Has a 5-year return" count={fac?.tick.has_hist5 ?? null} checked={q.tick.includes("has_hist5")} onChange={() => upd({ tick: toggleIn(q.tick, "has_hist5") })} />
      </FilterGroup>

      {/* ----- cost */}
      <FilterGroup id="cost" title="Cost" active={nr(fieldsOf(COST_FIGS)) + q.exit.length} {...og("cost")}>
        {figured("cost", COST_FIGS)}
        <Sub>Exit load</Sub>
        <p className="fgx-note">Read from the fund house's wording; about three in four funds have a readable text.</p>
        <Chips opts={EXIT_OPTS} sel={q.exit} counts={fac?.exit} onToggle={tog("exit")} label="Exit load" />
      </FilterGroup>

      {/* ----- risk */}
      <FilterGroup id="risk" title="Risk" active={nr(fieldsOf(RISK_FIGS)) + q.tick.filter((t) => TICK_FALL.some((o) => o.v === t)).length} {...og("risk")}>
        <p className="fgx-hint">All figures come from month-end NAVs up to the last full month, so every fund is on the same ruler.</p>
        {figured("risk", RISK_FIGS)}
        <Sub>Quick ticks</Sub>
        <Opts opts={TICK_FALL} sel={q.tick} counts={fac?.tick} onToggle={tog("tick")} label="Quick risk ticks" />
      </FilterGroup>

      {/* ----- portfolio */}
      <FilterGroup id="portfolio" title="Portfolio" active={nr([...fieldsOf(PORT_FIGS), "n_hold", "top10", "max_hold"]) + (q.sector ? 1 : 0) + (q.holds ? 1 : 0) + q.pfdate.length} {...og("portfolio")}>
        <p className="fgx-hint">From each fund house's monthly portfolio file (latest month-end). {fac ? <>Funds of houses with no parsed file ({nf(fac.portfolio.none ?? 0, 0)} in this result) have no value here and are shown in the “no data” count, never as zero.</> : null}</p>
        <Sub>Asset split</Sub>
        {figured("port", PORT_FIGS)}
        <Sub>Number of holdings</Sub>{rf("n_hold", true)}
        <Sub>Top-10 concentration</Sub>{rf("top10", true)}
        <Sub>Largest single holding</Sub>{rf("max_hold", true)}
        <Sub>Sector exposure</Sub>
        <label className="mfs-sel"><span className="sr-only">Sector</span>
          <select value={q.sector} onChange={(e) => upd({ sector: e.target.value, sectorMin: e.target.value ? q.sectorMin || "10" : "" })}>
            <option value="">Any sector</option>
            {(fac?.sectors ?? []).map((s) => <option key={s.name} value={s.name}>{s.name} ({s.n})</option>)}
            {q.sector && !(fac?.sectors ?? []).some((s) => s.name === q.sector) && <option value={q.sector}>{q.sector}</option>}
          </select></label>
        {q.sector && <div className="mfs-mm"><span>at least</span><input className="mfs-box" inputMode="decimal" aria-label="Minimum share of net assets in the sector" value={q.sectorMin} onChange={(e) => upd({ sectorMin: e.target.value.replace(/[^0-9.]/g, "").slice(0, 5) })} /><span>% of net assets</span></div>}
        <Sub>Holds this stock</Sub>
        <SearchBox value={stock} onChange={(v) => setStock(v.toUpperCase())} placeholder="NSE symbol, e.g. RELIANCE" label="Find a stock held by funds" />
        {stock.trim().length >= 2 && stocks.data && (
          <ul className="fgx-list mfs-opts" aria-label="Stocks found">
            {stocks.data.items.map((s) => <li key={s.isin}><CheckRow label={s.symbol} count={s.families} checked={q.holds === s.symbol} onChange={() => { upd({ holds: q.holds === s.symbol ? "" : s.symbol }); setStock(""); }} /></li>)}
            {!stocks.data.items.length && <li className="fgx-none">No fund holds a stock that starts with “{stock}”.</li>}
          </ul>)}
        {q.holds && <p className="fgx-note">Showing funds that hold <b>{q.holds}</b> in their latest portfolio. <button type="button" className="fgx-link" onClick={() => upd({ holds: "" })}>Clear</button></p>}
        <Sub>Portfolio date</Sub>
        <Chips opts={PFDATE_OPTS} sel={q.pfdate} counts={fac?.portfolio} onToggle={tog("pfdate")} label="Portfolio date" />
      </FilterGroup>

      {/* ----- theme, sector, strategy, index */}
      <FilterGroup id="tags" title="Theme, sector and strategy" active={q.tags.length} {...og("tags")}>
        <p className="fgx-hint">Tags come from the scheme name (and, for sector themes, from where the portfolio is invested). They are our own editable table, reviewed {fac ? "from time to time" : ""}; a fund can carry more than one.{fac && fac.built.rows > 0 && <> {nf(fac.built.tagged, 0)} funds carry a tag; {nf(fac.built.indexTagged, 0)} passive funds have an index name read from their name.</>}</p>
        {Object.keys(TAG_KIND_LABEL).map((kind) => {
          const rows = (tagsBy[kind] ?? []).filter((t) => t.n > 0 || q.tags.includes(t.tag));
          return rows.length ? (<div key={kind}><Sub>{TAG_KIND_LABEL[kind]}</Sub>
            <ul className="fgx-list mfs-opts" aria-label={TAG_KIND_LABEL[kind]}>{rows.map((t) => <li key={t.tag}><CheckRow label={t.label} count={t.n} checked={q.tags.includes(t.tag)} onChange={() => upd({ tags: toggleIn(q.tags, t.tag) })} /></li>)}</ul></div>) : null;
        })}
        {fac && !fac.tags.some((t) => t.n > 0) && <p className="fgx-note">No tagged fund in this result{fac.built.rows === 0 ? ": the nightly job that works tags out has not run yet" : ""}.</p>}
      </FilterGroup>

      {/* ----- the category's market view */}
      <FilterGroup id="market" title="Category market view" active={nr(fieldsOf(MARKET_FIGS)) + q.cflow.length + q.cstreak.length + q.csize.length} {...og("market")}>
        <p className="fgx-hint">What the fund's whole category is doing, from AMFI's monthly category report{fac?.built.flowMonth ? ` (${fac.built.flowMonth.slice(0, 7)})` : ""}. It says nothing about the fund itself.</p>
        <Sub>Category net flow, last month</Sub>
        <Chips opts={CFLOW_OPTS} sel={q.cflow} counts={fac?.cflow} onToggle={tog("cflow")} label="Category net flow, last month" />
        <Sub>Inflow streak</Sub>
        <Chips opts={CSTREAK_OPTS} sel={q.cstreak} counts={fac?.cstreak} onToggle={tog("cstreak")} label="Category inflow streak" />
        <Sub>Category size</Sub>
        <Chips opts={CSIZE_OPTS} sel={q.csize} counts={fac?.csize} onToggle={tog("csize")} label="Category size" />
        {figured("mkt", MARKET_FIGS)}
        <Sub>Net flow of the categories in this result</Sub>
        <FlowBars flows={fac?.flows} />
      </FilterGroup>

      {/* ----- the checklist */}
      <FilterGroup id="checklist" title="FinLit checklist" active={(q.chk ? 1 : 0) + q.chkEach.length} {...og("checklist")}>
        <p className="fgx-hint">Five plain checks against funds of the same category and plan. It sums up past figures; it is not a rating.</p>
        <Chips opts={[{ v: "5", label: "5 of 5" }, { v: "4", label: "4 or more" }, { v: "3", label: "3 or more" }]} sel={q.chk ? [q.chk] : []} counts={fac?.chk} onToggle={(v) => upd({ chk: q.chk === v ? "" : v })} label="Checks passed" />
        <Sub>Each check</Sub>
        <Opts opts={CHK_EACH} sel={q.chkEach} counts={fac?.chk_each} onToggle={tog("chkEach")} label="Each check" />
      </FilterGroup>

      {/* ----- data quality and lists */}
      <FilterGroup id="quality" title="Data quality and lists" active={q.tick.filter((t) => [...TICK_DATA, ...TICK_LISTS].some((o) => o.v === t && t !== "has_hist3" && t !== "has_hist5")).length} {...og("quality")}>
        <Opts opts={TICK_DATA.filter((o) => o.v !== "has_hist3" && o.v !== "has_hist5")} sel={q.tick} counts={fac?.tick} onToggle={tog("tick")} label="Data quality" />
        <Sub>Lists</Sub>
        <Opts opts={TICK_LISTS} sel={q.tick} counts={fac?.tick} onToggle={tog("tick")} label="Lists" />
      </FilterGroup>

      {/* ----- what is not built */}
      <FilterGroup id="soon" title="Needs a data source" meta={<span className="mfs-soon-n">{COMING.length}</span>} {...og("soon")}>
        <p className="fgx-hint">These filters are planned and are shown here so nothing is hidden. Each waits for data we do not hold yet; none is simulated.</p>
        <ul className="mfs-soon" aria-label="Filters that need a data source">
          {COMING.map((c) => (
            <li key={c.id} aria-disabled="true"><span className="mfs-lock" aria-hidden="true"><Icon name="lock" /></span>
              <div><b>{c.label}</b><small>{c.why}</small><small className="mfs-route">Free route: {c.route}</small>
                {c.id === "score" && canScore && <Link className="fgx-link" to="/fund-score-screener">Open the Fund score screener</Link>}</div></li>))}
        </ul>
      </FilterGroup>
    </div>
  );
}
