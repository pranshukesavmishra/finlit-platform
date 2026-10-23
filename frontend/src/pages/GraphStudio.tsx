import { DrawLayer } from "../components/DrawLayer";
import { viewId } from "../lib/drawings";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import { apiGet, apiSend, useSearchIndex, ApiError } from "../lib/api";
import { useIndices } from "../lib/indices";
import { useAuth, type Plan } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { Icon } from "../lib/icons";
import { useUI, useThemeKey } from "../lib/ui";
import { useDocTitle } from "../lib/title";
import { Candles, Heat, HBars, Pie, Scatter, TimeChart, useWidth, type Colors, type PS } from "../components/GraphCharts";
import { alignSeries, changes, corrMatrix, csvRow, pearson, rebase, RANGES, strength, windowPts } from "../lib/graphData";
import { BY_ID, extract, GROUPS, IDX, indexCode, isIndexSym, metricFor, metricsIn, unsupportedWhy, UNITS, type Bundle, type Extracted, type Metric, type UnitId } from "../lib/graphMetrics";
import { graphLimits, chartTier, type ChartKind } from "../lib/graphLimits";
import { CHART_LABEL, LAYOUTS, cellCount, chartCheck, decodeView, defaultView, encodeView, sanitize, type CellFacts, type CellSpec, type SeriesSpec, type View } from "../lib/graphState";
import "../styles/graphs.css";

const CHARTS = Object.keys(CHART_LABEL) as ChartKind[];
const LKEY = "finlit-graph-views";
const readLocal = (): Record<string, View> => { try { const v = JSON.parse(localStorage.getItem(LKEY) || "{}"); return v && typeof v === "object" ? v : {}; } catch { return {}; } };
const writeLocal = (v: Record<string, View>) => { try { localStorage.setItem(LKEY, JSON.stringify(v)); } catch { /* private mode */ } };

function readColors(): Colors {
  const cs = getComputedStyle(document.documentElement), g = (n: string, d = "#888") => cs.getPropertyValue(n).trim() || d;
  return { s: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => g(`--gx-${i}`)), surface: g("--gx-surface", "#fff"), text: g("--text", "#111"), muted: g("--gx-muted"), grid: g("--gx-grid"), axis: g("--gx-axis"), gain: g("--gx-gain"), loss: g("--gx-loss"), pos: g("--gx-pos"), neg: g("--gx-neg"), mid: g("--gx-mid") };
}

type Src = "fin" | "ratios" | "own" | "seg" | "price" | "ixl" | "ixv";
const SRC_OF: Record<string, Src> = { ixval: "ixv", pl: "fin", bs: "fin", cf: "fin", ratio: "ratios", val: "ratios", own: "own", ownnow: "own", seg: "seg", price: "price" };
const PATH: Record<"fin" | "ratios" | "own" | "seg" | "price", string> = { fin: "/financials", ratios: "/ratios", own: "/ownership", seg: "/segments", price: "/price" };

function useBundles(view: View, count: number, plan: Plan) {
  const need = useMemo(() => { const m = new Map<string, Set<Src>>(); view.cells.slice(0, count).forEach((c) => c.series.forEach((s) => { const mt = BY_ID[s.m]; if (!mt || unsupportedWhy(s.s, mt)) return;
    const ix = isIndexSym(s.s), src: Src = ix && mt.id === "price" ? "ixl" : SRC_OF[mt.src];
    if (src === "ixv" && plan !== "gold") return;   // the index valuation history is a Gold tool: not even asked for
    const set = m.get(s.s) ?? new Set<Src>(); set.add(src); if (c.chart === "candlestick" && !ix) set.add("price"); m.set(s.s, set); })); return m; }, [view.cells, count, plan]);
  const jobs = useMemo(() => [...need].flatMap(([sym, set]) => [...set].map((src) => ({ sym, src }))), [need]);
  const qs = useQueries({ queries: jobs.map(({ sym, src }) => {
    const ix = src === "ixl" || src === "ixv";
    const path = src === "ixl" ? "/history?years=5" : src === "ixv" ? "/valuation?years=5" : src === "price" ? `/price?range=${view.from ? "MAX" : view.range}` : PATH[src as "fin"];
    const url = ix ? `/api/indices/${encodeURIComponent(indexCode(sym))}${path}` : `/api/stocks/${encodeURIComponent(sym)}${path}`;
    return { queryKey: [ix ? "index" : "stock", sym, path], queryFn: () => apiGet<unknown>(url), staleTime: ix ? 300_000 : 60_000,
      retry: (n: number, e: ApiError) => (e.status === 202 ? n < 100 : e.status === 429 ? n < 8 : e.status >= 500 && n < 2),
      retryDelay: (_: number, e: ApiError) => (e.status === 202 ? (e.body.retryAfter || 3) * 1000 : 1500) };
  }) });
  const bundles = new Map<string, { b: Bundle; st: Partial<Record<Src, "loading" | "ok" | "error" | "locked">>; err?: string }>();
  jobs.forEach((j, i) => {
    const q = qs[i], e = bundles.get(j.sym) ?? { b: {}, st: {} };
    e.st[j.src] = q.isPending ? "loading" : q.isError ? ((q.error as ApiError)?.status === 403 ? "locked" : "error") : "ok";
    if (q.data) (e.b as Record<string, unknown>)[j.src] = q.data;
    if (q.isError) e.err = (q.error as ApiError)?.status === 404 ? (isIndexSym(j.sym) ? "No history for this index." : "No data for this company in this build.") : "Could not load this company's data.";
    bundles.set(j.sym, e);
  });
  return bundles;
}

