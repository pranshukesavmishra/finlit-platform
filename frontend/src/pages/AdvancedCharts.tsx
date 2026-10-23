// Graph Studio > Advanced charts: the founder's ten sections of correlation charts (docs/ADVANCED-CHARTS-SPEC.md), each with a tested
// regression line (docs/ADVANCED-CHARTS-PLAN.md). Every statistic comes from /api/advanced; this page only draws and words it.
import { DrawLayer } from "../components/DrawLayer";
import { viewId } from "../lib/drawings";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import { apiGet, useSearchIndex, ApiError, type Financials } from "../lib/api";
import { DEMO } from "../lib/demo";
import { Icon } from "../lib/icons";
import { RANK, useUI, type Plan } from "../lib/ui";
import { useDocTitle } from "../lib/title";
import { graphLimits } from "../lib/graphLimits";
import { rankMetrics } from "../lib/metricSearch";
import { rankCompanies } from "../lib/companySearch";
import { plFlags } from "../lib/plFlags";
import { ChartHelp } from "../components/ChartHelp";
import { useWidth } from "../components/GraphCharts";
import { AdvScatter, type ScMark, type ScFit, type ScPt, type ScSeries } from "../components/AdvScatter";
import {
  advSentence, ariaSummary, CAVEAT, cfoWarning, crossBody, crossCsv, decodeState, encodeState, fmtR, fmtUnit, fmtWhen, rounded, SECTIONS, sectionBySlug, SHAPES, sig3, tickUnit,
  useAdvCatalog, useCross, indexMarkers, INDEX_COLORS, INDEX_NOTE, MAX_INDICES, type IndexMarker, useFacets, useHistory, useTech, exportCsv,
  type AdvState, type AxisInfo, type Catalog, type CatMetric, type CatPair, type CrossResp, type Excluded, type HistResp, type Mode, type Scale, type Stats, type TechResp, type Tier,
} from "../lib/advanced";
import type { ChartHelpEntry } from "../lib/chartHelp";
import "../styles/advcharts.css";

const PRIORITY_1 = ["1.2", "1.9", "1.13", "1.19", "1.17"];   // section 1 "Priority checks", in the doc's order
const COLORS = ["var(--k1)", "var(--k2)", "var(--k3)", "var(--k4)", "var(--k5)", "var(--k7)"];
const MODE_LABEL: Record<Mode, string> = { cross: "Across companies", history: "Company history", tech: "Company time series" };
const TIER_NAME: Record<Tier, string> = { basic: "Basic", silver: "Silver", gold: "Gold" };
const nextPlan = (p: Plan): Plan => (p === "basic" ? "silver" : "gold");
const allowed = (plan: Plan, t: Tier | undefined) => RANK[plan] >= RANK[(t ?? "silver") as Plan];
const pairLabel = (p: { xLabel: string; yLabel: string }) => `${p.xLabel} vs ${p.yLabel}`;
const STATUS_CHIP: Record<string, string> = { ready: "Ready", adapted: "Adapted", unavailable: "Not available" };

/** (?) help for a pair: the doc's "What it helps analyse" text verbatim, plus both axis definitions from the catalogue. */
function helpFor(p: CatPair, cat: Catalog): ChartHelpEntry {
  const def = (id: string | null, label: string) => { const m = id ? cat.metrics[id] : null; return m ? `${label}. ${m.formula ?? ""}${m.source ? ` Source: ${m.source}.` : ""}`.trim() : label; };
  return {
    title: pairLabel(p),
    what: p.status === "unavailable" ? `Not available: ${p.reason ?? "the figures are not stored."}` : "Each dot is one company (or one year or window of one company in the company views): the first measure across, the second up. A straight line is drawn only when it passes every test; otherwise the page says why.",
    x: def(p.x, p.xLabel), y: def(p.y, p.yLabel),
    read: "A cloud that rises to the right means higher values of the first measure tend to go with higher values of the second; falling means lower. The shaded band is the 95% band for the fitted line, not a range for individual companies. Correlation is not causation.",
    why: p.help,
  };
}

export function AdvancedCharts() {
  const { section } = useParams();
  const sec = sectionBySlug(section);
  useDocTitle("Advanced charts", "Correlation charts across listed companies, with a regression line drawn only when it passes statistical tests. Information only, not advice.");
  if (!sec) return <Navigate to="/graphs/advanced/valuation" replace />;
  return <Page slug={sec.slug} n={sec.n} />;
}

function Page({ slug, n }: { slug: string; n: number }) {
  const { plan, upgrade } = useUI();
  const lim = graphLimits(plan);
  const [sp, setSp] = useSearchParams();
  const st = useMemo(() => decodeState(sp, lim.companies), [sp, lim.companies]);
  const set = (patch: Partial<AdvState>) => setSp(encodeState({ ...st, ...patch }), { replace: false });
  const cat = useAdvCatalog();
  const c = cat.data;
  const csec = c?.sections.find((s) => s.id === n);
  const pairs = useMemo(() => (csec && c ? csec.pairs.map((id) => c.pairs.find((p) => p.id === id)).filter((p): p is CatPair => !!p) : []), [c, csec]);
  const ordered = useMemo(() => (n === 1 ? [...pairs.filter((p) => PRIORITY_1.includes(p.id)).sort((a, b) => PRIORITY_1.indexOf(a.id) - PRIORITY_1.indexOf(b.id)), ...pairs.filter((p) => !PRIORITY_1.includes(p.id))] : pairs), [pairs, n]);
  const firstReady = ordered.find((p) => p.status !== "unavailable");
  const pair = st.pair === "custom" ? null : (pairs.find((p) => p.id === st.pair) ?? (st.pair ? c?.pairs.find((p) => p.id === st.pair) : undefined) ?? firstReady ?? null);
  const custom = st.pair === "custom";
  const unavailable = pairs.filter((p) => p.status === "unavailable");

  return (
    <>
      <section className="pagehead adv-head"><div className="wrap">
        <div className="eyebrow"><Link to="/graphs">Graph Studio</Link> · Advanced charts</div>
        <h1>Advanced charts</h1>
        <p>How two measures move together across listed companies, with a regression line drawn only when it passes statistical tests. Add companies to see where they sit. Information only, not advice.</p>
      </div></section>
      <div className="wrap adv">
        <SectionTabs current={slug} />
        <div role="tabpanel" id="adv-panel" aria-labelledby={`adv-tab-${slug}`} className="adv-panel">
          <header className="adv-sec">
            <h2>{n}. {c?.sections.find((s) => s.id === n)?.title ?? SECTIONS[n - 1].title}</h2>
            {csec?.intro && <p>{csec.intro}</p>}
            {csec?.note && <p className="adv-note">{csec.note}</p>}
          </header>
          {cat.isPending && <div className="adv-state" role="status">Loading the chart list…</div>}
          {cat.isError && <div className="adv-state" role="alert"><b>The chart list could not be loaded.</b> <button className="btn ghost" onClick={() => cat.refetch()}>Try again</button></div>}
          {c && <div className="adv-grid">
            <PairPicker pairs={ordered} priority={n === 1 ? PRIORITY_1 : []} current={custom ? "custom" : pair?.id ?? null} onPick={(id) => set({ pair: id, x: null, y: null, mode: "cross", variant: null, sx: null, sy: null, h: null })}
              alts={csec?.alternatives ?? []} onAlt={(a) => set({ pair: "custom", x: a.x, y: a.y, mode: "cross", universe: { ...st.universe, lenders: "only" } })} cat={c} st={st} onCustom={(x, y) => set({ pair: "custom", x, y, mode: "cross", sx: null, sy: null })} />
            <div className="adv-main">
              {custom ? (st.x && st.y && c.metrics[st.x] && c.metrics[st.y]
                ? <ChartCard key={`c:${st.x}:${st.y}`} cat={c} pair={null} xId={st.x} yId={st.y} st={st} set={set} plan={plan} upgrade={upgrade} section={n} />
                : <div className="adv-state">Choose two measures under “Your own pair”.</div>)
                : pair ? (pair.status === "unavailable"
                  ? <Unavailable p={pair} cat={c} />
                  : <ChartCard key={pair.id} cat={c} pair={pair} xId={pair.x!} yId={pair.y!} st={st} set={set} plan={plan} upgrade={upgrade} section={n} />)
                : <div className="adv-state">No chart in this section.</div>}
            </div>
          </div>}
          {c && unavailable.length > 0 && <details className="adv-na"><summary>Not available in this section ({unavailable.length})</summary>
            <ul>{unavailable.map((p) => <li key={p.id}><b>{p.id} {pairLabel(p)}</b><span>{p.reason ?? "The figures are not stored."}</span></li>)}</ul></details>}
        </div>
        {c && <CannotChart cat={c} />}
        <p className="adv-foot faint">{c?.coverageNote ?? "Only companies with a stored full report are charted: mostly the largest listed companies."} {CAVEAT}</p>
      </div>
    </>
  );
}

