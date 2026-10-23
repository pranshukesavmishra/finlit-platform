// Fund Compare, head to head: two funds of one category over 1, 3, 5 or 10 years, on four questions (returns, risk, consistency, costs), each
// fund also against its category's average. The default view of /funds/compare (the 2 to 4 scheme compare is /funds/compare?ids=...).
// Data: /api/mf-compare (backend/finlit/mf_compare.py). Every figure states its period and source; a missing one says why. Information only.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { PageArt } from "../components/PageArt";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { dateIN, nf } from "../lib/format";
import { factValueText, searchOptions, type FactVal } from "../lib/mf";
import {
  CARDS, PERIODS, pickCategory, cardTeaser, consistencyLine, costsLine, h2hToParams, parseH2H, pct, periodBlock, periodWords, returnsLine, riskLine, rupees, share,
  shortName, signedPct, useCompareCategories, useCompareFunds, useHeadToHead, type Card, type CostFacts, type H2HState, type HeadToHead, type Side,
} from "../lib/mfCompare";
import { FundChart, SERIES_STYLE } from "../mf/FundChart";
import { Foot, GTerm } from "../mf/Bits";
import "../styles/mf.css";
import "../styles/mfcompare.css";

const SIDES: Side[] = ["a", "b", "cat"];
const IDX: Record<Side, number> = { a: 0, b: 1, cat: 2 };
const Swatch = ({ i }: { i: number }) => <i className="mf-sw" style={{ borderColor: SERIES_STYLE[i].color, borderTopStyle: i === 0 ? "solid" : i === 1 ? "dashed" : "dotted" }} aria-hidden="true" />;

// ================================================================================================ a searchable menu

type Opt = { value: string; label: string; sub?: string; count?: number };
const SHOW_MAX = 150;

function SearchSelect({ label, hint, value, items, onChange, placeholder, disabled, swatch }: {
  label: string; hint?: string; value: string; items: Opt[]; onChange: (v: string) => void; placeholder: string; disabled?: boolean; swatch?: number;
}) {
  const [open, setOpen] = useState(false), [q, setQ] = useState(""), [at, setAt] = useState(0);
  const root = useRef<HTMLDivElement>(null), input = useRef<HTMLInputElement>(null), btn = useRef<HTMLButtonElement>(null);
  const id = useId();
  const all = useMemo(() => searchOptions(items, q, (i) => `${i.label} ${i.sub || ""}`), [items, q]);
  const shown = all.slice(0, SHOW_MAX);
  const current = items.find((i) => i.value === value);
  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const out = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", out);
    return () => document.removeEventListener("mousedown", out);
  }, [open]);
  useEffect(() => { setAt(0); }, [q]);
  useEffect(() => { if (open) document.getElementById(`${id}-${at}`)?.scrollIntoView({ block: "nearest" }); }, [at, id, open]);
  const choose = (v: string) => { onChange(v); setOpen(false); setQ(""); btn.current?.focus(); };
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setAt((a) => Math.min(shown.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); if (shown[at]) choose(shown[at].value); }
    else if (e.key === "Escape") { setOpen(false); btn.current?.focus(); }
  };
  return (
    <div className="mf-pick mf-h2h-pick" ref={root}>
      <span className="label" id={`${id}-l`}>{swatch != null && <Swatch i={swatch} />}{label}</span>
      <button type="button" ref={btn} className="mf-pick-b" aria-haspopup="listbox" aria-expanded={open} aria-labelledby={`${id}-l ${id}-v`} disabled={disabled} onClick={() => setOpen((o) => !o)}>
        <span id={`${id}-v`}>{current ? current.label : placeholder}</span><span aria-hidden="true">▾</span>
      </button>
      {hint && <small className="faint mf-h2h-hint">{hint}</small>}
      {open && (
        <div className="mf-pick-pop mf-h2h-pop">
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={key} placeholder="Type to search…" aria-label={`Search: ${label}`}
            role="combobox" aria-expanded="true" aria-controls={`${id}-list`} aria-activedescendant={shown.length ? `${id}-${at}` : undefined} autoComplete="off" spellCheck={false} />
          <ul id={`${id}-list`} role="listbox" aria-label={label}>
            {shown.map((i, n) => (
              <li key={i.value} id={`${id}-${n}`} role="option" aria-selected={i.value === value} className={at === n ? "on" : ""} onMouseDown={(e) => { e.preventDefault(); choose(i.value); }}>
                <span>{i.label}{i.sub && <small className="mf-h2h-sub">{i.sub}</small>}</span>{i.count != null && <small>{i.count.toLocaleString("en-IN")}</small>}
              </li>))}
            {!shown.length && <li className="mf-pick-none" role="presentation">Nothing matches “{q}”.</li>}
            {all.length > SHOW_MAX && <li className="mf-pick-none" role="presentation">{all.length - SHOW_MAX} more: type to narrow the list.</li>}
          </ul>
        </div>)}
    </div>
  );
}

