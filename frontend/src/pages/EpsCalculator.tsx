// EPS calculator (free): earnings per share and P/E from four inputs, then a future-EPS and price scenario with Bear/Base/Bull cases, a
// sensitivity grid, year-by-year charts, PEG and the growth a target price needs. All arithmetic lives in lib/epsCalc.ts (pure, tested).
// A company can be loaded from our stored annual figures (net profit attributable to owners, diluted weighted shares, price); every field stays editable.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useSearchIndex, useSection, useSummary, type Financials, type Glossary } from "../lib/api";
import { Icon } from "../lib/icons";
import { useUI } from "../lib/ui";
import { useDocTitle } from "../lib/title";
import { csvText, dateIN, nf } from "../lib/format";
import { TERMS } from "../lib/glossary";
import { Info } from "../components/Info";
import {
  LIMITS, MINUS, around, checkCase, eps as epsOf, fix2, parseNum, path, pctText, pe as peOf, peg as pegOf, project, requiredGrowth, sensitivity, type Case,
} from "../lib/epsCalc";
import "../styles/dcf.css";
import "../styles/eps.css";

// ------------------------------------------------------------------------------------------------------------- form state
type Form = { np: string; pd: string; sh: string; ds: string; px: string; m: "b" | "d"; g: string; pe: string; n: string; bg: string; bp: string; ug: string; up: string; tp: string; sym: string };
const DEFAULT: Form = { np: "100", pd: "0", sh: "10", ds: "", px: "300", m: "b", g: "12", pe: "20", n: "5", bg: "6", bp: "15", ug: "18", up: "25", tp: "", sym: "" };
const PARAM: Record<string, keyof Form> = { np: "np", pd: "pd", sh: "sh", ds: "ds", px: "px", m: "m", g: "g", pe: "pe", n: "n", bg: "bg", bp: "bp", ug: "ug", up: "up", tp: "tp", sym: "sym" };

function fromParams(sp: URLSearchParams): Form {
  const f = { ...DEFAULT };
  for (const [k, field] of Object.entries(PARAM)) { const v = sp.get(k); if (v != null) (f as Record<string, string>)[field] = v.slice(0, 30); }
  if (f.m !== "d") f.m = "b";
  f.sym = f.sym.toUpperCase().replace(/[^A-Z0-9&_-]/g, "");
  return f;
}
function toParams(f: Form): URLSearchParams {
  const sp = new URLSearchParams();
  for (const [k, field] of Object.entries(PARAM)) { const v = String(f[field]); if (v !== "" && v !== String(DEFAULT[field])) sp.set(k, v); }
  return sp;
}

// ------------------------------------------------------------------------------------------------------------- formatting
const rs = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : (v < 0 ? MINUS + "₹" : "₹") + nf(Math.abs(Number(fix2(v))), 2));
const mult = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : nf(Number(fix2(v)), 2) + "x");
const pcA = (v: number) => (v < 0 ? MINUS : "") + nf(Math.abs(Number(fix2(v))), 2) + "%";

// ------------------------------------------------------------------------------------------------------------- help (glossary mechanism)
const term = (id: string, label?: string): Glossary | undefined => {
  const t = TERMS.find((x) => x.id === id);
  return t ? ({ key: t.id, label: label ?? t.term, what: t.meaning, read: t.how, formula: t.formula || undefined, note: t.finlit || undefined } as Glossary) : undefined;
};
const HELP = {
  eps: term("earnings-per-share-eps"), basic: term("basic-eps"), diluted: term("diluted-eps"), shares: term("weighted-average-shares"), pe: term("price-to-earnings-ratio-p-e"),
  target: term("target-pe"), implied: term("implied-future-price"), peg: term("peg-ratio"),
  pref: { key: "pref", label: "Preference dividends", what: "Dividends owed to preference shareholders. They are paid before ordinary shareholders, so they come off profit when working out EPS. Enter 0 if the company has no preference shares.", formula: "Profit for ordinary shareholders = Net profit − Preference dividends" } as Glossary,
};

// ------------------------------------------------------------------------------------------------------------- company data
type Loaded = { symbol: string; name: string; statement: string; period: string | null; periodEnd: string | null; priceAsOf: string | null; reportedEps: number | null; notes: string[] };

function lastIndex(rows: (number | null)[] | undefined): number {
  if (!rows) return -1;
  for (let k = rows.length - 1; k >= 0; k--) if (rows[k] != null && Number.isFinite(rows[k])) return k;
  return -1;
}
const round6 = (x: number) => String(Math.round(x * 1e6) / 1e6);

