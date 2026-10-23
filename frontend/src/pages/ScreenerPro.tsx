import { HScroll } from "../components/HScroll";
import { SplitDivider, useSideWidth } from "../components/SplitDivider";
import { Fragment, lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { PageArt } from "../components/PageArt";
import { Plain } from "../components/Plain";
import { Icon } from "../lib/icons";
import { nf, MINUS } from "../lib/format";
import { API_BASE, apiUrl } from "../lib/api";
import { limitsFor } from "../lib/auth";
import { READY, UNIT_SUFFIX, activeCount, decodeState, encodeState, fmtMetric, norm, toBody, useCatalog, useScreen, type Catalog, type MetricInfo, type PState, type Range } from "../lib/proscreen";
import { screens, useSavedScreens } from "../lib/screens";
import { saveFile } from "../stock/derive";
import { useDocTitle } from "../lib/title";
import { TIER, useUI, type Plan } from "../lib/ui";
import { supports3d, whenIdle } from "../three/support";
import { ChartHelp } from "../components/ChartHelp";
import { matchesMetric, rankMetrics } from "../lib/metricSearch";

const Cloud3D = lazy(() => import("../three/Cloud3D"));

const TIER_ORDER: Plan[] = ["basic", "silver", "gold"];
const PAGE = 50;
const MAX_COLS = 12;
const VISIBLE_GROUPS = 9;

const useDebounced = <T,>(v: T, ms: number) => { const [d, setD] = useState(v); useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]); return d; };

const TAB_LABEL: Record<string, string> = { now: "Now", "3y": "3Y avg", "5y": "5Y avg", "7y": "7Y avg" };
const fmtEdge = (v: number, m: MetricInfo) => nf(v, Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 100 ? 1 : m.digits > 1 ? 2 : 1);

/** A bar chart of where every company sits, with a two-handle slider underneath: drag to set the range, or type it in the boxes. */
function RangeBox({ m, r, set }: { m: MetricInfo; r: Range; set: (r: Range) => void }) {
  const st = m.stats;
  if (!st) return <p className="pl-say">Not enough companies report this yet.</p>;
  const lo = st.lo ?? st.min, hi = st.hi ?? st.max, span = hi - lo || 1, steps = 200;
  const toPos = (v: number | undefined, dflt: number) => Math.round(((Math.min(hi, Math.max(lo, v ?? dflt)) - lo) / span) * steps);
  const a = toPos(r.min, lo), b = toPos(r.max, hi);
  const at = (pos: number) => lo + (pos / steps) * span;
  const nice = (v: number) => Number(v.toPrecision(3));
  const num = (raw: string) => (raw === "" ? undefined : Number.isFinite(Number(raw)) ? Number(raw) : undefined);
  const bars = st.hist || [], top = Math.max(1, ...bars);
  const inside = (i: number) => { const c0 = lo + (i / bars.length) * span, c1 = lo + ((i + 1) / bars.length) * span; return (r.min == null || c1 >= r.min) && (r.max == null || c0 <= r.max); };
  return (
    <>
      <div className="pl-hist" role="img" aria-label={`How ${m.label} is spread across ${nf(st.n, 0)} companies`}>{bars.map((c, i) => <i key={i} className={inside(i) ? "in" : ""} style={{ height: `${Math.max(3, (c / top) * 100)}%` }} />)}</div>
      <div className="pl-slider">
        <input type="range" min={0} max={steps} value={a} aria-label={`${m.label} minimum slider`} onChange={(e) => { const v = Number(e.target.value); set({ ...r, min: v <= 0 ? undefined : Math.min(nice(at(v)), r.max ?? Infinity) }); }} />
        <input type="range" min={0} max={steps} value={b} aria-label={`${m.label} maximum slider`} onChange={(e) => { const v = Number(e.target.value); set({ ...r, max: v >= steps ? undefined : Math.max(nice(at(v)), r.min ?? -Infinity) }); }} />
        <span className="pl-track"><span style={{ left: `${(a / steps) * 100}%`, right: `${100 - (b / steps) * 100}%` }} /></span>
      </div>
      <div className="pl-mm">
        <label><small>MIN</small><input type="number" inputMode="decimal" placeholder={fmtEdge(st.min, m)} value={r.min ?? ""} onChange={(e) => set({ ...r, min: num(e.target.value) })} aria-label={`${m.label} minimum`} /></label>
        <label><small>MAX</small><input type="number" inputMode="decimal" placeholder={fmtEdge(st.max, m)} value={r.max ?? ""} onChange={(e) => set({ ...r, max: num(e.target.value) })} aria-label={`${m.label} maximum`} /></label>
      </div>
      <small className="pl-typ">Most companies: {fmtEdge(st.p10, m)}{UNIT_SUFFIX[m.unit] ?? ""} to {fmtEdge(st.p90, m)}{UNIT_SUFFIX[m.unit] ?? ""} · {nf(st.n, 0)} companies reported</small>
    </>
  );
}

