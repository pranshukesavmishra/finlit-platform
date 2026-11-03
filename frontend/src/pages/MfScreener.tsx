// /funds/screener: the Mutual Fund Screener. A left panel of filters (a bottom sheet on narrow screens), preset screens, the active filters as removable chips,
// a sort menu, two small graphics and a table. Every count comes from the server in one call (/api/mf/filters?screen=1); the list is /api/mf?extra=true.
// Information only: figures describe past data, nothing here says what to do. Plan: free.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { PageHeader } from "../components/PageHeader";
import { Toolbar } from "../components/screener/PageParts";
import { Icon } from "../lib/icons";
import { nf, dateIN } from "../lib/format";
import { useFocusTrap } from "../lib/focusTrap";
import { loadUi, saveUi, isBool } from "../lib/persist";
import { DISCLAIMER } from "../lib/mf";
import { DEMO } from "../lib/demo";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import {
  DEFAULTS, PAGE_SIZE, PRESETS, chipsFor, isDefault, loadSaved, parseQuery, presetOn, queryToParams, storeSaved, useScreenFacets, useScreenList, type Saved, type SQ,
} from "../lib/mfScreen";
import { SORTS } from "../lib/mfScreenDefs";
import { FlowBars, RiskReturn } from "../mf/screen/Graphics";
import { Panel } from "../mf/screen/Panel";
import { ResultTable } from "../mf/screen/Results";
import "../styles/fgx.css";
import "../styles/mf.css";
import "../styles/mfscreen.css";

const narrow = () => typeof window !== "undefined" && !!window.matchMedia && window.matchMedia("(max-width: 900px)").matches;