const RANK: Record<Plan, number> = { basic: 0, silver: 1, gold: 2 };
type RS = { sp: SeriesSpec; mt: Metric; ex: Extracted; label: string; color: string; sym: string; err?: string };
const name = (rows: [string, string][] | undefined, s: string) => rows?.find((r) => r[0] === s)?.[1] ?? s;

function Cell({ i, cell, view, bundles, active, onActive, onChange, onDrop, plan, c, names, picked }: { i: number; cell: CellSpec; view: View; bundles: ReturnType<typeof useBundles>; active: boolean; onActive: () => void; onChange: (n: CellSpec) => void; onDrop: (m: string) => void; plan: Plan; c: Colors; names: [string, string][] | undefined; picked: string[] }) {
  const { ref, w } = useWidth();
  const { upgrade } = useUI();
  const lim = graphLimits(plan);
  const multi = new Set(cell.series.map((s) => s.s)).size > 1;
  const rs: RS[] = cell.series.map((sp, k) => {
    const mt = metricFor(sp.s, BY_ID[sp.m]), bd = bundles.get(sp.s), ix = isIndexSym(sp.s), sname = ix ? indexCode(sp.s) : sp.s;
    const src: Src = ix && mt.id === "price" ? "ixl" : SRC_OF[mt.src], st = bd?.st[src];
    let ex = unsupportedWhy(sp.s, mt) ? { status: "unsupported" as const, pts: [], note: unsupportedWhy(sp.s, mt)! } : extract(mt, bd?.b ?? {}, view.basis, plan, st !== "loading");
    if (st === "error") ex = { status: "error", pts: [] };
    if (st === "locked" || (src === "ixv" && RANK[plan] < RANK[mt.tier])) ex = { status: "locked", pts: [] };
    return { sp, mt, ex: { ...ex, pts: mt.grain === "composition" ? ex.pts : windowPts(ex.pts, view.range, view.from) }, label: multi ? `${sname} · ${mt.label}` : mt.label, color: c.s[k % 8], sym: sp.s, err: bd?.err };
  });
  const bad = rs.find((r) => r.ex.status !== "ok");
  const ok = rs.filter((r) => r.ex.status === "ok");
  const comp = ok.some((r) => r.mt.grain === "composition");
  const facts: CellFacts = { n: ok.length, comp, mixedComp: comp && ok.some((r) => r.mt.grain !== "composition"), units: ok.map((r) => r.mt.unit), ratioUnits: ok.some((r) => r.mt.kind === "ratio"), maxPts: Math.max(0, ...ok.map((r) => r.ex.pts.length)), ohlc: ok.length === 1 && !!ok[0].ex.ohlc, priceOnly1: ok.length === 1 && ok[0].mt.id === "price", companies: new Set(ok.map((r) => r.sym)).size };
  const chk = chartCheck(cell.chart, facts, plan);
  const tfDefault = ["scatter", "heatmap"].includes(cell.chart) && ok.length > 0 && ok.every((r) => r.mt.grain === "price") ? "change" : "values";
  const tf = cell.tf ?? tfDefault;
  const asSet = (patch: Partial<CellSpec>) => onChange({ ...cell, ...patch });
  const title = rs.length === 0 ? `Chart ${i + 1}` : rs.length <= 2 ? rs.map((r) => r.label).join(" and ") : `${rs[0].label} and ${rs.length - 1} more`;

  // series for time charts, after the chosen transformation
  const ps: PS[] = ok.filter((r) => r.mt.grain !== "composition").flatMap((r): PS[] => {
    let pts = r.ex.pts, unit: UnitId = r.mt.unit;
    if (tf === "index") { const rb = rebase(pts); if (!rb || r.mt.kind === "ratio") return []; pts = rb; unit = "idx"; }
    else if (tf === "change" && ["line", "area", "column", "combo"].includes(cell.chart)) { const ch = changes(pts.map((p) => p.v), r.mt.kind); pts = pts.map((p, k) => ({ ...p, v: ch[k] })); unit = r.mt.kind === "amount" ? "pct" : r.mt.unit; }
    return [{ key: r.sp.s + r.sp.m, label: r.label, unit, pts, color: r.color, as: r.mt.grain === "price" ? "line" : (r.sp.as ?? "bar"), periodic: r.mt.grain === "periodic" }];
  });
  const comboPs = ps.map((p, k) => ({ ...p, as: cell.chart === "combo" ? (rs[k]?.sp.as ?? (k === 0 && p.periodic ? "bar" : "line")) : p.as })) as PS[];
  const align = useMemo(() => (["scatter", "heatmap"].includes(cell.chart) && ok.length ? alignSeries(ok.filter((r) => r.mt.grain !== "composition").map((r) => ({ pts: r.ex.pts, grain: r.mt.grain as "price" | "periodic" })), view.basis) : null), [cell.chart, ok.map((r) => r.sp.s + r.sp.m + r.ex.pts.length).join("|"), view.basis]);
  const tfCols = align ? align.cols.map((col, k) => (tf === "change" ? changes(col, ok[k].mt.kind) : col)) : [];
  const units = (k: number): UnitId => (tf === "change" && ok[k]?.mt.kind === "amount" ? "pct" : ok[k]?.mt.unit);

  let body: React.ReactNode = null;
  if (rs.length === 0) body = <div className="gx-empty"><Icon name="line" /><b>Drop a metric here</b><span>Or pick one from the list, or use “Add series” below.</span></div>;
  else if (bad && ok.length === 0) body = <div className="gx-note"><b>{bad.ex.status === "loading" ? "Loading…" : bad.ex.status === "locked" ? `${bad.mt.label} is part of the ${bad.mt.tier === "gold" ? "Gold" : "Silver"} plan.` : bad.ex.status === "unsupported" ? `${bad.mt.label} is not available for ${isIndexSym(bad.sym) ? "an index" : "a company"}. ${bad.ex.note ?? ""}` : bad.ex.status === "noperiod" ? `${bad.mt.label} is reported once a year. Switch to Annual to see it.` : bad.ex.status === "error" ? bad.err ?? "Could not load the data." : `No ${bad.mt.label} figures for ${isIndexSym(bad.sym) ? indexCode(bad.sym) : bad.sym}.`}</b>{bad.ex.status === "locked" && <button className="btn" onClick={() => upgrade(bad.mt.tier, `${bad.mt.label} history`)}>Unlock</button>}</div>;
  else if (!chk.ok) body = <div className="gx-note"><b>{CHART_LABEL[cell.chart]} does not fit this data</b><span>{chk.why}.</span><button className="btn ghost" onClick={() => asSet({ chart: comp ? "pie" : "line" })}>Show as {comp ? "pie" : "line"}</button></div>;
  else if (w > 0) {
    const k = cell.chart;
    if (k === "pie" || (comp && k === "bar")) { const r = ok[0]; const cats = r.ex.cats ?? []; body = k === "pie" ? <Pie cats={cats} unit={r.mt.unit} c={c} w={w} /> : <HBars rows={cats.map((x, n) => ({ key: x.name, label: x.name, v: x.value, color: c.s[n % 8], note: x.note }))} unit={r.mt.unit} c={c} w={w} />; }
    else if (k === "bar") body = <HBars rows={ok.map((r) => { const l = [...r.ex.pts].reverse().find((p) => p.v != null); return l ? { key: r.sp.s + r.sp.m, label: `${r.label} (${l.l ?? l.t})`, v: l.v as number, color: r.color } : null; }).filter(Boolean) as never} unit={ok[0].mt.unit} c={c} w={w} />;
    else if (k === "candlestick") body = <Candles pts={ok[0].ex.pts} c={c} w={w} />;
    else if (k === "scatter" && align) {
      const xi = Math.min(cell.x ?? 0, ok.length - 1), yi = Math.min(cell.y ?? 1, ok.length - 1), xs: number[] = [], ys: number[] = [], lb: string[] = [];
      align.dates.forEach((_, n) => { const a = tfCols[xi][n], b = tfCols[yi][n]; if (a != null && b != null) { xs.push(a); ys.push(b); lb.push(align.labels[n]); } });
      const pr = pearson(tfCols[xi], tfCols[yi]);
      body = xi === yi ? <div className="gx-note"><b>Pick two different series for X and Y.</b></div> : xs.length < 2 ? <div className="gx-note"><b>Not enough overlapping periods.</b><span>{pr.why}</span></div> : <>
        <Scatter xs={xs} ys={ys} labels={lb} xl={ok[xi].label} yl={ok[yi].label} xu={units(xi)} yu={units(yi)} r={pr.r} c={c} w={w} />
        <p className="gx-r">{pr.r != null ? <><b>Pearson r = {pr.r.toFixed(2).replace("-", "−")}</b> ({strength(pr.r)}) over {pr.n} {view.basis === "annual" ? "years" : "periods"}. </> : <>{pr.why} </>}{pr.r != null && pr.n < 6 && "Few points: treat it as a hint. "}{tf === "values" && pr.r != null && Math.abs(pr.r) > 0.8 && "Two rising series correlate even when unrelated; try “Period change”. "}Correlation shows that two measures moved together, not that one causes the other.{align.maxGap > 31 && ` Period ends differ by up to ${align.maxGap} days.`}</p></>;
    } else if (k === "heatmap" && align) {
      const mode = cell.mode ?? (ok.length > 1 ? "corr" : "grid");
      const labels = ok.map((r) => r.label);
      if (mode === "corr" && ok.length < 2) body = <div className="gx-note"><b>A correlation matrix needs two or more series.</b></div>;
      else if (mode === "grid" && align.dates.length > 24) body = <div className="gx-note"><b>Too many periods for a grid ({align.dates.length}).</b><span>Use Annual or Quarterly with a shorter range, or add a statement measure.</span></div>;
      else body = <><Heat mode={mode} labels={labels} matrix={mode === "corr" ? corrMatrix(tfCols) : undefined} grid={tfCols} cols={align.labels} units={ok.map((_, n) => units(n))} c={c} w={w} />
        {mode === "corr" && <p className="gx-r">Pearson r between each pair, using only the {align.dates.length} dates both have. Blue: move together. Red: move opposite. Not a cause.</p>}</>;
    } else if (ps.length) body = <TimeChart kind={k as "line"} series={k === "combo" ? comboPs : ps} c={c} w={w} />;
    else body = <div className="gx-note"><b>Nothing to draw.</b><span>Index to 100 needs a positive starting value and an amount, not a ratio.</span></div>;
  }
  const dualNote = ps.length > 1 && new Set(ps.map((p) => p.unit)).size === 2 && ["line", "area", "column", "combo"].includes(cell.chart);
  const csvOnly = ps.length > 0;

  return (
    <section className={"gx-cell" + (active ? " on" : "")} onClick={onActive} onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const m = e.dataTransfer.getData("text/plain"); if (BY_ID[m]) onDrop(m); }} aria-label={`Chart ${i + 1}: ${title}`}>
      <header><h3 title={title}>{title}</h3>
        <select aria-label={`Chart ${i + 1} type`} value={cell.chart} onChange={(e) => { const v = e.target.value as ChartKind; if (!lim.charts.includes(v)) upgrade(chartTier(v), `The ${CHART_LABEL[v]} chart`); else asSet({ chart: v }); }}>
          {CHARTS.map((k) => { const r = chartCheck(k, facts, plan); return <option key={k} value={k} disabled={!r.ok && k !== cell.chart && !!r.why && r.why !== "Not in your plan"}>{CHART_LABEL[k]}{!r.ok && r.why ? ` — ${r.why}` : ""}</option>; })}
        </select>
        <button className="gx-x" aria-label={`Clear chart ${i + 1}`} title="Clear this chart" onClick={(e) => { e.stopPropagation(); onChange({ chart: cell.chart, series: [] }); }}>×</button></header>
      <div className="gx-legend">{rs.map((r, n) => <span key={r.sp.s + r.sp.m} className="gx-chip"><i style={{ background: r.color }} />{r.label} <small>{UNITS[r.mt.unit].label}</small>
        {cell.chart === "combo" && r.mt.grain !== "price" && <button className="gx-mini" title="Switch between bars and line" onClick={() => onChange({ ...cell, series: cell.series.map((s, m) => (m === n ? { ...s, as: (s.as ?? (n === 0 ? "bar" : "line")) === "bar" ? "line" : "bar" } : s)) })}>{(r.sp.as ?? (n === 0 ? "bar" : "line")) === "bar" ? "bars" : "line"}</button>}
        {r.ex.status !== "ok" && <em title={r.ex.status}>{r.ex.status === "loading" ? "loading" : r.ex.status === "locked" ? "plan" : r.ex.status === "noperiod" ? "annual only" : r.ex.status === "unsupported" ? "n/a" : "no data"}</em>}
        <button aria-label={`Remove ${r.label}`} onClick={(e) => { e.stopPropagation(); onChange({ ...cell, series: cell.series.filter((_, m) => m !== n) }); }}>×</button></span>)}</div>
      {cell.chart === "scatter" && ok.length >= 2 && <div className="gx-xy"><label>X <select value={Math.min(cell.x ?? 0, ok.length - 1)} onChange={(e) => asSet({ x: +e.target.value })}>{ok.map((r, n) => <option key={n} value={n}>{r.label}</option>)}</select></label><label>Y <select value={Math.min(cell.y ?? 1, ok.length - 1)} onChange={(e) => asSet({ y: +e.target.value })}>{ok.map((r, n) => <option key={n} value={n}>{r.label}</option>)}</select></label></div>}
      {cell.chart === "heatmap" && ok.length >= 1 && <div className="gx-seg" role="group" aria-label="Heatmap kind">{(["corr", "grid"] as const).map((m) => <button key={m} aria-pressed={(cell.mode ?? (ok.length > 1 ? "corr" : "grid")) === m} onClick={() => asSet({ mode: m })}>{m === "corr" ? "Correlation" : "Period × measure"}</button>)}</div>}
      {ok.length > 0 && !comp && !["candlestick", "bar"].includes(cell.chart) && <div className="gx-seg" role="group" aria-label="Values or changes">{([["values", "Values"], ["change", "Period change"], ["index", "Index to 100"]] as const).map(([v, l]) => <button key={v} aria-pressed={tf === v} disabled={v === "index" && (facts.ratioUnits || ["scatter", "heatmap"].includes(cell.chart))} onClick={() => asSet({ tf: v })}>{l}</button>)}</div>}
      <div ref={ref} className="gx-body"><DrawLayer id={"gx:" + viewId(JSON.stringify([cell.chart, tf, cell.x, cell.y, cell.mode, view.range, view.from, view.basis, cell.series.map((x) => [x.s, x.m, x.as])]))} enabled={w > 0 && ok.length > 0 && chk.ok && (ps.length > 0 || !!align || comp || cell.chart === "candlestick" || cell.chart === "bar")}>{body}</DrawLayer></div>
      {dualNote && <p className="gx-r">Two units, so two axes: {[...new Set(ps.map((p) => p.unit))].map((u, n) => `${n ? "right" : "left"} ${UNITS[u].label}`).join(", ")}. Compare shapes, not heights.</p>}
      {csvOnly && ps.some((p) => p.pts.filter((x) => x.v != null).length < 3) && !["scatter", "heatmap"].includes(cell.chart) && <p className="gx-r faint">Few points in this window; widen the range or switch to Quarterly.</p>}
      <AddSeries onAdd={(m, s) => onDrop(m + "@" + s)} picked={picked} names={names} cell={cell} />
    </section>
  );
}