function CompanyLoader({ initial, loaded, onLoad }: { initial: string | null; loaded: Loaded | null; onLoad: (patch: Partial<Form>, info: Loaded) => void }) {
  const [q, setQ] = useState("");
  const [sym, setSym] = useState<string | null>(initial);
  const index = useSearchIndex(q.trim().length > 0);
  const hits = useMemo(() => {
    const t = q.trim().toUpperCase();
    if (!t || !index.data) return [];
    const starts = index.data.rows.filter((r) => r[0].startsWith(t) || r[1].toUpperCase().startsWith(t));
    const has = index.data.rows.filter((r) => !starts.includes(r) && r[1].toUpperCase().includes(t));
    return [...starts, ...has].slice(0, 8);
  }, [q, index.data]);
  const summary = useSummary(sym ?? "", !!sym), fin = useSection<Financials>(sym ?? "", "financials", !!sym);
  const busy = !!sym && (summary.isFetching || fin.isFetching) && !(summary.data && fin.data);
  const failed = !!sym && (summary.isError || fin.isError);
  const doneFor = useRef<string | null>(null);
  useEffect(() => {
    const s = summary.data, f = fin.data;
    if (!sym || !s || !f || s.meta.symbol !== sym.toUpperCase() || f.meta.symbol !== sym.toUpperCase() || doneFor.current === sym + s.meta.statement) return;
    doneFor.current = sym + s.meta.statement;
    const pl = f.yearly.pl, k = lastIndex(pl.rows.net_profit);
    const notes: string[] = [];
    const patch: Partial<Form> = { sym: s.meta.symbol, m: "d", pd: "", sh: "" };
    let reported: number | null = null;
    if (k >= 0) {
      patch.np = round6(pl.rows.net_profit[k] as number);
      const sh = pl.rows.diluted_shares_cr?.[k];
      if (sh != null && sh > 0) patch.ds = round6(sh); else { patch.ds = ""; notes.push("The diluted weighted average share count is not available for this period; enter it from the annual report."); }
      reported = pl.rows.eps?.[k] ?? null;
    } else { patch.np = ""; patch.ds = ""; notes.push("No annual net profit is stored for this company yet; enter the figures by hand."); }
    notes.push("Basic weighted average shares and preference dividends are not stored; preference dividends are treated as 0 until you enter them. Take the basic share count from the annual report to use the basic measure.");
    if (s.quote.price != null && s.quote.price > 0) patch.px = String(s.quote.price); else { patch.px = ""; notes.push("No current share price is available; enter one."); }
    onLoad(patch, { symbol: s.meta.symbol, name: s.profile.name, statement: s.meta.statement, period: k >= 0 ? pl.periods[k] : null, periodEnd: k >= 0 ? pl.periodEnds?.[k] ?? null : null, priceAsOf: s.quote.asOf, reportedEps: reported, notes });
  }, [summary.data, fin.data, sym]);   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <section className="card dcf-co" aria-labelledby="eps-co-h">
      <div className="dcf-co-h"><h2 id="eps-co-h">Start from a company</h2>
        <p className="muted">Fills net profit (attributable to owners), diluted weighted average shares and the latest price from FinLit's stored figures. Every field stays editable, and anything we do not hold is left empty.</p></div>
      <div className="dcf-co-row">
        <label className="dcf-search"><Icon name="search" /><span className="sr-only">Search a company</span>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Company name or NSE symbol" autoComplete="off" spellCheck={false} maxLength={60}
            onKeyDown={(e) => { if (e.key === "Enter" && hits[0]) { e.preventDefault(); doneFor.current = null; setSym(hits[0][0]); setQ(""); } }} /></label>
      </div>
      {q.trim() && hits.length > 0 && <ul className="dcf-hits" aria-label="Matching companies">{hits.map((h) => <li key={h[0]}><button type="button" onClick={() => { doneFor.current = null; setSym(h[0]); setQ(""); }}><b>{h[1]}</b><span className="mono faint">{h[0]}</span></button></li>)}</ul>}
      {q.trim() && index.data && hits.length === 0 && <p className="faint">No listed company matches “{q.trim()}”.</p>}
      {busy && <p className="muted" aria-live="polite">Loading {sym}…</p>}
      {failed && !busy && <p className="formerr" role="alert">Could not load this company's figures. Enter them by hand.</p>}
      {loaded && !busy && (
        <div className="dcf-src">
          <p><b>{loaded.name}</b> <span className="mono faint">{loaded.symbol}</span> · {loaded.statement} statements</p>
          <ul>
            <li>Net profit and shares: {loaded.period ? `annual report for ${loaded.period}${loaded.periodEnd ? ` (year ended ${dateIN(loaded.periodEnd.slice(0, 10))})` : ""}` : "not available"}. Source: FinLit stored financial statements; net profit is profit attributable to the owners of the company, as EPS is.</li>
            <li>Price: latest stored quote{loaded.priceAsOf ? ` (${dateIN(loaded.priceAsOf.slice(0, 10))})` : ""}.</li>
            {loaded.reportedEps != null && <li>EPS as reported for {loaded.period}: {rs(loaded.reportedEps)}. The calculation below may differ slightly if you change a figure.</li>}
          </ul>
          {loaded.notes.map((n) => <p key={n} className="dcf-note" role="note"><Icon name="info" />{n}</p>)}
        </div>)}
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- inputs
function Field({ id, label, help, value, onChange, unit, error, hint, required = true }: {
  id: string; label: string; help?: Glossary; value: string; onChange: (v: string) => void; unit?: string; error?: string; hint?: string; required?: boolean;
}) {
  return (
    <div className={"dcf-f" + (error ? " has-err" : "")}>
      <label htmlFor={"eps-" + id}>{label}{required && <span className="req" aria-hidden="true">*</span>}{help && <Info g={help} />}</label>
      <div className="dcf-in">
        <input id={"eps-" + id} inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={!!error} aria-describedby={error ? `eps-${id}-err` : hint ? `eps-${id}-hint` : undefined}
          autoComplete="off" spellCheck={false} maxLength={24} />
        {unit && <span className="unit">{unit}</span>}
      </div>
      {error ? <p className="dcf-err" id={`eps-${id}-err`} role="alert">{error}</p> : hint ? <p className="dcf-hint faint" id={`eps-${id}-hint`}>{hint}</p> : null}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- charts
function Chart({ title, unitLabel, kind, pts, sel, setSel, fmt, years }: { title: string; unitLabel: string; kind: "bar" | "line"; pts: number[]; sel: number; setSel: (t: number) => void; fmt: (v: number) => string; years: number }) {
  const W = 600, H = 230, L = 58, R = 12, T = 12, B = 30, iw = W - L - R, ih = H - T - B;
  const max = Math.max(...pts) * 1.08 || 1;
  const x = (t: number) => (kind === "bar" ? L + (iw * (t + 0.5)) / pts.length : L + (iw * t) / Math.max(1, pts.length - 1)), y = (v: number) => T + ih - (v / max) * ih;
  const step = Math.max(1, Math.ceil(pts.length / 12));
  const bw = Math.min(40, (iw / pts.length) * 0.7);
  const onKey = (e: React.KeyboardEvent) => {
    const k = e.key; if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(k)) return;
    e.preventDefault(); setSel(k === "Home" ? 0 : k === "End" ? years : Math.min(years, Math.max(0, sel + (k === "ArrowRight" ? 1 : -1))));
  };
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    const t = kind === "bar" ? Math.floor(((px - L) / iw) * pts.length) : Math.round(((px - L) / iw) * (pts.length - 1));
    setSel(Math.min(years, Math.max(0, t)));
  };
  return (
    <figure className="eps-chart">
      <figcaption><b>{title}</b> <span className="faint">{unitLabel}</span></figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`${title}. Use the left and right arrow keys to read each year.`} tabIndex={0} onKeyDown={onKey} onPointerMove={onMove} onPointerDown={onMove}>
        {[0, 0.5, 1].map((f) => <g key={f}><line x1={L} x2={W - R} y1={y(max * f)} y2={y(max * f)} className="gl" /><text x={L - 6} y={y(max * f) + 4} textAnchor="end" className="ax">{fmt(max * f)}</text></g>)}
        {kind === "bar"
          ? pts.map((v, t) => <rect key={t} x={x(t) - bw / 2} y={y(v)} width={bw} height={Math.max(0, T + ih - y(v))} className={t === sel ? "bar on" : "bar"} />)
          : <><polyline points={pts.map((v, t) => `${x(t)},${y(v)}`).join(" ")} className="ln" fill="none" />{pts.map((v, t) => (pts.length <= 16 || t === sel) && <circle key={t} cx={x(t)} cy={y(v)} r={t === sel ? 5 : 3} className={t === sel ? "dot on" : "dot"} />)}</>}
        <line x1={x(sel)} x2={x(sel)} y1={T} y2={T + ih} className="cur" />
        {pts.map((_, t) => t % step === 0 && <text key={t} x={x(t)} y={H - 10} textAnchor="middle" className="ax">{t}</text>)}
        <text x={L + iw / 2} y={H - 0.5} textAnchor="middle" className="ax">Year</text>
      </svg>
    </figure>
  );
}

// ------------------------------------------------------------------------------------------------------------- CSV
function exportCsv(f: Form, rows: (string | number)[][]) {
  const lines: (string | number)[][] = [["FinLit EPS calculator", f.sym || "custom inputs", new Date().toISOString().slice(0, 10)], [], ...rows];
  const csv = lines.map((r) => r.map((c) => { const s = csvText(String(c)); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }).join(",")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  a.download = `finlit-eps-${f.sym || "custom"}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

const FORMULAS: [string, string][] = [
  ["Basic EPS", "(Net profit − Preference dividends) ÷ Weighted average ordinary shares"],
  ["Diluted EPS", "Profit attributable to ordinary shareholders ÷ Diluted weighted average shares"],
  ["Current P/E", "Current share price ÷ EPS"],
  ["Future EPS", "Current EPS × (1 + g)^n"],
  ["Implied future price", "Future EPS × Target P/E"],
  ["Potential price return", "(Future price ÷ Current price − 1) × 100"],
  ["PEG ratio", "P/E ÷ EPS growth (%)"],
  ["Growth needed", "((Target price ÷ Target P/E) ÷ EPS)^(1/n) − 1"],
];

// ------------------------------------------------------------------------------------------------------------- page
export function EpsCalculatorPage() {
  useDocTitle("EPS calculator", "Earnings per share, P/E and a future-price scenario: basic or diluted EPS, Bear/Base/Bull cases, a sensitivity grid, PEG and the growth a target price needs.");
  const { toast } = useUI();
  const [sp, setSp] = useSearchParams();
  const [form, setForm] = useState<Form>(() => fromParams(sp));
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [sel, setSel] = useState(0);
  const [gridMode, setGridMode] = useState<"price" | "return">("price");
  useEffect(() => { const h = window.setTimeout(() => setSp(toParams(form), { replace: true }), 300); return () => window.clearTimeout(h); }, [form]);   // eslint-disable-line react-hooks/exhaustive-deps
  const set = <K extends keyof Form>(k: K) => (v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));
  const diluted = form.m === "d";

  // ---- section 1
  const a = useMemo(() => {
    const np = parseNum(form.np), pd = form.pd.trim() === "" ? 0 : parseNum(form.pd), sh = parseNum(diluted ? form.ds : form.sh), px = parseNum(form.px);
    const errs: Partial<Record<"np" | "pd" | "sh" | "px", string>> = {};
    if (!Number.isFinite(np)) errs.np = "Enter net profit as a number (negative for a loss).";
    if (!Number.isFinite(pd) || pd < 0) errs.pd = "Enter preference dividends as 0 or more.";
    if (!Number.isFinite(sh)) errs.sh = `Enter the ${diluted ? "diluted " : ""}weighted average shares in crore.`;
    else if (sh <= 0) errs.sh = "Shares must be above zero.";
    if (!Number.isFinite(px)) errs.px = "Enter the current share price.";
    else if (px <= 0) errs.px = "The share price must be above zero.";
    const e = errs.np || errs.pd || errs.sh ? null : epsOf(np, pd, sh);
    return { np, pd, sh, px, errs, e, pe: peOf(px, e) };
  }, [form.np, form.pd, form.sh, form.ds, form.px, diluted]);

  // ---- section 2
  const n = parseNum(form.n);
  const base: Case = { growth: parseNum(form.g), targetPe: parseNum(form.pe) };
  const bear: Case = { growth: parseNum(form.bg), targetPe: parseNum(form.bp) }, bull: Case = { growth: parseNum(form.ug), targetPe: parseNum(form.up) };
  const chk = checkCase(base, n);
  const proj = project(a.e, a.px, base, n);
  const cases = [{ k: "bear", label: "Bear", c: bear, gk: "bg", pk: "bp" }, { k: "base", label: "Base", c: base, gk: "g", pk: "pe" }, { k: "bull", label: "Bull", c: bull, gk: "ug", pk: "up" }] as const;
  const whyNone = a.e == null ? "Complete the four inputs above first." : a.e <= 0 ? "Not meaningful: EPS is zero or negative, so growing it by a percentage does not describe a business." : !(a.px > 0) ? "Enter a share price above zero." : !chk.ok ? "Fix the assumptions to see the scenario." : "";
  const pts = useMemo(() => (proj && a.e ? path(a.e, base, n) : null), [proj, a.e, base.growth, base.targetPe, n]);   // eslint-disable-line react-hooks/exhaustive-deps
  const selYear = Math.min(sel, Number.isInteger(n) ? n : 0);
  const tpNum = parseNum(form.tp);
  const req = form.tp.trim() === "" ? null : requiredGrowth(tpNum, base.targetPe, a.e, n);
  const peg = pegOf(a.pe.value, base.growth);
  const gCols = around(base.targetPe, base.targetPe >= 20 ? 5 : 2.5, 5, 0.5, LIMITS.peMax), gRows = around(base.growth, 3, 5, LIMITS.growthMin, LIMITS.growthMax);
  const grid = useMemo(() => (proj ? sensitivity(a.e, a.px, gRows, gCols, n) : null), [proj, a.e, a.px, n, base.growth, base.targetPe]);   // eslint-disable-line react-hooks/exhaustive-deps

  const onLoad = (patch: Partial<Form>, info: Loaded) => { setForm((f) => ({ ...f, ...patch })); setLoaded(info); };
  const copyLink = async () => { try { await navigator.clipboard.writeText(location.href); toast("Link copied: it opens the calculator with these inputs."); } catch { toast("Copy the address from the browser bar."); } };
  const reset = () => { setForm(DEFAULT); setLoaded(null); setSel(0); };
  const csv = () => exportCsv(form, [["Input", "Value"], ["Net profit (Rs Cr)", a.np], ["Preference dividends (Rs Cr)", a.pd], [diluted ? "Diluted weighted average shares (crore)" : "Weighted average shares (crore)", a.sh],
    ["Current share price (Rs)", a.px], ["EPS measure", diluted ? "diluted" : "basic"], ["EPS growth %", base.growth], ["Target P/E (x)", base.targetPe], ["Years", n], [],
    ["Result", "Value"], ["EPS (Rs)", a.e == null ? "" : fix2(a.e)], ["Current P/E (x)", a.pe.value == null ? "not meaningful" : fix2(a.pe.value)],
    ["Projected EPS (Rs)", proj ? fix2(proj.eps) : ""], ["Implied future price (Rs)", proj ? fix2(proj.price) : ""], ["Potential price return %", proj ? fix2(proj.returnPct) : ""], [],
    ["Case", "Growth %", "Target P/E", "Projected EPS", "Implied price", "Return %"],
    ...cases.map(({ label, c }) => { const p = project(a.e, a.px, c, n); return [label, c.growth, c.targetPe, p ? fix2(p.eps) : "", p ? fix2(p.price) : "", p ? fix2(p.returnPct) : ""]; }),
    [], ["Year", "EPS (Rs)", "Implied price (Rs)"], ...(pts ?? []).map((p) => [p.year, fix2(p.eps), fix2(p.price)]), [],
    ["Price return excludes dividends, taxes and transaction costs. Scenario calculation, not a price forecast. Information only, not investment advice."]]);
  const slider = Number.isInteger(n) ? Math.min(LIMITS.yearsMax, Math.max(LIMITS.yearsMin, n)) : 5;
  const Pc = (v: number, k: string) => <span className={k}>{pctText(v)}</span>;

  return (
    <>
      <section className="pagehead"><div className="wrap"><div className="eyebrow">Free tool</div><h1>EPS calculator</h1>
        <p>Work out earnings per share and the P/E ratio from four numbers, then see what a future EPS and a target P/E would imply for the share price. Everything updates as you type, and the working is shown.</p></div></section>
      <div className="wrap dcf eps">
        <CompanyLoader initial={sp.get("load") === "1" && form.sym ? form.sym : null} loaded={loaded} onLoad={onLoad} />

        <section className="card" aria-labelledby="eps-1-h">
          <h2 id="eps-1-h">1. Calculate EPS <span className="faint">₹ crore unless stated</span></h2>
          <div className="dcf-opts eps-measure" role="group" aria-label="EPS measure">
            <span>EPS measure</span>
            <button type="button" className={"chip-b" + (!diluted ? " on" : "")} aria-pressed={!diluted} onClick={() => set("m")("b")}>Basic</button><Info g={HELP.basic} />
            <button type="button" className={"chip-b" + (diluted ? " on" : "")} aria-pressed={diluted} onClick={() => setForm((f) => ({ ...f, m: "d", ds: f.ds.trim() === "" ? f.sh : f.ds }))}>Diluted</button><Info g={HELP.diluted} />
          </div>
          <div className="dcf-grid">
            <Field id="np" label="Net profit (₹ crore)" help={HELP.eps} value={form.np} onChange={set("np")} error={a.errs.np} hint="Profit attributable to the owners of the company. Negative for a loss." />
            <Field id="pd" label="Preference dividends (₹ crore)" help={HELP.pref} value={form.pd} onChange={set("pd")} error={a.errs.pd} required={false} hint="Leave empty or 0 if there are no preference shares." />
            {diluted
              ? <Field id="ds" label="Diluted weighted average shares (crore)" help={HELP.shares} value={form.ds} onChange={set("ds")} error={a.errs.sh} hint="Includes shares that options and convertibles could create." />
              : <Field id="sh" label="Weighted average shares (crore)" help={HELP.shares} value={form.sh} onChange={set("sh")} error={a.errs.sh} hint="Ordinary shares, each counted for the part of the year it existed." />}
            <Field id="px" label="Current share price (₹)" value={form.px} onChange={set("px")} error={a.errs.px} />
          </div>
          <div className="dcf-sum eps-sum" aria-live="polite">
            <div className="dcf-k main"><span>Earnings Per Share (₹) <Info g={HELP.eps} /></span><b className={a.e != null && a.e < 0 ? "down" : ""}>{a.e == null ? "—" : rs(a.e)}</b><small>{diluted ? "Diluted" : "Basic"} EPS{a.e != null && a.e < 0 ? ": a loss per share" : ""}</small></div>
            <div className="dcf-k"><span>Calculated P/E ratio <Info g={HELP.pe} /></span><b>{a.pe.value == null ? "Not meaningful" : mult(a.pe.value)}</b><small>{a.pe.value == null ? a.pe.reason : "price ÷ EPS"}</small></div>
          </div>
          <p className="faint eps-formula">(Net profit − Preference dividends) ÷ Weighted average diluted or basic shares, depending on the EPS measure selected.
            {a.e != null && <> Here: ({nf(a.np, 2)} − {nf(a.pd, 2)}) ÷ {nf(a.sh, 2)} = <b>{rs(a.e)}</b>.</>}</p>
          {a.e != null && a.pd > 0 && a.np - a.pd < 0 && a.np >= 0 && <p className="dcf-note" role="note"><Icon name="info" />Preference dividends are larger than net profit, so nothing is left for ordinary shareholders and EPS is negative.</p>}
        </section>

        <section className="card" aria-labelledby="eps-2-h">
          <h2 id="eps-2-h">2. Future EPS & valuation</h2>
          <div className="dcf-grid">
            <Field id="g" label="Annual EPS growth (%)" value={form.g} onChange={set("g")} unit="%" error={chk.growth} hint={`A scenario assumption, from ${LIMITS.growthMin}% to ${LIMITS.growthMax}%.`} />
            <Field id="pe" label="Target P/E multiple (x)" help={HELP.target} value={form.pe} onChange={set("pe")} unit="x" error={chk.targetPe} hint="The multiple assumed at the end of the period." />
            <div className={"dcf-f" + (chk.years ? " has-err" : "")}>
              <label htmlFor="eps-n">Projection period (years)<span className="req" aria-hidden="true">*</span></label>
              <div className="eps-years">
                <input type="range" min={LIMITS.yearsMin} max={LIMITS.yearsMax} step={1} value={slider} aria-label="Projection period in years, slider" onChange={(e) => set("n")(e.target.value)} />
                <div className="dcf-in"><input id="eps-n" inputMode="numeric" value={form.n} onChange={(e) => set("n")(e.target.value)} aria-invalid={!!chk.years} aria-describedby={chk.years ? "eps-n-err" : undefined} maxLength={3} /><span className="unit">yrs</span></div>
              </div>
              {chk.years && <p className="dcf-err" id="eps-n-err" role="alert">{chk.years}</p>}
            </div>
          </div>
          {whyNone && <p className="dcf-note" role="note"><Icon name="info" />{whyNone}</p>}
          <div className="dcf-sum eps-sum eps-sum3" aria-live="polite">
            <div className="dcf-k"><span>Projected EPS after {Number.isInteger(n) ? n : "—"} years</span><b>{proj ? rs(proj.eps) : "—"}</b><small>current EPS × (1 + g)^n</small></div>
            <div className="dcf-k"><span>Implied future share price <Info g={HELP.implied} /></span><b>{proj ? rs(proj.price) : "—"}</b><small>projected EPS × target P/E</small></div>
            <div className="dcf-k"><span>Potential price return</span><b className={proj ? (proj.returnPct >= 0 ? "up" : "down") : ""}>{proj ? pctText(proj.returnPct) : "—"}</b><small>over the whole period</small></div>
          </div>
          <p className="faint">Price return excludes dividends, taxes and transaction costs. This is a scenario calculation, not a price forecast.</p>
          <div className="dcf-opts"><button className="btn sm ghost" type="button" onClick={reset}>Reset calculator</button></div>
        </section>

        {proj && pts && (<>
          <section className="card" aria-labelledby="eps-sc-h">
            <h2 id="eps-sc-h">Bear, Base and Bull</h2>
            <div className="eps-cases">
              {cases.map(({ k, label, c, gk, pk }) => {
                const cc = checkCase(c, n), p = project(a.e, a.px, c, n), pg = pegOf(a.pe.value, c.growth);
                return (
                  <div key={k} className={"eps-case " + k} role="group" aria-label={`${label} case`}>
                    <h3>{label}{k === "base" && <span className="faint"> (the inputs above)</span>}</h3>
                    <label>Growth (%)<input inputMode="decimal" value={form[gk]} onChange={(e) => set(gk)(e.target.value)} aria-invalid={!!cc.growth} /></label>
                    <label>Target P/E (x)<input inputMode="decimal" value={form[pk]} onChange={(e) => set(pk)(e.target.value)} aria-invalid={!!cc.targetPe} /></label>
                    {(cc.growth || cc.targetPe) && <p className="dcf-err" role="alert">{cc.growth || cc.targetPe}</p>}
                    <dl><dt>Projected EPS</dt><dd>{p ? rs(p.eps) : "—"}</dd><dt>Implied price</dt><dd>{p ? rs(p.price) : "—"}</dd>
                      <dt>Price return</dt><dd>{p ? Pc(p.returnPct, p.returnPct >= 0 ? "up" : "down") : "—"}</dd><dt>PEG <Info g={HELP.peg} /></dt><dd>{pg.value == null ? "—" : fix2(pg.value)}</dd></dl>
                  </div>);
              })}
            </div>
            <p className="faint">The Base case is the assumptions in section 2; edit it here or there. Bear and Bull are yours to set.</p>
          </section>

          <section className="card" aria-labelledby="eps-sens-h">
            <h2 id="eps-sens-h">Sensitivity</h2>
            <div className="dcf-opts eps-gridopts"><label className="dcf-tog">Show: <select value={gridMode} onChange={(e) => setGridMode(e.target.value as "price" | "return")}><option value="price">Implied future price (₹)</option><option value="return">Potential price return (%)</option></select></label></div>
            {grid && <div className="dcf-sens"><div className="eps-tw"><table><caption className="sr-only">{gridMode === "price" ? "Implied future price" : "Potential price return"} for each EPS growth rate (rows) and target P/E (columns) after {n} years</caption>
              <thead><tr><th scope="col">Growth ↓ · Target P/E →</th>{gCols.map((c) => <th key={c} scope="col" className={"num" + (c === base.targetPe ? " cur" : "")}>{nf(c, c % 1 ? 1 : 0)}x</th>)}</tr></thead>
              <tbody>{gRows.map((rv, i) => <tr key={rv}><th scope="row" className={rv === base.growth ? "cur" : ""}>{nf(rv, rv % 1 ? 1 : 0)}%</th>
                {grid[i].map((cell, j) => <td key={j} className={"num " + (cell ? (cell.returnPct > 0 ? "s-gain" : cell.returnPct < 0 ? "s-loss" : "") : "") + (rv === base.growth && gCols[j] === base.targetPe ? " base" : "")}
                  title={cell ? `${rs(cell.price)}, ${pctText(cell.returnPct)}` : undefined}>{cell ? (gridMode === "price" ? rs(cell.price) : pctText(cell.returnPct)) : "—"}</td>)}</tr>)}</tbody></table></div>
              <p className="faint">Outlined cell: your case. Green with a plus sign: a price above today's; red with a minus sign: below. Rows are EPS growth a year, columns the target P/E, after {n} years.</p></div>}
          </section>

          <section className="card" aria-labelledby="eps-ch-h">
            <h2 id="eps-ch-h">Year by year</h2>
            <div className="eps-charts">
              <Chart title="Projected EPS" unitLabel="₹ per share" kind="bar" pts={pts.map((p) => p.eps)} sel={selYear} setSel={setSel} fmt={(v) => nf(v, v < 100 ? 1 : 0)} years={n} />
              <Chart title="Implied price path" unitLabel={`₹, at a ${nf(base.targetPe, 1)}x P/E each year`} kind="line" pts={pts.map((p) => p.price)} sel={selYear} setSel={setSel} fmt={(v) => nf(v, 0)} years={n} />
            </div>
            <p className="eps-read" aria-live="polite">Year {selYear}{selYear === 0 ? " (today)" : ""}: EPS <b>{rs(pts[selYear].eps)}</b> · implied price <b>{rs(pts[selYear].price)}</b>{selYear > 0 && <> · {pctText(((pts[selYear].price / a.px) - 1) * 100)} on today's price</>}</p>
            <p className="faint">Hover, touch or use the arrow keys on a chart to read a year. The price path applies the same target P/E to every year's EPS, so it is not a forecast of where the price will be along the way.</p>
          </section>

          <section className="card" aria-labelledby="eps-an-h">
            <h2 id="eps-an-h">Growth, PEG and the reverse question</h2>
            <div className="dcf-kv">
              <span>PEG ratio <Info g={HELP.peg} /> <b>{peg.value == null ? "—" : fix2(peg.value)}</b></span>
              <span>P/E {mult(a.pe.value)} ÷ assumed growth {pcA(base.growth)}</span>
            </div>
            <p className="faint">{peg.value == null ? `PEG is not shown: ${peg.reason?.toLowerCase()}` : "PEG uses the growth rate assumed above, not a history, and says nothing where growth is zero or negative or the P/E is not meaningful. FinLit's PEG on company pages uses 5-year profit growth instead."}</p>
            <div className="dcf-grid eps-rev">
              <Field id="tp" label="Target price (₹), to work backwards" value={form.tp} onChange={set("tp")} required={false} hint={`Uses the target P/E (${nf(base.targetPe, 1)}x) and ${n} years above.`} />
              <div className="dcf-f"><span className="eps-revlabel">EPS growth needed a year</span>
                <output className="eps-revout" aria-live="polite">{req == null ? "Enter a target price" : req.value == null ? "Not available" : pcA(req.value)}</output>
                {req && req.value == null && <p className="dcf-err">{req.reason}</p>}
                {req && req.value != null && <p className="dcf-hint faint">{req.value > LIMITS.growthMax ? `Above the ${LIMITS.growthMax}% a year this calculator accepts, which suggests the target is very demanding for ${n} years. ` : ""}Compared with {pcA(base.growth)} a year in your Base case. Formula: ((target price ÷ target P/E) ÷ EPS)^(1/n) − 1.</p>}
              </div>
            </div>
          </section>
        </>)}

        <section className="card" aria-labelledby="eps-sh-h">
          <h2 id="eps-sh-h">Save, share and export</h2>
          <div className="dcf-acts"><button className="btn" type="button" onClick={copyLink}><Icon name="arrow" /> Copy share link</button>
            <button className="btn" type="button" onClick={csv}>Download CSV (Excel)</button>
            <button className="btn" type="button" onClick={() => window.print()}>Print / PDF</button></div>
          <p className="faint">The link carries your inputs in the address and nothing else.</p>
        </section>

        <section className="card" aria-labelledby="eps-f-h">
          <h2 id="eps-f-h">Formulas</h2>
          <div className="eps-tw"><table><caption className="sr-only">Formulas used by the calculator</caption><thead><tr><th scope="col">Measure</th><th scope="col">Formula</th></tr></thead>
            <tbody>{FORMULAS.map(([k, v]) => <tr key={k}><th scope="row">{k}</th><td>{v}</td></tr>)}</tbody></table></div>
          <p className="faint">g = annual EPS growth, n = number of years. The price is worked from the unrounded EPS; figures are rounded to 2 decimals only for display.</p>
        </section>
        <p className="faint dcf-disc">Information only, not investment advice. Results are scenarios from the numbers you enter, not forecasts. <Link to="/glossary#earnings-per-share-eps">What is EPS?</Link></p>
      </div>
    </>
  );
}