// ================================================================================================ small pieces

/** A figure, or a dash that says why there is none (on hover, and to screen readers). */
function Val({ v, why, fmt = pct }: { v: number | null | undefined; why?: string | null; fmt?: (v: number) => string }) {
  if (v == null) return <span className="mf-na" title={why || undefined} aria-label={why ? `No figure. ${why}` : "No figure"}>—</span>;
  return <>{fmt(v)}</>;
}
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "pos" : "neg");

function Table({ d, caption, rows }: { d: HeadToHead; caption: string; rows: { label: React.ReactNode; cell: (s: Side) => React.ReactNode; head?: boolean; sides?: Side[] }[] }) {
  return (
    <div className="tw"><table className="mf-cmp mf-h2h-t">
      <caption className="sr-only">{caption}</caption>
      <thead><tr><th scope="col"><span className="sr-only">Measure</span></th>
        {SIDES.map((s) => <th scope="col" key={s}><Swatch i={IDX[s]} />{s === "cat" ? "Category average" : s === "a" ? "Fund A" : "Fund B"}<small>{s === "cat" ? d.category.short : shortName(d.funds[s].name)}</small></th>)}</tr></thead>
      <tbody>{rows.map((r, i) => r.head
        ? <tr key={i} className="mf-grp"><th scope="colgroup" colSpan={4}>{r.label}</th></tr>
        : <tr key={i}><th scope="row">{r.label}</th>{SIDES.map((s) => <td key={s}>{!r.sides || r.sides.includes(s) ? r.cell(s) : <span className="faint">·</span>}</td>)}</tr>)}</tbody>
    </table></div>
  );
}

const Verdict = ({ text }: { text: string }) => <p className="mf-h2h-verdict" role="status"><Icon name="spark" /><span>{text}</span></p>;

/** The reasons figures are missing, once each, under a table. */
function Whys({ d }: { d: HeadToHead }) {
  const lines = [d.why.a && `Fund A: ${d.why.a}`, d.why.b && `Fund B: ${d.why.b}`, !d.category.pending && d.category.why && `Category average: ${d.category.why}`].filter(Boolean) as string[];
  return lines.length ? <ul className="mf-h2h-whys faint">{lines.map((l) => <li key={l}>{l}</li>)}</ul> : null;
}

// ================================================================================================ the four cards

