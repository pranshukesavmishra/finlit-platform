import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { PageArt } from "../components/PageArt";
import { Plain } from "../components/Plain";
import { Icon } from "../lib/icons";
import { nf, MINUS } from "../lib/format";
import { apiUrl } from "../lib/api";
import { limitsFor } from "../lib/auth";
import { READY, UNIT_SUFFIX, activeCount, decodeState, encodeState, fmtMetric, norm, toBody, useCatalog, useScreen, type Catalog, type MetricInfo, type PState, type Range } from "../lib/proscreen";
import { screens, useSavedScreens } from "../lib/screens";
import { saveFile } from "../stock/derive";
import { useDocTitle } from "../lib/title";
import { TIER, useUI, type Plan } from "../lib/ui";

const TIER_ORDER: Plan[] = ["basic", "silver", "gold"];
const PAGE = 50;
const MAX_COLS = 12;
const VISIBLE_GROUPS = 9;

const useDebounced = <T,>(v: T, ms: number) => { const [d, setD] = useState(v); useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]); return d; };

/** One numeric filter: min and max, with where most companies sit as the hint. Yes/no filters are a three-way switch. */
function FilterRow({ m, r, set, locked, ask }: { m: MetricInfo; r: Range; set: (r: Range) => void; locked: boolean; ask: () => void }) {
  const [info, setInfo] = useState(false);
  const st = m.stats, sfx = UNIT_SUFFIX[m.unit] ?? "";
  const hint = (v: number) => nf(v, Math.abs(v) >= 100 ? 0 : m.digits > 1 ? 2 : 1);
  const num = (raw: string) => (raw === "" ? undefined : Number.isFinite(Number(raw)) ? Number(raw) : undefined);
  if (m.unit === "flag") {
    const v = r.min === 1 ? "yes" : r.max === 0 ? "no" : "any";
    return (
      <div className={"scr-f" + (locked ? " is-locked" : "")}>
        <div className="scr-fl"><span>{m.label}</span>{locked ? <button className="pl-tier" onClick={ask}><Icon name="lock" />{TIER[m.tier].n}</button> : <button className="pl-i" aria-label="What this means" aria-expanded={info} onClick={() => setInfo(!info)}><Icon name="info" /></button>}</div>
        {info && <p className="pl-say">{m.say}</p>}
        <div className="pm-seg" role="group" aria-label={m.label}>{(["any", "yes", "no"] as const).map((o) => <button key={o} aria-pressed={v === o} onClick={() => (locked ? ask() : set(o === "any" ? {} : o === "yes" ? { min: 1 } : { max: 0 }))}>{o === "any" ? "Any" : o === "yes" ? "Yes" : "No"}</button>)}</div>
      </div>
    );
  }
  return (
    <div className={"scr-f" + (locked ? " is-locked" : "")}>
      <div className="scr-fl"><span>{m.label}</span>{locked ? <button className="pl-tier" onClick={ask}><Icon name="lock" />{TIER[m.tier].n}</button> : <button className="pl-i" aria-label={`What ${m.label} means`} aria-expanded={info} onClick={() => setInfo(!info)}><Icon name="info" /></button>}</div>
      {info && <p className="pl-say">{m.say}{m.better !== "none" ? ` ${m.better === "higher" ? "Higher" : "Lower"} is usually better.` : ""}</p>}
      <div className="scr-fi">
        <input type="number" inputMode="decimal" placeholder={st ? `Min ${hint(st.p10)}` : "Min"} value={r.min ?? ""} disabled={locked} onChange={(e) => set({ ...r, min: num(e.target.value) })} aria-label={`${m.label} minimum`} />
        <span>to</span>
        <input type="number" inputMode="decimal" placeholder={st ? `Max ${hint(st.p90)}` : "Max"} value={r.max ?? ""} disabled={locked} onChange={(e) => set({ ...r, max: num(e.target.value) })} aria-label={`${m.label} maximum`} />
      </div>
      {st && !locked && <small className="pl-typ">Most companies: {hint(st.p10)}{sfx} to {hint(st.p90)}{sfx}</small>}
    </div>
  );
}