function AddSeries({ onAdd, picked, names, cell }: { onAdd: (m: string, s: string) => void; picked: string[]; names: [string, string][] | undefined; cell: CellSpec }) {
  const [m, setM] = useState(""), [s, setS] = useState(picked[0] ?? "");
  useEffect(() => { if (!picked.includes(s)) setS(picked[0] ?? ""); }, [picked, s]);
  return <form className="gx-add" onSubmit={(e) => { e.preventDefault(); if (m && s) { onAdd(m, s); setM(""); } }} onClick={(e) => e.stopPropagation()}>
    <select aria-label="Measure to add" value={m} onChange={(e) => setM(e.target.value)}><option value="">Add series…</option>{GROUPS.filter((g) => g.id !== "popular").map((g) => <optgroup key={g.id} label={g.label}>{metricsIn(g.id).map((x) => <option key={x.id} value={x.id}>{x.label} ({UNITS[x.unit].label})</option>)}</optgroup>)}</select>
    {picked.length > 1 && <select aria-label="Company" value={s} onChange={(e) => setS(e.target.value)}>{picked.map((p) => <option key={p} value={p}>{name(names, p)}</option>)}</select>}
    <button className="btn ghost" disabled={!m || !s || cell.series.length >= 9}>Add</button></form>;
}