/** Ten section tabs: arrow keys, Home and End move between them; the address is the source of truth. Under 600 px a labelled select. */
// The layout remounts the page on every path change (its error boundary is keyed by the path), so a tab reached with the keyboard is
// focused again after the new section mounts.
let refocusTab = false;
function SectionTabs({ current }: { current: string }) {
  const nav = useNavigate();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => { if (refocusTab) { refocusTab = false; refs.current[SECTIONS.findIndex((s) => s.slug === current)]?.focus(); } }, [current]);
  const go = (slug: string) => nav(`/graphs/advanced/${slug}`);
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const k = e.key, last = SECTIONS.length - 1;
    const j = k === "ArrowRight" ? (i + 1) % SECTIONS.length : k === "ArrowLeft" ? (i - 1 + SECTIONS.length) % SECTIONS.length : k === "Home" ? 0 : k === "End" ? last : -1;
    if (j < 0) return;
    e.preventDefault(); refs.current[j]?.focus(); refocusTab = true; go(SECTIONS[j].slug);
  };
  return <>
    <div className="adv-tabs" role="tablist" aria-label="Chart sections">
      {SECTIONS.map((s, i) => <button key={s.slug} ref={(el) => { refs.current[i] = el; }} role="tab" id={`adv-tab-${s.slug}`} aria-selected={s.slug === current} aria-controls="adv-panel" tabIndex={s.slug === current ? 0 : -1}
        onClick={() => go(s.slug)} onKeyDown={(e) => onKey(e, i)}><span className="adv-tn">{s.n}</span>{s.label}</button>)}
    </div>
    <label className="adv-tabsel"><span>Section</span>
      <select value={current} onChange={(e) => go(e.target.value)}>{SECTIONS.map((s) => <option key={s.slug} value={s.slug}>{s.n}. {s.title}</option>)}</select></label>
  </>;
}

function PairPicker({ pairs, priority, current, onPick, alts, onAlt, cat, st, onCustom }: {
  pairs: CatPair[]; priority: string[]; current: string | null; onPick: (id: string) => void;
  alts: { id: string; xLabel: string; yLabel: string; x: string; y: string; label?: string; help?: string }[]; onAlt: (a: { x: string; y: string }) => void;
  cat: Catalog; st: AdvState; onCustom: (x: string, y: string) => void;
}) {
  const pri = pairs.filter((p) => priority.includes(p.id)), rest = pairs.filter((p) => !priority.includes(p.id));
  const altCur = current === "custom" ? alts.find((a) => a.x === st.x && a.y === st.y) : undefined;
  const opt = (p: CatPair) => <option key={p.id} value={p.id}>{p.id} {pairLabel(p)}{p.status !== "ready" ? ` (${STATUS_CHIP[p.status]})` : ""}</option>;
  const row = (p: CatPair) => <li key={p.id}>
    <button className={"adv-pair" + (p.status === "unavailable" ? " na" : "")} aria-current={current === p.id ? "true" : undefined} onClick={() => onPick(p.id)}>
      <span className="adv-pid">{p.id}</span><span className="adv-pl">{pairLabel(p)}</span>
      <span className={"adv-st " + p.status}>{STATUS_CHIP[p.status]}</span></button>
    <ChartHelp id={`adv-${p.id}`} entry={helpFor(p, cat)} label={`About ${pairLabel(p)}`} />
  </li>;
  return <aside className="adv-picker" aria-label="Choose a chart">
    <label className="adv-pairsel"><span>Chart</span>
      <select value={altCur ? `alt:${altCur.id}` : current ?? ""} onChange={(e) => { const v = e.target.value; const a = alts.find((x) => `alt:${x.id}` === v); if (a) onAlt(a); else if (v && v !== "custom") onPick(v); }}>
        {current === "custom" && !altCur && <option value="custom">Your own pair</option>}
        {pri.length > 0 && <optgroup label="Priority checks">{pri.map(opt)}</optgroup>}
        {pri.length > 0 ? <optgroup label="All charts in this section">{rest.map(opt)}</optgroup> : rest.map(opt)}
        {alts.length > 0 && <optgroup label="Available for lenders">{alts.map((a) => <option key={a.id} value={`alt:${a.id}`}>{a.id} {a.xLabel} vs {a.yLabel}</option>)}</optgroup>}</select></label>
    <div className="adv-pairlist">
      {pri.length > 0 && <><h3>Priority checks</h3><ul>{pri.map(row)}</ul><h3>All charts in this section</h3></>}
      <ul>{rest.map(row)}</ul>
    </div>
    {alts.length > 0 && <div className="adv-alts"><h3>Available for lenders</h3><ul>{alts.map((a) => <li key={a.id}><button className="adv-pair" aria-current={current === "custom" && st.x === a.x && st.y === a.y ? "true" : undefined} onClick={() => onAlt(a)}>
      <span className="adv-pid">{a.id}</span><span className="adv-pl">{a.xLabel} vs {a.yLabel}</span><span className="adv-st adapted">{a.label ?? "Lenders"}</span></button></li>)}</ul></div>}
    <CustomPair cat={cat} st={st} onPick={onCustom} />
  </aside>;
}

/** "Your own pair": two typo-tolerant searches over the whitelisted metrics (the server checks the ids again). */
function CustomPair({ cat, st, onPick }: { cat: Catalog; st: AdvState; onPick: (x: string, y: string) => void }) {
  const items = useMemo(() => Object.entries(cat.metrics).map(([key, m]) => ({ key, label: m.label })), [cat]);
  const [x, setX] = useState(st.x ?? ""), [y, setY] = useState(st.y ?? "");
  return <details className="adv-custom" open={st.pair === "custom"}><summary>Your own pair</summary>
    <MetricField label="Across (X)" items={items} value={x} onChange={setX} />
    <MetricField label="Up (Y)" items={items} value={y} onChange={setY} />
    <button className="btn ghost" disabled={!x || !y || x === y} onClick={() => onPick(x, y)}>Draw</button>
    {x && y && x === y && <p className="faint">Pick two different measures.</p>}
  </details>;
}