function Checks({ items, picked, toggle, search }: { items: { key: string; label: string; n: number; sub?: string | null }[]; picked: string[]; toggle: (k: string) => void; search?: boolean }) {
  const [q, setQ] = useState(""), [all, setAll] = useState(false);
  const shown = items.filter((i) => !q.trim() || i.label.toLowerCase().includes(q.trim().toLowerCase()));
  const list = all || q ? shown : shown.slice(0, 12);
  return (
    <>
      {search && items.length > 8 && <label className="scr-find sm" style={{ margin: "0 0 6px" }}><Icon name="search" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search" aria-label="Search this list" /></label>}
      <ul className="scr-sec">{list.map((i) => <li key={i.key}><label><input type="checkbox" checked={picked.includes(i.key)} onChange={() => toggle(i.key)} /><span>{i.label}</span><em>{i.n}</em></label></li>)}
        {!list.length && <li className="faint">Nothing matches.</li>}</ul>
      {!q && shown.length > 12 && <button className="alx-link" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${shown.length}`}</button>}
    </>
  );
}

export function ScreenerPro() {
  useDocTitle("Stock screener", "Filter every listed Indian stock with 160+ filters: valuation, profitability, growth, quarterly results, financial health, ownership, red flags and trend. Gold adds FinLit model filters.");
  const { upgrade, toast, plan: uiPlan } = useUI();
  const nav = useNavigate();
  const cat = useCatalog();
  const [params, setParams] = useSearchParams();
  const init = useRef(decodeState(params.get("s")));
  const [f, setF] = useState<PState>(init.current.state);
  const [sort, setSort] = useState({ key: init.current.sort || "market_cap", dir: (init.current.dir || "desc") as "asc" | "desc" });
  const [cols, setCols] = useState<string[] | null>(null);
  const [q, setQ] = useState(""), [page, setPage] = useState(0);
  const [tab, setTab] = useState<"filters" | "quick">("filters");
  const [find, setFind] = useState(""), [open, setOpen] = useState<Record<string, boolean>>({ valuation: true });
  const [moreGroups, setMoreGroups] = useState(false), [colMenu, setColMenu] = useState(false), [colFind, setColFind] = useState(""), [saveName, setSaveName] = useState("");
  const saved = useSavedScreens();
  const data = cat.data;
  const plan: Plan = data?.plan ?? "basic";
  const byKey = useMemo(() => new Map((data?.groups || []).flatMap((g) => g.metrics.map((m) => [m.key, m] as const))), [data]);
  const columns = cols ?? data?.defaultColumns ?? [];
  const ask = (tier: Plan, why: string) => upgrade(tier, why);

  const dq = useDebounced(f, 250), dsort = useDebounced(sort, 0), dqq = useDebounced(q, 250);
  useEffect(() => setPage(0), [dq, dsort, dqq]);
  const body = useMemo(() => toBody(dq, dsort, columns, dqq, page * PAGE, PAGE), [dq, dsort, columns, dqq, page]);
  const res = useScreen(body, !!data && columns.length > 0);
  const rows = res.data?.rows || [];
  const nActive = activeCount(f);

  // keep the address bar in step so a screen can be shared
  useEffect(() => { const s = encodeState(dq, dsort.key, dsort.dir); const n = new URLSearchParams(params); s ? n.set("s", s) : n.delete("s"); if (n.toString() !== params.toString()) setParams(n, { replace: true }); }, [dq, dsort]); // eslint-disable-line react-hooks/exhaustive-deps

  const setRange = (k: string, r: Range) => setF((s) => { const ranges = { ...s.ranges }; if (r.min == null && r.max == null) delete ranges[k]; else ranges[k] = r; return { ...s, ranges }; });
  const toggle = (key: "sectors" | "industries" | "indices" | "caps" | "bands", v: string) => setF((s) => ({ ...s, [key]: s[key].includes(v) ? s[key].filter((x) => x !== v) : [...s[key], v] }));
  const fl = find.trim().toLowerCase();

  const sortBy = (key: string) => setSort((s) => (s.key === key ? { key, dir: s.dir === "desc" ? "asc" : "desc" } : { key, dir: key === "name" || byKey.get(key)?.better === "lower" ? "asc" : "desc" }));
  const toggleCol = (k: string) => { const cur = columns; if (cur.includes(k)) setCols(cur.filter((x) => x !== k)); else if (cur.length >= MAX_COLS) toast(`Up to ${MAX_COLS} columns at a time.`); else setCols([...cur, k]); };

  const chips: { label: string; clear: () => void }[] = [
    ...Object.entries(f.ranges).map(([k, r]) => { const m = byKey.get(k); return { label: m?.unit === "flag" ? `${m.label}: ${r.min === 1 ? "Yes" : "No"}` : `${m?.label || k} ${r.min != null ? "≥ " + r.min : ""}${r.min != null && r.max != null ? " and " : ""}${r.max != null ? "≤ " + r.max : ""}`, clear: () => setRange(k, {}) }; }),
    ...f.sectors.map((s) => ({ label: s, clear: () => toggle("sectors", s) })), ...f.industries.map((s) => ({ label: s, clear: () => toggle("industries", s) })),
    ...f.indices.map((s) => ({ label: data?.indices.find((i) => i.code === s)?.label || s, clear: () => toggle("indices", s) })), ...f.caps.map((s) => ({ label: `${s} cap`, clear: () => toggle("caps", s) })),
    ...f.bands.map((s) => ({ label: `FinLit band: ${s}`, clear: () => toggle("bands", s) })),
  ];

  const apply = (s: Partial<PState>, label: string) => { const n = norm(s); setF(n); if (n.sort) setSort({ key: n.sort, dir: n.dir || "desc" }); if (n.cols?.length) setCols(n.cols); setTab("filters"); toast(`Applied: ${label}.`); };
  const save = () => {
    const n = saveName.trim(); if (!n || !nActive) { toast("Add a filter and a name first."); return; }
    const max = limitsFor(uiPlan).screens; if (saved.length >= max && !saved.some((s) => s.name === n)) { toast(`Your plan keeps up to ${max} screens. Remove one first.`); return; }
    screens.save(n, { ...f, sort: sort.key, dir: sort.dir, cols: columns } as never, max); setSaveName(""); toast(`Saved “${n}”. You can find it under Quick screens.`);
  };
  const exportCsv = async () => {
    if (!data?.limits.export) { ask("silver", "Downloading results comes with the Silver plan."); return; }
    try {
      const r = await fetch(apiUrl("/api/screener/export"), { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", Accept: "text/csv" }, body: JSON.stringify(toBody(f, sort, columns, q, 0, 100)) });
      if (!r.ok) throw new Error(String(r.status));
      saveFile("FinLit-screen.csv", await r.text(), "text/csv;charset=utf-8"); toast("Saved your results as FinLit-screen.csv.");
    } catch { toast("We could not prepare the download. Please try again."); }
  };

  const ordered = [...(data?.groups || [])].sort((a, b) => Number(b.id === "model") - Number(a.id === "model"));   // the FinLit model group leads: it is what Gold adds
  const groups = ordered.filter((g) => !fl || g.label.toLowerCase().includes(fl) || g.metrics.some((m) => m.label.toLowerCase().includes(fl) || m.key.includes(fl)));
  const listed = fl || moreGroups ? groups : groups.slice(0, VISIBLE_GROUPS);
  const facetOpen = (id: string) => !!(open[id] || fl);
  const facetMatch = (label: string) => !fl || label.toLowerCase().includes(fl);
  const heat = useMemo(() => {
    const out: Record<string, [number, number]> = {};
    for (const k of res.data?.columns || []) { const v = rows.map((r) => r.v[k]).filter((x): x is number => x != null).sort((a, b) => a - b); if (v.length > 6) out[k] = [v[Math.floor(v.length * 0.25)], v[Math.floor(v.length * 0.75)]]; }
    return out;
  }, [rows, res.data?.columns]);
  const tone = (k: string, v: number | null) => { const m = byKey.get(k), h = heat[k]; if (v == null || !m || !h || m.better === "none" || m.unit === "flag" || h[0] === h[1]) return ""; const good = m.better === "higher" ? v >= h[1] : v <= h[0], bad = m.better === "higher" ? v <= h[0] : v >= h[1]; return good ? "hg" : bad ? "hb" : ""; };
  const err = res.error as { status?: number; body?: { plan?: string; detail?: string } } | null;
  const total = res.data?.total ?? 0;

  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="research" />
        <div className="eyebrow">Stock screener</div><h1>Find the companies that fit your rules.</h1>
        <p>{data ? nf(data.total, 0) : "Every listed"} companies and {data ? data.groups.reduce((a, g) => a + g.metrics.length, 0) : "160+"} filters, from valuation and quarterly results to ownership and red flags. {plan !== "gold" && "Gold adds filters built on the FinLit research model. "}Prefer a simpler start? Try the <Link to="/score-screener">Score screener</Link>.</p></div></section>
      <div className="wrap scr-wrap">
        <div className="scr">
          <aside className="scr-side card" aria-label="Filters">
            <div className="seg scr-tabs" role="tablist"><button role="tab" aria-selected={tab === "filters"} onClick={() => setTab("filters")}>Filters{nActive ? <i className="dotn">{nActive}</i> : null}</button><button role="tab" aria-selected={tab === "quick"} onClick={() => setTab("quick")}>Quick screens</button></div>
            {tab === "filters" ? (
              <>
                <label className="scr-find"><Icon name="search" /><input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Search for a filter, e.g. ROE or promoter" aria-label="Search for a filter" /></label>
                {cat.isLoading && <div className="skeleton" style={{ height: 320, marginTop: 12 }} />}
                {cat.isError && <div className="state"><p>The filters are not available right now. Please try again in a moment.</p><button className="btn" onClick={() => cat.refetch()}>Try again</button></div>}
                <div className="scr-groups">
                  {listed.map((g) => {
                    const isOpen = facetOpen(g.id), model = g.id === "model", allLocked = g.metrics.every((m) => m.locked);
                    const shownMetrics = fl ? g.metrics.filter((m) => m.label.toLowerCase().includes(fl) || g.label.toLowerCase().includes(fl)) : g.metrics;
                    const n = Object.keys(f.ranges).filter((k) => g.metrics.some((m) => m.key === k)).length;
                    return (
                      <div key={g.id} className={"scr-g" + (model ? " is-model" : "")}>
                        <button className="scr-gh" aria-expanded={isOpen} onClick={() => setOpen((o) => ({ ...o, [g.id]: !o[g.id] }))}>
                          <span>{g.label}{model && <span className="tier gold" style={{ marginLeft: 8 }}><Icon name="crown" />Gold</span>}{n > 0 && <i className="dotn" style={{ marginLeft: 8 }}>{n}</i>}</span><span className="scr-n">{g.metrics.length}</span><Icon name="arrow" />
                        </button>
                        {isOpen && (
                          <div className="scr-gb">
                            {g.id === "size" && data && <div className="scr-bands" role="group" aria-label="Company size">{data.caps.map((c) => <button key={c.name} className={"bandc" + (f.caps.includes(c.name) ? " on" : "")} aria-pressed={f.caps.includes(c.name)} onClick={() => toggle("caps", c.name)}>{c.name} cap <small>{c.n}</small></button>)}</div>}
                            {model && (
                              allLocked ? <div className="scr-lock"><span className="lk"><Icon name="lock" /></span><b>Filter by the FinLit model</b><p>The FinLit score, its band and each of the five pillars (Quality, Growth, Profitability, Balance sheet, Technical), plus how the score has moved.</p>
                                <button className="btn primary" onClick={() => ask("gold", "FinLit model filters come with the Gold plan.")}>Unlock with Gold</button></div>
                              : <div className="scr-bands" role="group" aria-label="FinLit band">{(data?.bands || []).map((b) => <button key={b.key} className={"bandc " + b.key} aria-pressed={f.bands.includes(b.key)} onClick={() => toggle("bands", b.key)}>{b.label}</button>)}</div>
                            )}
                            {!(model && allLocked) && shownMetrics.map((m) => <FilterRow key={m.key} m={m} r={f.ranges[m.key] || {}} set={(r) => setRange(m.key, r)} locked={m.locked} ask={() => ask(m.tier, `${m.label} is part of the ${TIER[m.tier].n} plan.`)} />)}
                          </div>)}
                      </div>);
                  })}
                  {!fl && groups.length > VISIBLE_GROUPS && <button className="alx-link" style={{ margin: "10px 0 4px" }} onClick={() => setMoreGroups(!moreGroups)}>{moreGroups ? "Show fewer categories" : `Show ${groups.length - VISIBLE_GROUPS} more categories`}</button>}
                  {data && facetMatch("Sector") && (
                    <div className="scr-g"><button className="scr-gh" aria-expanded={facetOpen("sector")} onClick={() => setOpen((o) => ({ ...o, sector: !o.sector }))}><span>Sector{f.sectors.length > 0 && <i className="dotn" style={{ marginLeft: 8 }}>{f.sectors.length}</i>}</span><span className="scr-n">{data.sectors.length}</span><Icon name="arrow" /></button>
                      {facetOpen("sector") && <div className="scr-gb"><Checks search items={data.sectors.map((s) => ({ key: s.name, label: s.name, n: s.n }))} picked={f.sectors} toggle={(k) => toggle("sectors", k)} /></div>}</div>)}
                  {data && facetMatch("Industry") && (
                    <div className="scr-g"><button className="scr-gh" aria-expanded={facetOpen("industry")} onClick={() => setOpen((o) => ({ ...o, industry: !o.industry }))}><span>Industry{f.industries.length > 0 && <i className="dotn" style={{ marginLeft: 8 }}>{f.industries.length}</i>}</span><span className="scr-n">{data.industries.length}</span><Icon name="arrow" /></button>
                      {facetOpen("industry") && <div className="scr-gb"><Checks search items={data.industries.map((s) => ({ key: s.name, label: s.name, n: s.n }))} picked={f.industries} toggle={(k) => toggle("industries", k)} /></div>}</div>)}
                  {data && data.indices.length > 0 && facetMatch("Index") && (
                    <div className="scr-g"><button className="scr-gh" aria-expanded={facetOpen("index")} onClick={() => setOpen((o) => ({ ...o, index: !o.index }))}><span>Index{f.indices.length > 0 && <i className="dotn" style={{ marginLeft: 8 }}>{f.indices.length}</i>}</span><span className="scr-n">{data.indices.length}</span><Icon name="arrow" /></button>
                      {facetOpen("index") && <div className="scr-gb"><Checks items={data.indices.map((s) => ({ key: s.code, label: s.label, n: s.n }))} picked={f.indices} toggle={(k) => toggle("indices", k)} /></div>}</div>)}
                </div>
                <div className="scr-save"><div className="scr-sh"><span>Save as a screen</span><button className="lnk" onClick={() => { setF(norm({})); toast("Filters cleared."); }}>Reset all</button></div>
                  <div className="scr-sr"><input value={saveName} onChange={(e) => setSaveName(e.target.value)} placeholder="Name this screen" aria-label="Screen name" maxLength={40} onKeyDown={(e) => e.key === "Enter" && save()} /><button className="btn" onClick={save}>Save</button></div></div>
              </>
            ) : (
              <div className="scr-quick">
                {saved.length > 0 && <><div className="label">My screens</div>{saved.map((s) => <div key={s.name} className="qs-row"><button className="qs" onClick={() => apply(s.state as Partial<PState>, s.name)}><b>{s.name}</b><span>{activeCount(norm(s.state as Partial<PState>))} filters</span></button><button className="qs-x" aria-label={`Delete ${s.name}`} onClick={() => screens.remove(s.name)}>×</button></div>)}</>}
                {TIER_ORDER.map((t) => { const items = READY.filter((s) => s.tier === t); return items.length ? (
                  <div key={t}><div className="label">{t === "basic" ? "Ready-made screens" : t === "silver" ? "Silver screens" : "Gold screens, built on the FinLit model"}</div>
                    {items.map((s) => { const lock = !TIER_ORDER.slice(0, TIER_ORDER.indexOf(plan) + 1).includes(s.tier); return (
                      <button key={s.id} className={"qs" + (lock ? " lock" : "")} onClick={() => lock ? ask(s.tier, `“${s.label}” is part of the ${TIER[s.tier].n} plan.`) : apply(s.state, s.label)}>
                        <b>{s.tier !== "basic" && <Icon name={lock ? "lock" : s.tier === "gold" ? "crown" : "check"} />}{s.label}</b><span>{s.says}</span></button>); })}
                  </div>) : null; })}
              </div>
            )}
          </aside>

          <section className="scr-main card" aria-label="Results">
            <div className="scr-top">
              <div aria-live="polite"><b className="scr-count">{res.isLoading || !res.data ? "…" : nf(total, 0)}</b> <span className="muted">of {data ? nf(data.total, 0) : "…"} stocks{res.data ? ` · ${res.data.took} ms` : ""}</span></div>
              <div className="scr-tools">
                <label className="scr-find sm"><Icon name="search" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search stocks" aria-label="Search stocks in results" /></label>
                <div className="scr-cm"><button className="btn" aria-expanded={colMenu} onClick={() => setColMenu(!colMenu)}>Columns · {columns.length}</button>
                  {colMenu && data && <div className="scr-colmenu pl-colmenu" role="menu">
                    <label className="scr-find sm" style={{ margin: "0 0 8px" }}><Icon name="search" /><input value={colFind} onChange={(e) => setColFind(e.target.value)} placeholder="Find a column" aria-label="Find a column" /></label>
                    {data.groups.map((g) => { const ms = g.metrics.filter((m) => !colFind.trim() || m.label.toLowerCase().includes(colFind.trim().toLowerCase())); return ms.length ? <div key={g.id}><div className="label">{g.label}</div>{ms.map((m) => <label key={m.key} className={m.locked ? "is-locked" : ""}><input type="checkbox" checked={columns.includes(m.key)} disabled={m.locked} onChange={() => toggleCol(m.key)} />{m.label}{m.locked && <Icon name="lock" />}</label>)}</div> : null; })}
                    <button className="alx-link" onClick={() => setCols(null)}>Reset columns</button></div>}</div>
                <button className="btn" onClick={exportCsv}><Icon name="table" />Download</button>
              </div>
            </div>
            {chips.length > 0 && <div className="scr-chips">{chips.map((c) => <button key={c.label} className="fchip" onClick={c.clear}>{c.label}<span aria-hidden="true">×</span><span className="sr">remove</span></button>)}<button className="alx-link" onClick={() => setF(norm({}))}>Clear all</button></div>}
            {res.isError && err?.status !== 403 ? <div className="state"><h2>The screener is unavailable right now</h2><p>Please try again in a moment.</p><button className="btn" onClick={() => res.refetch()}>Try again</button></div>
              : res.isError ? <div className="state"><h2>That filter is part of a higher plan</h2><p>{err?.body?.detail}</p><button className="btn primary" onClick={() => ask((err?.body?.plan as Plan) || "silver", err?.body?.detail || "")}>See the plan</button></div>
              : !res.data ? <div className="skeleton" style={{ height: 380 }} aria-busy="true" /> : (
                <>
                  <div className={"tw scr-tw" + (res.isFetching ? " is-busy" : "")}><table className="scr-t">
                    <thead><tr><th className="stick"><button onClick={() => sortBy("name")}>Company {sort.key === "name" ? (sort.dir === "asc" ? "▲" : "▼") : "▾"}</button></th>
                      {res.data.columns.map((k) => { const m = byKey.get(k); return <th key={k}><button onClick={() => sortBy(k)} title={m?.say} aria-label={`Sort by ${m?.label}`}>{m?.label} {sort.key === k ? (sort.dir === "asc" ? "▲" : "▼") : "▾"}</button></th>; })}</tr></thead>
                    <tbody>{rows.map((r) => (
                      <tr key={r.symbol} tabIndex={0} onClick={() => nav(`/stocks/${r.symbol}`)} onKeyDown={(e) => e.key === "Enter" && nav(`/stocks/${r.symbol}`)}>
                        <td className="stick"><span className="co"><span className="av mini" aria-hidden="true">{(r.name || r.symbol).slice(0, 2).toUpperCase()}</span><span><b>{r.symbol}</b><small>{r.name}{r.cap ? ` · ${r.cap}` : ""}</small></span></span></td>
                        {res.data!.columns.map((k) => { const m = byKey.get(k), v = r.v[k]; return <td key={k} className={tone(k, v)}>{m ? fmtMetric(m, v) : MINUS}</td>; })}
                      </tr>))}
                      {!rows.length && <tr><td colSpan={res.data.columns.length + 1} className="empty">No companies match all of these filters. Try loosening one, or <button className="alx-link" onClick={() => setF(norm({}))}>clear them all</button>.</td></tr>}
                    </tbody></table></div>
                  {res.data.capped ? (
                    <div className="pl-cap"><Icon name="lock" /><span><b>Showing the first {res.data.limit} of {nf(total, 0)} matches.</b> Silver shows every match, lets you download them, and unlocks all {data ? data.groups.reduce((a, g) => a + g.metrics.length, 0) : 160}+ filters.</span>
                      <button className="btn primary" onClick={() => ask("silver", "See every match and use every filter with Silver.")}>Unlock with Silver</button></div>
                  ) : total > PAGE && (
                    <div className="pm-pager"><span>{page * PAGE + 1}–{Math.min(total, page * PAGE + PAGE)} of {nf(total, 0)}</span><button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button><button className="btn" disabled={(page + 1) * PAGE >= total} onClick={() => setPage(page + 1)}>Next</button></div>)}
                </>)}
            <Plain>Green cells are in the best quarter of the results shown for that column, red cells the weakest quarter. “Best” means lower for P/E, P/B and debt, higher for returns and profitability. Hover a column name for what it means.</Plain>
            <p className="faint scr-foot">A screen narrows a long list; it does not say what to buy. Open a company's report to see why a number looks the way it does. Index lists come from NSE Indices. General information, not investment advice.</p>
          </section>
        </div>
      </div>
    </>
  );
}

export type { Catalog };