function ReturnsPanel({ d, names }: { d: HeadToHead; names: { a: string; b: string } }) {
  const r = d.returns, roll = r.rolling, perYear = r.kind === "cagr", rollYear = roll.kind === "cagr";
  const series = (pts: HeadToHead["returns"]["growth"]) => SIDES.filter((s) => pts[s]).map((s) => ({ key: s, label: s === "cat" ? "Category average" : names[s as "a" | "b"], t: pts[s]!.t, v: pts[s]!.v }));
  const growth = series(r.growth), rolling = series(roll.chart);
  return (
    <>
      <Verdict text={returnsLine(d, names)} />
      <Table d={d} caption={`Returns over ${periodWords(d.period)}`} rows={[
        { label: perYear ? <><GTerm id="cagr-compound-annual-growth-rate">Return per year (CAGR)</GTerm></> : "Return over 1 year (total)", cell: (s) => <b className={tone(r.funds[s].value)}><Val v={r.funds[s].value} why={r.funds[s].why} fmt={(v) => signedPct(v, 2)} /></b> },
        { label: "₹10,000 invested became", cell: (s) => <Val v={r.funds[s].growth} why={r.funds[s].why} fmt={rupees} /> },
        { label: <>Rolling {roll.label} returns{rollYear ? ", per year" : " (total change)"}</>, head: true, cell: () => null },
        { label: "Lowest", cell: (s) => <><Val v={roll.funds[s].min} why={roll.funds[s].why} fmt={(v) => signedPct(v)} />{roll.funds[s].minAt && <small className="faint"> to {dateIN(roll.funds[s].minAt!)}</small>}</> },
        { label: "Median (middle)", cell: (s) => <Val v={roll.funds[s].median} why={roll.funds[s].why} fmt={(v) => signedPct(v)} /> },
        { label: "Highest", cell: (s) => <><Val v={roll.funds[s].max} why={roll.funds[s].why} fmt={(v) => signedPct(v)} />{roll.funds[s].maxAt && <small className="faint"> to {dateIN(roll.funds[s].maxAt!)}</small>}</> },
        { label: "Windows with a gain", cell: (s) => <Val v={roll.funds[s].positive} why={roll.funds[s].why} fmt={(v) => `${nf(v, 0)}%`} /> },
        { label: "Windows measured", cell: (s) => roll.funds[s].count ? roll.funds[s].count.toLocaleString("en-IN") : <Val v={null} why={roll.funds[s].why} /> },
      ]} />
      <Whys d={d} />
      {growth.length > 0 && <div className="mf-h2h-chart"><h4 className="mf-h4">Growth of ₹10,000</h4>
        <FundChart series={growth} base={10000} format={rupees} label={`Value of ₹10,000 invested on ${d.from ? dateIN(d.from) : "the start date"}, NAV only`} />
        <p className="faint mf-fine">Each line starts at ₹10,000 on the fund's NAV of {d.from ? dateIN(d.from) : "the start date"} (or the NAV just before it) and follows the NAV. NAV already counts the fund's costs; taxes and exit loads are not taken off.</p></div>}
      {rolling.length > 0 && <div className="mf-h2h-chart"><h4 className="mf-h4">Rolling {roll.label} returns</h4>
        <FundChart series={rolling} base={0} format={(v) => signedPct(v)} label={`Return over each ${roll.label} window ending on the day shown`} />
        <p className="faint mf-fine">Each point is the {rollYear ? "per-year return" : "total return"} over the {roll.label} that ended that day, for every trading day of the period with a whole window behind it. A fund whose line stays high and narrow did well whenever someone happened to invest; wide swings mean the start day mattered a lot.</p></div>}
    </>
  );
}

function RiskPanel({ d, names }: { d: HeadToHead; names: { a: string; b: string } }) {
  const f = d.risk.funds;
  return (
    <>
      <Verdict text={riskLine(d, names)} />
      <Table d={d} caption={`Risk over ${periodWords(d.period)}`} rows={[
        { label: <><GTerm id="volatility">Volatility</GTerm>, a year</>, cell: (s) => <Val v={f[s].volatility.value} why={f[s].volatility.why} fmt={(v) => pct(v, 2)} /> },
        { label: "Downside deviation, a year", cell: (s) => <Val v={f[s].downside.value} why={f[s].downside.why} fmt={(v) => pct(v, 2)} /> },
        { label: <><GTerm id="drawdown">Largest fall</GTerm> (from a high)</>, cell: (s) => { const m = f[s].maxDrawdown; return <><b className={tone(m.value)}><Val v={m.value} why={m.why} fmt={(v) => pct(v, 2)} /></b>
          {m.peak && m.trough && <small className="faint mf-h2h-dates">{dateIN(m.peak)} to {dateIN(m.trough)}; {m.recovered ? `back to the high on ${dateIN(m.recovered)}` : "not back to the high yet"}</small>}</>; } },
        { label: "Worst calendar month", cell: (s) => <><span className={tone(f[s].worstMonth.value)}><Val v={f[s].worstMonth.value} why={f[s].worstMonth.why} fmt={(v) => signedPct(v)} /></span>{f[s].worstMonth.month && <small className="faint"> {f[s].worstMonth.month}</small>}</> },
        { label: "Best calendar month", cell: (s) => <><span className={tone(f[s].bestMonth.value)}><Val v={f[s].bestMonth.value} why={f[s].bestMonth.why} fmt={(v) => signedPct(v)} /></span>{f[s].bestMonth.month && <small className="faint"> {f[s].bestMonth.month}</small>}</> },
        { label: <><GTerm id="sharpe-ratio">Sharpe ratio</GTerm> <small className="faint">(at an assumed {nf(d.risk.riskFree, 0)}% risk-free)</small></>, cell: (s) => <Val v={f[s].sharpe.value} why={f[s].sharpe.why} fmt={(v) => (v < 0 ? "−" : "") + nf(Math.abs(v), 2)} /> },
      ]} />
      <Whys d={d} />
      <p className="faint mf-fine">Volatility is how much the NAV swings day to day, as a yearly figure (standard deviation of daily NAV changes × √252). Downside deviation counts only the falls. The largest fall is the deepest drop from a NAV high to a later low inside the period. {d.risk.note} All of these describe the past, not what comes next.</p>
    </>
  );
}