function MetricField({ label, items, value, onChange }: { label: string; items: { key: string; label: string }[]; value: string; onChange: (k: string) => void }) {
  const [q, setQ] = useState(""), [open, setOpen] = useState(false), [act, setAct] = useState(0);
  const hits = useMemo(() => rankMetrics(items, q).slice(0, 8), [items, q]);
  const cur = items.find((i) => i.key === value);
  const id = `adv-m-${label.replace(/\W+/g, "")}`;
  const pick = (k: string) => { onChange(k); setQ(""); setOpen(false); };
  return <div className="adv-field adv-combo">
    <label htmlFor={id}>{label}{cur && <b> {cur.label}</b>}</label>
    <input id={id} role="combobox" aria-expanded={open && hits.length > 0} aria-controls={`${id}-l`} aria-autocomplete="list" autoComplete="off" value={q} placeholder="Search measures (P/E, ROE, growth…)"
      aria-activedescendant={open && hits[act] ? `${id}-o${act}` : undefined}
      onChange={(e) => { setQ(e.target.value); setOpen(true); setAct(0); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
      onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setAct((a) => Math.min(hits.length - 1, a + 1)); } else if (e.key === "ArrowUp") { e.preventDefault(); setAct((a) => Math.max(0, a - 1)); } else if (e.key === "Enter" && hits[act]) { e.preventDefault(); pick(hits[act].key); } else if (e.key === "Escape") { setQ(""); setOpen(false); } }} />
    {open && q && <ul id={`${id}-l`} role="listbox" aria-label={label}>{hits.map((h, i) => <li key={h.key} id={`${id}-o${i}`} role="option" aria-selected={i === act} onMouseDown={(e) => { e.preventDefault(); pick(h.key); }}>{h.label}</li>)}
      {!hits.length && <li className="faint" role="option" aria-selected={false} aria-disabled="true">No measure matches.</li>}</ul>}
  </div>;
}

function Unavailable({ p, cat }: { p: CatPair; cat: Catalog }) {
  return <section className="adv-card" aria-labelledby="adv-ct">
    <header className="adv-ch"><h3 id="adv-ct">{pairLabel(p)}</h3><ChartHelp id={`adv-u-${p.id}`} entry={helpFor(p, cat)} /></header>
    <div className="adv-lock"><b>Not available</b><p>{p.reason ?? "The figures this chart needs are not stored."}</p><p className="faint">What it would help analyse: {p.help}</p></div>
  </section>;
}

/** The whole-site list of charts we cannot draw, with the reason for each. */
function CannotChart({ cat }: { cat: Catalog }) {
  const na = cat.pairs.filter((p) => p.status === "unavailable");
  if (!na.length) return null;
  return <details className="adv-na adv-all"><summary>What we cannot chart and why ({na.length} of {cat.pairs.length})</summary>
    <ul>{na.map((p) => <li key={p.id}><b>{p.id} {pairLabel(p)}</b><span>{p.reason ?? "The figures are not stored."}</span></li>)}</ul></details>;
}

// ------------------------------------------------------------------ the chart card

type CardProps = { cat: Catalog; pair: CatPair | null; xId: string; yId: string; st: AdvState; set: (p: Partial<AdvState>) => void; plan: Plan; upgrade: (t: Plan, why?: string) => void; section: number };