export function MfScreenerPage() {
  const { has } = useUI();
  const [sp, setSp] = useSearchParams();
  const q = useMemo(() => parseQuery(sp), [sp]);
  const list = useScreenList(q), facets = useScreenFacets(q);
  const fac = facets.data?.screen;
  const [text, setText] = useState(q.q);
  const [sheet, setSheet] = useState(false), [panelOpen, setPanelOpen] = useState(() => loadUi("mfscreen.panel", 1, isBool, true)), [glance, setGlance] = useState(() => loadUi("mfscreen.glance", 1, isBool, true));
  const [saved, setSaved] = useState<Saved[]>(loadSaved);
  const sideRef = useRef<HTMLElement>(null);
  const total = list.data?.total ?? 0, pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const title = "Mutual Fund Screener";
  useDocTitle(title, "Screen every Indian mutual fund and ETF by type, category, fund house, plan, size, returns, cost, risk, portfolio and what its category is doing. Free. Information only.");

  const set = (fn: (s: SQ) => SQ) => setSp(queryToParams(fn(q)), { replace: true });
  const go = (patch: Partial<SQ>) => setSp(queryToParams({ ...q, ...patch }), { replace: !("page" in patch) });
  useEffect(() => { if (text.trim() === q.q) return; const t = window.setTimeout(() => set((s) => ({ ...s, q: text.trim(), page: 1 })), 350); return () => window.clearTimeout(t); }, [text]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setText(q.q); }, [q.q]);
  useEffect(() => { if (!sheet) return; const k = (e: KeyboardEvent) => e.key === "Escape" && setSheet(false); document.addEventListener("keydown", k); const o = document.body.style.overflow; document.body.style.overflow = "hidden"; return () => { document.removeEventListener("keydown", k); document.body.style.overflow = o; }; }, [sheet]);
  useFocusTrap(sideRef, sheet);
  useEffect(() => { const m = window.matchMedia?.("(min-width: 901px)"); const f = () => m?.matches && setSheet(false); m?.addEventListener?.("change", f); return () => m?.removeEventListener?.("change", f); }, []);

  const subLabel = (k: string) => fac?.subs.find((s) => s.key === k)?.label ?? k.replace(/-/g, " ");
  const tagLabel = (k: string) => fac?.tags.find((t) => t.tag === k)?.label ?? k;
  const chips = chipsFor(q, subLabel, tagLabel);
  const shown = chips.length;
  const sortVal = `${q.sort}:${q.dir}`;
  const onSort = (key: string) => go({ sort: key, dir: q.sort === key ? (q.dir === "asc" ? "desc" : "asc") : (key === "name" || key === "ter" || key === "fall" || key === "rank3y" || key === "gap" || key === "worst" || key === "negshare" || key === "downdev" ? "asc" : "desc"), page: 1 });
  const showPanel = () => { if (narrow()) setSheet(true); else { setPanelOpen(true); saveUi("mfscreen.panel", 1, true); } };
  const togglePanel = () => { if (narrow()) setSheet(true); else { setPanelOpen(!panelOpen); saveUi("mfscreen.panel", 1, !panelOpen); } };
  const reset = () => setSp(new URLSearchParams(), { replace: true });
  const saveScreen = () => {
    const name = window.prompt("Name this screen (kept in this browser only)", "")?.trim().slice(0, 40);
    if (!name) return;
    const next = [{ name, query: queryToParams(q).toString() }, ...saved.filter((s) => s.name !== name)].slice(0, 8);
    setSaved(next); storeSaved(next);
  };
  const dropSaved = (name: string) => { const next = saved.filter((s) => s.name !== name); setSaved(next); storeSaved(next); };
  const sorts = SORTS.filter((s) => !s.gold || has("gold"));
  const noMatch = !list.isLoading && !list.isError && total === 0;
  const loadingNow = list.isFetching || facets.isFetching;
  const where = fac && fac.built.rows > 0 ? fac.built : null;

  return (
    <div className="wrap mf mfs-page">
      <PageHeader plan="free" title={title} art="funds" links={["/funds", "/fund-score-screener", "/funds/compare", "/funds/insights"]} learn={false}
        description="Filter every mutual fund and ETF by type, category, fund house, plan, size, returns, cost, risk, portfolio and what its category is doing. Counts beside every choice, a histogram under every slider. Information only, not investment advice."
        stats={[{ icon: "layers", value: list.data ? nf(total, 0) : null, label: "Funds match" }, { icon: "calendar", value: list.data?.dataDate ? dateIN(list.data.dataDate, { day: "numeric", month: "short", year: "numeric" }) : null, label: "NAV data date" }]} />

      {DEMO && <p className="mfs-demo" role="note"><Icon name="info" /> Preview build: the real AMFI NAVs and returns of 67 schemes are shown, but expense ratio, fund size, SIP, risk, portfolio and category figures here are sample values for layout only.</p>}
      <section className="mfs-presets" aria-label="Preset screens">
        <span className="mfs-pl">Preset screens</span>
        <div className="mfs-prow">
          {PRESETS.map((p) => { const on = presetOn(q, p); return (
            <button key={p.id} type="button" className={"fgx-chip mfs-preset" + (on ? " is-on" : "")} aria-pressed={on} disabled={!!p.off} title={p.off ?? p.say}
              onClick={() => (on ? reset() : setSp(queryToParams(p.set(DEFAULTS)), { replace: false }))}>{on && <i aria-hidden="true">&#10003;</i>}{p.label}{p.off && <Icon name="lock" />}</button>); })}
          {saved.map((s) => (
            <span key={s.name} className="mfs-saved"><button type="button" className="fgx-chip" onClick={() => setSp(new URLSearchParams(s.query))} title="A screen you saved in this browser">{s.name}</button>
              <button type="button" className="mfs-x" aria-label={`Delete the saved screen ${s.name}`} onClick={() => dropSaved(s.name)}>×</button></span>))}
        </div>
        <p className="fgx-note">Presets are plain starting points: they set filters you can change. They describe past figures and do not recommend any fund.</p>
      </section>

      <Toolbar q={text} setQ={setText} searchLabel="Search by fund or fund house, e.g. hdfc mid cap" buttons={panelOpen && !narrow() ? [] : [{ id: "filters", label: "Filters", active: shown, onClick: showPanel }]}
        sort={<label className="fgx-sort"><span className="sr-only">Sort by</span>
          <select aria-label="Sort by" value={sortVal} onChange={(e) => { const [k, d] = e.target.value.split(":"); go({ sort: k, dir: d as "asc" | "desc", page: 1 }); }}>
            {!sorts.some((s) => `${s.v}:${s.dir}` === sortVal) && <option value={sortVal}>Sorted by column</option>}
            {sorts.map((s) => <option key={s.v + s.dir} value={`${s.v}:${s.dir}`}>{s.v === "aum" && s.dir === "desc" ? "No sort: default order (fund size, largest first)" : `Sort: ${s.label}`}</option>)}</select></label>} />

      <div className={"mfs-layout" + (panelOpen ? "" : " is-collapsed") + (sheet ? " is-sheet" : "")}>
        {sheet && <div className="mfs-back" onClick={() => setSheet(false)} aria-hidden="true" />}
        <aside ref={sideRef} className="card mfs-side" aria-label="Filters" role={sheet ? "dialog" : undefined} aria-modal={sheet ? true : undefined} hidden={!panelOpen && !sheet}>
          <div className="mfs-grab" aria-hidden="true" />
          <div className="mfs-sh-top">
            <span className="mfs-sh-t">Filters{shown > 0 ? ` · ${shown} active` : ""}</span>
            <span className="fgx-tl">{!isDefault(q) && <button type="button" className="fgx-link" onClick={reset}>Reset</button>}
              <button type="button" className="mfs-hide" onClick={() => (sheet ? setSheet(false) : togglePanel())}>{sheet ? "Close" : "Hide filters"}</button></span>
          </div>
          <Panel q={q} set={set} fac={fac} waiting={facets.isFetching && !fac} canScore={has("gold")} />
          <div className="mfs-foot"><button type="button" className="btn primary" onClick={() => setSheet(false)}>Show {list.data ? nf(total, 0) : ""} fund{total === 1 ? "" : "s"}</button>
            <button type="button" className="btn" onClick={reset} disabled={isDefault(q)}>Reset</button></div>
        </aside>

        <section className="card mfs-main" aria-label="Results">
          <div className="mfs-bar">
            <p className="mf-count" role="status" aria-live="polite">{list.isLoading ? "Loading funds…" : list.isError ? "Could not load the funds." : <><b>{nf(total, 0)}</b> fund{total === 1 ? "" : "s"}{list.data?.dataDate ? <> · NAV data of {dateIN(list.data.dataDate)}</> : null}{loadingNow && !list.isLoading ? <span className="mfs-busy"> · updating…</span> : null}</>}</p>
            <span className="mfs-bar-b"><button type="button" className="btn sm mfs-open" onClick={showPanel}><Icon name="panel" /> Filters{shown > 0 && <span className="dotn">{shown}</span>}</button></span>
          </div>

          <div className="mfs-active" aria-label="Active filters">
            {chips.length === 0 ? <span className="faint">Default view: Direct plan, Growth option, funds still publishing, mutual funds and ETFs together. Choose a filter on the left.</span>
              : <>{chips.map((c) => <button key={c.id} type="button" className="fchip" onClick={() => set((s) => c.clear(s))} aria-label={`Remove filter: ${c.label}`}>{c.label} <span aria-hidden="true">×</span></button>)}
                <button type="button" className="fgx-link" onClick={reset}>Reset</button>
                <button type="button" className="fgx-link" onClick={saveScreen}>Save screen</button></>}
          </div>

          <div className="mfs-glance-h">
            <button type="button" className="mfs-gl-t" aria-expanded={glance} onClick={() => { setGlance(!glance); saveUi("mfscreen.glance", 1, !glance); }}><Icon name="line" /> Result at a glance<span className="mfs-chev" aria-hidden="true">{glance ? "−" : "+"}</span></button>
          </div>
          {glance && (
            <div className="mfs-glance">
              <div><h3>Return against risk</h3><RiskReturn data={fac?.scatter} /></div>
              <div><h3>Where the money is moving</h3><p className="faint">Net flow of the categories in the result, last six months (AMFI). Industry figures, not about any one fund.</p><FlowBars flows={fac?.flows} /></div>
            </div>)}

          {list.isError ? <div className="state" role="alert"><h2>Could not load the funds</h2><p>The fund data did not answer. <button className="btn" onClick={() => list.refetch()}>Try again</button></p></div>
            : noMatch ? <div className="mfs-empty" role="status"><h2>No fund passes all these filters</h2>
              <p>{chips.length ? "Remove a filter to widen the result:" : "There are no funds to show."}</p>
              <div>{chips.slice(0, 8).map((c) => <button key={c.id} type="button" className="fchip" onClick={() => set((s) => c.clear(s))}>{c.label} <span aria-hidden="true">×</span></button>)}</div>
              <button type="button" className="btn" onClick={reset}>Reset all filters</button></div>
              : <ResultTable rows={list.data?.items ?? []} q={q} onSort={onSort} loading={list.isFetching} />}

          {pages > 1 && (
            <nav className="mfs-pages" aria-label="Pages">
              <button className="btn sm" disabled={q.page <= 1} onClick={() => go({ page: q.page - 1 })}>Previous</button>
              <span>Page {q.page} of {nf(pages, 0)}</span>
              <button className="btn sm" disabled={q.page >= pages} onClick={() => go({ page: q.page + 1 })}>Next</button>
            </nav>)}

          <footer className="mfs-fine faint" aria-label="How to read this page">
            <p><b>{DISCLAIMER}</b> The figures describe past data; they are not a recommendation.</p>
            <p>Risk figures use month-end NAVs up to the last full month; ranks and “against category” compare funds of the same category and plan and need at least three funds with a figure. A dash means the fund has no figure: the reason is in its tooltip, and the “N of M funds have this figure” line under each slider counts them.
              {where && <> Screener figures worked out {where.run ? dateIN(where.run) : ""}{where.portfolioDate ? `; portfolios as of ${dateIN(where.portfolioDate)}` : ""}.</>}
              {fac && fac.built.rows === 0 && <> The nightly job that works out risk, ranks, portfolio and category figures has not run yet, so those filters show “no data”.</>}
              {" "}Source: AMFI and each fund house's own disclosures. <Link to="/funds">All schemes</Link> · <Link to="/funds/insights">Fund industry trends</Link></p>
          </footer>
        </section>
      </div>
    </div>
  );
}