function Split({ a, b, n, label }: { a: number; b: number; n: number; label: string }) {
  if (!n) return null;
  const pa = (100 * a) / n, pb = (100 * b) / n;
  return (
    <div className="mf-h2h-split" role="img" aria-label={`${label}: Fund A ahead in ${a} of ${n}, Fund B in ${b}${n - a - b ? `, level in ${n - a - b}` : ""}.`}>
      <span style={{ width: `${pa}%`, background: SERIES_STYLE[0].color }} />
      <span style={{ width: `${100 - pa - pb}%` }} className="mf-h2h-tie" />
      <span style={{ width: `${pb}%`, background: SERIES_STYLE[1].color }} />
    </div>
  );
}

function ConsistencyPanel({ d, names }: { d: HeadToHead; names: { a: string; b: string } }) {
  const c = d.consistency, w = c.window.label;
  const tile = (title: React.ReactNode, t: { a: number; b: number; n: number; why: string | null }, unit: string) => (
    <div className="mf-tile">
      <dt>{title}</dt>
      <dd>{t.n ? <>
        <span className="mf-h2h-score"><b><Swatch i={0} />A {t.a.toLocaleString("en-IN")}</b><b><Swatch i={1} />B {t.b.toLocaleString("en-IN")}</b></span>
        <Split a={t.a} b={t.b} n={t.n} label={String(title)} />
        <small className="faint">of {t.n.toLocaleString("en-IN")} {unit}{t.n - t.a - t.b ? `, ${t.n - t.a - t.b} level` : ""}</small></>
        : <small className="mf-why">{t.why || "Nothing to count in this period."}</small>}</dd>
    </div>
  );
  const vs = (k: "a" | "b") => c.vsCategory[k];
  return (
    <>
      <Verdict text={consistencyLine(d, names)} />
      <dl className="mf-ret3 mf-h2h-tiles">
        {tile(`Ahead in ${w} windows`, c.rolling, `${w} windows`)}
        {tile("Calendar months won", c.months, "whole months")}
        {tile("Calendar years won", c.years, "whole years")}
      </dl>
      <div className="mf-h2h-vs">
        <h4 className="mf-h4">Ahead of the category average</h4>
        <ul>{(["a", "b"] as const).map((k) => (
          <li key={k}><Swatch i={IDX[k]} /><span>{names[k]}</span>
            <b>{vs(k).beat != null && vs(k).n ? share(vs(k).beat!, vs(k).n) : <Val v={null} why={vs(k).why} />}</b>
            <small className="faint">of the {w} windows</small></li>))}</ul>
      </div>
      {c.years.rows.length > 0 && (
        <div className="tw"><table className="mf-cmp mf-h2h-t mf-h2h-years">
          <caption className="sr-only">Return in each whole calendar year of the period</caption>
          <thead><tr><th scope="col">Year</th><th scope="col"><Swatch i={0} />Fund A</th><th scope="col"><Swatch i={1} />Fund B</th><th scope="col"><Swatch i={2} />Category average</th><th scope="col">Ahead</th></tr></thead>
          <tbody>{c.years.rows.map((y) => (
            <tr key={y.year}><th scope="row">{y.year}</th>
              <td className={tone(y.a)}><Val v={y.a} fmt={(v) => signedPct(v)} /></td><td className={tone(y.b)}><Val v={y.b} fmt={(v) => signedPct(v)} /></td><td className={tone(y.cat)}><Val v={y.cat} fmt={(v) => signedPct(v)} /></td>
              <td>{y.a == null || y.b == null ? "—" : Math.abs(y.a - y.b) < 0.005 ? "Level" : y.a > y.b ? "A" : "B"}</td></tr>))}</tbody>
        </table></div>)}
      <Whys d={d} />
      <p className="faint mf-fine">A {w} window is the {w} ending on one trading day; every trading day of the period with a whole window behind it counts once. Calendar months and years count only those wholly inside the period (the first, part-covered one and the unfinished current one are left out). Being ahead often in the past says nothing certain about the future.</p>
    </>
  );
}