function ChartCard({ cat, pair, xId, yId, st, set, plan, upgrade, section }: CardProps) {
  const mx = cat.metrics[xId], my = cat.metrics[yId];
  const modes: Mode[] = pair?.modes?.length ? pair.modes : ["cross"];
  const mode: Mode = modes.includes(st.mode) ? st.mode : modes[0];
  const tier = pair?.tier?.[mode] ?? (mode === "tech" ? "gold" : "silver");
  const variant = pair?.variants.find((v) => v.id === st.variant) ?? null;
  const needTier: Tier = variant && RANK[variant.tier as Plan] > RANK[tier as Plan] ? variant.tier : tier;
  const open = allowed(plan, needTier);
  const lim = graphLimits(plan);
  const scaleOf = (axis: "x" | "y"): Scale => { const want = axis === "x" ? st.sx : st.sy, ok = pair ? !!pair.logOk?.[axis] : !!(axis === "x" ? mx : my)?.logOk; const def = pair?.scale?.[axis] ?? "lin"; return want === "log" && ok ? "log" : want === "lin" ? "lin" : def; };
  const scale = { x: scaleOf("x"), y: scaleOf("y") };
  const title = pair ? pairLabel(pair) : `${mx.label} vs ${my.label}`;
  const [table, setTable] = useState(false);
  const mech = pair?.mechanical;
  const notes = [...new Set([...(pair?.notes ?? [])])];

  return <section className="adv-card" aria-labelledby="adv-ct">
    <header className="adv-ch">
      <h3 id="adv-ct">{title}</h3>
      {pair && <ChartHelp id={`adv-c-${pair.id}`} entry={helpFor(pair, cat)} label={`About ${title}`} />}
      {pair && pair.status === "adapted" && <span className="adv-st adapted">Adapted</span>}
    </header>
    {pair?.status === "adapted" && pair.reason && <p className="adv-banner bi">{pair.reason}</p>}
    {pair?.sameAs && <p className="adv-banner bi">This is the same chart as {pair.sameAs}: the two rows of the founder's table use identical definitions here.</p>}
    {mech && <p className="adv-banner bw"><Icon name="spark" /> {mech}</p>}

    <div className="adv-controls">
      {modes.length > 1 && <div className="adv-seg" role="group" aria-label="View">{modes.map((m) => { const t = pair?.tier?.[m]; const ok = allowed(plan, t);
        return <button key={m} aria-pressed={mode === m} onClick={() => set({ mode: m })}>{MODE_LABEL[m]}{!ok && <Icon name="lock" />}</button>; })}</div>}
      {pair && pair.variants.length > 0 && mode === "cross" && <div className="adv-seg" role="group" aria-label="Timing">
        <button aria-pressed={!variant} onClick={() => set({ variant: null })}>Same financial year</button>
        {pair.variants.map((v) => <button key={v.id} aria-pressed={variant?.id === v.id} onClick={() => set({ variant: v.id })}>{v.label}{!allowed(plan, v.tier) && <Icon name="lock" />}</button>)}</div>}
      {mode !== "tech" && (["x", "y"] as const).map((a) => { const ok = pair ? !!pair.logOk?.[a] : !!(a === "x" ? mx : my)?.logOk; if (!ok) return null;
        return <div key={a} className="adv-seg" role="group" aria-label={`${a === "x" ? "Across" : "Up"} axis scale`}>{(["lin", "log"] as const).map((s) => <button key={s} aria-pressed={scale[a] === s} onClick={() => set(a === "x" ? { sx: s } : { sy: s })}>{a.toUpperCase()} {s === "lin" ? "linear" : "log"}</button>)}</div>; })}
      {pair?.alt && <button className="adv-link" onClick={() => set({ pair: "custom", x: pair.alt!.x, y: pair.alt!.y, mode: "cross" })}>{pair.alt.label}</button>}
    </div>

    {!open ? <Locked tier={needTier} what={variant ? variant.label : MODE_LABEL[mode]} upgrade={upgrade} />
      : mode === "cross" ? <CrossView cat={cat} pair={pair} xId={xId} yId={yId} st={st} set={set} scale={scale} table={table} lim={lim.companies} plan={plan} upgrade={upgrade} title={title} section={section} />
      : mode === "history" ? <HistoryView cat={cat} pair={pair} xId={xId} yId={yId} st={st} set={set} table={table} lim={lim.companies} plan={plan} upgrade={upgrade} section={section} />
      : <TechView cat={cat} pair={pair!} st={st} set={set} table={table} plan={plan} upgrade={upgrade} />}

    {open && <label className="adv-check"><input type="checkbox" checked={table} onChange={(e) => setTable(e.target.checked)} /> Show as table</label>}
    {notes.length > 0 && <ul className="adv-notes">{notes.map((t) => <li key={t}>{t}</li>)}</ul>}
    <Defs mx={mx} my={my} />
  </section>;
}

function Locked({ tier, what, upgrade }: { tier: Tier; what: string; upgrade: (t: Plan, why?: string) => void }) {
  return <div className="adv-lock"><Icon name="lock" /><b>{what} is part of the {TIER_NAME[tier]} plan.</b>
    <p>The list of charts, their help and the reasons some cannot be drawn are open to everyone. Drawing them needs {TIER_NAME[tier]}.</p>
    <button className="btn primary" onClick={() => upgrade(tier as Plan, `Advanced charts (${what})`)}>See {TIER_NAME[tier]}</button></div>;
}

function Defs({ mx, my }: { mx?: CatMetric; my?: CatMetric }) {
  if (!mx && !my) return null;
  return <details className="adv-defs"><summary>How these measures are defined</summary><dl>
    {[mx, my].filter(Boolean).map((m) => <div key={m!.label}><dt>{m!.label}</dt><dd>{m!.formula ?? "—"}{m!.source ? <> <span className="faint">Source: {m!.source}.</span></> : null}{m!.lenders === "excluded" ? <> <span className="faint">Not used for banks and lenders.</span></> : null}</dd></div>)}
  </dl></details>;
}

/** Shared bits of the three views. */
const unitOf = (a: AxisInfo | undefined, m: CatMetric | undefined) => a?.unit ?? m?.unit;
const shortOf = (a: AxisInfo | undefined, m: CatMetric | undefined) => m?.short ?? a?.label ?? m?.label ?? "";
function errText(e: ApiError | null): string {
  if (!e) return "";
  if (e.status === 403 && e.body.status === "plan_limit") return e.body.detail || "More companies than your plan allows.";
  if (e.status === 403) return e.body.detail || "This chart is part of a higher plan.";
  if (e.status === 404) return e.body.detail || "This chart is not known to the server.";
  if (e.status === 400) return e.body.detail || "The server could not draw this combination.";
  return e.body.detail || "The chart could not be loaded. Please try again.";
}

function StatsPanel({ stats, sentence, method, extra }: { stats: Stats | null; sentence: string; method?: string; extra?: ReactNode }) {
  const R = stats ? rounded(stats) : null;
  const ci = (v: [number, number] | null | undefined, f: (n: number) => string) => (v ? `${f(v[0])} to ${f(v[1])}` : "—");
  return <div className="adv-stats">
    <p className="adv-sentence">{sentence}</p>
    {stats && R && <details className="adv-allstats"><summary>All statistics</summary>
      <table><tbody>
        <tr><th scope="row">Points used (n)</th><td>{stats.n.toLocaleString("en-IN")}</td></tr>
        <tr><th scope="row">Pearson r</th><td>{R.r}{stats.pearson?.ci ? <span className="faint"> (95% interval {ci(stats.pearson.ci, (v) => fmtR(v))})</span> : null}</td></tr>
        <tr><th scope="row">p-value (Pearson)</th><td>{R.p}</td></tr>
        <tr><th scope="row">Spearman rho</th><td>{R.rho}{stats.spearman?.p != null ? <span className="faint"> (p {stats.spearman.p < 0.001 ? "< 0.001" : `= ${stats.spearman.p.toPrecision(3)}`})</span> : null}</td></tr>
        <tr><th scope="row">Share of variation explained (R²)</th><td>{R.r2pct}</td></tr>
        <tr><th scope="row">Slope (Y per 1 X)</th><td>{R.slope}{stats.ols?.ci ? <span className="faint"> (95% interval {ci(stats.ols.ci, sig3)})</span> : null}</td></tr>
        <tr><th scope="row">Intercept</th><td>{sig3(stats.ols?.intercept)}</td></tr>
        <tr><th scope="row">Robust (Theil-Sen) slope</th><td>{stats.theilSen ? sig3(stats.theilSen.slope) : "— (every X is equal)"}</td></tr>
        {stats.influence?.max && <tr><th scope="row">Most influential point</th><td>{stats.influence.max.name || stats.influence.max.label || stats.influence.max.s}{stats.influence.without ? <span className="faint"> (without it: r {fmtR(stats.influence.without.r)}, slope {sig3(stats.influence.without.slope)})</span> : null}</td></tr>}
        {stats.curvature?.p != null && <tr><th scope="row">Curvature test p</th><td>{stats.curvature.p < 0.001 ? "< 0.001" : stats.curvature.p.toPrecision(3)}</td></tr>}
        <tr><th scope="row">Line decision</th><td>{stats.decision.text}</td></tr>
        {stats.space && (stats.space.x === "log" || stats.space.y === "log") && <tr><th scope="row">Computed on</th><td>{stats.space.x === "log" ? "log10 of X" : "X"} and {stats.space.y === "log" ? "log10 of Y" : "Y"} (Spearman is the same on either scale)</td></tr>}
      </tbody></table>
      {method && <p className="faint">{method}</p>}
    </details>}
    {extra}
  </div>;
}

function ExcludedList({ items, total }: { items: Excluded[]; total?: number }) {
  const left = items.reduce((s, e) => s + e.count, 0);
  if (!left) return null;
  return <details className="adv-excl"><summary>{left.toLocaleString("en-IN")} left out{total != null ? ` of ${total.toLocaleString("en-IN")}` : ""}: why</summary>
    <ul>{items.filter((e) => e.count > 0).map((e, i) => <li key={e.code + i}><b>{e.count.toLocaleString("en-IN")}</b> {e.axis ? <span className="faint">({e.axis === "x" ? "across" : "up"}) </span> : null}{e.text}</li>)}</ul></details>;
}

function Caveats({ list }: { list: string[] }) {
  const all = [...new Set([...list, "Correlation is not causation.", "Information only, not advice."])];
  return <ul className="adv-caveats" aria-label="Caveats">{all.map((t) => <li key={t}>{t}</li>)}</ul>;
}

// ------------------------------------------------------------------ cross-section

function CrossView({ cat, pair, xId, yId, st, set, scale, table, lim, plan, upgrade, title, section }: { cat: Catalog; pair: CatPair | null; xId: string; yId: string; st: AdvState; set: (p: Partial<AdvState>) => void; scale: { x: Scale; y: Scale }; table: boolean; lim: number; plan: Plan; upgrade: (t: Plan, why?: string) => void; title: string; section: number }) {
  const body = useMemo(() => crossBody({ ...st, x: xId, y: yId }, pair, scale), [st, xId, yId, pair, scale.x, scale.y]); // eslint-disable-line react-hooks/exhaustive-deps
  const q = useCross(body, true);
  const { ref, w } = useWidth();
  const r = q.data;
  const mx = cat.metrics[xId], my = cat.metrics[yId];
  const ux = unitOf(r?.x, mx), uy = unitOf(r?.y, my);
  const hiSet = new Set(r?.highlights.filter((h) => h.status === "included").map((h) => h.s) ?? []);
  const cloud: ScPt[] = r ? r.points.filter((p) => !hiSet.has(p.s)).map((p) => ({ key: p.s, label: p.name || p.s, x: p.x, y: p.y, note: [p.sector, p.fy].filter(Boolean).join(" · ") || undefined })) : [];
  const series: ScSeries[] = r ? st.companies.map((s, i): ScSeries | null => { const h = r.highlights.find((x) => x.s === s); if (!h || h.x == null || h.y == null || (h.status !== "included" && h.status !== "outside")) return null;
    return { key: s, name: h.name || s, color: COLORS[i % COLORS.length], shape: SHAPES[i % SHAPES.length], hollow: h.status === "outside", pts: [{ key: s, label: h.name || s, x: h.x, y: h.y, note: h.status === "outside" ? "Outside the filters: not part of the statistics." : h.fy ?? undefined }] }; }).filter((x): x is ScSeries => !!x) : [];
  const fits = fitsOf(r?.stats ?? null, "all");
  const ixm = r ? indexMarkers(r.indices, st.indices, (r.x.scale ?? scale.x) as Scale, (r.y.scale ?? scale.y) as Scale, (v) => fmtUnit(v, ux, mx?.digits), (v) => fmtUnit(v, uy, my?.digits), r.x.label, r.y.label) : [];
  const marks: ScMark[] = ixm.filter((m) => m.drawn).map((m) => ({ key: "ix:" + m.code, label: m.label, color: m.color, x: m.x!, y: m.y!, lines: m.lines }));
  const left = r ? r.excluded.reduce((s, e) => s + e.count, 0) : 0;
  const sentence = r ? advSentence(r.stats, { kind: "cross", who: "companies", x: { short: shortOf(r.x, mx), unit: ux! }, y: { short: shortOf(r.y, my), unit: uy! }, left, total: r.universeTotal, fy: r.fyBreakdown, builtAt: r.tableBuiltAt, indices: ixm.length > 0 }) : "";
  const xs = (r?.x.scale ?? scale.x) as Scale, ys = (r?.y.scale ?? scale.y) as Scale;
  const fx = (v: number) => fmtUnit(v, ux, mx?.digits), fy = (v: number) => fmtUnit(v, uy, my?.digits);
  const lenderMsg = r?.lenders && r.lenders.count > 0 && r.lenders.mode === "excluded" ? `${r.lenders.count.toLocaleString("en-IN")} banks and lenders left out: ${r.lenders.forced ? "these ratios do not apply to lenders" : "as chosen in the filters"}.` : null;

  return <>
    {r?.sample && <p className="adv-banner bi">Demo preview: sample companies with made-up figures (marked “Sample”), not real data. The statistics are computed from them with the same formulas as the live site.</p>}
    {lenderMsg && <p className="adv-banner bi">{lenderMsg}</p>}
    {r?.preset && <p className="adv-banner bi">Filtered to {r.preset.label}.</p>}
    <div ref={ref} className="adv-body" aria-busy={q.isFetching}><DrawLayer id={"adv:" + viewId(JSON.stringify([section, body, scale, st.all]))} enabled={!!r && r.n > 0 && !table && w > 0}>
      {q.isPending ? <div className="adv-state" role="status">Working out the chart…</div>
        : q.isError ? <div className="adv-state" role="alert"><b>{errText(q.error)}</b>{q.error.status === 403 && <button className="btn primary" onClick={() => upgrade((q.error.body.plan as Plan) || nextPlan(plan), title)}>See plans</button>}</div>
        : r && w > 0 ? <>
          {r.n === 0 && <div className="adv-state">No company has both figures for this selection.</div>}
          {r.n > 0 && !table && <AdvScatter cloud={cloud} series={series} fits={fits} sx={xs} sy={ys} xLabel={r.x.label} yLabel={r.y.label} fmtX={fx} fmtY={fy} tickX={(v) => tickUnit(v, ux)} tickY={(v) => tickUnit(v, uy)}
            all={st.all} w={w} view={r.view} marks={marks} summary={ariaSummary(r.stats, r.x.label, r.y.label, r.n, "companies") + (marks.length ? ` Index markers: ${marks.map((m) => m.label).join(", ")}; reference points, not part of the fitted line.` : "")} />}
          {r.n > 0 && table && <PointsTable head={["Company", "Sector", "Year", r.x.label, r.y.label]} rows={[...ixm.map((m) => [`${m.label} (index reference, not in the statistics)`, "—", "—", r.indices?.find((i) => i.code === m.code)?.x != null ? fx(r.indices!.find((i) => i.code === m.code)!.x!) : `— ${m.why ?? ""}`.trim(), r.indices?.find((i) => i.code === m.code)?.y != null ? fy(r.indices!.find((i) => i.code === m.code)!.y!) : `— ${m.why ?? ""}`.trim()]), ...r.points.map((p) => [p.name || p.s, p.sector ?? "—", p.fy ?? "—", fx(p.x), fy(p.y)])]} caption={`${title}: ${r.n} companies used in the statistics${ixm.length ? "; index rows are reference points" : ""}`} />}
          {r.n > 0 && !table && <div className="adv-viewbar">
            <label className="adv-check"><input type="checkbox" checked={st.all} onChange={(e) => set({ all: e.target.checked })} /> Show every point (the window otherwise covers the 1st to 99th percentile)</label>
            <Legend fits={fits} indices={marks.length > 0} />
          </div>}
          {ixm.some((m) => !m.drawn) && <ul className="adv-ixmiss">{ixm.filter((m) => !m.drawn).map((m) => <li key={m.code}><b>{m.label}</b>: not drawn — {m.why}</li>)}</ul>}
        </> : null}
    </DrawLayer></div>
    <Companies st={st} set={set} lim={lim} plan={plan} upgrade={upgrade} status={r?.highlights ?? []} mode="cross" />
    <IndexPicker cat={cat} st={st} set={set} markers={ixm} />
    {r && <StatsPanel stats={r.stats} sentence={sentence} method={r.method} extra={<>
      <ExcludedList items={r.excluded} total={r.universeTotal} />
      {r.coverage && <p className="adv-cov faint">{r.coverage.withReport.toLocaleString("en-IN")} companies with a stored report out of {r.coverage.listed.toLocaleString("en-IN")} listed, mostly the largest.{r.tableBuiltAt ? ` Table built ${fmtWhen(r.tableBuiltAt)}.` : ""}</p>}
      {[...new Set(r.notes)].length > 0 && <ul className="adv-notes">{[...new Set(r.notes)].filter((t) => t !== pair?.mechanical).map((t) => <li key={t}>{t}</li>)}</ul>}
      <Caveats list={r.caveats} />
      <ExportBtn plan={plan} upgrade={upgrade} body={{ mode: "cross", ...body }} demo={() => crossCsv(r, title)} name={pair?.id ?? `${xId}-${yId}`} />
    </>} />}
    {!r && !q.isPending && <Caveats list={[]} />}
    <Filters st={st} set={set} pair={pair} resp={r} />
    {section === 9 && <PlWarnings symbols={st.companies} />}
  </>;
}

function fitsOf(stats: Stats | null, key: string, color?: string): ScFit[] {
  if (!stats || stats.decision.line === "none" || !stats.line) return [];
  const out: ScFit[] = [{ key: key + "ols", kind: "ols", line: stats.line, band: stats.band, color }];
  if (stats.decision.line === "ols_ts" && stats.tsLine) out.push({ key: key + "ts", kind: "ts", line: stats.tsLine, color });
  return out;
}

function Legend({ fits, indices }: { fits: ScFit[]; indices?: boolean }) {
  return <ul className="adv-legend" aria-label="Key">
    <li><i className="k-pt" />One company</li>
    {fits.some((f) => f.kind === "ols") && <li><i className="k-ols" />Straight (OLS) line, with its 95% band for the line</li>}
    {fits.some((f) => f.kind === "ts") && <li><i className="k-ts" />Robust (Theil-Sen) line</li>}
    <li><i className="k-edge" />Outside the window</li>
    {indices && <li><i className="k-ix" />{INDEX_NOTE}</li>}
  </ul>;
}

function PointsTable({ head, rows, caption }: { head: string[]; rows: (string | number)[][]; caption: string }) {
  return <div className="adv-tablewrap" tabIndex={0} role="region" aria-label={caption}><table className="adv-table"><caption>{caption}</caption>
    <thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
    <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => j === 0 ? <th key={j} scope="row">{c}</th> : <td key={j}>{c}</td>)}</tr>)}</tbody></table></div>;
}