export function GraphStudio() {
  useDocTitle("Graph Studio", "Put several graphs side by side: choose companies and measures, pick a chart type for each, and compare patterns and correlation.");
  const { user } = useAuth();
  const { plan, toast, upgrade } = useUI();
  const theme = useThemeKey();
  const lim = graphLimits(plan);
  const [sp, setSp] = useSearchParams();
  const [view, setView] = useState<View>(() => decodeView(sp.get("g"), plan) ?? defaultView(sp.get("c")?.split(",")[0]?.toUpperCase().match(/^[A-Z0-9&_.-]{1,24}$/)?.[0] ?? "RELIANCE"));
  const [companies, setCompanies] = useState<string[]>(() => [...new Set(view.cells.flatMap((c) => c.series.map((s) => s.s)))].slice(0, 6));
  const [active, setActive] = useState(0), [tab, setTab] = useState<"list" | "drag">("list"), [group, setGroup] = useState("popular"), [q, setQ] = useState(""), [cq, setCq] = useState("");
  const [panel, setPanel] = useState(() => (typeof window === "undefined" ? true : window.innerWidth >= 900));
  const idx = useSearchIndex(true);
  const feed = useIndices(true);
  const rows = useMemo(() => [...((idx.data?.rows as [string, string][] | undefined) ?? []), ...(feed.data?.items ?? []).map((x): [string, string] => [IDX + x.code, x.name])], [idx.data, feed.data]);
  const colors = useMemo(readColors, [theme]); // eslint-disable-line react-hooks/exhaustive-deps
  const count = Math.min(cellCount(view.layout), lim.cells);
  const bundles = useBundles(view, count, plan);
  const gridRef = useRef<HTMLDivElement>(null);
  const [views, setViews] = useState<Record<string, View>>(readLocal), [vname, setVname] = useState("");
  const clamp = (v: View) => sanitize(v, plan);

  useEffect(() => { // keep the address current so "Copy link" always shares what is on screen
    const t = window.setTimeout(() => setSp({ g: encodeView({ ...view, cells: view.cells.slice(0, count) }) }, { replace: true }), 400);
    return () => window.clearTimeout(t);
  }, [view, count, setSp]);
  useEffect(() => { // signed-in members keep views on the server; visitors keep them in this browser
    if (DEMO || !user) { setViews(readLocal()); return; }
    apiGet<{ views: { name: string; config: View }[] }>("/api/me/graph-views").then((r) => setViews(Object.fromEntries(r.views.map((x) => [x.name, clamp(x.config)])))).catch(() => setViews(readLocal()));
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (n: View) => setView(n);
  const setCell = (i: number, c: CellSpec) => { const cells = [...view.cells]; while (cells.length <= i) cells.push({ chart: "line", series: [] }); cells[i] = c; set({ ...view, cells }); };
  const cellOf = (i: number): CellSpec => view.cells[i] ?? { chart: "line", series: [] };
  const addTo = (i: number, mid: string, only?: string) => {
    const mt = BY_ID[mid], cell = cellOf(i); if (!mt) return;
    const syms = only ? [only] : companies.length ? companies : ["RELIANCE"];
    const isComp = mt.grain === "composition", hasComp = cell.series.some((s) => BY_ID[s.m]?.grain === "composition");
    if ((isComp && cell.series.length && !hasComp) || (!isComp && hasComp)) { toast("A breakdown (pie) can't share a chart with time series. Use another chart."); return; }
    let series = isComp ? [] : [...cell.series], added = 0;
    for (const s of isComp ? syms.slice(0, 1) : syms) { const why = unsupportedWhy(s, mt); if (why) { toast(`${mt.label} for ${isIndexSym(s) ? name(rows, s) : s}: ${why}`); continue; } if (isComp && isIndexSym(s)) { toast("Breakdowns are for companies."); continue; } if (series.some((x) => x.s === s && x.m === mid)) continue; if (series.length >= lim.series) { toast(`Your plan allows ${lim.series} series per chart.`); break; } series.push({ s, m: mid }); added++; }
    if (!added && !isComp) return;
    setCell(i, { ...cell, series, chart: isComp ? "pie" : cell.chart === "pie" ? "line" : cell.chart, x: undefined, y: undefined });
  };
  const toggle = (mid: string) => { const cell = cellOf(active); const has = cell.series.some((s) => s.m === mid); if (has) setCell(active, { ...cell, series: cell.series.filter((s) => s.m !== mid) }); else addTo(active, mid); };
  const nCo = (l: string[]) => l.filter((x) => !isIndexSym(x)).length;
  const addCompany = (s: string) => { if (companies.includes(s)) return; if (!isIndexSym(s) && nCo(companies) >= lim.companies) { upgrade(plan === "basic" ? "silver" : "gold", `Comparing more than ${lim.companies} companies`); return; } setCompanies([...companies, s]); setCq(""); };
  const removeCompany = (s: string) => { const left = companies.filter((x) => x !== s); setCompanies(left); set({ ...view, cells: view.cells.map((c) => ({ ...c, series: c.series.filter((x) => x.s !== s) })) }); };
  const hits = useMemo(() => { const n = cq.trim().toLowerCase(); if (n.length < 1) return []; const f = rows.filter((r) => r[0].toLowerCase().startsWith(n) || r[1].toLowerCase().includes(n)), ixs = f.filter((r) => isIndexSym(r[0])).slice(0, 3); return [...f.filter((r) => !isIndexSym(r[0])).slice(0, 8 - ixs.length), ...ixs]; }, [cq, rows]);
  const setLayout = (l: string) => { if (cellCount(l) > lim.cells) { upgrade(plan === "basic" ? "silver" : "gold", `Layouts with ${cellCount(l)} charts`); return; } set({ ...view, layout: l }); };

  const save = async () => {
    const nm = vname.trim(); if (!nm) { toast("Give the view a name first."); return; }
    const v = clamp({ ...view, cells: view.cells.slice(0, count) });
    if (!DEMO && user) { try { await apiSend("PUT", `/api/me/graph-views/${encodeURIComponent(nm)}`, { config: v }); setViews({ ...views, [nm]: v }); toast(`Saved “${nm}” to your account.`); setVname(""); return; } catch (e) { if (e instanceof ApiError && e.status === 403) { toast(e.body.detail || "Your plan's limit for saved views is reached."); return; } toast("Could not reach your account; saved in this browser instead."); } }
    if (Object.keys(views).length >= lim.views && !(nm in views)) { toast(`Your plan keeps ${lim.views} saved views.`); return; }
    const next = { ...readLocal(), [nm]: v }; writeLocal(next); setViews(next); setVname(""); toast(`Saved “${nm}” in this browser.`);
  };
  const load = (nm: string) => { const v = views[nm]; if (!v) return; set(clamp(v)); setCompanies([...new Set(v.cells.flatMap((c) => c.series.map((s) => s.s)))]); toast(`Loaded “${nm}”.`); };
  const del = async (nm: string) => { if (!DEMO && user) { try { await apiSend("DELETE", `/api/me/graph-views/${encodeURIComponent(nm)}`); } catch { return; } } else writeLocal(Object.fromEntries(Object.entries(readLocal()).filter(([k]) => k !== nm))); const { [nm]: _, ...rest } = views; setViews(rest); };
  const copy = () => { const u = `${location.origin}${location.pathname}?g=${encodeView({ ...view, cells: view.cells.slice(0, count) })}`; navigator.clipboard?.writeText(u).then(() => toast("Link to this view copied."), () => toast(u)); };

  const download = (blob: Blob, file: string) => { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = file; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); };
  const exportCsv = () => {
    const out = [csvRow(["chart", "chart_type", "company", "measure", "unit", "period_or_date", "value"])];
    view.cells.slice(0, count).forEach((cell, i) => cell.series.forEach((s) => { const mt0 = BY_ID[s.m], bd = bundles.get(s.s); if (!mt0 || !bd || unsupportedWhy(s.s, mt0)) return; const mt = metricFor(s.s, mt0); const ex = extract(mt, bd.b, view.basis, plan, true);
      (ex.cats ?? []).forEach((x) => out.push(csvRow([i + 1, cell.chart, s.s, mt.label, UNITS[mt.unit].name, x.name, x.value])));
      windowPts(ex.pts, view.range, view.from).forEach((p) => out.push(csvRow([i + 1, cell.chart, s.s, mt.label, UNITS[mt.unit].name, p.l && mt.grain === "periodic" ? p.l : p.t, p.v]))); }));
    download(new Blob([out.join("\n")], { type: "text/csv" }), "finlit-graphs.csv");
  };
  const exportPng = async () => {
    const cells = [...(gridRef.current?.querySelectorAll<HTMLElement>(".gx-cell") ?? [])]; if (!cells.length) return;
    const cols = LAYOUTS[view.layout].cols, cw = 640, ch = 420, rowsN = Math.ceil(cells.length / cols), cv = document.createElement("canvas"); cv.width = cols * cw; cv.height = rowsN * ch + 36;
    const g = cv.getContext("2d")!; g.fillStyle = colors.surface; g.fillRect(0, 0, cv.width, cv.height); g.font = "12px system-ui, sans-serif"; g.fillStyle = colors.muted; g.fillText("FinLit Graph Studio · information only, not investment advice", 14, 22);
    for (let n = 0; n < cells.length; n++) {
      const x0 = (n % cols) * cw, y0 = Math.floor(n / cols) * ch + 36, svg = cells[n].querySelector<SVGSVGElement>(".gx-body svg");
      g.fillStyle = colors.text; g.font = "600 15px system-ui, sans-serif"; g.fillText((cells[n].querySelector("h3")?.textContent ?? "").slice(0, 70), x0 + 14, y0 + 20);
      let lx = x0 + 14; g.font = "12px system-ui, sans-serif"; cells[n].querySelectorAll<HTMLElement>(".gx-chip").forEach((chip) => { const dot = chip.querySelector("i")?.style.background ?? "#888", t = (chip.childNodes[1]?.textContent ?? "").trim(); g.fillStyle = dot; g.fillRect(lx, y0 + 34, 14, 3); g.fillStyle = colors.text; g.fillText(t, lx + 20, y0 + 40); lx += 28 + g.measureText(t).width; });
      if (!svg) continue;
      const s = svg.cloneNode(true) as SVGSVGElement; s.setAttribute("xmlns", "http://www.w3.org/2000/svg"); s.setAttribute("font-family", "system-ui, sans-serif");
      const wv = +(svg.getAttribute("width") || 300), hv = +(svg.getAttribute("height") || 300); s.setAttribute("viewBox", `0 0 ${wv} ${hv}`);
      const img = new Image(); await new Promise<void>((res) => { img.onload = () => res(); img.onerror = () => res(); img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(s)); });
      const k = Math.min((cw - 28) / wv, (ch - 56) / hv); g.drawImage(img, x0 + 14, y0 + 50, wv * k, hv * k);
    }
    cv.toBlob((b) => b && download(b, "finlit-graphs.png"));
  };

  const needsLoad = [...bundles.values()].some((b) => Object.values(b.st).includes("loading"));
  const list = metricsIn(group, q), whyOff = (m: Metric) => (companies.length ? (companies.every((s) => unsupportedWhy(s, m)) ? unsupportedWhy(companies[0], m) : null) : null);
  const activeCell = cellOf(active);
  const co = LAYOUTS[view.layout];

  return (
    <>
      <section className="pagehead"><div className="wrap"><div className="eyebrow">Graph Studio</div><h1>Graphs, side by side.</h1>
        <p>Put several graphs next to each other to see patterns and correlation. Choose companies and measures, pick a chart type for each, and keep what you build.</p>
        <p className="gx-adv"><Link to="/graphs/advanced">Advanced charts</Link>: correlations across listed companies, with tested regression lines.</p></div></section>
      <div className="wrap gx">
        <aside className="gx-panel" aria-label="Choose companies and measures">
          <button className="btn ghost gx-toggle" aria-expanded={panel} onClick={() => setPanel(!panel)}>{panel ? "Hide" : "Choose"} companies and measures</button>
          <div hidden={!panel}>
            <h2>1. Companies</h2>
            <div className="gx-chips">{companies.map((s) => <span key={s} className="gx-chip">{name(rows, s)}{isIndexSym(s) && <small> Index</small>}<button aria-label={`Remove ${name(rows, s)}`} onClick={() => removeCompany(s)}>×</button></span>)}</div>
            <div className="gx-search"><label className="sr" htmlFor="gx-co">Add a company or index</label><input id="gx-co" value={cq} onChange={(e) => setCq(e.target.value)} placeholder={`Add a company or index (${nCo(companies)}/${lim.companies} companies)`} autoComplete="off" />
              {hits.length > 0 && <ul role="listbox" aria-label="Companies and indices">{hits.map((r) => <li key={r[0]} role="option" aria-selected={false}><button onClick={() => addCompany(r[0])}>{r[1]} <small>{isIndexSym(r[0]) ? "Index" : r[0]}</small></button></li>)}</ul>}</div>
            <h2>2. Measures</h2>
            <div className="gx-seg" role="tablist" aria-label="How to pick">{([["list", "Choose from list"], ["drag", "Drag & drop"]] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} aria-pressed={tab === k} onClick={() => setTab(k)}>{l}</button>)}</div>
            <p className="faint gx-hint">{tab === "list" ? <>Ticks apply to <b>Chart {active + 1}</b> (click a chart to change it).</> : "Drag a measure onto a chart, or use the Add menu on each row."}</p>
            <label className="sr" htmlFor="gx-q">Search measures</label><input id="gx-q" className="gx-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search measures (revenue, P/E, ROE…)" />
            {!q && <div className="gx-groups">{GROUPS.map((g) => <button key={g.id} aria-pressed={group === g.id} onClick={() => setGroup(g.id)}>{g.label}</button>)}</div>}
            <ul className="gx-list">{list.map((m) => { const on = activeCell.series.some((s) => s.m === m.id); return (
              <li key={m.id} draggable={!whyOff(m)} className={whyOff(m) ? "off" : undefined} onDragStart={(e) => { e.dataTransfer.setData("text/plain", m.id); e.dataTransfer.effectAllowed = "copy"; }} title={m.hint}>
                {tab === "list" ? <label><input type="checkbox" checked={on} disabled={!!whyOff(m)} onChange={() => toggle(m.id)} /><span>{m.label}</span></label> : <><span className="grip" aria-hidden="true">⋮⋮</span><span>{m.label}</span></>}
                {whyOff(m) && <small className="faint">{whyOff(m)}</small>}<small>{UNITS[m.unit].label}{m.tier !== "basic" && <> · {m.tier === "gold" ? "Gold" : "Silver"}</>}</small>
                {tab === "drag" && <select aria-label={`Add ${m.label} to a chart`} disabled={!!whyOff(m)} value="" onChange={(e) => { const n = +e.target.value; if (!Number.isNaN(n)) addTo(n, m.id); }}><option value="">Add to…</option>{Array.from({ length: count }, (_, n) => <option key={n} value={n}>Chart {n + 1}</option>)}</select>}
              </li>); })}{!list.length && <li className="faint">No measure matches.</li>}</ul>
          </div>
        </aside>
        <div className="gx-main">
          <div className="gx-bar">
            <div className="gx-seg" role="group" aria-label="Time range">{RANGES.map((r) => <button key={r.id} aria-pressed={!view.from && view.range === r.id} onClick={() => set({ ...view, range: r.id, from: undefined })}>{r.label}</button>)}</div>
            <label className="gx-yr">From year <select value={view.from ?? ""} onChange={(e) => set({ ...view, from: e.target.value ? Number(e.target.value) : undefined })}><option value="">Any</option>{Array.from({ length: new Date().getFullYear() - 2009 }, (_, i) => new Date().getFullYear() - i).map((y) => <option key={y} value={y}>{y}</option>)}</select></label>
            <div className="gx-seg" role="group" aria-label="Annual or quarterly">{(["annual", "quarterly"] as const).map((b) => <button key={b} aria-pressed={view.basis === b} onClick={() => set({ ...view, basis: b })}>{b === "annual" ? "Annual" : "Quarterly"}</button>)}</div>
            <div className="gx-seg" role="group" aria-label="Layout">{Object.keys(LAYOUTS).map((l) => <button key={l} aria-pressed={view.layout === l} aria-label={`Layout ${l.replace("x", " by ")}`} onClick={() => setLayout(l)}>{l.replace("x", "×")}{cellCount(l) > lim.cells && <Icon name="lock" />}</button>)}</div>
            <button className="btn ghost" onClick={copy}><Icon name="spark" />Copy link</button>
            <button className="btn ghost" onClick={exportPng}>PNG</button><button className="btn ghost" onClick={exportCsv}>CSV</button>
          </div>
          <div className="gx-bar gx-views">
            <label className="sr" htmlFor="gx-vn">View name</label><input id="gx-vn" value={vname} onChange={(e) => setVname(e.target.value)} maxLength={60} placeholder="Name this view" /><button className="btn ghost" onClick={save}>Save view</button>
            {Object.keys(views).length > 0 && <><label className="sr" htmlFor="gx-vl">Saved views</label><select id="gx-vl" value="" onChange={(e) => e.target.value && load(e.target.value)}><option value="">Load a saved view…</option>{Object.keys(views).map((n) => <option key={n} value={n}>{n}</option>)}</select>
              <select aria-label="Delete a saved view" value="" onChange={(e) => e.target.value && del(e.target.value)}><option value="">Delete…</option>{Object.keys(views).map((n) => <option key={n} value={n}>{n}</option>)}</select></>}
            <span className="faint">{DEMO || !user ? "Views are kept in this browser. Sign in to keep them in your account." : `${Object.keys(views).length}/${lim.views} saved in your account`}</span>
          </div>
          {needsLoad && <p className="faint" role="status">Loading company data…</p>}
          <div className="gx-grid" ref={gridRef} style={{ "--cols": co.cols } as React.CSSProperties}>
            {Array.from({ length: count }, (_, i) => <Cell key={i} i={i} cell={cellOf(i)} view={view} bundles={bundles} active={active === i} onActive={() => setActive(i)} plan={plan} c={colors} names={rows} picked={companies}
              onChange={(n) => setCell(i, n)} onDrop={(m) => (m.includes("@") ? addTo(i, m.split("@")[0], m.split("@")[1]) : addTo(i, m))} />)}
          </div>
          <p className="faint gx-foot">Figures are as reported by each company, in the units shown. Each series covers the chosen range back from its own latest reading. Information only; not advice to buy or sell.</p>
        </div>
      </div>
    </>
  );
}