const COST_ROWS: { k: keyof CostFacts; label: React.ReactNode }[] = [
  { k: "ter", label: <GTerm id="expense-ratio">Expense ratio (TER), a year</GTerm> }, { k: "exitLoad", label: <GTerm id="exit-load">Exit load</GTerm> },
  { k: "aum", label: "Fund size (AUM)" }, { k: "benchmark", label: "Benchmark index" }, { k: "managers", label: "Fund managers" },
  { k: "riskometer", label: "Risk-o-meter" }, { k: "launchDate", label: "Launch date" },
];

function Fact({ f }: { f: FactVal }) {
  const text = factValueText(f);
  if (!text) { const why = "unavailable" in f ? f.unavailable : "The source gives no value."; return <span className="mf-na" title={why}>—<small className="mf-why mf-h2h-dates">{why}</small></span>; }
  return <>{text}{!("unavailable" in f) && (f.asOf || f.source) && <small className="faint mf-h2h-dates">{[f.asOf ? `As of ${dateIN(f.asOf)}` : "", f.source || ""].filter(Boolean).join(" · ")}</small>}</>;
}

function CostsPanel({ d, names }: { d: HeadToHead; names: { a: string; b: string } }) {
  const f = d.costs.funds;
  return (
    <>
      <Verdict text={costsLine(d, names)} />
      <div className="tw"><table className="mf-cmp mf-h2h-t">
        <caption className="sr-only">Costs and fund facts</caption>
        <thead><tr><th scope="col"><span className="sr-only">Fact</span></th>{(["a", "b"] as const).map((k) => <th scope="col" key={k}><Swatch i={IDX[k]} />Fund {k.toUpperCase()}<small>{names[k]}</small></th>)}</tr></thead>
        <tbody>
          {COST_ROWS.map((r) => <tr key={r.k}><th scope="row">{r.label}</th>{(["a", "b"] as const).map((k) => <td key={k}><Fact f={f[k][r.k] as FactVal} /></td>)}</tr>)}
          <tr className="mf-grp"><th scope="colgroup" colSpan={3}>Excess return over the category average, a year ({periodWords(d.period)})</th></tr>
          <tr><th scope="row">Fund minus category average</th>{(["a", "b"] as const).map((k) => <td key={k}><b className={tone(d.costs.alpha[k].value)}><Val v={d.costs.alpha[k].value} why={d.costs.alpha[k].why} fmt={(v) => `${v < 0 ? "−" : v > 0 ? "+" : ""}${nf(Math.abs(v), 2)} points`} /></b></td>)}</tr>
        </tbody>
      </table></div>
      <Whys d={d} />
      <p className="faint mf-fine">{d.costs.alphaNote} The expense ratio shown is the {d.funds.a.plan === d.funds.b.plan ? d.funds.a.plan : "each fund's own"} plan's; it is already taken out of the NAV, so every return on this page is after it.</p>
    </>
  );
}

// ================================================================================================ the page