/** Add-company chips with a typo-tolerant search; shows used/limit and the upgrade at the limit. */
function Companies({ st, set, lim, plan, upgrade, status, mode, single }: { st: AdvState; set: (p: Partial<AdvState>) => void; lim: number; plan: Plan; upgrade: (t: Plan, why?: string) => void; status: { s: string; name?: string | null; status: string; reasonText?: string | null; reason?: string | null }[]; mode: Mode; single?: boolean }) {
  const idx = useSearchIndex(true);
  const facets = useFacets();
  const rows = useMemo(() => [...(DEMO ? ((facets.data as { samples?: [string, string][] } | undefined)?.samples ?? []) : []), ...(idx.data?.rows ?? [])], [idx.data, facets.data]);
  const [q, setQ] = useState(""), [act, setAct] = useState(0), [open, setOpen] = useState(false);
  const hits = useMemo(() => rankCompanies(rows, q, 8, st.companies), [rows, q, st.companies]);
  const max = single ? 1 : lim;
  const nameOf = (s: string) => status.find((x) => x.s === s)?.name || rows.find((r) => r[0] === s)?.[1] || s;
  const add = (s: string) => {
    if (st.companies.includes(s)) return;
    if (single) { set({ companies: [s, ...st.companies.filter((x) => x !== s)] }); setQ(""); return; }
    if (st.companies.length >= lim) { upgrade(nextPlan(plan), `Comparing more than ${lim} companies`); return; }
    set({ companies: [...st.companies, s] }); setQ(""); setAct(0);
  };
  const id = "adv-co-" + mode;
  const shown = single ? st.companies.slice(0, 1) : st.companies;
  return <div className="adv-cos">
    <div className="adv-chips">{shown.map((s, i) => { const h = status.find((x) => x.s === s); const bad = h && h.status !== "included" && h.status !== "ok";
      return <span key={s} className={"adv-chip" + (bad ? " bad" : "")}><svg width="14" height="14" aria-hidden="true" style={{ color: COLORS[i % COLORS.length] }}><path d={shapeIcon(i)} /></svg>
        <span>{nameOf(s)}{bad && <small> — {h.reasonText ?? statusText(h.status)}</small>}</span>
        <button aria-label={`Remove ${nameOf(s)}`} onClick={() => set({ companies: st.companies.filter((x) => x !== s) })}>×</button></span>; })}</div>
    <div className="adv-field adv-combo">
      <label htmlFor={id}>{single ? "Company" : "Add a company"} <span className="faint">({shown.length}/{max})</span></label>
      <input id={id} role="combobox" aria-expanded={open && hits.length > 0} aria-controls={`${id}-l`} aria-autocomplete="list" autoComplete="off" value={q} placeholder={single ? "Search a company (name or symbol)" : "Search by name or symbol, e.g. reliance"}
        aria-activedescendant={open && hits[act] ? `${id}-o${act}` : undefined}
        onChange={(e) => { setQ(e.target.value); setOpen(true); setAct(0); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setAct((a) => Math.min(hits.length - 1, a + 1)); } else if (e.key === "ArrowUp") { e.preventDefault(); setAct((a) => Math.max(0, a - 1)); } else if (e.key === "Enter" && hits[act]) { e.preventDefault(); add(hits[act].symbol); } else if (e.key === "Escape") { setQ(""); setOpen(false); } }} />
      {open && q.trim() && <ul id={`${id}-l`} role="listbox" aria-label="Companies">{hits.map((h, i) => <li key={h.symbol} id={`${id}-o${i}`} role="option" aria-selected={i === act} onMouseDown={(e) => { e.preventDefault(); add(h.symbol); }}>{h.name} <small>{h.symbol}</small></li>)}
        {!hits.length && <li className="faint" role="option" aria-selected={false} aria-disabled="true">{idx.isPending ? "Loading the company list…" : "No company matches."}</li>}</ul>}
      {!single && st.companies.length >= lim && <p className="faint adv-limit">Your plan shows {lim} companies per chart. <button className="adv-link" onClick={() => upgrade(nextPlan(plan), `Comparing more than ${lim} companies`)}>More with {plan === "basic" ? "Silver" : "Gold"}</button></p>}
    </div>
  </div>;
}
const statusText = (s: string) => ({ excluded: "left out", outside: "outside the filters: shown, not counted", no_report: "no stored report yet: open its page to load it", unknown: "not a listed symbol", lender_excluded: "a lender: these ratios do not apply" } as Record<string, string>)[s] ?? s;
const shapeIcon = (i: number) => ["M7,2a5,5 0 1,0 0.01,0Z", "M2.5,2.5h9v9h-9Z", "M7,1.5L12.5,12h-11Z", "M7,1L13,7L7,13L1,7Z", "M5,1.5h4v3.5h3.5v4H9v3.5H5V9H1.5V5H5Z", "M7,1L8.8,5.2L13.3,5.4L9.8,8.3L11,12.7L7,10.2L3,12.7L4.2,8.3L0.7,5.4L5.2,5.2Z"][i % 6];