/** The card that opens under a chip: name, what it means, Now / 3Y / 5Y / 7Y tabs where they exist, the range, and Remove. */
function FilterCard({ m, byKey, ranges, setRange, ask }: { m: MetricInfo; byKey: Map<string, MetricInfo>; ranges: Record<string, Range>; setRange: (k: string, r: Range) => void; ask: (tier: Plan, why: string) => void }) {
  const [info, setInfo] = useState(false);
  const tabs = m.variants ? Object.entries(m.variants) : null;
  const firstActive = tabs?.find(([, k]) => ranges[k])?.[0] ?? "now";
  const [tab, setTab] = useState(firstActive);
  const key = tabs ? m.variants![tab] : m.key, cur = byKey.get(key) || m;
  const r = ranges[key] || {};
  const locked = cur.locked;
  const clearAll = () => (tabs ? tabs.forEach(([, k]) => setRange(k, {})) : setRange(m.key, {}));
  const any = (tabs ? tabs.some(([, k]) => ranges[k]) : !!ranges[m.key]);
  return (
    <div className={"pl-card" + (locked ? " is-locked" : "")}>
      <div className="pl-card-h"><b>{m.label}</b>{!locked && cur.unit !== "flag" && cur.stats && <ChartHelp id={tabs && tab !== "now" ? "screener-avg" : "screener-range"} />}{locked ? <button className="pl-tier" onClick={() => ask(m.tier, `${m.label} is part of the ${TIER[m.tier].n} plan.`)}><Icon name="lock" />{TIER[m.tier].n}</button>
        : <button className="pl-i" aria-label={`What ${m.label} means`} aria-expanded={info} onClick={() => setInfo(!info)}><Icon name="info" /></button>}
        {any && <button className="pl-rm" onClick={clearAll}>Remove</button>}</div>
      {info && <p className="pl-say">{m.say}{m.better !== "none" ? ` ${m.better === "higher" ? "Higher" : "Lower"} is usually better.` : ""}</p>}
      {tabs && <div className="pm-seg" role="tablist" aria-label={`${m.label} period`}>{tabs.map(([t, k]) => <button key={t} role="tab" aria-selected={tab === t} aria-pressed={tab === t} onClick={() => setTab(t)}>{TAB_LABEL[t]}{ranges[k] ? " •" : ""}</button>)}</div>}
      {cur.unit === "flag" ? (
        <div className="pm-seg" role="group" aria-label={cur.label}>{(["any", "yes", "no"] as const).map((o) => { const v = r.min === 1 ? "yes" : r.max === 0 ? "no" : "any"; return <button key={o} aria-pressed={v === o} onClick={() => (locked ? ask(cur.tier, `${cur.label} is part of the ${TIER[cur.tier].n} plan.`) : setRange(key, o === "any" ? {} : o === "yes" ? { min: 1 } : { max: 0 }))}>{o === "any" ? "Any" : o === "yes" ? "Yes" : "No"}</button>; })}</div>
      ) : locked ? <p className="pl-say">Unlock this filter with the {TIER[m.tier].n} plan to set a range.</p> : <RangeBox key={key} m={cur} r={r} set={(nr) => setRange(key, nr)} />}
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
  const [sideW, setSide] = useSideWidth("screener");
  const nav = useNavigate();
  const cat = useCatalog();
  const [params, setParams] = useSearchParams();
  const init = useRef(decodeState(params.get("s")));
  const [f, setF] = useState<PState>(init.current.state);
  const [sort, setSort] = useState({ key: init.current.sort || "market_cap", dir: (init.current.dir || "desc") as "asc" | "desc" });
  const [cols, setCols] = useState<string[] | null>(null);
  const [q, setQ] = useState(""), [pg, setPg] = useState({ k: "", p: 0 });
  const [tab, setTab] = useState<"filters" | "quick">("filters");
  const [pick, setPick] = useState<Record<string, string>>({ valuation: "pe" });
  const [find, setFind] = useState(""), [open, setOpen] = useState<Record<string, boolean>>({ valuation: true });
  const [moreGroups, setMoreGroups] = useState(false), [colMenu, setColMenu] = useState(false), [colFind, setColFind] = useState(""), [saveName, setSaveName] = useState("");
  const saved = useSavedScreens();
  const data = cat.data;
  const plan: Plan = data?.plan ?? "basic";
  const byKey = useMemo(() => new Map((data?.groups || []).flatMap((g) => g.metrics.map((m) => [m.key, m] as const))), [data]);
  // Opens with the default columns; every filter adds its own column and takes it away again when the filter goes.
  const columns = useMemo(() => { const base = cols ?? data?.defaultColumns ?? []; const extra = Object.keys(f.ranges).filter((k) => !base.includes(k) && (!data || byKey.has(k))); return [...base, ...extra].slice(0, 40); }, [cols, data, f.ranges, byKey]);
  const ask = (tier: Plan, why: string) => upgrade(tier, why);

  const dq = useDebounced(f, 250), dsort = useDebounced(sort, 0), dqq = useDebounced(q, 250);
  // The page belongs to the filters it was chosen under: change a filter, the sort or the search and it is page 1 at once (no request with the old offset).
  const pkey = JSON.stringify([dq, dsort, dqq]), page = pg.k === pkey ? pg.p : 0, setPage = (p: number) => setPg({ k: pkey, p });
  // A shared or old link can name a filter or sort the screener does not have: leave those out instead of failing the whole screen.
  const known = (k: string) => !data || byKey.has(k);
  const safe = useMemo(() => ({ ...dq, ranges: Object.fromEntries(Object.entries(dq.ranges).filter(([k]) => known(k))) }), [dq, data]); // eslint-disable-line react-hooks/exhaustive-deps
  const safeSort = known(dsort.key) || dsort.key === "name" || dsort.key === "symbol" ? dsort : { key: "market_cap", dir: "desc" as const };
  const body = useMemo(() => toBody(safe, safeSort, columns, dqq, page * PAGE, PAGE), [safe, safeSort.key, safeSort.dir, columns, dqq, page]); // eslint-disable-line react-hooks/exhaustive-deps
  const res = useScreen(body, !!data && columns.length > 0);
  const rows = res.data?.rows || [];
  const nActive = activeCount(f);

  // keep the address bar in step so a screen can be shared
  useEffect(() => { const s = encodeState(dq, dsort.key, dsort.dir); const n = new URLSearchParams(params); s ? n.set("s", s) : n.delete("s"); if (n.toString() !== params.toString()) setParams(n, { replace: true }); }, [dq, dsort]); // eslint-disable-line react-hooks/exhaustive-deps

  const setRange = (k: string, r: Range) => setF((s) => { const ranges = { ...s.ranges }; if (r.min == null && r.max == null) delete ranges[k]; else ranges[k] = r; return { ...s, ranges }; });
  const toggle = (key: "sectors" | "industries" | "indices" | "caps" | "bands", v: string) => setF((s) => ({ ...s, [key]: s[key].includes(v) ? s[key].filter((x) => x !== v) : [...s[key], v] }));
  const fl = find.trim().toLowerCase();
  const lastTap = useRef({ k: "", t: 0 });
  /** True on the second click/tap of the same chip within 400 ms: works for mouse, touch and Enter alike. */
  const tap = (k: string) => { const now = Date.now(), dbl = lastTap.current.k === k && now - lastTap.current.t < 400; lastTap.current = dbl ? { k: "", t: 0 } : { k, t: now }; return dbl; };
  const clearMetric = (m: MetricInfo, gid: string) => { (m.variants ? Object.values(m.variants) : [m.key]).forEach((k) => setRange(k, {})); setPick((x) => ({ ...x, [gid]: "" })); };

  const sortBy = (key: string) => setSort((s) => (s.key === key ? { key, dir: s.dir === "desc" ? "asc" : "desc" } : { key, dir: key === "name" || byKey.get(key)?.better === "lower" ? "asc" : "desc" }));
  const toggleCol = (k: string) => { if (f.ranges[k] && !(cols ?? data?.defaultColumns ?? []).includes(k)) { toast("Remove the filter to hide its column."); return; } const cur = cols ?? data?.defaultColumns ?? []; if (cur.includes(k)) setCols(cur.filter((x) => x !== k)); else if (cur.length >= MAX_COLS) toast(`Up to ${MAX_COLS} columns at a time.`); else setCols([...cur, k]); };

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
    screens.save(n, { ...f, sort: sort.key, dir: sort.dir, cols: cols ?? undefined } as never, max); setSaveName(""); toast(`Saved “${n}”. You can find it under Quick screens.`);
  };
  const exportCsv = async () => {
    if (!data?.limits.export) { ask("silver", "Downloading results comes with the Silver plan."); return; }
    try {
      const r = await fetch(apiUrl("/api/screener/export"), { method: "POST", credentials: API_BASE ? "include" : "same-origin", headers: { "Content-Type": "application/json", Accept: "text/csv" }, body: JSON.stringify(toBody(safe, safeSort, columns, dqq, 0, 100)) });
      if (!r.ok) throw new Error(String(r.status));
      saveFile("FinLit-screen.csv", await r.text(), "text/csv;charset=utf-8"); toast("Saved your results as FinLit-screen.csv.");
    } catch { toast("We could not prepare the download. Please try again."); }
  };

  const ordered = [...(data?.groups || [])].sort((a, b) => Number(b.id === "model") - Number(a.id === "model"));   // the FinLit model group leads: it is what Gold adds
  const groups = ordered.filter((g) => !fl || g.label.toLowerCase().includes(fl) || g.metrics.some((m) => matchesMetric(find, m)));
  const listed = fl || moreGroups ? groups : groups.slice(0, VISIBLE_GROUPS);
  const facetOpen = (id: string) => !!(open[id] || fl);
  const facetMatch = (label: string) => !fl || label.toLowerCase().includes(fl);
  const [webgl, setWebgl] = useState(false);
  useEffect(() => { if (supports3d()) return whenIdle(() => setWebgl(true)); }, []);
  /** The first three shown columns that hold numbers become the three axes of the 3D view. */
  const cloud = useMemo(() => {
    const cs = (res.data?.columns || []).filter((k) => byKey.get(k)?.unit !== "flag" && rows.filter((r) => typeof r.v[k] === "number").length >= 5).slice(0, 3);
    if (cs.length < 3) return null;
    const pts = rows.filter((r) => cs.every((k) => typeof r.v[k] === "number" && isFinite(r.v[k] as number)))
      .map((r) => ({ id: r.symbol, label: `${r.symbol}: ${cs.map((k) => `${byKey.get(k)?.label} ${fmtMetric(byKey.get(k)!, r.v[k])}`).join(" · ")}`, x: r.v[cs[0]] as number, y: r.v[cs[1]] as number, z: r.v[cs[2]] as number }));
    return pts.length >= 5 ? { pts, axes: cs.map((k) => byKey.get(k)?.label || k) as [string, string, string] } : null;
  }, [rows, res.data?.columns, byKey]);
  const heat = useMemo(() => {
    const out: Record<string, [number, number]> = {};
    for (const k of res.data?.columns || []) { const v = rows.map((r) => r.v[k]).filter((x): x is number => x != null).sort((a, b) => a - b); if (v.length > 6) out[k] = [v[Math.floor(v.length * 0.25)], v[Math.floor(v.length * 0.75)]]; }
    return out;
  }, [rows, res.data?.columns]);
  const tone = (k: string, v: number | null) => { const m = byKey.get(k), h = heat[k]; if (v == null || !m || !h || m.better === "none" || m.unit === "flag" || h[0] === h[1]) return ""; const good = m.better === "higher" ? v >= h[1] : v <= h[0], bad = m.better === "higher" ? v <= h[0] : v >= h[1]; return good ? "tone-good" : bad ? "tone-bad" : ""; };
  const err = res.error as { status?: number; body?: { plan?: string; detail?: string } } | null;
  const total = res.data?.total ?? 0;

  // Sector, Industry and Index sit straight after the FinLit model group (or at the top while a search hides it)
  const facetBlocks = <>
                  {data && facetMatch("Sector") && (
                    <div className="scr-g"><button className="scr-gh" aria-expanded={facetOpen("sector")} onClick={() => setOpen((o) => ({ ...o, sector: !o.sector }))}><span>Sector{f.sectors.length > 0 && <i className="dotn" style={{ marginLeft: 8 }}>{f.sectors.length}</i>}</span><span className="scr-n">{data.sectors.length}</span><Icon name="arrow" /></button>
                      {facetOpen("sector") && <div className="scr-gb"><Checks search items={data.sectors.map((s) => ({ key: s.name, label: s.name, n: s.n }))} picked={f.sectors} toggle={(k) => toggle("sectors", k)} /></div>}</div>)}
                  {data && facetMatch("Industry") && (
                    <div className="scr-g"><button className="scr-gh" aria-expanded={facetOpen("industry")} onClick={() => setOpen((o) => ({ ...o, industry: !o.industry }))}><span>Industry{f.industries.length > 0 && <i className="dotn" style={{ marginLeft: 8 }}>{f.industries.length}</i>}</span><span className="scr-n">{data.industries.length}</span><Icon name="arrow" /></button>
                      {facetOpen("industry") && <div className="scr-gb"><Checks search items={data.industries.map((s) => ({ key: s.name, label: s.name, n: s.n }))} picked={f.industries} toggle={(k) => toggle("industries", k)} /></div>}</div>)}
                  {data && data.indices.length > 0 && facetMatch("Index") && (
                    <div className="scr-g"><button className="scr-gh" aria-expanded={facetOpen("index")} onClick={() => setOpen((o) => ({ ...o, index: !o.index }))}><span>Index{f.indices.length > 0 && <i className="dotn" style={{ marginLeft: 8 }}>{f.indices.length}</i>}</span><span className="scr-n">{data.indices.length}</span><Icon name="arrow" /></button>
                      {facetOpen("index") && <div className="scr-gb"><Checks items={data.indices.map((s) => ({ key: s.code, label: s.label, n: s.n }))} picked={f.indices} toggle={(k) => toggle("indices", k)} /></div>}</div>)}
  </>;

  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="research" />
        <div className="eyebrow">Stock screener</div><h1>Find the companies that fit your rules.</h1>
        <p>{data ? nf(data.total, 0) : "Every listed"} companies and {data ? data.groups.reduce((a, g) => a + g.metrics.length, 0) : "160+"} filters, from valuation and quarterly results to ownership and red flags. {plan !== "gold" && "Gold adds filters built on the FinLit research model. "}Prefer a simpler start? Try the <Link to="/score-screener">Score screener</Link>.</p></div></section>
      <div className="wrap scr-wrap">
        <div className="scr" style={{ "--side-w": `${sideW}px` } as React.CSSProperties}>
          <aside className="scr-side card" aria-label="Filters" hidden={sideW === 0}>
            <div className="seg scr-tabs" role="tablist"><button role="tab" aria-selected={tab === "filters"} onClick={() => setTab("filters")}>Filters{nActive ? <i className="dotn">{nActive}</i> : null}</button><button role="tab" aria-selected={tab === "quick"} onClick={() => setTab("quick")}>Quick screens</button></div>
            {tab === "filters" ? (
              <>
                <label className="scr-find"><Icon name="search" /><input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Search for a filter, e.g. ROE or promoter" aria-label="Search for a filter" /></label>
                {cat.isLoading && <div className="skeleton" style={{ height: 320, marginTop: 12 }} />}
                {cat.isError && <div className="state"><p>The filters are not available right now. Please try again in a moment.</p><button className="btn" onClick={() => cat.refetch()}>Try again</button></div>}
                <div className="scr-groups">
                  {!listed.some((g) => g.id === "model") && facetBlocks}
                  {listed.map((g) => {
                    const isOpen = facetOpen(g.id), model = g.id === "model", allLocked = g.metrics.every((m) => m.locked);
                    const shownMetrics = fl ? (g.label.toLowerCase().includes(fl) ? g.metrics : rankMetrics(g.metrics, find)) : g.metrics;
                    const n = Object.keys(f.ranges).filter((k) => g.metrics.some((m) => m.key === k)).length;
                    return (
                      <Fragment key={g.id}><div className={"scr-g" + (model ? " is-model" : "")}>
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
                            {!(model && allLocked) && <>
                              {(() => {
                                // The main filters of a group come first, the chart of the chosen filter right under them, then the rest,
                                // so opening a filter never pushes its chart to the bottom of a long group.
                                const visible = shownMetrics.filter((m) => !m.hidden), MAIN = visible.length > 8 ? 6 : visible.length;
                                const chip = (m: MetricInfo) => {
                                  const active = m.variants ? Object.values(m.variants).some((k) => f.ranges[k]) : !!f.ranges[m.key];
                                  return <button key={m.key} className={"pl-chip" + (active ? " on" : "") + (pick[g.id] === m.key ? " open" : "") + (m.locked ? " is-locked" : "")} aria-pressed={pick[g.id] === m.key} onClick={() => { if (active && tap(m.key)) { clearMetric(m, g.id); return; } setPick((x) => ({ ...x, [g.id]: x[g.id] === m.key ? "" : m.key })); }} onKeyDown={(e) => { if (active && (e.key === "Delete" || e.key === "Backspace")) { e.preventDefault(); clearMetric(m, g.id); } }} title={active ? "Double-click (or press Delete) to remove this filter" : undefined}>{m.label}{m.locked && <Icon name="lock" />}</button>;
                                };
                                const card = pick[g.id] && byKey.get(pick[g.id]) && <FilterCard key={pick[g.id]} m={byKey.get(pick[g.id])!} byKey={byKey} ranges={f.ranges} setRange={setRange} ask={ask} />;
                                return <>
                                  <div className="pl-chips" role="group" aria-label={`${g.label} filters`}>{visible.slice(0, MAIN).map(chip)}</div>
                                  {card}
                                  {visible.length > MAIN && <div className="pl-chips pl-more" role="group" aria-label={`More ${g.label.toLowerCase()} filters`}>{visible.slice(MAIN).map(chip)}</div>}
                                </>;
                              })()}
                            </>}
                          </div>)}
                      </div>{model && facetBlocks}</Fragment>);
                  })}
                  {!fl && groups.length > VISIBLE_GROUPS && <button className="alx-link" style={{ margin: "10px 0 4px" }} onClick={() => setMoreGroups(!moreGroups)}>{moreGroups ? "Show fewer categories" : `Show ${groups.length - VISIBLE_GROUPS} more categories`}</button>}
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
          <SplitDivider width={sideW} set={setSide} />

          <section className="scr-main card" aria-label="Results">
            <div className="scr-top">
              <div aria-live="polite"><b className="scr-count">{res.isLoading || !res.data ? "…" : nf(total, 0)}</b> <span className="muted">of {data ? nf(data.total, 0) : "…"} listed stocks{res.data ? ` · ${res.data.took} ms` : ""}</span></div>
              <div className="scr-tools">
                <label className="scr-find sm"><Icon name="search" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search stocks" aria-label="Search stocks in results" /></label>
                <div className="scr-cm"><button className="btn" aria-expanded={colMenu} onClick={() => setColMenu(!colMenu)}>Columns · {columns.length}</button>
                  {colMenu && data && <div className="scr-colmenu pl-colmenu" role="menu">
                    <label className="scr-find sm" style={{ margin: "0 0 8px" }}><Icon name="search" /><input value={colFind} onChange={(e) => setColFind(e.target.value)} placeholder="Find a column" aria-label="Find a column" /></label>
                    {data.groups.map((g) => { const ms = colFind.trim() ? rankMetrics(g.metrics, colFind) : g.metrics; return ms.length ? <div key={g.id}><div className="label">{g.label}</div>{ms.map((m) => <label key={m.key} className={m.locked ? "is-locked" : ""}><input type="checkbox" checked={columns.includes(m.key)} disabled={m.locked} onChange={() => toggleCol(m.key)} />{m.label}{m.locked && <Icon name="lock" />}</label>)}</div> : null; })}
                    <button className="alx-link" onClick={() => setCols(null)}>Reset columns</button></div>}</div>
                <button className="btn" onClick={exportCsv}><Icon name="table" />Download</button>
              </div>
            </div>
            {chips.length > 0 && <div className="scr-chips">{chips.map((c) => <button key={c.label} className="fchip" onClick={c.clear} onKeyDown={(e) => { if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); c.clear(); } }}>{c.label}<span aria-hidden="true">×</span><span className="sr">remove</span></button>)}<button className="alx-link" onClick={() => setF(norm({}))}>Clear all</button></div>}
            {res.isError && err?.status !== 403 ? <div className="state"><h2>The screener is unavailable right now</h2><p>Please try again in a moment.</p><button className="btn" onClick={() => res.refetch()}>Try again</button></div>
              : res.isError ? <div className="state"><h2>That filter is part of a higher plan</h2><p>{err?.body?.detail}</p><button className="btn primary" onClick={() => ask((err?.body?.plan as Plan) || "silver", err?.body?.detail || "")}>See the plan</button></div>
              : !res.data ? <div className="skeleton" style={{ height: 380 }} aria-busy="true" /> : (
                <>
                  {webgl && cloud && <Suspense fallback={null}><Cloud3D points={cloud.pts} axes={cloud.axes} onPick={(id) => nav(`/stocks/${id}`)}
                    label={`The ${cloud.pts.length} companies on this page as points in 3D, spread by ${cloud.axes.join(", ")}. The table below lists the same numbers.`} /></Suspense>}
                  <HScroll className={"scr-tw" + (res.isFetching ? " is-busy" : "")} label="results table"><table className="scr-t">
                    <thead><tr><th className="stick"><button onClick={() => sortBy("name")}>Company {sort.key === "name" ? (sort.dir === "asc" ? "▲" : "▼") : "▾"}</button></th>
                      {res.data.columns.map((k) => { const m = byKey.get(k); return <th key={k}><button onClick={() => sortBy(k)} title={m?.say} aria-label={`Sort by ${m?.label}`}>{m?.label} {sort.key === k ? (sort.dir === "asc" ? "▲" : "▼") : "▾"}</button></th>; })}</tr></thead>
                    <tbody>{rows.map((r) => (
                      <tr key={r.symbol} tabIndex={0} onClick={() => nav(`/stocks/${r.symbol}`)} onKeyDown={(e) => e.key === "Enter" && nav(`/stocks/${r.symbol}`)}>
                        <td className="stick"><span className="co"><span className="av mini" aria-hidden="true">{(r.name || r.symbol).slice(0, 2).toUpperCase()}</span><span><b>{r.symbol}</b><small>{r.name}{r.cap ? ` · ${r.cap}` : ""}</small></span></span></td>
                        {res.data!.columns.map((k) => { const m = byKey.get(k), v = r.v[k]; return <td key={k} className={tone(k, v)}>{m ? fmtMetric(m, v) : MINUS}</td>; })}
                      </tr>))}
                      {!rows.length && <tr><td colSpan={res.data.columns.length + 1} className="empty">No companies match all of these filters. Try loosening one, or <button className="alx-link" onClick={() => setF(norm({}))}>clear them all</button>.</td></tr>}
                    </tbody></table></HScroll>
                  {res.data.capped ? (
                    <div className="pl-cap"><Icon name="lock" /><span><b>Showing the first {res.data.limit} of {nf(total, 0)} matches.</b> Silver shows every match, lets you download them, and unlocks all {data ? data.groups.reduce((a, g) => a + g.metrics.length, 0) : 160}+ filters.</span>
                      <button className="btn primary" onClick={() => ask("silver", "See every match and use every filter with Silver.")}>Unlock with Silver</button></div>
                  ) : total > PAGE && (
                    <div className="pm-pager"><span>{page * PAGE + 1}–{Math.min(total, page * PAGE + PAGE)} of {nf(total, 0)}</span><button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button><button className="btn" disabled={(page + 1) * PAGE >= total} onClick={() => setPage(page + 1)}>Next</button></div>)}
                </>)}
            <Plain>Green cells are in the best quarter of the results shown for that column, red cells the weakest quarter. “Best” means lower for P/E, P/B and debt, higher for returns and profitability. Hover a column name for what it means.</Plain>
            {data && data.withReport < data.total && <p className="faint scr-foot">All {nf(data.total, 0)} listed companies are here with their price and market cap. Ratios, growth and statements show a dash until a company's report is loaded ({nf(data.withReport, 0)} are today); filtering on one of those leaves out the companies that lack it.</p>}
            <p className="faint scr-foot">A screen narrows a long list; it does not say what to buy. Open a company's report to see why a number looks the way it does. Index lists come from NSE Indices. General information, not investment advice.</p>
          </section>
        </div>
      </div>
    </>
  );
}

export type { Catalog };