export function FundHeadToHead() {
  useDocTitle("Fund Compare", "Two mutual funds of the same category, head to head over 1, 3, 5 or 10 years: returns, risk, consistency and costs, each against the category average. Information only.");
  const [sp, setSp] = useSearchParams();
  const s = useMemo(() => parseH2H(sp), [sp]);
  const cats = useCompareCategories();
  const category = pickCategory(cats.data?.categories, s.category)?.name || s.category;
  const funds = useCompareFunds(category, s.plan);
  const set = (patch: Partial<H2HState>) => setSp(h2hToParams({ ...s, category, ...patch }), { replace: true });
  const list = funds.data?.funds || [];
  const fa = list.find((f) => f.code === s.a), fb = list.find((f) => f.code === s.b);
  const dataDate = funds.data?.dataDate || cats.data?.dataDate || null;
  const blocked = useMemo(() => Object.fromEntries(PERIODS.map((p) => [p, periodBlock(p, [fa, fb], dataDate)])) as Record<string, string | null>, [fa, fb, dataDate]);
  const h = useHeadToHead(s.a, s.b, s.period);
  const d = h.data;
  const stale = !!d && (d.funds.a.code !== s.a || d.funds.b.code !== s.b || d.period !== s.period);

  const catItems: Opt[] = useMemo(() => (cats.data?.categories || []).filter((c) => (s.plan === "Direct" ? c.direct : c.regular) >= 2)
    .map((c) => ({ value: c.name, label: c.short, sub: c.group, count: s.plan === "Direct" ? c.direct : c.regular })), [cats.data, s.plan]);
  const fundItems = (other: number): Opt[] => list.filter((f) => f.code !== other).map((f) => ({ value: String(f.code), label: shortName(f.name), sub: `${f.amc.replace(/\s*mutual fund\s*$/i, "")}${f.launch ? ` · since ${dateIN(f.launch, { month: "short", year: "numeric" })}` : ""}` }));
  const names = d ? { a: shortName(d.funds.a.name), b: shortName(d.funds.b.name) } : { a: "Fund A", b: "Fund B" };
  const errText = h.error ? (h.error.status === 400 || h.error.status === 404 ? h.error.message : h.error.status === 503 && h.error.body.status === "demo" ? h.error.message : "This comparison is unavailable right now. Please try again in a moment.") : "";

  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="portfolio" />
        <div className="eyebrow">Mutual funds</div><h1>Fund Compare</h1><p>Two funds of the same category, head to head: returns, risk, consistency and costs over 1, 3, 5 or 10 years, each also against the category average. Information only, never advice.</p></div></section>
      <div className="wrap mf mf-h2h">
        <section className="card mf-card mf-h2h-setup" aria-labelledby="h2h-h">
          <div className="card-h"><h3 id="h2h-h"><span className="ci"><Icon name="compare" /></span>Compare performance, consistency and risk</h3>
            <Link className="mf-linkbtn" to="/funds/compare?ids=">Compare up to 4 schemes instead</Link></div>
          <div className="mf-h2h-row">
            <SearchSelect label="Mutual fund category" hint="Compare funds within the same category" value={category} items={catItems} placeholder={cats.isLoading ? "Loading categories…" : "Choose a category"}
              disabled={!catItems.length} onChange={(v) => set({ category: v, a: 0, b: 0 })} />
            <div className="mf-seg-w"><span className="label" id="h2h-plan">Plan</span>
              <div className="seg" role="group" aria-labelledby="h2h-plan">{(["Direct", "Regular"] as const).map((p) => <button key={p} type="button" aria-pressed={s.plan === p} onClick={() => set({ plan: p, a: 0, b: 0 })}>{p}</button>)}</div>
              <small className="faint mf-h2h-hint">Growth option of each fund</small></div>
          </div>
          <div className="mf-h2h-pair">
            <SearchSelect label="Fund A" swatch={0} value={s.a ? String(s.a) : ""} items={fundItems(s.b)} disabled={!list.length} onChange={(v) => set({ a: Number(v) })}
              placeholder={!category ? "Choose a category first" : funds.isLoading ? "Loading funds…" : `Choose from ${list.length.toLocaleString("en-IN")} funds`} />
            <button type="button" className="mf-x mf-h2h-swap" aria-label="Swap Fund A and Fund B" title="Swap Fund A and Fund B" disabled={!s.a && !s.b} onClick={() => set({ a: s.b, b: s.a })}>⇄</button>
            <SearchSelect label="Fund B" swatch={1} value={s.b ? String(s.b) : ""} items={fundItems(s.a)} disabled={!list.length} onChange={(v) => set({ b: Number(v) })}
              placeholder={!category ? "Choose a category first" : funds.isLoading ? "Loading funds…" : `Choose from ${list.length.toLocaleString("en-IN")} funds`} />
          </div>
          <div className="mf-seg-w"><span className="label" id="h2h-period">Investment period</span>
            <div className="seg" role="group" aria-labelledby="h2h-period">{PERIODS.map((p) => (
              <button key={p} type="button" aria-pressed={s.period === p} disabled={!!blocked[p] && s.period !== p} title={blocked[p] || undefined} onClick={() => set({ period: p })}>{p}</button>))}</div>
            {PERIODS.some((p) => blocked[p]) && <small className="faint mf-h2h-hint">{PERIODS.filter((p) => blocked[p]).join(", ")} not available: {blocked[PERIODS.filter((p) => blocked[p]).slice(-1)[0]]}</small>}
          </div>
        </section>

        {!(s.a && s.b) ? (
          <div className="pm-empty mf-empty"><b>Choose Fund A and Fund B.</b>
            <p>Pick a category, then two of its funds. Funds are compared on their Growth option and the same plan, over the same days, and each against the average of its category.</p></div>
        ) : h.error && !d ? (
          <div className="card mf-card" role="alert"><p>{errText}</p>{h.error.status >= 500 && <button className="btn" onClick={() => h.refetch()}>Try again</button>}</div>
        ) : !d ? (
          <div className="card" aria-busy="true"><div className="skeleton" style={{ height: 360 }} /></div>
        ) : (
          <div aria-busy={h.isFetching || stale} className={stale ? "mf-h2h-stale" : undefined}>
            <section aria-labelledby="h2h-what">
              <div className="mf-h2h-head">
                <h2 id="h2h-what">Compare what matters</h2>
                <p className="muted">{d.from && d.to ? <>{dateIN(d.from)} to {dateIN(d.to)} ({periodWords(d.period)}), {d.funds.a.plan === d.funds.b.plan ? `${d.funds.a.plan} plan, ` : ""}Growth option.</> : "No common period."}</p>
              </div>
              <ul className="mf-h2h-legend" aria-label="Lines and columns">
                <li><Swatch i={0} /><span><b>A</b> <Link to={`/funds/${d.funds.a.code}`}>{names.a}</Link></span></li>
                <li><Swatch i={1} /><span><b>B</b> <Link to={`/funds/${d.funds.b.code}`}>{names.b}</Link></span></li>
                <li><Swatch i={2} /><span>Category average · {d.category.short}{d.category.members ? ` (${d.category.members} funds)` : ""}</span></li>
              </ul>
              <div className="mf-h2h-cards" role="group" aria-label="What to compare">
                {CARDS.map((c) => { const t = cardTeaser(c.id, d); return (
                  <button key={c.id} type="button" className="mf-h2h-card" aria-pressed={s.card === c.id} aria-controls="h2h-panel" onClick={() => set({ card: c.id as Card })}>
                    <span className="mf-h2h-ct">{c.title}</span><small>{c.sub}</small>{t && <em>{t}</em>}
                  </button>); })}
              </div>
            </section>
            {d.pending && <p className="mf-note" role="status"><Icon name="info" /><span>{d.category.why}</span></p>}
            {d.planNote && <p className="mf-note warn" role="note"><Icon name="alert" /><span>{d.planNote}</span></p>}
            <section id="h2h-panel" className="card mf-card mf-h2h-panel" aria-label={CARDS.find((c) => c.id === s.card)!.title}>
              {s.card === "returns" ? <ReturnsPanel d={d} names={names} /> : s.card === "risk" ? <RiskPanel d={d} names={names} /> : s.card === "consistency" ? <ConsistencyPanel d={d} names={names} /> : <CostsPanel d={d} names={names} />}
            </section>
            <div className="card mf-card mf-h2h-about">
              <h4 className="mf-h4">About the category average</h4>
              <p className="muted">{d.category.pending ? d.category.why : d.category.note || d.category.why}{d.category.membersAtStart != null && d.category.members ? ` ${d.category.membersAtStart} of the ${d.category.members} had a NAV on the first day of this period; younger funds join on their first NAV.` : ""} {d.category.survivorship}</p>
              {(d.funds.a.history.source === "mirror" || d.funds.b.history.source === "mirror") && <p className="faint mf-fine">Some NAV history here comes from a third-party mirror of AMFI data (api.mfapi.in), used only after its NAV for AMFI's latest date was checked against AMFI's own. AMFI's own history is kept for five years, so the 10 year view always uses the mirror.</p>}
            </div>
          </div>
        )}
        <Foot facts={d || funds.data || cats.data || null} />
      </div>
    </>
  );
}