function Filters({ st, set, pair, resp }: { st: AdvState; set: (p: Partial<AdvState>) => void; pair: CatPair | null; resp?: CrossResp }) {
  const f = useFacets();
  const u = st.universe;
  const forced = pair?.lenders === "excluded" || resp?.lenders?.forced;
  const setU = (patch: Partial<AdvState["universe"]>) => set({ universe: { ...u, ...patch } });
  const multi = (label: string, opts: { v: string; l: string }[], val: string[], on: (v: string[]) => void) => <div className="adv-field"><label>{label}
    <select multiple size={Math.min(6, Math.max(3, opts.length))} value={val} onChange={(e) => on([...e.target.selectedOptions].map((o) => o.value))}>{opts.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}</select></label></div>;
  const active = u.sector.length + u.industry.length + u.index.length + u.cap.length + (u.mcapMin != null ? 1 : 0) + (u.mcapMax != null ? 1 : 0) + (u.lenders !== "auto" ? 1 : 0) + (u.sameFy ? 1 : 0) + (st.trim ? 1 : 0);
  const industries = (f.data?.industries ?? []).filter((i) => !u.sector.length || (i.sector && u.sector.includes(i.sector)));
  return <details className="adv-filters"><summary>Which companies{active ? ` (${active} filter${active === 1 ? "" : "s"} on)` : ""}</summary>
    {f.isError && <p className="faint">The filter lists could not be loaded.</p>}
    <div className="adv-fgrid">
      {multi("Sector", (f.data?.sectors ?? []).map((s) => ({ v: s.name, l: `${s.name} (${s.n})` })), u.sector, (v) => setU({ sector: v }))}
      {multi("Industry", industries.map((s) => ({ v: s.name, l: `${s.name} (${s.n})` })), u.industry, (v) => setU({ industry: v }))}
      {multi("Index", (f.data?.indices ?? []).map((s) => ({ v: s.code, l: `${s.label} (${s.n})` })), u.index, (v) => setU({ index: v }))}
      <fieldset className="adv-field"><legend>Size (SEBI band)</legend>{["Large", "Mid", "Small"].map((c) => <label key={c} className="adv-check"><input type="checkbox" checked={u.cap.includes(c)} onChange={(e) => setU({ cap: e.target.checked ? [...u.cap, c] : u.cap.filter((x) => x !== c) })} /> {c} cap</label>)}</fieldset>
      <div className="adv-field"><label>Market cap from (₹ Cr)<input type="number" min={0} inputMode="decimal" value={u.mcapMin ?? ""} onChange={(e) => setU({ mcapMin: e.target.value === "" ? null : Math.max(0, +e.target.value) })} /></label>
        <label>to (₹ Cr)<input type="number" min={0} inputMode="decimal" value={u.mcapMax ?? ""} onChange={(e) => setU({ mcapMax: e.target.value === "" ? null : Math.max(0, +e.target.value) })} /></label></div>
      <div className="adv-field"><label>Banks and lenders
        <select value={forced ? "exclude" : u.lenders} disabled={!!forced} onChange={(e) => setU({ lenders: e.target.value as AdvState["universe"]["lenders"] })}>
          <option value="auto">As suits the chart</option><option value="exclude">Leave them out</option><option value="include">Include them</option><option value="only">Only lenders</option></select></label>
        {forced && <small className="faint">Always left out here: these ratios do not apply to lenders.</small>}</div>
      <div className="adv-field">
        <label className="adv-check"><input type="checkbox" checked={u.sameFy} onChange={(e) => setU({ sameFy: e.target.checked })} /> Same financial year only{resp?.fyBreakdown?.length ? <span className="faint"> ({resp.fyBreakdown.map((b) => `${b.fy}: ${b.n}`).join(", ")})</span> : null}</label>
        <label className="adv-check"><input type="checkbox" checked={st.trim} onChange={(e) => set({ trim: e.target.checked })} /> Leave out the most extreme 1% at each end (names listed under “left out”)</label>
      </div>
    </div>
    {active > 0 && <button className="btn ghost" onClick={() => set({ universe: { sector: [], industry: [], index: [], cap: [], mcapMin: null, mcapMax: null, lenders: "auto", sameFy: false }, trim: false })}>Clear filters</button>}
  </details>;
}

function ExportBtn({ plan, upgrade, body, demo, name }: { plan: Plan; upgrade: (t: Plan, why?: string) => void; body: Record<string, unknown>; demo: () => string; name: string }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const go = async () => {
    if (!allowed(plan, "silver")) { upgrade("silver", "Exporting chart data"); return; }
    setBusy(true); setErr("");
    try {
      const csrf = (qc.getQueryData(["me"]) as { csrf?: string | null } | undefined)?.csrf ?? null;
      const blob = DEMO ? new Blob(["﻿" + demo()], { type: "text/csv;charset=utf-8" }) : await exportCsv(body, csrf);
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `finlit-advanced-${name.replace(/[^\w.-]+/g, "-")}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) { setErr(e instanceof ApiError ? errText(e) : "The export failed. Please try again."); } finally { setBusy(false); }
  };
  return <div className="adv-export"><button className="btn ghost" onClick={go} disabled={busy}>{busy ? "Preparing…" : "Download the data (CSV)"}{!allowed(plan, "silver") && <Icon name="lock" />}</button>
    <span className="faint">Every point used, with the statistics and method, so the figures can be checked in a spreadsheet.</span>{err && <span role="alert" className="adv-err">{err}</span>}</div>;
}

/** "Add index": reference markers from the index list the API exposes (catalog "indices", else the screener's index facet). */
function IndexPicker({ cat, st, set, markers }: { cat: Catalog; st: AdvState; set: (p: Partial<AdvState>) => void; markers: IndexMarker[] }) {
  const f = useFacets();
  const list: { code: string; label: string }[] = cat.indices ?? f.data?.indices ?? [];
  const label = (c: string) => list.find((x) => x.code === c)?.label ?? markers.find((m) => m.code === c)?.label ?? c;
  const left = list.filter((x) => !st.indices.includes(x.code));
  return <div className="adv-ixpick">
    {st.indices.length > 0 && <div className="adv-chips">{st.indices.map((c, i) => <span key={c} className="adv-chip ix"><svg width="14" height="14" aria-hidden="true" style={{ color: INDEX_COLORS[i % INDEX_COLORS.length] }}><path d="M7,1L13,7L7,13L1,7Z" /></svg>
      <span>{label(c)} <small>index</small></span><button aria-label={`Remove index ${label(c)}`} onClick={() => set({ indices: st.indices.filter((x) => x !== c) })}>×</button></span>)}</div>}
    <label className="adv-field">Add an index <span className="faint">({st.indices.length}/{MAX_INDICES}, reference points only)</span>
      <select value="" disabled={st.indices.length >= MAX_INDICES || !left.length} onChange={(e) => e.target.value && set({ indices: [...st.indices, e.target.value].slice(0, MAX_INDICES) })}>
        <option value="">{!list.length ? (f.isPending ? "Loading indices…" : "No index list available") : st.indices.length >= MAX_INDICES ? `Up to ${MAX_INDICES} indices` : "Choose an index…"}</option>
        {left.map((x) => <option key={x.code} value={x.code}>{x.label}</option>)}</select></label>
  </div>;
}

// ------------------------------------------------------------------ company history

function HistoryView({ cat, pair, xId, yId, st, set, table, lim, plan, upgrade, section }: { cat: Catalog; pair: CatPair | null; xId: string; yId: string; st: AdvState; set: (p: Partial<AdvState>) => void; table: boolean; lim: number; plan: Plan; upgrade: (t: Plan, why?: string) => void; section: number }) {
  const q = useHistory(st.companies, pair?.id ?? null, xId, yId, st.companies.length > 0);
  const { ref, w } = useWidth();
  const r: HistResp | undefined = q.data;
  const mx = cat.metrics[xId], my = cat.metrics[yId];
  const ux = unitOf(r?.x, mx), uy = unitOf(r?.y, my);
  const fx = (v: number) => fmtUnit(v, ux, mx?.digits), fy = (v: number) => fmtUnit(v, uy, my?.digits);
  const cos = r ? st.companies.map((s) => r.companies.find((c) => c.s === s)).filter((c): c is NonNullable<typeof c> => !!c) : [];
  const series: ScSeries[] = cos.map((c) => ({ key: c.s, name: c.name || c.s, color: COLORS[st.companies.indexOf(c.s) % COLORS.length], shape: SHAPES[st.companies.indexOf(c.s) % SHAPES.length], pts: c.points.map((p) => ({ key: c.s + p.fy, label: `${c.name || c.s} ${p.fy}`, x: p.x, y: p.y })) }));
  const fits = cos.flatMap((c) => fitsOf(c.stats, c.s, COLORS[st.companies.indexOf(c.s) % COLORS.length]));
  const total = cos.reduce((s, c) => s + c.points.length, 0);
  return <>
    {r?.sample && <p className="adv-banner bi">Demo preview: sample figures, not real data.</p>}
    <div ref={ref} className="adv-body"><DrawLayer id={"adv:" + viewId(JSON.stringify([section, pair?.id ?? [xId, yId], "history", st.companies]))} enabled={!!r && total > 0 && !table && w > 0}>
      {!st.companies.length ? <div className="adv-state">Add a company below to see its own years on this chart (one point per financial year).</div>
        : q.isPending ? <div className="adv-state" role="status">Working out the chart…</div>
        : q.isError ? <div className="adv-state" role="alert"><b>{errText(q.error)}</b>{q.error.status === 403 && <button className="btn primary" onClick={() => upgrade((q.error.body.plan as Plan) || nextPlan(plan), "Company history")}>See plans</button>}</div>
        : r && w > 0 ? (total === 0 ? <div className="adv-state">No year has both figures for the chosen companies.</div>
          : table ? <PointsTable head={["Company", "Year", r.x.label, r.y.label]} rows={cos.flatMap((c) => c.points.map((p) => [c.name || c.s, p.fy, fx(p.x), fy(p.y)]))} caption={`${r.x.label} and ${r.y.label} by financial year`} />
          : <><AdvScatter cloud={[]} series={series} fits={fits} sx="lin" sy="lin" xLabel={r.x.label} yLabel={r.y.label} fmtX={fx} fmtY={fy} tickX={(v) => tickUnit(v, ux)} tickY={(v) => tickUnit(v, uy)} all w={w}
              summary={`Scatter of ${r.y.label} against ${r.x.label} by financial year for ${cos.map((c) => `${c.name || c.s} (${c.n} years)`).join(", ")}. ${cos.map((c) => `${c.name || c.s}: ${c.stats ? c.stats.decision.text : "no statistics"}`).join(" ")}`} />
            <Legend fits={fits} /></>) : null}
    </DrawLayer></div>
    <Companies st={st} set={set} lim={lim} plan={plan} upgrade={upgrade} status={r?.companies.map((c) => ({ s: c.s, name: c.name, status: c.status })) ?? []} mode="history" />
    {r && cos.map((c) => <div key={c.s} className="adv-co-stats">
      <h4><svg width="14" height="14" aria-hidden="true" style={{ color: COLORS[st.companies.indexOf(c.s) % COLORS.length] }}><path d={shapeIcon(st.companies.indexOf(c.s))} /></svg> {c.name || c.s}</h4>
      {c.status !== "ok" ? <p>— {statusText(c.status)}</p> : <StatsPanel stats={c.stats} sentence={advSentence(c.stats, { kind: "history", who: `financial years of ${c.name || c.s}`, x: { short: shortOf(r.x, mx), unit: ux! }, y: { short: shortOf(r.y, my), unit: uy! } })}
        extra={c.missing.length > 0 ? <details className="adv-excl"><summary>{c.missing.length} year value{c.missing.length === 1 ? "" : "s"} missing: why</summary><ul>{c.missing.map((m, i) => <li key={i}><b>{m.fy}</b> <span className="faint">({m.axis === "x" ? "across" : "up"})</span> — {m.text}</li>)}</ul></details> : null} />}
    </div>)}
    {r && <><ul className="adv-notes">{[...new Set(r.notes)].map((t) => <li key={t}>{t}</li>)}</ul><Caveats list={r.caveats} />
      <ExportBtn plan={plan} upgrade={upgrade} body={{ mode: "history", symbols: st.companies, x: xId, y: yId, ...(pair ? { pair: pair.id } : {}) }} demo={() => historyCsv(r)} name={`${pair?.id ?? `${xId}-${yId}`}-history`} /></>}
    {!r && <Caveats list={[]} />}
    {section === 9 && <PlWarnings symbols={st.companies} />}
  </>;
}
function historyCsv(r: HistResp): string {
  const rows = [["symbol", "name", "fy", "x", "y", "included", "reason"].join(",")];
  r.companies.forEach((c) => { c.points.forEach((p) => rows.push([c.s, JSON.stringify(c.name), p.fy, p.x, p.y, "yes", ""].join(","))); c.missing.forEach((m) => rows.push([c.s, JSON.stringify(c.name), m.fy, "", "", "no", m.code].join(","))); });
  return rows.join("\n");
}

// ------------------------------------------------------------------ section 8 company time series

function TechView({ cat, pair, st, set, table, plan, upgrade }: { cat: Catalog; pair: CatPair; st: AdvState; set: (p: Partial<AdvState>) => void; table: boolean; plan: Plan; upgrade: (t: Plan, why?: string) => void }) {
  const kind = pair.tech?.kind ?? "rsi", hs = pair.tech?.h ?? [];
  const h = hs.length ? (st.h && hs.includes(st.h) ? st.h : hs.includes(20) ? 20 : hs[0]) : null;
  const sym = st.companies[0] ?? null;
  const ixList = cat.benchmarks ?? [];   // the API's benchmark list for the market return (beta)
  const bix = kind === "beta" ? st.indices[0] ?? null : null;
  const q = useTech(sym, kind, h, !!sym, bix);
  const { ref, w } = useWidth();
  const r: TechResp | undefined = q.data;
  const ux = r?.x.unit, uy = r?.y.unit;
  const fx = (v: number) => fmtUnit(v, ux), fy = (v: number) => fmtUnit(v, uy);
  const cloud: ScPt[] = r ? r.points.map((p) => ({ key: p.d, label: p.d, x: p.x, y: p.y })) : [];
  const fits = fitsOf(r?.stats ?? null, "t");
  return <>
    {hs.length > 0 && <div className="adv-seg" role="group" aria-label="Forward horizon">{hs.map((x) => <button key={x} aria-pressed={h === x} onClick={() => set({ h: x })}>Next {x} trading days</button>)}</div>}
    {kind === "beta" && ixList.length > 0 && <label className="adv-field">Market index for the market return
      <select value={bix ?? ""} onChange={(e) => set({ indices: e.target.value ? [e.target.value] : [] })}><option value="">{ixList.find((x) => x.code === "NIF50")?.label ?? "Default index"}{ixList.some((x) => x.code === "NIF50") ? " (default)" : ""}</option>{ixList.filter((x) => x.code !== "NIF50").map((x) => <option key={x.code} value={x.code}>{x.label}</option>)}</select></label>}
    {r?.sample && <p className="adv-banner bi">Demo preview: sample prices, not real data.</p>}
    <div ref={ref} className="adv-body"><DrawLayer id={"adv:" + viewId(JSON.stringify([pair.id, "tech", sym, h, bix]))} enabled={!!r && r.n > 0 && !table && w > 0}>
      {!sym ? <div className="adv-state">Choose a company below: this chart follows one company over time, from its stored daily closes.</div>
        : q.isPending ? <div className="adv-state" role="status">Working out the chart…</div>
        : q.isError ? <div className="adv-state" role="alert"><b>{errText(q.error)}</b>{q.error.status === 403 && <button className="btn primary" onClick={() => upgrade((q.error.body.plan as Plan) || "gold", "Technical charts")}>See plans</button>}</div>
        : r && w > 0 ? (r.n === 0 ? <div className="adv-state">No complete window for this company.</div>
          : table ? <PointsTable head={["Signal date", r.x.label, r.y.label]} rows={r.points.map((p) => [p.d, fx(p.x), fy(p.y)])} caption={`${r.name}: ${r.x.label} and ${r.y.label}`} />
          : <><AdvScatter cloud={cloud} series={[]} fits={fits} sx="lin" sy="lin" xLabel={r.x.label} yLabel={r.y.label} fmtX={fx} fmtY={fy} tickX={(v) => tickUnit(v, ux)} tickY={(v) => tickUnit(v, uy)} all={st.all} w={w} summary={ariaSummary(r.stats, r.x.label, r.y.label, r.n, "windows")} /><Legend fits={fits} /></>) : null}
    </DrawLayer></div>
    <Companies st={st} set={set} lim={1} plan={plan} upgrade={upgrade} status={r ? [{ s: r.symbol, name: r.name, status: "included" }] : []} mode="tech" single />
    {r && <StatsPanel stats={r.stats} sentence={advSentence(r.stats, { kind: "tech", who: `${kind === "beta" ? "weeks" : "non-overlapping windows"} of ${r.name}`, x: { short: r.x.label, unit: r.x.unit }, y: { short: r.y.label, unit: r.y.unit }, builtAt: null })}
      extra={<><ExcludedList items={r.excluded} /><p className="faint adv-cov">{r.grid}{r.asOf ? `. Prices up to ${r.asOf}.` : ""}</p><ul className="adv-notes">{[...new Set(r.notes)].map((t) => <li key={t}>{t}</li>)}</ul><Caveats list={r.caveats} />
        <ExportBtn plan={plan} upgrade={upgrade} body={{ mode: "tech", symbol: r.symbol, kind, ...(h ? { h } : {}), ...(bix ? { market: bix } : {}) }} demo={() => ["date,x,y,included,reason", ...r.points.map((p) => `${p.d},${p.x},${p.y},yes,`)].join("\n")} name={`${pair.id}-${r.symbol}`} /></>} />}
    {!r && <Caveats list={[]} />}
  </>;
}

// ------------------------------------------------------------------ section 9: warning flags that are rules, not correlations

function PlWarnings({ symbols }: { symbols: string[] }) {
  const qs = useQueries({ queries: symbols.map((s) => ({ queryKey: ["stock", s, "/financials"], queryFn: () => apiGet<Financials>(`/api/stocks/${encodeURIComponent(s)}/financials`), staleTime: 60_000, retry: 1 })) });
  return <section className="adv-flags" aria-labelledby="adv-flags-h">
    <h4 id="adv-flags-h">Warning rules for the chosen companies</h4>
    <p className="faint">Two checks from the founder's document that are rules, not correlations: profit growing more than three times as fast as revenue, and revenue and profit rising while operating cash flow falls. Worth a closer look, never a verdict.</p>
    {!symbols.length ? <p>Add a company above to run these checks on its reported figures.</p> : <ul>{symbols.map((s, i) => { const q = qs[i];
      if (!q || q.isPending) return <li key={s}><b>{s}</b> — loading its statements…</li>;
      if (q.isError || !q.data) return <li key={s}><b>{s}</b> — its statements could not be loaded{(q.error as ApiError)?.status === 404 ? " (no stored report)" : ""}.</li>;
      const flags = plFlags({ annual: q.data.yearly?.pl, quarterly: q.data.quarterly?.pl }), cw = cfoWarning(q.data);
      return <li key={s}><b>{s}</b>{!flags.length && !cw ? <span> — no flag on the latest reported periods.</span> : <ul>
        {flags.map((f) => <li key={f.key}><span className={"adv-st " + (f.severity === "caution" ? "warn" : "adapted")}>{f.severity === "caution" ? "Caution" : "Watch"}</span> <b>{f.title}</b> ({f.period}). {f.text} <span className="faint">{f.why}</span></li>)}
        {cw && <li><span className="adv-st warn">Caution</span> <b>Revenue and profit rose but operating cash flow fell</b> ({cw.period} against {cw.against}). {cw.text}</li>}</ul>}</li>; })}</ul>}
  </section>;
}
